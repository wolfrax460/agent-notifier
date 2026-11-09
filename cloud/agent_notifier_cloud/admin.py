"""Super-admin console: /admin/*. Only Telegram IDs listed in ADMIN_TG_IDS get in; everyone else sees a 404.

Admins can see account metadata and usage counts. They can NOT see message contents or token values (never stored in readable form).
Every state-changing action needs a CSRF token and is written to the audit log.
"""
from __future__ import annotations

import asyncio
import os
import time

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from . import telegram as tg
from .ui import esc
from . import ui_admin as A

PER_PAGE = 25


def register_admin(mcp, cfg, db, limiter, auth, read_form, csrf_ok, csrf_field, page, logout_form) -> None:
    started = time.time()

    def is_admin(user) -> bool:
        return bool(user) and str(user["tg_chat_id"]) in cfg.admin_ids

    def not_found() -> Response:
        return page("Not found", "<h1>Not found</h1><p>This page does not exist.</p>", status=404)

    def gate(request: Request):
        """-> (sid, admin_user) or a Response."""
        sid, user = auth(request)
        if not user:
            return RedirectResponse("/login?next=" + request.url.path, 303)
        if not is_admin(user):
            return not_found()
        return sid, user

    async def gate_post(request: Request):
        g = gate(request)
        if isinstance(g, Response):
            return g
        sid, user = g
        form = await read_form(request)
        if not csrf_ok(cfg.session_secret, sid, form.get("csrf", "")):
            return page("Blocked", "<h1>Request blocked</h1><p>Reload the page and try again.</p>", status=403)
        if not limiter.allow(f"admin:{user['id']}", 60, 60):
            return page("Slow down", "<h1>Too many actions</h1><p>Wait a minute.</p>", status=429)
        return sid, user, form

    def render(admin, sid, active, title, lede, inner, flash="", status=200):
        stats_total = db.one("SELECT COUNT(*) FROM users")[0]
        body = A.shell(active, title, lede, inner, admin_name=admin["tg_name"] or "Admin", logout=logout_form(sid), flash=flash, users_total=stats_total)
        return page(f"Admin: {title}", body, layout="app", status=status)

    def pform(sid, action, label, extra="", cls=""):
        return f'<form method="post" action="{action}">{csrf_field(sid)}{extra}<button class="{cls}">{esc(label)}</button></form>'

    # ------------------------------------------------------------------ overview
    @mcp.custom_route("/admin", methods=["GET"])
    async def admin_home(request: Request) -> Response:
        g = gate(request)
        if isinstance(g, Response):
            return g
        sid, admin = g
        s = db.admin_stats(14)
        sysinfo = {
            "Uptime": f"{int((time.time() - started) // 3600)}h {int((time.time() - started) % 3600 // 60)}m",
            "Database": f"{db.db_size(cfg.db_path) / 1024:.0f} KB",
            "Limits": f"{cfg.rate_per_min}/min, {cfg.rate_per_day}/day",
            "Public URL": cfg.public_url,
            "Admins": len(cfg.admin_ids),
        }
        return render(admin, sid, "overview", "Overview", "Everything happening across all users.", A.overview(s, sysinfo))

    # ------------------------------------------------------------------ users
    @mcp.custom_route("/admin/users", methods=["GET"])
    async def admin_users(request: Request) -> Response:
        g = gate(request)
        if isinstance(g, Response):
            return g
        sid, admin = g
        q = request.query_params.get("q", "").strip()[:60]
        status = request.query_params.get("status", "all")
        status = status if status in ("all", "active", "suspended") else "all"
        try:
            pg = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            pg = 1
        rows, total = db.admin_users(q, PER_PAGE, (pg - 1) * PER_PAGE, status)
        return render(admin, sid, "users", "Users", "Every account on the service.", A.users_page(rows, total, q, status, pg, PER_PAGE, cfg.admin_ids))

    def detail(admin, sid, uid, flash="", status=200):
        u = db.admin_user(uid)
        if not u:
            return not_found()
        target_admin = str(u["tg_chat_id"]) in cfg.admin_ids
        series = db.usage_series(uid, 14)
        suspended = bool(u["suspended"])
        forms = {
            "suspend": pform(sid, f"/admin/users/{uid}/suspend", "Unsuspend user" if suspended else "Suspend user",
                             f"<input type=hidden name=value value={'0' if suspended else '1'}>", "ghost" if suspended else "danger"),
            "revoke": pform(sid, f"/admin/users/{uid}/revoke", "Revoke all tokens and sessions", "", "ghost"),
            "message": (f"<form method='post' action='/admin/users/{uid}/message'>{csrf_field(sid)}"
                        "<textarea name='text' maxlength='1000' placeholder='Message sent to this user on Telegram'></textarea>"
                        "<div style='margin-top:10px'><button>Send message</button></div></form>"),
            "delete": (f"<form method='post' action='/admin/users/{uid}/delete'>{csrf_field(sid)}<div class='inline'>"
                       "<input type='text' name='confirm' placeholder='type DELETE'><button class='danger'>Delete user</button></div></form>"),
        }
        inner = A.user_detail(dict(u), db.admin_tokens(uid), series, sum(v for _, v in series), db.usage_today(uid), db.oauth_apps(uid),
                              db.inbox_pending(uid), target_admin, forms)
        return render(admin, sid, "users", u["tg_name"] or "User", "Account details and controls.", inner, flash, status)

    @mcp.custom_route("/admin/users/{uid}", methods=["GET"])
    async def admin_user(request: Request) -> Response:
        g = gate(request)
        if isinstance(g, Response):
            return g
        sid, admin = g
        return detail(admin, sid, request.path_params["uid"])

    def target_of(request, admin):
        uid = request.path_params["uid"]
        u = db.admin_user(uid)
        if not u:
            return uid, None, "User not found."
        return uid, u, None

    @mcp.custom_route("/admin/users/{uid}/suspend", methods=["POST"])
    async def admin_suspend(request: Request) -> Response:
        g = await gate_post(request)
        if isinstance(g, Response):
            return g
        sid, admin, form = g
        uid, u, err = target_of(request, admin)
        if err:
            return render(admin, sid, "users", "Users", "", "", err, 404)
        if str(u["tg_chat_id"]) in cfg.admin_ids:
            return detail(admin, sid, uid, "Admin accounts cannot be suspended.", 403)
        value = form.get("value") == "1"
        db.set_suspended(uid, value)
        db.audit(admin["id"], "suspend" if value else "unsuspend", uid, u["tg_name"] or "")
        return detail(admin, sid, uid, "User suspended and signed out." if value else "User unsuspended.")

    @mcp.custom_route("/admin/users/{uid}/revoke", methods=["POST"])
    async def admin_revoke(request: Request) -> Response:
        g = await gate_post(request)
        if isinstance(g, Response):
            return g
        sid, admin, form = g
        uid, u, err = target_of(request, admin)
        if err:
            return render(admin, sid, "users", "Users", "", "", err, 404)
        if str(u["tg_chat_id"]) in cfg.admin_ids:
            return detail(admin, sid, uid, "Not allowed on admin accounts.", 403)
        db.revoke_everything(uid)
        db.audit(admin["id"], "revoke_all", uid, u["tg_name"] or "")
        return detail(admin, sid, uid, "All tokens, connections and sessions revoked.")

    @mcp.custom_route("/admin/users/{uid}/message", methods=["POST"])
    async def admin_message(request: Request) -> Response:
        g = await gate_post(request)
        if isinstance(g, Response):
            return g
        sid, admin, form = g
        uid, u, err = target_of(request, admin)
        if err:
            return render(admin, sid, "users", "Users", "", "", err, 404)
        text = form.get("text", "").strip()[:1000]
        if not text:
            return detail(admin, sid, uid, "Write a message first.", 400)
        try:
            await tg.send(cfg, u["tg_chat_id"], "Message from the Agent Notifier admin\n\n" + text)
        except tg.DeliveryError as exc:
            return detail(admin, sid, uid, f"Not delivered: {exc}", 502)
        db.audit(admin["id"], "message", uid, f"{len(text)} chars")
        return detail(admin, sid, uid, "Message sent.")

    @mcp.custom_route("/admin/users/{uid}/delete", methods=["POST"])
    async def admin_delete(request: Request) -> Response:
        g = await gate_post(request)
        if isinstance(g, Response):
            return g
        sid, admin, form = g
        uid, u, err = target_of(request, admin)
        if err:
            return render(admin, sid, "users", "Users", "", "", err, 404)
        if str(u["tg_chat_id"]) in cfg.admin_ids:
            return detail(admin, sid, uid, "Admin accounts cannot be deleted here.", 403)
        if form.get("confirm", "").strip() != "DELETE":
            return detail(admin, sid, uid, "Type DELETE to confirm.", 400)
        db.delete_user(uid)
        db.audit(admin["id"], "delete_user", uid, u["tg_name"] or "")
        rows, total = db.admin_users("", PER_PAGE, 0, "all")
        return render(admin, sid, "users", "Users", "Every account on the service.", A.users_page(rows, total, "", "all", 1, PER_PAGE, cfg.admin_ids), "User deleted.")

    # ------------------------------------------------------------------ broadcast
    def bform(sid):
        return (f"<form method='post' action='/admin/broadcast'>{csrf_field(sid)}"
                "<textarea name='text' maxlength='1000' placeholder='Announcement text'></textarea>"
                "<div class='inline' style='margin-top:10px'><input type='text' name='confirm' placeholder='type SEND to confirm'><button>Send to everyone</button></div></form>")

    @mcp.custom_route("/admin/broadcast", methods=["GET"])
    async def admin_broadcast(request: Request) -> Response:
        g = gate(request)
        if isinstance(g, Response):
            return g
        sid, admin = g
        return render(admin, sid, "broadcast", "Broadcast", "Message every active user.", A.broadcast_page(bform(sid), len(db.broadcast_targets())))

    @mcp.custom_route("/admin/broadcast", methods=["POST"])
    async def admin_broadcast_send(request: Request) -> Response:
        g = await gate_post(request)
        if isinstance(g, Response):
            return g
        sid, admin, form = g
        text = form.get("text", "").strip()[:1000]
        targets = db.broadcast_targets()
        if not text or form.get("confirm", "").strip() != "SEND":
            return render(admin, sid, "broadcast", "Broadcast", "Message every active user.", A.broadcast_page(bform(sid), len(targets)), "Write a message and type SEND to confirm.", 400)
        if not limiter.allow("broadcast", 3, 3600):
            return render(admin, sid, "broadcast", "Broadcast", "Message every active user.", A.broadcast_page(bform(sid), len(targets)), "Limit: 3 broadcasts per hour.", 429)
        sent = failed = 0
        for t in targets[:2000]:
            try:
                await tg.send(cfg, t["tg_chat_id"], "Agent Notifier announcement\n\n" + text)
                sent += 1
            except tg.DeliveryError:
                failed += 1
            await asyncio.sleep(0.05)
        db.audit(admin["id"], "broadcast", "", f"sent {sent}, failed {failed}, {len(text)} chars")
        return render(admin, sid, "broadcast", "Broadcast", "Message every active user.", A.broadcast_page(bform(sid), len(targets)), f"Sent to {sent} users, {failed} failed.")

    # ------------------------------------------------------------------ audit
    @mcp.custom_route("/admin/audit", methods=["GET"])
    async def admin_audit(request: Request) -> Response:
        g = gate(request)
        if isinstance(g, Response):
            return g
        sid, admin = g
        return render(admin, sid, "audit", "Audit log", "Every admin action, newest first.", A.audit_page(db.audit_list(100)))
