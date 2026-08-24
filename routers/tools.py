from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from core.security import verify_api_key
import asyncio
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

router = APIRouter(prefix="/tools", tags=["Tools"], dependencies=[Depends(verify_api_key)])

class ToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]

@router.post("/execute")
async def execute_tool(request: ToolRequest):
    """
    The Ultimate Tool Executor. Supports shell commands, web search, web scraping, and file operations.
    """
    tool = request.tool_name
    params = request.parameters

    try:
        if tool == "shell_command":
            cmd = params.get("command")
            if not cmd:
                raise ValueError("Missing 'command'")
            
            # Using asyncio to prevent blocking the FastAPI event loop
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Add a timeout so runaway scripts don't hang the connector
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
            # DDGS blocks, so we run it in a threadpool to keep the async loop fast
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
            def sync_read():
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()
            content = await asyncio.to_thread(sync_read)
            return {"content": content}

        else:
            raise HTTPException(status_code=404, detail=f"Tool '{tool}' is not recognized by the Supreme Connector.")
            
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e), "status": "failed"}
