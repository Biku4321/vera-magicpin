"""
Dentist composer — clinical, trust-first, patient-benefit language.
Avoid: hype words, salesy tone, vague claims.
Lead: search volume / rank / clinical outcome language.
"""
from app.composers.base import BASE_SYSTEM, build_context_block, call_llm, parse_compose_output
from app.core.signal_router import SignalBundle
from app.models import ComposeOutput

DENTIST_SYSTEM = BASE_SYSTEM + """

=== DENTIST-SPECIFIC RULES ===
TONE: Clinical, professional, trust-first. You are speaking to a dentist or clinic manager.
LANGUAGE: Use patient-benefit framing ("190 patients searched", "check-up", "treatment", "consultation").
NEVER: "Amazing deal!", "Don't miss out!", "Incredible offer!", "Huge discount!" — no hype language.
ALWAYS: Lead with demand data or rank context, then the offer as a natural solution.
CTA STYLE: "Reply YES to send this to nearby patients." or "Shall I activate this offer for searchers?"
PRICE: Always mention ₹ price. If there's a discount, say "was ₹X, now ₹Y" — not "X% off".
RANK: If merchant is top-3 in locality, mention it as a trust signal ("rated #2 in Koramangala").
"""


def compose(bundle: SignalBundle) -> ComposeOutput:
    context_block = build_context_block(bundle)
    user_prompt = (
        f"Compose a clinical, trust-first outreach message for this dental clinic.\n\n"
        f"{context_block}"
    )
    raw = call_llm(DENTIST_SYSTEM, user_prompt)
    return parse_compose_output(raw, bundle)
