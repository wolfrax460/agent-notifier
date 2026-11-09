import base64, hashlib, json, os, re, secrets, tempfile, threading, time
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient

from agent_notifier_cloud.config import load
from agent_notifier_cloud.app import create_app
from agent_notifier_cloud.db import DB
from agent_notifier_cloud import telegram as tg

tmp = tempfile.mkdtemp()
ENV = dict(PUBLIC_URL="https://notify.test", DB_PATH=f"{tmp}/t.db", TG_BOT_TOKEN="111:BOTSECRETTOKEN",
           TG_BOT_USERNAME="NotifyBot", TG_WEBHOOK_SECRET="whsecret_0123456789abcdef", SESSION_SECRET="s" * 48, ADMIN_TG_IDS="900, 901")
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
        hook({"callback_query": {"id": "c1", "from": {"id": chat_id}, "data": f"ok:{code}"}})
        ok(c.get("/login/status").json()["approved"] is True, f"{name} signed in")
        return dict(c.cookies)
    def use(cookies):
        c.cookies.clear()
        for k, v in cookies.items():
            c.cookies.set(k, v)
    def csrf_of(html):
        return re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)

    ok(cfg.admin_ids == ("900", "901"), "ADMIN_TG_IDS parsed")
    ana = login_user(111, "Ana"); use(ana)
    r = c.post("/app/token", data={"csrf": csrf_of(c.get("/app").text), "label": "ana-laptop"})
    ana_pat = re.search(r"(an_pat_[A-Za-z0-9_\-]+)", r.text).group(1)
    hook({"message": {"chat": {"id": 111, "type": "private"}, "text": "SECRET reply text from Ana"}})
    ok(c.post("/api/notify", json={"message": "hi"}, headers={"Authorization": f"Bearer {ana_pat}"}).status_code == 200, "Ana can notify")
    bob = login_user(222, "Bob")

    # ---- access control -------------------------------------------------------------------
    use(ana)
    ok(c.get("/admin").status_code == 404, "normal user gets 404 on /admin")
    ok(c.get("/admin/users").status_code == 404 and c.get("/admin/audit").status_code == 404, "normal user gets 404 on all admin pages")
    ok("Admin console" not in c.get("/app").text, "no admin link for normal users")
    c.cookies.clear()
    r = c.get("/admin", follow_redirects=False)
    ok(r.status_code == 303 and r.headers["location"].startswith("/login"), "anonymous is sent to sign in")

    root = login_user(900, "Root"); use(root)
    ok("Admin console" in c.get("/app").text, "admin sees the admin link")
    r = c.get("/admin"); ok(r.status_code == 200 and "Total users" in r.text and "Messages per day" in r.text, "overview renders")
    ok("SECRET reply text" not in r.text, "overview shows no message contents")
    r = c.get("/admin/users"); ok("Ana" in r.text and "Bob" in r.text and "Root" in r.text, "users list shows everyone")
    ok("an_pat_" not in r.text, "no token values in the list")
    ok("Ana" in c.get("/admin/users?q=ana").text and "Bob" not in c.get("/admin/users?q=ana").text, "search filters")
    ok("Bob" in c.get("/admin/users?q=222").text, "search by Telegram ID")
    ok(c.get("/admin/users?q=%25%27%3B--").status_code == 200, "search survives hostile input")
    ana_id = db.user_by_chat("111")["id"]; bob_id = db.user_by_chat("222")["id"]; root_id = db.user_by_chat("900")["id"]
    r = c.get(f"/admin/users/{ana_id}"); ok("ana-laptop" in r.text and "SECRET reply text" not in r.text and ana_pat not in r.text, "detail shows token labels, never values or message text")

    # ---- CSRF and self-protection -----------------------------------------------------------
    ok(c.post(f"/admin/users/{ana_id}/suspend", data={"value": "1"}).status_code == 403, "suspend without CSRF is blocked")
    ok(db.user_by_id(ana_id)["suspended"] == 0, "nothing changed without CSRF")
    tok = csrf_of(c.get(f"/admin/users/{ana_id}").text)
    r = c.post(f"/admin/users/{root_id}/suspend", data={"csrf": csrf_of(c.get(f"/admin/users/{root_id}").text), "value": "1"})
    ok(r.status_code == 403 and db.user_by_id(root_id)["suspended"] == 0, "admins cannot suspend admins")
    r = c.post(f"/admin/users/{root_id}/delete", data={"csrf": csrf_of(c.get(f"/admin/users/{root_id}").text), "confirm": "DELETE"})
    ok(db.user_by_id(root_id) is not None, "admins cannot delete admins")

    # ---- suspend / unsuspend ----------------------------------------------------------------
    r = c.post(f"/admin/users/{ana_id}/suspend", data={"csrf": tok, "value": "1"}); ok("suspended" in r.text.lower(), "suspend succeeds")
    ok(c.post("/api/notify", json={"message": "hi"}, headers={"Authorization": f"Bearer {ana_pat}"}).status_code == 401, "suspended user's token is rejected")
    use(ana); ok(c.get("/app", follow_redirects=False).status_code == 303, "suspended user's session is dead")
    calls.clear()
    hook({"message": {"chat": {"id": 111, "type": "private"}, "text": "/start"}})
    ok("suspended" in json.dumps(calls[-1][1]).lower(), "suspended user told why on /start")
    use(root)
    r = c.post(f"/admin/users/{ana_id}/suspend", data={"csrf": csrf_of(c.get(f"/admin/users/{ana_id}").text), "value": "0"}); ok("unsuspended" in r.text.lower(), "unsuspend succeeds")
    ok(c.post("/api/notify", json={"message": "hi"}, headers={"Authorization": f"Bearer {ana_pat}"}).status_code == 200, "token works again after unsuspend")

    # ---- revoke everything, message ----------------------------------------------------------
    r = c.post(f"/admin/users/{ana_id}/revoke", data={"csrf": csrf_of(c.get(f"/admin/users/{ana_id}").text)}); ok("revoked" in r.text.lower(), "revoke all")
    ok(c.post("/api/notify", json={"message": "hi"}, headers={"Authorization": f"Bearer {ana_pat}"}).status_code == 401, "token dead after revoke-all")
    use(root); calls.clear()
    r = c.post(f"/admin/users/{ana_id}/message", data={"csrf": csrf_of(c.get(f"/admin/users/{ana_id}").text), "text": "Hello from admin"})
    ok(calls and calls[-1][1]["chat_id"] == "111" and "Hello from admin" in calls[-1][1]["text"], "admin message reaches the user on Telegram")

    # ---- broadcast ----------------------------------------------------------------------------
    db.set_suspended(bob_id, True)
    calls.clear()
    f = csrf_of(c.get("/admin/broadcast").text)
    r = c.post("/admin/broadcast", data={"csrf": f, "text": "Maintenance tonight", "confirm": "no"}); ok(r.status_code == 400 and not calls, "broadcast needs SEND confirmation")
    r = c.post("/admin/broadcast", data={"csrf": f, "text": "Maintenance tonight", "confirm": "SEND"})
    sent_to = sorted(p["chat_id"] for m, p in calls if m == "sendMessage")
    ok(sent_to == ["111", "900"], f"broadcast reaches active users only ({sent_to})")
    db.set_suspended(bob_id, False)

    # ---- delete ---------------------------------------------------------------------------------
    r = c.post(f"/admin/users/{bob_id}/delete", data={"csrf": csrf_of(c.get(f"/admin/users/{bob_id}").text), "confirm": "nope"}); ok(db.user_by_id(bob_id) is not None, "delete needs DELETE")
    r = c.post(f"/admin/users/{bob_id}/delete", data={"csrf": csrf_of(c.get(f"/admin/users/{bob_id}").text), "confirm": "DELETE"})
    ok(db.user_by_id(bob_id) is None, "admin deletes a user")
    ok(c.get("/admin/users/u_doesnotexist").status_code == 404, "unknown user is 404")

    # ---- audit log -------------------------------------------------------------------------------
    r = c.get("/admin/audit"); txt = r.text
    ok(all(w in txt for w in ("suspend", "unsuspend", "revoke_all", "message", "broadcast", "delete_user")), "audit log recorded every action")
    ok("Hello from admin" not in txt and "Maintenance tonight" not in txt, "audit log stores sizes, not content")
    ok("BOTSECRETTOKEN" not in json.dumps([m for m, _ in calls]), "no secrets in recorded calls")
print("ADMIN_ALL_PASSED")
