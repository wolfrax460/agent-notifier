"""Assemble the ASGI app: remote MCP server + OAuth + pages + webhook."""
from __future__ import annotations

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .config import Config, load
from .db import DB
from .oauth import SCOPES, NotifyOAuthProvider
from .security import RateLimiter
from .tools import INSTRUCTIONS, register_tools
from .web import register_web


def create_app(cfg: Config | None = None):
    cfg = cfg or load()
    db = DB(cfg.db_path)
    db.purge()
    limiter = RateLimiter()
    provider = NotifyOAuthProvider(cfg, db)

    mcp = MCPServer(
        "agent-notifier",
        instructions=INSTRUCTIONS,
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=cfg.public_url,
            resource_server_url=cfg.mcp_url,
            validate_token_resource=False,
            client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=SCOPES, default_scopes=SCOPES),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )
    register_tools(mcp, cfg, db, limiter)
    register_web(mcp, cfg, db, limiter, provider)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[cfg.hostname, f"{cfg.host}:{cfg.port}", f"localhost:{cfg.port}"],
        allowed_origins=[cfg.public_url, "https://claude.ai", "https://chatgpt.com", "https://chat.openai.com"],
    )
    return mcp.streamable_http_app(host=cfg.host, transport_security=security, stateless_http=True)
