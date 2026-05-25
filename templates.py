"""Per-stage nurture email templates.

Each stage returns (subject, html, text). Built to email best practices:
preheader text, one clear primary CTA, a social-proof review, a plain-text
alternative, and a footer explaining why they're receiving it.
"""
from __future__ import annotations

from typing import Any

import config

BRAND = "#C77177"        # blush-700
INK = "#2B2A33"
MUTED = "#6B6776"
BG = "#FAF6F6"

# A couple of curated reviews to drop into emails as social proof.
REVIEWS = [
    ("I lost 8 kgs but more than that, I got my cycle back. YogHer understood me.", "Priya M."),
    ("My PCOS markers improved in 8 weeks. I've never felt this in control.", "Sneha K."),
    ("The only program that made me feel safe and strong during pregnancy.", "Anika R."),
]

# A friendly hero image (already on your Cloudinary, auto-optimised).
HERO_IMG = (
    "https://res.cloudinary.com/dmtggqp0f/image/upload/"
    "f_auto,q_auto,w_1000/v1779726637/Gemini_Generated_Image_f5wtff5wtff5wtff_lshpe6.png"
)


def _button(label: str, href: str) -> str:
    return (
        f'<a href="{href}" style="display:inline-block;background:{BRAND};color:#fff;'
        f'text-decoration:none;font-weight:600;padding:14px 28px;border-radius:999px;'
        f'font-size:16px">{label}</a>'
    )


def _review_card(idx: int = 0) -> str:
    quote, who = REVIEWS[idx % len(REVIEWS)]
    return (
        f'<table role="presentation" width="100%" style="margin:24px 0;background:{BG};'
        f'border-radius:16px"><tr><td style="padding:18px 20px">'
        f'<div style="font-size:15px;line-height:1.6;color:{INK}">“{quote}”</div>'
        f'<div style="margin-top:8px;font-size:13px;color:{MUTED}">— {who}, YogHer member</div>'
        f"</td></tr></table>"
    )


def _wrap(preheader: str, body_html: str) -> str:
    year = "2026"
    return f"""\
<!doctype html><html><body style="margin:0;background:{BG};font-family:Helvetica,Arial,sans-serif">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</span>
<table role="presentation" width="100%" style="background:{BG};padding:24px 0">
<tr><td align="center">
  <table role="presentation" width="100%" style="max-width:560px;background:#fff;border-radius:20px;overflow:hidden">
    <tr><td>
      <img src="{HERO_IMG}" width="560" alt="YogHer — live online yoga for women"
           style="width:100%;height:auto;display:block"/>
    </td></tr>
    <tr><td style="padding:28px 28px 8px">
      <div style="font-size:20px;font-weight:700;color:{BRAND};letter-spacing:.5px">YogHer</div>
    </td></tr>
    <tr><td style="padding:4px 28px 28px;color:{INK};font-size:16px;line-height:1.6">
      {body_html}
    </td></tr>
  </table>
  <table role="presentation" width="100%" style="max-width:560px">
    <tr><td style="padding:18px 28px;color:{MUTED};font-size:12px;line-height:1.6;text-align:center">
      You're receiving this because you started a YogHer journey.<br/>
      Questions? WhatsApp us at {config.SUPPORT_WHATSAPP}.<br/>
      © {year} YogHer · <a href="{config.SITE_URL}" style="color:{MUTED}">{config.SITE_URL}</a>
    </td></tr>
  </table>
</td></tr></table></body></html>"""


def _first_name(lead: dict[str, Any]) -> str:
    name = (lead.get("name") or "").strip()
    return name.split(" ")[0] if name else "there"


def render_followup(n: int, lead: dict[str, Any]) -> tuple[str, str, str]:
    """One of the 3 time-based follow-ups (day 1 / 7 / 15).

    These are stage-agnostic, anchored to first contact, and stop once a lead
    converts. n is 1-based.
    """
    first = _first_name(lead)
    plans_url = f"{config.SITE_URL}/#plans"
    journey_url = f"{config.SITE_URL}/start-your-journey"

    if n == 1:
        subject = f"{first}, your YogHer plan is still waiting 🌸"
        pre = "Pick up right where you left off — it only takes a minute."
        body = f"""
        <p>Hi {first},</p>
        <p>You started your YogHer journey but didn't quite finish — and your
        matched plan is still saved for you. Live classes run every day, 5 AM–9 PM
        IST, so there's always a slot that fits.</p>
        <p style="text-align:center;margin:28px 0">{_button("Pick up where I left off", plans_url)}</p>
        {_review_card(0)}
        <p style="color:{MUTED};font-size:14px">Have a question first? Just reply — a real person reads every email.</p>
        """
        text = (
            f"Hi {first},\n\nYour YogHer plan is still saved. Pick up where you "
            f"left off:\n{plans_url}\n\n“{REVIEWS[0][0]}” — {REVIEWS[0][1]}\n\n— Team YogHer"
        )
        return subject, _wrap(pre, body), text

    if n == 2:
        subject = f"What's holding you back, {first}? 🌷"
        pre = "Real women, real results — and a coach who'll know your name."
        body = f"""
        <p>Hi {first},</p>
        <p>A week ago you were looking for a yoga practice built around <em>your</em>
        body and goals. We're still here — and so is your spot. We cap each cohort
        at 50 women so every coach knows your name, your cycle, your goals.</p>
        <p>Whether it's PCOS, weight, energy, or pregnancy — this is for you.</p>
        <p style="text-align:center;margin:28px 0">{_button("See plans & start this week", plans_url)}</p>
        {_review_card(1)}
        <p style="color:{MUTED};font-size:14px">Not sure which plan fits? Reply and we'll help you choose.</p>
        """
        text = (
            f"Hi {first},\n\nStill here for you. We cap each cohort at 50 women so "
            f"your coach knows you personally. See plans:\n{plans_url}\n\n"
            f"“{REVIEWS[1][0]}” — {REVIEWS[1][1]}\n\n— Team YogHer"
        )
        return subject, _wrap(pre, body), text

    # n == 3 (or anything beyond) — final, gentle nudge.
    subject = f"One last nudge, {first} 🤍"
    pre = "We'll stop here — but the door stays open."
    body = f"""
    <p>Hi {first},</p>
    <p>This is the last we'll nudge you — we don't like crowding inboxes. But we
    didn't want you to miss your chance to start something that's helped thousands
    of women feel strong, calm, and in control again.</p>
    <p>If now isn't the time, no worries at all. Whenever you're ready, we're one
    tap away.</p>
    <p style="text-align:center;margin:28px 0">{_button("Start my journey", journey_url)}</p>
    {_review_card(2)}
    <p style="color:{MUTED};font-size:14px">Prefer to chat? WhatsApp us at {config.SUPPORT_WHATSAPP}.</p>
    """
    text = (
        f"Hi {first},\n\nOne last nudge — whenever you're ready, we're here. "
        f"Start your journey:\n{journey_url}\n\n"
        f"“{REVIEWS[2][0]}” — {REVIEWS[2][1]}\n\n— Team YogHer"
    )
    return subject, _wrap(pre, body), text


def render(stage: str, session: dict[str, Any]) -> tuple[str, str, str]:
    import stages as st

    first = st.lead_first_name(session)
    plan_slug = st.selected_plan(session) or "transformation"
    plan = config.PLANS.get(plan_slug, config.PLANS["transformation"])
    plans_url = f"{config.SITE_URL}/#plans"
    rapid_url = f"{config.SITE_URL}/rapid-start?plan={plan_slug}"
    journey_url = f"{config.SITE_URL}/start-your-journey"

    if stage == "details":
        subject = f"{first}, your personalized YogHer plan is ready 🌸"
        pre = "You're moments away from a plan built for your body."
        body = f"""
        <p>Hi {first},</p>
        <p>You told us about your goals — now your matched plan is waiting. It only
        takes a minute to pick the membership that fits where you are and lock in
        your first live session this week.</p>
        <p style="text-align:center;margin:28px 0">{_button("See my plan & pricing", plans_url)}</p>
        {_review_card(0)}
        <p style="color:{MUTED};font-size:14px">Prefer to talk it through first? Just reply to this email.</p>
        """
        text = (
            f"Hi {first},\n\nYour matched YogHer plan is ready. Pick your membership "
            f"and start your first live session this week:\n{plans_url}\n\n"
            f"“{REVIEWS[0][0]}” — {REVIEWS[0][1]}\n\n— Team YogHer"
        )
        return subject, _wrap(pre, body), text

    if stage == "plan":
        subject = f"You're one step away, {first} ✨"
        pre = f"Your {plan['name']} plan is held for you."
        body = f"""
        <p>Hi {first},</p>
        <p>Great choice — the <strong>{plan['name']}</strong> plan
        (₹{plan['price']:,} / {plan['days']} days) is a brilliant fit. You're just
        one step from your first session. Finish enrolling and we'll send your
        schedule on WhatsApp within hours.</p>
        <p style="text-align:center;margin:28px 0">{_button(f"Complete my {plan['name']} enrolment", rapid_url)}</p>
        {_review_card(1)}
        <p style="color:{MUTED};font-size:14px">Live classes run 5 AM–9 PM IST, every day. Pick any slot that suits you.</p>
        """
        text = (
            f"Hi {first},\n\nYour {plan['name']} plan (Rs {plan['price']}/{plan['days']} days) "
            f"is ready. Finish enrolling here:\n{rapid_url}\n\n"
            f"“{REVIEWS[1][0]}” — {REVIEWS[1][1]}\n\n— Team YogHer"
        )
        return subject, _wrap(pre, body), text

    if stage == "payment":
        subject = f"Still thinking it over, {first}? 🌷"
        pre = "Your spot in this week's cohort is almost gone."
        body = f"""
        <p>Hi {first},</p>
        <p>You were so close to starting! Your <strong>{plan['name']}</strong> plan is
        still saved, and we cap each cohort at 50 women so every coach knows your
        name and your goals — spots fill fast.</p>
        <p>Checkout is quick and secure on HDFC SmartBuy.</p>
        <p style="text-align:center;margin:28px 0">{_button("Finish my checkout", rapid_url)}</p>
        {_review_card(2)}
        <p style="color:{MUTED};font-size:14px">Changed your mind about the plan? <a href="{plans_url}" style="color:{BRAND}">Compare all plans</a> or just reply — we're happy to help.</p>
        """
        text = (
            f"Hi {first},\n\nYour {plan['name']} plan is still saved. Finish your "
            f"secure checkout here:\n{rapid_url}\n\n"
            f"“{REVIEWS[2][0]}” — {REVIEWS[2][1]}\n\n— Team YogHer"
        )
        return subject, _wrap(pre, body), text

    if stage == "welcome":
        subject = f"Welcome to YogHer, {first}! 🎉"
        pre = "Here's how to get started in the next 24 hours."
        body = f"""
        <p>Hi {first},</p>
        <p>Welcome — we're so glad you're here. Your <strong>{plan['name']}</strong>
        journey starts now. Here's what to do next:</p>
        <ol style="padding-left:18px;color:{INK}">
          <li style="margin-bottom:8px">Join the women-only WhatsApp community for your schedule + class links.</li>
          <li style="margin-bottom:8px">Your first live session is within 24 hours — pick any slot, 5 AM–9 PM IST.</li>
          <li>Meet your coach this week for a quick 1:1 intro.</li>
        </ol>
        <p style="text-align:center;margin:28px 0">{_button("Join the WhatsApp community", config.WHATSAPP_COMMUNITY_URL)}</p>
        {_review_card(0)}
        <p style="color:{MUTED};font-size:14px">Need anything at all? Just reply or WhatsApp {config.SUPPORT_WHATSAPP}.</p>
        """
        text = (
            f"Hi {first},\n\nWelcome to YogHer! Join the community to get your schedule "
            f"and class links:\n{config.WHATSAPP_COMMUNITY_URL}\n\nYour first session is "
            f"within 24 hours. — Team YogHer"
        )
        return subject, _wrap(pre, body), text

    raise ValueError(f"Unknown stage: {stage}")
