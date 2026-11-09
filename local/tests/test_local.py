import asyncio, json, os, sys, time
os.environ["AGENT_NOTIFIER_HOME"] = "/tmp/cn-home-test"
import httpx
from agent_notifier.config import Settings
from agent_notifier import core, hooks, state, inbox
from agent_notifier.server import mcp

calls = []

def fake_post(url, **kw):
    calls.append(("POST", url, kw.get("json")))
    if "telegram" in url and FAIL_TG:
        return httpx.Response(500, text="boom", request=httpx.Request("POST", url))
    return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

def fake_get(url, **kw):
    calls.append(("GET", url, kw.get("params")))
    if "getUpdates" in url:
        return httpx.Response(200, json={"result": [
            {"update_id": 5, "message": {"chat": {"id": 999}, "text": "intruder", "date": time.time()}},
            {"update_id": 6, "message": {"chat": {"id": 123}, "text": "go ahead", "date": time.time()}},
        ]}, request=httpx.Request("GET", url))
    return httpx.Response(200, text="", request=httpx.Request("GET", url))

httpx.post, httpx.get = fake_post, fake_get
time.sleep = lambda *_: None
FAIL_TG = False

S = Settings({"TG_TOKEN": "123456:SECRETTOKEN", "TG_CHAT_ID": "123", "NTFY_TOPIC": "topicxyz",
              "CALLMEBOT_PHONE": "+1", "CALLMEBOT_APIKEY": "apikey123", "NOTIFY_DEFAULT_CHANNELS": "telegram"})

# 1 normal -> default only
r = core.notify("hi", settings=S); assert r["sent"] == ["telegram"], r
# 2 high -> all configured
r = core.notify("hi", priority="urgent", settings=S); assert set(r["sent"]) == {"telegram", "ntfy", "whatsapp"}, r
# 3 telegram fails -> fallback, token never leaks
FAIL_TG = True
r = core.notify("hi", settings=S); assert r.get("fallback_used") and r["sent"], r
assert "SECRETTOKEN" not in json.dumps(r), r
# 4 explicit channel + unknown
FAIL_TG = False
r = core.notify("hi", channels=["ntfy", "gmail", "nope"], settings=S)
assert r["sent"] == ["ntfy"] and len(r["skipped"]) == 2, r
# 5 inbound filters other chats
state.save({}); msgs = inbox.poll_inbox(S)
assert [m["text"] for m in msgs] == ["go ahead"], msgs
assert state.load()["tg_offset"] == 7
# 6 hook: short run skipped, long run sent once, stop_hook_active ignored
state.save({}); calls.clear()
hooks.handle({"hook_event_name": "UserPromptSubmit", "session_id": "a"}, S)
hooks.handle({"hook_event_name": "Stop", "session_id": "a", "cwd": "/x/proj"}, S)
assert not calls, "short run must not notify"
d = state.RUNS_DIR / "a.json"; d.write_text(json.dumps({"start": time.time() - 200}))
hooks.handle({"hook_event_name": "Stop", "session_id": "a", "cwd": "/x/proj", "stop_hook_active": True}, S)
assert not calls
hooks.handle({"hook_event_name": "Stop", "session_id": "a", "cwd": "/x/proj"}, S)
body = calls[-1][2]["text"]; assert "proj" in body and "3m 20s" in body, body
n = len(calls)
hooks.handle({"hook_event_name": "Stop", "session_id": "a", "cwd": "/x/proj"}, S)
assert len(calls) == n, "debounce"
# 7 MCP server tools
async def mcp_check():
    tools = {t.name for t in await mcp.list_tools()}
    assert tools == {"notify_me", "ask_me", "check_inbox", "channel_status"}, tools
    out = await mcp.call_tool("channel_status", {})
    assert "SECRETTOKEN" not in str(out)
asyncio.run(mcp_check())
print("ALL_TESTS_PASSED")
