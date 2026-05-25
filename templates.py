"""Per-stage nurture email templates.

Each stage returns (subject, html, text). Built to email best practices:
preheader text, one clear primary CTA, a social-proof review, a plain-text
alternative, and a footer explaining why they're receiving it.
"""
from __future__ import annotations

import re
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


def _wrap(preheader: str, body_html: str, hero_url: str | None = HERO_IMG) -> str:
    year = "2026"
    hero_row = (
        f'<tr><td><img src="{hero_url}" width="560" alt="YogHer — live online yoga for women"'
        f' style="width:100%;height:auto;display:block"/></td></tr>'
        if hero_url
        else ""
    )
    return f"""\
<!doctype html><html><body style="margin:0;background:{BG};font-family:Helvetica,Arial,sans-serif">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</span>
<table role="presentation" width="100%" style="background:{BG};padding:24px 0">
<tr><td align="center">
  <table role="presentation" width="100%" style="max-width:560px;background:#fff;border-radius:20px;overflow:hidden">
    {hero_row}
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


# Built-in follow-up copy as editable token templates. Anything in {curly} is
# replaced from the lead's context (see TEMPLATE_TOKENS). A saved override in the
# DB takes precedence over these — see render_followup().
DEFAULT_FOLLOWUPS: dict[str, dict[str, Any]] = {
    "followup1": {
        "subject": "{first_name}, your YogHer plan is still waiting 🌸",
        "preheader": "Pick up right where you left off — it only takes a minute.",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>You started your YogHer journey but didn't quite finish — and your "
            "matched plan is still saved for you. Live classes run every day, "
            "5 AM–9 PM IST, so there's always a slot that fits.</p>"
        ),
        "button_label": "Pick up where I left off",
        "button_url": "{plans_url}",
        "hero_image": HERO_IMG,
        "review": 0,
    },
    "followup2": {
        "subject": "What's holding you back, {first_name}? 🌷",
        "preheader": "Real women, real results — and a coach who'll know your name.",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>A week ago you were looking for a yoga practice built around "
            "<em>your</em> body and goals. We're still here — and so is your spot. "
            "We cap each cohort at 50 women so every coach knows your name, your "
            "cycle, your goals.</p>"
            "<p>Whether it's PCOS, weight, energy, or pregnancy — this is for you.</p>"
        ),
        "button_label": "See plans & start this week",
        "button_url": "{plans_url}",
        "hero_image": HERO_IMG,
        "review": 1,
    },
    "followup3": {
        "subject": "One last nudge, {first_name} 🤍",
        "preheader": "We'll stop here — but the door stays open.",
        "body": (
            "<p>Hi {first_name},</p>"
            "<p>This is the last we'll nudge you — we don't like crowding inboxes. "
            "But we didn't want you to miss your chance to start something that's "
            "helped thousands of women feel strong, calm, and in control again.</p>"
            "<p>If now isn't the time, no worries at all. Whenever you're ready, "
            "we're one tap away.</p>"
        ),
        "button_label": "Start my journey",
        "button_url": "{journey_url}",
        "hero_image": HERO_IMG,
        "review": 2,
    },
}

# Tokens an editor can use in subject / body / button fields.
TEMPLATE_TOKENS = [
    "first_name", "site_url", "plans_url", "rapid_url", "journey_url",
    "whatsapp_url", "support_whatsapp", "plan_name", "plan_price", "plan_days",
]


def _context(lead: dict[str, Any]) -> dict[str, str]:
    plan = config.PLANS["transformation"]
    return {
        "first_name": _first_name(lead),
        "site_url": config.SITE_URL,
        "plans_url": f"{config.SITE_URL}/#plans",
        "rapid_url": f"{config.SITE_URL}/rapid-start",
        "journey_url": f"{config.SITE_URL}/start-your-journey",
        "whatsapp_url": config.WHATSAPP_COMMUNITY_URL,
        "support_whatsapp": config.SUPPORT_WHATSAPP,
        "plan_name": plan["name"],
        "plan_price": f"{plan['price']:,}",
        "plan_days": str(plan["days"]),
    }


def _subst(s: str | None, ctx: dict[str, str]) -> str:
    """Replace {token} placeholders. Stray braces (e.g. in CSS) are left alone."""
    out = s or ""
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def _to_text(body_html: str, label: str, url: str, review_idx: int) -> str:
    text = re.sub(r"<br\s*/?>", "\n", body_html)
    text = re.sub(r"</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if label and url:
        text += f"\n\n{label}: {url}"
    quote, who = REVIEWS[review_idx % len(REVIEWS)]
    return f"{text}\n\n“{quote}” — {who}\n\n— Team YogHer"


# In-process cache of saved overrides so rendering a whole batch is one query,
# not one per email. Invalidated on save/reset; warmed via load_overrides().
_OVERRIDES: dict[str, dict] | None = None


def load_overrides(force: bool = False) -> dict[str, dict]:
    global _OVERRIDES
    if _OVERRIDES is None or force:
        import state

        _OVERRIDES = state.all_template_overrides()
    return _OVERRIDES


def invalidate_overrides() -> None:
    global _OVERRIDES
    _OVERRIDES = None


def followup_source(key: str) -> dict[str, Any]:
    """The editable source for a follow-up: a saved override, else the default."""
    default = DEFAULT_FOLLOWUPS[key]
    ov = load_overrides().get(key)
    if not ov:
        return {**default, "is_custom": False}
    return {
        "subject": ov["subject"],
        "preheader": ov["preheader"],
        "body": ov["body"],
        "button_label": ov["button_label"],
        "button_url": ov["button_url"],
        # blank hero in a saved override means "no image"; only fall back to the
        # default hero when the column was never populated (legacy rows = None).
        "hero_image": default["hero_image"] if ov["hero_image"] is None else ov["hero_image"],
        "review": default["review"],
        "is_custom": True,
    }


def render_followup(n: int, lead: dict[str, Any]) -> tuple[str, str, str]:
    """One of the 3 time-based follow-ups (day 1 / 7 / 15), using a saved
    override if one exists, otherwise the built-in copy. n is 1-based."""
    key = f"followup{n}" if n in (1, 2, 3) else "followup3"
    src = followup_source(key)
    ctx = _context(lead)

    subject = _subst(src["subject"], ctx)
    pre = _subst(src["preheader"], ctx)
    body = _subst(src["body"], ctx)
    label = _subst(src["button_label"], ctx)
    url = _subst(src["button_url"], ctx)
    hero = _subst(src.get("hero_image", HERO_IMG), ctx).strip()
    review_idx = src["review"]

    button_html = (
        f'<p style="text-align:center;margin:28px 0">{_button(label, url)}</p>'
        if label and url
        else ""
    )
    full = body + button_html + _review_card(review_idx)
    return subject, _wrap(pre, full, hero or None), _to_text(body, label, url, review_idx)


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
