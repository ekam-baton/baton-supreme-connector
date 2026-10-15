from fastapi import Security, HTTPException, status, Request
from fastapi.security.api_key import APIKeyHeader
from .config import settings

api_key_header = APIKeyHeader(name="X-Baton-API-Key", auto_error=False)

# Role definitions
# format: { "api_key": "role" }
API_KEYS = {
    settings.api_key: "admin"
}

def add_api_key(key: str, role: str = "standard"):
    API_KEYS[key] = role

def remove_api_key(key: str):
    if key in API_KEYS and key != settings.api_key:
        del API_KEYS[key]

async def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    # Store role in request state
    request.state.role = API_KEYS[api_key]
    return api_key

def require_role(allowed_roles: list):
    async def role_checker(request: Request):
        role = getattr(request.state, "role", "standard")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not allowed to perform this action.",
            )
    return role_checker
