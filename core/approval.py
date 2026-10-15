"""
Baton Supreme Connector — Command Approval System
For dangerous operations, the agent pauses and waits for user approval.
"""

import asyncio
import uuid
import time
from typing import Dict, Optional
from pydantic import BaseModel


class ApprovalRequest(BaseModel):
    id: str
    tool_name: str
    parameters: dict
    reason: str
    timestamp: float
    status: str = "pending"   # pending, approved, denied, expired


class ApprovalManager:
    """
    Manages a queue of pending command approvals.
    When enabled, dangerous tool calls are held here until the user
    explicitly approves or denies them from the dashboard.
    """

    def __init__(self, timeout_seconds: int = 300):
        self._pending: Dict[str, ApprovalRequest] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self.timeout_seconds = timeout_seconds
        self.enabled = False  # Disabled by default, toggled from Security Panel

    def request_approval(self, tool_name: str, parameters: dict, reason: str) -> str:
        """Creates a new approval request and returns its ID."""
        req_id = str(uuid.uuid4())[:8]
        self._pending[req_id] = ApprovalRequest(
            id=req_id,
            tool_name=tool_name,
            parameters=parameters,
            reason=reason,
            timestamp=time.time(),
        )
        self._events[req_id] = asyncio.Event()
        return req_id

    async def wait_for_decision(self, req_id: str) -> str:
        """Blocks until the user approves/denies, or timeout expires."""
        if req_id not in self._events:
            return "denied"

        try:
            await asyncio.wait_for(
                self._events[req_id].wait(),
                timeout=self.timeout_seconds
            )
            return self._pending[req_id].status
        except asyncio.TimeoutError:
            self._pending[req_id].status = "expired"
            return "expired"
        finally:
            self._cleanup(req_id)

    def approve(self, req_id: str) -> bool:
        if req_id in self._pending and self._pending[req_id].status == "pending":
            self._pending[req_id].status = "approved"
            self._events[req_id].set()
            return True
        return False

    def deny(self, req_id: str) -> bool:
        if req_id in self._pending and self._pending[req_id].status == "pending":
            self._pending[req_id].status = "denied"
            self._events[req_id].set()
            return True
        return False

    def get_pending(self) -> list:
        """Returns all pending approval requests."""
        self._cleanup_expired()
        return [
            req.dict() for req in self._pending.values()
            if req.status == "pending"
        ]

    def _cleanup(self, req_id: str):
        self._events.pop(req_id, None)

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            rid for rid, req in self._pending.items()
            if now - req.timestamp > self.timeout_seconds and req.status == "pending"
        ]
        for rid in expired:
            self._pending[rid].status = "expired"
            if rid in self._events:
                self._events[rid].set()


# Global singleton
approval_manager = ApprovalManager()


# ─── Dangerous tool check ────────────────────────────────────

DANGEROUS_TOOLS = ["shell_command", "write_file"]

def requires_approval(tool_name: str) -> bool:
    """Returns True if this tool requires user approval when approval mode is enabled."""
    return approval_manager.enabled and tool_name in DANGEROUS_TOOLS
