from __future__ import annotations
import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.models import MerchantPayload, ReplyOutput, ReplyRequest, ReplyResponse
from app.composers.base import build_context_block, call_llm
from app.core.signal_router import SignalBundle

router = APIRouter()

REPLY_SYSTEM = """You are Vera, Magicpin's AI growth assistant.

A merchant has replied to your previous outreach message. Your job is TWO-STEP:

STEP 1 — CLASSIFY INTENT from the merchant's reply text:
- "approved"           → yes / go ahead / confirm / send / proceed / ok / sure / haan / bilkul
- "objection_price"    → too expensive / high price / reduce / discount / cheaper / mahanga
- "objection_timing"   → not now / later / busy / tomorrow / baad mein / wait
- "objection_trust"    → not sure / sceptical / prove it / really? / doubtful / how do I know
- "question"           → any genuine question about how it works, reach, timing, etc.
- "cancelled"          → stop / cancel / no / nahi / not interested / band karo

CRITICAL: Classify based on DOMINANT intent. "I'm not sure if I should say yes" = objection_trust, NOT approved.
Nuanced example: "Yes, but can you reduce the price?" = objection_price (not approved — they conditioned it).

STEP 2 — COMPOSE follow-up grounded in context:
- approved:           Confirm exact action ("Sending to X nearby searchers now."), give concrete next step.
- objection_price:    Use discount_pct and original vs current price to justify value. Do not apologise.
- objection_timing:   Acknowledge, give a time-limited reason to act now (search window, slots remaining).
- objection_trust:    Use rating, rank, review count as social proof. Be factual, not defensive.
- question:           Answer directly using context numbers. No vague answers.
- cancelled:          Acknowledge gracefully, leave door open ("We'll be here when you're ready.").

OUTPUT — valid JSON only, no markdown:
{
  "intent_detected": "approved|objection_price|objection_timing|objection_trust|question|cancelled",
  "rationale": "Exactly which words/phrases in the reply signal this intent? Then: why this response strategy?",
  "message": "1-2 sentences. Must reference at least one specific number from context.",
  "cta": "One yes/no action or none if cancelled.",
  "send_as": "vera",
  "handoff": false,
  "score_hints": {}
}"""


def _preclass_intent(reply_text: str) -> str:
    """
    Lightweight safety-net classifier — used ONLY as the fallback label
    if the LLM call fails entirely. Not used to bias the LLM prompt.
    """
    t = reply_text.lower()
    # Check cancellation first (highest priority negative signal)
    if any(w in t for w in ["stop", "cancel", "not interested", "band karo", "nahi"]):
        return "cancelled"
    # Check objections before approvals (avoids "yes, but expensive" → approved)
    if any(w in t for w in ["expensive", "costly", "price", "discount", "cheaper", "reduce", "mahanga"]):
        return "objection_price"
    if any(w in t for w in ["later", "not now", "busy", "tomorrow", "baad mein", "wait"]):
        return "objection_timing"
    if any(w in t for w in ["not sure", "sceptical", "prove", "really", "doubt", "how do i know"]):
        return "objection_trust"
    # Only classify approved if no objection markers present
    if any(w in t for w in ["yes", "go ahead", "confirm", "proceed", "send it", "ok", "sure", "approved", "haan", "bilkul"]):
        return "approved"
    return "question"


@router.post("/reply", response_model=ReplyResponse)
async def reply(req: ReplyRequest, request: Request):
    store = request.app.state.store

    # Load session
    session = await store.get_session(req.session_id)
    if not session:
        raise HTTPException(404, detail=f"Session {req.session_id!r} not found")

    # Load merchant for context
    raw_merchant = await store.get_context("merchant", req.merchant_id)
    if not raw_merchant:
        raise HTTPException(422, detail=f"No merchant context for id={req.merchant_id!r}")
    merchant = MerchantPayload(**raw_merchant)

    # Build minimal bundle for context block
    from app.models import TriggerPayload, TriggerType
    dummy_trigger = TriggerPayload(trigger_id="reply", trigger_type=TriggerType.RECALL)
    bundle = SignalBundle(
        merchant=merchant,
        trigger=dummy_trigger,
        customer=None,
        category_id=merchant.identity.category or "dentists",
    )
    if merchant.offers:
        active = [o for o in merchant.offers if o.is_active]
        bundle.available_offers = active
        if active:
            bundle.best_offer = active[0]
            bundle.should_attach_offer = True

    context_block = build_context_block(bundle)

    # Get last Vera message for context
    last_vera_msg = "N/A"
    for turn in reversed(session.get("turns", [])):
        if turn.get("role") == "vera":
            last_vera_msg = turn.get("content", "N/A")
            break

    pre_intent = _preclass_intent(req.reply_text)

    user_prompt = (
        f'Merchant reply: "{req.reply_text}"\n\n'
        f"Previous Vera message: {last_vera_msg}\n\n"
        f"{context_block}\n\n"
        f"Classify intent and compose the follow-up response now."
    )

    raw = call_llm(REPLY_SYSTEM, user_prompt, max_tokens=500)

    # Parse response
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        data = json.loads(text)
    except Exception:
        data = {
            "intent_detected": pre_intent,
            "message": f"Understood! I'll proceed based on your reply.",
            "cta": "Reply YES to continue.",
            "send_as": "vera",
            "rationale": f"Keyword-classified intent: {pre_intent}",
            "handoff": False,
            "score_hints": {},
        }

    suppression_key = f"{req.session_id}:reply:{uuid.uuid4().hex[:6]}"

    compose_out = ReplyOutput(
        message=data.get("message", "")[:500],
        cta=data.get("cta", "Reply YES to continue.")[:200],
        send_as=data.get("send_as", "vera"),
        suppression_key=suppression_key,
        rationale=data.get("rationale", "")[:500],
        score_hints=data.get("score_hints", {}),
        intent_detected=data.get("intent_detected", pre_intent),
        handoff=data.get("handoff", False),
    )

    # Update session
    await store.append_turn(
        req.session_id,
        role=req.reply_from,
        content=req.reply_text,
        meta={"intent_detected": compose_out.intent_detected},
    )
    await store.append_turn(
        req.session_id,
        role="vera",
        content=compose_out.message,
        meta={"intent_detected": compose_out.intent_detected, "handoff": compose_out.handoff},
    )

    return ReplyResponse(
        session_id=req.session_id,
        compose=compose_out,
        composed_at=datetime.now(timezone.utc).isoformat(),
    )