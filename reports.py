"""Basic funnel reports / KPIs from Supabase."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import config
import stages
import supabase_client as sb

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def compute(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(sessions)
    visitors = len({s.get("anon_id") for s in sessions if s.get("anon_id")})
    converted = sum(1 for s in sessions if s.get("status") == "converted")
    reached_payment = sum(
        1 for s in sessions if s.get("status") == "converted" or (s.get("current_step") or 0) >= 7
    )
    with_email = sum(1 for s in sessions if stages.lead_email(s))

    by_stage: Counter[str] = Counter(stages.stage_label(s) for s in sessions)
    by_status: Counter[str] = Counter(s.get("status") or "unknown" for s in sessions)
    by_funnel: Counter[str] = Counter(s.get("funnel_key") or "unknown" for s in sessions)
    by_plan: Counter[str] = Counter(
        (stages.selected_plan(s) or "—") for s in sessions
    )
    by_source: Counter[str] = Counter(
        ((s.get("leads") or {}).get("source") or "—") for s in sessions
    )

    # Drop-off funnel: how many reached at least step N.
    funnel = {}
    for step in range(1, 9):
        funnel[step] = sum(
            1
            for s in sessions
            if (s.get("current_step") or 0) >= step or s.get("status") == "converted"
        )

    return {
        "total": total,
        "visitors": visitors,
        "converted": converted,
        "reached_payment": reached_payment,
        "with_email": with_email,
        "conversion_rate": (converted / total * 100) if total else 0.0,
        "payment_rate": (reached_payment / total * 100) if total else 0.0,
        "by_stage": by_stage,
        "by_status": by_status,
        "by_funnel": by_funnel,
        "by_plan": by_plan,
        "by_source": by_source,
        "funnel": funnel,
    }


def _bar(n: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return ""
    filled = round(n / total * width)
    return "█" * filled + "·" * (width - filled)


def print_report(k: dict[str, Any]) -> None:
    line = "─" * 56
    print("\n" + line)
    print("  YogHer — Funnel report   " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print(line)
    print(f"  Total journeys      : {k['total']}")
    print(f"  Unique visitors     : {k['visitors']}")
    print(f"  Gave email          : {k['with_email']}")
    print(f"  Reached payment     : {k['reached_payment']}  ({k['payment_rate']:.1f}%)")
    print(f"  Converted (paid)    : {k['converted']}  ({k['conversion_rate']:.1f}%)")

    print("\n  Stage where each journey sits")
    print("  " + line[:54])
    for label, n in sorted(k["by_stage"].items()):
        print(f"  {label:<22} {n:>4}  {_bar(n, k['total'])}")

    print("\n  Drop-off funnel (reached at least step N)")
    print("  " + line[:54])
    for step, n in k["funnel"].items():
        lbl = f"{step}. {stages.STEP_LABELS.get(step, '')}"
        print(f"  {lbl:<22} {n:>4}  {_bar(n, k['total'])}")

    print("\n  By journey type")
    for label, n in k["by_funnel"].items():
        print(f"  {label:<22} {n:>4}")

    print("\n  By selected plan")
    for label, n in k["by_plan"].most_common():
        print(f"  {label:<22} {n:>4}")

    print("\n  By source")
    for label, n in k["by_source"].most_common():
        print(f"  {label:<22} {n:>4}")
    print(line + "\n")


def write_csv(k: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"funnel-{stamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for key in ("total", "visitors", "with_email", "reached_payment", "converted"):
            w.writerow([key, k[key]])
        w.writerow(["conversion_rate_%", f"{k['conversion_rate']:.1f}"])
        w.writerow(["payment_rate_%", f"{k['payment_rate']:.1f}"])
        w.writerow([])
        w.writerow(["stage", "count"])
        for label, n in sorted(k["by_stage"].items()):
            w.writerow([label, n])
    return path


def run(export_csv: bool = False) -> None:
    sessions = sb.get_funnel_sessions()
    k = compute(sessions)
    print_report(k)
    if export_csv:
        path = write_csv(k)
        print(f"  CSV written → {path}\n")
