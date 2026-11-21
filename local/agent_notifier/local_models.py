"""Discover the installed CLI model catalogs without reading credentials or using API keys.

Codex uses its local debug catalog. OpenCode models are read through its official
CLI. Claude Code does not expose a portable machine-readable catalog; the three
documented CLI model aliases are offered as unverified choices if Claude is installed.
The remote owner approves every job and the local CLI performs final access checks.
"""
from __future__ import annotations

import re
import subprocess
from .agents import _resolve
from .windows_process import hidden_kwargs
from . import codex_models

MODEL_ID = codex_models.MODEL_ID
AGENTS = ("codex", "claude", "opencode")
MAX_MODELS = 150
MAX_BYTES = 100_000


def parse_opencode(raw: str) -> list[dict]:
    """Parse lines emitted by 'opencode models': provider/model, optionally labels."""
    if not isinstance(raw, str) or len(raw) > MAX_BYTES:
        return []
    found, seen = [], set()
    for line in raw.splitlines():
        ident = line.strip().split(maxsplit=1)[0] if line.strip() else ""
        if (not MODEL_ID.fullmatch(ident) or "/" not in ident
                or ident in seen or ident.startswith(("http:", "https:"))):
            continue
        seen.add(ident)
        found.append({"id": ident, "name": ident})
        if len(found) >= MAX_MODELS:
            break
    return found


def _cmd(executable: str, args: list[str], timeout: int = 12) -> str:
    try:
        process = subprocess.run(
            [executable, *args], capture_output=True, text=True, errors="replace",
            timeout=timeout, stdin=subprocess.DEVNULL, **hidden_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if process.returncode != 0 or len(process.stdout) > MAX_BYTES:
        return ""
    return process.stdout


def discover(agent: str) -> list[dict]:
    """A model list is not a guarantee of entitlement or remaining quota."""
    if agent not in AGENTS:
        return []
    if agent == "codex":
        # Codex's own discovery validates its executable; do not resolve twice.
        return codex_models.discover()
    executable = _resolve(agent)
    if not executable:
        return []
    if agent == "opencode":
        return parse_opencode(_cmd(executable, ["models"]))
    # Claude Code's documented --model flag accepts these stable aliases.
    # This is an alias list, not authenticated account model discovery.
    # The UI labels them as unverified; CLI will reject unavailable models.
    return [{"id": name, "name": f"{name.title()} (CLI alias; access unverified)"}
            for name in ("sonnet", "opus", "haiku")]


def all_installed(installed: set[str]) -> dict[str, list[dict]]:
    return {agent: discover(agent) for agent in AGENTS if agent in installed}
