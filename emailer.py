"""Gmail SMTP sender (HTML + plain-text). Honours DRY_RUN.

`send()` is for one-off emails. `send_bulk()` reuses a single authenticated
connection and respects a daily cap — use it for follow-up runs and manual
blasts so we don't reconnect (and risk Gmail throttling) per message.
"""
from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Callable, Iterable

import config


def _log(msg: str) -> None:
    """Print without ever crashing on a non-UTF-8 console (e.g. Windows cp1252)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _build(to_email: str, subject: str, html: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((config.EMAIL_FROM_NAME, config.EMAIL_FROM))
    msg["To"] = to_email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _connect() -> smtplib.SMTP:
    """Open and authenticate an SMTP connection. Caller must close it."""
    if config.SMTP_PORT == 465:
        ctx = ssl.create_default_context()
        s: smtplib.SMTP = smtplib.SMTP_SSL(
            config.SMTP_HOST, config.SMTP_PORT, context=ctx, timeout=30
        )
    else:
        s = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
        s.starttls(context=ssl.create_default_context())
    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
    return s


def send(to_email: str, subject: str, html: str, text: str) -> bool:
    """Send one email. In DRY_RUN, prints a summary instead of sending.

    Returns True if sent (or dry-run "sent"), False on failure.
    """
    if config.DRY_RUN:
        _log(f"   [DRY_RUN] would email {to_email}  ·  {subject}")
        return True

    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        _log("   ! SMTP_USER / SMTP_PASSWORD not configured — cannot send.")
        return False

    try:
        with _connect() as s:
            s.send_message(_build(to_email, subject, html, text))
        _log(f"   ✓ sent → {to_email}  ·  {subject}")
        return True
    except Exception as exc:  # noqa: BLE001 — surface any SMTP error to the operator
        _log(f"   ! failed → {to_email}: {exc}")
        return False


def send_bulk(
    jobs: Iterable[dict[str, Any]],
    cap: int | None = None,
    on_sent: Callable[[dict[str, Any]], None] | None = None,
    throttle_seconds: float = 0.3,
) -> tuple[int, int]:
    """Send many emails over one connection.

    Each job is a dict with keys: to, subject, html, text (plus any metadata the
    caller wants back in on_sent). `cap` limits how many to actually send this
    run (e.g. the remaining daily budget). `on_sent(job)` fires after each
    successful send so the caller can persist state.

    Returns (sent_count, failed_count).
    """
    jobs = list(jobs)
    if cap is not None:
        jobs = jobs[: max(cap, 0)]

    if not jobs:
        return 0, 0

    if config.DRY_RUN:
        for job in jobs:
            _log(f"   [DRY_RUN] would email {job['to']}  ·  {job['subject']}")
            if on_sent:
                on_sent(job)  # let caller exercise its bookkeeping in dry runs too
        return len(jobs), 0

    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        _log("   ! SMTP_USER / SMTP_PASSWORD not configured — cannot send.")
        return 0, len(jobs)

    sent = failed = 0
    try:
        with _connect() as s:
            for job in jobs:
                try:
                    s.send_message(_build(job["to"], job["subject"], job["html"], job["text"]))
                    _log(f"   ✓ sent → {job['to']}  ·  {job['subject']}")
                    sent += 1
                    if on_sent:
                        on_sent(job)
                    if throttle_seconds:
                        time.sleep(throttle_seconds)
                except Exception as exc:  # noqa: BLE001
                    _log(f"   ! failed → {job['to']}: {exc}")
                    failed += 1
    except Exception as exc:  # noqa: BLE001 — connection/login failure aborts the run
        _log(f"   ! SMTP connection failed: {exc}")
        failed += len(jobs) - sent
    return sent, failed
