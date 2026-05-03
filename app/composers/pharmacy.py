"""
Pharmacy composer — utility-first, informational, seasonal health demand.
Avoid: promotional/salesy language on Rx items. No hype.
Lead: health need / seasonal demand, then the practical solution.
"""
from app.composers.base import BASE_SYSTEM, build_context_block, call_llm, parse_compose_output
from app.core.signal_router import SignalBundle
from app.models import ComposeOutput

PHARMACY_SYSTEM = BASE_SYSTEM + """

=== PHARMACY-SPECIFIC RULES ===
TONE: Utility-first, informational, caring. You are a helpful neighbourhood pharmacist, not a salesperson.
LANGUAGE: Health-need framing ("monsoon season brings cough and cold", "allergy season is here").
NEVER: Promotional language for prescription drugs. Never say "amazing deal on medicines".
SEASONAL HOOK: Lead with the health context ("82 people near you searched for cold relief this week").
PRACTICAL: Focus on convenience ("we have stock", "no prescription needed for OTC", "home delivery available").
CTA STYLE: "Reply YES to send our seasonal care kit offer to nearby customers."
PRICE: OTC wellness products, health kits, vitamins — price these clearly ("Immunity Kit at ₹349").
TRUST: If rating is high, mention it as a trust signal. Mention years in locality if available.
SENSITIVITY: For prescription categories, focus on availability and convenience, not price discounts.
"""


def compose(bundle: SignalBundle) -> ComposeOutput:
    context_block = build_context_block(bundle)
    user_prompt = (
        f"Compose a utility-first, informational outreach message for this pharmacy.\n\n"
        f"{context_block}"
    )
    raw = call_llm(PHARMACY_SYSTEM, user_prompt)
    return parse_compose_output(raw, bundle)
