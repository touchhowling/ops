-- YogHer Ops — state tables. Run this ONCE in the Supabase SQL editor
-- (Dashboard → SQL → New query → paste → Run).
--
-- These are prefixed ops_ so they never clash with the website's tables. The
-- ops tool reads/writes them with the service key; row-level security is left
-- off because only the server (never the browser) touches them.

-- Which of the 3 follow-ups each lead has received (idempotency).
create table if not exists ops_follow_ups (
    lead_id     text not null,
    followup_no integer not null,
    to_email    text,
    sent_at     timestamptz not null default now(),
    primary key (lead_id, followup_no)
);

-- Leads marked converted / "stop emailing" from the admin app.
create table if not exists ops_suppressed (
    lead_id   text primary key,
    reason    text,
    marked_at timestamptz not null default now()
);

-- Audit log of manual bulk blasts (also powers bulk dedupe + daily cap).
create table if not exists ops_manual_sends (
    id        bigint generated always as identity primary key,
    template  text,
    to_email  text,
    subject   text,
    sent_at   timestamptz not null default now()
);

-- Stage-email idempotency (older per-step automation).
create table if not exists ops_sent_emails (
    session_id text not null,
    stage      text not null,
    to_email   text,
    sent_at    timestamptz not null default now(),
    primary key (session_id, stage)
);

-- Edited email templates (overrides; absent = use built-in copy).
create table if not exists ops_email_templates (
    key          text primary key,
    subject      text,
    preheader    text,
    body_html    text,
    button_label text,
    button_url   text,
    hero_image   text,
    updated_at   timestamptz not null default now()
);

-- Small key/value store (scheduler run-times, etc.).
create table if not exists ops_meta (
    key   text primary key,
    value text
);

-- Helpful indexes for the "today" and "by follow-up number" lookups.
create index if not exists idx_ops_follow_ups_no   on ops_follow_ups (followup_no);
create index if not exists idx_ops_follow_ups_sent on ops_follow_ups (sent_at);
create index if not exists idx_ops_manual_sent     on ops_manual_sends (sent_at);
create index if not exists idx_ops_manual_tpl      on ops_manual_sends (template);
