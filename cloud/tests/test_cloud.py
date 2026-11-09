import base64, hashlib, json, os, re, secrets, tempfile, threading, time
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient

from agent_notifier_cloud.config import load
from agent_notifier_cloud.app import create_app
from agent_notifier_cloud.db import DB
from agent_notifier_cloud import telegram as tg

tmp = tempfile.mkdtemp()
ENV = dict(PUBLIC_URL="https://notify.test", DB_PATH=f"{tmp}/t.db", TG_BOT_TOKEN="111:BOTSECRETTOKEN",
           TG_BOT_USERNAME="NotifyBot", TG_WEBHOOK_SECRET="whsecret_0123456789abcdef", SESSION_SECRET="s" * 48)
cfg = load(ENV)
calls = []

async def fake_api(cfg_, method, payload):
    calls.append((method, payload))
    return {"ok": True}

tg.api = fake_api
from agent_notifier_cloud import notify as nt

async def fake_ntfy(cfg_, topic, title, message, priority):
    calls.append(("ntfy", {"topic": topic}))

nt._ntfy = fake_ntfy
app = create_app(cfg)
db = DB(cfg.db_path)
WH = f"/telegram/webhook/{cfg.tg_webhook_secret}"
HDR = {"x-telegram-bot-api-secret-token": cfg.tg_webhook_secret}
MCPH = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)

with TestClient(app, base_url="https://notify.test") as c:
    def hook(update, headers=HDR, path=WH):
        return c.post(path, json=update, headers=headers)

    def login_user(chat_id, name):
        c.cookies.clear()
        r = c.get("/login")
        code = re.search(r"start=(L[0-9a-f]+)", r.text).group(1)
        hook({"message": {"chat": {"id": chat_id, "type": "private"}, "from": {"first_name": name}, "text": f"/start {code}"}})
        ok(any(m == "sendMessage" and "inline_keyboard" in json.dumps(p) for m, p in calls[-3:]), f"confirm prompt sent to {name}")
        ok(c.get("/login/status").json()["approved"] is False, "not approved before Confirm")
        hook({"callback_query": {"id": "c1", "from": {"id": chat_id}, "data": f"ok:{code}"}})
        ok(c.get("/login/status").json()["approved"] is True, f"{name} approved after Confirm")
        return dict(c.cookies)

    def use(cookies):
        c.cookies.clear()
        for k, v in cookies.items():
            c.cookies.set(k, v)

    def csrf_of(html):
        return re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)

    def rpc(token, method, params=None, id_=1):
        body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if id_:
            body["id"] = id_
        r = c.post("/mcp", json=body, headers={**MCPH, "Authorization": f"Bearer {token}"})
        data = None
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
        elif r.text:
            try:
                data = r.json()
            except ValueError:
                pass
        return r.status_code, data

    def tool(token, name, args=None):
        rpc(token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}, 1)
        st, d = rpc(token, "tools/call", {"name": name, "arguments": args or {}}, 2)
        ok(st == 200 and d and "result" in d, f"tools/call {name} -> {st}")
        res = d["result"]
        return res.get("structuredContent") or json.loads(res["content"][0]["text"])

    # ---- basics -----------------------------------------------------------
    ok(c.get("/health").json() == {"ok": True}, "health")
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=MCPH)
    ok(r.status_code == 401 and "resource_metadata" in r.headers.get("www-authenticate", ""), "unauthenticated /mcp -> 401 with resource_metadata")
    meta = c.get("/.well-known/oauth-authorization-server").json()
    ok(meta["issuer"].rstrip("/") == "https://notify.test" and "registration_endpoint" in meta, "OAuth server metadata")
    pr = c.get("/.well-known/oauth-protected-resource/mcp").json()
    ok(pr["resource"].rstrip("/") == "https://notify.test/mcp", "protected resource metadata")
    ok(hook({}, headers={}).status_code == 403, "webhook without secret -> 403")
    ok(hook({}, headers=HDR, path="/telegram/webhook/wrongwrongwrongwrong").status_code == 403, "webhook wrong path secret -> 403")

    # ---- login + dashboard ----------------------------------------------------
    ana = login_user(111, "Ana")
    use(ana)
    r = c.get("/app")
    ok(r.status_code == 200 and "https://notify.test/mcp" in r.text, "dashboard shows MCP URL")
    ok("BOTSECRETTOKEN" not in r.text, "dashboard never contains bot token")
    csrf = csrf_of(r.text)
    ok(c.post("/app/token", data={"label": "x"}).status_code == 403, "POST without csrf blocked")
    r = c.post("/app/token", data={"csrf": csrf, "label": "laptop"})
    ana_pat = re.search(r"(an_pat_[A-Za-z0-9_\-]+)", r.text).group(1)
    ok(True, "personal token created")

    # ---- MCP with personal token ------------------------------------------------
    st, d = rpc(ana_pat, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    ok(st == 200 and d["result"]["serverInfo"]["name"] == "agent-notifier", "initialize over HTTP")
    st, d = rpc(ana_pat, "tools/list", {}, 3)
    ok({t["name"] for t in d["result"]["tools"]} == {"notify_me", "ask_me", "check_inbox", "channel_status"}, "tools listed")
    calls.clear()
    res = tool(ana_pat, "notify_me", {"message": "build done", "title": "Claude finished"})
    ok(res["sent"] == ["telegram"] and calls[-1][1]["chat_id"] == "111" and "build done" in calls[-1][1]["text"], "notify_me -> Ana's Telegram chat")

    hook({"message": {"chat": {"id": 111, "type": "private"}, "from": {"first_name": "Ana"}, "text": "hello claude"}})
    ok(tool(ana_pat, "check_inbox")["messages"] == ["hello claude"], "check_inbox returns Ana's reply")
    ok(tool(ana_pat, "check_inbox")["count"] == 0, "inbox consumed")

    threading.Timer(1.6, lambda: db.add_inbox(db.user_by_chat("111")["id"], "yes, ship it")).start()
    t0 = time.time()
    res = tool(ana_pat, "ask_me", {"question": "Deploy?", "timeout_seconds": 20})
    ok(res.get("answered") and res["reply"] == "yes, ship it" and time.time() - t0 < 10, "ask_me waits and returns the reply")

    # ---- isolation -----------------------------------------------------------------
    bob = login_user(222, "Bob")
    use(bob)
    r = c.get("/app")
    r = c.post("/app/token", data={"csrf": csrf_of(r.text), "label": "bob"})
    bob_pat = re.search(r"(an_pat_[A-Za-z0-9_\-]+)", r.text).group(1)
    hook({"message": {"chat": {"id": 111, "type": "private"}, "from": {"first_name": "Ana"}, "text": "private to Ana"}})
    ok(tool(bob_pat, "check_inbox")["count"] == 0, "Bob cannot read Ana's replies")
    calls.clear()
    tool(bob_pat, "notify_me", {"message": "for bob"})
    ok(all(p["chat_id"] == "222" for m, p in calls if m == "sendMessage"), "Bob's notification only goes to Bob")
    ok(tool(ana_pat, "check_inbox")["messages"] == ["private to Ana"], "Ana still has her own message")

    # ---- ntfy toggle + REST API ----------------------------------------------------------
    use(ana)
    r = c.get("/app")
    r = c.post("/app/ntfy", data={"csrf": csrf_of(r.text), "enable": "1"})
    ok("cn-" in r.text and "ntfy enabled" in r.text, "ntfy enabled, topic shown")
    r = c.post("/api/notify", json={"message": "from curl", "priority": "low"}, headers={"Authorization": f"Bearer {ana_pat}"})
    ok(r.status_code == 200 and r.json()["sent"] == ["telegram"], "REST /api/notify (low -> telegram only)")
    r = c.post("/api/notify", json={"message": "urgent", "priority": "urgent"}, headers={"Authorization": f"Bearer {ana_pat}"})
    ok(set(r.json()["sent"]) == {"telegram", "ntfy"}, "urgent -> all enabled channels")
    ok(c.post("/api/notify", json={"message": "x"}, headers={"Authorization": "Bearer an_pat_bogus"}).status_code == 401, "REST bad token -> 401")

    # ---- OAuth (what claude.ai / ChatGPT do) -----------------------------------------------
    c.cookies.clear()
    r = c.post("/register", json={"client_name": "Test App", "redirect_uris": ["https://app.test/cb"], "grant_types": ["authorization_code", "refresh_token"],
                                  "response_types": ["code"], "token_endpoint_auth_method": "none"})
    ok(r.status_code in (200, 201), f"dynamic client registration ({r.status_code})")
    client_id = r.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = dict(response_type="code", client_id=client_id, redirect_uri="https://app.test/cb", code_challenge=challenge,
             code_challenge_method="S256", state="xyz", scope="notify")
    r = c.get("/authorize", params=q, follow_redirects=False)
    ok(r.status_code in (302, 303) and "/oauth/consent?req=" in r.headers["location"], "authorize -> consent page")
    consent = urlparse(r.headers["location"])
    consent_path = consent.path + "?" + consent.query
    r = c.get(consent_path, follow_redirects=False)
    ok(r.status_code == 303 and r.headers["location"].startswith("/login?next="), "consent without session -> login")
    use(ana)
    r = c.get(consent_path)
    ok(r.status_code == 200 and "Test App" in r.text and "app.test" in r.text, "consent page names the app and redirect host")
    req_id = parse_qs(consent.query)["req"][0]
    ok(c.post("/oauth/consent", data={"req": req_id, "action": "allow"}, follow_redirects=False).status_code == 403, "consent POST needs csrf")
    r = c.post("/oauth/consent", data={"csrf": csrf_of(c.get(consent_path).text), "req": req_id, "action": "allow"}, follow_redirects=False)
    loc = urlparse(r.headers["location"])
    qs = parse_qs(loc.query)
    ok(loc.netloc == "app.test" and qs["state"] == ["xyz"] and "code" in qs, "consent allow -> redirect with code+state")
    code = qs["code"][0]
    c.cookies.clear()
    bad = c.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://app.test/cb", "client_id": client_id, "code_verifier": "wrong" * 12})
    ok(bad.status_code == 400, "wrong PKCE verifier rejected")
    r = c.get("/authorize", params=q, follow_redirects=False)  # fresh flow since failed exchange may burn the code
    consent = urlparse(r.headers["location"]); consent_path = consent.path + "?" + consent.query
    use(ana)
    r = c.post("/oauth/consent", data={"csrf": csrf_of(c.get(consent_path).text), "req": parse_qs(consent.query)["req"][0], "action": "allow"}, follow_redirects=False)
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    c.cookies.clear()
    tok = c.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://app.test/cb", "client_id": client_id, "code_verifier": verifier})
    ok(tok.status_code == 200 and tok.json().get("refresh_token"), "token exchange with PKCE")
    access, refresh = tok.json()["access_token"], tok.json()["refresh_token"]
    again = c.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://app.test/cb", "client_id": client_id, "code_verifier": verifier})
    ok(again.status_code == 400, "authorization code is single-use")
    calls.clear()
    res = tool(access, "notify_me", {"message": "via oauth"})
    ok(res["sent"] == ["telegram"] and calls[-1][1]["chat_id"] == "111", "OAuth token resolves to the right user")
    new = c.post("/token", data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id})
    ok(new.status_code == 200, "refresh token exchange")
    ok(rpc(access, "tools/list", {}, 9)[0] == 401, "old access token dead after rotation")
    ok(c.post("/token", data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id}).status_code == 400, "old refresh token cannot be reused")
    access2 = new.json()["access_token"]
    ok(rpc(access2, "tools/list", {}, 9)[0] == 200, "rotated access token works")
    rv = c.post("/revoke", data={"token": access2, "client_id": client_id, "client_secret": ""}); ok(rv.status_code == 200, f"revoke endpoint ({rv.status_code})")
    ok(rpc(access2, "tools/list", {}, 9)[0] == 401, "revoked token rejected")

    # ---- rate limit + deletion ----------------------------------------------------------------
    cam = login_user(333, "Cam"); use(cam)
    r = c.post("/app/token", data={"csrf": csrf_of(c.get("/app").text), "label": "c"})
    cam_pat = re.search(r"(an_pat_[A-Za-z0-9_\-]+)", r.text).group(1)
    codes = [c.post("/api/notify", json={"message": f"m{i}"}, headers={"Authorization": f"Bearer {cam_pat}"}).status_code for i in range(12)]
    ok(codes[:10] == [200] * 10 and codes[10] == 429, f"rate limit kicks in after 10/min ({codes[9]},{codes[10]})")
    r = c.post("/app/delete", data={"csrf": csrf_of(c.get("/app").text), "confirm": "DELETE"})
    ok(c.post("/api/notify", json={"message": "x"}, headers={"Authorization": f"Bearer {cam_pat}"}).status_code == 401, "deleted account's token stops working")
    ok(db.user_by_chat("333") is None, "user row removed")
    ok("BOTSECRETTOKEN" not in json.dumps([m for m, _ in calls]), "no secrets in recorded calls")

print("CLOUD_ALL_PASSED")
