"""Configuration + env loading.

Reads ops/.env first, then falls back to ../main_website/.env.local for the
Supabase credentials so they don't have to be duplicated.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBSITE_ENV = ROOT.parent / "main_website" / ".env.local"
OPS_ENV = ROOT / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        out[key] = val
    return out


# Layer the sources: process env > ops/.env > website .env.local
_website = _parse_env_file(WEBSITE_ENV)
_ops = _parse_env_file(OPS_ENV)


def get(key: str, default: str = "") -> str:
    return os.environ.get(key) or _ops.get(key) or _website.get(key) or default


def get_bool(key: str, default: bool = False) -> bool:
    return get(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


def get_int(key: str, default: int) -> int:
    try:
        return int(get(key, str(default)))
    except ValueError:
        return default


# ─── Supabase ────────────────────────────────────────────────────────────────
SUPABASE_URL = get("NEXT_PUBLIC_SUPABASE_URL").rstrip("/")
SUPABASE_KEY = get("SUPABASE_SECRET_KEY") or get("SUPABASE_SERVICE_ROLE_KEY")

# ─── Email (Resend HTTPS API — works on hosts that block SMTP) ──────────────
RESEND_API_KEY = get("RESEND_API_KEY")
EMAIL_FROM = get("EMAIL_FROM")
EMAIL_FROM_NAME = get("EMAIL_FROM_NAME", "YogHer")

# ─── Behaviour ───────────────────────────────────────────────────────────────
DRY_RUN = get_bool("DRY_RUN", True)
WAIT_MINUTES = get_int("WAIT_MINUTES", 60)
MAX_AGE_DAYS = get_int("MAX_AGE_DAYS", 14)

# ─── Follow-up sequence ──────────────────────────────────────────────────────
# Days after first contact (lead created) to send follow-ups 1, 2, 3.
def _parse_offsets(raw: str, default: list[int]) -> list[int]:
    try:
        vals = [int(x.strip()) for x in raw.split(",") if x.strip()]
        return vals or default
    except ValueError:
        return default


FOLLOWUP_OFFSETS_DAYS = _parse_offsets(
    get("FOLLOWUP_OFFSETS_DAYS", "0,1,7,15"), [0, 1, 7, 15]
)

# Safety valve for Gmail's daily send limit. Follow-ups AND manual blasts share
# this budget. Free Gmail ≈ 500/day, Workspace ≈ 2000/day — stay under it.
MAX_PER_DAY = get_int("MAX_PER_DAY", 450)

# ─── Admin web app ───────────────────────────────────────────────────────────
ADMIN_USER = get("ADMIN_USER", "admin")
ADMIN_PASS = get("ADMIN_PASS")  # blank = app refuses to start (set one in .env)

# Shared secret for the external-cron trigger (/cron/followups?key=...). Set a
# long random value; the endpoint is disabled until this is set.
CRON_SECRET = get("CRON_SECRET")

# ─── Built-in scheduler ──────────────────────────────────────────────────────
# When the web app runs always-on (Render/Railway), it fires the follow-up pass
# itself once a day — no external cron needed. Sends are idempotent, so an extra
# run never double-emails.
SCHEDULER_ENABLED = get_bool("SCHEDULER_ENABLED", True)
FOLLOWUP_HOUR = get_int("FOLLOWUP_HOUR", 10)        # legacy single-hour fallback


def _parse_hours(raw: str, default: list[int]) -> list[int]:
    try:
        vals = sorted({int(x.strip()) % 24 for x in raw.split(",") if x.strip()})
        return vals or default
    except ValueError:
        return default


# One or more hours of day (local) to run the follow-up pass, e.g. "6,11,16,21"
# for four times a day. Defaults to the single FOLLOWUP_HOUR above.
FOLLOWUP_HOURS = _parse_hours(get("FOLLOWUP_HOURS", str(FOLLOWUP_HOUR)), [FOLLOWUP_HOUR])

# Minutes east of UTC for the "local" hours above. India = 330 (IST, no DST).
SCHEDULER_OFFSET_MINUTES = get_int("SCHEDULER_OFFSET_MINUTES", 330)

# ─── Links / content ─────────────────────────────────────────────────────────
SITE_URL = get("SITE_URL", "https://yogher.in").rstrip("/")
WHATSAPP_COMMUNITY_URL = get("WHATSAPP_COMMUNITY_URL", "#")
SUPPORT_WHATSAPP = get("SUPPORT_WHATSAPP", "+919457592078")

# Plan catalogue (mirrors main_website/lib/site.ts). Prices in INR.
PLANS = {
    "starter": {"name": "Starter", "price": 1499, "days": 30},
    "transformation": {"name": "Transformation", "price": 3999, "days": 90},
    "elite": {"name": "Elite", "price": 7999, "days": 90},
}


def require_supabase() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit(
            "Missing Supabase credentials. Set NEXT_PUBLIC_SUPABASE_URL and "
            "SUPABASE_SECRET_KEY in ops/.env or ../main_website/.env.local."
        )
