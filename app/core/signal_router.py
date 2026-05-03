"""
Signal Router — the intelligence layer that runs BEFORE compose().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.models import (
    CustomerPayload,
    MerchantPayload,
    Offer,
    SendAsIdentity,
    TriggerPayload,
    TriggerType,
    UrgencyLevel,
)

URGENCY_RANK = {
    TriggerType.FESTIVAL: 5,
    TriggerType.SPIKE: 4,
    TriggerType.CAMPAIGN: 3,
    TriggerType.DIP: 3,
    TriggerType.REVIEW: 2,
    TriggerType.RECALL: 2,
    TriggerType.RESEARCH: 1,
}

URGENCY_LABEL = {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "minimal"}


@dataclass
class SignalBundle:
    # Raw payloads
    merchant: MerchantPayload
    trigger: TriggerPayload
    customer: Optional[CustomerPayload]
    category_id: str

    # Routed signals
    urgency_rank: int = 0
    urgency_label: str = "low"
    best_offer: Optional[Offer] = None
    suppression_key: str = ""
    send_as: SendAsIdentity = SendAsIdentity.VERA

    # Merchant state signals
    has_revenue_dip: bool = False
    has_traffic_spike: bool = False
    dip_pct: float = 0.0
    spike_pct: float = 0.0
    revenue_change_pct: float = 0.0
    is_top_ranked: bool = False
    rank_context: str = ""

    # Customer signals
    is_lapsed: bool = False
    days_since_visit: int = 0
    churn_risk: str = "low"
    customer_name: str = ""

    # Trigger specifics
    search_term: str = ""
    search_volume: int = 0
    festival_name: str = ""
    days_until_festival: int = 0
    metric_name: str = ""
    metric_change_pct: float = 0.0
    campaign_name: str = ""
    review_text: str = ""
    review_rating: float = 0.0

    # Compose hints
    should_attach_offer: bool = False
    available_offers: List[Offer] = field(default_factory=list)
    prior_turns: List[Dict[str, Any]] = field(default_factory=list)
    digest_items: List[Dict[str, Any]] = field(default_factory=list)
    compose_hint: Optional[str] = None
    digest_facts: Optional[str] = None
    category_guidelines: Optional[Any] = None  # CategoryPayload injected by tick.py

    # ── Flat aliases for base.py build_context_block() ──────────────────────
    @property
    def merchant_name(self) -> str:
        return self.merchant.identity.name

    @property
    def category(self) -> str:
        return self.category_id

    @property
    def locality(self) -> str:
        return self.merchant.identity.locality

    @property
    def city(self) -> str:
        return self.merchant.identity.city

    @property
    def rating(self) -> Optional[float]:
        return self.merchant.identity.rating

    @property
    def total_reviews(self) -> Optional[int]:
        return self.merchant.identity.total_reviews

    @property
    def rank_in_locality(self) -> Optional[int]:
        return self.merchant.performance.rank_in_locality if self.merchant.performance else None

    @property
    def total_merchants_in_locality(self) -> Optional[int]:
        return self.merchant.performance.total_merchants_in_locality if self.merchant.performance else None

    @property
    def orders_last_7d(self) -> Optional[int]:
        return self.merchant.performance.orders_last_7d if self.merchant.performance else None

    @property
    def orders_prev_7d(self) -> Optional[int]:
        return self.merchant.performance.orders_prev_7d if self.merchant.performance else None

    @property
    def monthly_revenue_inr(self) -> Optional[float]:
        return self.merchant.performance.monthly_revenue_inr if self.merchant.performance else None

    @property
    def conversion_rate_pct(self) -> Optional[float]:
        return self.merchant.performance.conversion_rate_pct if self.merchant.performance else None

    @property
    def slow_days(self) -> Optional[List[str]]:
        return self.merchant.performance.slow_days if self.merchant.performance else None

    @property
    def trigger_type(self) -> Optional[TriggerType]:
        return self.trigger.trigger_type if self.trigger else None

    @property
    def all_offers(self) -> List[Offer]:
        return [o for o in self.merchant.offers if o.is_active]

    @property
    def last_visit_days_ago(self) -> Optional[int]:
        return self.customer.last_visit_days_ago if self.customer else None

    @property
    def total_visits(self) -> Optional[int]:
        return self.customer.total_visits if self.customer else None

    @property
    def avg_spend_inr(self) -> Optional[float]:
        return self.customer.avg_spend_inr if self.customer else None

    @property
    def preferred_services(self) -> Optional[List[str]]:
        return self.customer.preferred_services if self.customer else None


class SignalRouter:
    """Class wrapper — tests call SignalRouter().route(...)"""
    def route(
        self,
        merchant: MerchantPayload,
        trigger: Optional[TriggerPayload],
        customer: Optional[CustomerPayload],
        merchant_id: str,
        session_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> SignalBundle:
        return route(merchant, trigger, customer, merchant_id, session_turns)


def route(
    merchant: MerchantPayload,
    trigger: Optional[TriggerPayload],
    customer: Optional[CustomerPayload],
    category_id: str,
    session_turns: Optional[List[Dict[str, Any]]] = None,
) -> SignalBundle:
    if trigger is None:
        trigger = TriggerPayload(
            trigger_id=f"auto_recall_{category_id}",
            trigger_type=TriggerType.RECALL,
        )

    bundle = SignalBundle(
        merchant=merchant,
        trigger=trigger,
        customer=customer,
        category_id=merchant.identity.category or category_id,
        prior_turns=session_turns or [],
        digest_items=merchant.digest or [],
    )

    _score_urgency(bundle)
    _extract_trigger_specifics(bundle)
    _analyze_merchant_performance(bundle)
    _analyze_customer(bundle)
    _select_best_offer(bundle)
    _parse_digest(bundle)
    _fusion_hints(bundle)
    _resolve_suppression_key(bundle, category_id)
    _resolve_send_as(bundle)
    return bundle


def _score_urgency(b: SignalBundle):
    rank = URGENCY_RANK.get(b.trigger.trigger_type, 1)
    if b.trigger.urgency == UrgencyLevel.CRITICAL:
        rank = max(rank, 5)
    elif b.trigger.urgency == UrgencyLevel.HIGH:
        rank = max(rank, 4)
    b.urgency_rank = rank
    b.urgency_label = URGENCY_LABEL.get(rank, "low")


def _extract_trigger_specifics(b: SignalBundle):
    t = b.trigger
    b.search_term = t.search_term or ""
    b.search_volume = t.search_volume or 0
    b.festival_name = t.festival_name or ""
    b.days_until_festival = t.days_until_festival or 0
    b.metric_name = t.metric_name or ""
    b.metric_change_pct = t.metric_change_pct or 0.0
    b.campaign_name = t.campaign_name or ""
    b.review_text = t.review_text or ""
    b.review_rating = t.review_rating or 0.0


def _analyze_merchant_performance(b: SignalBundle):
    p = b.merchant.performance
    if not p:
        return
    if p.revenue_last_7d and p.revenue_prev_7d and p.revenue_prev_7d > 0:
        change = (p.revenue_last_7d - p.revenue_prev_7d) / p.revenue_prev_7d * 100
        b.revenue_change_pct = round(change, 1)
        if change < -10:
            b.has_revenue_dip = True
            b.dip_pct = round(abs(change), 1)
    if p.orders_last_7d and p.orders_prev_7d and p.orders_prev_7d > 0:
        change = (p.orders_last_7d - p.orders_prev_7d) / p.orders_prev_7d * 100
        if change > 15:
            b.has_traffic_spike = True
            b.spike_pct = round(change, 1)
        elif change < -10 and not b.has_revenue_dip:
            b.has_revenue_dip = True
            b.dip_pct = round(abs(change), 1)
    if p.rank_in_locality and p.total_merchants_in_locality:
        b.is_top_ranked = p.rank_in_locality <= 3
        b.rank_context = (
            f"#{p.rank_in_locality} of {p.total_merchants_in_locality} "
            f"in {b.merchant.identity.locality}"
        )


def _analyze_customer(b: SignalBundle):
    if not b.customer:
        return
    c = b.customer
    b.customer_name = c.name or ""
    b.churn_risk = c.churn_risk.value if c.churn_risk else "low"
    if c.last_visit_days_ago is not None:
        b.days_since_visit = c.last_visit_days_ago
        b.is_lapsed = c.last_visit_days_ago >= 30


def _select_best_offer(b: SignalBundle):
    active = [o for o in b.merchant.offers if o.is_active]
    b.available_offers = active
    if not active:
        b.should_attach_offer = False
        return
    if b.search_term:
        term_lower = b.search_term.lower()
        matched = [
            o for o in active
            if (o.service_name and term_lower in o.service_name.lower())
            or (o.title and term_lower in o.title.lower())
        ]
        if matched:
            b.best_offer = sorted(matched, key=lambda o: o.discount_pct or 0, reverse=True)[0]
            b.should_attach_offer = True
            return
    if b.trigger.trigger_type == TriggerType.FESTIVAL:
        b.best_offer = sorted(active, key=lambda o: o.discount_pct or 0, reverse=True)[0]
        b.should_attach_offer = True
        return
    if b.is_lapsed:
        priced = [o for o in active if o.price_inr]
        if priced:
            b.best_offer = sorted(priced, key=lambda o: o.price_inr or 9999)[0]
            b.should_attach_offer = True
            return
    discounted = [o for o in active if o.discount_pct]
    b.best_offer = sorted(discounted, key=lambda o: o.discount_pct or 0, reverse=True)[0] if discounted else active[0]
    b.should_attach_offer = True


def _parse_digest(b: SignalBundle):
    if not b.digest_items:
        return

    # Map known digest item keys → their display label for the LLM
    TYPE_LABELS: Dict[str, str] = {
        "alert":       "URGENT MARKET ALERT",
        "competitor":  "COMPETITOR INTEL",
        "review":      "REPUTATION DATA",
        "fact":        "MARKET FACT",
        "insight":     "STRATEGIC INSIGHT",
        "note":        "PLATFORM NOTE",
        "campaign":    "ACTIVE CAMPAIGN",
        "text":        "CONTEXT NOTE",
        "message":     "CONTEXT NOTE",
    }

    lines = []
    for item in b.digest_items:
        if not isinstance(item, dict):
            continue
        # Try to find a known typed key first
        matched = False
        for key, label in TYPE_LABELS.items():
            if key in item:
                lines.append(f"{label}: {item[key]}")
                matched = True
                break
        if not matched:
            # Fallback: dump all non-null key-value pairs as a CONTEXT NOTE
            parts = [f"{k}={v}" for k, v in item.items() if v is not None]
            if parts:
                lines.append("CONTEXT NOTE: " + "; ".join(parts))

    if lines:
        b.digest_facts = "\n".join(lines)


def _fusion_hints(b: SignalBundle):
    p = b.merchant.performance
    conv = p.conversion_rate_pct if p else None
    if b.trigger.trigger_type == TriggerType.SPIKE and conv is not None:
        if conv < 10:
            b.compose_hint = "low_conversion_spike"
        elif conv > 20:
            b.compose_hint = "high_conversion_spike"
    if b.trigger.trigger_type == TriggerType.DIP and b.slow_days:
        b.compose_hint = "dip_with_slow_days"
    if b.is_lapsed and b.trigger.trigger_type == TriggerType.RECALL:
        b.compose_hint = "lapsed_recall"


def _resolve_suppression_key(b: SignalBundle, merchant_id: str):
    slug = merchant_id.lower().replace(" ", "_")
    trigger_part = b.trigger.trigger_type.value
    offer_part = b.best_offer.offer_id if b.best_offer else "no_offer"
    customer_part = b.customer.customer_id if b.customer else "broadcast"
    date_bucket = date.today().strftime("%Y-%W")
    b.suppression_key = f"{slug}:{trigger_part}:{offer_part}:{customer_part}:{date_bucket}"


def _resolve_send_as(b: SignalBundle):
    if b.customer:
        b.send_as = SendAsIdentity.MERCHANT
    elif b.trigger.trigger_type == TriggerType.CAMPAIGN:
        b.send_as = SendAsIdentity.MERCHANT
    else:
        b.send_as = SendAsIdentity.VERA