"""Crash-safe delivery journal for approved companion jobs (Task 025).

Claim records contain no credentials, prompts or executable commands.
Result records may include private agent output; never log or publish them.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from .config import HOME

_JOB_RE = re.compile(r"j_[0-9a-f]{16}\Z")
_MAX_RECORD_SIZE = 45000


def _root() -> Path:
    home = Path(os.environ.get("AGENT_NOTIFIER_HOME") or str(HOME))
    return home / "job-recovery"


def _file(kind: str, job_id: str) -> Path:
    if kind not in ("claim", "result") or not _JOB_RE.fullmatch(job_id):
        raise ValueError("invalid journal key")
    return _root() / (kind + "-" + job_id + ".json")


def _write(kind: str, job_id: str, device_id: str, payload: dict | None = None) -> None:
    if not device_id or len(device_id) > 120:
        raise ValueError("invalid device")
    path = _file(kind, job_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    item = {"v":1,"device_id":device_id,"job_id":job_id,"created":time.time()}
    if kind == "result":
        if not isinstance(payload, dict) or payload.get("job_id") != job_id:
            raise ValueError("invalid completed result")
        item["payload"] = payload
    content = json.dumps(item, separators=(",",":"), ensure_ascii=False)
    if len(content.encode("utf-8")) > _MAX_RECORD_SIZE:
        raise ValueError("result too large for recovery journal")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            try:
                fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError:
                pass
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def save_claim(job_id: str, device_id: str) -> None:
    _write("claim",job_id,device_id)


def save_result(job_id: str, device_id: str, payload: dict) -> None:
    _write("result",job_id,device_id,payload)


def records(kind: str, device_id: str) -> list[dict]:
    root = _root()
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.glob(kind + "-j_*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            if path.stat().st_size > _MAX_RECORD_SIZE:
                continue
            item = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(item,dict) or item.get("v")!=1
                or item.get("device_id")!=device_id
                or not isinstance(item.get("job_id"),str)
                or path!=_file(kind,item["job_id"])):
                continue
            if kind=="result":
                payload=item.get("payload")
                if not isinstance(payload,dict) or payload.get("job_id")!=item["job_id"]:
                    continue
            found.append(item)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return found


def exists(kind: str, job_id: str) -> bool:
    return _file(kind,job_id).exists()


def discard(kind: str, job_id: str) -> None:
    try:
        _file(kind,job_id).unlink()
    except FileNotFoundError:
        pass


def has_unresolved() -> bool:
    """Fail closed even for corrupt recovery entries."""
    root = _root()
    if not root.is_dir():
        return False
    return any(root.glob("claim-j_*.json")) or any(root.glob("result-j_*.json"))
