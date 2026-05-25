"""Shared funnel-stage definitions (mirrors the website funnel steps)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# current_step -> human label (matches admin Customers page)
STEP_LABELS: dict[int, str] = {
    1: "Age",
    2: "Body details",
    3: "Goals",
    4: "Picked a slot",
    5: "Contact details",
    6: "Chose plan",
    7: "Reached payment",
    8: "Completed",
}

# Email stages: which nurture email applies to a session right now.
#   details  -> gave contact details, hasn't chosen a plan          (step 5)
#   plan     -> chose a plan, hasn't reached payment                (step 6)
#   payment  -> reached payment hand-off, hasn't converted          (step 7+)
#   welcome  -> converted / paid                                    (status)
EMAIL_STAGE_FOR_STEP = {5: "details", 6: "plan", 7: "payment", 8: "payment"}


def stage_label(session: dict[str, Any]) -> str:
    if session.get("status") == "converted":
        return "Paid / Converted"
    step = session.get("current_step") or 1
    return f"{step} · {STEP_LABELS.get(step, 'Step ' + str(step))}"


def email_stage(session: dict[str, Any]) -> str | None:
    """The nurture email that applies, or None (too early / nothing to send)."""
    if session.get("status") == "converted":
        return "welcome"
    step = session.get("current_step") or 1
    return EMAIL_STAGE_FOR_STEP.get(step)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Supabase returns ISO 8601, often with 'Z' or +00:00
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def minutes_since(value: str | None) -> float | None:
    ts = parse_ts(value)
    if ts is None:
        return None
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 60.0


def lead_email(session: dict[str, Any]) -> str | None:
    lead = session.get("leads") or {}
    answers = session.get("answers") or {}
    email = lead.get("email") or answers.get("email")
    return email.strip() if isinstance(email, str) and email.strip() else None


def lead_first_name(session: dict[str, Any]) -> str:
    lead = session.get("leads") or {}
    answers = session.get("answers") or {}
    name = lead.get("name") or answers.get("name") or ""
    first = name.strip().split(" ")[0] if name.strip() else ""
    return first or "there"


def selected_plan(session: dict[str, Any]) -> str | None:
    answers = session.get("answers") or {}
    plan = answers.get("selectedPlan")
    return plan if isinstance(plan, str) else None
