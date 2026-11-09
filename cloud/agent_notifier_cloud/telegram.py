"""Shared Telegram bot: delivery, account linking, browser sign-in confirmation, replies."""
from __future__ import annotations

import time

import httpx

from .config import Config
from .db import DB
from .security import RateLimiter


class DeliveryError(Exception):
    pass


async def api(cfg: Config, method: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"https://api.telegram.org/bot{cfg.tg_token}/{method}", json=payload)
    except httpx.HTTPError as exc:  # never include the URL (it contains the bot token)
        raise DeliveryError(f"telegram network error ({type(exc).__name__})") from None
    if resp.status_code == 403:
        raise DeliveryError("telegram: bot blocked or not started - open the bot and press Start")
    if resp.status_code >= 400:
        raise DeliveryError(f"telegram HTTP {resp.status_code}")
    return resp.json()


async def send(cfg: Config, chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await api(cfg, "sendMessage", payload)


async def set_webhook(cfg: Config) -> dict:
    return await api(
        cfg,
        "setWebhook",
        {
            "url": f"{cfg.public_url}/telegram/webhook/{cfg.tg_webhook_secret}",
            "secret_token": cfg.tg_webhook_secret,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        },
    )


def _ua_summary(ua: str) -> str:
    browser = next((n for n in ("Edg", "Firefox", "Chrome", "Safari") if n in ua), "Unknown browser")
    browser = {"Edg": "Edge"}.get(browser, browser)
    system = next((n for n in ("Windows", "Android", "iPhone", "iPad", "Mac OS", "Linux") if n in ua), "unknown OS")
    return f"{browser} on {system}"


WELCOME = (
    "Welcome to Agent Notifier.\n\n"
    "Your account is ready. Open {url}/login to get your connector URL and settings.\n\n"
    "Your AI tools will message you here when they finish work. "
    "Reply to a message here to answer a question your AI asked.\n\n"
    "/help - commands   /delete - remove my account and data"
)

HELP = (
    "Commands:\n/start - create or open your account\n/delete - delete your account and all data\n\n"
    "Any other text you send is delivered to your AI tool as a reply (it expires after 7 days)."
)


async def handle_update(cfg: Config, db: DB, limiter: RateLimiter, update: dict) -> None:
    if "callback_query" in update:
        await _callback(cfg, db, update["callback_query"])
        return
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    text = (msg.get("text") or "").strip()
    if chat.get("type") != "private" or not text:
        return
    chat_id = str(chat.get("id"))
    if not limiter.allow(f"tg:{chat_id}", 30, 60):
        return
    name = (msg.get("from") or {}).get("first_name") or chat.get("username") or ""
    cmd, _, arg = text.partition(" ")
    cmd, arg = cmd.split("@")[0].lower(), arg.strip()

    if cmd == "/start":
        user = db.get_or_create_user(chat_id, name)
        if user["suspended"]:
            await send(cfg, chat_id, "This account is suspended. Contact the service owner.")
            return
        session = db.session_for_code(arg) if arg.startswith("L") else None
        if arg.startswith("L") and not session:
            await send(cfg, chat_id, f"That sign-in link expired. Open {cfg.public_url}/login and try again.")
        elif session:
            when = time.strftime("%H:%M UTC", time.gmtime())
            await send(
                cfg,
                chat_id,
                "Sign-in request\n\nA browser wants to sign in to Agent Notifier as you.\n"
                f"IP: {session['ip'] or 'unknown'}\nDevice: {_ua_summary(session['ua'] or '')}\nTime: {when}\n\n"
                "Tap Confirm ONLY if you started this just now. If someone sent you this link, tap Deny.",
                {"inline_keyboard": [[
                    {"text": "Confirm", "callback_data": f"ok:{arg}"},
                    {"text": "Deny", "callback_data": f"no:{arg}"},
                ]]},
            )
        else:
            await send(cfg, chat_id, WELCOME.format(url=cfg.public_url))
        return

    user = db.active(db.user_by_chat(chat_id))
    if cmd == "/help":
        await send(cfg, chat_id, HELP)
    elif not user:
        await send(cfg, chat_id, f"Send /start first, or open {cfg.public_url}/login to create your account.")
    elif cmd == "/delete":
        if arg.lower() == "confirm":
            db.delete_user(user["id"])
            await send(cfg, chat_id, "Done. Your account, tokens and messages were deleted.")
        else:
            await send(cfg, chat_id, "This permanently deletes your account, tokens and stored replies.\nSend /delete confirm to proceed.")
    elif not cmd.startswith("/"):
        db.add_inbox(user["id"], text)


async def _callback(cfg: Config, db: DB, cq: dict) -> None:
    chat_id = str((cq.get("from") or {}).get("id", ""))
    data = cq.get("data") or ""
    action, _, code = data.partition(":")
    user = db.active(db.user_by_chat(chat_id))
    try:
        await api(cfg, "answerCallbackQuery", {"callback_query_id": cq.get("id", "")})
    except DeliveryError:
        pass
    if not user or action not in ("ok", "no") or not code.startswith("L"):
        return
    if action == "ok":
        done = db.bind_session(code, user["id"])
        reply = "Signed in. You can go back to your browser." if done else "That sign-in request expired. Start again on the website."
    else:
        db.kill_code(code)
        reply = "Sign-in denied. Nothing was changed."
    try:
        await send(cfg, chat_id, reply)
    except DeliveryError:
        pass
