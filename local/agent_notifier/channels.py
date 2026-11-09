"""Channels: Telegram, ntfy, Gmail (SMTP), WhatsApp (CallMeBot).

Inbound (user -> Claude) is supported for Telegram and ntfy only.
"""
from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage

import httpx

from .config import Settings

TIMEOUT = 15.0
NTFY_PRIORITY = {"low": 2, "normal": 3, "high": 4, "urgent": 5}
NTFY_TAGS = {"low": "robot", "normal": "robot", "high": "warning", "urgent": "rotating_light"}


class ChannelError(Exception):
    pass


def _check(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise ChannelError(f"HTTP {resp.status_code}: {resp.text[:200]}")


class Channel:
    name = ""
    inbound = False
    needs = ""  # human hint for status output

    def __init__(self, settings: Settings):
        self.s = settings

    def configured(self) -> bool:
        raise NotImplementedError

    def send(self, title: str, message: str, priority: str = "normal") -> None:
        raise NotImplementedError


class Telegram(Channel):
    name = "telegram"
    inbound = True
    needs = "TG_TOKEN, TG_CHAT_ID"

    def configured(self) -> bool:
        return bool(self.s.get("TG_TOKEN") and self.s.get("TG_CHAT_ID"))

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.s.get('TG_TOKEN')}/{method}"

    def send(self, title: str, message: str, priority: str = "normal") -> None:
        text = f"{title}\n\n{message}" if title else message
        resp = httpx.post(
            self._url("sendMessage"),
            json={
                "chat_id": self.s.get("TG_CHAT_ID"),
                "text": text[:4000],
                "disable_notification": priority == "low",
            },
            timeout=TIMEOUT,
        )
        _check(resp)

    def poll(self, offset: int | None, wait: int = 0) -> tuple[list[dict], int | None]:
        params: dict = {"timeout": wait, "allowed_updates": '["message"]'}
        if offset:
            params["offset"] = offset
        resp = httpx.get(self._url("getUpdates"), params=params, timeout=wait + TIMEOUT)
        _check(resp)
        chat_id = self.s.get("TG_CHAT_ID")
        msgs: list[dict] = []
        nxt = offset
        for upd in resp.json().get("result", []):
            nxt = max(nxt or 0, upd["update_id"] + 1)
            msg = upd.get("message") or {}
            # Security: only accept messages from YOUR chat. Replies become instructions.
            if str(msg.get("chat", {}).get("id")) != chat_id:
                continue
            if msg.get("text"):
                msgs.append({"channel": "telegram", "text": msg["text"], "ts": msg.get("date", 0)})
        return msgs, nxt


def discover_telegram_chats(token: str) -> list[tuple[str, str]]:
    resp = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=TIMEOUT)
    _check(resp)
    seen: dict[str, str] = {}
    for upd in resp.json().get("result", []):
        chat = (upd.get("message") or {}).get("chat") or {}
        if "id" in chat:
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
            seen[str(chat["id"])] = name
    return list(seen.items())


class Ntfy(Channel):
    name = "ntfy"
    inbound = True
    needs = "NTFY_TOPIC"

    def configured(self) -> bool:
        return bool(self.s.get("NTFY_TOPIC"))

    def _server(self) -> str:
        return self.s.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self.s.get("NTFY_TOKEN")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def send(self, title: str, message: str, priority: str = "normal") -> None:
        resp = httpx.post(
            self._server(),
            json={
                "topic": self.s.get("NTFY_TOPIC"),
                "title": title,
                "message": message[:3900],
                "priority": NTFY_PRIORITY.get(priority, 3),
                "tags": [NTFY_TAGS.get(priority, "robot")],
            },
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        _check(resp)

    def poll(self, since: str | None) -> tuple[list[dict], str | None]:
        inbox = self.s.get("NTFY_INBOX_TOPIC")
        if not inbox:
            return [], since
        # First run: start from "now" so old backlog is not replayed.
        cursor = since or str(int(time.time()))
        resp = httpx.get(
            f"{self._server()}/{inbox}/json",
            params={"poll": "1", "since": cursor},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        _check(resp)
        import json

        msgs: list[dict] = []
        last = since
        for line in resp.text.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") != "message":
                continue
            last = ev.get("id", last)
            msgs.append({"channel": "ntfy", "text": ev.get("message", ""), "ts": ev.get("time", 0)})
        return msgs, last or cursor


class Gmail(Channel):
    name = "gmail"
    needs = "GMAIL_USER, GMAIL_APP_PASSWORD"

    def configured(self) -> bool:
        return bool(self.s.get("GMAIL_USER") and self.s.get("GMAIL_APP_PASSWORD"))

    def send(self, title: str, message: str, priority: str = "normal") -> None:
        user = self.s.get("GMAIL_USER")
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = self.s.get("GMAIL_TO") or user
        prefix = {"high": "[!] ", "urgent": "[!!] "}.get(priority, "")
        msg["Subject"] = f"{prefix}[Claude] {title}"[:200]
        if priority in ("high", "urgent"):
            msg["X-Priority"] = "1"
        msg.set_content(message)
        password = self.s.get("GMAIL_APP_PASSWORD").replace(" ", "")
        try:
            with smtplib.SMTP_SSL(
                "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=TIMEOUT
            ) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        except smtplib.SMTPException as exc:
            raise ChannelError(f"SMTP error: {exc.__class__.__name__}") from None


class WhatsApp(Channel):
    name = "whatsapp"
    needs = "CALLMEBOT_PHONE, CALLMEBOT_APIKEY"

    def configured(self) -> bool:
        return bool(self.s.get("CALLMEBOT_PHONE") and self.s.get("CALLMEBOT_APIKEY"))

    def send(self, title: str, message: str, priority: str = "normal") -> None:
        text = f"{title}\n{message}" if title else message
        resp = httpx.get(
            "https://api.callmebot.com/whatsapp.php",
            params={
                "phone": self.s.get("CALLMEBOT_PHONE"),
                "text": text[:1000],
                "apikey": self.s.get("CALLMEBOT_APIKEY"),
            },
            timeout=TIMEOUT,
        )
        _check(resp)


ALL_CHANNELS = (Telegram, Ntfy, Gmail, WhatsApp)


def build(settings: Settings) -> dict[str, Channel]:
    return {cls.name: cls(settings) for cls in ALL_CHANNELS}
