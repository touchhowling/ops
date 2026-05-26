"""Resend HTTPS email sender — works on hosts that block SMTP (e.g. Render free).

Set RESEND_API_KEY (the API key from https://resend.com) and EMAIL_FROM (an
address on a domain you've verified in Resend, or the sandbox
'onboarding@resend.dev' for first-time testing).
"""
from __future__ import annotations

import time
from email.utils import formataddr
from typing import Any, Callable, Iterable

import requests

import config

API_URL = "https://api.resend.com/emails"
TIMEOUT = 30


def _log(msg: str) -> None:
    """Print without ever crashing on a non-UTF-8 console; flushes immediately
    so hosts that buffer stdout (Render etc.) show it live."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _session() -> requests.Session | None:
    if not config.RESEND_API_KEY:
        return None
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        }
    )
    return s


def _send(session: requests.Session, to_email: str, subject: str, html: str, text: str) -> tuple[bool, str]:
    """Send one email via Resend. Returns (ok, error_message)."""
    body = {
        "from": formataddr((config.EMAIL_FROM_NAME, config.EMAIL_FROM)),
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    try:
        resp = session.post(API_URL, json=body, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — network errors etc.
        return False, str(exc)
    if resp.status_code in (200, 201, 202):
        return True, ""
    # Surface Resend's structured error if there is one
    try:
        j = resp.json()
        msg = j.get("message") or j.get("error") or resp.text[:200]
    except Exception:  # noqa: BLE001
        msg = resp.text[:200]
    return False, f"{resp.status_code}: {msg}"


def send(to_email: str, subject: str, html: str, text: str) -> bool:
    """Send one email. In DRY_RUN, prints a summary instead of sending.
    Returns True if sent (or dry-run 'sent'), False on failure."""
    if config.DRY_RUN:
        _log(f"   [DRY_RUN] would email {to_email}  ·  {subject}")
        return True

    session = _session()
    if session is None:
        _log("   ! RESEND_API_KEY not configured — cannot send.")
        return False

    ok, err = _send(session, to_email, subject, html, text)
    if ok:
        _log(f"   ✓ sent → {to_email}  ·  {subject}")
        return True
    _log(f"   ! failed → {to_email}: {err}")
    return False


def send_bulk(
    jobs: Iterable[dict[str, Any]],
    cap: int | None = None,
    on_sent: Callable[[dict[str, Any]], None] | None = None,
    throttle_seconds: float = 0.3,
) -> tuple[int, int, str]:
    """Send many emails over one HTTPS session.

    Each job is a dict with keys: to, subject, html, text (plus any metadata).
    `cap` limits how many to actually send this run (e.g. remaining daily
    budget). `on_sent(job)` fires after each successful send so the caller can
    persist state.

    Returns (sent_count, failed_count, first_error). first_error is "" on
    success — otherwise the first error message captured, so the UI can show
    why nothing went out without needing to read server logs."""
    jobs = list(jobs)
    if cap is not None:
        jobs = jobs[: max(cap, 0)]

    if not jobs:
        return 0, 0, ""

    if config.DRY_RUN:
        for job in jobs:
            _log(f"   [DRY_RUN] would email {job['to']}  ·  {job['subject']}")
            if on_sent:
                on_sent(job)  # let caller exercise its bookkeeping in dry runs too
        return len(jobs), 0, ""

    session = _session()
    if session is None:
        msg = "RESEND_API_KEY not configured"
        _log(f"   ! {msg} — cannot send.")
        return 0, len(jobs), msg

    sent = failed = 0
    first_error = ""
    for job in jobs:
        ok, err = _send(session, job["to"], job["subject"], job["html"], job["text"])
        if ok:
            _log(f"   ✓ sent → {job['to']}  ·  {job['subject']}")
            sent += 1
            if on_sent:
                on_sent(job)
            if throttle_seconds:
                time.sleep(throttle_seconds)
        else:
            _log(f"   ! failed → {job['to']}: {err}")
            if not first_error:
                first_error = err
            failed += 1
    return sent, failed, first_error
