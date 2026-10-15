"""
Baton Supreme Connector — Messaging Channel Adapters
Bridges the agent loop to external messaging platforms (Telegram, Discord).
Users can text their agent like texting a friend.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional
from core.security import verify_api_key
import httpx
import os

router = APIRouter(prefix="/channels", tags=["Channels"], dependencies=[Depends(verify_api_key)])


# ─── Telegram Integration ────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramMessage(BaseModel):
    chat_id: str
    text: str


@router.post("/telegram/send")
async def send_telegram(msg: TelegramMessage):
    """Send a message to a Telegram chat."""
    if not TELEGRAM_BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN not configured. Set it as an environment variable."}
    
    url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"chat_id": msg.chat_id, "text": msg.text})
        return resp.json()


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Receive incoming Telegram messages. Set your bot's webhook URL to:
    https://your-server/channels/telegram/webhook
    
    When a user sends a message, this triggers the agent loop and replies.
    """
    body = await request.json()
    message = body.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return {"ok": True}

    # Run the agent
    try:
        from routers.agent import run_agent_loop, AgentRequest
        request_obj = AgentRequest(goal=text, stream=False)
        response = await run_agent_loop(request_obj)
        reply = response.final_answer

        # Send reply back to Telegram
        if TELEGRAM_BOT_TOKEN:
            url = f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={"chat_id": chat_id, "text": reply[:4096]})
    except Exception as e:
        reply = f"Agent error: {str(e)}"

    return {"ok": True}


# ─── Discord Integration ─────────────────────────────────────

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


class DiscordMessage(BaseModel):
    content: str
    username: Optional[str] = "Baton Supreme"


@router.post("/discord/send")
async def send_discord(msg: DiscordMessage):
    """Send a message to a Discord channel via webhook."""
    if not DISCORD_WEBHOOK_URL:
        return {"error": "DISCORD_WEBHOOK_URL not configured. Set it as an environment variable."}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(DISCORD_WEBHOOK_URL, json={
            "content": msg.content,
            "username": msg.username,
        })
        return {"status": resp.status_code}


# ─── Channel Status ──────────────────────────────────────────

@router.get("/status")
async def channel_status():
    """Check which messaging channels are configured."""
    return {
        "telegram": {
            "configured": bool(TELEGRAM_BOT_TOKEN),
            "instructions": "Set TELEGRAM_BOT_TOKEN env var. Create a bot via @BotFather on Telegram."
        },
        "discord": {
            "configured": bool(DISCORD_WEBHOOK_URL),
            "instructions": "Set DISCORD_WEBHOOK_URL env var. Create a webhook in your Discord server settings."
        },
    }
