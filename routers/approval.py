"""
Baton Supreme Connector — Approval Router
Endpoints for the frontend to manage the command approval queue.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from core.security import verify_api_key
from core.approval import approval_manager

router = APIRouter(prefix="/approval", tags=["Approval"], dependencies=[Depends(verify_api_key)])


class ApprovalDecision(BaseModel):
    decision: str  # "approve" or "deny"


@router.get("/status")
async def get_approval_status():
    """Check if approval mode is enabled and get pending requests."""
    return {
        "enabled": approval_manager.enabled,
        "pending_requests": approval_manager.get_pending()
    }


@router.post("/toggle")
async def toggle_approval_mode():
    """Enable or disable the command approval requirement."""
    approval_manager.enabled = not approval_manager.enabled
    return {"enabled": approval_manager.enabled}


@router.post("/{req_id}")
async def make_decision(req_id: str, payload: ApprovalDecision):
    """Approve or deny a pending tool call request."""
    if payload.decision == "approve":
        success = approval_manager.approve(req_id)
    elif payload.decision == "deny":
        success = approval_manager.deny(req_id)
    else:
        raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'deny'")

    if not success:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    return {"status": "success", "request_id": req_id, "decision": payload.decision}
