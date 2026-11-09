"""Browser pages (Telegram sign-in, dashboard, OAuth consent), Telegram webhook, REST API."""
from __future__ import annotations

import hmac
import html
import json
import secrets
import time
from urllib.parse import parse_qs, quote, urlparse

from mcp.server.auth.provider import construct_redirect_uri
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from . import telegram as tg
from .config import Config
from .db import DB
from .notify import deliver
from .oauth import NotifyOAuthProvider
from .admin import register_admin
from .ui import CSS, DASH_JS, auth_page, dashboard_html
from .security import PAT_PREFIX, RateLimiter, csrf_ok, csrf_token, safe_next

esc = html.escape

COPY_JS = """document.querySelectorAll('[data-copy]').forEach(function(b){b.addEventListener('click',function(){
navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function(){var t=b.textContent;b.textContent='Copied';setTimeout(function(){b.textContent=t},1200)})})});"""


def page(title: str, body: str, script: str = "", status: int = 200, layout: str = "plain") -> HTMLResponse:
    nonce = secrets.token_urlsafe(12)
    tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
    wrapped = body if layout in ("app", "auth") else f"<main class=plain>{body}</main>"
    doc = (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>{wrapped}{tag}</body></html>"
    )
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": (
            f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
        ),
    }
    return HTMLResponse(doc, status_code=status, headers=headers)


async def read_form(request: Request) -> dict[str, str]:
    body = await request.body()
    if len(body) > 10_000:
        return {}
    return {k: v[0] for k, v in parse_qs(body.decode("utf-8", "ignore")).items()}


def register_web(mcp, cfg: Config, db: DB, limiter: RateLimiter, provider: NotifyOAuthProvider) -> None:
    counter = {"n": 0}

    def auth(request: Request):
        sid = request.cookies.get("cn_sid")
        if not sid:
            return None, None
        session = db.get_session(sid)
        if not session or not session["user_id"]:
            return sid, None
        return sid, db.active(db.user_by_id(session["user_id"]))

    def set_cookie(resp: Response, sid: str) -> None:
        resp.set_cookie("cn_sid", sid, httponly=True, secure=cfg.secure, samesite="lax", max_age=30 * 86400, path="/")

    def csrf_field(sid: str) -> str:
        return f'<input type="hidden" name="csrf" value="{csrf_token(cfg.session_secret, sid)}">'

    def post_form(sid: str, action: str, label: str, extra: str = "", cls: str = "") -> str:
        return f'<form method="post" action="{action}">{csrf_field(sid)}{extra}<button class="{cls}">{esc(label)}</button></form>'

    # ------------------------------------------------------------------ basics
    @mcp.custom_route("/", methods=["GET"])
    async def root(request: Request) -> Response:
        if cfg.landing_url:
            return RedirectResponse(cfg.landing_url, 302)
        return page("Agent Notifier", '<h1>Agent Notifier</h1><p>Get pinged when your AI finishes.</p><a class="btn" href="/login">Sign in with Telegram</a>')

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------ login
    @mcp.custom_route("/login", methods=["GET"])
    async def login(request: Request) -> Response:
        nxt = safe_next(request.query_params.get("next"))
        sid, user = auth(request)
        if user:
            return RedirectResponse(nxt, 303)
        ip = request.client.host if request.client else "unknown"
        if not limiter.allow(f"login:{ip}", 20, 60):
            return page("Slow down", "<h1>Too many attempts</h1><p>Wait a minute and retry.</p>", status=429)
        counter["n"] += 1
        if counter["n"] % 50 == 0:
            db.purge()
        session = db.get_session(sid) if sid else None
        new_sid = None
        if session and not session["user_id"] and session["login_code"]:
            code = session["login_code"]
        else:
            new_sid, code = db.new_session(ip, request.headers.get("user-agent", ""))
        link = f"https://t.me/{cfg.tg_bot_username}?start={code}"
        body = auth_page(link)
        js = (
            f"var next={json.dumps(nxt)};var t0=Date.now();"
            "async function poll(){try{var r=await fetch('/login/status',{cache:'no-store'});var j=await r.json();"
            "if(j.approved){location.href=next;return}}catch(e){}"
            "if(Date.now()-t0>600000){document.getElementById('st').textContent='Expired. Reload this page.';return}"
            "setTimeout(poll,2000)}poll();"
        )
        resp = page("Sign in", body, js, layout="auth")
        if new_sid:
            set_cookie(resp, new_sid)
        return resp

    @mcp.custom_route("/login/status", methods=["GET"])
    async def login_status(request: Request) -> Response:
        _, user = auth(request)
        return JSONResponse({"approved": bool(user)}, headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------------ dashboard
    def dashboard(user, sid: str, flash: str = "", new_token: str | None = None) -> HTMLResponse:
        uid = user["id"]
        tokens = [dict(t) for t in db.list_pats(uid)]
        ntfy_on = bool(user["ntfy_enabled"])
        forms = {
            "logout": post_form(sid, "/app/logout", "Sign out", "", "ghost"),
            "test": post_form(sid, "/app/test", "Send a test notification"),
            "ntfy_on": post_form(sid, "/app/ntfy", "Enable ntfy", "<input type=hidden name=enable value=1>", "ghost"),
            "ntfy_off": post_form(sid, "/app/ntfy", "Disable ntfy", "<input type=hidden name=enable value=0>", "ghost"),
            "revoke": lambda tid: post_form(sid, "/app/token/revoke", "Revoke", "<input type=hidden name=id value=" + esc(tid) + ">", "ghost sm"),
            "create_token": (
                f"<form method='post' action='/app/token'>{csrf_field(sid)}<div class='inline'>"
                "<input type='text' name='label' placeholder='label, e.g. laptop-codex' maxlength='40'><button>Create token</button></div></form>"
            ),
            "delete": (
                f"<form method='post' action='/app/delete'>{csrf_field(sid)}<div class='inline'>"
                "<input type='text' name='confirm' placeholder='type DELETE'><button class='danger'>Delete</button></div></form>"
            ),
        }
        body = dashboard_html(
            name=user["tg_name"] or "Telegram user", flash=flash, new_token=new_token, mcp_url=cfg.mcp_url, tokens=tokens,
            oauth_apps=db.oauth_apps(uid), series=db.usage_series(uid, 14), today=db.usage_today(uid), per_day=cfg.rate_per_day,
            per_min=cfg.rate_per_min, pending=db.inbox_pending(uid), ntfy_on=ntfy_on, ntfy_topic=user["ntfy_topic"],
            ntfy_server=cfg.ntfy_server, forms=forms, is_admin=str(user["tg_chat_id"]) in cfg.admin_ids,
        )
        low = flash.lower()
        start = "tokens" if (new_token or "token" in low) else "channels" if "ntfy" in low else "settings" if flash else "overview"
        script = (f"window.__start={json.dumps(start)};" + DASH_JS)
        return page("Dashboard", body, script, layout="app")

    @mcp.custom_route("/app", methods=["GET"])
    async def app_home(request: Request) -> Response:
        sid, user = auth(request)
        if not user:
            return RedirectResponse("/login", 303)
        return dashboard(user, sid)

    async def guarded(request: Request):
        """Common checks for dashboard POSTs: returns (sid, user, form) or an error Response."""
        sid, user = auth(request)
        if not user:
            return RedirectResponse("/login", 303)
        form = await read_form(request)
        if not csrf_ok(cfg.session_secret, sid, form.get("csrf", "")):
            return page("Blocked", "<h1>Request blocked</h1><p>Reload the page and try again.</p>", status=403)
        return sid, user, form

    @mcp.custom_route("/app/token", methods=["POST"])
    async def make_token(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        sid, user, form = g
        token = db.create_pat(user["id"], form.get("label", ""))
        if not token:
            return dashboard(user, sid, "Token limit reached (10). Revoke one first.")
        return dashboard(user, sid, new_token=token)

    @mcp.custom_route("/app/token/revoke", methods=["POST"])
    async def revoke_token(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        sid, user, form = g
        db.revoke_pat(user["id"], form.get("id", ""))
        return dashboard(user, sid, "Token revoked.")

    @mcp.custom_route("/app/ntfy", methods=["POST"])
    async def toggle_ntfy(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        sid, user, form = g
        db.set_ntfy(user["id"], form.get("enable") == "1")
        return dashboard(db.user_by_id(user["id"]), sid, "ntfy setting saved.")

    @mcp.custom_route("/app/test", methods=["POST"])
    async def test_notify(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        sid, user, _ = g
        res = await deliver(cfg, db, limiter, user, "Test from Agent Notifier. If you see this, it works.", "Test", "high")
        msg = f"Sent via: {', '.join(res['sent'])}" if res["sent"] else f"Not sent: {res.get('error') or res['failed']}"
        return dashboard(user, sid, msg)

    @mcp.custom_route("/app/logout", methods=["POST"])
    async def logout(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        sid, _, _ = g
        db.delete_session(sid)
        resp = RedirectResponse("/login", 303)
        resp.delete_cookie("cn_sid", path="/")
        return resp

    @mcp.custom_route("/app/delete", methods=["POST"])
    async def delete_account(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        sid, user, form = g
        if form.get("confirm", "").strip() != "DELETE":
            return dashboard(user, sid, "Type DELETE to confirm.")
        db.delete_user(user["id"])
        resp = page("Deleted", "<h1>Account deleted</h1><p>Your data was removed.</p>")
        resp.delete_cookie("cn_sid", path="/")
        return resp

    # ------------------------------------------------------------------ OAuth consent
    @mcp.custom_route("/oauth/consent", methods=["GET"])
    async def consent_page(request: Request) -> Response:
        req = request.query_params.get("req", "")
        pend = provider.pending(req)
        if not pend:
            return page("Expired", "<h1>Request expired</h1><p>Go back to your app and connect again.</p>", status=400)
        sid, user = auth(request)
        if not user:
            return RedirectResponse("/login?next=" + quote(f"/oauth/consent?req={req}", safe=""), 303)
        client_id, params = pend
        client = await provider.get_client(client_id)
        name = (client.client_name if client and client.client_name else "An application")[:80]
        host = urlparse(str(params.redirect_uri)).netloc
        body = (
            "<h1>Allow access?</h1><div class='card'>"
            f"<p><b>{esc(name)}</b> wants to send notifications to your Telegram as <b>{esc(user['tg_name'] or 'you')}</b>.</p>"
            f"<p>It will return you to <span class='mono'>{esc(host)}</span>.</p>"
            f"<form method='post' action='/oauth/consent'>{csrf_field(sid)}<input type='hidden' name='req' value='{esc(req)}'>"
            "<button name='action' value='allow'>Allow</button> <button class='ghost' name='action' value='deny'>Deny</button></form></div>"
            "<p>Only allow apps you started connecting just now. You can revoke access by deleting the connector.</p>"
        )
        return page("Allow access", body)

    @mcp.custom_route("/oauth/consent", methods=["POST"])
    async def consent_submit(request: Request) -> Response:
        g = await guarded(request)
        if isinstance(g, Response):
            return g
        _, user, form = g
        req = form.get("req", "")
        pend = provider.pending(req)
        if not pend:
            return page("Expired", "<h1>Request expired</h1><p>Go back to your app and connect again.</p>", status=400)
        client_id, params = pend
        provider.finish_pending(req)
        base = str(params.redirect_uri)
        if form.get("action") == "allow":
            code = provider.issue_code(user["id"], client_id, params)
            url = construct_redirect_uri(base, code=code, state=params.state)
        else:
            url = construct_redirect_uri(base, error="access_denied", state=params.state)
        return RedirectResponse(url, 303)

    # ------------------------------------------------------------------ Telegram webhook
    @mcp.custom_route("/telegram/webhook/{secret}", methods=["POST"])
    async def webhook(request: Request) -> Response:
        header = request.headers.get("x-telegram-bot-api-secret-token", "").encode()
        path = request.path_params.get("secret", "").encode()
        want = cfg.tg_webhook_secret.encode()
        if not (hmac.compare_digest(header, want) and hmac.compare_digest(path, want)):
            return Response(status_code=403)
        body = await request.body()
        if len(body) > 100_000:
            return Response(status_code=413)
        try:
            await tg.handle_update(cfg, db, limiter, json.loads(body))
        except Exception as exc:  # noqa: BLE001 - always 200 so Telegram does not retry forever
            print(f"webhook error: {type(exc).__name__}", flush=True)
        return JSONResponse({"ok": True})

    # ------------------------------------------------------------------ REST API (hooks, scripts)
    @mcp.custom_route("/api/notify", methods=["POST"])
    async def api_notify(request: Request) -> Response:
        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        uid = db.pat_user(token) if token.startswith(PAT_PREFIX) else None
        user = db.active(db.user_by_id(uid)) if uid else None
        if not user:
            return JSONResponse({"error": "invalid or missing token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        body = await request.body()
        if len(body) > 20_000:
            return JSONResponse({"error": "body too large"}, status_code=413)
        try:
            data = json.loads(body)
            message = str(data["message"])
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": 'JSON body needs a "message" field'}, status_code=400)
        channels = data.get("channels") if isinstance(data.get("channels"), list) else None
        res = await deliver(cfg, db, limiter, user, message, str(data.get("title", "Claude")), str(data.get("priority", "normal")), channels)
        return JSONResponse(res, status_code=200 if res["sent"] else 502 if not res.get("error") else 429)

    register_admin(mcp, cfg, db, limiter, auth, read_form, csrf_ok, csrf_field, page,
                   lambda sid: post_form(sid, "/app/logout", "Sign out", "", "ghost"))
