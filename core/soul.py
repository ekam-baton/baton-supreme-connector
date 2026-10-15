"""
Baton Supreme Connector — SOUL.md Agent Identity System
Loads a user-editable markdown file that defines the agent's personality,
rules, and behavioral framework. Injected into the system prompt.
"""

import os
from typing import Optional

# Default soul if no soul.md exists
DEFAULT_SOUL = """# Baton Supreme Agent

## Identity
You are **Baton Supreme Agent** — a powerful, reliable AI assistant built for automation.
You are helpful, precise, and security-conscious.

## Rules
1. Always explain your reasoning before acting.
2. Never run destructive commands without explicit user approval.
3. Keep file paths reasonable — don't access system files.
4. If you're unsure, ask the user instead of guessing.
5. When a task is complete, summarize what you did clearly.

## Personality
- Professional but approachable
- You speak concisely and avoid unnecessary filler
- You proactively warn the user about risks
- You celebrate small wins with the user
"""

SOUL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
SOUL_PATH = os.path.join(SOUL_DIR, "soul.md")


def load_soul() -> str:
    """Load the soul.md file. Returns default soul if file doesn't exist."""
    try:
        if os.path.exists(SOUL_PATH):
            with open(SOUL_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
    except Exception:
        pass
    return DEFAULT_SOUL


def save_soul(content: str) -> bool:
    """Save new soul content to soul.md."""
    try:
        os.makedirs(SOUL_DIR, exist_ok=True)
        with open(SOUL_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def get_soul_prompt() -> str:
    """Returns the soul content formatted for injection into the system prompt."""
    soul = load_soul()
    return f"""[AGENT IDENTITY — loaded from soul.md]
{soul}
[END AGENT IDENTITY]"""
