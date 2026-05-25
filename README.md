# YogHer Ops — reports + email automation

A small standalone Python tool that sits beside `main_website`. It reads the
**same Supabase database** the website writes to and does two things:

1. **Reports** — funnel KPIs: visitors, where each customer is in the journey,
   drop-off, and conversion.
2. **Email automation** — stage-aware nurture emails (one per funnel step),
   sent from your Gmail, with a built-in "wait" so people who are actively
   moving through aren't interrupted.

It reads lead/funnel data from Supabase and stores all **sending state** —
which emails went out, who's converted, who to stop emailing — in its own
`ops_*` tables in that same Supabase. That means nobody gets the same email
twice, and the state survives restarts and works on a free/stateless host (run
[supabase_schema.sql](supabase_schema.sql) once to create the tables).

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

**One-time:** create the state tables by running [supabase_schema.sql](supabase_schema.sql)
in the Supabase SQL editor (Dashboard → SQL → New query → paste → Run).

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
- **Edit email templates** (`/templates`) — change the subject, preheader, body,
  button, and **top image** of each follow-up right in the browser, with a live
  **Preview** and **Reset to default**. Edits are stored in Supabase and
  apply to both the automatic sequence and manual bulk sends. Use placeholders
  like `{first_name}`, `{plans_url}`, `{site_url}` — the branded header, footer
  and a testimonial are added automatically.
  - **Images via link:** paste any hosted image URL into the *Top image URL*
    field (a thumbnail previews it live); leave it blank for no image. To add
    more images inside the email, drop `<img src="https://…">` tags into the
    Body HTML. Host images anywhere public (your Cloudinary, S3, etc.).

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

Because state lives in Supabase, the follow-ups can be driven by an **external
cron** hitting a secret endpoint — which works even on a free, sleepy host (the
request both wakes it and triggers the send). Sends are idempotent, so running
several times a day **never double-emails**; it just sends due emails sooner.

The endpoint (enabled once `CRON_SECRET` is set):
```
POST /cron/followups?key=<CRON_SECRET>      # or header  X-Cron-Key: <CRON_SECRET>
```

Two ways to schedule it (pick one):
- **GitHub Actions** — [.github/workflows/followups.yml](.github/workflows/followups.yml)
  is included; it runs 4×/day. Add repo secrets `OPS_URL` (your deployed URL) and
  `CRON_SECRET`.
- **cron-job.org** (or any uptime pinger) — create a job that POSTs that URL on
  your schedule.

> **Always-on alternative:** if you host on an always-on box, you can instead use
> the built-in scheduler ([scheduler.py](scheduler.py)) — set
> `SCHEDULER_ENABLED=true` and `FOLLOWUP_HOURS=6,11,16,21`. Don't use a separate
> Render "Cron Job": it can't see the app and isn't needed — the external-cron
> endpoint above is the equivalent.

## Deploying on Render (free)

State is in Supabase, so **no persistent disk and no paid plan are required.**

1. Run [supabase_schema.sql](supabase_schema.sql) once in the Supabase SQL editor.
2. Push this repo to GitHub → Render → **New + → Blueprint** → pick the repo
   ([render.yaml](render.yaml) sets it up as a free web service).
3. Fill the secret env vars in the dashboard: `CRON_SECRET`, `ADMIN_USER`,
   `ADMIN_PASS`, `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SMTP_USER`,
   `SMTP_PASSWORD`, `EMAIL_FROM`, `WHATSAPP_COMMUNITY_URL`, `SUPPORT_WHATSAPP`.
4. Keep `DRY_RUN=true`, deploy, open the URL, log in, and **Preview** the emails.
5. Set up the external cron (GitHub Actions secrets, or cron-job.org).
6. When happy, set `DRY_RUN=false`. Do a tiny live test first (e.g.
   `MAX_PER_DAY=2`), confirm inbox delivery, then restore `MAX_PER_DAY`.

The free instance sleeps when idle; the cron ping wakes it. A URL exists but you
never have to open it as a dashboard.

> Why not Vercel? It's serverless with no always-on process; the cron-endpoint
> approach here gives you the same "scheduled job" without that complexity.

## Files
| File | Purpose |
|---|---|
| `main.py` | CLI entrypoint |
| `config.py` | env + settings (reads website `.env.local` for Supabase) |
| `supabase_client.py` | Supabase REST: lead/funnel reads + ops_* read/write |
| `supabase_schema.sql` | one-time: creates the `ops_*` state tables |
| `reports.py` | KPI computation + console/CSV output |
| `stages.py` | funnel-stage logic shared by reports & automation |
| `templates.py` | per-stage + 3 editable follow-up templates (cached) |
| `emailer.py` | Gmail SMTP sender — single send + bulk (one connection) |
| `automation.py` | the "wait + send the right stage" orchestration |
| `sequences.py` | the day-1/7/15 follow-up engine |
| `scheduler.py` | built-in timer (always-on hosts) that auto-sends follow-ups |
| `webapp.py` | admin dashboard + `/cron/followups` endpoint (Flask) |
| `state.py` | Supabase-backed: follow-ups, suppression, templates, daily count |
| `.github/workflows/followups.yml` | free external cron (4×/day) |
