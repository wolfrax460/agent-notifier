"""agent-notifier CLI: send, test, status, telegram-id, inbox, hook, install-hooks."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import channels as ch
from .config import HOME, PACKAGE_ROOT, Settings
from .core import notify

HOOK_MARK = "agent_notifier hook"


def _hook_command() -> str:
    return f'"{sys.executable}" -m agent_notifier hook'


def cmd_status(_: argparse.Namespace) -> int:
    s = Settings()
    print(f"default channels: {', '.join(s.default_channels)}   min seconds: {s.min_seconds}")
    for name, c in ch.build(s).items():
        state = "OK     " if c.configured() else "missing"
        way = "two-way" if c.inbound else "send-only"
        print(f"  {name:<9} {state}  {way:<9}  needs: {c.needs}")
    return 0


def cmd_send(a: argparse.Namespace) -> int:
    res = notify(a.message, a.title, a.priority, a.channel or None)
    print(json.dumps(res, indent=2))
    return 0 if res.get("sent") else 1


def cmd_test(_: argparse.Namespace) -> int:
    res = notify("agent-notifier test: if you see this, the channel works.", "Test", "high")
    print(json.dumps(res, indent=2))
    return 0 if res.get("sent") else 1


def cmd_bridge_id(_: argparse.Namespace) -> int:
    from .bridge import cmd_bridge_id as _cmd

    return _cmd(_)


def cmd_device_pair(a: argparse.Namespace) -> int:
    from .device import cmd_device_pair as _cmd

    return _cmd(a)


def cmd_device_status(a: argparse.Namespace) -> int:
    from .device import cmd_device_status as _cmd

    return _cmd(a)


def cmd_device_unpair(a: argparse.Namespace) -> int:
    from .device import cmd_device_unpair as _cmd

    return _cmd(a)


def cmd_companion_start(a: argparse.Namespace) -> int:
    from .companion import cmd_companion_start as _cmd

    return _cmd(a)


def cmd_companion_status(a: argparse.Namespace) -> int:
    from .companion import cmd_companion_status as _cmd

    return _cmd(a)


def cmd_companion_stop(a: argparse.Namespace) -> int:
    from .companion import cmd_companion_stop as _cmd

    return _cmd(a)


def cmd_autostart_install(a: argparse.Namespace) -> int:
    from .autostart import install

    return install()


def cmd_autostart_uninstall(a: argparse.Namespace) -> int:
    from .autostart import uninstall

    return uninstall()


def cmd_autostart_status(a: argparse.Namespace) -> int:
    from .autostart import status

    state = status()
    print(json.dumps(state, indent=2))
    return 0

def cmd_install_bridge_service(_: argparse.Namespace) -> int:
    from .bridge import cmd_install_bridge_service as _cmd

    return _cmd(_)

def cmd_telegram_id(_: argparse.Namespace) -> int:
    token = Settings().get("TG_TOKEN")
    if not token:
        print("Set TG_TOKEN first (from @BotFather), then message your bot once.")
        return 1
    chats = ch.discover_telegram_chats(token)
    if not chats:
        print("No messages found. Send any message to your bot in Telegram, then run again.")
        return 1
    for cid, name in chats:
        print(f"TG_CHAT_ID={cid}   ({name})")
    return 0


def cmd_inbox(a: argparse.Namespace) -> int:
    from .inbox import poll_inbox

    msgs = poll_inbox(wait=a.wait, consume=not a.peek)
    for m in msgs:
        print(f"[{m['channel']}] {m['text']}")
    if not msgs:
        print("(no new messages)")
    return 0


def cmd_hook(_: argparse.Namespace) -> int:
    from .hooks import run_from_stdin

    return run_from_stdin()


def cmd_listen(a: argparse.Namespace) -> int:
    from .bridge import cmd_listen as _cmd

    return _cmd(a)


def cmd_run(a: argparse.Namespace) -> int:
    """Run any command, then notify when it exits. Works with every agent, script or build."""
    import subprocess
    import time

    from .hooks import _fmt_duration

    cmd = list(a.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("usage: agent-notifier run [--title T] [--min-seconds N] -- <command ...>", file=sys.stderr)
        return 2
    start = time.time()
    try:
        rc = subprocess.call(cmd)
    except FileNotFoundError:
        print(f"agent-notifier: command not found: {cmd[0]}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        rc = 130
    elapsed = time.time() - start
    if rc == 0 and elapsed < a.min_seconds:
        return rc
    # Only the program name and folder are sent, never its arguments (they may contain API keys).
    label = a.title or Path(cmd[0]).name
    where = Path.cwd().name
    took = _fmt_duration(elapsed)
    if rc == 0:
        notify(f"Finished OK in {took} ({where})", title=f"{label} finished", priority="normal")
    else:
        notify(f"Exited with code {rc} after {took} ({where})", title=f"{label} FAILED", priority="high")
    return rc


def cmd_codex_notify(a: argparse.Namespace) -> int:
    from .hooks import handle_codex

    try:
        raw = a.payload if a.payload else sys.stdin.read()
        handle_codex(json.loads(raw) if raw and raw.strip() else {})
    except Exception:  # noqa: BLE001 - a hook must never break the agent
        pass
    return 0


def cmd_init(_: argparse.Namespace) -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    target = HOME / ".env"
    if target.exists():
        print(f"already exists: {target}")
        return 0
    src = PACKAGE_ROOT / ".env.example"
    if not src.exists():
        src = PACKAGE_ROOT / "_env.example"
    shutil.copy(src, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    print(f"created {target} - fill it in, then run: agent-notifier status")
    return 0


def cmd_install_hooks(a: argparse.Namespace) -> int:
    path = Path.home() / ".claude" / "settings.json" if a.scope == "user" else Path.cwd() / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        print(f"{path} is not valid JSON - fix it first.")
        return 1
    hooks = data.setdefault("hooks", {})
    for event in ("UserPromptSubmit", "Stop", "Notification"):
        groups = hooks.setdefault(event, [])
        for g in groups:  # idempotent: drop any previous agent-notifier entry
            g["hooks"] = [h for h in g.get("hooks", []) if HOOK_MARK not in h.get("command", "")]
        groups[:] = [g for g in groups if g.get("hooks")]
        groups.append({"hooks": [{"type": "command", "command": _hook_command(), "timeout": 30}]})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"hooks installed in {path}")
    print("\nAdd the MCP server too (so Claude can choose when/where to ping you):")
    print(f'  claude mcp add agent-notifier -- "{sys.executable}" -m agent_notifier.server')
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agent-notifier", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("test").set_defaults(fn=cmd_test)
    sub.add_parser("telegram-id").set_defaults(fn=cmd_telegram_id)
    sub.add_parser("hook").set_defaults(fn=cmd_hook)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("send")
    s.add_argument("message")
    s.add_argument("--title", default="Claude")
    s.add_argument("--priority", default="normal", choices=["low", "normal", "high", "urgent"])
    s.add_argument("--channel", action="append", help="repeatable; default = routing rules")
    s.set_defaults(fn=cmd_send)
    i = sub.add_parser("inbox")
    i.add_argument("--wait", type=int, default=0)
    i.add_argument("--peek", action="store_true")
    i.set_defaults(fn=cmd_inbox)
    r = sub.add_parser("run", help="run a command and notify when it exits")
    r.add_argument("--title", default="")
    r.add_argument("--min-seconds", type=int, default=0, help="skip the ping if it finished faster (success only)")
    r.add_argument("command", nargs=argparse.REMAINDER)
    r.set_defaults(fn=cmd_run)
    cx = sub.add_parser("codex-notify", help="Codex CLI notify hook (JSON argument)")
    cx.add_argument("payload", nargs="?", default="")
    cx.set_defaults(fn=cmd_codex_notify)
    h = sub.add_parser("install-hooks")
    h.add_argument("--scope", choices=["user", "project"], default="user")
    h.set_defaults(fn=cmd_install_hooks)

    bi = sub.add_parser("bridge-id", help="print the chat id that messaged the bridge bot")
    bi.set_defaults(fn=cmd_bridge_id)

    ibs = sub.add_parser("install-bridge-service", help="print (do not run) service install steps")
    ibs.set_defaults(fn=cmd_install_bridge_service)

    dev = sub.add_parser("device", help="manage paired devices")
    dev_sub = dev.add_subparsers(dest="device_cmd", required=True)
    dp = dev_sub.add_parser("pair", help="pair this computer with your account")
    dp.add_argument("--name", default=None)
    dp.set_defaults(fn=cmd_device_pair)
    ds = dev_sub.add_parser("status", help="show pairing status")
    ds.set_defaults(fn=cmd_device_status)
    du = dev_sub.add_parser("unpair", help="remove pairing")
    du.set_defaults(fn=cmd_device_unpair)

    comp = sub.add_parser("companion", help="connect this computer to the hosted service")
    comp_sub = comp.add_subparsers(dest="companion_cmd", required=True)
    cps = comp_sub.add_parser("start", help="connect and send heartbeats")
    cps.add_argument("--supervise", action="store_true",
                     help="restart automatically after a crash (opt-in at login via install-autostart)")
    cps.set_defaults(fn=cmd_companion_start)
    cpa = comp_sub.add_parser("install-autostart", help="opt in: start the companion at Windows sign-in")
    cpa.set_defaults(fn=cmd_autostart_install)
    cpau = comp_sub.add_parser("uninstall-autostart", help="remove the login launcher")
    cpau.set_defaults(fn=cmd_autostart_uninstall)
    cpas = comp_sub.add_parser("autostart-status", help="show auto-start configuration")
    cpas.set_defaults(fn=cmd_autostart_status)
    cpst = comp_sub.add_parser("status", help="show companion status")
    cpst.set_defaults(fn=cmd_companion_status)
    cpstp = comp_sub.add_parser("stop", help="stop companion (run in its terminal)")
    cpstp.set_defaults(fn=cmd_companion_stop)

    li = sub.add_parser("listen", help="Telegram wake-up bridge: message -> headless agent -> reply")
    li.add_argument("--agent", choices=["claude", "codex", "opencode", "custom"], default=None)
    li.add_argument("--workdir", default=None)
    li.add_argument("--permissions", choices=["readonly", "edit", "full"], default=None)
    li.add_argument("--timeout", type=int, default=None)
    li.add_argument("--dry-run", action="store_true")
    li.add_argument("--i-understand-the-risk", action="store_true")
    li.set_defaults(fn=cmd_listen)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
