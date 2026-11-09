# agent-notifier-cloud

Hosted, multi-user version of agent-notifier. A remote **MCP server** (streamable HTTP) that lets any MCP-capable AI tool message a user on Telegram (and optionally ntfy) when work finishes, and receive replies.

- **Accounts**: sign in with Telegram (no passwords). The browser shows a deep link, the bot asks the user to Confirm, with IP and device shown.
- **Auth for AI tools**: OAuth 2.1 with dynamic client registration + PKCE (claude.ai, ChatGPT and other web connectors) and personal tokens `an_pat_...` (Claude Code, Codex, OpenCode, scripts).
- **Tools**: `notify_me`, `ask_me`, `check_inbox`, `channel_status`. The user is always taken from the verified token.
- **REST**: `POST /api/notify` with a personal token, for hooks and any tool without MCP.
- **Footprint**: one Python process, SQLite, ~100 MB RAM.

```
AI tool --HTTPS/MCP--> nginx:443 --> 127.0.0.1:8787 (agent_notifier_cloud) --> Telegram Bot API / ntfy
                                          |
                                    SQLite (users, hashed tokens, replies)
```

## Security design

- Tokens, sessions and OAuth codes are stored hashed (SHA-256); personal tokens are shown once.
- CSRF tokens on every dashboard and consent POST; strict CSP; cookies HttpOnly + Secure + SameSite=Lax; open-redirect protection on `next`.
- Telegram webhook is verified by header secret and path secret. Only private chats are processed.
- Per-user rate limits (minute and day), per-IP login throttling, request body caps, control-character stripping.
- Message text is never logged. Bot token never appears in errors (network errors are reduced to their type).
- Gmail/WhatsApp are intentionally NOT in the hosted version: storing other people's mail passwords is the biggest risk for a public service.

## Develop and test

```bash
pip install -e .
python tests/test_cloud.py; python tests/test_admin.py        # end-to-end checks, Telegram mocked
```

Deploy: see [docs/SELF_HOSTING.md](../docs/SELF_HOSTING.md).
