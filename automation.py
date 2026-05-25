"""Stage-aware email automation.

Rules (the "wait" logic):
  • We only have an email address from step 5 onward, so steps 1–4 never email
    — we simply wait for the customer to progress.
  • For nurture stages (details / plan / payment) we only email once the
    customer has been IDLE at that stage for WAIT_MINUTES. If they're still
    moving step→step, we leave them alone.
  • 'welcome' (converted) sends right away.
  • Each (journey, stage) is emailed at most once (tracked in state.sqlite3).
  • Journeys older than MAX_AGE_DAYS are skipped.
"""
from __future__ import annotations

import time
from typing import Any

import config
import emailer
import stages
import state
import supabase_client as sb
import templates


def _due(session: dict[str, Any]) -> str | None:
    """Return the email stage to send now, or None."""
    stage = stages.email_stage(session)
    if stage is None:
        return None  # too early (steps 1–4) — wait

    if not stages.lead_email(session):
        return None  # no address yet

    if state.already_sent(session["id"], stage):
        return None  # already emailed this stage

    # Skip very old journeys.
    age = stages.minutes_since(session.get("started_at"))
    if age is not None and age > config.MAX_AGE_DAYS * 24 * 60:
        return None

    if stage == "welcome":
        return stage  # send immediately on conversion

    # Nurture stages: only when idle long enough (the "wait").
    idle = stages.minutes_since(session.get("last_step_at"))
    if idle is None or idle < config.WAIT_MINUTES:
        return None

    return stage


def run_once(verbose: bool = True) -> int:
    sessions = sb.get_funnel_sessions()
    sent = 0
    for s in sessions:
        stage = _due(s)
        if not stage:
            continue
        to = stages.lead_email(s)
        subject, html, text = templates.render(stage, s)
        if emailer.send(to, subject, html, text):
            # Don't persist "sent" during a dry run, or testing would block the
            # real email later.
            if not config.DRY_RUN:
                state.mark_sent(s["id"], stage, to)
            sent += 1
    if verbose:
        mode = "DRY RUN" if config.DRY_RUN else "LIVE"
        print(f"\n[{mode}] processed {len(sessions)} journeys · {sent} email(s) this pass.\n")
    return sent


def run_loop(interval_seconds: int = 300) -> None:
    print(
        f"Email automation running every {interval_seconds}s "
        f"(wait={config.WAIT_MINUTES}m, dry_run={config.DRY_RUN}). Ctrl+C to stop."
    )
    try:
        while True:
            run_once()
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
