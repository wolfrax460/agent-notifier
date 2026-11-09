"""Agent detection and registry for the bridge."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

KNOWN = ("claude", "codex", "opencode")


def _resolve(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    for suffix in ("", ".exe", ".cmd", ".bat"):
        p = shutil.which(name + suffix)
        if p:
            return p
    return None


def _version(exe: str) -> str:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=8, errors="replace")
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0][:60] if out else ""
    except Exception:
        return ""


def _running_processes(name: str) -> int:
    """Best-effort count of processes whose name matches. Never reads cmdline/env."""
    count = 0
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10)
            needle = name.lower()
            for line in r.stdout.splitlines():
                # CSV first field is "name"
                if line.startswith('"'):
                    first = line.split('","', 1)[0].strip('"').lower()
                    if needle in first:
                        count += 1
        else:
            r = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=10)
            needle = name.lower()
            for line in r.stdout.splitlines():
                if needle in line.lower():
                    count += 1
    except Exception:
        pass
    return count


def detect(settings) -> list[dict[str, Any]]:
    custom = {}
    raw = settings.get("BRIDGE_AGENTS_CUSTOM", "")
    for pair in raw.split(","):
        if "=" in pair:
            n, cmd = pair.split("=", 1)
            custom[n.strip()] = cmd.strip()
    agents = []
    for name in list(KNOWN) + list(custom):
        exe = _resolve(name) if name in KNOWN else _resolve(custom[name].split()[0]) if custom.get(name) else None
        # for custom, resolve first token
        if name.startswith("custom:") or name in custom:
            cname = name if name in custom else name.split(":", 1)[1]
            cmd = custom.get(cname, "")
            first = cmd.split()[0] if cmd else ""
            exe = _resolve(first) if first else None
            display = cname
        else:
            display = name
        installed = bool(exe)
        ver = _version(exe) if installed else ""
        folder = Path(exe).parent.name if exe else ""
        others = _running_processes(display) if installed else 0
        agents.append({
            "name": display,
            "installed": installed,
            "version": ver,
            "folder": folder,
            "others": others,
            "custom": display in custom or name.startswith("custom:"),
            "cmd": custom.get(display, ""),
        })
    return agents


def find_executable(name: str, custom_cmd: str = "") -> str | None:
    if custom_cmd:
        first = custom_cmd.split()[0]
        return _resolve(first)
    return _resolve(name)
