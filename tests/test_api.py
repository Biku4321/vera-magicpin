"""
Full end-to-end test suite for Vera.
LLM calls are mocked — no GEMINI_API_KEY needed.
Run: pytest tests/ -v
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Patch Gemini before importing app
MOCK_LLM_RESPONSE = '''{
  "rationale": "Search spike of 190 is dominant signal. Offer o_001 matches search term. Spike rank 4 > dip rank 3.",
  "message": "190 people in Koramangala are searching for 'Dental Check Up' right now. Dr Meera Dental Clinic is ranked #2 of 18 in the area with a 4.7 rating — your ₹299 check-up offer (was ₹799, 38 slots left) is perfectly positioned.",
  "cta": "Should I send this offer to all 190 nearby searchers? Reply YES.",
  "send_as": "vera",
  "score_hints": {
    "decision_quality": "Spike rank 4 chosen over dip rank 3",
    "specificity": "Used: 190, Koramangala, #2 of 18, 4.7, ₹299, ₹799, 38",
    "category_fit": "Clinical: check-up not deal, patient-benefit language"
  }
}'''


@pytest.fixture(autouse=True)
def mock_gemini():
    with patch("app.composers.base.get_client") as mock_get:
        mock_model = MagicMock()
        mock_resp  = MagicMock()
        mock_resp.text = MOCK_LLM_RESPONSE
        mock_model.generate_content.return_value = mock_resp
        mock_get.return_value = mock_model
        yield mock_get


@pytest.fixture
def client():
    from main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Fixtures: canonical Dr Meera scenario ────────────────────────────────────

MERCHANT_PAYLOAD = {
    "identity": {
        "name":         "Dr Meera Dental Clinic",
        "category":     "dentists",
        "locality":     "Koramangala",
        "city":         "Bangalore",
        "rating":       4.7,
        "total_reviews": 312,
    },
    "performance": {
        "monthly_revenue_inr":         185000,
        "orders_last_7d":              34,
        "orders_prev_7d":              41,
        "conversion_rate_pct":         14.5,
        "rank_in_locality":            2,
        "total_merchants_in_locality": 18,
    },
    "offers": [{
        "offer_id":           "o_001",
        "title":              "Dental Check-Up Package",
        "price_inr":          299,
        "original_price_inr": 799,
        "discount_pct":       62.6,
        "service_name":       "Dental Check Up",
        "is_active":          True,
        "redemptions":        12,
        "max_redemptions":    50,
    }],
}

TRIGGER_PAYLOAD = {
    "trigger_id":   "t_001_spike",
    "trigger_type": "spike",
    "search_term":  "Dental Check Up",
    "search_volume": 190,
    "urgency":      "high",
}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_healthz(self, client):
        r = client.get("/v1/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "ts" in data
        assert data["version"] == "1.0.0"

    def test_metadata(self, client):
        r = client.get("/v1/metadata")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Vera"
        assert "dentists" in data["supported_categories"]
        assert "spike" in data["supported_triggers"]
        assert data["model"] == "gemini-1.5-pro"
        assert len(data["endpoints"]) == 5

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200


class TestContext:
    def test_store_merchant_context(self, client):
        r = client.post("/v1/context", json={
            "scope":      "merchant",
            "context_id": "m_test_001",
            "version":    1,
            "payload":    MERCHANT_PAYLOAD,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["accepted"] is True
        assert data["ack_id"].startswith("ack_")

    def test_same_version_rejected(self, client):
        client.post("/v1/context", json={
            "scope": "merchant", "context_id": "m_test_v", "version": 1, "payload": MERCHANT_PAYLOAD
        })
        r = client.post("/v1/context", json={
            "scope": "merchant", "context_id": "m_test_v", "version": 1, "payload": MERCHANT_PAYLOAD
        })
        assert r.json()["accepted"] is False

    def test_higher_version_accepted(self, client):
        client.post("/v1/context", json={
            "scope": "merchant", "context_id": "m_test_vv", "version": 1, "payload": MERCHANT_PAYLOAD
        })
        r = client.post("/v1/context", json={
            "scope": "merchant", "context_id": "m_test_vv", "version": 2, "payload": MERCHANT_PAYLOAD
        })
        assert r.json()["accepted"] is True

    def test_store_trigger_context(self, client):
        r = client.post("/v1/context", json={
            "scope": "trigger", "context_id": "t_test_001", "version": 1, "payload": TRIGGER_PAYLOAD
        })
        assert r.status_code == 200
        assert r.json()["accepted"] is True


class TestTick:
    def _setup(self, client, merchant_id="m_tick_test", trigger_id="t_tick_test"):
        client.post("/v1/context", json={
            "scope": "merchant", "context_id": merchant_id, "version": 1, "payload": MERCHANT_PAYLOAD
        })
        client.post("/v1/context", json={
            "scope": "trigger", "context_id": trigger_id, "version": 1, "payload": TRIGGER_PAYLOAD
        })
        return merchant_id, trigger_id

    def test_tick_basic(self, client):
        mid, tid = self._setup(client)
        r = client.post("/v1/tick", json={"merchant_id": mid, "trigger_id": tid})
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data
        assert "compose" in data
        c = data["compose"]
        assert "message" in c
        assert "cta" in c
        assert "suppression_key" in c
        assert "rationale" in c
        assert c["send_as"] in ("vera", "merchant", "platform")

    def test_tick_no_merchant_returns_422(self, client):
        r = client.post("/v1/tick", json={"merchant_id": "nonexistent_merchant_xyz"})
        assert r.status_code == 422

    def test_tick_without_trigger_uses_recall(self, client):
        mid = "m_recall_test"
        client.post("/v1/context", json={
            "scope": "merchant", "context_id": mid, "version": 1, "payload": MERCHANT_PAYLOAD
        })
        r = client.post("/v1/tick", json={"merchant_id": mid})
        assert r.status_code == 200
        assert "compose" in r.json()

    def test_tick_returns_session_id(self, client):
        mid, tid = self._setup(client, "m_sess_test", "t_sess_test")
        r1 = client.post("/v1/tick", json={"merchant_id": mid, "trigger_id": tid})
        sess = r1.json()["session_id"]
        assert sess.startswith("sess_")

    def test_tick_compose_contains_numbers(self, client):
        """The mocked LLM response contains real numbers from context."""
        mid, tid = self._setup(client, "m_num_test", "t_num_test")
        r = client.post("/v1/tick", json={"merchant_id": mid, "trigger_id": tid})
        msg = r.json()["compose"]["message"]
        assert "190" in msg   # search volume from trigger
        assert "299" in msg   # offer price


class TestReply:
    def _full_setup(self, client):
        mid, tid = "m_reply_m", "t_reply_t"
        client.post("/v1/context", json={
            "scope": "merchant", "context_id": mid, "version": 1, "payload": MERCHANT_PAYLOAD
        })
        client.post("/v1/context", json={
            "scope": "trigger", "context_id": tid, "version": 1, "payload": TRIGGER_PAYLOAD
        })
        tick_r = client.post("/v1/tick", json={
            "merchant_id": mid,
            "trigger_id":  tid,
        })
        return mid, tick_r.json()["session_id"]

    def test_reply_approved(self, client):
        mid, sess = self._full_setup(client)
        r = client.post("/v1/reply", json={
            "session_id":  sess,
            "merchant_id": mid,
            "reply_text":  "Yes, go ahead!",
            "reply_from":  "merchant",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sess
        assert "intent_detected" in data["compose"]

    def test_reply_unknown_session(self, client):
        r = client.post("/v1/reply", json={
            "session_id":  "sess_nonexistent_xyz",
            "merchant_id": "m_any",
            "reply_text":  "Yes",
            "reply_from":  "merchant",
        })
        assert r.status_code == 404


class TestSignalRouterUnit:
    """Unit tests for signal router — no HTTP, no LLM."""

    def test_spike_urgency_rank(self):
        from app.core.signal_router import SignalRouter
        from app.models import MerchantPayload, TriggerPayload, TriggerType

        router = SignalRouter()
        merchant = MerchantPayload(**MERCHANT_PAYLOAD)
        trigger  = TriggerPayload(**TRIGGER_PAYLOAD)

        bundle = router.route(merchant, trigger, None, "m_unit_test")
        assert bundle.urgency_rank == 4   # SPIKE = 4
        assert bundle.search_term  == "Dental Check Up"
        assert bundle.search_volume == 190

    def test_best_offer_selected_by_search_term(self):
        from app.core.signal_router import SignalRouter
        from app.models import MerchantPayload, TriggerPayload

        router   = SignalRouter()
        merchant = MerchantPayload(**MERCHANT_PAYLOAD)
        trigger  = TriggerPayload(**TRIGGER_PAYLOAD)
        bundle   = router.route(merchant, trigger, None, "m_offer_test")

        assert bundle.best_offer is not None
        assert bundle.best_offer.offer_id == "o_001"

    def test_suppression_key_format(self):
        from app.core.signal_router import SignalRouter
        from app.models import MerchantPayload, TriggerPayload

        router   = SignalRouter()
        merchant = MerchantPayload(**MERCHANT_PAYLOAD)
        trigger  = TriggerPayload(**TRIGGER_PAYLOAD)
        bundle   = router.route(merchant, trigger, None, "m_supp_test")

        key = bundle.suppression_key
        parts = key.split(":")
        assert len(parts) == 5   # slug:trigger:offer:customer:week
        assert parts[1] == "spike"
        assert parts[2] == "o_001"
        assert parts[3] == "broadcast"