"""Outbound secret redaction for notifications."""
from __future__ import annotations

import re
from typing import Any

from .config import Settings

_API_KEY_PATTERNS = [
    re.compile(r"\b(sk-[A-Za-z0-9_-]{10,}|AKIA[A-Z0-9]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"),
]
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_BEARER_RE = re.compile(r"(?i)Authorization:\s*Bearer\s+\S+")
_KV_RE = re.compile(r"(?i)(key|token|secret|password)\s*[:=]\s*[\"']?([A-Za-z0-9+/=_-]{12,})[\"']?")


def _mask_kv(m: re.Match) -> str:
    return m.group(0).replace(m.group(2), "***")


def redact(text: Any, settings: Settings | None = None, extra: list[str] | None = None) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    secrets_list: list[str] = []
    if settings is not None:
        try:
            secrets_list.extend(settings.secrets())
        except Exception:
            pass
    if extra:
        secrets_list.extend(x for x in extra if x)
    for s in secrets_list:
        if s and len(s) >= 4:
            text = text.replace(s, "***")
    text = _BEARER_RE.sub("Authorization: Bearer ***", text)
    text = _PEM_RE.sub("[REDACTED PRIVATE KEY]", text)
    for pat in _API_KEY_PATTERNS:
        text = pat.sub("***", text)
    text = _KV_RE.sub(_mask_kv, text)
    return text