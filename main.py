from fastapi import FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi import Limiter
from slowapi.util import get_remote_address

from fastapi.middleware.cors import CORSMiddleware

from core.exceptions import global_exception_handler
from routers import llm, tools, integrations, agent, security, heartbeat, approval, soul, channels, apikeys

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Baton Supreme Connector",
    description=(
        "A highly resilient, all-encompassing AI agent connector for the Baton ecosystem. "
        "Features autonomous tool-use via ReAct loop, browser automation, shell execution, "
        "web search, file I/O, and universal LLM routing."
    ),
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Register routers
app.include_router(agent.router)   # The brain — autonomous agent loop
app.include_router(llm.router)     # Universal LLM proxy
app.include_router(tools.router)   # Individual tool execution
app.include_router(integrations.router)  # External API integrations
app.include_router(security.router)      # Security health check engine
app.include_router(heartbeat.router)     # Proactive agent scheduler
app.include_router(approval.router)      # Command approval system
app.include_router(soul.router)          # Agent identity system
app.include_router(channels.router)      # Messaging integrations
app.include_router(apikeys.router)       # API Key & Role Management

@app.get("/")
@limiter.limit("5/minute")
async def root(request: Request):
    return {
        "message": "Baton Supreme Connector v2.0 is running.",
        "capabilities": [
            "Autonomous Agent Loop (ReAct)",
            "Universal LLM Routing (OpenAI, Anthropic, Gemini, Ollama)",
            "Shell Command Execution (Sandboxed)",
            "Web Search (DuckDuckGo)",
            "Browser Automation (Playwright)",
            "File Read/Write",
            "Session Memory",
            "Streaming (SSE)",
        ]
    }

if __name__ == "__main__":
    import uvicorn
    from core.config import settings
    uvicorn.run(app, host=settings.host, port=settings.port)

