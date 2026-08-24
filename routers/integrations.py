from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.security import verify_api_key
from tenacity import retry, stop_after_attempt, wait_fixed
import httpx

router = APIRouter(prefix="/integrations", tags=["Integrations"], dependencies=[Depends(verify_api_key)])

class GitHubRequest(BaseModel):
    repo: str

@retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
async def fetch_github_info(repo: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"https://api.github.com/repos/{repo}")
        response.raise_for_status()
        return response.json()

@router.post("/github/repo-info")
async def github_repo_info(request: GitHubRequest):
    try:
        data = await fetch_github_info(request.repo)
        return {"description": data.get("description"), "stars": data.get("stargazers_count")}
    except Exception as e:
        return {"error": str(e)}
