"""Sending state, stored in Supabase (ops_* tables).

This is the source of truth for what the tool has done — so it survives restarts
and a stateless/free host, and is shared by every copy of the app:
  • ops_follow_ups    — which of the 3 day-1/7/15 touches each LEAD has received
  • ops_suppressed    — leads marked converted / "stop emailing"
  • ops_manual_sends  — audit log of manual bulk blasts (dedupe + daily cap)
  • ops_sent_emails   — stage-email idempotency
  • ops_email_templates — edited templates (overrides)
  • ops_meta          — small key/value (scheduler run-times)

Run supabase_schema.sql once to create these tables.
"""
from __future__ import annotations

from datetime import datetime, timezone

import supabase_client as sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_start() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


# ─── Stage automation ─────────────────────────────────────────────────────────
def already_sent(session_id: str, stage: str) -> bool:
    rows = sb.select(
        "ops_sent_emails", "session_id",
        {"session_id": f"eq.{session_id}", "stage": f"eq.{stage}", "limit": "1"},
    )
    return bool(rows)


def mark_sent(session_id: str, stage: str, to_email: str) -> None:
    sb.upsert(
        "ops_sent_emails",
        [{"session_id": session_id, "stage": stage, "to_email": to_email, "sent_at": _now()}],
        on_conflict="session_id,stage",
    )


def count() -> int:
    return sb.count("ops_sent_emails")


# ─── Follow-up sequence ───────────────────────────────────────────────────────
def followup_sent(lead_id: str, followup_no: int) -> bool:
    rows = sb.select(
        "ops_follow_ups", "followup_no",
        {"lead_id": f"eq.{lead_id}", "followup_no": f"eq.{followup_no}", "limit": "1"},
    )
    return bool(rows)


def mark_followup(lead_id: str, followup_no: int, to_email: str) -> None:
    sb.upsert(
        "ops_follow_ups",
        [{"lead_id": lead_id, "followup_no": followup_no, "to_email": to_email, "sent_at": _now()}],
        on_conflict="lead_id,followup_no",
    )


def followups_for(lead_id: str) -> set[int]:
    rows = sb.select("ops_follow_ups", "followup_no", {"lead_id": f"eq.{lead_id}"})
    return {r["followup_no"] for r in rows}


def all_followups() -> dict[str, set[int]]:
    """Every (lead_id -> {follow-up numbers sent}) — one query for bulk use."""
    out: dict[str, set[int]] = {}
    for r in sb.select("ops_follow_ups", "lead_id,followup_no"):
        out.setdefault(str(r["lead_id"]), set()).add(r["followup_no"])
    return out


def lead_ids_with_followup(followup_no: int) -> set[str]:
    rows = sb.select("ops_follow_ups", "lead_id", {"followup_no": f"eq.{followup_no}"})
    return {str(r["lead_id"]) for r in rows}


# ─── Suppression ──────────────────────────────────────────────────────────────
def suppress(lead_id: str, reason: str = "converted") -> None:
    sb.upsert(
        "ops_suppressed",
        [{"lead_id": lead_id, "reason": reason, "marked_at": _now()}],
        on_conflict="lead_id",
    )


def unsuppress(lead_id: str) -> None:
    sb.delete("ops_suppressed", {"lead_id": f"eq.{lead_id}"})


def is_suppressed(lead_id: str) -> bool:
    rows = sb.select("ops_suppressed", "lead_id", {"lead_id": f"eq.{lead_id}", "limit": "1"})
    return bool(rows)


def suppressed_ids() -> set[str]:
    return {str(r["lead_id"]) for r in sb.select("ops_suppressed", "lead_id")}


# ─── Manual bulk audit + daily cap accounting ────────────────────────────────
def log_manual_send(template: str, to_email: str, subject: str) -> None:
    sb.insert(
        "ops_manual_sends",
        [{"template": template, "to_email": to_email, "subject": subject, "sent_at": _now()}],
    )


def manual_emails_sent_today(template: str) -> set[str]:
    rows = sb.select(
        "ops_manual_sends", "to_email",
        {"template": f"eq.{template}", "sent_at": f"gte.{_today_start()}"},
    )
    return {(r["to_email"] or "").lower() for r in rows if r.get("to_email")}


def sent_today() -> int:
    f = {"sent_at": f"gte.{_today_start()}"}
    return (
        sb.count("ops_sent_emails", f)
        + sb.count("ops_follow_ups", f)
        + sb.count("ops_manual_sends", f)
    )


# ─── Small key/value store ────────────────────────────────────────────────────
def set_meta(key: str, value: str) -> None:
    sb.upsert("ops_meta", [{"key": key, "value": value}], on_conflict="key")


def get_meta(key: str, default: str = "") -> str:
    rows = sb.select("ops_meta", "value", {"key": f"eq.{key}", "limit": "1"})
    return rows[0]["value"] if rows else default


# ─── Editable email templates ────────────────────────────────────────────────
def _row_to_override(row: dict) -> dict:
    return {
        "subject": row.get("subject"),
        "preheader": row.get("preheader"),
        "body": row.get("body_html"),
        "button_label": row.get("button_label"),
        "button_url": row.get("button_url"),
        "hero_image": row.get("hero_image"),  # None for legacy; "" = no image
    }


def get_template_override(key: str) -> dict | None:
    rows = sb.select("ops_email_templates", "*", {"key": f"eq.{key}", "limit": "1"})
    return _row_to_override(rows[0]) if rows else None


def all_template_overrides() -> dict[str, dict]:
    return {r["key"]: _row_to_override(r) for r in sb.select("ops_email_templates", "*")}


def save_template_override(
    key: str,
    subject: str,
    preheader: str,
    body_html: str,
    button_label: str,
    button_url: str,
    hero_image: str = "",
) -> None:
    sb.upsert(
        "ops_email_templates",
        [{
            "key": key,
            "subject": subject,
            "preheader": preheader,
            "body_html": body_html,
            "button_label": button_label,
            "button_url": button_url,
            "hero_image": hero_image,
            "updated_at": _now(),
        }],
        on_conflict="key",
    )


def reset_template(key: str) -> None:
    sb.delete("ops_email_templates", {"key": f"eq.{key}"})


def customized_template_keys() -> set[str]:
    return {r["key"] for r in sb.select("ops_email_templates", "key")}
