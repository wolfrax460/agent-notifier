"""MCP tools. The calling user comes from the verified access token - never from tool arguments."""
from __future__ import annotations

import asyncio
import time

from mcp.server.auth.middleware.auth_context import get_access_token

from .config import Config
from .db import DB
from .notify import deliver
from .security import RateLimiter

INSTRUCTIONS = """\
Use these tools to reach the user away from the screen.

- notify_me: call it ONCE when you finish a long task (more than a minute or two of work) or when you
  are blocked and need the user. Message = what was done / what is needed, 1-3 short lines, no secrets.
  priority: low = FYI, normal = finished, high = needs attention soon, urgent = blocked or broken.
- ask_me: use when you need a decision to continue. It sends the question and waits for the reply.
  If it times out, state your assumption, proceed safely, and notify_me.
- check_inbox: read messages the user sent while you were working.
Never send API keys, tokens, passwords or private file contents. One ping per finished task, not per step.
"""


def register_tools(mcp, cfg: Config, db: DB, limiter: RateLimiter) -> None:
    def current_user():
        token = get_access_token()
        if not token or not token.subject:
            raise ValueError("not authenticated")
        user = db.user_by_id(token.subject)
        if not user:
            raise ValueError("account no longer exists")
        if user["suspended"]:
            raise ValueError("account suspended")
        return user

    @mcp.tool()
    async def notify_me(
        message: str, title: str = "Claude", priority: str = "normal", channels: list[str] | None = None
    ) -> dict:
        """Send the user a notification (Telegram, plus ntfy if they enabled it).

        priority: low | normal | high | urgent. high/urgent go to every enabled channel.
        """
        return await deliver(cfg, db, limiter, current_user(), message, title, priority, channels)

    @mcp.tool()
    async def ask_me(question: str, timeout_seconds: int = 90, title: str = "Claude needs a decision") -> dict:
        """Ask the user a question on Telegram and wait for their reply (max 240s)."""
        user = current_user()
        timeout = max(10, min(int(timeout_seconds), 240))
        sent_at = time.time()
        body = f"{question}\n\n(Reply to this chat. Waiting up to {max(1, timeout // 60)} min.)"
        res = await deliver(cfg, db, limiter, user, body, title, "high", ["telegram"])
        if not res["sent"]:
            return {"answered": False, "error": "could not send question", "detail": res}
        deadline = time.time() + timeout
        while time.time() < deadline:
            replies = db.pop_inbox(user["id"], since=sent_at - 1, limit=1)
            if replies:
                return {"answered": True, "reply": replies[0]["text"]}
            await asyncio.sleep(1.0)
        return {"answered": False, "reply": None, "note": "timed out; proceed with a safe assumption"}

    @mcp.tool()
    async def check_inbox() -> dict:
        """Read new messages the user sent via Telegram since the last check."""
        msgs = db.pop_inbox(current_user()["id"])
        return {"count": len(msgs), "messages": [m["text"] for m in msgs]}

    @mcp.tool()
    async def channel_status() -> dict:
        """Show which notification channels are active for this user."""
        user = current_user()
        return {
            "telegram": {"connected": True, "two_way": True},
            "ntfy": {"enabled": bool(user["ntfy_enabled"]), "two_way": False},
            "limits": {"per_minute": cfg.rate_per_min, "per_day": cfg.rate_per_day, "sent_today": db.usage_today(user["id"])},
        }
