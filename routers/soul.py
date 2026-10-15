"""
Baton Supreme Connector — SOUL Router
Endpoints for the frontend to view and edit the agent's identity file (SOUL.md).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.security import verify_api_key
from core.soul import load_soul, save_soul

router = APIRouter(prefix="/soul", tags=["SOUL"], dependencies=[Depends(verify_api_key)])


class SoulUpdate(BaseModel):
    content: str


@router.get("/")
async def get_soul():
    """Retrieve the current SOUL.md content."""
    return {"content": load_soul()}


@router.post("/")
async def update_soul(payload: SoulUpdate):
    """Update the SOUL.md content."""
    success = save_soul(payload.content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save SOUL.md")
    return {"status": "success", "message": "SOUL.md updated successfully"}
