"""MCP server: lets Claude decide when/where to ping you, and listen for replies."""
from __future__ import annotations

import asyncio
import time

try:  # mcp >= 2.0 renamed FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from . import channels as ch
from .config import Settings
from .core import norm_priority, notify
from .inbox import poll_inbox, wait_for_reply

INSTRUCTIONS = """\
Use these tools to reach the user away from the screen.

- notify_me: call it ONCE when you finish a long task (more than a minute or two of work) or when you
  are blocked and need the user. Message = what was done / what is needed, in 1-3 short lines, no secrets.
  priority: low = FYI, normal = finished, high = needs attention soon, urgent = blocked or something broke
  (high/urgent go to every configured channel).
- ask_me: use when you need a decision to continue. It sends the question and waits for the reply
  (Telegram / ntfy inbox). If it times out, state your assumption, proceed safely, and notify_me.
- check_inbox: read messages the user sent while you were working.
Never send API keys, tokens, passwords or private file contents through these tools. Do not spam:
one ping per finished task, not one per step.
"""

mcp = FastMCP("agent-notifier", instructions=INSTRUCTIONS)


@mcp.tool()
async def notify_me(
    message: str, title: str = "Claude", priority: str = "normal", channels: list[str] | None = None
) -> dict:
    """Send the user a notification (Telegram / ntfy / Gmail / WhatsApp).

    priority: low | normal | high | urgent. `channels` optionally forces specific channels.
    """
    return await asyncio.to_thread(notify, message, title, norm_priority(priority), channels)


@mcp.tool()
async def ask_me(question: str, timeout_seconds: int = 300, title: str = "Claude needs a decision") -> dict:
    """Ask the user a question and wait for the reply (max 900s). Returns the reply text or a timeout."""
    timeout = max(10, min(int(timeout_seconds), 900))
    settings = Settings()
    sent_at = time.time()
    body = f"{question}\n\n(Reply to this message. Waiting up to {timeout // 60 or 1} min.)"
    res = await asyncio.to_thread(notify, body, title, "high", None, settings)
    if not res.get("sent"):
        return {"answered": False, "error": "could not send question", "detail": res}
    reply, earlier = await asyncio.to_thread(wait_for_reply, settings, timeout, sent_at)
    out: dict = {"answered": reply is not None, "reply": reply["text"] if reply else None}
    if reply:
        out["via"] = reply["channel"]
    if earlier:
        out["earlier_messages"] = [m["text"] for m in earlier]
    return out


@mcp.tool()
async def check_inbox(wait_seconds: int = 0) -> dict:
    """Read new messages the user sent (Telegram replies / ntfy inbox topic)."""
    msgs = await asyncio.to_thread(poll_inbox, None, max(0, min(int(wait_seconds), 30)), True)
    return {"count": len(msgs), "messages": [{"via": m["channel"], "text": m["text"]} for m in msgs]}


@mcp.tool()
async def channel_status() -> dict:
    """Show which channels are configured (never reveals secrets)."""
    settings = Settings()
    return {
        "default_channels": settings.default_channels,
        "channels": {
            name: {"configured": c.configured(), "two_way": c.inbound, "needs": c.needs}
            for name, c in ch.build(settings).items()
        },
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
