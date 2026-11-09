"""Configuration from environment variables (systemd EnvironmentFile in production)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    public_url: str
    host: str = "127.0.0.1"
    port: int = 8787
    db_path: str = "/var/lib/agent-notifier/notify.db"
    tg_token: str = ""
    tg_bot_username: str = ""
    tg_webhook_secret: str = ""
    session_secret: str = ""
    landing_url: str = ""
    ntfy_server: str = "https://ntfy.sh"
    rate_per_min: int = 10
    rate_per_day: int = 300
    admin_ids: tuple = ()

    @property
    def hostname(self) -> str:
        return urlparse(self.public_url).netloc

    @property
    def secure(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def mcp_url(self) -> str:
        return self.public_url + "/mcp"


def _int(env, key: str, default: int) -> int:
    try:
        return max(1, int(env.get(key, default)))
    except (TypeError, ValueError):
        return default


def load(env=None) -> Config:
    e = env if env is not None else os.environ
    cfg = Config(
        public_url=e.get("PUBLIC_URL", "").strip().rstrip("/"),
        host=e.get("HOST", "127.0.0.1").strip(),
        port=_int(e, "PORT", 8787),
        db_path=e.get("DB_PATH", "/var/lib/agent-notifier/notify.db").strip(),
        tg_token=e.get("TG_BOT_TOKEN", "").strip(),
        tg_bot_username=e.get("TG_BOT_USERNAME", "").strip().lstrip("@"),
        tg_webhook_secret=e.get("TG_WEBHOOK_SECRET", "").strip(),
        session_secret=e.get("SESSION_SECRET", "").strip(),
        landing_url=e.get("LANDING_URL", "").strip().rstrip("/"),
        ntfy_server=e.get("NTFY_SERVER", "https://ntfy.sh").strip().rstrip("/"),
        rate_per_min=_int(e, "RATE_PER_MIN", 10),
        rate_per_day=_int(e, "RATE_PER_DAY", 300),
        admin_ids=tuple(x.strip() for x in e.get("ADMIN_TG_IDS", "").replace(";", ",").split(",") if x.strip().lstrip("-").isdigit()),
    )
    problems = []
    if not cfg.public_url.startswith(("https://", "http://")):
        problems.append("PUBLIC_URL must be like https://notify.example.com")
    if cfg.public_url.startswith("http://") and "localhost" not in cfg.public_url and "127.0.0.1" not in cfg.public_url:
        problems.append("PUBLIC_URL must be https (http only allowed for localhost)")
    if len(cfg.session_secret) < 32:
        problems.append("SESSION_SECRET must be 32+ chars: python -c 'import secrets;print(secrets.token_urlsafe(48))'")
    if not cfg.tg_token:
        problems.append("TG_BOT_TOKEN is required (from @BotFather)")
    if not cfg.tg_bot_username:
        problems.append("TG_BOT_USERNAME is required (bot username without @)")
    if len(cfg.tg_webhook_secret) < 16 or not all(c.isalnum() or c in "_-" for c in cfg.tg_webhook_secret):
        problems.append("TG_WEBHOOK_SECRET must be 16+ chars of A-Z a-z 0-9 _ -")
    if problems:
        raise SystemExit("config errors:\n - " + "\n - ".join(problems))
    return cfg
