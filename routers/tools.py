from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from core.security import verify_api_key
from core.sandbox import validate_command, validate_filepath
import asyncio
import os
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from services import browser

router = APIRouter(prefix="/tools", tags=["Tools"], dependencies=[Depends(verify_api_key)])

class ToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]

@router.post("/execute")
async def execute_tool(request: ToolRequest):
    """
    The Ultimate Tool Executor. Supports shell commands, web search, web scraping,
    file read/write, and browser automation. All commands are sandboxed.
    """
    tool = request.tool_name
    params = request.parameters

    try:
        if tool == "shell_command":
            cmd = params.get("command")
            if not cmd:
                raise ValueError("Missing 'command'")
            
            # SAFETY: Validate command against blocklist
            check = validate_command(cmd)
            if not check.allowed:
                raise HTTPException(status_code=403, detail=check.reason)
            
            # Check if docker sandbox is enabled
            # We assume a global setting or pass it in somehow, for now let's just make it possible to use Docker via param
            use_docker = params.get("use_docker", False)
            if use_docker:
                # Wrap the command to run inside a disposable alpine container
                escaped_cmd = cmd.replace("'", "'\\''")
                cmd = f"docker run --rm alpine sh -c '{escaped_cmd}'"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                process.kill()
                raise HTTPException(status_code=408, detail="Command timed out after 30 seconds.")
                
            return {
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "returncode": process.returncode
            }

        elif tool == "web_search":
            query = params.get("query")
            max_results = params.get("max_results", 5)
            def sync_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=max_results))
            results = await asyncio.to_thread(sync_search)
            return {"results": results}

        elif tool == "fetch_url":
            url = params.get("url")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                text = ' '.join(soup.stripped_strings)
                return {"text": text[:5000]}

        elif tool == "read_file":
            filepath = params.get("filepath")
            if not filepath:
                raise HTTPException(status_code=400, detail="Missing 'filepath'")
            check = validate_filepath(filepath)
            if not check.allowed:
                raise HTTPException(status_code=403, detail=check.reason)
            def sync_read():
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
                except FileNotFoundError:
                    raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
            content = await asyncio.to_thread(sync_read)
            return {"content": content}

        elif tool == "write_file":
            filepath = params.get("filepath")
            content = params.get("content", "")
            if not filepath:
                raise HTTPException(status_code=400, detail="Missing 'filepath'")
            check = validate_filepath(filepath)
            if not check.allowed:
                raise HTTPException(status_code=403, detail=check.reason)
            def sync_write():
                try:
                    parent_dir = os.path.dirname(filepath)
                    if parent_dir:
                        os.makedirs(parent_dir, exist_ok=True)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    return len(content)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Failed to write file: {str(e)}")
            bytes_written = await asyncio.to_thread(sync_write)
            return {"status": "success", "filepath": filepath, "bytes_written": bytes_written}

        elif tool == "browser_screenshot":
            url = params.get("url")
            return await browser.take_screenshot(url)

        elif tool == "browser_get_text":
            url = params.get("url")
            return await browser.get_rendered_text(url)

        elif tool == "browser_click":
            url = params.get("url")
            selector = params.get("selector")
            return await browser.click_element(url, selector)

        elif tool == "browser_fill":
            url = params.get("url")
            selector = params.get("selector")
            value = params.get("value")
            return await browser.fill_form(url, selector, value)

        else:
            raise HTTPException(status_code=404, detail=f"Tool '{tool}' is not recognized by the Supreme Connector.")
            
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e), "status": "failed"}
