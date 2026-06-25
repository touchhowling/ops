"""Time-based follow-up sequence (day 1 / 7 / 15 after first contact).

Works at the LEAD level (not per funnel session):
  • Anchor = the lead's created_at ("first contact").
  • Three dedicated follow-up emails at FOLLOWUP_OFFSETS_DAYS.
  • Each follow-up goes out at most once per lead.
  • A lead is skipped entirely if they've converted (any funnel session with
    status='converted') or been suppressed in the admin app ("mark converted").
  • The earliest still-due follow-up is sent per run, so a daily scheduler keeps
    the 1→2→3 order even if a run is missed.
  • Sends share the MAX_PER_DAY budget with manual blasts.
"""
from __future__ import annotations

from typing import Any

import config
import emailer
import stages
import state
import supabase_client as sb
import templates


def _norm(email: str | None) -> str:
    return email.strip().lower() if isinstance(email, str) else ""


def converted_emails(sessions: list[dict[str, Any]]) -> set[str]:
    """Emails that have at least one funnel session indicating they paid.

    Treats two signals as "converted":
      • status == 'converted'  — the website explicitly marked them.
      • completed_at is set AND current_step >= 7  — they finished the
        checkout step. The step floor guards against unrelated rows that
        happen to have completed_at populated at an earlier step.
    """
    out: set[str] = set()
    for s in sessions:
        is_converted = s.get("status") == "converted" or (
            s.get("completed_at") and (s.get("current_step") or 0) >= 7
        )
        if not is_converted:
            continue
        e = _norm(stages.lead_email(s))
        if e:
            out.add(e)
    return out


def due_followup(
    lead: dict[str, Any],
    converted: set[str],
    followups_map: dict[str, set[int]],
    suppressed: set[str],
) -> int | None:
    """Return the follow-up number due for this lead now, or None.

    Takes prefetched state (followups_map, suppressed) so a whole pass is a
    handful of queries rather than one per lead."""
    lead_id = str(lead.get("id") or "")
    email = lead.get("email")
    if not lead_id or not email:
        return None
    if lead_id in suppressed:
        return None
    if _norm(email) in converted:
        return None

    age_min = stages.minutes_since(lead.get("created_at"))
    if age_min is None:
        return None
    age_days = age_min / 1440.0

    already = followups_map.get(lead_id, set())
    # Offsets are ordered; follow-up numbers are 1-based by position.
    for idx, offset_days in enumerate(config.FOLLOWUP_OFFSETS_DAYS):
        n = idx + 1
        if n in already:
            continue
        if age_days >= offset_days:
            return n  # earliest still-due touch
        break  # this one isn't due yet, so later ones aren't either
    return None


def build_due_jobs() -> list[dict[str, Any]]:
    """One job per email address. Duplicate lead records sharing an email are
    collapsed into a single send, and ALL their lead_ids are marked on send so
    the duplicate doesn't regenerate a job next run."""
    leads = sb.get_leads()
    converted = converted_emails(sb.get_funnel_sessions())
    followups_map = state.all_followups()  # prefetched once
    suppressed = state.suppressed_ids()    # prefetched once
    templates.load_overrides()             # warm template cache for this batch

    # Group due leads by (normalized email, follow-up number).
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for lead in leads:
        n = due_followup(lead, converted, followups_map, suppressed)
        if n is None:
            continue
        groups.setdefault((_norm(lead["email"]), n), []).append(lead)

    # Per email, send only the earliest still-due follow-up this run.
    earliest: dict[str, int] = {}
    for (email, n) in groups:
        if email not in earliest or n < earliest[email]:
            earliest[email] = n

    jobs: list[dict[str, Any]] = []
    for (email, n), members in groups.items():
        if n != earliest[email]:
            continue
        lead = members[0]
        subject, html, text = templates.render_followup(n, lead)
        jobs.append(
            {
                "to": lead["email"],
                "subject": subject,
                "html": html,
                "text": text,
                "lead_ids": [str(m["id"]) for m in members],
                "followup_no": n,
            }
        )
    return jobs


def run_once(verbose: bool = True) -> int:
    jobs = build_due_jobs()
    remaining = max(0, config.MAX_PER_DAY - state.sent_today())

    def _persist(job: dict[str, Any]) -> None:
        if not config.DRY_RUN:
            for lead_id in job["lead_ids"]:
                state.mark_followup(lead_id, job["followup_no"], job["to"])

    sent, failed, first_error = emailer.send_bulk(jobs, cap=remaining, on_sent=_persist)
    if verbose:
        mode = "DRY RUN" if config.DRY_RUN else "LIVE"
        skipped = max(0, len(jobs) - remaining)
        note = f" · {skipped} held back (daily cap)" if skipped else ""
        err = f" · first error: {first_error}" if first_error else ""
        print(
            f"\n[{mode}] follow-ups: {len(jobs)} due · {sent} sent · "
            f"{failed} failed{note}{err}. Budget left today: {max(0, remaining - sent)}.\n",
            flush=True,
        )
    return sent
