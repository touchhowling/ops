-- One-time migration: adding the new "immediate" follow-up (FU1 = day 0).
-- The sequence is being renumbered:  old 1→2, old 2→3, old 3→4. Run this ONCE
-- in the Supabase SQL editor BEFORE deploying the new code (so the in-app
-- counters keep matching the emails already sent).

begin;

-- 1) Shift every existing follow-up record up by one so the old FU1 (day-1)
--    becomes FU2 (still day-1 under the new numbering), etc.
--    Done as a two-step bump (+100, -99) so a lead that already has rows at
--    both 1 AND 2 doesn't hit a primary-key collision during the +1 update.
update ops_follow_ups set followup_no = followup_no + 100;
update ops_follow_ups set followup_no = followup_no - 99;

-- 2) Grandfather every existing lead-with-email: mark them as having already
--    received FU1 (the new "immediate" welcome). This prevents a "welcome"
--    email going out to leads who joined long before this feature.
insert into ops_follow_ups (lead_id, followup_no, to_email, sent_at)
select id::text, 1, email, now()
from leads
where email is not null and email <> ''
on conflict (lead_id, followup_no) do nothing;

commit;
