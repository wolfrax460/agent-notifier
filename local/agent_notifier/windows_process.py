"""Keep background CLI discovery from flashing console windows on Windows.

Only use this for trusted, fixed local subprocesses. No shell is introduced.
"""
from __future__ import annotations

import os
import subprocess


def hidden_kwargs(platform: str | None = None) -> dict:
    """Return subprocess flags; portable on Linux/macOS and safe for Windows .cmd."""
    if (os.name if platform is None else platform) != "nt":
        return {}
    flags = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    # CREATE_NO_WINDOW covers console executables; SW_HIDE also helps with
    # .cmd/.bat launchers that would otherwise briefly steal focus.
    startup_class = getattr(subprocess, "STARTUPINFO", None)
    if startup_class is not None:
        startup = startup_class()
        startup.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x0001)
        startup.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        flags["startupinfo"] = startup
    return flags
