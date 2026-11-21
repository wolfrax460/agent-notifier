"""Local Codex CLI model catalog discovery. No API key or cloud provider calls.

The companion executes the already-installed user's Codex binary in a bounded
subprocess and reports only model identifiers and display names. Experimental
Codex CLI versions lacking 'debug models' report no selectable models.
"""
from __future__ import annotations
import json
import re
import subprocess
from .agents import _resolve
from .windows_process import hidden_kwargs

MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")
MAX_OUTPUT = 700_000


def parse_catalog(raw: str) -> list[dict]:
    if len(raw) > MAX_OUTPUT:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("models", data.get("data", []))
        if isinstance(items, dict):
            items = items.get("models", [])
    else:
        return []
    if not isinstance(items, list):
        return []
    result, seen = [], set()
    for item in items[:1500]:
        if not isinstance(item, dict):
            continue
        if item.get("visibility") in ("hide", "hidden", "disabled") or item.get("is_supported") is False:
            continue
        ident = item.get("slug") or item.get("id")
        if not isinstance(ident, str) or not MODEL_ID.fullmatch(ident) or ident in seen:
            continue
        label = item.get("display_name") or item.get("name") or ident
        if not isinstance(label, str) or len(label) > 140 or any(ord(c) < 32 for c in label):
            label = ident
        seen.add(ident)
        result.append({"id": ident, "name": label})
    return result[:150]


def discover() -> list[dict]:
    exe = _resolve("codex")
    if not exe:
        return []
    try:
        done = subprocess.run([exe, "debug", "models"], capture_output=True,
                              text=True, timeout=18, errors="replace",
                              stdin=subprocess.DEVNULL, **hidden_kwargs())
    except (OSError, subprocess.TimeoutExpired):
        return []
    if done.returncode != 0:
        return []
    return parse_catalog(done.stdout)
