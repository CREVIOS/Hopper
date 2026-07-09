#!/usr/bin/env python3
"""VPS SSH helper for Hopper prod ops. Usage: python vps.py '<remote command>'
Reads command from argv or stdin. kubectl on the VPS = `sudo -n k3s kubectl`."""
import sys
import paramiko

HOST = "20.193.138.159"
USER = "vmuser"
PW = "DENynX3438cf%i"


def run(cmd: str, timeout: int = 180) -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    c.close()
    return rc


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    sys.exit(run(cmd))
