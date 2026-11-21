"""Local companion: outbound connection to the hosted backend."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx

from . import device as devmod
from . import agents as agent_registry
from . import recovery
from . import codex_models
from . import local_models
from .windows_process import hidden_kwargs
from . import runtime
from . import codex_workspace
from .config import Settings

HEARTBEAT_INTERVAL = 30
JOBS_POLL_INTERVAL = 5
MODEL_REPORT_INTERVAL = 300
JOB_TIMEOUT = 900
JOB_PROGRESS_INTERVAL = 15  # liveness only; no stdout/stderr streaming
# Fixed command per supported agent: the server can never choose an arbitrary binary,
# and the prompt is passed as a single argv element (never through a shell).
AGENT_COMMANDS = {
    "claude": lambda prompt: ["claude", "-p", prompt],
    "codex": lambda prompt: ["codex", "exec", prompt],
    "opencode": lambda prompt: ["opencode", "run", prompt],
}


def _cloud_url(settings) -> str:
    return settings.get("CLOUD_URL", "https://agentnotifier.duckdns.org").rstrip("/")


def _companion_loop(settings) -> int:
    dev = devmod._load_device()
    if not dev or not dev.get("device_token"):
        print("No paired device. Run `agent-notifier device pair` first.")
        return 1
    cloud = dev.get("cloud") or _cloud_url(settings)
    token = dev["device_token"]
    headers = {"Authorization": "Bearer " + token}
    print(f"Companion connecting to {cloud} as device {dev['device_id']}")
    backoff = 1
    while True:
        try:
            # SSE stream
            with httpx.stream("GET", cloud + "/api/companion/stream", headers=headers, timeout=None) as resp:
                if resp.status_code == 401:
                    print("Device revoked or invalid. Re-pair.")
                    return 1
                resp.raise_for_status()
                # Read-only agent inventory. Never send executable paths, command templates
                # or private workspace information to the hosted service.
                def report_agents_and_models():
                    reports = [
                        {"name": a["name"], "version": a["version"], "installed": a["installed"]}
                        for a in agent_registry.detect(settings)
                        if a.get("name") in ("claude", "codex", "opencode")
                    ]
                    installed = {a["name"] for a in reports if a["installed"]}
                    catalogs = local_models.all_installed(installed)
                    httpx.post(cloud + "/api/companion/agents", headers=headers,
                               json={"agents": reports, "agent_models": catalogs,
                                     "codex_models": catalogs.get("codex", [])}, timeout=15)
                try:
                    report_agents_and_models()
                except (httpx.HTTPError, OSError):
                    pass
                backoff = 1
                # Recovery is never permission to restart a claimed job.
                _reconcile_saved_jobs(cloud, headers, dev["device_id"])
                last_hb = 0
                last_poll = 0
                last_model_report = time.time()
                for line in resp.iter_lines():
                    now = time.time()
                    if now - last_hb >= HEARTBEAT_INTERVAL:
                        try:
                            hb = httpx.post(cloud + "/api/companion/heartbeat", headers=headers, timeout=10)
                            if hb.status_code == 200 and hb.json().get("refresh_models"):
                                report_agents_and_models()
                                last_model_report = time.time()
                        except Exception:
                            pass
                        last_hb = now
                    if now - last_model_report >= MODEL_REPORT_INTERVAL:
                        try:
                            report_agents_and_models()
                            last_model_report = now
                        except (httpx.HTTPError, OSError):
                            pass
                    if now - last_poll >= JOBS_POLL_INTERVAL:
                        last_poll = now
                        _poll_and_run_job(cloud, headers, dev["device_id"])
                    # process SSE events (none actionable)
        except KeyboardInterrupt:
            print("Stopping companion.")
            return 0
        except Exception as exc:
            print(f"Connection lost ({type(exc).__name__}). Reconnecting in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


def cmd_companion_start(args) -> int:
    """Foreground companion, optionally supervised so crashes restart it.

    Exactly one companion may run per user account: two processes would poll
    the same jobs and could execute the same approved task twice.
    """
    settings = Settings()
    with runtime.instance_lock() as primary:
        if not primary:
            state = runtime.status()
            detail = f" (pid {state['pid']})" if state["pid"] else ""
            print(f"A companion is already running{detail}. Not starting a second one.")
            print("Use `agent-notifier companion status` to inspect it.")
            return 1
        if getattr(args, "supervise", False):
            from .autostart import supervise

            print("Companion supervisor active; Ctrl+C stops it.")
            return supervise(lambda: _companion_loop(settings))
        return _companion_loop(settings)


def launch_argv(agent: str, prompt: str, model_id: str | None = None, *, skip_codex_git_check: bool = False) -> list[str] | None:
    """Resolve the allowlisted adapter to an absolute executable path.

    Windows resolves `opencode` to a `.CMD` shim that CreateProcess does not
    find by bare name, so launching the name alone reports a false
    "not installed" even when the agent works.
    """
    build = AGENT_COMMANDS.get(agent)
    if not build:
        return None
    argv = list(build(prompt))
    resolved = agent_registry._resolve(argv[0])
    if resolved:
        argv[0] = resolved
    if model_id:
        if not local_models.MODEL_ID.fullmatch(model_id):
            return None
        if model_id not in {m["id"] for m in local_models.discover(agent)}:
            return None
        if agent == "codex":
            argv = [argv[0], "exec", "--model", model_id, prompt]
        elif agent == "claude":
            argv = [argv[0], "--model", model_id, "-p", prompt]
        elif agent == "opencode":
            argv = [argv[0], "run", "--model", model_id, prompt]
        else:
            return None
    if agent == "codex" and skip_codex_git_check:
        argv.insert(2, "--skip-git-repo-check")
    return argv


def _allow_codex_no_repo(settings: Settings) -> bool:
    """Only local owner settings may disable the repo check, never cloud jobs."""
    return (settings.get("COMPANION_CODEX_SKIP_GIT_REPO_CHECK").lower()
            in ("1", "yes", "true", "on") and bool(runtime.authorized_roots(settings)))


def _clean_cli_output(value: str) -> str:
    """Strip ANSI color codes and control characters from chat text."""
    value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", value)
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return "".join(c for c in value if c in "\n\t" or ord(c) >= 32).strip()


def _send_job_progress(cloud: str, headers: dict, job_id: str, counter: int) -> bool:
    """Return an authenticated owner's stop request, otherwise keep running."""
    if not job_id:
        return False
    try:
        response = httpx.post(
            cloud + "/api/companion/jobs/" + job_id + "/progress",
            headers=headers, json={"event_id": f"heartbeat_{counter:08d}"}, timeout=5,
        )
        requested=response.status_code == 200 and bool(response.json().get("stop_requested"))
        if requested:
            try:
                httpx.post(cloud + "/api/companion/jobs/" + job_id + "/stop-ack",
                           headers=headers,timeout=5)
            except httpx.HTTPError:
                pass
        return requested
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return False


def _stop_owned_process(proc: subprocess.Popen) -> None:
    """Terminate only the process launched for this approved job."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()


def _reconcile_saved_jobs(cloud: str, headers: dict, device_id: str) -> bool:
    """Retry delivery only. Unknown execution outcomes are not retried."""
    for entry in recovery.records("result", device_id):
        jid=entry["job_id"]
        try:
            r=httpx.post(cloud+"/api/companion/jobs/result",
                         headers=headers,json=entry["payload"],timeout=20)
            receipt=r.json() if r.status_code==200 else None
            if r.status_code==200 and isinstance(receipt,dict) and receipt.get("ok") is True:
                recovery.discard("result",jid)
                recovery.discard("claim",jid)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, OSError):
            pass
    for entry in recovery.records("claim",device_id):
        jid=entry["job_id"]
        if recovery.exists("result",jid):
            continue
        try:
            r=httpx.post(cloud+"/api/companion/jobs/"+jid+"/interrupted",
                         headers=headers,timeout=15)
            if r.status_code==200 and r.json().get("state") in ("running","terminal"):
                recovery.discard("claim",jid)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, OSError):
            pass
    # Unknown, corrupt or other-device records block new job claims.
    return not recovery.has_unresolved()


def _run_job(cloud: str, headers: dict, job: dict, device_id: str = "local_test") -> None:
    """Run one approved agent process; persist before posting result."""
    agent = str(job.get("agent") or "")
    prompt = str(job.get("prompt") or "")
    job_id = str(job.get("id") or "")
    payload: dict = {"job_id": job_id}
    if not job_id or recovery.has_unresolved():
        return
    # Resolve the workspace before claiming, so an unusable configuration never
    # leaves an orphaned claim blocking the queue.
    try:
        workdir = runtime.authorized_workdir(Settings())
    except (ValueError, OSError):
        print("No authorized working directory is configured; refusing this job.")
        return
    try:
        recovery.save_claim(job_id,device_id)
    except (OSError,ValueError):
        print("Unable to persist claim; refusing to start this job.")
        return
    model_id = job.get("model_id") or None
    settings = Settings()
    non_git_codex = agent == "codex" and not codex_workspace.is_git_worktree(workdir)
    allow_no_repo = non_git_codex and _allow_codex_no_repo(settings)
    argv = launch_argv(agent, prompt, model_id, skip_codex_git_check=allow_no_repo) if prompt else None
    if non_git_codex and not allow_no_repo:
        payload["error"] = (
            "Codex needs a trusted Git workspace. Set COMPANION_WORKDIRS in "
            "~/.agent-notifier/.env to an existing Git repository and restart "
            "the companion. For a dedicated non-repository workspace, the "
            "owner can explicitly configure COMPANION_CODEX_SKIP_GIT_REPO_CHECK=1 "
            "together with COMPANION_WORKDIRS.")
    elif not argv:
        payload["error"] = ("Selected agent model is unavailable on this computer"
                            if model_id else f"unsupported agent: {agent or 'none'}")
    else:
        proc = None
        try:
            proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                cwd=str(workdir), stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", **hidden_kwargs(),
            )
            deadline = time.monotonic() + JOB_TIMEOUT
            counter = 0
            requested = _send_job_progress(cloud, headers, job_id, counter)
            while True:
                if requested:
                    _stop_owned_process(proc)
                    payload["exit_code"] = proc.returncode
                    payload["error"] = "Stopped by owner"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _stop_owned_process(proc)
                    payload["exit_code"] = proc.returncode
                    payload["error"] = f"timed out after {JOB_TIMEOUT}s"
                    break
                try:
                    stdout, stderr = proc.communicate(
                        timeout=min(remaining, JOB_PROGRESS_INTERVAL),
                    )
                except subprocess.TimeoutExpired:
                    counter += 1
                    requested = _send_job_progress(cloud, headers, job_id, counter)
                    continue
                payload["exit_code"] = proc.returncode
                payload["result"] = _clean_cli_output(stdout or "")[-20000:]
                if proc.returncode != 0:
                    payload["error"] = (_clean_cli_output(stderr or "") or f"exit {proc.returncode}")[:2000]
                break
        except FileNotFoundError:
            payload["error"] = f"{agent} is not installed on this computer"
        except Exception as exc:
            payload["error"] = type(exc).__name__
        finally:
            if proc is not None and proc.poll() is None:
                _stop_owned_process(proc)
    try:
        recovery.save_result(job_id,device_id,payload)
    except (OSError,ValueError):
        print("Result could not be saved; this job requires operator investigation.")
        return
    _reconcile_saved_jobs(cloud,headers,device_id)


def _poll_and_run_job(cloud: str, headers: dict, device_id: str = "local_test") -> bool:
    """Never claim new work with undelivered results or orphaned claims."""
    if not _reconcile_saved_jobs(cloud,headers,device_id):
        return False
    try:
        resp = httpx.post(cloud + "/api/companion/jobs/poll",
                          headers={**headers, "X-AN-Model-Selection": "1"}, timeout=15)
        if resp.status_code != 200:
            return False
        job = (resp.json() or {}).get("job")
    except (httpx.HTTPError, ValueError):
        return False
    if not job:
        return False
    print(f"Running {job.get('agent')} job {job.get('id')}...")
    _run_job(cloud, headers, job, device_id=device_id)
    return True


def cmd_companion_status(args) -> int:
    from .autostart import status as autostart_status

    dev = devmod._load_device()
    auto = autostart_status()
    print(f"Auto-start: {'installed' if auto['installed'] else 'not installed'} "
          f"({auto['path']})")
    if not dev:
        print("No device paired. Run `agent-notifier device pair` first.")
        return 1
    print(runtime.describe(Settings()))
    print(f"Device: {dev.get('name')} ({dev.get('device_id')})")
    print(f"Cloud: {dev.get('cloud')}")
    print("Status: unknown (heartbeat is tracked by the backend, not locally)")
    try:
        detected = [a["name"] for a in agent_registry.detect(Settings()) if a.get("installed")]
    except Exception:
        detected = []
    print(f"Installed agents: {', '.join(detected) if detected else 'none detected'}")
    print("Follow-up jobs start a new agent process with the saved conversation "
          "context; no agent CLI is resumed natively.")
    print("A sleeping or powered-off computer cannot be woken by the cloud.")
    return 0


def cmd_companion_stop(args) -> int:
    print("Stop the companion process (Ctrl+C) to disconnect.")
    return 0