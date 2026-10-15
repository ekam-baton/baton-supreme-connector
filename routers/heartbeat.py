"""
Baton Supreme Connector — Heartbeat Scheduler
Proactive agent that wakes up at configurable intervals to check pending tasks,
send briefings, monitor repos, or any recurring autonomous work.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from core.security import verify_api_key
import asyncio
import uuid
import time
import json

router = APIRouter(prefix="/heartbeat", tags=["Heartbeat"], dependencies=[Depends(verify_api_key)])


class HeartbeatTask(BaseModel):
    name: str
    goal: str                          # Natural language goal for the agent
    interval_seconds: int = 3600       # Default: every hour
    model: str = "ollama/llama3"
    enabled: bool = True
    api_key: Optional[str] = None      # LLM provider key override


class HeartbeatEntry:
    def __init__(self, task: HeartbeatTask):
        self.id = str(uuid.uuid4())
        self.task = task
        self.created_at = time.time()
        self.last_run: Optional[float] = None
        self.run_count: int = 0
        self.last_result: Optional[str] = None
        self.running: bool = False
        self._cancel_event = asyncio.Event()


class HeartbeatScheduler:
    """
    A persistent background scheduler that periodically triggers the agent loop.
    Each registered task runs at its own interval.
    """

    def __init__(self):
        self._tasks: Dict[str, HeartbeatEntry] = {}
        self._background_tasks: Dict[str, asyncio.Task] = {}

    def register(self, task: HeartbeatTask) -> str:
        entry = HeartbeatEntry(task)
        self._tasks[entry.id] = entry
        # Start the background loop
        bg = asyncio.create_task(self._run_loop(entry))
        self._background_tasks[entry.id] = bg
        return entry.id

    def unregister(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id]._cancel_event.set()
            if task_id in self._background_tasks:
                self._background_tasks[task_id].cancel()
                del self._background_tasks[task_id]
            del self._tasks[task_id]
            return True
        return False

    def list_tasks(self) -> list:
        return [
            {
                "id": e.id,
                "name": e.task.name,
                "goal": e.task.goal,
                "interval_seconds": e.task.interval_seconds,
                "enabled": e.task.enabled,
                "last_run": e.last_run,
                "run_count": e.run_count,
                "last_result": e.last_result[:200] if e.last_result else None,
                "running": e.running,
            }
            for e in self._tasks.values()
        ]

    async def _run_loop(self, entry: HeartbeatEntry):
        """The core heartbeat loop for a single task."""
        while not entry._cancel_event.is_set():
            if entry.task.enabled:
                entry.running = True
                try:
                    result = await self._execute_agent_goal(entry)
                    entry.last_result = result
                    entry.last_run = time.time()
                    entry.run_count += 1
                except Exception as e:
                    entry.last_result = f"ERROR: {str(e)}"
                finally:
                    entry.running = False

            # Wait for the interval or cancellation
            try:
                await asyncio.wait_for(
                    entry._cancel_event.wait(),
                    timeout=entry.task.interval_seconds
                )
                break  # Cancel event was set
            except asyncio.TimeoutError:
                continue  # Interval elapsed, loop again

    async def _execute_agent_goal(self, entry: HeartbeatEntry) -> str:
        """Calls the agent loop internally to execute the heartbeat goal."""
        try:
            from routers.agent import run_agent_loop, AgentRequest

            request = AgentRequest(
                goal=f"[HEARTBEAT TASK: {entry.task.name}] {entry.task.goal}",
                model=entry.task.model,
                stream=False,
                api_key=entry.task.api_key,
            )
            response = await run_agent_loop(request)
            return response.final_answer
        except Exception as e:
            return f"Agent execution failed: {str(e)}"


# Global singleton
scheduler = HeartbeatScheduler()


# ─── API Endpoints ───────────────────────────────────────────

@router.post("/tasks")
async def create_heartbeat(task: HeartbeatTask):
    """Register a new recurring heartbeat task."""
    task_id = scheduler.register(task)
    return {"status": "created", "task_id": task_id, "name": task.name, "interval": task.interval_seconds}

@router.get("/tasks")
async def list_heartbeats():
    """List all registered heartbeat tasks."""
    return {"tasks": scheduler.list_tasks()}

@router.delete("/tasks/{task_id}")
async def delete_heartbeat(task_id: str):
    """Stop and remove a heartbeat task."""
    if scheduler.unregister(task_id):
        return {"status": "deleted", "task_id": task_id}
    raise HTTPException(status_code=404, detail="Task not found")

@router.post("/tasks/{task_id}/toggle")
async def toggle_heartbeat(task_id: str):
    """Enable or disable a heartbeat task without deleting it."""
    if task_id in scheduler._tasks:
        entry = scheduler._tasks[task_id]
        entry.task.enabled = not entry.task.enabled
        return {"status": "toggled", "task_id": task_id, "enabled": entry.task.enabled}
    raise HTTPException(status_code=404, detail="Task not found")
