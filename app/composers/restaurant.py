"""
Restaurant composer — sensory, local, time-aware.
Avoid: generic "great food", "amazing taste" claims.
Lead: specific dish name + search demand or slow-day angle.
"""
from app.composers.base import BASE_SYSTEM, build_context_block, call_llm, parse_compose_output
from app.core.signal_router import SignalBundle
from app.models import ComposeOutput

RESTAURANT_SYSTEM = BASE_SYSTEM + """

=== RESTAURANT-SPECIFIC RULES ===
TONE: Sensory, local, warm. Make the reader almost taste the food.
LANGUAGE: Use dish-specific words ("butter chicken", "crispy dosa", "mango lassi") — never "food items".
TIME-AWARE: If it's a slow day (Tuesday, Wednesday), call it out ("Tuesdays are quiet — let's change that").
NEVER: Generic claims ("great food", "amazing taste", "best restaurant"). Always use specifics.
DISH-FIRST: Lead with the most popular/searched dish name, not the restaurant name.
CTA STYLE: "Reply YES to send a combo deal to nearby diners." or "Shall I push this to hungry customers near you?"
URGENCY: For dip triggers, create urgency ("Today's footfall is 18% lower — this deal can recover it").
PRICE: Always mention the exact offer price ("Biryani + Raita combo at ₹199").
LOCAL HOOK: Mention the locality name to make it hyper-local ("craving biryani in Indiranagar").
"""


def compose(bundle: SignalBundle) -> ComposeOutput:
    context_block = build_context_block(bundle)
    user_prompt = (
        f"Compose a sensory, time-aware outreach message for this restaurant.\n\n"
        f"{context_block}"
    )
    raw = call_llm(RESTAURANT_SYSTEM, user_prompt)
    return parse_compose_output(raw, bundle)
