"""YogHer ops CLI — funnel reports + stage-aware email automation.

Usage:
  python main.py report [--csv]                 Print KPI report (+ optional CSV)
  python main.py emails --once                  One stage-automation pass
  python main.py followups --once               One follow-up (day 1/7/15) pass
  python main.py web [--port 8000]              Launch the admin dashboard
  python main.py preview <stage> [--to you@x]   Preview/send a sample
                       stage = details|plan|payment|welcome|followup1|followup2|followup3
"""
from __future__ import annotations

import argparse
import sys

import config

# Windows consoles default to cp1252, which can't render the report's box/bar
# characters — force UTF-8 so output is consistent across platforms.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass


def cmd_report(args: argparse.Namespace) -> None:
    import reports

    reports.run(export_csv=args.csv)


def cmd_emails(args: argparse.Namespace) -> None:
    import automation

    if args.loop:
        automation.run_loop(interval_seconds=args.interval)
    else:
        automation.run_once()


def cmd_followups(args: argparse.Namespace) -> None:
    import sequences

    sequences.run_once()


def cmd_web(args: argparse.Namespace) -> None:
    try:
        import webapp
    except ImportError:
        raise SystemExit(
            "Flask isn't installed. Run: pip install -r requirements.txt"
        )
    webapp.serve(host=args.host, port=args.port)


def cmd_preview(args: argparse.Namespace) -> None:
    from pathlib import Path

    import emailer
    import templates

    if args.stage.startswith("followup"):
        n = int(args.stage[-1])
        lead = {"name": "Aanya Sharma", "email": args.to}
        subject, html, text = templates.render_followup(n, lead)
    else:
        # A fake session so you can eyeball a stage without real data.
        sample = {
            "id": "preview",
            "current_step": 6,
            "status": "in_progress",
            "answers": {"name": "Aanya Sharma", "selectedPlan": "transformation", "email": args.to},
            "leads": {"name": "Aanya Sharma", "email": args.to},
        }
        subject, html, text = templates.render(args.stage, sample)
    print(f"Subject: {subject}\n")
    if args.to:
        emailer.send(args.to, subject, html, text)
    else:
        path = Path(__file__).resolve().parent / f"preview-{args.stage}.html"
        path.write_text(html, encoding="utf-8")
        print(f"No --to given. Wrote HTML preview → {path}")
        print("Open it in a browser to review the design.")


def main() -> None:
    parser = argparse.ArgumentParser(description="YogHer ops: reports + email automation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="Print funnel KPIs")
    p_report.add_argument("--csv", action="store_true", help="Also write a CSV")
    p_report.set_defaults(func=cmd_report)

    p_emails = sub.add_parser("emails", help="Run the stage email automation")
    p_emails.add_argument("--once", action="store_true", help="Single pass (default)")
    p_emails.add_argument("--loop", action="store_true", help="Run continuously")
    p_emails.add_argument("--interval", type=int, default=300, help="Loop interval seconds")
    p_emails.set_defaults(func=cmd_emails)

    p_follow = sub.add_parser("followups", help="Run the day-1/7/15 follow-up pass")
    p_follow.add_argument("--once", action="store_true", help="Single pass (default)")
    p_follow.set_defaults(func=cmd_followups)

    p_web = sub.add_parser("web", help="Launch the admin dashboard")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_web.add_argument("--port", type=int, default=8000, help="Bind port")
    p_web.set_defaults(func=cmd_web)

    p_prev = sub.add_parser("preview", help="Preview or send a sample email")
    p_prev.add_argument(
        "stage",
        choices=[
            "details", "plan", "payment", "welcome",
            "followup1", "followup2", "followup3", "followup4",
        ],
    )
    p_prev.add_argument("--to", default="", help="Send the sample to this address")
    p_prev.set_defaults(func=cmd_preview)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
