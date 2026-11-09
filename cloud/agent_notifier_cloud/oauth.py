"""OAuth 2.1 authorization server for claude.ai / ChatGPT / Claude Code connectors.

Flow: DCR (/register) -> /authorize -> our consent page (Telegram sign-in) -> code -> /token (PKCE).
Personal access tokens (an_pat_...) are also accepted by load_access_token for local agents.
"""
from __future__ import annotations

import secrets
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthToken,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull

from .config import Config
from .db import DB
from .security import PAT_PREFIX, new_secret, sha

ACCESS_TTL = 3600
REFRESH_TTL = 90 * 86400
CODE_TTL = 300
SCOPES = ["notify"]


class NotifyOAuthProvider:
    def __init__(self, cfg: Config, db: DB):
        self.cfg, self.db = cfg, db

    # -- clients -----------------------------------------------------------
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = self.db.one("SELECT data FROM oauth_clients WHERE client_id=?", (client_id,))
        return OAuthClientInformationFull.model_validate_json(row["data"]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if self.db.one("SELECT COUNT(*) c FROM oauth_clients")["c"] >= 5000:
            raise RegistrationError(error="invalid_client_metadata", error_description="registration unavailable")
        self.db.run(
            "INSERT OR REPLACE INTO oauth_clients(client_id,data,created) VALUES(?,?,?)",
            (client_info.client_id, client_info.model_dump_json(), time.time()),
        )

    # -- authorization -------------------------------------------------------
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        pending = "p_" + secrets.token_urlsafe(24)
        self.db.run(
            "INSERT INTO oauth_pending(id,client_id,params,created) VALUES(?,?,?,?)",
            (pending, client.client_id, params.model_dump_json(), time.time()),
        )
        return f"{self.cfg.public_url}/oauth/consent?req={pending}"

    def pending(self, req: str):
        row = self.db.one("SELECT * FROM oauth_pending WHERE id=? AND created>?", (req, time.time() - 600))
        if not row:
            return None
        return row["client_id"], AuthorizationParams.model_validate_json(row["params"])

    def finish_pending(self, req: str) -> None:
        self.db.run("DELETE FROM oauth_pending WHERE id=?", (req,))

    def issue_code(self, user_id: str, client_id: str, params: AuthorizationParams) -> str:
        code = new_secret(32)
        record = AuthorizationCode(
            code=code,
            scopes=params.scopes or SCOPES,
            expires_at=time.time() + CODE_TTL,
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject=user_id,
        )
        self.db.run(
            "INSERT INTO oauth_codes(code_hash,data,expires) VALUES(?,?,?)",
            (sha(code), record.model_dump_json(), record.expires_at),
        )
        return code

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str):
        row = self.db.one("SELECT data FROM oauth_codes WHERE code_hash=? AND expires>?", (sha(authorization_code), time.time()))
        if not row:
            return None
        record = AuthorizationCode.model_validate_json(row["data"])
        return record if record.client_id == client.client_id else None

    # -- tokens ------------------------------------------------------------------
    def _mint(self, user_id: str, client_id: str, scopes: list[str]) -> OAuthToken:
        scopes = scopes or SCOPES
        pair, access, refresh, now = secrets.token_hex(8), new_secret(32), new_secret(32), time.time()
        for kind, token, ttl in (("access", access, ACCESS_TTL), ("refresh", refresh, REFRESH_TTL)):
            self.db.run(
                "INSERT INTO oauth_tokens(hash,kind,client_id,user_id,scopes,expires,pair_id) VALUES(?,?,?,?,?,?,?)",
                (sha(token), kind, client_id, user_id, " ".join(scopes), now + ttl, pair),
            )
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL, scope=" ".join(scopes), refresh_token=refresh)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        # single use: delete first, fail if someone else already consumed it
        if self.db.run("DELETE FROM oauth_codes WHERE code_hash=?", (sha(authorization_code.code),)) != 1:
            raise TokenError(error="invalid_grant", error_description="authorization code already used")
        if not authorization_code.subject or not self.db.active(self.db.user_by_id(authorization_code.subject)):
            raise TokenError(error="invalid_grant", error_description="account no longer exists")
        return self._mint(authorization_code.subject, client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str):
        row = self.db.one(
            "SELECT * FROM oauth_tokens WHERE hash=? AND kind='refresh' AND client_id=? AND expires>?",
            (sha(refresh_token), client.client_id, time.time()),
        )
        if not row:
            return None
        return RefreshToken(
            token=refresh_token, client_id=row["client_id"], scopes=row["scopes"].split(), expires_at=int(row["expires"]), subject=row["user_id"]
        )

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        removed = self.db.run(
            "DELETE FROM oauth_tokens WHERE pair_id=(SELECT pair_id FROM oauth_tokens WHERE hash=?)", (sha(refresh_token.token),)
        )
        if removed == 0 or not refresh_token.subject:
            raise TokenError(error="invalid_grant", error_description="refresh token no longer valid")
        return self._mint(refresh_token.subject, client.client_id, scopes or refresh_token.scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token.startswith(PAT_PREFIX):
            uid = self.db.pat_user(token)
            if not uid:
                return None
            return AccessToken(token=token, client_id="personal-token", scopes=SCOPES, expires_at=None, subject=uid)
        row = self.db.one("SELECT * FROM oauth_tokens WHERE hash=? AND kind='access' AND expires>?", (sha(token), time.time()))
        if not row:
            return None
        return AccessToken(
            token=token, client_id=row["client_id"], scopes=row["scopes"].split(), expires_at=int(row["expires"]), subject=row["user_id"]
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.db.run("DELETE FROM oauth_tokens WHERE pair_id=(SELECT pair_id FROM oauth_tokens WHERE hash=?)", (sha(token.token),))
