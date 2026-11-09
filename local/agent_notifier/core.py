"""Dispatcher: routing, retry, fallback, secret redaction."""
from __future__ import annotations

import time

from . import channels as ch
from . import state
from .config import Settings

PRIORITIES = ("low", "normal", "high", "urgent")


def norm_priority(value: str | None) -> str:
    value = (value or "normal").strip().lower()
    return value if value in PRIORITIES else "normal"


def _try(channel: ch.Channel, title: str, message: str, priority: str, settings: Settings) -> str | None:
    """Return None on success, else a redacted error string. One retry on failure."""
    last = ""
    for attempt in range(2):
        try:
            channel.send(title, message, priority)
            return None
        except Exception as exc:  # noqa: BLE001 - never leak a token through an exception
            last = settings.redact(f"{exc.__class__.__name__}: {exc}")
            if attempt == 0:
                time.sleep(1.0)
    return last


def notify(
    message: str,
    title: str = "Claude",
    priority: str = "normal",
    channels: list[str] | None = None,
    settings: Settings | None = None,
) -> dict:
    """Send a notification.

    Routing:
      * explicit `channels` -> exactly those
      * high/urgent         -> every configured channel
      * low/normal          -> NOTIFY_DEFAULT_CHANNELS, falling back to the rest if all fail
    """
    settings = settings or Settings()
    priority = norm_priority(priority)
    available = ch.build(settings)
    configured = [n for n, c in available.items() if c.configured()]
    result: dict = {"sent": [], "failed": {}, "skipped": []}

    if not configured:
        result["error"] = "no channels configured - run `agent-notifier status`"
        return result

    if channels:
        wanted = [c.lower() for c in channels]
        unknown = [c for c in wanted if c not in available]
        result["skipped"] += [f"{c} (unknown)" for c in unknown]
        primary = [c for c in wanted if c in configured]
        result["skipped"] += [f"{c} (not configured)" for c in wanted if c in available and c not in configured]
        fallback: list[str] = []
    elif priority in ("high", "urgent"):
        primary, fallback = configured, []
    else:
        primary = [c for c in settings.default_channels if c in configured] or configured
        fallback = [c for c in configured if c not in primary]

    for name in primary:
        err = _try(available[name], title, message, priority, settings)
        if err is None:
            result["sent"].append(name)
        else:
            result["failed"][name] = err

    if not result["sent"] and fallback:
        for name in fallback:
            err = _try(available[name], title, message, priority, settings)
            if err is None:
                result["sent"].append(name)
                result["fallback_used"] = True
                break
            result["failed"][name] = err

    state.log(f"notify priority={priority} sent={result['sent']} failed={list(result['failed'])}")
    return result
