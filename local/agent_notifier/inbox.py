"""Inbound messages (you -> Claude): Telegram replies and an ntfy inbox topic."""
from __future__ import annotations

import time

from . import channels as ch
from . import state
from .config import Settings


def poll_inbox(settings: Settings | None = None, wait: int = 0, consume: bool = True) -> list[dict]:
    """Fetch new messages. consume=False peeks without advancing cursors."""
    settings = settings or Settings()
    available = ch.build(settings)
    st = state.load()
    msgs: list[dict] = []

    tg = available["telegram"]
    if tg.configured():
        try:
            new, nxt = tg.poll(st.get("tg_offset"), wait=wait)
            msgs += new
            if consume and nxt:
                st["tg_offset"] = nxt
        except Exception as exc:  # noqa: BLE001
            state.log("telegram poll failed: " + settings.redact(str(exc)))

    nt = available["ntfy"]
    if nt.configured() and settings.get("NTFY_INBOX_TOPIC"):
        try:
            new, last = nt.poll(st.get("ntfy_last_id"))
            msgs += new
            if consume and last:
                st["ntfy_last_id"] = last
        except Exception as exc:  # noqa: BLE001
            state.log("ntfy poll failed: " + settings.redact(str(exc)))

    if consume:
        state.save(st)
    return sorted(msgs, key=lambda m: m.get("ts", 0))


def wait_for_reply(
    settings: Settings | None = None, timeout: int = 300, since_ts: float | None = None
) -> tuple[dict | None, list[dict]]:
    """Block until a reply newer than since_ts arrives.

    Returns (reply, earlier). `earlier` holds messages queued before the question
    so nothing you sent while Claude was away is silently lost.
    """
    settings = settings or Settings()
    since_ts = since_ts if since_ts is not None else time.time()
    deadline = time.time() + timeout
    earlier: list[dict] = []
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None, earlier
        for msg in poll_inbox(settings, wait=int(min(3, remaining))):
            if msg.get("ts", 0) >= since_ts - 2:
                return msg, earlier
            earlier.append(msg)
        time.sleep(1.0)
