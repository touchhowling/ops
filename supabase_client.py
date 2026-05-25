"""Thin Supabase REST client for the ops tooling.

Reads lead/funnel data and reads+writes the ops_* state tables (follow-ups,
suppression, manual sends, templates, meta). Uses the service key, so it works
regardless of row-level security.
"""
from __future__ import annotations

from typing import Any

import requests

import config

TIMEOUT = 30


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Accept": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _url(table: str) -> str:
    config.require_supabase()
    return f"{config.SUPABASE_URL}/rest/v1/{table}"


# ─── Reads ────────────────────────────────────────────────────────────────────
def _fetch(table: str, select: str, order: str | None = None, page_size: int = 1000) -> list[dict[str, Any]]:
    """Fetch all rows from a table using range pagination."""
    url = _url(table)
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, str] = {"select": select}
        if order:
            params["order"] = order
        headers = _headers({"Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"})
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if resp.status_code not in (200, 206):
            raise SystemExit(f"Supabase error {resp.status_code} on {table}: {resp.text[:300]}")
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def select(table: str, select: str = "*", filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Generic filtered select. filters values are PostgREST exprs, e.g.
    {"lead_id": "eq.123", "sent_at": "gte.2026-01-01"}."""
    params: dict[str, str] = {"select": select}
    if filters:
        params.update(filters)
    resp = requests.get(_url(table), headers=_headers(), params=params, timeout=TIMEOUT)
    if resp.status_code not in (200, 206):
        raise SystemExit(f"Supabase select error {resp.status_code} on {table}: {resp.text[:300]}")
    return resp.json()


def count(table: str, filters: dict[str, str] | None = None) -> int:
    """Exact row count matching filters (cheap — uses the Content-Range header)."""
    params: dict[str, str] = {"select": "*"}
    if filters:
        params.update(filters)
    headers = _headers({"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
    resp = requests.get(_url(table), headers=headers, params=params, timeout=TIMEOUT)
    if resp.status_code not in (200, 206):
        raise SystemExit(f"Supabase count error {resp.status_code} on {table}: {resp.text[:300]}")
    # Content-Range looks like "0-0/123" or "*/0"
    rng = resp.headers.get("Content-Range", "*/0")
    total = rng.split("/")[-1]
    return int(total) if total.isdigit() else 0


# ─── Writes ───────────────────────────────────────────────────────────────────
def insert(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    resp = requests.post(
        _url(table),
        headers=_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
        json=rows,
        timeout=TIMEOUT,
    )
    if resp.status_code not in (200, 201, 204):
        raise SystemExit(f"Supabase insert error {resp.status_code} on {table}: {resp.text[:300]}")


def upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    """Insert-or-update on the given conflict column(s)."""
    if not rows:
        return
    resp = requests.post(
        _url(table),
        headers=_headers(
            {"Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
        ),
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=TIMEOUT,
    )
    if resp.status_code not in (200, 201, 204):
        raise SystemExit(f"Supabase upsert error {resp.status_code} on {table}: {resp.text[:300]}")


def delete(table: str, filters: dict[str, str]) -> None:
    if not filters:
        raise ValueError("refusing to delete without filters")
    resp = requests.delete(
        _url(table),
        headers=_headers({"Prefer": "return=minimal"}),
        params=filters,
        timeout=TIMEOUT,
    )
    if resp.status_code not in (200, 204):
        raise SystemExit(f"Supabase delete error {resp.status_code} on {table}: {resp.text[:300]}")


# ─── Domain reads (lead/funnel data) ─────────────────────────────────────────
def get_funnel_sessions() -> list[dict[str, Any]]:
    """Every funnel journey with the linked lead (name/email/phone/source)."""
    return _fetch(
        "funnel_sessions",
        select=(
            "id,anon_id,funnel_key,current_step,status,answers,"
            "started_at,last_step_at,completed_at,"
            "leads(name,email,phone,source)"
        ),
        order="last_step_at.desc",
    )


def get_leads() -> list[dict[str, Any]]:
    return _fetch("leads", select="id,name,email,phone,source,state,created_at", order="created_at.desc")
