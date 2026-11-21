"""Companion runtime guards: one instance, authorized workspaces, diagnostics."""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from .config import HOME


def _state_root() -> Path:
    return Path(os.environ.get("AGENT_NOTIFIER_HOME") or str(HOME))


def lock_path() -> Path:
    return _state_root() / "companion.lock"


def pid_path() -> Path:
    """The owner PID lives in its own file: Windows byte-range locks also block
    reads of the locked region, so it cannot be stored inside the lock file."""
    return _state_root() / "companion.pid"


def _lock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def instance_lock():
    """Yield True when this process owns the companion, False if one already runs.

    The lock is advisory and per-user: it never needs Administrator rights and a
    crashed process releases it automatically when the OS closes the handle.
    """
    path = lock_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    handle = path.open("a+", encoding="utf-8")
    try:
        _lock(handle)
    except OSError:
        handle.close()
        yield False
        return
    owner = pid_path()
    try:
        owner.write_text(str(os.getpid()), encoding="utf-8")
        yield True
    finally:
        try:
            owner.unlink()
        except OSError:
            pass
        try:
            _unlock(handle)
        finally:
            handle.close()


def _lock_held() -> bool:
    """True when another process (or this one) owns the companion lock."""
    path = lock_path()
    if not path.exists():
        return False
    try:
        handle = path.open("a+", encoding="utf-8")
    except OSError:
        return False
    try:
        _lock(handle)
    except OSError:
        handle.close()
        return True
    try:
        _unlock(handle)
    except OSError:
        pass
    finally:
        handle.close()
    return False


def status() -> dict:
    """Diagnostics for the companion lock; takes it only for an instant."""
    path = lock_path()
    owner = ""
    try:
        owner = pid_path().read_text(encoding="utf-8").strip()
    except OSError:
        pass
    pid = int(owner) if owner.isdigit() else 0
    return {
        "lock": str(path),
        "pid": pid,
        "running": _lock_held(),
        "workdirs": [str(p) for p in authorized_roots()],
    }


def _configured(settings=None) -> str:
    if settings is not None:
        return settings.get("COMPANION_WORKDIRS", "")
    return os.environ.get("COMPANION_WORKDIRS", "")


def authorized_roots(settings=None) -> list[Path]:
    """Configured workspaces the companion may launch agents in."""
    raw = _configured(settings)
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    roots: list[Path] = []
    for part in parts:
        try:
            resolved = Path(part).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def authorized_workdir(settings=None) -> Path:
    """The directory a launched agent runs in.

    With no configuration the user's home directory is the only workspace, so
    an unconfigured companion still works without granting extra access. When
    workspaces are configured, a job never runs outside them.
    """
    roots = authorized_roots(settings)
    if not roots:
        if _configured(settings).strip():
            # Configured but unusable: fail closed rather than widening access.
            raise ValueError("configured workspaces are unavailable")
        home = Path.home().resolve()
        if home.is_dir():
            return home
        raise ValueError("no authorized working directory is available")
    return roots[0]


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    return True


def describe(settings=None) -> str:
    state = status()
    agent_line = "running" if state["running"] else "not running"
    dirs = ", ".join(state["workdirs"]) if state["workdirs"] else str(Path.home())
    return (f"Companion: {agent_line}"
            + (f" (pid {state['pid']})" if state["running"] else "")
            + f"\nAuthorized workspaces: {dirs}"
            + f"\nLock: {state['lock']}")


if __name__ == "__main__":
    sys.stdout.write(describe() + "\n")
