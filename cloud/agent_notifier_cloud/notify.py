"""Delivery logic shared by MCP tools, REST API and the dashboard test button."""
from __future__ import annotations

import re

import httpx

from . import telegram as tg
from .config import Config
from .db import DB
from .security import RateLimiter

PRIORITIES = ("low", "normal", "high", "urgent")
NTFY_PRIORITY = {"low": 2, "normal": 3, "high": 4, "urgent": 5}
NTFY_TAG = {"low": "robot", "normal": "robot", "high": "warning", "urgent": "rotating_light"}
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str | None, limit: int) -> str:
    return _CTRL.sub("", text or "").strip()[:limit]


async def _ntfy(cfg: Config, topic: str, title: str, message: str, priority: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                cfg.ntfy_server,
                json={
                    "topic": topic,
                    "title": title,
                    "message": message[:3900],
                    "priority": NTFY_PRIORITY[priority],
                    "tags": [NTFY_TAG[priority]],
                },
            )
    except httpx.HTTPError as exc:
        raise tg.DeliveryError(f"ntfy network error ({type(exc).__name__})") from None
    if resp.status_code >= 400:
        raise tg.DeliveryError(f"ntfy HTTP {resp.status_code}")


async def deliver(
    cfg: Config,
    db: DB,
    limiter: RateLimiter,
    user,
    message: str,
    title: str = "Claude",
    priority: str = "normal",
    channels: list[str] | None = None,
) -> dict:
    message, title = clean(message, 3500), clean(title, 100) or "Claude"
    priority = priority if priority in PRIORITIES else "normal"
    result: dict = {"sent": [], "failed": {}, "skipped": []}
    if not message:
        result["error"] = "empty message"
        return result
    if not limiter.allow(f"n:{user['id']}", cfg.rate_per_min, 60):
        result["error"] = f"rate limit: max {cfg.rate_per_min} notifications per minute"
        return result
    if db.usage_today(user["id"]) >= cfg.rate_per_day:
        result["error"] = f"daily limit reached ({cfg.rate_per_day}/day)"
        return result

    available = ["telegram"] + (["ntfy"] if user["ntfy_enabled"] else [])
    if channels:
        wanted = [c.strip().lower() for c in channels]
        result["skipped"] = [f"{c} (not available)" for c in wanted if c not in available]
        wanted = [c for c in wanted if c in available]
    elif priority in ("high", "urgent"):
        wanted = available
    else:
        wanted = ["telegram"]

    for name in wanted:
        try:
            if name == "telegram":
                await tg.send(cfg, user["tg_chat_id"], f"{title}\n\n{message}")
            else:
                await _ntfy(cfg, user["ntfy_topic"], title, message, priority)
            result["sent"].append(name)
        except tg.DeliveryError as exc:
            result["failed"][name] = str(exc)
    if result["sent"]:
        db.bump_usage(user["id"])
    return result
