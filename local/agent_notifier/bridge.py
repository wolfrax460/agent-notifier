"""Telegram wake-up bridge: a message starts a headless coding agent, the answer comes back.

Security model: narrow defaults, fixed workdir, no shell, one request at a time,
optional PIN, timeouts. Treat the Telegram account as potentially compromised.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx

from . import state
from .config import HOME, Settings

BRIDGE_LOG = HOME / "bridge.log"
TG_TIMEOUT = 15.0


def _log(event: str, **kw) -> None:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        parts = [time.strftime("%Y-%m-%d %H:%M:%S"), event]
        for k, v in kw.items():
            parts.append(f"{k}={v}")
        with open(BRIDGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(" ".join(parts) + "\n")
    except OSError:
        pass


def resolve_exe(name: str) -> str | None:
    """Resolve an executable, handling Windows .cmd shims."""
    path = shutil.which(name)
    if path:
        return path
    # try common suffixes
    for suffix in ("", ".exe", ".cmd", ".bat"):
        p = shutil.which(name + suffix)
        if p:
            return p
    return None


def _is_root_or_home(path: Path) -> tuple[bool, str]:
    rp = path.resolve()
    if rp.parent == rp:
        return True, "filesystem root"
    try:
        if rp == Path.home().resolve():
            return True, "home directory"
    except Exception:
        pass
    return False, ""


def _inside(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _real(p: str) -> Path:
    return Path(p).expanduser().resolve()


def build_env(settings: Settings) -> tuple[dict[str, str], list[str]]:
    env = os.environ.copy()
    extra_values: list[str] = []
    env_file = settings.get("BRIDGE_AGENT_ENV_FILE")
    if env_file:
        p = Path(env_file).expanduser()
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if key.strip():
                    env[key.strip()] = value
                    if value:
                        extra_values.append(value)
    return env, extra_values


class Redactor:
    def __init__(self, settings: Settings, env_values: list[str]):
        self.settings = settings
        self.env_values = env_values

    def redact(self, text: str) -> str:
        if not text:
            return text
        for secret in self.settings.secrets() + self.env_values:
            if secret and len(secret) >= 4:
                text = text.replace(secret, "***")
        # Authorization: Bearer ...
        import re

        text = re.sub(r"(?i)Authorization:\s*Bearer\s+\S+", "Authorization: Bearer ***", text)
        # PEM private key blocks
        text = re.sub(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            "[REDACTED PRIVATE KEY]",
            text,
            flags=re.S,
        )
        # known key prefixes
        text = re.sub(
            r"\b(sk-[A-Za-z0-9_-]{10,}|AKIA[A-Z0-9]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b",
            "***",
            text,
        )
        # keyword-adjacent values
        def _repl(m: re.Match) -> str:
            full = m.group(0)
            val = m.group(2)
            return full.replace(val, "***")

        text = re.sub(
            r"(?i)(key|token|secret|password)\s*[:=]\s*[\"']?([A-Za-z0-9+/=_-]{12,})[\"']?",
            _repl,
            text,
        )
        return text


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    text = (text or "").rstrip("\n")
    if not text.strip():
        return ["(the agent returned no text)"]
    chunks: list[str] = []
    buf = text
    while len(buf) > limit:
        window = buf[:limit]
        idx = window.rfind("\n\n")
        if idx == -1 or idx < limit // 3:
            idx = window.rfind("\n")
        if idx == -1 or idx < limit // 3:
            idx = limit
        else:
            idx += 2 if window[idx : idx + 2] == "\n\n" else 1
        chunks.append(buf[:idx].rstrip())
        buf = buf[idx:].lstrip("\n")
    if buf.strip():
        chunks.append(buf)
    if not chunks:
        chunks = ["(the agent returned no text)"]
    return chunks


def kill_process_tree(proc: subprocess.Popen) -> None:
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


# ---------------- Agent presets ----------------


class ClaudeAgent:
    name = "claude"

    def __init__(self, exe: str):
        self.exe = exe
        self._session: str | None = None

    def build(self, message: str, session_id: str | None, permissions: str) -> list[str]:
        cmd = [self.exe, "-p", message, "--output-format", "json"]
        if session_id:
            cmd += ["--resume", session_id]
        if permissions == "readonly":
            cmd += ["--allowedTools", "Read Grep Glob"]
        elif permissions == "edit":
            cmd += ["--allowedTools", "Read Grep Glob Edit Write"]
        elif permissions == "full":
            cmd += ["--dangerously-skip-permissions"]
        return cmd

    def parse(self, stdout: str, stderr: str, rc: int):
        text = (stdout or "").strip()
        sid = None
        # try single JSON object
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                sid = data.get("session_id") or data.get("sessionId")
                result = data.get("result")
                if result is not None:
                    text = result if isinstance(result, str) else json.dumps(result)
        except (ValueError, json.JSONDecodeError):
            # try JSONL: last event wins
            for line in reversed((stdout or "").splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict):
                    sid = data.get("session_id") or data.get("sessionId") or sid
                    if "result" in data and data.get("result") is not None:
                        r = data["result"]
                        text = r if isinstance(r, str) else json.dumps(r)
                        break
        if text is None:
            text = ""
        return text, sid


class CodexAgent:
    name = "codex"

    def __init__(self, exe: str):
        self.exe = exe
        self._out_file: str | None = None

    def build(self, message: str, session_id: str | None, permissions: str) -> list[str]:
        fd, path = tempfile.mkstemp(prefix="codex-out-")
        os.close(fd)
        self._out_file = path
        if session_id:
            cmd = [self.exe, "exec", "resume", session_id, message, "--skip-git-repo-check"]
        else:
            cmd = [self.exe, "exec", message, "--skip-git-repo-check"]
        if permissions == "readonly":
            cmd += ["--sandbox", "read-only"]
        elif permissions == "edit":
            cmd += ["--sandbox", "workspace-write"]
        elif permissions == "full":
            cmd += ["--dangerously-bypass-approvals-and-sandbox"]
        cmd += ["-o", path]
        return cmd

    def parse(self, stdout: str, stderr: str, rc: int):
        text = ""
        if self._out_file and os.path.exists(self._out_file):
            try:
                text = Path(self._out_file).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                text = ""
        if not text:
            text = (stdout or "").strip()
        # clean up
        if self._out_file:
            try:
                os.remove(self._out_file)
            except OSError:
                pass
            self._out_file = None
        # codex has no session id in simple output; return None
        return text, None


class OpenCodeAgent:
    name = "opencode"

    def __init__(self, exe: str):
        self.exe = exe
        self._model: str = ""

    def build(self, message: str, session_id: str | None, permissions: str) -> list[str]:
        cmd = [self.exe, "run", message, "--format", "json"]
        if session_id:
            cmd += ["--session", session_id]
        if permissions == "full":
            cmd += ["--auto"]
        return cmd

    def parse(self, stdout: str, stderr: str, rc: int):
        texts: list[str] = []
        sid = None
        model = ""
        last_error = ""
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                # skip non-JSON lines
                continue
            if not isinstance(data, dict):
                continue
            sid = data.get("sessionID") or data.get("session_id") or sid
            if data.get("type") == "text":
                t = data.get("text")
                if not isinstance(t, str):
                    part = data.get("part")
                    if isinstance(part, dict):
                        t = part.get("text")
                if isinstance(t, str):
                    texts.append(t)
            # capture model if present
            m = data.get("model") or data.get("modelID")
            if isinstance(m, str) and m:
                model = m
            # track last error-ish line
            if data.get("type") in ("error",) or data.get("error"):
                err = data.get("error") or data.get("message")
                if isinstance(err, str):
                    last_error = err
        if model:
            self._model = model
        if texts:
            text = "".join(texts)
        else:
            text = "(opencode returned no text)"
            if last_error:
                text += f"\n{last_error}"
            elif (stderr or "").strip():
                text += f"\n{(stderr or '').strip()[-800:]}"
        return text, sid


class CustomAgent:
    name = "custom"

    def __init__(self, template: str):
        self.template = template
        self._use_stdin = False
        self._stdin_text: str | None = None

    def build(self, message: str, session_id: str | None, permissions: str) -> list[str]:
        posix = os.name != "nt"
        try:
            parts = shlex.split(self.template, posix=posix)
        except ValueError:
            parts = self.template.split()
        # Windows shlex(posix=False) keeps quotes; strip them so paths work.
        cleaned = []
        for p in parts:
            if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'":
                p = p[1:-1]
            cleaned.append(p)
        parts = cleaned
        if "{message}" in parts:
            idx = parts.index("{message}")
            parts[idx] = message
            self._use_stdin = False
            self._stdin_text = None
        else:
            self._use_stdin = True
            self._stdin_text = message
        return parts

    @property
    def uses_stdin(self) -> bool:
        return self._use_stdin

    def parse(self, stdout: str, stderr: str, rc: int):
        return (stdout or "").strip(), None


def make_agent(name: str, template: str | None):
    if name == "claude":
        exe = resolve_exe("claude")
        if not exe:
            return None
        return ClaudeAgent(exe)
    if name == "codex":
        exe = resolve_exe("codex")
        if not exe:
            return None
        return CodexAgent(exe)
    if name == "opencode":
        exe = resolve_exe("opencode")
        if not exe:
            # try known install location
            known = Path.home() / ".dsh" / "opencode-xdbridge" / "runtime" / "1.19.5" / "opencode.exe"
            if known.exists():
                exe = str(known)
            else:
                return None
        return OpenCodeAgent(exe)
    if name == "custom":
        return CustomAgent(template or "")
    return None


def run_agent(agent, message, workdir, permissions, timeout, env, session_id):
    cmd = agent.build(message, session_id, permissions)
    use_stdin = False
    stdin_data = None
    if isinstance(agent, CustomAgent) and agent.uses_stdin:
        use_stdin = True
        stdin_data = agent._stdin_text
    # resolve first token
    if cmd and not os.path.isabs(cmd[0]) and not os.path.exists(cmd[0]):
        resolved = resolve_exe(cmd[0]) or shutil.which(cmd[0])
        if resolved:
            cmd[0] = resolved
    # windows shim
    if os.name == "nt" and cmd and str(cmd[0]).lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c", cmd[0]] + cmd[1:]
    proc = None
    stdout = ""
    stderr = ""
    timed_out = False
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=env,
            stdin=subprocess.PIPE if use_stdin else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name != "nt"),
        )
        try:
            stdout, stderr = proc.communicate(input=stdin_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                stdout = stdout or ""
                stderr = stderr or ""
    except FileNotFoundError as exc:
        return "", str(exc), 127, False, None
    except Exception as exc:
        return "", str(exc), 1, False, None
    rc = proc.returncode if proc is not None else 1
    text, sid = agent.parse(stdout or "", stderr or "", rc)
    return text, (stderr or ""), rc, timed_out, sid


# ---------------- Telegram helpers ----------------


def _tg_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def tg_call(token: str, method: str, payload: dict | None = None, timeout: float = TG_TIMEOUT) -> Any:
    r = httpx.post(_tg_url(token, method), json=payload or {}, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "telegram error"))
    return data.get("result")


def tg_get_updates(token: str, offset: int | None, timeout: int = 30) -> list[dict]:
    payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset:
        payload["offset"] = offset
    r = httpx.post(_tg_url(token, "getUpdates"), json=payload, timeout=timeout + 5)
    if r.status_code == 409:
        raise httpx.HTTPStatusError("conflict", request=r.request, response=r)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "getUpdates failed"))
    return data.get("result", []) or []


def tg_send_message(token: str, chat_id: str, text: str) -> None:
    tg_call(token, "sendMessage", {"chat_id": chat_id, "text": text})


def tg_send_chat_action(token: str, chat_id: str, action: str = "typing") -> None:
    try:
        tg_call(token, "sendChatAction", {"chat_id": chat_id, "action": action}, timeout=10)
    except Exception:
        pass


# ---------------- Commands helpers ----------------


def cmd_bridge_id(_: argparse.Namespace) -> int:
    settings = Settings()
    token = settings.get("BRIDGE_TG_TOKEN")
    if not token:
        print("Set BRIDGE_TG_TOKEN first (from @BotFather), then message your bot once.")
        return 1
    try:
        updates = tg_get_updates(token, None, timeout=5)
    except Exception as exc:
        print(f"Failed to reach Telegram: {type(exc).__name__}")
        return 1
    seen: dict[str, str] = {}
    for upd in updates:
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
            seen[str(chat["id"])] = name
    if not seen:
        print("No messages found. Send any message to your bridge bot in Telegram, then run again.")
        return 1
    for cid, name in seen.items():
        print(f"BRIDGE_TG_CHAT_ID={cid}   ({name})")
    return 0


def cmd_install_bridge_service(_: argparse.Namespace) -> int:
    python = sys.executable
    home = str(HOME)
    print("=== Agent Notifier: bridge service install instructions ===")
    print()
    print("These are instructions only. Nothing is installed automatically.")
    print()
    print("--- Windows (Task Scheduler) ---")
    print("1. Open Task Scheduler -> Create Task.")
    print("   General: Name 'AgentNotifierBridge', 'Run whether user is logged on or not' optional, 'Hidden' checked.")
    print("   Triggers: 'At log on' (your user).")
    print("   Actions: Start a program:")
    print(f"     Program: {python}")
    print(f"     Arguments: -m agent_notifier listen")
    print(f"     Start in: {os.path.dirname(python)}")
    print("   Settings: 'Restart on failure' every 1 minute, 3 times; 'Stop if runs longer than' unchecked.")
    print("   Conditions: uncheck 'Start only if on AC power' if on a laptop.")
    print()
    print("--- macOS (launchd) ---")
    print(f"Create ~/Library/LaunchAgents/com.agentnotifier.bridge.plist with:")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.agentnotifier.bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>agent_notifier</string>
    <string>listen</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{home}/bridge-stdout.log</string>
  <key>StandardErrorPath</key><string>{home}/bridge-stderr.log</string>
</dict>
</plist>"""
    print(plist)
    print("Then: launchctl load ~/Library/LaunchAgents/com.agentnotifier.bridge.plist")
    print()
    print("--- Linux (systemd user unit) ---")
    unit = f"""[Unit]
Description=Agent Notifier Telegram bridge
After=network-online.target

[Service]
Type=simple
ExecStart={python} -m agent_notifier listen
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
    print(f"Create ~/.config/systemd/user/agent-notifier-bridge.service with:")
    print(unit)
    print("Then: systemctl --user daemon-reload && systemctl --user enable --now agent-notifier-bridge")
    print()
    print("Ensure BRIDGE_WORKDIR and all keys are set in ~/.agent-notifier/.env before starting.")
    return 0


# ---------------- listen implementation ----------------


def cmd_listen(args: argparse.Namespace) -> int:
    settings = Settings()
    token = settings.get("BRIDGE_TG_TOKEN")
    chat_id = settings.get("BRIDGE_TG_CHAT_ID")
    agent_name = (args.agent or settings.get("BRIDGE_AGENT", "claude")).strip().lower()
    workdir_str = args.workdir or settings.get("BRIDGE_WORKDIR")
    permissions = args.permissions or settings.get("BRIDGE_PERMISSIONS", "edit")
    roots_raw = settings.get("BRIDGE_ROOTS")
    # parse roots: JSON array or separator list
    roots: list[Path] = []
    roots_raw = roots_raw.strip()
    if roots_raw:
        try:
            arr = json.loads(roots_raw)
            if isinstance(arr, list):
                roots = [Path(str(x)).expanduser() for x in arr]
        except (ValueError, json.JSONDecodeError):
            sep = ";" if os.name == "nt" else ":"
            roots = [Path(x.strip()).expanduser() for x in roots_raw.split(sep) if x.strip()]
    roots = [r.resolve() for r in roots if r.exists()]
    if not roots:
        print("BRIDGE_ROOTS is required (semicolon-separated folders).")
        return 1
    try:
        timeout = int(args.timeout if args.timeout is not None else settings.get("BRIDGE_TIMEOUT", "900"))
    except ValueError:
        timeout = 900
    try:
        queue_max = int(settings.get("BRIDGE_QUEUE_MAX", "5"))
    except ValueError:
        queue_max = 5
    try:
        full_ttl = int(settings.get("BRIDGE_FULL_TTL", "120"))
    except ValueError:
        full_ttl = 120
    allow_shell = settings.get("BRIDGE_ALLOW_SHELL", "false").lower() in ("1", "true", "yes")
    try:
        shell_timeout = int(settings.get("BRIDGE_SHELL_TIMEOUT", "120"))
    except ValueError:
        shell_timeout = 120
    pin = settings.get("BRIDGE_PIN")
    agent_cmd = settings.get("BRIDGE_AGENT_CMD")
    dry_run = bool(args.dry_run)
    i_understand = bool(getattr(args, "i_understand_the_risk", False))

    if not token:
        print("BRIDGE_TG_TOKEN is required. Set it in ~/.agent-notifier/.env (or env).")
        return 1
    if not chat_id:
        print("BRIDGE_TG_CHAT_ID is required. Run `agent-notifier bridge-id` to learn it.")
        return 1
    if not workdir_str:
        print("BRIDGE_WORKDIR is required and must be an existing directory.")
        return 1
    workdir = Path(workdir_str).expanduser()
    try:
        workdir = workdir.resolve(strict=True)
    except FileNotFoundError:
        print(f"BRIDGE_WORKDIR does not exist: {workdir_str}")
        return 1
    if not workdir.is_dir():
        print("BRIDGE_WORKDIR must be a directory.")
        return 1
    bad, reason = _is_root_or_home(workdir)
    if bad:
        print(f"Refusing workdir that is the {reason}. Use a subfolder.")
        return 1
    # require inside a root
    if not any(_inside(workdir, r) for r in roots):
        print("BRIDGE_WORKDIR must be inside one of BRIDGE_ROOTS.")
        return 1
    if permissions not in ("readonly", "edit", "full"):
        permissions = "readonly"
    if agent_name not in ("claude", "codex", "opencode", "custom"):
        print(f"Unknown agent: {agent_name}")
        return 1
    if agent_name == "custom" and not agent_cmd:
        print("BRIDGE_AGENT_CMD is required when --agent custom.")
        return 1

    if permissions == "full" and not dry_run and not i_understand:
        print("WARNING: 'full' permissions let the agent run shell commands without approval.")
        print("This is dangerous if your Telegram account is compromised.")
        try:
            answer = input("Type 'yes' to continue: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "yes":
            print("Aborted.")
            return 1

    agent = make_agent(agent_name, agent_cmd)
    if agent is None:
        print(f"Agent CLI not found for '{agent_name}'. Is it installed and on PATH?")
        return 1

    env, env_values = build_env(settings)
    redactor = Redactor(settings, env_values)

    if dry_run:
        print(f"Would listen. agent={agent_name} workdir={workdir.name} permissions={permissions} timeout={timeout}s")
        try:
            sample = agent.build("HELLO", None, permissions)
            print("Sample command:", redactor.redact(" ".join(sample)))
        except Exception as exc:
            print("Sample command: (build failed)", type(exc).__name__)
        return 0

    # state containers
    st0 = state.load()
    offset_box = {"v": st0.get("bridge_offset")}
    sessions0 = st0.get("bridge_sessions", {})
    active_agent = {"v": args.agent or settings.get("BRIDGE_AGENT", "claude")}
    _key0 = f"{active_agent['v']}|{workdir}"
    session_box = {"v": sessions0.get(_key0)}
    active_folder = {"v": workdir}
    permission = {"v": permissions}
    recent_folders = {"v": list(st0.get("bridge_recent_folders", []))}
    full_until = {"v": st0.get("bridge_full_until", 0) or 0}
    remote_proc = {"p": None}
    running = {"v": False}
    queue: list[str] = []
    lock = threading.Lock()
    current_proc = {"p": None}
    start_time = time.time()
    wrong_attempts: list[float] = []
    ignored_counter = {"n": 0}

    def send(text: str) -> None:
        for chunk in chunk_text(redactor.redact(text)):
            try:
                tg_send_message(token, chat_id, chunk)
            except Exception as exc:
                _log("send_error", type=type(exc).__name__)

    def handle_command(text: str, msg_id=None) -> None:
        parts = text.split()
        cmd = parts[0].lower().split("@")[0] if parts else ""
        if cmd == "/help":
            send("Commands: /agents /agent <name> /pwd /folders /cd <name> /mkdir <name> /mode [readonly|edit|full <pin>] /lock /status /new /stop /remote [/remote stop] /sh <cmd> (if enabled) /auth <pin> /help")
        elif cmd == "/agents":
            from . import agents as ag
            ags = ag.detect(settings)
            lines = ["Agents:"]
            for a in ags:
                mark = " (selected)" if a["name"] == active_agent["v"] else ""
                inst = "installed" if a["installed"] else "MISSING"
                lines.append(f"  {a['name']}: {inst} {a['version']}  bridge={running['v'] and active_agent['v']==a['name']}  other={a['others']}{mark}")
            send("\n".join(lines))
            btns = [[{"text": f"Use {a['name']}", "callback_data": f"agent:{a['name']}"}] for a in ags if a["installed"]]
            if btns:
                try:
                    tg_call(token, "sendMessage", {"chat_id": chat_id, "text": "Pick an agent:", "reply_markup": {"inline_keyboard": btns}})
                except Exception:
                    pass
        elif cmd == "/agent":
            if len(parts) < 2:
                send("Usage: /agent <name>")
                return
            name = parts[1].strip()
            from . import agents as ag
            ags = {a["name"]: a for a in ag.detect(settings)}
            if name not in ags or not ags[name]["installed"]:
                send(f"Agent not installed: {name}")
                return
            key = f"{active_agent['v']}|{active_folder['v']}"
            st = state.load()
            sessions = st.setdefault("bridge_sessions", {})
            if session_box["v"]:
                sessions[key] = session_box["v"]
            active_agent["v"] = name
            new_key = f"{name}|{active_folder['v']}"
            session_box["v"] = sessions.get(new_key)
            st["bridge_agent"] = name
            state.save(st)
            send(f"Switched to {name}.")
        elif cmd == "/pwd":
            rootname = next((r.name for r in roots if _inside(active_folder["v"], r)), "?")
            send(f"folder: {active_folder['v'].name}\nroot: {rootname}")
        elif cmd == "/folders":
            root = next((r for r in roots if _inside(active_folder["v"], r)), roots[0])
            subs = []
            try:
                for p in sorted(root.iterdir()):
                    if p.is_dir():
                        subs.append(p)
            except OSError:
                pass
            subs = subs[:20]
            btns = [[{"text": p.name, "callback_data": f"cd:{p.name}"}] for p in subs]
            btns.append([{"text": "Up", "callback_data": "up:1"}, {"text": "Recent", "callback_data": "recent:1"}])
            send(f"Root: {root.name}\nCurrent: {active_folder['v'].name}")
            try:
                tg_call(token, "sendMessage", {"chat_id": chat_id, "text": "Folders:", "reply_markup": {"inline_keyboard": btns}})
            except Exception:
                pass
        elif cmd == "/cd":
            if len(parts) < 2:
                send("Usage: /cd <name or path>")
                return
            if running["v"]:
                send("A job is running; folder change applies to the next request.")
            target = parts[1]
            if os.path.isabs(target) or (os.name == "nt" and len(target) > 1 and target[1] == ":"):
                cand = Path(target)
            else:
                cand = active_folder["v"] / target
            try:
                cand = cand.resolve(strict=True)
            except FileNotFoundError:
                send("Folder not found.")
                return
            if not cand.is_dir():
                send("Not a directory.")
                return
            if not any(_inside(cand, r) for r in roots):
                send("Rejected: outside allowed roots.")
                return
            active_folder["v"] = cand
            rec = [str(cand)] + [x for x in recent_folders["v"] if x != str(cand)]
            recent_folders["v"] = rec[:5]
            st = state.load()
            st["bridge_recent_folders"] = rec[:5]
            st["bridge_folder"] = str(cand)
            state.save(st)
            send(f"Changed to {cand.name}.")
        elif cmd == "/mkdir":
            if len(parts) < 2:
                send("Usage: /mkdir <name>")
                return
            name = parts[1]
            if ("/" in name or "\\" in name or ".." in name or name in ("", ".", "..")):
                send("Invalid folder name.")
                return
            newp = active_folder["v"] / name
            try:
                newp.mkdir(parents=False, exist_ok=False)
                send(f"Created {name}.")
            except Exception:
                send("Could not create folder.")
        elif cmd == "/mode":
            if len(parts) == 1:
                send(f"Mode: {permission['v']}")
                return
            lvl = parts[1].lower()
            if lvl in ("readonly", "edit"):
                permission["v"] = lvl
                full_until["v"] = 0
                st = state.load(); st["bridge_permission"] = lvl; st["bridge_full_until"] = 0; state.save(st)
                send(f"Mode set to {lvl}.")
            elif lvl == "full":
                if len(parts) < 3:
                    send("Usage: /mode full <pin>")
                    return
                configured_pin = settings.get("BRIDGE_PIN")
                if not configured_pin:
                    send("No PIN configured.")
                    return
                submitted = parts[2]
                now = time.time()
                st = state.load()
                wrong = st.get("bridge_wrong_pins", [])
                wrong = [t for t in wrong if now - t < 600]
                if len(wrong) >= 5:
                    send("Too many wrong attempts. Try later.")
                    return
                import hmac as _hmac
                if not _hmac.compare_digest(submitted, configured_pin):
                    wrong.append(now)
                    st["bridge_wrong_pins"] = wrong
                    state.save(st)
                    send("Wrong PIN.")
                    _log("wrong_pin")
                    return
                try:
                    tg_call(token, "deleteMessage", {"chat_id": chat_id, "message_id": msg_id}, timeout=5)
                except Exception:
                    pass
                permission["v"] = "full"
                ttl = full_ttl
                until = (now + ttl * 60) if ttl > 0 else 0
                full_until["v"] = until
                st = state.load()
                st["bridge_permission"] = "full"
                st["bridge_full_until"] = until
                st["bridge_wrong_pins"] = []
                state.save(st)
                send(f"Full mode enabled" + (f" for {ttl} min." if ttl > 0 else "."))
                _log("full_enable")
            else:
                send("Unknown mode. Use readonly, edit, or full <pin>.")
        elif cmd == "/lock":
            permission["v"] = "readonly"
            full_until["v"] = 0
            st = state.load(); st["bridge_permission"] = "readonly"; st["bridge_full_until"] = 0; state.save(st)
            send("Locked to readonly. PIN required to raise level.")
        elif cmd == "/new":
            key = f"{active_agent['v']}|{active_folder['v']}"
            st = state.load()
            sessions = st.get("bridge_sessions", {})
            sessions.pop(key, None)
            st["bridge_sessions"] = sessions
            state.save(st)
            session_box["v"] = None
            send("Session cleared. Next message starts fresh.")
        elif cmd == "/stop":
            p = current_proc["p"]
            if p is not None:
                kill_process_tree(p)
                current_proc["p"] = None
            rp = remote_proc["p"]
            if rp is not None:
                kill_process_tree(rp)
                remote_proc["p"] = None
            with lock:
                queue.clear()
            send("Stopped. Queue cleared.")
        elif cmd == "/remote":
            if active_agent["v"] != "claude":
                send("Remote Control is Claude Code only.")
                return
            if len(parts) > 1 and parts[1].lower() == "stop":
                rp = remote_proc["p"]
                if rp is not None:
                    kill_process_tree(rp)
                    remote_proc["p"] = None
                    send("Remote Control stopped.")
                else:
                    send("Remote Control not running.")
                return
            if remote_proc["p"] is not None:
                send("Remote Control already running.")
                return
            import shutil as _sh
            exe = _sh.which("claude")
            if not exe:
                send("Claude CLI not found.")
                return
            send("Remote Control requires an interactive terminal. Run this by hand:\nclaude --remote-control\n(in folder " + active_folder["v"].name + ")\nThe session link belongs to your Claude account; do not forward it.")
        elif cmd == "/sh":
            if not allow_shell:
                send("Shell disabled (BRIDGE_ALLOW_SHELL=false).")
                return
            if permission["v"] != "full":
                send("Shell requires full mode (/mode full <pin>).")
                return
            command = text[len(parts[0]):].strip()
            if not command:
                send("Usage: /sh <command>")
                return
            import subprocess as _sp
            proc = None
            try:
                proc = _sp.Popen(command, shell=True, cwd=str(active_folder["v"]), stdout=_sp.PIPE, stderr=_sp.PIPE, text=True)
                current_proc["p"] = proc
                try:
                    out, err = proc.communicate(timeout=shell_timeout)
                except _sp.TimeoutExpired:
                    kill_process_tree(proc)
                    out, err = proc.communicate()
                    send(redactor.redact(f"Timed out.\n{(out or '')[-1700:]}\n{(err or '')[-800:]}")[:3500])
                    current_proc["p"] = None
                    return
                combined = (out or "") + (("\n" + err) if err else "")
                combined = redactor.redact(combined)
                if len(combined) > 3500:
                    combined = combined[:3500] + "\n... (truncated)"
                if not combined.strip():
                    combined = "(no output)"
                send(combined)
            except Exception:
                send("Shell command failed.")
            finally:
                current_proc["p"] = None
            _log("shell", exit=getattr(proc, "returncode", "?"), duration=0)
        elif cmd == "/auth":
            if not pin:
                send("No PIN configured.")
                return
            if len(parts) < 2:
                send("Usage: /auth <pin>")
                return
            now = time.time()
            st = state.load()
            wrong = st.get("bridge_wrong_pins", [])
            wrong = [t for t in wrong if now - t < 600]
            if len(wrong) >= 5:
                send("Too many wrong attempts. Try later.")
                return
            import hmac as _hmac
            if not _hmac.compare_digest(parts[1], pin):
                wrong.append(now)
                st["bridge_wrong_pins"] = wrong
                state.save(st)
                send("Wrong PIN.")
                _log("wrong_pin")
                return
            try:
                tg_call(token, "deleteMessage", {"chat_id": chat_id, "message_id": msg_id}, timeout=5)
            except Exception:
                pass
            st["bridge_wrong_pins"] = []
            st["bridge_auth_until"] = time.time() + 8 * 3600
            st["bridge_pin_hash"] = __import__("hashlib").sha256(pin.encode()).hexdigest()
            state.save(st)
            send("PIN accepted.")
        elif cmd == "/status":
            with lock:
                qlen = len(queue)
                is_running = running["v"]
            uptime = fmt_duration(time.time() - start_time)
            lines = [
                f"agent: {active_agent['v']}",
                f"folder: {active_folder['v'].name}",
                f"mode: {permission['v']}",
                f"running: {is_running}",
                f"queue: {qlen}",
                f"uptime: {uptime}",
                f"remote: {'running' if remote_proc['p'] is not None else 'stopped'}",
                f"session: {'yes' if session_box['v'] else 'none'}",
            ]
            send("\n".join(lines))
        else:
            send("Unknown command. Send /help for the list.")

    def process_job(message: str) -> None:
        stop_typing = threading.Event()
        stop_status = threading.Event()

        def typing_loop():
            while not stop_typing.wait(4):
                tg_send_chat_action(token, chat_id, "typing")

        def status_loop():
            start = time.time()
            last = start
            while not stop_status.wait(30):
                if time.time() - start >= 60 and time.time() - last >= 120:
                    try:
                        send(f"Still working ({int((time.time() - start) // 60)}m)")
                    except Exception:
                        pass
                    last = time.time()

        tt = threading.Thread(target=typing_loop, daemon=True)
        ts = threading.Thread(target=status_loop, daemon=True)
        tt.start()
        ts.start()

        run_start = time.time()
        text, stderr, rc, timed_out, sid = run_agent(
            agent, message, workdir, permissions, timeout, env, session_box["v"]
        )
        if sid:
            session_box["v"] = sid
            key = f"{active_agent['v']}|{active_folder['v']}"
            st = state.load()
            sessions = st.setdefault("bridge_sessions", {})
            sessions[key] = sid
            state.save(st)

        stop_typing.set()
        stop_status.set()
        tt.join(timeout=2)
        ts.join(timeout=2)

        duration = int(time.time() - run_start)
        if timed_out:
            err = redactor.redact(f"Timed out after {timeout}s. Last stderr:\n{stderr[-800:]}")
            send(err)
            _log("run_timeout", duration=duration, exit=-1)
        elif rc != 0:
            err = redactor.redact(f"Agent exited with code {rc}. Last stderr:\n{stderr[-800:]}")
            send(err)
            _log("run_fail", duration=duration, exit=rc)
        else:
            out = redactor.redact(text)
            if getattr(agent, "name", "") == "opencode":
                model = getattr(agent, "_model", "") or "default"
                out = out.rstrip() + f"\n\n[opencode | {model} | {active_folder['v'].name}]"
            for chunk in chunk_text(out):
                send(chunk)
            _log("run_ok", duration=duration, exit=0)

        current_proc["p"] = None

    def worker(first: str) -> None:
        running["v"] = True
        current = first
        while current is not None:
            process_job(current)
            with lock:
                current = queue.pop(0) if queue else None
        running["v"] = False

    print(f"Bridge listening. agent={agent.name} workdir={workdir.name} permissions={permissions}")
    print("Commands: /agents /agent /pwd /folders /cd /mkdir /mode /lock /status /new /stop /remote /sh /auth /help")
    print("Press Ctrl+C to stop.")
    _log("start", version="0.1.0", agent=agent.name, permissions=permissions, commands="/agents /agent /pwd /folders /cd /mkdir /mode /lock /status /new /stop /remote /sh /auth /help")

    backoff = 1
    try:
        while True:
            try:
                updates = tg_get_updates(token, offset_box["v"], timeout=30)
                backoff = 1
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 409:
                    print("This bot has a webhook or another poller; use a dedicated bot.")
                    return
                _log("http_error", code=getattr(exc.response, "status_code", "?"))
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            except Exception as exc:
                _log("net_error", type=type(exc).__name__)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # full-mode TTL revert
            if permission["v"] == "full" and full_ttl > 0 and full_until["v"] and time.time() > full_until["v"]:
                permission["v"] = "edit"
                full_until["v"] = 0
                st = state.load()
                st["bridge_permission"] = "edit"
                st["bridge_full_until"] = 0
                state.save(st)
                send("Full mode expired; reverted to edit.")
                _log("full_revert")
            for upd in updates or []:
                try:
                    offset_box["v"] = max(offset_box["v"] or 0, upd["update_id"] + 1)
                    # callback queries (inline buttons)
                    cq = upd.get("callback_query")
                    if cq:
                        cq_from = str((cq.get("from") or {}).get("id", ""))
                        if cq_from != str(chat_id):
                            continue
                        data = cq.get("data") or ""
                        # answer callback
                        try:
                            tg_call(token, "answerCallbackQuery", {"callback_query_id": cq.get("id", "")}, timeout=5)
                        except Exception:
                            pass
                        if data.startswith("agent:"):
                            name = data.split(":", 1)[1]
                            # validate installed
                            from . import agents as ag
                            ags = {a["name"]: a for a in ag.detect(settings)}
                            if name in ags and ags[name]["installed"]:
                                # save current session
                                key = f"{active_agent['v']}|{active_folder['v']}"
                                st = state.load()
                                sessions = st.setdefault("bridge_sessions", {})
                                if session_box["v"]:
                                    sessions[key] = session_box["v"]
                                active_agent["v"] = name
                                new_key = f"{name}|{active_folder['v']}"
                                session_box["v"] = sessions.get(new_key)
                                st["bridge_agent"] = name
                                state.save(st)
                                send(f"Switched to {name}.")
                        elif data.startswith("cd:"):
                            name = data.split(":", 1)[1]
                            cand = active_folder["v"] / name
                            try:
                                cand = cand.resolve(strict=True)
                            except Exception:
                                cand = None
                            if cand and cand.is_dir() and any(_inside(cand, r) for r in roots):
                                active_folder["v"] = cand
                                rec = [str(cand)] + [x for x in recent_folders["v"] if x != str(cand)]
                                recent_folders["v"] = rec[:5]
                                st = state.load()
                                st["bridge_recent_folders"] = rec[:5]
                                st["bridge_folder"] = str(cand)
                                state.save(st)
                                send(f"Changed to {cand.name}.")
                        continue
                    st = state.load()
                    st["bridge_offset"] = offset_box["v"]
                    state.save(st)

                    msg = upd.get("message") or {}
                    chat = msg.get("chat") or {}
                    if chat.get("type") != "private":
                        ignored_counter["n"] += 1
                        continue
                    if str(chat.get("id")) != str(chat_id):
                        ignored_counter["n"] += 1
                        if ignored_counter["n"] % 10 == 0:
                            _log("ignored", count=ignored_counter["n"])
                        continue
                    text = msg.get("text")
                    if not text:
                        continue

                    if text.startswith("/"):
                        handle_command(text, msg.get("message_id"))
                        continue

                    # PIN gate
                    if pin:
                        st = state.load()
                        auth_until = st.get("bridge_auth_until", 0) or 0
                        pin_hash = st.get("bridge_pin_hash")
                        current_hash = hashlib.sha256(pin.encode()).hexdigest()
                        if not (time.time() < auth_until and pin_hash == current_hash):
                            _log("locked_ignore")
                            continue

                    with lock:
                        if running["v"]:
                            if len(queue) >= queue_max:
                                send("Busy, try again shortly.")
                                _log("busy")
                                continue
                            queue.append(text)
                            pos = len(queue)
                            queued = True
                        else:
                            queued = False
                    if running["v"] and queued:
                        send(f"Queued (position {pos}).")
                        continue
                    if not running["v"]:
                        threading.Thread(target=worker, args=(text,), daemon=True).start()
                except Exception as exc:
                    _log("update_error", type=type(exc).__name__)
    except KeyboardInterrupt:
        print("\nStopping bridge.")
        _log("stop", reason="keyboard")
    return 0
