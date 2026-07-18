#!/usr/bin/env python3
"""In-VM first-boot provisioner for Hopper's Smart Sandbox generator.

Runs once, early in the VM's life (started by supervisord). It fetches the
``provision.sh`` the Smart Sandbox agent generated for this VM and runs it, so
the workspace comes up pre-loaded with the exact dependencies, frameworks, and
VS Code extensions the user's project needs.

Config comes from the environment the orchestrator injects at pod creation
(the same HOPPER_* vars the idle agent uses):

  HOPPER_POD_ID     pod UUID (matches the /pods/{id} URL)
  HOPPER_API_URL    e.g. http://api-gateway:8000
  HOPPER_POD_TOKEN  per-pod HMAC bearer for the sandbox endpoints
  HOPPER_PROVISION  "1" when this VM was created via the sandbox generator

Idempotent + one-shot: a marker file at /workspace/.hopper-provisioned means the
script already ran, so supervisord restarts (or pod restarts with a persistent
workspace PVC) never re-run it. Fail-safe: any error is logged and reported but
never crashes the VM — the box stays usable even if provisioning fails.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

POD_ID = os.environ.get("HOPPER_POD_ID", "")
API = os.environ.get("HOPPER_API_URL", "").rstrip("/")
TOKEN = os.environ.get("HOPPER_POD_TOKEN", "")
PROVISION = os.environ.get("HOPPER_PROVISION", "") == "1"

MARKER = "/workspace/.hopper-provisioned"
SCRIPT_PATH = "/workspace/.hopper-provision.sh"
LOG_PATH = "/var/log/supervisor/hopper-provision.log"


def _log(msg: str) -> None:
    print(f"hopper-provisioner: {msg}", flush=True)


def _report(status: str) -> None:
    """Best-effort status ping. Never raises."""
    try:
        req = urllib.request.Request(
            f"{API}/sandbox/pods/{POD_ID}/provision-status",
            data=json.dumps({"status": status}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Pod-Token": TOKEN},
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:  # noqa: BLE001 - status reporting is advisory only
        _log(f"status report ({status}) failed: {exc}")


def _fetch_script() -> str | None:
    req = urllib.request.Request(
        f"{API}/sandbox/pods/{POD_ID}/provision-script",
        headers={"X-Pod-Token": TOKEN},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _log("no provisioning script for this VM; nothing to do")
        else:
            _log(f"fetch failed: HTTP {exc.code}")
    except urllib.error.URLError as exc:
        _log(f"gateway unreachable: {exc}")
    return None


def main() -> None:
    if os.path.exists(MARKER):
        _log("already provisioned; skipping")
        return
    if not PROVISION:
        _log("not a sandbox VM (HOPPER_PROVISION!=1); skipping")
        return
    if not (POD_ID and API and TOKEN):
        _log("HOPPER_POD_ID/API_URL/POD_TOKEN unset; cannot provision")
        return

    os.makedirs("/workspace", exist_ok=True)
    script = _fetch_script()
    if script is None:
        return

    with open(SCRIPT_PATH, "w") as f:
        f.write(script)
    os.chmod(SCRIPT_PATH, 0o755)

    _log("running provision script...")
    _report("running")
    with open(LOG_PATH, "w") as logf:
        proc = subprocess.run(
            ["/bin/bash", SCRIPT_PATH],
            stdout=logf,
            stderr=subprocess.STDOUT,
            check=False,
        )

    if proc.returncode == 0:
        # Only mark done on success, so a transient failure can be retried on the
        # next boot rather than being permanently skipped by the marker.
        with open(MARKER, "w") as f:
            f.write("ok\n")
        _log("provisioning complete")
        _report("done")
    else:
        _log(f"provision script exited {proc.returncode}; see {LOG_PATH}")
        _report("failed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never take the VM down
        _log(f"unexpected error: {exc}")
        sys.exit(0)
