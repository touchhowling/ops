"""Separate small admin app (Flask) for the YogHer email ops.

Run it with:  python main.py web   (then open http://127.0.0.1:8000)

What it gives the team, in the browser:
  • A lead table with each lead's status, which follow-ups have gone out, and
    what's due next.
  • "Mark converted / Stop emails" and "Resume" buttons (local suppression).
  • A manual bulk send: pick one of the 3 follow-up templates + a segment.
  • "Run follow-ups now" to fire the scheduled pass on demand.
  • A live daily-budget meter so you never blow past the Gmail cap.

Auth is HTTP basic (ADMIN_USER / ADMIN_PASS from .env). It refuses to start
without a password set.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from flask import Flask, Response, redirect, render_template_string, request, url_for

from datetime import datetime, timedelta, timezone

import config
import emailer
import scheduler
import sequences
import stages
import state
import supabase_client as sb
import templates

app = Flask(__name__)

_LOCAL_OFFSET = timedelta(minutes=config.SCHEDULER_OFFSET_MINUTES)


def _fmt_local(iso: str) -> str:
    """Format a stored UTC ISO timestamp in the scheduler's local tz."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt + _LOCAL_OFFSET).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso

TEMPLATE_CHOICES = {
    "followup1": "Follow-up 1 (gentle nudge)",
    "followup2": "Follow-up 2 (overcome hesitation)",
    "followup3": "Follow-up 3 (final nudge)",
}


# ─── Auth ─────────────────────────────────────────────────────────────────────
def _check_auth(auth: Any) -> bool:
    return bool(auth) and auth.username == config.ADMIN_USER and auth.password == config.ADMIN_PASS


def requires_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _check_auth(request.authorization):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="YogHer Ops"'},
            )
        return f(*args, **kwargs)

    return wrapped


# ─── Data assembly ────────────────────────────────────────────────────────────
def _overview() -> dict[str, Any]:
    leads = sb.get_leads()
    converted = sequences.converted_emails(sb.get_funnel_sessions())
    suppressed = state.suppressed_ids()

    rows = []
    sources: set[str] = set()
    counts = {"active": 0, "converted": 0, "stopped": 0, "no_email": 0}
    for lead in leads:
        lead_id = str(lead.get("id") or "")
        email = lead.get("email")
        src = lead.get("source") or "—"
        sources.add(src)
        is_conv = bool(email) and sequences._norm(email) in converted
        is_supp = lead_id in suppressed
        done = state.followups_for(lead_id)
        if not email:
            status, status_class = "no email", "noemail"
            counts["no_email"] += 1
        elif is_conv:
            status, status_class = "converted", "converted"
            counts["converted"] += 1
        elif is_supp:
            status, status_class = "stopped", "stopped"
            counts["stopped"] += 1
        else:
            status, status_class = "active", "active"
            counts["active"] += 1
        ts = stages.parse_ts(lead.get("created_at"))
        rows.append(
            {
                "id": lead_id,
                "name": lead.get("name") or "—",
                "email": email or "—",
                "source": src,
                "created": ts.strftime("%Y-%m-%d") if ts else "—",
                "status": status,
                "status_class": status_class,
                "followups": [n in done for n in (1, 2, 3)],
                "next_due": sequences.due_followup(lead, converted)
                if status == "active"
                else None,
            }
        )

    sent_today = state.sent_today()
    return {
        "rows": rows,
        "sources": sorted(s for s in sources if s and s != "—"),
        "counts": counts,
        "sent_today": sent_today,
        "cap": config.MAX_PER_DAY,
        "remaining": max(0, config.MAX_PER_DAY - sent_today),
        "dry_run": config.DRY_RUN,
        "sched": {
            "enabled": config.SCHEDULER_ENABLED,
            "hour": config.FOLLOWUP_HOUR,
            "last_run": _fmt_local(state.get_meta("last_followup_run")),
            "last_count": state.get_meta("last_followup_count", "—"),
            "next_run": _fmt_local(state.get_meta("next_followup_run")),
            "error": state.get_meta("last_followup_error"),
        },
    }


PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YogHer Ops</title>
<style>
 *{box-sizing:border-box}
 body{font-family:Helvetica,Arial,sans-serif;background:#FAF6F6;color:#2B2A33;margin:0;padding:24px}
 h1{color:#C77177;margin:0 0 4px} .sub{color:#6B6776;margin:0 0 20px}
 .bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:20px}
 .card{background:#fff;border-radius:14px;padding:14px 18px;box-shadow:0 1px 4px rgba(0,0,0,.05);font-size:13px;color:#6B6776}
 .card b{font-size:22px;display:block;color:#2B2A33}
 .pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
 .active{background:#E7F4EA;color:#1E7A3C}.converted{background:#E8EEFB;color:#2A52BE}
 .stopped{background:#FBE8E8;color:#B23838}.noemail{background:#EFEFEF;color:#6B6776}
 .tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:14px;background:#fff}
 table{width:100%;border-collapse:collapse;min-width:680px}
 th,td{padding:10px 12px;text-align:left;font-size:14px;border-bottom:1px solid #F0EBEB;white-space:nowrap}
 th{background:#F7F1F1;color:#6B6776;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
 .dot{display:inline-block;width:18px;height:18px;border-radius:50%;text-align:center;line-height:18px;font-size:11px;margin-right:2px}
 .on{background:#C77177;color:#fff}.off{background:#EFEbEb;color:#bbb}
 button{background:#C77177;color:#fff;border:0;padding:9px 16px;border-radius:999px;font-weight:600;cursor:pointer;font-size:14px}
 button.ghost{background:#fff;color:#C77177;border:1px solid #E6cfd1}
 .panel{background:#fff;border-radius:14px;padding:18px;margin-bottom:20px}
 label{display:block;font-size:13px;color:#6B6776}
 select,input{padding:9px;border:1px solid #E0D7D7;border-radius:8px;font-size:15px;width:100%;margin-top:4px}
 .row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
 .row > label{flex:1 1 160px}
 .warn{background:#FFF6E5;color:#8A5A00;padding:10px 14px;border-radius:10px;margin-bottom:16px;font-size:14px}
 form.inline{display:inline}
 a.tpl{display:inline-block;margin-right:8px;color:#C77177;font-weight:600;text-decoration:none;border:1px solid #E6cfd1;padding:6px 12px;border-radius:999px;font-size:13px}
 @media(max-width:640px){body{padding:14px}h1{font-size:22px}}
</style></head><body>
<h1>YogHer Ops</h1>
<p class="sub">Email follow-ups & manual sends · {{ "DRY RUN — nothing is actually sent" if o.dry_run else "LIVE" }}</p>

{% if o.dry_run %}<div class="warn">DRY_RUN is ON. Set <code>DRY_RUN=false</code> in .env to send for real.</div>{% endif %}

<div class="bar">
 <div class="card"><b>{{ o.counts.active }}</b>Active leads</div>
 <div class="card"><b>{{ o.counts.converted }}</b>Converted</div>
 <div class="card"><b>{{ o.counts.stopped }}</b>Stopped</div>
 <div class="card"><b>{{ o.sent_today }}/{{ o.cap }}</b>Sent today</div>
 <div class="card"><b>{{ o.remaining }}</b>Budget left today</div>
</div>

{% if msg %}<div class="warn">{{ msg }}</div>{% endif %}

<div class="panel">
 <div class="row" style="justify-content:space-between">
   <div>
     <strong>Automatic follow-ups</strong>
     <div style="color:#6B6776;font-size:13px;margin-top:4px">
       {% if o.sched.enabled %}
         On — runs daily at {{ '%02d:00'|format(o.sched.hour) }} (IST). Last run:
         <b>{{ o.sched.last_run }}</b>{% if o.sched.last_count != '—' %} ({{ o.sched.last_count }} sent){% endif %} ·
         Next: <b>{{ o.sched.next_run }}</b>
       {% else %}
         Off (SCHEDULER_ENABLED=false). Use the button or a cron to send.
       {% endif %}
     </div>
     {% if o.sched.error %}<div style="color:#B23838;font-size:12px;margin-top:4px">Last error: {{ o.sched.error }}</div>{% endif %}
   </div>
   <form class="inline" method="post" action="{{ url_for('run_followups') }}">
     <button type="submit">▶ Run now</button>
   </form>
 </div>
 <div style="color:#6B6776;font-size:13px;margin-top:8px">Sends every due day-{{ offsets }} touch.</div>
</div>

<div class="panel">
 <strong>Preview emails</strong>
 <div style="margin-top:12px">
   {% for key,label in choices.items() %}
     <a class="tpl" href="{{ url_for('preview', template=key) }}" target="_blank">👁 {{ label }}</a>
   {% endfor %}
 </div>
 <div style="color:#6B6776;font-size:13px;margin-top:8px">Opens the exact email — subject, body, testimonial — in a new tab.</div>
</div>

<div class="panel">
 <form method="post" action="{{ url_for('bulk') }}">
   <strong>Manual bulk send</strong>
   <div class="row" style="margin-top:12px">
     <label>Template
       <select name="template">
         {% for key,label in choices.items() %}<option value="{{ key }}">{{ label }}</option>{% endfor %}
       </select>
     </label>
     <label>Segment
       <select name="segment">
         <option value="active">Active only (not converted / not stopped)</option>
         <option value="all">All leads with an email</option>
       </select>
     </label>
     <label>Source
       <select name="source">
         <option value="">Any source</option>
         {% for s in o.sources %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
       </select>
     </label>
     <button type="submit" onclick="return confirm('Send this bulk email now?')">Send bulk</button>
   </div>
   <label style="display:flex;align-items:center;gap:8px;margin-top:12px;font-size:13px;color:#6B6776">
     <input type="checkbox" name="force" value="1" style="width:auto;margin:0">
     Resend even to people who already received this email (off = skip duplicates)
   </label>
   <div style="color:#6B6776;font-size:13px;margin-top:8px">
     By default, skips anyone who already got this follow-up (auto or manual today),
     duplicate addresses, and respects suppression, conversions and the daily budget.
   </div>
 </form>
</div>

<div class="tablewrap">
<table>
 <tr><th>Name</th><th>Email</th><th>Source</th><th>Joined</th><th>Status</th><th>Follow-ups</th><th>Next due</th><th></th></tr>
 {% for r in o.rows %}
 <tr>
   <td>{{ r.name }}</td>
   <td>{{ r.email }}</td>
   <td>{{ r.source }}</td>
   <td>{{ r.created }}</td>
   <td><span class="pill {{ r.status_class }}">{{ r.status }}</span></td>
   <td>{% for done in r.followups %}<span class="dot {{ 'on' if done else 'off' }}">{{ loop.index }}</span>{% endfor %}</td>
   <td>{{ ('#' ~ r.next_due) if r.next_due else '—' }}</td>
   <td>
     {% if r.status == 'stopped' %}
       <form class="inline" method="post" action="{{ url_for('unsuppress', lead_id=r.id) }}"><button class="ghost" type="submit">Resume</button></form>
     {% elif r.status in ['active'] %}
       <form class="inline" method="post" action="{{ url_for('suppress', lead_id=r.id) }}"><button class="ghost" type="submit">Mark converted</button></form>
     {% endif %}
   </td>
 </tr>
 {% endfor %}
</table>
</div>
</body></html>
"""


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
@requires_auth
def index():
    msg = request.args.get("msg", "")
    return render_template_string(
        PAGE,
        o=_overview(),
        choices=TEMPLATE_CHOICES,
        offsets="/".join(str(d) for d in config.FOLLOWUP_OFFSETS_DAYS),
        msg=msg,
    )


PREVIEW_PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview — {{ label }}</title>
<style>
 body{font-family:Helvetica,Arial,sans-serif;background:#FAF6F6;margin:0;padding:16px;color:#2B2A33}
 a{color:#C77177} .meta{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:14px}
 .meta b{color:#6B6776;font-size:12px;text-transform:uppercase;display:block}
 iframe{width:100%;height:78vh;border:1px solid #EADADA;border-radius:12px;background:#fff}
</style></head><body>
 <p><a href="{{ url_for('index') }}">← back to dashboard</a></p>
 <div class="meta"><b>Subject</b><div style="font-size:17px;font-weight:600">{{ subject }}</div></div>
 <iframe srcdoc="{{ html }}"></iframe>
</body></html>
"""


@app.route("/preview/<template>")
@requires_auth
def preview(template: str):
    n = {"followup1": 1, "followup2": 2, "followup3": 3}.get(template, 1)
    sample = {"name": "Aanya Sharma", "email": "preview@example.com"}
    subject, html, _ = templates.render_followup(n, sample)
    return render_template_string(
        PREVIEW_PAGE, label=TEMPLATE_CHOICES.get(template, template), subject=subject, html=html
    )


@app.route("/suppress/<lead_id>", methods=["POST"])
@requires_auth
def suppress(lead_id: str):
    state.suppress(lead_id, reason="marked in admin")
    return redirect(url_for("index", msg="Lead marked converted — emails stopped."))


@app.route("/unsuppress/<lead_id>", methods=["POST"])
@requires_auth
def unsuppress(lead_id: str):
    state.unsuppress(lead_id)
    return redirect(url_for("index", msg="Lead resumed."))


@app.route("/run-followups", methods=["POST"])
@requires_auth
def run_followups():
    sent = sequences.run_once(verbose=False)
    return redirect(url_for("index", msg=f"Follow-up pass complete — {sent} sent."))


@app.route("/bulk", methods=["POST"])
@requires_auth
def bulk():
    template = request.form.get("template", "followup1")
    segment = request.form.get("segment", "active")
    source = request.form.get("source", "").strip()
    force = request.form.get("force") == "1"  # resend even if already received
    n = {"followup1": 1, "followup2": 2, "followup3": 3}.get(template, 1)

    leads = sb.get_leads()
    converted = sequences.converted_emails(sb.get_funnel_sessions())
    suppressed = state.suppressed_ids()

    # Duplicate guards (skipped unless "force" is ticked):
    #  • already got this follow-up number via the AUTO sequence, or
    #  • already got this template via a manual blast earlier TODAY.
    auto_ids = state.lead_ids_with_followup(n)
    auto_emails = {
        sequences._norm(l["email"])
        for l in leads
        if l.get("email") and str(l.get("id") or "") in auto_ids
    }
    manual_today = state.manual_emails_sent_today(template)

    jobs = []
    seen: set[str] = set()
    dupes = 0
    for lead in leads:
        email = lead.get("email")
        if not email or "@" not in email:  # skip blanks / malformed
            continue
        norm = sequences._norm(email)
        if source and (lead.get("source") or "") != source:
            continue
        lead_id = str(lead.get("id") or "")
        if segment == "active" and (lead_id in suppressed or norm in converted):
            continue
        if norm in seen:  # same address twice in this run
            continue
        if not force and (norm in auto_emails or norm in manual_today):
            dupes += 1  # would be a duplicate of content they already received
            continue
        seen.add(norm)
        subject, html, text = templates.render_followup(n, lead)
        jobs.append(
            {"to": email, "subject": subject, "html": html, "text": text, "template": template}
        )

    remaining = max(0, config.MAX_PER_DAY - state.sent_today())

    def _persist(job):
        if not config.DRY_RUN:
            state.log_manual_send(job["template"], job["to"], job["subject"])
        manual_today.add(sequences._norm(job["to"]))  # guard within this same run too

    sent, failed = emailer.send_bulk(jobs, cap=remaining, on_sent=_persist)
    held = max(0, len(jobs) - remaining)
    parts = [f"{sent} sent", f"{failed} failed"]
    if dupes:
        parts.append(f"{dupes} skipped (already received)")
    if held:
        parts.append(f"{held} held back by daily cap")
    return redirect(url_for("index", msg="Bulk send: " + ", ".join(parts) + "."))


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    if not config.ADMIN_PASS:
        raise SystemExit(
            "ADMIN_PASS is not set. Add ADMIN_USER / ADMIN_PASS to ops/.env before "
            "starting the admin app."
        )
    config.require_supabase()
    if scheduler.start():
        print(
            f"Scheduler ON — follow-ups run daily at {config.FOLLOWUP_HOUR:02d}:00 "
            f"(offset {config.SCHEDULER_OFFSET_MINUTES}m from UTC)."
        )
    print(f"YogHer Ops admin → http://{host}:{port}  (login: {config.ADMIN_USER})")
    app.run(host=host, port=port, debug=False)
