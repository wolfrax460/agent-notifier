# Agent Notifier

## Agent Notifiers 0.2.0 — public companion release

[Download the verified GitHub release](https://github.com/wolfrax460/agent-notifier/releases/tag/agent-notifiers-v0.2.0) (Python wheel, source archive, npm launcher, and SHA256SUMS).

**Python / pip (Windows, macOS, Linux):**

```sh
python -m pip install "https://github.com/wolfrax460/agent-notifier/releases/download/agent-notifiers-v0.2.0/agent_notifiers-0.2.0-py3-none-any.whl"
agent-notifiers --help
agent-notifiers device pair
```

**uv or pipx** can install the same verified Python wheel URL. The Python distribution also provides the legacy `agent-notifier` command.

**npm-compatible launcher:**

```sh
npm install -g "https://github.com/wolfrax460/agent-notifier/releases/download/agent-notifiers-v0.2.0/agent-notifiers-0.2.0.tgz"
agent-notifiers --help
```

The npm launcher requires the separate Python companion installation; it does not bundle or download Python. If the command is not recognized, use `python -m agent_notifier` (or `py -m agent_notifier` on Windows) with the Python environment that installed the package. Approve your computer's pairing code in the phone app, then run one companion instance. Your computer must remain on and connected for remote agent runs.

**Registry status:** These are publicly downloadable **GitHub Release artifacts**, not listings on PyPI, npmjs.com, or WinGet. Those registries are not yet published under this project. Do not install similarly named third-party packages. The Oracle cloud backend remains in the private repository.

---


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
