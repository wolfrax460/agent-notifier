"""Tiny JSON state store (inbox cursors, run start times, debounce)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .config import HOME

STATE_FILE = HOME / "state.json"
RUNS_DIR = HOME / "runs"


def _ensure() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(HOME, 0o700)
    except OSError:
        pass


def load() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any]) -> None:
    _ensure()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(STATE_FILE)


def mark_run_start(session_id: str) -> None:
    _ensure()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{_safe(session_id)}.json").write_text(
        json.dumps({"start": time.time()}), encoding="utf-8"
    )


def run_start(session_id: str) -> float | None:
    try:
        data = json.loads((RUNS_DIR / f"{_safe(session_id)}.json").read_text(encoding="utf-8"))
        return float(data["start"])
    except (OSError, ValueError, KeyError):
        return None


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_")[:80] or "default"


def log(line: str) -> None:
    _ensure()
    try:
        with open(HOME / "notify.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:
        pass
