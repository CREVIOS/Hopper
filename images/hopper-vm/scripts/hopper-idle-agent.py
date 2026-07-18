#!/usr/bin/env python3
"""In-VM activity reporter for Hopper's idle-detection agent.

Runs inside every student VM (started by supervisord). Two jobs:

  1. Report local activity to the API gateway so a pending idle warning is
     cancelled while the student is actually using the machine. Activity =
     any ESTABLISHED SSH session, any ESTABLISHED code-server websocket, or a
     fresh ``/tmp/active`` marker (touched by the shell hook on every command).

  2. When the gateway's heartbeat response says the VM is ``warned``, broadcast
     the warning to every terminal with ``wall`` so the student sees it.

Config comes from the environment the orchestrator injects at pod creation:

  HOPPER_POD_ID              pod UUID (matches the /pods/{id} URL)
  HOPPER_API_URL             e.g. http://api-gateway:8000
  HOPPER_POD_TOKEN           per-pod HMAC bearer for POST /pods/{id}/heartbeat
  HOPPER_HEARTBEAT_INTERVAL  seconds between beats (default 60)
  HOPPER_CODESERVER_PORT     code-server local port (default 8080)

Fail-safe: this agent never terminates anything itself. If the gateway is
unreachable it simply does nothing — the VM keeps running.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

POD_ID = os.environ.get("HOPPER_POD_ID", "")
API = os.environ.get("HOPPER_API_URL", "").rstrip("/")
TOKEN = os.environ.get("HOPPER_POD_TOKEN", "")
INTERVAL = int(os.environ.get("HOPPER_HEARTBEAT_INTERVAL", "60") or "60")
CODE_PORT = int(os.environ.get("HOPPER_CODESERVER_PORT", "8080") or "8080")
ACTIVE_FILE = "/tmp/active"
ACTIVE_WINDOW = max(INTERVAL * 2, 120)


def _established_count(local_port: int) -> int:
    """Count ESTABLISHED (state 01) TCP sockets whose LOCAL port == local_port,
    by scanning /proc/net/tcp{,6}. Covers inbound SSH and code-server WS."""
    count = 0
    hexport = f"{local_port:04X}"
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as f:
                next(f, None)  # header
                for line in f:
                    parts = line.split()
                    if len(parts) < 4 or parts[3] != "01":
                        continue
                    if parts[1].rsplit(":", 1)[-1].upper() == hexport:
                        count += 1
        except (FileNotFoundError, OSError):
            pass
    return count


def _active_marker_fresh() -> bool:
    try:
        return (time.time() - os.path.getmtime(ACTIVE_FILE)) <= ACTIVE_WINDOW
    except OSError:
        return False


def _broadcast(message: str) -> None:
    try:
        subprocess.run(["wall", "-n"], input=message.encode(), timeout=5, check=False)
        return
    except Exception:
        pass
    # Fallback: write straight to each pseudo-terminal.
    try:
        for pts in os.listdir("/dev/pts"):
            if pts.isdigit():
                try:
                    with open(f"/dev/pts/{pts}", "w") as term:
                        term.write("\r\n" + message + "\r\n")
                except OSError:
                    pass
    except OSError:
        pass


def _heartbeat(active: bool) -> dict:
    body = json.dumps({"active": active}).encode()
    req = urllib.request.Request(
        f"{API}/pods/{POD_ID}/heartbeat",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Pod-Token": TOKEN},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode() or "{}")


def main() -> None:
    if not (POD_ID and API and TOKEN):
        print("hopper-idle-agent: HOPPER_POD_ID/API_URL/POD_TOKEN unset; idle reporting disabled", flush=True)
        return
    print(f"hopper-idle-agent: reporting activity for {POD_ID} every {INTERVAL}s", flush=True)
    while True:
        try:
            active = (
                _established_count(22) > 0
                or _established_count(CODE_PORT) > 0
                or _active_marker_fresh()
            )
            resp = _heartbeat(active)
            if (resp or {}).get("status") == "warned":
                msg = (resp.get("message") or "").strip() or (
                    "SYSTEM WARNING: this idle VM will auto-terminate soon. "
                    "Type any command or run: touch /tmp/active"
                )
                _broadcast(msg)
        except urllib.error.URLError:
            # Gateway unreachable — stay quiet, never self-terminate.
            pass
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            print(f"hopper-idle-agent: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
