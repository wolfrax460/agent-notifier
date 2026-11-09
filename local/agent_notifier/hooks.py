"""Claude Code hook handler. One command handles every event: `agent-notifier hook`.

Events (JSON on stdin, `hook_event_name`):
  UserPromptSubmit -> remember when the run started
  Stop             -> "finished" ping (skipped if the run was shorter than NOTIFY_MIN_SECONDS)
  Notification     -> "Claude needs you" ping (permission prompt / idle), high priority

Hooks must never break Claude: every path swallows errors and exits 0 silently.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from . import state
from .config import Settings
from .core import notify

DEBOUNCE_SECONDS = 30


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _last_assistant_text(transcript_path: str | None, limit: int = 400) -> str:
    """Best-effort: tail of the transcript JSONL -> last assistant text block."""
    if not transcript_path:
        return ""
    try:
        path = Path(transcript_path).expanduser()
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 200_000))
            lines = fh.read().decode("utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            msg = entry.get("message") if isinstance(entry, dict) else None
            if not msg or msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if isinstance(content, str):
                text = content
            else:
                text = " ".join(
                    b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"
                )
            text = " ".join(text.split())
            if text:
                return text[:limit] + ("..." if len(text) > limit else "")
    except OSError:
        pass
    return ""


def _debounced(key: str) -> bool:
    st = state.load()
    now = time.time()
    if now - st.get(key, 0) < DEBOUNCE_SECONDS:
        return True
    st[key] = now
    state.save(st)
    return False


def handle(payload: dict, settings: Settings | None = None) -> None:
    settings = settings or Settings()
    event = payload.get("hook_event_name", "")
    session = str(payload.get("session_id", "default"))
    project = Path(payload.get("cwd") or ".").resolve().name or "project"

    if event == "UserPromptSubmit":
        state.mark_run_start(session)
        return

    if event == "Stop":
        if payload.get("stop_hook_active"):
            return
        start = state.run_start(session)
        elapsed = time.time() - start if start else None
        if elapsed is not None and elapsed < settings.min_seconds:
            return
        if _debounced("last_stop"):
            return
        took = f" in {_fmt_duration(elapsed)}" if elapsed is not None else ""
        summary = _last_assistant_text(payload.get("transcript_path"))
        body = f"Finished{took} ({project})" + (f"\n\n{summary}" if summary else "")
        notify(body, title="Claude finished", priority="normal", settings=settings)
        return

    if event == "Notification":
        if _debounced("last_attention"):
            return
        text = payload.get("message") or "Claude needs your attention"
        notify(f"{text} ({project})", title="Claude needs you", priority="high", settings=settings)


def handle_codex(payload: dict, settings: Settings | None = None) -> None:
    """Codex CLI `notify` hook: Codex passes one JSON argument; only `agent-turn-complete` exists."""
    settings = settings or Settings()
    if payload.get("type") != "agent-turn-complete":
        return
    if _debounced("last_codex"):
        return
    project = Path(payload.get("cwd") or os.getcwd()).resolve().name or "project"
    last = " ".join(str(payload.get("last-assistant-message") or "").split())
    summary = last[:400] + ("..." if len(last) > 400 else "")
    body = f"Turn complete ({project})" + (f"\n\n{summary}" if summary else "")
    notify(body, title="Codex finished", priority="normal", settings=settings)


def run_from_stdin() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        handle(payload)
    except Exception as exc:  # noqa: BLE001
        state.log(f"hook error: {exc.__class__.__name__}")
    return 0
