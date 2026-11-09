"""CLI: `python -m agent_notifier_cloud serve` | `set-webhook` | `check`."""
from __future__ import annotations

import asyncio
import sys

from .config import load


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:]) or ["serve"]
    cmd = args[0]
    cfg = load()
    if cmd == "serve":
        import uvicorn

        from .app import create_app

        uvicorn.run(
            create_app(cfg),
            host=cfg.host,
            port=cfg.port,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1",
            access_log=False,
            server_header=False,
        )
        return 0
    if cmd == "set-webhook":
        from .telegram import DeliveryError, set_webhook

        try:
            print(asyncio.run(set_webhook(cfg)))
        except DeliveryError as exc:
            print(f"failed: {exc}")
            return 1
        return 0
    if cmd == "check":
        print(f"config OK. MCP URL: {cfg.mcp_url}  bot: @{cfg.tg_bot_username}  db: {cfg.db_path}")
        return 0
    print("usage: python -m agent_notifier_cloud [serve|set-webhook|check]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
