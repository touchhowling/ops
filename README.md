# YogHer Ops — reports + email automation

A small standalone Python tool that sits beside `main_website`. It reads the
**same Supabase database** the website writes to and does two things:

1. **Reports** — funnel KPIs: visitors, where each customer is in the journey,
   drop-off, and conversion.
2. **Email automation** — stage-aware nurture emails (one per funnel step),
   sent from your Gmail, with a built-in "wait" so people who are actively
   moving through aren't interrupted.

It reads lead/funnel data from Supabase (never writes to it). All sending
state — which emails went out, who's converted, who to stop emailing — lives in
a local `state.sqlite3`, so nobody gets the same email twice and the admin app
and scheduler stay in sync.

On top of the stage emails it adds:
- **A 3-step follow-up sequence** (day 1 / 7 / 15 after first contact), with
  3 dedicated templates, that stops the moment a lead converts.
- **A small admin dashboard** (`python main.py web`) to watch leads, mark a lead
  converted ("stop emailing"), and fire manual bulk sends.
- **A daily send cap** so follow-ups + manual blasts never blow past Gmail's
  limit.

---

## Setup

```bash
cd ops
python -m venv .venv
.venv\Scripts\activate          # Windows  (use: source .venv/bin/activate on mac/linux)
pip install -r requirements.txt
copy .env.example .env          # then edit .env
```

Supabase credentials are auto-read from `../main_website/.env.local`, so you
usually only need to fill in the **email** settings in `.env`.

---

## Reports

```bash
python main.py report           # pretty KPI summary in the terminal
python main.py report --csv     # also writes reports/funnel-<timestamp>.csv
```

You'll see totals, a per-stage breakdown (Age → … → Paid), a drop-off funnel,
and splits by journey type / plan / source.

---

## Email automation

```bash
python main.py preview details            # write an HTML preview to open in a browser
python main.py preview payment --to you@gmail.com   # send yourself a sample
python main.py emails --once              # one pass over all journeys
python main.py emails --loop --interval 600   # keep running, every 10 min
```

### What gets sent, and when
| Funnel stage | Email | When |
|---|---|---|
| Steps 1–4 | *(nothing — no email address yet)* | we wait |
| Step 5 — gave contact details | "Your personalized plan is ready" | after idle ≥ `WAIT_MINUTES` |
| Step 6 — chose a plan | "You're one step away" | after idle ≥ `WAIT_MINUTES` |
| Step 7 — reached payment | "Finish your checkout" (abandoned) | after idle ≥ `WAIT_MINUTES` |
| Converted / paid | "Welcome to YogHer" | immediately |

The **wait** (`WAIT_MINUTES`, default 60) is the key idea you described: if a
customer is moving step 1 → step 2 → step 3, they're "active" and we don't email.
Only once they've paused at a stage for that long do we send the matching nudge.

Emails include your hero image (auto-optimised via Cloudinary), a real member
review, one clear call-to-action button, and a plain-text fallback.

### Safety
`DRY_RUN=true` (the default) **prints** what it would send instead of sending.
Review the output, then set `DRY_RUN=false` in `.env` to go live.

---

## Follow-up sequence (day 1 / 7 / 15)

A separate, time-based drip aimed at leads who gave their email but haven't
converted. It's anchored to **first contact** (the lead's `created_at`) and uses
3 dedicated templates:

| Touch | When | Email |
|---|---|---|
| Follow-up 1 | day 1 | "Your plan is still waiting" — gentle nudge |
| Follow-up 2 | day 7 | "What's holding you back?" — social proof |
| Follow-up 3 | day 15 | "One last nudge" — final, soft close |

```bash
python main.py preview followup1            # eyeball the design
python main.py followups --once             # send every due touch (one pass)
```

- Each lead gets each follow-up **at most once**. Duplicate lead records sharing
  an email are collapsed into a single send.
- A lead is skipped entirely if they've **converted** (any funnel session
  `status=converted`) or been **marked converted / stopped** in the admin app.
- The earliest still-due touch is sent per run, so a daily scheduler keeps the
  1→2→3 order even if a day is missed.
- Offsets are configurable: `FOLLOWUP_OFFSETS_DAYS=1,7,15` in `.env`.

### Daily send cap
Follow-ups **and** manual blasts share `MAX_PER_DAY` (default 450 — stay under
Gmail's ~500/day). Anything over the budget is held back for the next run.

---

## Admin dashboard

A small separate web app (Flask) for the team — no terminal needed.

```bash
# set ADMIN_USER / ADMIN_PASS in .env first, then:
python main.py web                          # http://127.0.0.1:8000
```

It shows every lead with status (active / converted / stopped), which follow-ups
have gone out, what's due next, and today's send budget. From there you can:
- **Mark converted / Stop emails** on any lead (and **Resume** later).
- **Send a manual bulk** — pick a follow-up template + a segment (active-only or
  all, optionally filtered by source). **Duplicate-safe by default:** it skips
  duplicate addresses, anyone who already received that follow-up via the auto
  sequence, and anyone who already got that template in a manual blast earlier
  the same day — and reports how many it skipped. Tick *"Resend even to people
  who already received this"* to override. Always respects suppression,
  conversions and the daily cap.
- **Run follow-ups now** on demand.

Login is HTTP basic auth (`ADMIN_USER` / `ADMIN_PASS`). The app refuses to start
without a password. It binds to `127.0.0.1` by default — only expose it on a
network behind something that adds TLS.

---

## Sending from Gmail — how to set it up

**Recommended: Gmail SMTP with an App Password.** Simplest, supports HTML +
images + reviews, no OAuth dance.

1. Turn on **2-Step Verification** for the Gmail account.
2. Go to <https://myaccount.google.com/apppasswords> and create an app password
   (pick "Mail"). You'll get a 16-character code.
3. In `.env` set:
   ```
   SMTP_USER=youraddress@gmail.com
   SMTP_PASSWORD=that16charcode
   EMAIL_FROM=youraddress@gmail.com
   EMAIL_FROM_NAME=YogHer
   DRY_RUN=false
   ```

**Limits & deliverability**
- Free Gmail: ~500 emails/day. Google Workspace: ~2,000/day. This tool is for
  nurture volumes well within that.
- For higher volume or better inbox placement later, switch to a transactional
  provider (Resend / SendGrid / Amazon SES) and set up SPF/DKIM on a custom
  domain — the `emailer.py` send function is the only file you'd swap.
- Images use hosted URLs (your Cloudinary), so some clients show "display
  images" first — the copy still reads fine without them.

**Alternative: Gmail API (OAuth).** Higher limits and no app password, but needs
a Google Cloud project + OAuth consent screen. Overkill for now; ask if you want
it and I'll add a `gmail_api.py` sender.

---

## Automatic follow-ups

When the admin app runs **always-on**, it sends the follow-ups itself — no
external cron needed. A built-in scheduler ([scheduler.py](scheduler.py)) fires
one follow-up pass per day at `FOLLOWUP_HOUR` (default 10:00 IST, set via
`FOLLOWUP_HOUR` + `SCHEDULER_OFFSET_MINUTES`). The dashboard shows the last run,
how many it sent, and the next scheduled run. Sends are idempotent, so a restart
or an extra run never double-emails.

```
SCHEDULER_ENABLED=true          # set false to disable the built-in timer
FOLLOWUP_HOUR=10                # 24h clock
SCHEDULER_OFFSET_MINUTES=330    # IST
```

## Deploying (Render, always-on)

A [render.yaml](render.yaml) blueprint is included. Push the repo to GitHub →
Render → **New + → Blueprint** → pick the repo, then fill the secret env vars
(Supabase, SMTP, `ADMIN_PASS`, etc.) in the dashboard.

- The app binds `0.0.0.0:$PORT` and runs the dashboard + scheduler in one
  process. Start command: `python main.py web --host 0.0.0.0 --port $PORT`.
- **Use a paid plan with a persistent disk.** The "don't send twice" guarantee
  and suppression live in SQLite; on the free plan the disk isn't persistent and
  the service sleeps when idle, so the scheduler won't fire reliably. The
  blueprint mounts a 1 GB disk at `/var/data` and sets
  `STATE_DB_PATH=/var/data/state.sqlite3`.
- Keep `DRY_RUN=true` until you've reviewed previews, then set it `false`.

> Why not Vercel? It's serverless — the SQLite state would be wiped between
> requests (causing repeat emails) and there's no always-on process for the
> scheduler. An always-on host fits this tool.

### Alternative: run it on a timer instead of always-on
If you'd rather not keep a process running, disable the scheduler
(`SCHEDULER_ENABLED=false`) and trigger passes externally:
- **Windows Task Scheduler** → `python main.py followups --once` once daily;
  `python main.py emails --once` every 15–30 min for the stage emails.
- **cron** → `0 10 * * * cd /path/ops && .venv/bin/python main.py followups --once`

## Files
| File | Purpose |
|---|---|
| `main.py` | CLI entrypoint |
| `config.py` | env + settings (reads website `.env.local` for Supabase) |
| `supabase_client.py` | read-only REST queries |
| `reports.py` | KPI computation + console/CSV output |
| `stages.py` | funnel-stage logic shared by reports & automation |
| `templates.py` | per-stage + 3 follow-up email templates (subject/HTML/text) |
| `emailer.py` | Gmail SMTP sender — single send + bulk (one connection) |
| `automation.py` | the "wait + send the right stage" orchestration |
| `sequences.py` | the day-1/7/15 follow-up engine |
| `scheduler.py` | built-in daily timer that auto-sends follow-ups |
| `webapp.py` | the admin dashboard (Flask) |
| `state.py` | local SQLite: sent log, follow-ups, suppression, daily count |
