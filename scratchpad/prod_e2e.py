"""End-to-end prod verification of the auth changes against hopper.farefin.com.

- Drives the public API over HTTPS.
- Retrieves verification/reset codes from the api-gateway pod (issue_code),
  since we can't read the mailbox. Real emails still send (checked via logs).
- Cleans up all test users (DB + Keycloak) in a finally block.
"""
import base64
import subprocess
import sys
import time

import httpx

BASE = "https://hopper.farefin.com/api"
REPO = "/home/anindya/Hopper"
NS = "hopper"

E_OK = "anindyakundu63+hopok@gmail.com"      # happy path
E_UNV = "anindyakundu63+hopunv@gmail.com"    # unverified/duplicate/wrong-code
PASS = "TestPass1234"      # Keycloak realm policy: min length 12
NEWPASS = "NewerPass5678"
EMAILS = [E_OK, E_UNV]

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + extra) if extra else ''}")


def vps(remote_cmd, timeout=90):
    p = subprocess.run(["python3", "scratchpad/vps.py", remote_cmd], cwd=REPO,
                       capture_output=True, text=True, timeout=timeout)
    return p.stdout + p.stderr


def pod_python(snippet):
    b64 = base64.b64encode(snippet.encode()).decode()
    cmd = f"echo {b64} | base64 -d | sudo -n k3s kubectl exec -i -n {NS} deploy/api-gateway -- python"
    return vps(cmd)


def get_code(email, purpose):
    snip = f"""
import asyncio
from app.core.database import async_session
from app.services import verification
async def go():
    async with async_session() as db:
        code = await verification.issue_code(db, "{email}", "{purpose}")
        await db.commit()
        print("CODE:"+code)
asyncio.run(go())
"""
    out = pod_python(snip)
    for line in out.splitlines():
        if line.startswith("CODE:"):
            return line[5:].strip()
    raise RuntimeError(f"could not get code: {out}")


def cleanup():
    print("\n=== cleanup ===")
    snip = f"""
import asyncio, httpx
from app.core.database import async_session
from app.services.keycloak_admin import keycloak_admin
from sqlalchemy import text
emails = {EMAILS!r}
async def go():
    for e in emails:
        try:
            ku = await keycloak_admin.get_user_by_email(e)
            if ku:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.delete(await keycloak_admin._admin_url("/users/"+ku["id"]),
                                       headers=await keycloak_admin._headers())
                    print("kc delete", e, r.status_code)
        except Exception as ex:
            print("kc err", e, ex)
        async with async_session() as db:
            await db.execute(text("delete from email_codes where email=:e"), {{"e": e}})
            await db.execute(text("delete from accounts where owner_id in (select id from users where email=:e)"), {{"e": e}})
            await db.execute(text("delete from users where email=:e"), {{"e": e}})
            await db.commit()
            print("db cleaned", e)
asyncio.run(go())
"""
    print(pod_python(snip))


def main():
    c = httpx.Client(base_url=BASE, timeout=30, follow_redirects=False)

    # pre-clean in case of a prior run
    cleanup()

    # 1. DOMAIN LIFT: signup with a @gmail.com (non-cs.du.ac.bd) -> 202, not 403
    r = c.post("/auth/signup", json={"name": "Hop OK", "email": E_OK, "password": PASS, "role": "student"})
    check("signup @gmail.com allowed (domain restriction lifted)", r.status_code == 202, f"status={r.status_code}")
    check("signup returns verification_required + no session", r.json().get("status") == "verification_required" and "session_token" not in r.cookies)

    # 2. EMAIL DELIVERY: no send failure / DEV fallback / TLS error (a failed
    #    send logs at ERROR and would appear; the success line is INFO and is
    #    filtered by the app's WARNING root logger, so absence-of-failure is the
    #    reliable signal here — corroborated by the direct relay send test).
    time.sleep(3)
    logs = vps(f"sudo -n k3s kubectl logs deploy/api-gateway -n {NS} --since=90s 2>&1 | grep -iE 'email (send failed|DEV)|ssl|certificate|smtp.*error' | tail -5")
    check("prod email path healthy (no send failure / DEV fallback / TLS error)", logs.strip() == "", logs.strip() or "clean")

    # 3. WRONG verify code -> 400
    r = c.post("/auth/verify-email", json={"email": E_OK, "code": "000001"})
    check("wrong verify code -> 400", r.status_code == 400, f"status={r.status_code}")

    # 4. VERIFY happy path (fetch a fresh code from the pod)
    code = get_code(E_OK, "verify_email")
    r = c.post("/auth/verify-email", json={"email": E_OK, "code": code})
    check("correct verify code -> 200", r.status_code == 200, f"status={r.status_code}")

    # 5. LOGIN after verify -> 200 + session cookie
    r = c.post("/auth/login", json={"email": E_OK, "password": PASS})
    check("login after verify -> 200 + session", r.status_code == 200 and "session_token" in r.cookies, f"status={r.status_code}")

    # 6. UNVERIFIED login blocked: new signup, login without verifying -> 403
    r = c.post("/auth/signup", json={"name": "Hop Unv", "email": E_UNV, "password": PASS, "role": "student"})
    check("second signup -> 202", r.status_code == 202)
    r = c.post("/auth/login", json={"email": E_UNV, "password": PASS})
    check("login while unverified -> 403", r.status_code == 403, f"status={r.status_code}")

    # 7. DUPLICATE signup -> 409
    r = c.post("/auth/signup", json={"name": "Dup", "email": E_UNV, "password": PASS, "role": "student"})
    check("duplicate signup -> 409", r.status_code == 409, f"status={r.status_code}")

    # 8. FORGOT + RESET on the verified account
    r = c.post("/auth/forgot-password", json={"email": E_OK})
    check("forgot-password -> 200", r.status_code == 200)
    rcode = get_code(E_OK, "password_reset")
    r = c.post("/auth/reset-password", json={"email": E_OK, "code": rcode, "password": NEWPASS})
    check("reset-password -> 200", r.status_code == 200, f"status={r.status_code}")
    r = c.post("/auth/login", json={"email": E_OK, "password": NEWPASS})
    check("login with NEW password -> 200", r.status_code == 200 and "session_token" in r.cookies, f"status={r.status_code}")
    r = c.post("/auth/login", json={"email": E_OK, "password": PASS})
    check("login with OLD password -> 401", r.status_code == 401, f"status={r.status_code}")

    # 9. FORGOT unknown user -> 200 (no enumeration)
    r = c.post("/auth/forgot-password", json={"email": "definitelynobody+x@gmail.com"})
    check("forgot unknown user -> 200 (no enumeration)", r.status_code == 200, f"status={r.status_code}")

    ok = all(p for _, p in results)
    print(f"\n{'='*56}\n{'ALL PASS' if ok else 'SOME FAILED'}: {sum(p for _,p in results)}/{len(results)}")
    return ok


if __name__ == "__main__":
    ok = False
    try:
        ok = main()
    finally:
        cleanup()
    sys.exit(0 if ok else 1)
