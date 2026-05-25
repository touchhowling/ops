"""Local SQLite state: idempotency + follow-up tracking + suppression.

Everything the admin app and scheduler need to coordinate lives here, on the
one machine that runs them:
  • sent_emails  — stage automation idempotency (one email per journey+stage)
  • follow_ups   — which of the 3 day-1/7/15 touches each LEAD has received
  • suppressed   — leads marked converted / "stop emailing" from the admin app
  • manual_sends — audit log of manual bulk blasts

Supabase stays read-only; this file is the source of truth for what we've sent
and who to leave alone.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import config

DB_PATH = config.STATE_DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_emails (
            session_id TEXT NOT NULL,
            stage      TEXT NOT NULL,
            to_email   TEXT,
            sent_at    TEXT NOT NULL,
            PRIMARY KEY (session_id, stage)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS follow_ups (
            lead_id     TEXT NOT NULL,
            followup_no INTEGER NOT NULL,
            to_email    TEXT,
            sent_at     TEXT NOT NULL,
            PRIMARY KEY (lead_id, followup_no)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS suppressed (
            lead_id   TEXT PRIMARY KEY,
            reason    TEXT,
            marked_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_sends (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            template  TEXT,
            to_email  TEXT,
            subject   TEXT,
            sent_at   TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    return conn


# ─── Small key/value store (scheduler run-times etc.) ────────────────────────
def set_meta(key: str, value: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )


def get_meta(key: str, default: str = "") -> str:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


# ─── Stage automation (unchanged API) ────────────────────────────────────────
def already_sent(session_id: str, stage: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "SELECT 1 FROM sent_emails WHERE session_id = ? AND stage = ?",
            (session_id, stage),
        )
        return cur.fetchone() is not None


def mark_sent(session_id: str, stage: str, to_email: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sent_emails (session_id, stage, to_email, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, stage, to_email, _now()),
        )


def count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM sent_emails").fetchone()[0]


# ─── Follow-up sequence ───────────────────────────────────────────────────────
def followup_sent(lead_id: str, followup_no: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "SELECT 1 FROM follow_ups WHERE lead_id = ? AND followup_no = ?",
            (lead_id, followup_no),
        )
        return cur.fetchone() is not None


def mark_followup(lead_id: str, followup_no: int, to_email: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO follow_ups (lead_id, followup_no, to_email, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (lead_id, followup_no, to_email, _now()),
        )


def followups_for(lead_id: str) -> set[int]:
    """Which follow-up numbers have already gone out for this lead."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT followup_no FROM follow_ups WHERE lead_id = ?", (lead_id,)
        ).fetchall()
        return {r[0] for r in rows}


def lead_ids_with_followup(followup_no: int) -> set[str]:
    """Every lead that has already received a given follow-up number."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT lead_id FROM follow_ups WHERE followup_no = ?", (followup_no,)
        ).fetchall()
        return {r[0] for r in rows}


# ─── Suppression (mark converted / stop emails) ──────────────────────────────
def suppress(lead_id: str, reason: str = "converted") -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO suppressed (lead_id, reason, marked_at) VALUES (?, ?, ?)",
            (lead_id, reason, _now()),
        )


def unsuppress(lead_id: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM suppressed WHERE lead_id = ?", (lead_id,))


def is_suppressed(lead_id: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("SELECT 1 FROM suppressed WHERE lead_id = ?", (lead_id,))
        return cur.fetchone() is not None


def suppressed_ids() -> set[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT lead_id FROM suppressed").fetchall()
        return {r[0] for r in rows}


# ─── Manual bulk audit + daily cap accounting ────────────────────────────────
def log_manual_send(template: str, to_email: str, subject: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO manual_sends (template, to_email, subject, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (template, to_email, subject, _now()),
        )


def manual_emails_sent_today(template: str) -> set[str]:
    """Lower-cased addresses that already got this template via a manual blast
    today (UTC) — used to stop a re-run double-emailing the same people."""
    today = _today() + "%"
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT lower(to_email) FROM manual_sends "
            "WHERE template = ? AND sent_at LIKE ?",
            (template, today),
        ).fetchall()
        return {r[0] for r in rows if r[0]}


def sent_today() -> int:
    """Total real sends today (UTC) across all tables — drives the daily cap."""
    today = _today() + "%"
    with _conn() as conn:
        a = conn.execute(
            "SELECT COUNT(*) FROM sent_emails WHERE sent_at LIKE ?", (today,)
        ).fetchone()[0]
        b = conn.execute(
            "SELECT COUNT(*) FROM follow_ups WHERE sent_at LIKE ?", (today,)
        ).fetchone()[0]
        c = conn.execute(
            "SELECT COUNT(*) FROM manual_sends WHERE sent_at LIKE ?", (today,)
        ).fetchone()[0]
        return a + b + c
