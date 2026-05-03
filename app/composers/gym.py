"""
Gym composer — motivational, goal-oriented, metric-driven.
Avoid: body-shaming, unrealistic promises, generic "get fit" language.
Lead: search demand as momentum, goal framing.
"""
from app.composers.base import BASE_SYSTEM, build_context_block, call_llm, parse_compose_output
from app.core.signal_router import SignalBundle
from app.models import ComposeOutput

GYM_SYSTEM = BASE_SYSTEM + """

=== GYM-SPECIFIC RULES ===
TONE: Motivational, positive, goal-focused. Channel the energy of a supportive coach.
LANGUAGE: Goal-oriented ("strength training", "fitness journey", "first session", "new members").
MOMENTUM FRAMING: Use search spikes as social proof ("145 people near you are looking to start training").
NEVER: Body-shaming language, unrealistic promises ("lose 10kg in 10 days"), or pressure tactics.
NEVER: Generic ("join now", "get healthy") — always tie to a specific goal or program name.
CTA STYLE: "Reply YES to offer them a free first session." or "Shall I send this intro offer to searchers?"
PRICE: Frame as investment ("₹799/month — less than ₹27/day for unlimited access").
SPECIFICS: Use membership price, program name, or trial offer. Never just say "affordable rates".
URGENCY: Frame enrollment windows positively ("New batch starts Monday — 12 spots remaining").
"""


def compose(bundle: SignalBundle) -> ComposeOutput:
    context_block = build_context_block(bundle)
    user_prompt = (
        f"Compose a motivational, goal-oriented outreach message for this gym.\n\n"
        f"{context_block}"
    )
    raw = call_llm(GYM_SYSTEM, user_prompt)
    return parse_compose_output(raw, bundle)
