"""HTML/CSS for the hosted pages: shared styles, sign-in page, and the dashboard (sidebar layout).

Pure functions that return strings. No secrets are handled here; callers pass already-escaped-safe values
through `esc` where noted. Scripts run under a CSP nonce, so there are no inline event handlers.
"""
from __future__ import annotations

import html
import time

esc = html.escape

CSS = """
:root{color-scheme:dark;--bg:#070A0F;--bg2:#0B1017;--card:#101722;--card2:#161F2D;--line:#1F2B3D;--line2:#2B3A52;--fg:#EAF0F7;--mut:#92A1B7;--dim:#5F6F86;
--acc:#3DDC97;--acc2:#5BE8AB;--acc-ink:#04180F;--bad:#F87171;--amber:#FFC93C;--side:236px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--acc)}b,strong{color:var(--fg)}p{margin:.3rem 0 .7rem;color:var(--mut)}
code,.mono{font-family:ui-monospace,"JetBrains Mono",Consolas,monospace;font-size:.84rem}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:8px}
button,.btn{background:var(--acc);color:var(--acc-ink);border:1px solid var(--acc);border-radius:10px;padding:9px 16px;font:600 .9rem/1.2 Inter,system-ui,sans-serif;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:8px;transition:transform .15s,box-shadow .15s,background .15s,border-color .15s}
button:hover,.btn:hover{background:var(--acc2);transform:translateY(-1px);box-shadow:0 8px 22px -10px rgba(61,220,151,.8)}
button.ghost,.btn.ghost{background:transparent;border-color:var(--line2);color:var(--fg);box-shadow:none}
button.ghost:hover,.btn.ghost:hover{border-color:var(--acc);background:var(--card2)}
button.danger{background:transparent;border-color:#7f1d1d;color:var(--bad);box-shadow:none}
button.danger:hover{background:#3a1212}
button.sm{padding:6px 12px;font-size:.84rem}
input[type=text]{background:#06090D;border:1px solid var(--line2);border-radius:10px;color:var(--fg);padding:9px 12px;font:inherit;width:min(280px,100%)}
input[type=text]::placeholder{color:var(--dim)}
form{display:inline-block;margin:0}
.inline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
code.block{display:block;background:#06090D;border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:10px 0;word-break:break-all;color:var(--acc)}
.pre{position:relative;margin:10px 0}
.pre pre{margin:0;background:#06090D;border:1px solid var(--line);border-radius:12px;padding:14px 16px;overflow-x:auto;color:var(--fg);font:400 .82rem/1.7 ui-monospace,"JetBrains Mono",Consolas,monospace}
.pre button{position:absolute;right:8px;top:8px}

/* plain pages (errors, consent) */
main.plain{max-width:560px;margin:0 auto;padding:48px 18px}
main.plain h1{font-size:1.5rem;margin:.2rem 0 1rem;letter-spacing:-.02em}
main.plain .card{margin:14px 0}
.card{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:0 18px 40px -30px rgba(0,0,0,.9)}
.card h2{font-size:.98rem;margin:0 0 .6rem;letter-spacing:-.01em}

/* auth (sign-in) */
.auth{min-height:100vh;display:grid;place-items:center;padding:24px 16px;background:radial-gradient(700px 420px at 50% -80px,rgba(61,220,151,.14),transparent 70%)}
.auth__box{width:min(430px,100%)}
.logo{display:flex;align-items:center;gap:10px;font:700 1.15rem/1 Inter,system-ui,sans-serif;margin-bottom:22px;justify-content:center}
.logo i{width:30px;height:30px;border-radius:9px;background:var(--acc);display:grid;place-items:center;box-shadow:0 0 22px rgba(61,220,151,.5)}
.auth h1{font-size:1.65rem;text-align:center;margin:0 0 6px;letter-spacing:-.025em}
.auth .sub{text-align:center;margin:0 0 22px}
.auth .card{padding:22px}
.auth ol{list-style:none;margin:0 0 18px;padding:0;display:grid;gap:14px}
.auth li{display:grid;grid-template-columns:30px 1fr;gap:12px;align-items:start;color:var(--mut)}
.auth li i{font-style:normal;width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:rgba(61,220,151,.1);border:1px solid rgba(61,220,151,.35);color:var(--acc);font-weight:700}
.auth .btn{width:100%;justify-content:center;padding:13px 16px;font-size:1rem}
.wait{display:flex;align-items:center;gap:10px;justify-content:center;margin-top:16px;color:var(--mut);font-size:.92rem}
.dot{width:9px;height:9px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 0 rgba(61,220,151,.6);animation:pulse 1.8s infinite;flex:none}
@keyframes pulse{70%{box-shadow:0 0 0 10px rgba(61,220,151,0)}100%{box-shadow:0 0 0 0 rgba(61,220,151,0)}}
.auth .fine{text-align:center;font-size:.85rem;color:var(--dim);margin-top:18px}
.back{display:block;text-align:center;margin-top:16px;font-size:.9rem}

/* app shell */
.shell{display:grid;grid-template-columns:var(--side) 1fr;min-height:100vh}
.side{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;background:var(--bg2);border-right:1px solid var(--line);padding:16px 12px}
.brand{display:flex;align-items:center;gap:11px;padding:4px 6px 16px}
.brand i{width:34px;height:34px;border-radius:10px;background:var(--acc);display:grid;place-items:center;box-shadow:0 0 20px rgba(61,220,151,.4);flex:none}
.brand b{display:block;font-size:.98rem;line-height:1.2}.brand span{font-size:.76rem;color:var(--mut)}
.nav{display:grid;gap:2px;margin-top:4px}
.nav h6{margin:14px 8px 6px;font-size:.68rem;letter-spacing:.09em;color:var(--dim);font-weight:600}
.nav a{display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:10px;color:var(--mut);text-decoration:none;font-weight:500;transition:background .12s,color .12s}
.nav a svg{width:18px;height:18px;flex:none;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.nav a:hover{background:var(--card);color:var(--fg)}
.nav a.on{background:var(--card2);color:var(--fg);box-shadow:inset 2px 0 0 var(--acc)}
.nav a.on svg{color:var(--acc)}
.nav .badge{margin-left:auto;background:var(--acc);color:var(--acc-ink);font-size:.7rem;font-weight:700;border-radius:999px;padding:1px 8px}
.me{margin-top:auto;border:1px solid var(--line);background:var(--card);border-radius:14px;padding:12px}
.me small{display:block;color:var(--mut);font-size:.76rem}
.me b{display:block;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.me .inline{flex-wrap:nowrap}.me form{flex:1}.me button{width:100%;justify-content:center}

.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 28px;border-bottom:1px solid var(--line);background:rgba(7,10,15,.85);backdrop-filter:blur(8px);position:sticky;top:0;z-index:5}
.top .grow{flex:1}
.crumb{font-size:.8rem;color:var(--dim)}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:.78rem;font-weight:600;border-radius:999px;padding:5px 11px;border:1px solid rgba(61,220,151,.35);background:rgba(61,220,151,.08);color:var(--acc)}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.off{border-color:var(--line2);background:transparent;color:var(--mut)}
.pill.warn{border-color:rgba(255,201,60,.4);background:rgba(255,201,60,.08);color:var(--amber)}
.main{min-width:0}
.content{padding:24px 28px 60px;max-width:1120px;min-width:0}
h1.title{font-size:1.6rem;margin:0 0 4px;letter-spacing:-.025em}
.lede{margin:0 0 20px}
.view{display:block}
.js .view{display:none}.js .view.on{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}
.grid2{display:grid;grid-template-columns:1.7fr 1fr;gap:14px;align-items:start}
.stat{padding:16px 18px}
.stat small{font-size:.72rem;letter-spacing:.08em;color:var(--mut);font-weight:600;text-transform:uppercase}
.stat b{display:block;font-size:1.9rem;line-height:1.15;margin:6px 0 2px;letter-spacing:-.02em}
.stat span{font-size:.8rem;color:var(--mut)}
.stat .up{color:var(--acc)}.stat .hot{color:var(--amber)}
.bar{height:6px;border-radius:99px;background:var(--line);overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--acc),var(--acc2));border-radius:99px}
.chart{width:100%;height:auto;display:block;margin-top:6px}
.chart text{fill:var(--dim);font:11px Inter,system-ui,sans-serif}
.chart rect.b{transition:opacity .15s}.chart rect.b:hover{opacity:.75}
.chead{display:flex;justify-content:space-between;align-items:center}
.tag{font-size:.74rem;border:1px solid var(--line2);border-radius:999px;padding:2px 10px;color:var(--mut)}
.todo{list-style:none;margin:0;padding:0;display:grid;gap:2px}
.todo li{display:flex;align-items:center;gap:11px;padding:10px 4px;border-top:1px solid var(--line);color:var(--fg)}
.todo li:first-child{border-top:0}
.todo .ck{width:20px;height:20px;border-radius:50%;border:1.5px solid var(--line2);display:grid;place-items:center;flex:none;color:transparent}
.todo li.done .ck{background:var(--acc);border-color:var(--acc);color:var(--acc-ink)}
.todo li.done span{color:var(--mut)}
.todo a{margin-left:auto;font-size:.82rem}
table{width:100%;border-collapse:collapse}
th{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);text-align:left;font-weight:600;padding:0 8px 8px}
td{padding:11px 8px;border-top:1px solid var(--line);color:var(--mut);font-size:.9rem}
td:first-child{color:var(--fg)}td.r,th.r{text-align:right}
.empty{padding:22px 8px;color:var(--dim);text-align:center}
.flash{border:1px solid rgba(61,220,151,.45);background:rgba(61,220,151,.08);border-radius:14px;padding:14px 16px;margin:0 0 16px}
.flash code.block{margin:8px 0}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.chan{display:flex;gap:14px;align-items:flex-start}
.chan .ic{width:38px;height:38px;border-radius:11px;background:var(--card2);border:1px solid var(--line2);display:grid;place-items:center;flex:none}
.chan .ic svg{width:19px;height:19px;stroke:var(--acc);fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.chan h3{margin:0 0 2px;font-size:.98rem;display:flex;gap:10px;align-items:center}
.danger-zone{border-color:#4a1d1d}


/* admin extras */
textarea{background:#06090D;border:1px solid var(--line2);border-radius:10px;color:var(--fg);padding:10px 12px;font:inherit;width:100%;min-height:110px;resize:vertical}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.toolbar form{display:flex;gap:10px;flex-wrap:wrap;align-items:center;flex:1}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:10px;overflow:hidden}
.seg a{padding:8px 14px;color:var(--mut);text-decoration:none;font-size:.86rem;font-weight:600}
.seg a.on{background:var(--card2);color:var(--fg)}
tr.link{cursor:pointer}tr.link:hover td{background:rgba(255,255,255,.02)}
td a.who{color:var(--fg);text-decoration:none;font-weight:600}td a.who:hover{color:var(--acc)}
.tbl-wrap{overflow-x:auto}
.badge2{display:inline-block;font-size:.72rem;font-weight:700;border-radius:999px;padding:2px 9px;border:1px solid var(--line2);color:var(--mut)}
.badge2.ok{border-color:rgba(61,220,151,.4);color:var(--acc);background:rgba(61,220,151,.08)}
.badge2.bad{border-color:rgba(248,113,113,.45);color:var(--bad);background:rgba(248,113,113,.08)}
.badge2.warn{border-color:rgba(255,201,60,.4);color:var(--amber);background:rgba(255,201,60,.08)}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 14px;margin:0}.kv dt{color:var(--dim);font-size:.82rem}.kv dd{margin:0;color:var(--fg);word-break:break-all}
.pager{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:14px;color:var(--mut);font-size:.86rem}
.actions{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.stack{display:grid;gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:16px}
@media (max-width:980px){.grid3{grid-template-columns:1fr}.kv{grid-template-columns:1fr}}

@media (max-width:980px){.grid4{grid-template-columns:repeat(2,1fr)}.grid2,.row2{grid-template-columns:1fr}}
@media (max-width:760px){
  .shell{grid-template-columns:1fr}
  .side{position:static;height:auto;flex-direction:row;align-items:center;gap:8px;overflow-x:auto;padding:10px 12px;border-right:0;border-bottom:1px solid var(--line)}
  .brand{padding:0 6px 0 0}.brand span,.nav h6,.me{display:none}
  .nav{display:flex;margin:0}.nav a{white-space:nowrap;padding:8px 12px}.nav a.on{box-shadow:none}
  .top{padding:12px 16px;position:static}.content{padding:18px 16px 50px}
  .grid4{grid-template-columns:1fr 1fr;gap:10px}.stat b{font-size:1.5rem}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

LOGO = (
    '<svg width="17" height="17" viewBox="0 0 14 14"><path d="M2.5 7.4l3 3L11.5 4" fill="none" stroke="#04180F" '
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

ICONS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "plug": '<path d="M9 2v6M15 2v6"/><path d="M6 8h12v4a6 6 0 0 1-12 0z"/><path d="M12 18v4"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "send": '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 3-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5c2.2.6 3.5 2.4 3.5 5.5"/>',
    "megaphone": '<path d="M3 11v3a1 1 0 0 0 1 1h2l8 4V6L6 10H4a1 1 0 0 0-1 1z"/><path d="M18 9a4 4 0 0 1 0 6"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
}


def icon(name: str) -> str:
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def chart_svg(series: list[tuple[str, int]]) -> str:
    """Bar chart of (label, value). Inline SVG, scales with the container."""
    w, h, pad_l, pad_b, pad_t = 700, 210, 30, 26, 8
    peak = max([v for _, v in series] + [1])
    top = peak if peak >= 4 else 4
    n = len(series)
    slot = (w - pad_l) / n
    bw = slot * 0.62
    parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Messages sent per day">',
             '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3DDC97"/>'
             '<stop offset="1" stop-color="#136B49"/></linearGradient></defs>']
    plot_h = h - pad_b - pad_t
    for i in range(3):
        y = pad_t + plot_h * i / 2
        val = round(top * (1 - i / 2))
        parts.append(f'<line x1="{pad_l}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}" stroke="#1F2B3D" stroke-dasharray="3 5"/>')
        parts.append(f'<text x="0" y="{y + 4:.1f}">{val}</text>')
    for i, (label, v) in enumerate(series):
        bh = max(plot_h * v / top, 2 if v == 0 else 4)
        x = pad_l + i * slot + (slot - bw) / 2
        y = pad_t + plot_h - bh
        fill = "url(#g)" if v else "#1F2B3D"
        parts.append(f'<rect class="b" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4" fill="{fill}"><title>{esc(label)}: {v}</title></rect>')
    parts.append(f'<text x="{pad_l}" y="{h - 6}">{esc(series[0][0])}</text>')
    parts.append(f'<text x="{w}" y="{h - 6}" text-anchor="end">{esc(series[-1][0])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def auth_page(link: str) -> str:
    return (
        '<div class="auth"><div class="auth__box">'
        f'<div class="logo"><i>{LOGO}</i>Agent Notifier</div>'
        "<h1>Sign in with Telegram</h1>"
        '<p class="sub">No password. Your Telegram account is your identity.</p>'
        '<div class="card"><ol>'
        "<li><i>1</i><span>Open the bot and press <b>Start</b>.</span></li>"
        "<li><i>2</i><span>Tap <b>Confirm</b> in the chat. The bot shows the device that asked.</span></li></ol>"
        f'<a class="btn" href="{esc(link)}">Open Telegram</a>'
        '<div class="wait"><span class="dot"></span><span id="st">Waiting for confirmation...</span></div></div>'
        '<p class="fine">If it was not you, tap Deny in Telegram.</p>'
        "</div></div>"
    )


def dashboard_html(*, name: str, flash: str, new_token: str | None, mcp_url: str, tokens: list[dict], oauth_apps: int,
                   series: list[tuple[str, int]], today: int, per_day: int, per_min: int, pending: int,
                   ntfy_on: bool, ntfy_topic: str, ntfy_server: str, forms: dict, is_admin: bool = False) -> str:
    """forms: pre-built, CSRF-protected form HTML snippets from web.py:
    logout, test, ntfy_toggle, revoke(id)->callable, create_token, delete."""
    total14 = sum(v for _, v in series)
    pct = min(100, round(100 * today / per_day)) if per_day else 0
    connected = bool(tokens) or oauth_apps > 0
    sent_any = total14 > 0

    def view(vid: str, title: str, lede: str, inner: str) -> str:
        return (f'<section class="view" id="v-{vid}" data-view="{vid}"><h1 class="title">{title}</h1>'
                f'<p class="lede">{lede}</p>{inner}</section>')

    def check(done: bool, text: str, href: str) -> str:
        return (f'<li class="{"done" if done else ""}"><span class="ck">&#10003;</span><span>{text}</span>'
                + ("" if done else f'<a href="{href}" data-go="{href[1:]}">Do it</a>') + "</li>")

    rows = "".join(
        f"<tr><td>{esc(t['label'] or 'token')}</td>"
        f"<td>{time.strftime('%Y-%m-%d', time.gmtime(t['created']))}</td>"
        f"<td>{time.strftime('%Y-%m-%d', time.gmtime(t['last_used'])) if t['last_used'] else 'never'}</td>"
        f"<td class='r'>{forms['revoke'](t['id'])}</td></tr>"
        for t in tokens
    ) or '<tr><td colspan="4" class="empty">No tokens yet. Create one for Codex, OpenCode or scripts.</td></tr>'

    overview = view("overview", "Overview", "How your notifier is doing.",
        '<div class="grid4">'
        f'<div class="card stat"><small>Sent today</small><b>{today}</b><span>of {per_day} a day</span><div class="bar"><i style="width:{pct}%"></i></div></div>'
        f'<div class="card stat"><small>Last 14 days</small><b>{total14}</b><span>messages delivered</span></div>'
        f'<div class="card stat"><small>Waiting replies</small><b class="{"hot" if pending else ""}">{pending}</b><span>messages you sent your AI</span></div>'
        f'<div class="card stat"><small>Connections</small><b>{len(tokens) + oauth_apps}</b><span>{len(tokens)} tokens, {oauth_apps} sign-in</span></div>'
        "</div>"
        '<div class="grid2">'
        f'<div class="card"><div class="chead"><h2>Messages per day</h2><span class="tag">14 days</span></div>{chart_svg(series)}</div>'
        '<div class="card"><h2>Setup checklist</h2><ul class="todo">'
        + check(True, "Telegram connected", "#channels")
        + check(connected, "Connect an AI tool", "#connect")
        + check(sent_any, "Send your first notification", "#settings")
        + check(ntfy_on, "Optional: turn on ntfy push", "#channels")
        + "</ul></div></div>")

    connect = view("connect", "Connect your AI", "Add this server to any tool that supports MCP.",
        f'<div class="card"><h2>Server URL</h2><div class="pre"><pre><code>{esc(mcp_url)}</code></pre><button class="ghost sm" data-copy="{esc(mcp_url)}">Copy</button></div>'
        "<p>claude.ai and ChatGPT: add a custom connector with this URL and sign in when asked.</p></div>"
        '<div class="row2" style="margin-top:14px">'
        f'<div class="card"><h2>Claude Code</h2><div class="pre"><pre><code>claude mcp add --transport http agent-notifier {esc(mcp_url)}</code></pre>'
        f'<button class="ghost sm" data-copy="claude mcp add --transport http agent-notifier {esc(mcp_url)}">Copy</button></div></div>'
        '<div class="card"><h2>Codex CLI (config.toml)</h2><div class="pre"><pre><code>'
        f'[mcp_servers.agent-notifier]\nurl = "{esc(mcp_url)}"\nbearer_token_env_var = "AGENT_NOTIFIER_TOKEN"</code></pre></div>'
        "<p>Create a token in <b>Tokens</b>, then set it as the <code>AGENT_NOTIFIER_TOKEN</code> environment variable.</p></div></div>")

    new_tok = ""
    if new_token:
        new_tok = ("<div class='flash'><b>Copy your token now. It is shown only once.</b>"
                   f"<code class='block'>{esc(new_token)}</code><button data-copy='{esc(new_token)}'>Copy token</button></div>")
    tokens_v = view("tokens", "Personal tokens", "Bearer tokens for tools that cannot sign in (Codex CLI, OpenCode, scripts).",
        new_tok + f'<div class="card"><table><thead><tr><th>Label</th><th>Created</th><th>Last used</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
        f'<div style="margin-top:14px">{forms["create_token"]}</div></div>')

    ntfy_box = (
        f"<p><b>ntfy enabled.</b> Install the ntfy app and subscribe to this topic on <span class='mono'>{esc(ntfy_server)}</span>:</p>"
        f"<code class='block'>{esc(ntfy_topic)}</code>{forms['ntfy_off']}"
        if ntfy_on else "<p>Optional push notifications through the ntfy app (send-only).</p>" + forms["ntfy_on"]
    )
    channels = view("channels", "Channels", "Where your notifications go.",
        '<div class="row2">'
        f'<div class="card chan"><div class="ic">{icon("send")}</div><div><h3>Telegram <span class="pill">Connected</span></h3>'
        "<p>Two-way. Reply in the chat to answer your AI.</p></div></div>"
        f'<div class="card chan"><div class="ic">{icon("bell")}</div><div><h3>ntfy <span class="pill {"" if ntfy_on else "off"}">{"On" if ntfy_on else "Off"}</span></h3>{ntfy_box}</div></div>'
        "</div>")

    settings = view("settings", "Settings", "Test your setup or remove your data.",
        f'<div class="card"><h2>Send a test notification</h2><p>Limits: {per_min} messages a minute, {per_day} a day.</p>{forms["test"]}</div>'
        '<div class="card danger-zone" style="margin-top:14px"><h2>Delete account</h2>'
        f'<p>Removes your account, tokens, connections and stored replies.</p>{forms["delete"]}</div>')

    nav_items = [("overview", "Overview", "home", ""), ("connect", "Connect", "plug", ""), ("tokens", "Tokens", "key", str(len(tokens)) if tokens else ""),
                 ("channels", "Channels", "bell", ""), ("settings", "Settings", "gear", "")]
    admin_link = ('<h6>ADMIN</h6><a href="/admin">' + icon("shield") + "<span>Admin console</span></a>") if is_admin else ""
    nav = "".join(
        f'<a href="#{i}" data-nav="{i}">{icon(ic)}<span>{lbl}</span>' + (f'<em class="badge">{b}</em>' if b else "") + "</a>"
        for i, lbl, ic, b in nav_items
    )
    pills = (
        '<span class="pill">Telegram connected</span>'
        f'<span class="pill {"" if ntfy_on else "off"}">ntfy {"on" if ntfy_on else "off"}</span>'
        f'<span class="pill {"warn" if pct >= 80 else ""}">{today}/{per_day} today</span>'
    )
    flash_html = f"<div class='flash'>{esc(flash)}</div>" if flash else ""
    return (
        '<div class="shell"><aside class="side">'
        f'<div class="brand"><i>{LOGO}</i><div><b>Agent Notifier</b><span>Your dashboard</span></div></div>'
        f'<nav class="nav" aria-label="Dashboard"><h6>MENU</h6>{nav}{admin_link}</nav>'
        f'<div class="me"><small>Signed in as</small><b>{esc(name)}</b>{forms["logout"]}</div></aside>'
        '<div class="main"><header class="top"><span class="crumb">Agent Notifier / <span id="crumb">Overview</span></span>'
        f'<span class="grow"></span>{pills}</header>'
        f'<div class="content">{flash_html}{overview}{connect}{tokens_v}{channels}{settings}</div></div></div>'
    )


DASH_JS = """
(function(){
var d=document,root=d.documentElement;root.classList.add('js');
var views=[].slice.call(d.querySelectorAll('[data-view]')),links=[].slice.call(d.querySelectorAll('[data-nav]'));
function show(id){if(!d.getElementById('v-'+id))id='overview';
views.forEach(function(v){v.classList.toggle('on',v.getAttribute('data-view')===id)});
links.forEach(function(a){a.classList.toggle('on',a.getAttribute('data-nav')===id)});
var a=d.querySelector('[data-nav="'+id+'"] span');d.getElementById('crumb').textContent=a?a.textContent:'Overview';}
function route(){show((location.hash||'#'+(window.__start||'overview')).slice(1))}
window.addEventListener('hashchange',route);route();
d.querySelectorAll('[data-copy]').forEach(function(b){b.addEventListener('click',function(){
navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function(){var t=b.textContent;b.textContent='Copied';setTimeout(function(){b.textContent=t},1200)})})});
})();
"""
