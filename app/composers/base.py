from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, Optional

import google.generativeai as genai

from app.models import ComposeOutput, SendAsIdentity
from app.core.signal_router import SignalBundle


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

_client: Optional[Any] = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        genai.configure(api_key=api_key)
        _client = genai.GenerativeModel(GEMINI_MODEL)
    return _client


# ── Base system prompt ────────────────────────────────────────────────────────

BASE_SYSTEM = """You are Vera, Magicpin's AI growth assistant for merchants.

Your job: compose a SHORT, hyper-specific outreach message a merchant can send to capture demand.

RULES — NON-NEGOTIABLE:
1. Every factual claim MUST trace to the context block below. Never invent numbers.
2. Think RATIONALE FIRST — write your reasoning before you write the message.
3. Message = 2-3 sentences max. CTA = exactly ONE yes/no action.
4. Use real numbers: search volume, price, rank, rating, discount, days, slots remaining.
5. No hype ("amazing!", "incredible!"). No vague claims ("many customers", "great offer").
6. suppression_key must match the format: merchant_slug:trigger_type:offer_id:customer_or_broadcast:YYYY-WW
7. If a COMPOSE HINT is provided, it is the HIGHEST-PRIORITY strategic directive.
   Your rationale MUST explicitly explain how you incorporated this hint into the message.
   If the hint is a CRITICAL CORRECTION, fix every issue it names before anything else.
8. If CATEGORY GUIDELINES are provided, they override default tone rules for this response.

OUTPUT FORMAT — return ONLY valid JSON, no prose, no markdown fences:
{
  "rationale": "Why this signal? Why this offer? Why this tone? Reference specific numbers.",
  "message": "2-3 sentence message grounded in context.",
  "cta": "One yes/no CTA. Example: Reply YES to confirm.",
  "send_as": "vera",
  "score_hints": {
    "decision_quality": "Which signal dominated and why",
    "specificity": "List every number used and its source field",
    "category_fit": "How tone matches category"
  }
}"""


# ── Context block serializer ──────────────────────────────────────────────────

def build_context_block(b: SignalBundle) -> str:
    """Serialize only non-null facts from the bundle into a structured prompt block."""
    lines = ["=== MERCHANT CONTEXT ==="]

    lines.append(f"Name: {b.merchant_name}")
    lines.append(f"Category: {b.category}")
    lines.append(f"Location: {b.locality}, {b.city}")
    if b.rating:          lines.append(f"Rating: {b.rating} stars")
    if b.total_reviews:   lines.append(f"Reviews: {b.total_reviews}")
    if b.rank_in_locality and b.total_merchants_in_locality:
        lines.append(f"Rank: #{b.rank_in_locality} of {b.total_merchants_in_locality} in {b.locality}")

    if any([b.orders_last_7d, b.monthly_revenue_inr, b.conversion_rate_pct]):
        lines.append("\n=== PERFORMANCE ===")
        if b.orders_last_7d is not None:
            lines.append(f"Orders this week: {b.orders_last_7d}")
        if b.orders_prev_7d is not None:
            lines.append(f"Orders last week: {b.orders_prev_7d}")
        if b.dip_pct:
            lines.append(f"Order dip: -{b.dip_pct:.1f}%")
        if b.spike_pct:
            lines.append(f"Order spike: +{b.spike_pct:.1f}%")
        if b.monthly_revenue_inr:
            lines.append(f"Monthly revenue: ₹{b.monthly_revenue_inr:,.0f}")
        if b.conversion_rate_pct is not None:
            lines.append(f"Conversion rate: {b.conversion_rate_pct}%")
        if b.slow_days:
            lines.append(f"Slow days: {', '.join(b.slow_days)}")

    if b.trigger_type:
        lines.append("\n=== TRIGGER ===")
        lines.append(f"Type: {b.trigger_type.value.upper()} (urgency rank: {b.urgency_rank}/5)")
        if b.search_term:    lines.append(f"Search term: '{b.search_term}'")
        if b.search_volume:  lines.append(f"Search volume: {b.search_volume} people searching NOW")
        if b.festival_name:  lines.append(f"Festival: {b.festival_name}")
        if b.days_until_festival is not None:
            lines.append(f"Days until festival: {b.days_until_festival}")
        if b.metric_name:    lines.append(f"Metric: {b.metric_name}")
        if b.metric_change_pct is not None:
            lines.append(f"Metric change: {b.metric_change_pct:+.1f}%")
        if b.campaign_name:  lines.append(f"Campaign: {b.campaign_name}")
        if b.review_text:    lines.append(f"Recent review: \"{b.review_text}\"")
        if b.review_rating:  lines.append(f"Review rating: {b.review_rating}")

    if b.best_offer:
        o = b.best_offer
        lines.append("\n=== BEST OFFER ===")
        lines.append(f"Offer ID: {o.offer_id}")
        lines.append(f"Title: {o.title}")
        lines.append(f"Price: ₹{o.price_inr}")
        if o.original_price_inr:
            lines.append(f"Original price: ₹{o.original_price_inr}")
        if o.discount_pct:
            lines.append(f"Discount: {o.discount_pct}% off")
        if o.valid_till:
            lines.append(f"Valid till: {o.valid_till}")
        if o.max_redemptions and o.redemptions is not None:
            remaining = o.max_redemptions - o.redemptions
            lines.append(f"Slots remaining: {remaining}")

    if b.all_offers and len(b.all_offers) > 1:
        lines.append(f"\nOther active offers: {len(b.all_offers) - 1} more available")

    if b.customer_name:
        lines.append("\n=== CUSTOMER ===")
        lines.append(f"Name: {b.customer_name}")
        if b.last_visit_days_ago is not None:
            lines.append(f"Last visit: {b.last_visit_days_ago} days ago")
        if b.is_lapsed:
            lines.append("Status: LAPSED (30+ days)")
        if b.total_visits:     lines.append(f"Total visits: {b.total_visits}")
        if b.avg_spend_inr:    lines.append(f"Avg spend: ₹{b.avg_spend_inr:.0f}")
        if b.preferred_services:
            lines.append(f"Preferred: {', '.join(b.preferred_services)}")
        if b.churn_risk:       lines.append(f"Churn risk: {b.churn_risk}")

    if b.digest_facts:
        lines.append("\n=== FRESH DIGEST FACTS (judge-injected, high priority) ===")
        lines.append(b.digest_facts)

    # Dynamic category guidelines injected by judge via POST /v1/context scope=category
    if b.category_guidelines is not None:
        cg = b.category_guidelines
        lines.append("\n=== CATEGORY GUIDELINES (override defaults) ===")
        if hasattr(cg, "tone_guidelines") and cg.tone_guidelines:
            lines.append(f"Tone: {cg.tone_guidelines}")
        if hasattr(cg, "avoid_phrases") and cg.avoid_phrases:
            lines.append(f"NEVER use these phrases: {', '.join(cg.avoid_phrases)}")
        if hasattr(cg, "preferred_cta") and cg.preferred_cta:
            lines.append(f"Preferred CTA format: {cg.preferred_cta}")

    if b.compose_hint:
        lines.append(f"\n=== COMPOSE HINT ===")
        hints = {
            "low_conversion_spike":  "High search demand but low conversion — focus message on offer quality/value, not just traffic volume.",
            "high_conversion_spike": "High demand AND high conversion — amplify momentum, reinforce winning position.",
            "dip_with_slow_days":    "Revenue dip coincides with known slow days — target slow-day offer to recover.",
            "lapsed_recall":         "Lapsed customer — lead with personalised win-back, acknowledge the gap warmly.",
        }
        lines.append(hints.get(b.compose_hint, b.compose_hint))

    lines.append(f"\n=== ROUTING ===")
    lines.append(f"Suppression key: {b.suppression_key}")
    lines.append(f"Send as: {b.send_as.value}")

    return "\n".join(lines)


# ── LLM call ─────────────────────────────────────────────────────────────────

def call_llm(system: str, user: str, max_tokens: int = 800) -> str:
    client = get_client()
    combined = f"{system}\n\n---\n\n{user}"
    response = client.generate_content(
        combined,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.2,
            candidate_count=1,
        ),
    )
    return response.text.strip()


# ── Output parser ─────────────────────────────────────────────────────────────

def parse_compose_output(raw: str, b: SignalBundle) -> ComposeOutput:
    """Robust JSON parse — handles markdown fences, mixed text+JSON."""
    text = raw.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$",          "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try to find JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Regex fallback — extract key fields
        def _extract(key: str) -> str:
            m = re.search(rf'"{key}"\s*:\s*"(.*?)"(?:,|\}})', raw, re.DOTALL)
            return m.group(1).strip() if m else ""

        data = {
            "rationale": _extract("rationale") or "Signal-based compose",
            "message":   _extract("message")   or raw[:300],
            "cta":       _extract("cta")        or "Reply YES to proceed.",
            "send_as":   _extract("send_as")    or b.send_as.value,
            "score_hints": {},
        }

    return ComposeOutput(
        message         = data.get("message", "")[:500],
        cta             = data.get("cta",     "Reply YES to confirm.")[:200],
        send_as         = data.get("send_as", b.send_as.value),
        suppression_key = b.suppression_key,
        rationale       = data.get("rationale", "")[:600],
        score_hints     = data.get("score_hints", {}),
    )