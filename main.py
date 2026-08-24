from fastapi import FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.exceptions import global_exception_handler
from routers import llm, tools, integrations

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Baton Supreme Connector",
    description="A highly resilient, all-encompassing connector for the Baton ecosystem.",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Register routers
app.include_router(llm.router)
app.include_router(tools.router)
app.include_router(integrations.router)

@app.get("/")
@limiter.limit("5/minute")
async def root(request: Request):
    return {"message": "Baton Supreme Connector is running."}

if __name__ == "__main__":
    import uvicorn
    from core.config import settings
    uvicorn.run(app, host=settings.host, port=settings.port)
