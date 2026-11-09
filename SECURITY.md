# Security policy

## Reporting a vulnerability
Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting
(Security tab, "Report a vulnerability") on this repository, or email the address listed on the project website.
You will get a reply within a few days.

## What is in scope
- The hosted service code in `cloud/` (sign-in, OAuth, tokens, admin console, REST API).
- The local tool in `local/` (CLI, hooks, MCP server).

## Design notes
- Tokens, sessions and OAuth codes are stored hashed. Personal tokens are shown once.
- Message text is never logged. The admin console shows account metadata and usage counts only.
- Never commit `.env` files, bot tokens or personal access tokens. If one leaks, revoke it (Telegram: BotFather `/revoke`; Agent Notifier: dashboard, Tokens, Revoke).
