"""Thin Supabase REST client (read-only) for the ops tooling."""
from __future__ import annotations

from typing import Any

import requests

import config


def _headers() -> dict[str, str]:
    return {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Accept": "application/json",
    }


def _fetch(table: str, select: str, order: str | None = None, page_size: int = 1000) -> list[dict[str, Any]]:
    """Fetch all rows from a table using range pagination."""
    config.require_supabase()
    url = f"{config.SUPABASE_URL}/rest/v1/{table}"
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, str] = {"select": select}
        if order:
            params["order"] = order
        headers = {**_headers(), "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code not in (200, 206):
            raise SystemExit(f"Supabase error {resp.status_code} on {table}: {resp.text[:300]}")
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


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
