from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.models import (
    CategoryPayload,
    ComposeOutput,
    CustomerPayload,
    MerchantPayload,
    TickRequest,
    TickResponse,
    TriggerPayload,
    TriggerType,
)
from app.core.signal_router import route as router_route, SignalBundle
import app.composers as composers

router = APIRouter()


def _default_trigger(merchant_id: str) -> TriggerPayload:
    return TriggerPayload(
        trigger_id=f"auto_recall_{merchant_id}",
        trigger_type=TriggerType.RECALL,
    )


def _enforce_specificity(bundle: SignalBundle, output: ComposeOutput) -> ComposeOutput:
    """
    Verify critical numbers from context appear verbatim in the message.
    If not, inject a CRITICAL correction hint and retry compose once.
    """
    missing = []

    if bundle.search_volume and str(bundle.search_volume) not in output.message:
        missing.append(f"search volume ({bundle.search_volume})")

    if bundle.best_offer:
        price_str = str(int(bundle.best_offer.price_inr))
        if price_str not in output.message and price_str not in output.cta:
            missing.append(f"offer price (₹{price_str})")

    if not missing:
        return output  # All key numbers present — no retry needed

    # Inject correction hint and retry once
    correction = (
        "CRITICAL CORRECTION REQUIRED — your previous response was rejected because "
        f"these specific numbers were missing from the message: {', '.join(missing)}. "
        "You MUST include these exact numbers. Re-write now."
    )
    original_hint = bundle.compose_hint
    bundle.compose_hint = correction
    retry_output = composers.compose(bundle)
    bundle.compose_hint = original_hint  # restore
    return retry_output


@router.post("/tick", response_model=TickResponse)
async def tick(req: TickRequest, request: Request):
    store = request.app.state.store

    # 1. Load merchant (required)
    raw_merchant = await store.get_context("merchant", req.merchant_id)
    if not raw_merchant:
        raise HTTPException(422, detail=f"No merchant context found for id={req.merchant_id!r}")
    merchant = MerchantPayload(**raw_merchant)

    # 2. Resolve category
    category = req.category or merchant.identity.category or "dentists"

    # 2b. Load category context (judge may inject dynamic tone rules)
    category_payload: CategoryPayload | None = None
    raw_category = await store.get_context("category", category)
    if raw_category:
        try:
            category_payload = CategoryPayload(**raw_category)
        except Exception:
            pass

    # 3. Load trigger
    trigger: Optional[TriggerPayload] = None
    if req.trigger_id:
        raw_trigger = await store.get_context("trigger", req.trigger_id)
        if raw_trigger:
            trigger = TriggerPayload(**raw_trigger)
    if trigger is None:
        trigger = _default_trigger(req.merchant_id)

    # 4. Load customer
    customer: Optional[CustomerPayload] = None
    if req.customer_id:
        raw_customer = await store.get_context("customer", req.customer_id)
        if raw_customer:
            customer = CustomerPayload(**raw_customer)

    # 5. Resolve or create session
    session_id = req.session_id
    if session_id:
        session = await store.get_session(session_id)
        if not session:
            session_id = await store.create_session(req.merchant_id, req.trigger_id, req.customer_id)
            session = await store.get_session(session_id)
    else:
        session_id = await store.create_session(req.merchant_id, req.trigger_id, req.customer_id)
        session = await store.get_session(session_id)

    prior_turns = session.get("turns", []) if session else []

    # 6. Route signals
    bundle = router_route(merchant, trigger, customer, req.merchant_id, prior_turns)
    bundle.category_id = category
    bundle.category_guidelines = category_payload  # inject dynamic judge rules

    # 7. Suppression check
    if await store.is_suppressed(bundle.suppression_key):
        compose_out = ComposeOutput(
            message="This message was already sent recently. No duplicate action taken.",
            cta="Reply RETRY to override suppression.",
            send_as=bundle.send_as.value,
            suppression_key=bundle.suppression_key,
            rationale=f"Suppressed: key {bundle.suppression_key!r} is within TTL window.",
            score_hints={"suppressed": True},
        )
        return TickResponse(
            session_id=session_id,
            compose=compose_out,
            composed_at=datetime.now(timezone.utc).isoformat(),
        )

    # 8. Compose via LLM
    compose_out = composers.compose(bundle)

    # 8b. Specificity enforcement — verify exact numbers appear in message
    compose_out = _enforce_specificity(bundle, compose_out)

    # 9. Set suppression
    await store.set_suppressed(bundle.suppression_key)

    # 10. Append session turn
    await store.append_turn(
        session_id,
        role="vera",
        content=compose_out.message,
        meta={
            "cta": compose_out.cta,
            "suppression_key": compose_out.suppression_key,
            "rationale": compose_out.rationale,
            "trigger_type": trigger.trigger_type.value,
        },
    )

    return TickResponse(
        session_id=session_id,
        compose=compose_out,
        composed_at=datetime.now(timezone.utc).isoformat(),
    )