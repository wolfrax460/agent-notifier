"""Opt-in companion auto-start and crash supervision (Windows-first, no admin).

The companion is an outbound client: it can start installed agent CLIs on this
computer, but it can never power a sleeping or switched-off machine on. This
module only manages a per-user login launcher and supervision loop.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from .windows_process import hidden_kwargs

APP_DIR_NAME = "agent-notifier"
LAUNCHER_NAME = "agent-notifier-companion.vbs"
LEGACY_LAUNCHER_NAME = "agent-notifier-companion.cmd"
TASK_NAME = "AgentNotifierCompanion"


def _startup_dir() -> Path:
    """Per-user Startup folder (or an explicit override for tests)."""
    override = os.environ.get("AN_AUTOSTART_DIR")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    # Non-Windows: XDG autostart is a different mechanism; keep an explicit dir.
    return Path.home() / ".config" / "autostart"


def _log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home()
    return root / APP_DIR_NAME / "logs"


def _launcher_path() -> Path:
    return _startup_dir() / LAUNCHER_NAME


def _python_windowless() -> str:
    """Prefer pythonw.exe so login startup does not open a console window."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def build_launcher_command() -> str:
    """Fixed command line: no shell metacharacters, no server-selected binaries."""
    return (
        '"' + _python_windowless() + '" -m agent_notifier companion start --supervise'
    )


def install() -> int:
    if os.name != "nt":
        print("Auto-start is implemented for Windows. On Linux/macOS use your service manager.")
        return 1
    path = _launcher_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    logs = _log_dir()
    logs.mkdir(parents=True, exist_ok=True)
    log_file = logs / "companion.log"
    # Windows Startup invokes .vbs via wscript.exe without opening a console.
    # The legacy batch launcher is deliberately removed to prevent two instances.
    command = (os.environ.get("ComSpec", "cmd.exe") + ' /D /C ""'
               + build_launcher_command() + ' >> "' + str(log_file) + '" 2>&1"')
    vb_command = '"' + command.replace('"', '""') + '"'
    script = ("' Opt-in Agent Notifier hidden login launcher\r\n"
              "Set shell = CreateObject(\"WScript.Shell\")\r\n"
              "shell.CurrentDirectory = shell.ExpandEnvironmentStrings(\"%USERPROFILE%\")\r\n"
              f"shell.Run {vb_command}, 0, False\r\n")
    path.write_text(script, encoding="utf-8", newline="")
    legacy = _startup_dir() / LEGACY_LAUNCHER_NAME
    try:
        legacy.unlink(missing_ok=True)
    except OSError:
        print("WARNING: legacy CMD startup launcher could not be removed; check Startup folder.")
    print(f"Auto-start installed: {path}")
    print("It runs at your next Windows sign-in and only while you are logged in.")
    print("Disable anytime with: agent-notifier companion uninstall-autostart")
    return 0


def uninstall() -> int:
    path = _launcher_path()
    removed = False
    for target in (path, _startup_dir() / (LAUNCHER_NAME + ".disabled"),
                   _startup_dir() / LEGACY_LAUNCHER_NAME,
                   _startup_dir() / (LEGACY_LAUNCHER_NAME + ".disabled")):
        try:
            if target.exists():
                target.unlink()
                removed = True
        except OSError as exc:
            print(f"Could not remove {target}: {exc}")
            return 1
    print("Auto-start removed." if removed else "Auto-start was not installed.")
    return 0


def task_state() -> str:
    """Read-only look at a legacy scheduled task, if one exists."""
    if os.name != "nt" or not shutil.which("schtasks"):
        return "n/a"
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
            capture_output=True, text=True, timeout=10, **hidden_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return "present" if result.returncode == 0 else "absent"


def status() -> dict:
    path = _launcher_path()
    legacy = _startup_dir() / LEGACY_LAUNCHER_NAME
    actual = path if path.exists() else legacy if legacy.exists() else path
    return {
        "platform": os.name,
        "installed": actual.exists(),
        "path": str(actual),
        "command": build_launcher_command(),
        "log": str(_log_dir() / "companion.log"),
        "task": task_state(),
    }


def supervise(run_once, sleep=time.sleep) -> int:
    """Restart the companion loop after crashes until the user stops it.

    Returns 0 on a clean operator interrupt, otherwise keeps retrying with a
    bounded backoff. A revoked device (exit code 1 with a terminal message)
    is not retried forever: after repeated immediate failures we stop.
    """
    delay = 3
    immediate_failures = 0
    while True:
        started = time.monotonic()
        code = run_once()
        lasted = time.monotonic() - started
        if code == 0:
            return 0
        if lasted < 10:
            immediate_failures += 1
        else:
            immediate_failures = 0
        if immediate_failures >= 5:
            print("Companion keeps failing immediately; stopping supervision. "
                  "Check pairing and logs, then run `agent-notifier companion start`.")
            return code
        print(f"Companion exited (code {code}); restarting in {delay}s...")
        try:
            sleep(delay)
        except KeyboardInterrupt:
            print("Supervision stopped.")
            return 0
        delay = min(delay * 2, 60)
