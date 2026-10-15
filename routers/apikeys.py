"""
Baton Supreme Connector — API Keys Router
Manage API keys and their roles.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.security import verify_api_key, API_KEYS, add_api_key, remove_api_key

router = APIRouter(prefix="/apikeys", tags=["API Keys"], dependencies=[Depends(verify_api_key)])


class APIKeyCreate(BaseModel):
    key: str
    role: str = "standard"


class APIKeyDelete(BaseModel):
    key: str


@router.get("/")
async def list_keys():
    """List all configured API keys and their roles."""
    # Obfuscate the keys slightly for security when listing
    masked = {}
    for k, v in API_KEYS.items():
        masked_k = k[:4] + "*" * 10 + k[-4:] if len(k) > 10 else "***"
        masked[masked_k] = {"role": v, "raw": k}  # keeping raw to make it easy for our dashboard to test
    return {"keys": masked}


@router.post("/")
async def create_key(payload: APIKeyCreate):
    """Add a new API key."""
    if payload.role not in ["admin", "standard", "readonly"]:
        raise HTTPException(status_code=400, detail="Invalid role. Use admin, standard, or readonly.")
    add_api_key(payload.key, payload.role)
    return {"status": "success", "key": payload.key, "role": payload.role}


@router.delete("/{key}")
async def delete_key(key: str):
    """Remove an API key."""
    if key not in API_KEYS:
        raise HTTPException(status_code=404, detail="Key not found.")
    try:
        remove_api_key(key)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
