# Agent Notifier: local guide

Get a message on Telegram, ntfy or Gmail when an AI agent finishes, and answer its questions from your phone. This guide covers the **local** tool (`agent_notifier/local`), which runs on your own computer and connects to your coding agents and models.

## 1. How the pieces fit

```
your agent (Claude Code / Codex / OpenCode / Claude Desktop / any CLI)
   |-- hook or wrapper -> agent-notifier  --\
   |-- MCP tools (notify_me, ask_me ...)  ---+--> Telegram / ntfy / Gmail / WhatsApp
                                             \--> your phone
```

Three ways to trigger a message. Use whichever your tool supports, and combine them:

| Way | Who decides | Works with | Reliability |
|---|---|---|---|
| **Hook** | Automatic, every time a run ends | Claude Code (`Stop`), Codex (`notify`) | Very high, costs no tokens |
| **MCP server** | The model chooses message, priority, can ask you questions | Anything that supports MCP | Good, depends on the model remembering |
| **`run` wrapper** | Automatic when the command exits | Literally any command | Very high |

The model you use does not matter. Your **tool** (the harness) talks to Agent Notifier, so Claude, GPT, DeepSeek, Gemini or a local model all work as long as the tool supports hooks, MCP, or can be wrapped. For MCP, the model must support tool calling.

## 2. Install

You need Python 3.10 or newer.

**Windows (PowerShell)**
```powershell
cd agent_notifier\local
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
agent-notifier init
```

**macOS, Linux, WSL**
```bash
cd agent_notifier/local
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
agent-notifier init
```

`init` creates `~/.agent-notifier/.env` (on Windows: `C:\Users\YOU\.agent-notifier\.env`). Everything is configured there.

**Write down your Python path.** Desktop apps and agents do not activate your virtual environment, so you will give them the full path to the interpreter:
- Windows: `C:\Users\YOU\...\agent_notifier\local\.venv\Scripts\python.exe`
- macOS/Linux: `/home/YOU/.../agent_notifier/local/.venv/bin/python`

Get it any time with `python -c "import sys; print(sys.executable)"` while the venv is active. Below it is written as `PYTHON`.

## 3. Set up channels

Edit `~/.agent-notifier/.env`. Then run `agent-notifier status` and `agent-notifier test`.

### Telegram (recommended, two-way)
1. In Telegram open @BotFather, send `/newbot`, copy the token into `TG_TOKEN`.
2. Send any message to your bot.
3. Run `agent-notifier telegram-id` and put the number in `TG_CHAT_ID`.

> **Use a separate bot for the local tool.** Telegram lets a bot receive messages in only one way at a time. The hosted service uses a webhook, and the local tool uses polling, so sharing one bot makes replies fail with a "409 conflict". Sending works either way, but replies (`ask_me`, `check_inbox`) break. Make one bot for local and one for hosted.

### ntfy (free push, no account)
Install the ntfy app, subscribe to a long random topic, and set `NTFY_TOPIC`. Treat the topic like a password. For replies, subscribe to a second topic, set `NTFY_INBOX_TOPIC`, and publish to it from the app.

### Gmail (send-only)
Turn on 2-step verification, create an App Password at myaccount.google.com/apppasswords, and set `GMAIL_USER` and `GMAIL_APP_PASSWORD`.

### WhatsApp (send-only, free, personal use)
Activate CallMeBot (callmebot.com), then set `CALLMEBOT_PHONE` and `CALLMEBOT_APIKEY`. There is no clean free way to receive WhatsApp messages, so use Telegram or ntfy for replies.

### Routing
- `low` and `normal` go to `NOTIFY_DEFAULT_CHANNELS`. If those fail, the next configured channel is tried.
- `high` and `urgent` go to every configured channel.
- `NOTIFY_MIN_SECONDS=45`: the Claude Code hook stays quiet for runs shorter than this.

## 4. Connect your tools

### 4.1 Claude Code (hooks and MCP)
```bash
agent-notifier install-hooks            # adds UserPromptSubmit, Stop and Notification hooks to ~/.claude/settings.json
claude mcp add agent-notifier -- PYTHON -m agent_notifier.server
```
Restart Claude Code. Check with `/mcp`. Now every run longer than 45 seconds pings you when it ends, and Claude can also call `notify_me` and `ask_me`.
Use `--scope project` on `install-hooks` to limit it to one repository. Running the command twice is safe, it never duplicates.

### 4.2 Claude Desktop (MCP only)
Open the config file:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add:
```json
{
  "mcpServers": {
    "agent-notifier": {
      "command": "C:\\Users\\YOU\\agent_notifier\\local\\.venv\\Scripts\\python.exe",
      "args": ["-m", "agent_notifier.server"]
    }
  }
}
```
Use double backslashes on Windows. Fully quit and restart Claude Desktop. Desktop has no finish hook, so add the instruction from section 5 to your project or system instructions.

### 4.3 Codex CLI (MCP and the finish hook)
Edit `~/.codex/config.toml`. The root-level `notify` line must come **before** any `[table]` header:
```toml
notify = ["C:/Users/YOU/agent_notifier/local/.venv/Scripts/python.exe", "-m", "agent_notifier", "codex-notify"]

[mcp_servers.agent-notifier]
command = "C:/Users/YOU/agent_notifier/local/.venv/Scripts/python.exe"
args = ["-m", "agent_notifier.server"]
```
Use forward slashes in TOML paths. `notify` makes Codex call the adapter after each completed turn, passing one JSON argument, and the adapter pings you with the last message. It fires every turn, not only long ones, and repeats within 30 seconds are skipped. If that is too chatty, use only the MCP part and the instruction from section 5.

### 4.4 OpenCode (MCP)
Add to your OpenCode config (`opencode.json` or `opencode.jsonc`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "agent-notifier": {
        "type": "local",
        "command": ["PYTHON", "-m", "agent_notifier.server"]
      }
    }
  }
}
```
Per the current OpenCode docs, servers go under `mcp.servers`. Older versions put them directly under `mcp`, so check the MCP page of the docs for your version. For a finish ping that needs no model decision, run OpenCode through the wrapper in 4.7.

### 4.5 DeepSeek
DeepSeek models do not talk to MCP. The tool running them does. Two good routes:

**A. Claude Code driven by DeepSeek.** DeepSeek offers an Anthropic-compatible endpoint, so Claude Code can use it, and then sections 4.1 hooks and MCP work unchanged. From DeepSeek's integration page (names change, so confirm there):
```bash
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN=<your DeepSeek API key>
export ANTHROPIC_MODEL=deepseek-flash[1m]
export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-flash[1m]
export ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-flash[1m]
export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-flash
export CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash
claude
```
On PowerShell use `$env:NAME="value"`. Keep the key out of shell history and git.

**B. OpenCode or another multi-model harness** with a DeepSeek provider configured. Add the OpenCode snippet from 4.4.

### 4.6 Local models (Ollama, LM Studio, llama.cpp)
A local model cannot call MCP by itself. Run it **through a harness**:
- A coding CLI such as OpenCode pointed at your local OpenAI-compatible endpoint (Ollama serves one at `http://localhost:11434/v1`), then use the 4.4 config.
- Apps with built-in MCP hosting. LM Studio supports MCP servers through its own MCP settings. I have not verified the current file format, so check its docs.

The model must support tool calling, otherwise it never calls `notify_me`. Small local models often do this unreliably, so use the wrapper in 4.7 for a guaranteed finish ping.

### 4.7 Anything else: the `run` wrapper (works with every tool)
```bash
agent-notifier run --title opencode -- opencode
agent-notifier run --min-seconds 60 -- python train.py
agent-notifier run -- npm run build
```
It runs your command normally, then pings you when it exits. Success is a normal ping, a failure is a high-priority ping with the exit code. Only the program name and folder are sent, never the arguments, because arguments can contain keys.

Make it permanent:
- bash/zsh: `alias oc='agent-notifier run --title opencode -- opencode'`
- PowerShell: `function oc { agent-notifier run --title opencode -- opencode @args }` in your `$PROFILE`

For scripts and CI you can also call `agent-notifier send "Deploy finished" --priority high`.

### 4.8 Freebuff and other tools I have not verified
I do not know Freebuff's config format. In order of preference: use its MCP settings with the stdio command from 4.2 (`PYTHON -m agent_notifier.server`), or wrap its launch with `agent-notifier run`, or call `agent-notifier send` from any hook or script step it offers.

## 5. Tell the model when to ping you
For MCP-only tools, add this to `CLAUDE.md`, `AGENTS.md`, custom instructions or the system prompt:

```
When you finish a task that took more than a minute or two, call notify_me once with a 1-3 line summary.
If you are blocked or need a decision, call ask_me instead of guessing.
Use priority "urgent" only if something is broken. Never include secrets or private file contents in a notification.
```

## 6. Replying from your phone
- `ask_me` sends your question and waits (default 300 seconds). Reply to the Telegram message. Many tools cut off tool calls after about a minute or two, so if it times out use a smaller `timeout_seconds` or ask the model to use `check_inbox` later.
- Messages you send to the bot while the agent works are held. The agent reads them with `check_inbox`.
- Only messages from your own `TG_CHAT_ID` are accepted, and they act as instructions to your agent. Do not share the bot.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Nothing arrives | `agent-notifier status`, then `agent-notifier test`. Look at `~/.agent-notifier/notify.log` |
| Telegram 401 or 404 | Wrong `TG_TOKEN` |
| Replies never arrive, 409 error | The bot has a webhook (hosted service). Use a separate bot for local |
| Tools not visible in Claude Desktop | Use the full interpreter path, double backslashes, fully quit the app, check JSON validity |
| MCP server "failed to start" | Run `PYTHON -m agent_notifier.server` in a terminal. It should wait silently. An import error means the venv is wrong |
| Hook never fires | Run was shorter than `NOTIFY_MIN_SECONDS`, or a ping was sent in the last 30 seconds |
| Codex pings too often | Use MCP only, or raise the bar by wrapping long jobs with `run --min-seconds` |
| Two pings per run in Claude Code | You enabled both the hook and the model also called `notify_me`. Keep the hook, drop the instruction |
| Gmail "authentication failed" | You need an App Password, not your normal password |

## 8. Security
- `~/.agent-notifier/.env` holds secrets. Do not commit it or share it. Keys are redacted from errors and logs.
- Hooks never block or crash your agent. Any error is swallowed and logged.
- Do not let agents send secrets through notifications. The server instructions tell the model not to.
- If a token leaks: Telegram `/revoke` in BotFather, Gmail revoke the App Password, change the ntfy topic.

## 9. Uninstall
```bash
pip uninstall agent-notifier
rm -rf ~/.agent-notifier
claude mcp remove agent-notifier          # and delete the entries added to Claude Desktop, Codex and OpenCode configs
```
Remove the three `agent_notifier hook` entries from `~/.claude/settings.json`.

## 11. Controlling agents from Telegram (extended bridge)

The bridge now supports agent picker, folder picker, permission levels, raw shell, and Claude Remote Control.

Commands: /agents, /agent <name>, /pwd, /folders, /cd <name>, /mkdir <name>, /mode [readonly|edit|full <pin>], /lock, /status, /new, /stop, /remote, /remote stop, /sh <cmd> (when enabled), /auth <pin>, /help.

Config: BRIDGE_ROOTS (required, semicolon-separated), BRIDGE_FULL_TTL (default 120 min), BRIDGE_ALLOW_SHELL (default false), BRIDGE_SHELL_TIMEOUT (120), BRIDGE_AGENTS_CUSTOM.

Folder safety: /cd resolves real paths and requires the target to be inside a root (case-insensitive on Windows, defeats .. and symlink/junction escapes). /mkdir validates names. Full paths are never shown in Telegram.

Permission levels: readonly (default tools only), edit (edits, no shell), full (shell allowed, requires PIN, auto-reverts after BRIDGE_FULL_TTL). /lock drops to readonly. File or agent output can never raise the level.

Remote Control: /remote starts `claude --remote-control` in the current folder and sends the captured link. The link belongs to your Claude account; do not forward it. /remote stop ends it. Only Claude Code supports it.

Raw shell: /sh runs in the current folder only when BRIDGE_ALLOW_SHELL=true and mode is full. Output truncated to 3500 chars and redacted. /stop kills it.

Running instances: detected by process name only (tasklist/ps), best-effort; command lines and environment are never read.

## 10. Control your agent from Telegram (wake-up bridge)

A separate, always-on listener: a Telegram message starts a headless coding agent on your machine, and the agent's complete answer comes back to you in Telegram.

### 10.1 Setup
1. Create a **third** bot with @BotFather (hosted service, notifier bot, bridge bot — three separate bots; sharing breaks polling with 409 conflicts).
2. Put its token in `BRIDGE_TG_TOKEN` and your chat id in `BRIDGE_TG_CHAT_ID` (learn it with `agent-notifier bridge-id`).
3. Set `BRIDGE_WORKDIR` to an existing project folder. Refuses filesystem root and your home directory.
4. Start: `agent-notifier listen` (or `--agent codex`, `--permissions edit`, `--dry-run`).

Config keys: `BRIDGE_TG_TOKEN`, `BRIDGE_TG_CHAT_ID`, `BRIDGE_AGENT` (claude/codex/opencode/custom), `BRIDGE_WORKDIR`, `BRIDGE_PERMISSIONS` (readonly/edit/full), `BRIDGE_TIMEOUT` (900), `BRIDGE_QUEUE_MAX` (5), `BRIDGE_PIN`, `BRIDGE_AGENT_CMD`, `BRIDGE_AGENT_ENV_FILE`.

### 10.2 Agent support

| Agent | Supported | How | Verified |
|---|---|---|---|
| Codex CLI | Yes | `codex exec "<msg>"` with `--sandbox` mapped from permissions; resume via `codex exec resume <id>` | `--help` inspected; flags `--sandbox`, `--skip-git-repo-check`, `-o`, `--dangerously-bypass-approvals-and-sandbox` |
| Claude Code (CLI) | Yes | `claude -p "<msg>" --output-format json`, session via `--resume <id>` | `--help` inspected |
| Claude Desktop, Code tab | Partly | Same engine, so `--agent claude` works in the same folder. Sharing a live Desktop session is unverified and may conflict if both use it at once. The bridge keeps its own session by default. | Transcripts found under `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl`; resumable via `--resume <id>` / `--continue`. |
| Claude Desktop, chat tab | No | No headless interface exists. | n/a |
| OpenCode | Yes | `opencode run "<msg>" --format json`, session via `--session` | `--help` inspected (not installed on this machine; flags from a local binary) |
| Any other CLI | Yes | `--agent custom` with `BRIDGE_AGENT_CMD` template | n/a |

### 10.3 Third-party providers (e.g. Nemotron)
Claude Code reads provider settings from `~/.claude/settings.json` (`env.ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL`, ...). A headless `claude -p` started by the bridge usually inherits these, but to be safe set `BRIDGE_AGENT_ENV_FILE` to a dotenv file containing those variables. They are added to the agent process environment, never logged, never sent to Telegram, never printed. Create the file yourself (e.g. `~/.agent-notifier/agent.env`) and point `BRIDGE_AGENT_ENV_FILE` at it. Do not paste secrets in chat.

### 10.4 Permissions
- `readonly` (default): only read-type tools (Claude: `Read Grep Glob`; Codex: `read-only` sandbox).
- `edit`: also file edits, no shell.
- `full`: allows shell. Requires typing `yes` at startup or `--i-understand-the-risk`. Use only in an isolated folder.

### 10.5 Commands (send to the bot)
`/help`, `/status`, `/new` (forget session), `/stop` (kill + clear queue), `/auth <pin>` (only if `BRIDGE_PIN` set). Anything else starting with `/` gets a short help reply and is not sent to the agent. Other text runs the agent.

### 10.6 Safety
- Fixed workdir; refuses root and home.
- One request at a time; queue up to `BRIDGE_QUEUE_MAX`, then "Busy, try again shortly".
- `BRIDGE_TIMEOUT` kills the whole process tree.
- PIN is constant-time compared; only a hash + 8-hour expiry is stored.
- Prompt-injection risk: files the agent reads may contain hostile instructions. Keep permissions low.

### 10.7 Windows autostart
Run `agent-notifier install-bridge-service` for Task Scheduler / launchd / systemd instructions (printed only, nothing installed).

### 10.8 Troubleshooting
- 409 conflict: use a dedicated bot; another poller or webhook is using it.
- Agent refuses actions: expected in readonly/edit; surface the refusal.
- Long runs: "Still working (2m)" every 2 minutes; typing indicator every 4s.
- Output > 4000 chars is split into ordered chunks.
