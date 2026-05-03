"""
Salon composer — aspirational, visual, occasion-aware.
Avoid: clinical language, vague claims like "great service".
Lead: occasion/festival hook, trend, transformation language.
"""
from app.composers.base import BASE_SYSTEM, build_context_block, call_llm, parse_compose_output
from app.core.signal_router import SignalBundle
from app.models import ComposeOutput

SALON_SYSTEM = BASE_SYSTEM + """

=== SALON-SPECIFIC RULES ===
TONE: Aspirational, warm, visual. Speak to the transformation the customer will experience.
LANGUAGE: Use outcome-focused words ("look stunning", "refresh your look", "before the occasion").
OCCASION-FIRST: If there's a festival or upcoming occasion, lead with it ("Eid is in 3 days — ").
NEVER: Clinical language ("treatment plan", "procedure"), corporate jargon, or vague ("great service").
ALWAYS: Mention the specific service name (haircut, facial, bridal package — not just "service").
CTA STYLE: "Reply YES and I'll book the slot." or "Should I send this to nearby customers?"
PRICE: Show value clearly — "Full bridal package at ₹2,499 (was ₹3,500)".
VISUAL HOOK: Use a sensory/visual word in the first sentence.
"""


def compose(bundle: SignalBundle) -> ComposeOutput:
    context_block = build_context_block(bundle)
    user_prompt = (
        f"Compose an aspirational, occasion-aware outreach message for this salon.\n\n"
        f"{context_block}"
    )
    raw = call_llm(SALON_SYSTEM, user_prompt)
    return parse_compose_output(raw, bundle)
