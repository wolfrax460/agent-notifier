# Agent Notifier

Get a message when your AI agent finishes, or answer its questions from your phone.

```
agent_notifier/
  local/   run on your computer: CLI, MCP server (stdio), Claude Code and Codex hooks, run wrapper
  cloud/   hosted multi-user service: remote MCP (OAuth + tokens), Telegram sign-in, dashboard, deploy files
    landing/   static website for Vercel
  docs/
    LOCAL_GUIDE.md     how to install and connect the local tool to your agents and models
    DEPLOY_PROMPT.md   paste into your most capable agent to deploy cloud + landing page for you
```

Start here:
1. Local tool: `docs/LOCAL_GUIDE.md`
2. Hosted service and website: give `docs/DEPLOY_PROMPT.md` to your agent (do the 5 pre-steps at the top of that file first)

Tests: `python local/tests/test_local.py`, `python local/tests/test_run.py`, `python local/tests/test_bridge.py`, `python cloud/tests/test_cloud.py`.

New: Telegram wake-up bridge (`agent-notifier listen`) — see docs/LOCAL_GUIDE.md section 10.
