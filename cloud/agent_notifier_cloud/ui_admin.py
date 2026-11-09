"""Admin console HTML. Same design system as ui.py. No message contents or secrets are ever shown here."""
from __future__ import annotations

import time
from urllib.parse import urlencode

from .ui import LOGO, chart_svg, esc, icon

NAV = [("overview", "/admin", "Overview", "home"), ("users", "/admin/users", "Users", "users"),
       ("broadcast", "/admin/broadcast", "Broadcast", "megaphone"), ("audit", "/admin/audit", "Audit log", "list")]


def _date(ts) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else "never"


def shell(active: str, title: str, lede: str, inner: str, *, admin_name: str, logout: str, flash: str = "", users_total: int = 0) -> str:
    nav = "".join(f'<a href="{href}" class="{"on" if key == active else ""}">{icon(ic)}<span>{lbl}</span></a>' for key, href, lbl, ic in NAV)
    nav += f'<h6>ACCOUNT</h6><a href="/app">{icon("back")}<span>My dashboard</span></a>'
    flash_html = f"<div class='flash'>{esc(flash)}</div>" if flash else ""
    return (
        '<div class="shell"><aside class="side">'
        f'<div class="brand"><i>{LOGO}</i><div><b>Agent Notifier</b><span>Admin console</span></div></div>'
        f'<nav class="nav" aria-label="Admin"><h6>OPERATIONS</h6>{nav}</nav>'
        f'<div class="me"><small>Admin</small><b>{esc(admin_name)}</b>{logout}</div></aside>'
        f'<div class="main"><header class="top"><span class="crumb">Admin / {esc(title)}</span><span class="grow"></span>'
        f'<span class="pill warn">Admin</span><span class="pill">{users_total} users</span></header>'
        f'<div class="content">{flash_html}<h1 class="title">{esc(title)}</h1><p class="lede">{esc(lede)}</p>{inner}</div></div></div>'
    )


def status_badge(u: dict) -> str:
    return '<span class="badge2 bad">Suspended</span>' if u["suspended"] else '<span class="badge2 ok">Active</span>'


def overview(s: dict, sysinfo: dict) -> str:
    stat = lambda label, value, sub, cls="": f'<div class="card stat"><small>{label}</small><b class="{cls}">{value}</b><span>{sub}</span></div>'
    top = "".join(
        f'<tr><td><a class="who" href="/admin/users/{esc(r["id"])}">{esc(r["tg_name"] or "unnamed")}</a></td><td class="r">{r["n"]}</td></tr>' for r in s["top_today"]
    ) or '<tr><td colspan="2" class="empty">No activity yet today.</td></tr>'
    recent = "".join(
        f'<tr><td><a class="who" href="/admin/users/{esc(r["id"])}">{esc(r["tg_name"] or "unnamed")}</a></td><td class="r">{_date(r["created"])}</td></tr>' for r in s["recent"]
    ) or '<tr><td colspan="2" class="empty">No users.</td></tr>'
    sys_rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(str(v))}</dd>" for k, v in sysinfo.items())
    return (
        '<div class="grid4">'
        + stat("Total users", s["users"], f'{s["new7"]} joined in 7 days')
        + stat("Active today", s["active_today"], f'{s["active7"]} in the last 7 days')
        + stat("Messages today", s["sent_today"], f'{s["sent14"]} in 14 days')
        + stat("Suspended", s["suspended"], "locked out", "hot" if s["suspended"] else "")
        + "</div>"
        '<div class="grid4">'
        + stat("Active tokens", s["tokens"], "personal access tokens")
        + stat("Sign-in apps", s["oauth_apps"], "OAuth connections")
        + stat("ntfy users", s["ntfy"], "push enabled")
        + stat("Waiting replies", s["pending"], "unread by their AI")
        + "</div>"
        '<div class="grid2"><div class="card"><div class="chead"><h2>Messages per day, all users</h2><span class="tag">14 days</span></div>'
        f'{chart_svg(s["sent_series"])}</div>'
        '<div class="card"><div class="chead"><h2>New users per day</h2><span class="tag">14 days</span></div>'
        f'{chart_svg(s["new_series"])}</div></div>'
        '<div class="grid3" style="margin-top:14px">'
        f'<div class="card"><h2>Top senders today</h2><table><tbody>{top}</tbody></table></div>'
        f'<div class="card"><h2>Newest users</h2><table><tbody>{recent}</tbody></table></div>'
        f'<div class="card"><h2>System</h2><dl class="kv">{sys_rows}</dl></div></div>'
    )


def users_page(rows: list[dict], total: int, q: str, status: str, page: int, per: int, admin_ids: tuple) -> str:
    def link(**kw):
        base = {"q": q, "status": status, "page": 1}
        base.update(kw)
        return "/admin/users?" + urlencode({k: v for k, v in base.items() if v not in ("", None, "all") or k == "page"})
    seg = "".join(f'<a class="{"on" if status == k else ""}" href="{link(status=k)}">{lbl}</a>' for k, lbl in (("all", "All"), ("active", "Active"), ("suspended", "Suspended")))
    body = "".join(
        f'<tr class="link"><td><a class="who" href="/admin/users/{esc(r["id"])}">{esc(r["tg_name"] or "unnamed")}</a>'
        f'{" <span class=badge2>admin</span>" if r["tg_chat_id"] in admin_ids else ""}</td>'
        f'<td class="mono">{esc(r["tg_chat_id"])}</td><td>{_date(r["created"])}</td><td>{esc(r["last_day"] or "never")}</td>'
        f'<td class="r">{r["m_today"]}</td><td class="r">{r["m14"]}</td><td class="r">{r["toks"]}</td><td>{status_badge(r)}</td></tr>'
        for r in rows
    ) or '<tr><td colspan="8" class="empty">No users match.</td></tr>'
    pages = max(1, (total + per - 1) // per)
    prev = f'<a class="btn ghost sm" href="{link(page=page - 1)}">Previous</a>' if page > 1 else ""
    nxt = f'<a class="btn ghost sm" href="{link(page=page + 1)}">Next</a>' if page < pages else ""
    return (
        f'<div class="toolbar"><form method="get" action="/admin/users"><input type="text" name="q" value="{esc(q)}" placeholder="Search name, Telegram ID or user ID" maxlength="60">'
        f'<input type="hidden" name="status" value="{esc(status)}"><button>Search</button></form><div class="seg">{seg}</div></div>'
        '<div class="card"><div class="tbl-wrap"><table><thead><tr><th>User</th><th>Telegram ID</th><th>Joined</th><th>Last active</th>'
        '<th class="r">Today</th><th class="r">14 days</th><th class="r">Tokens</th><th>Status</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
        f'<div class="pager">{prev}<span>Page {page} of {pages} ({total} users)</span>{nxt}</div></div>'
    )


def user_detail(u: dict, tokens: list[dict], series: list, sent14: int, today: int, apps: int, pending: int, is_admin_target: bool, forms: dict) -> str:
    rows = "".join(
        f"<tr><td>{esc(t['label'] or 'token')}</td><td>{_date(t['created'])}</td><td>{_date(t['last_used'])}</td></tr>" for t in tokens
    ) or '<tr><td colspan="3" class="empty">No active tokens.</td></tr>'
    if is_admin_target:
        actions = "<p>This is an admin account. Suspend, revoke and delete are disabled for admins.</p>" + forms["message"]
    else:
        actions = (
            f'<div class="actions">{forms["suspend"]}{forms["revoke"]}</div>'
            f'<h2 style="margin-top:18px">Send a message</h2>{forms["message"]}'
            f'<h2 style="margin-top:18px">Delete account</h2><p>Permanently removes the user, tokens, connections and replies.</p>{forms["delete"]}'
        )
    return (
        '<div class="grid4">'
        f'<div class="card stat"><small>Status</small><b style="font-size:1.3rem">{status_badge(u)}</b><span>joined {_date(u["created"])}</span></div>'
        f'<div class="card stat"><small>Sent today</small><b>{today}</b><span>messages</span></div>'
        f'<div class="card stat"><small>Last 14 days</small><b>{sent14}</b><span>messages</span></div>'
        f'<div class="card stat"><small>Connections</small><b>{len(tokens) + apps}</b><span>{len(tokens)} tokens, {apps} sign-in</span></div></div>'
        '<div class="grid2"><div class="stack">'
        f'<div class="card"><div class="chead"><h2>Messages per day</h2><span class="tag">14 days</span></div>{chart_svg(series)}</div>'
        f'<div class="card"><h2>Active tokens</h2><table><thead><tr><th>Label</th><th>Created</th><th>Last used</th></tr></thead><tbody>{rows}</tbody></table></div></div>'
        '<div class="stack"><div class="card"><h2>Profile</h2><dl class="kv">'
        f'<dt>Name</dt><dd>{esc(u["tg_name"] or "unnamed")}</dd><dt>Telegram ID</dt><dd>{esc(u["tg_chat_id"])}</dd><dt>User ID</dt><dd>{esc(u["id"])}</dd>'
        f'<dt>ntfy</dt><dd>{"on" if u["ntfy_enabled"] else "off"}</dd><dt>Waiting replies</dt><dd>{pending}</dd></dl></div>'
        f'<div class="card"><h2>Actions</h2>{actions}</div></div></div>'
    )


def broadcast_page(form: str, count: int) -> str:
    return (
        f'<div class="card"><h2>Announcement to all active users</h2><p>Sent on Telegram to {count} users. Suspended users are skipped. Keep it short and useful.</p>{form}</div>'
    )


def audit_page(rows: list[dict]) -> str:
    body = "".join(
        f"<tr><td>{time.strftime('%Y-%m-%d %H:%M', time.gmtime(r['ts']))}</td><td>{esc(r['admin'] or 'unknown')}</td>"
        f"<td>{esc(r['action'])}</td><td class='mono'>{esc(r['target'] or '')}</td><td>{esc(r['detail'] or '')}</td></tr>" for r in rows
    ) or '<tr><td colspan="5" class="empty">No admin actions yet.</td></tr>'
    return ('<div class="card"><div class="tbl-wrap"><table><thead><tr><th>Time (UTC)</th><th>Admin</th><th>Action</th><th>Target</th><th>Detail</th></tr></thead>'
            f"<tbody>{body}</tbody></table></div></div>")
