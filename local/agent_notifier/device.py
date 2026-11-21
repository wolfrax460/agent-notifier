"""Device pairing with the hosted Agent Notifier service."""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

import httpx

from .config import HOME, Settings

DEVICE_FILE = HOME / "device.json"
PAIRING_TIMEOUT = 300


def _cloud_url(settings) -> str:
    return settings.get("CLOUD_URL", "https://agentnotifier.duckdns.org").rstrip("/")


def _save_device(data: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    DEVICE_FILE.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(DEVICE_FILE, 0o600)
    except OSError:
        pass


def _load_device() -> dict | None:
    try:
        return json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cmd_device_pair(args) -> int:
    settings = Settings()
    cloud = _cloud_url(settings)
    verifier = secrets.token_urlsafe(32)
    device_name = getattr(args, "name", None) or os.uname().nodename if hasattr(os, "uname") else "device"
    try:
        import platform
        device_name = platform.node() or "device"
    except Exception:
        device_name = "device"
    print(f"Pairing device '{device_name}' with {cloud}")
    try:
        r = httpx.post(cloud + "/api/device-pairings/start", json={
            "device_name": device_name,
            "device_info": "agent-notifier companion",
            "verifier": verifier,
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"Failed to start pairing: {type(exc).__name__}")
        return 1
    code = data["code"]
    pid = data["pairing_id"]
    expires = data.get("expires_in", 300)
    print(f"\nPairing code: {code}")
    print(f"Open {cloud}/app and confirm this device, or visit:")
    print(f"  {cloud}/app?pair={code}")
    print(f"\nWaiting up to {expires}s for approval...")
    deadline = time.time() + expires
    while time.time() < deadline:
        try:
            r = httpx.post(cloud + "/api/device-pairings/poll", json={
                "pairing_id": pid, "verifier": verifier,
            }, timeout=15)
            res = r.json()
        except Exception:
            time.sleep(2)
            continue
        status = res.get("status")
        if status == "approved":
            dev_id = res.get("device_id")
            token = res.get("device_token")
            _save_device({"device_id": dev_id, "device_token": token, "cloud": cloud, "name": device_name, "paired_at": time.time()})
            print(f"\nPaired successfully. Device id: {dev_id}")
            if token:
                print("Device credential saved locally (mode 600).")
            return 0
        if status in ("rejected", "expired", "invalid_verifier", "not_found"):
            print(f"\nPairing failed: {status}")
            return 1
        time.sleep(2)
    print("\nPairing timed out.")
    return 1


def cmd_device_status(args) -> int:
    dev = _load_device()
    if not dev:
        print("No device paired. Run `agent-notifier device pair`.")
        return 1
    print(f"Device: {dev.get('name')}")
    print(f"Device id: {dev.get('device_id')}")
    print(f"Cloud: {dev.get('cloud')}")
    print(f"Paired at: {dev.get('paired_at')}")
    return 0


def cmd_device_unpair(args) -> int:
    dev = _load_device()
    if not dev:
        print("No device paired.")
        return 0
    cloud = dev.get("cloud", "")
    token = dev.get("device_token")
    if not cloud or not token:
        print("Missing cloud credential. Revoke this device in the web dashboard.")
        return 1
    try:
        r = httpx.post(
            cloud + "/api/companion/unpair",
            headers={"Authorization": "Bearer " + token},
            timeout=15,
        )
        if r.status_code not in (200, 401):
            print(f"Cloud revocation failed (HTTP {r.status_code}); local pairing retained.")
            return 1
    except httpx.HTTPError as exc:
        print(f"Cloud unavailable ({type(exc).__name__}); local pairing retained.")
        return 1
    try:
        DEVICE_FILE.unlink()
    except OSError as exc:
        print(f"Cloud access revoked, but local credential file could not be deleted ({type(exc).__name__}).")
        return 1
    print("Device unpaired; cloud access revoked or credential already invalid.")
    return 0
