"""Built-in daily scheduler for the follow-up pass.

Runs inside the always-on web app, so follow-ups send automatically with no
external cron. It fires once a day at FOLLOWUP_HOUR (interpreted in the timezone
given by SCHEDULER_OFFSET_MINUTES, default IST). Sends are idempotent — an extra
run never double-emails — so this is safe even if the process restarts.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import config
import state

_started = False
_OFFSET = timedelta(minutes=config.SCHEDULER_OFFSET_MINUTES)


def next_run(after: datetime | None = None) -> datetime:
    """Next FOLLOWUP_HOUR (local) as an aware UTC datetime."""
    now_utc = after or datetime.now(timezone.utc)
    local = now_utc + _OFFSET
    target = local.replace(hour=config.FOLLOWUP_HOUR, minute=0, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=1)
    return target - _OFFSET  # back to UTC


def _loop() -> None:
    state.set_meta("next_followup_run", next_run().isoformat())
    while True:
        wait = (next_run() - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            time.sleep(min(wait, 3600))  # wake hourly so clock changes are picked up
            continue
        try:
            import sequences  # imported lazily so a Supabase outage can't kill startup

            sent = sequences.run_once(verbose=False)
            state.set_meta("last_followup_run", datetime.now(timezone.utc).isoformat())
            state.set_meta("last_followup_count", str(sent))
        except Exception as exc:  # noqa: BLE001 — never let the thread die
            state.set_meta("last_followup_error", f"{datetime.now(timezone.utc).isoformat()} {exc}")
        # Schedule the next one (tomorrow) and sleep past the current slot.
        nxt = next_run(datetime.now(timezone.utc) + timedelta(minutes=1))
        state.set_meta("next_followup_run", nxt.isoformat())
        time.sleep(120)


def start() -> bool:
    """Launch the scheduler thread once. Returns True if it started."""
    global _started
    if _started or not config.SCHEDULER_ENABLED:
        return False
    _started = True
    threading.Thread(target=_loop, daemon=True, name="followup-scheduler").start()
    return True
