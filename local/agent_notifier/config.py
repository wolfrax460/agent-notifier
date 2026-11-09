"""Settings: .env files + real environment (env wins). No secrets are ever logged."""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("AGENT_NOTIFIER_HOME", Path.home() / ".agent-notifier"))
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

SECRET_HINTS = ("TOKEN", "PASSWORD", "APIKEY", "API_KEY")


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def load_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in (PACKAGE_ROOT / ".env", HOME / ".env"):
        merged.update(_parse_env(path))
    merged.update({k: v for k, v in os.environ.items() if v != ""})
    return merged


class Settings:
    def __init__(self, env: dict[str, str] | None = None):
        self.env = env if env is not None else load_env()

    def get(self, key: str, default: str = "") -> str:
        return (self.env.get(key) or default).strip()

    @property
    def default_channels(self) -> list[str]:
        raw = self.get("NOTIFY_DEFAULT_CHANNELS", "telegram,ntfy")
        return [c.strip().lower() for c in raw.split(",") if c.strip()]

    @property
    def min_seconds(self) -> int:
        try:
            return max(0, int(self.get("NOTIFY_MIN_SECONDS", "45")))
        except ValueError:
            return 45

    def secrets(self) -> list[str]:
        vals = []
        for key, value in self.env.items():
            if value and len(value) >= 6 and any(h in key.upper() for h in SECRET_HINTS):
                vals.append(value)
        return vals

    def redact(self, text: str) -> str:
        for secret in self.secrets():
            text = text.replace(secret, "***")
        return text
