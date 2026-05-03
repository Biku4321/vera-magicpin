from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ── Enums ──────────────────────────────────────────────────────────────────────

class TriggerType(str, Enum):
    RECALL   = "recall"
    SPIKE    = "spike"
    DIP      = "dip"
    RESEARCH = "research"
    FESTIVAL = "festival"
    CAMPAIGN = "campaign"
    REVIEW   = "review"


class UrgencyLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class SendAsIdentity(str, Enum):
    VERA     = "vera"
    MERCHANT = "merchant"
    PLATFORM = "platform"


class ChurnRisk(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class ContextScope(str, Enum):
    MERCHANT = "merchant"
    CUSTOMER = "customer"
    TRIGGER  = "trigger"
    CATEGORY = "category"


# ── Sub-models ─────────────────────────────────────────────────────────────────

class MerchantIdentity(BaseModel):
    merchant_id:  Optional[str]   = None
    name:         str
    category:     str
    locality:     str
    city:         str
    rating:       Optional[float] = None
    total_reviews: Optional[int]  = None


class MerchantPerformance(BaseModel):
    monthly_revenue_inr:          Optional[float] = None
    orders_last_7d:               Optional[int]   = None
    orders_prev_7d:               Optional[int]   = None
    revenue_last_7d:              Optional[float] = None
    revenue_prev_7d:              Optional[float] = None
    conversion_rate_pct:          Optional[float] = None
    rank_in_locality:             Optional[int]   = None
    total_merchants_in_locality:  Optional[int]   = None
    slow_days:                    Optional[List[str]] = None


class Offer(BaseModel):
    offer_id:           str
    title:              str
    price_inr:          float
    original_price_inr: Optional[float] = None
    discount_pct:       Optional[float] = None
    service_name:       Optional[str]   = None
    valid_till:         Optional[str]   = None
    is_active:          bool = True
    redemptions:        Optional[int]   = None
    max_redemptions:    Optional[int]   = None


class MerchantPayload(BaseModel):
    identity:    MerchantIdentity
    performance: Optional[MerchantPerformance] = None
    offers:      List[Offer] = Field(default_factory=list)
    digest:      Optional[List[Dict[str, Any]]] = None


class TriggerPayload(BaseModel):
    trigger_id:          str
    trigger_type:        TriggerType
    search_term:         Optional[str]   = None
    search_volume:       Optional[int]   = None
    festival_name:       Optional[str]   = None
    days_until_festival: Optional[int]   = None
    metric_name:         Optional[str]   = None
    metric_change_pct:   Optional[float] = None
    urgency:             Optional[UrgencyLevel] = None
    campaign_name:       Optional[str]   = None
    review_text:         Optional[str]   = None
    review_rating:       Optional[float] = None


class CustomerPayload(BaseModel):
    customer_id:        str
    name:               Optional[str]   = None
    last_visit_days_ago: Optional[int]  = None
    total_visits:       Optional[int]   = None
    avg_spend_inr:      Optional[float] = None
    preferred_services: Optional[List[str]] = None
    churn_risk:         Optional[ChurnRisk] = None
    consent_whatsapp:   bool = True


class CategoryPayload(BaseModel):
    category_id:    str
    tone_guidelines: Optional[str]  = None
    avoid_phrases:  Optional[List[str]] = None
    preferred_cta:  Optional[str]   = None


# ── API request/response models ────────────────────────────────────────────────

class ContextRequest(BaseModel):
    scope:        ContextScope
    context_id:   str
    version:      int
    payload:      Dict[str, Any]
    delivered_at: Optional[str] = None


class ContextResponse(BaseModel):
    accepted:   bool
    ack_id:     str
    stored_at:  str


class TickRequest(BaseModel):
    merchant_id: str
    trigger_id:  Optional[str] = None
    customer_id: Optional[str] = None
    category:    Optional[str] = None
    session_id:  Optional[str] = None


class ComposeOutput(BaseModel):
    message:         str
    cta:             str
    send_as:         str
    suppression_key: str
    rationale:       str
    score_hints:     Dict[str, Any] = Field(default_factory=dict)


class TickResponse(BaseModel):
    session_id:  str
    compose:     ComposeOutput
    composed_at: str


class ReplyRequest(BaseModel):
    session_id:  str
    merchant_id: str
    reply_text:  str
    reply_from:  str = "merchant"


class ReplyOutput(ComposeOutput):
    intent_detected: Optional[str] = None
    handoff:         bool = False


class ReplyResponse(BaseModel):
    session_id:  str
    compose:     ReplyOutput
    composed_at: str


class HealthResponse(BaseModel):
    status:  str
    ts:      str
    version: str


class MetadataResponse(BaseModel):
    name:                  str
    version:               str
    model:                 str
    supported_categories:  List[str]
    supported_triggers:    List[str]
    endpoints:             List[str]