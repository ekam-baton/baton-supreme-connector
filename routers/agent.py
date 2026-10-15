from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from core.security import verify_api_key
from core.memory_db import SQLiteSessionMemory
from core.sandbox import validate_command, validate_filepath
from core.soul import get_soul_prompt
from core.skills import get_skills_prompt
from core.approval import approval_manager, requires_approval
from services import browser
import litellm
import json
import asyncio
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

router = APIRouter(prefix="/agent", tags=["Agent"], dependencies=[Depends(verify_api_key)])

# SQLite-backed persistent memory (replaces in-memory dict)
memory_store = SQLiteSessionMemory()

# Maximum iterations the agent can run before being forced to stop
MAX_ITERATIONS = 15

# The system prompt that teaches the LLM how to use tools
SYSTEM_PROMPT = """You are Baton Supreme Agent — a powerful AI assistant with access to real tools.
You can execute shell commands, search the web, read/write files, browse websites, and more.

## Available Tools
You MUST respond with a JSON tool call when you need to use a tool. Use this exact format:

```json
{"tool": "tool_name", "parameters": {"param1": "value1"}}
```

Available tools:
- **shell_command**: Execute a shell command. Parameters: {"command": "string"}
- **web_search**: Search the web. Parameters: {"query": "string", "max_results": 5}
- **fetch_url**: Fetch and parse a URL. Parameters: {"url": "string"}
- **read_file**: Read a file. Parameters: {"filepath": "string"}
- **write_file**: Write content to a file. Parameters: {"filepath": "string", "content": "string"}
- **browser_screenshot**: Take a screenshot of a webpage. Parameters: {"url": "string"}
- **browser_get_text**: Get fully rendered text from a JS-heavy page. Parameters: {"url": "string"}
- **browser_click**: Click an element on a page. Parameters: {"url": "string", "selector": "css_selector"}

## Rules
1. Think step-by-step before acting. Explain your reasoning.
2. After each tool result, analyze it and decide your next action.
3. When you have enough information to answer the user's question, respond with your final answer in plain text (no JSON tool call).
4. If a tool fails, try an alternative approach.
5. NEVER run destructive commands (rm -rf, format, etc.).
6. Keep file paths reasonable — don't access system files.
"""


class AgentRequest(BaseModel):
    goal: str
    model: str = "ollama/llama3"
    session_id: Optional[str] = None
    stream: bool = False
    api_key: Optional[str] = None


class AgentResponse(BaseModel):
    session_id: str
    final_answer: str
    steps: List[Dict[str, Any]]
    iterations: int


async def execute_tool(tool_name: str, parameters: dict) -> dict:
    """Dispatches a tool call to the appropriate handler with safety checks."""
    try:
        if tool_name == "shell_command":
            cmd = parameters.get("command", "")
            # SAFETY CHECK
            check = validate_command(cmd)
            if not check.allowed:
                return {"error": check.reason, "blocked": True}
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                process.kill()
                return {"error": "Command timed out after 30 seconds"}
            
            return {
                "stdout": (stdout.decode() if stdout else "")[:3000],
                "stderr": (stderr.decode() if stderr else "")[:1000],
                "returncode": process.returncode
            }

        elif tool_name == "web_search":
            query = parameters.get("query", "")
            max_results = parameters.get("max_results", 5)
            def sync_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))
            results = await asyncio.to_thread(sync_search)
            return {"results": results}

        elif tool_name == "fetch_url":
            url = parameters.get("url", "")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                text = ' '.join(soup.stripped_strings)
                return {"text": text[:5000]}

        elif tool_name == "read_file":
            filepath = parameters.get("filepath", "")
            check = validate_filepath(filepath)
            if not check.allowed:
                return {"error": check.reason, "blocked": True}
            def sync_read():
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()[:10000]
            content = await asyncio.to_thread(sync_read)
            return {"content": content}

        elif tool_name == "write_file":
            filepath = parameters.get("filepath", "")
            content = parameters.get("content", "")
            check = validate_filepath(filepath)
            if not check.allowed:
                return {"error": check.reason, "blocked": True}
            def sync_write():
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return True
            await asyncio.to_thread(sync_write)
            return {"status": "success", "filepath": filepath, "bytes_written": len(content)}

        elif tool_name == "browser_screenshot":
            url = parameters.get("url", "")
            return await browser.take_screenshot(url)

        elif tool_name == "browser_get_text":
            url = parameters.get("url", "")
            return await browser.get_rendered_text(url)

        elif tool_name == "browser_click":
            url = parameters.get("url", "")
            selector = parameters.get("selector", "")
            return await browser.click_element(url, selector)

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        return {"error": str(e)}


def extract_tool_call(text: str) -> Optional[dict]:
    """Attempts to extract a JSON tool call from the LLM's response text."""
    # Try to find JSON in code blocks first
    import re
    code_block_match = re.search(r'```(?:json)?\s*\n?({.*?})\s*\n?```', text, re.DOTALL)
    if code_block_match:
        try:
            parsed = json.loads(code_block_match.group(1))
            if "tool" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
    
    # Try to find raw JSON with "tool" key
    json_match = re.search(r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if "tool" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
    
    return None


async def run_agent_loop(request: AgentRequest):
    """
    The core ReAct (Reason + Act) loop:
    1. Send goal + context to LLM
    2. LLM responds with reasoning + tool call
    3. Execute the tool
    4. Feed result back to LLM
    5. Repeat until LLM gives final answer or max iterations hit
    """
    # Session management
    session_id = request.session_id or memory_store.create_session()
    
    # Initialize conversation with dynamic system prompt
    dynamic_system_prompt = f"{SYSTEM_PROMPT}\n\n{get_soul_prompt()}\n\n{get_skills_prompt()}"
    messages = [{"role": "system", "content": dynamic_system_prompt}]
    
    # Load existing session history
    existing = memory_store.get_messages(session_id)
    if existing:
        messages.extend(existing)
    
    # Add the user's new goal
    messages.append({"role": "user", "content": request.goal})
    memory_store.add_message(session_id, "user", request.goal)
    
    steps = []
    
    for iteration in range(MAX_ITERATIONS):
        # Call the LLM
        try:
            response = await litellm.acompletion(
                model=request.model,
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
                api_key=request.api_key,
            )
            assistant_text = response.choices[0].message.content
        except Exception as e:
            steps.append({"type": "error", "detail": f"LLM call failed: {str(e)}"})
            break
        
        # Try to extract a tool call from the response
        tool_call = extract_tool_call(assistant_text)
        
        if tool_call is None:
            # No tool call found — the LLM is giving its final answer
            memory_store.add_message(session_id, "assistant", assistant_text)
            steps.append({"type": "final_answer", "content": assistant_text})
            
            return AgentResponse(
                session_id=session_id,
                final_answer=assistant_text,
                steps=steps,
                iterations=iteration + 1,
            )
        
        # Tool call found — execute it
        tool_name = tool_call.get("tool", "")
        tool_params = tool_call.get("parameters", {})
        
        steps.append({
            "type": "tool_call",
            "iteration": iteration + 1,
            "reasoning": assistant_text,
            "tool": tool_name,
            "parameters": tool_params,
        })
        
        # Check for command approval
        if requires_approval(tool_name):
            req_id = approval_manager.request_approval(tool_name, tool_params, assistant_text)
            
            steps.append({
                "type": "approval_pending",
                "iteration": iteration + 1,
                "tool": tool_name,
                "request_id": req_id
            })
            
            # Wait for decision
            decision = await approval_manager.wait_for_decision(req_id)
            
            if decision != "approved":
                tool_result = {"error": f"Tool execution {decision} by user."}
            else:
                tool_result = await execute_tool(tool_name, tool_params)
        else:
            # Execute the tool normally
            tool_result = await execute_tool(tool_name, tool_params)
        
        steps.append({
            "type": "tool_result",
            "iteration": iteration + 1,
            "tool": tool_name,
            "result": tool_result,
        })
        
        # Add the assistant's reasoning and the tool result to the conversation
        messages.append({"role": "assistant", "content": assistant_text})
        memory_store.add_message(session_id, "assistant", assistant_text,
                                tool_call=tool_name, tool_result=json.dumps(tool_result)[:2000])
        
        # Feed the tool result back as a user message (so the LLM can reason about it)
        tool_result_text = f"[Tool Result from '{tool_name}']\n{json.dumps(tool_result, indent=2)[:3000]}"
        messages.append({"role": "user", "content": tool_result_text})
        memory_store.add_message(session_id, "user", tool_result_text)
    
    # Max iterations reached
    return AgentResponse(
        session_id=session_id,
        final_answer="[Agent reached maximum iterations without a final answer. The steps above show all progress made.]",
        steps=steps,
        iterations=MAX_ITERATIONS,
    )


async def stream_agent_loop(request: AgentRequest):
    """
    Streaming version of the agent loop using Server-Sent Events (SSE).
    Each step is streamed to the client as it happens.
    """
    session_id = request.session_id or memory_store.create_session()
    
    dynamic_system_prompt = f"{SYSTEM_PROMPT}\n\n{get_soul_prompt()}\n\n{get_skills_prompt()}"
    messages = [{"role": "system", "content": dynamic_system_prompt}]
    existing = memory_store.get_messages(session_id)
    if existing:
        messages.extend(existing)
    messages.append({"role": "user", "content": request.goal})
    memory_store.add_message(session_id, "user", request.goal)
    
    # Stream the session ID first
    yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
    
    for iteration in range(MAX_ITERATIONS):
        # Stream: thinking
        yield f"data: {json.dumps({'type': 'thinking', 'iteration': iteration + 1})}\n\n"
        
        try:
            response = await litellm.acompletion(
                model=request.model,
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
                api_key=request.api_key,
            )
            assistant_text = response.choices[0].message.content
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
            break
        
        tool_call = extract_tool_call(assistant_text)
        
        if tool_call is None:
            # Final answer
            memory_store.add_message(session_id, "assistant", assistant_text)
            yield f"data: {json.dumps({'type': 'final_answer', 'content': assistant_text, 'iterations': iteration + 1})}\n\n"
            yield "data: [DONE]\n\n"
            return
        
        tool_name = tool_call.get("tool", "")
        tool_params = tool_call.get("parameters", {})
        
        # Stream: tool call
        yield f"data: {json.dumps({'type': 'tool_call', 'iteration': iteration + 1, 'reasoning': assistant_text[:500], 'tool': tool_name, 'parameters': tool_params})}\n\n"
        
        # Check for command approval
        if requires_approval(tool_name):
            req_id = approval_manager.request_approval(tool_name, tool_params, assistant_text)
            yield f"data: {json.dumps({'type': 'approval_pending', 'iteration': iteration + 1, 'tool': tool_name, 'request_id': req_id})}\n\n"
            
            # Wait for decision
            decision = await approval_manager.wait_for_decision(req_id)
            if decision != "approved":
                tool_result = {"error": f"Tool execution {decision} by user."}
            else:
                tool_result = await execute_tool(tool_name, tool_params)
        else:
            # Execute
            tool_result = await execute_tool(tool_name, tool_params)
        
        # Stream: tool result
        result_preview = json.dumps(tool_result)[:2000]
        yield f"data: {json.dumps({'type': 'tool_result', 'iteration': iteration + 1, 'tool': tool_name, 'result': json.loads(result_preview) if len(json.dumps(tool_result)) <= 2000 else result_preview})}\n\n"
        
        # Update conversation
        messages.append({"role": "assistant", "content": assistant_text})
        memory_store.add_message(session_id, "assistant", assistant_text,
                                tool_call=tool_name, tool_result=json.dumps(tool_result)[:2000])
        
        tool_result_text = f"[Tool Result from '{tool_name}']\n{json.dumps(tool_result, indent=2)[:3000]}"
        messages.append({"role": "user", "content": tool_result_text})
        memory_store.add_message(session_id, "user", tool_result_text)
    
    yield f"data: {json.dumps({'type': 'max_iterations', 'iterations': MAX_ITERATIONS})}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/run")
async def run_agent(request: AgentRequest):
    """
    The Supreme Agent endpoint. Give it a goal in natural language.
    It will autonomously reason, use tools, and iterate until the goal is achieved.
    
    Set `stream: true` to get real-time Server-Sent Events of each step.
    """
    if request.stream:
        return StreamingResponse(
            stream_agent_loop(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    return await run_agent_loop(request)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Retrieve the full conversation history for a session."""
    history = memory_store.get_full_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": [h.dict() for h in history]}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and free its memory."""
    memory_store.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}
