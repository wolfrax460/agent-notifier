# agent-notifier

Get pinged on **Telegram, ntfy, Gmail or WhatsApp** when Claude finishes work, and reply from your phone.

Two parts, use both:

| Part | What it does | Who decides |
|---|---|---|
| **Claude Code hooks** | Auto-ping when a run ends (`Stop`) or Claude needs you (`Notification`) | Automatic, no tokens used |
| **MCP server** | Tools `notify_me`, `ask_me`, `check_inbox`, `channel_status` | Claude picks message, priority, channel |

## Install

```bash
cd agent-notifier
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
agent-notifier init            # creates ~/.agent-notifier/.env  (chmod 600)
```

## Channels (all free)

**Telegram** (two-way, recommended)
1. @BotFather -> `/newbot` -> copy token into `TG_TOKEN`
2. Send any message to your new bot
3. `agent-notifier telegram-id` -> put the printed id in `TG_CHAT_ID`

**ntfy** (push, no account)
1. Install the ntfy app, subscribe to a long random topic, e.g. `wolfrax-9f3k2x8q7z`
2. Set `NTFY_TOPIC` to it. Treat the topic name like a password.
3. For replies: subscribe to a second topic and set `NTFY_INBOX_TOPIC`; publish to it from the app to message Claude.

**Gmail** (send-only)
Turn on 2FA, create an App Password at myaccount.google.com/apppasswords, set `GMAIL_USER`, `GMAIL_APP_PASSWORD`.

**WhatsApp** (send-only, via CallMeBot, personal use)
Follow the activation steps at callmebot.com, set `CALLMEBOT_PHONE`, `CALLMEBOT_APIKEY`. Free *receiving* on WhatsApp has no clean official route; use Telegram or ntfy for replies.

Check: `agent-notifier status` then `agent-notifier test`.

## Wire into Claude Code

```bash
agent-notifier install-hooks              # ~/.claude/settings.json (use --scope project for one repo)
claude mcp add agent-notifier -- "$(which python)" -m agent_notifier.server
```

Restart Claude Code. Now every run longer than `NOTIFY_MIN_SECONDS` pings you when it ends.

## Routing

- `low` / `normal` -> `NOTIFY_DEFAULT_CHANNELS`; if they all fail, falls back to any other configured channel
- `high` / `urgent` -> every configured channel
- explicit `channels=[...]` -> exactly those

## CLI

```
agent-notifier send "build done" --priority high --channel telegram
agent-notifier inbox --wait 10        # read what you sent from your phone
agent-notifier hook                   # what the hooks call (stdin JSON)
```

## Safety notes

- Only messages from **your** `TG_CHAT_ID` are accepted as replies; they become instructions to Claude.
- Tokens are redacted from every error and log. Keep `.env` out of git.
- Hooks never block or fail Claude: any error is swallowed and logged to `~/.agent-notifier/notify.log`.
- `ask_me` consumes queued replies; older ones come back as `earlier_messages` so none are lost.
- Do not let Claude send secrets through the tools; the MCP instructions tell it not to.
