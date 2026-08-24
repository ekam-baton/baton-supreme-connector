from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from core.security import verify_api_key
from tenacity import retry, stop_after_attempt, wait_exponential
import litellm

router = APIRouter(prefix="/llm", tags=["LLM"], dependencies=[Depends(verify_api_key)])

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str  # e.g., 'gpt-4o', 'claude-3-opus-20240229', 'gemini/gemini-1.5-pro', 'ollama/llama3'
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    api_key: Optional[str] = None # Optional override for the provider key

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def safe_llm_call(request: ChatRequest):
    try:
        # LiteLLM automatically routes to OpenAI, Anthropic, Gemini, Huggingface, Cohere, Ollama, etc.
        # based solely on the model string prefix!
        messages_dict = [{"role": m.role, "content": m.content} for m in request.messages]
        
        response = await litellm.acompletion(
            model=request.model,
            messages=messages_dict,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            api_key=request.api_key
        )
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM Provider Error: {str(e)}")

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Universal Router: Sends chat requests to ANY major LLM provider in the world.
    Just prefix the model name appropriately (e.g. 'ollama/llama3', 'gemini/gemini-pro').
    """
    content = await safe_llm_call(request)
    return {"status": "success", "response": content}
