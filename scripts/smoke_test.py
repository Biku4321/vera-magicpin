"""
Smoke test — run this with the server live to verify end-to-end Gemini output.

Usage:
    # Terminal 1
    uvicorn main:app --reload --port 8000

    # Terminal 2
    python scripts/smoke_test.py
"""
import json
import sys
import httpx

BASE = "http://localhost:8000"


def ok(label: str, r: httpx.Response):
    if r.status_code not in (200, 201):
        print(f"  FAIL [{label}] status={r.status_code} body={r.text[:300]}")
        sys.exit(1)
    data = r.json()
    print(f"  OK   [{label}] status={r.status_code}")
    return data


def main():
    client = httpx.Client(base_url=BASE, timeout=60)

    print("\n=== 1. Health check ===")
    ok("healthz", client.get("/v1/healthz"))
    ok("metadata", client.get("/v1/metadata"))

    print("\n=== 2. Store merchant context ===")
    merchant_payload = {
        "scope": "merchant",
        "context_id": "m_smoke_drmeera",
        "version": 1,
        "payload": {
            "identity": {
                "merchant_id": "m_smoke_drmeera",
                "name": "Dr Meera Dental Clinic",
                "category": "dentists",
                "locality": "Koramangala",
                "city": "Bangalore",
                "rating": 4.7,
                "total_reviews": 312,
            },
            "performance": {
                "monthly_revenue_inr": 185000,
                "orders_last_7d": 34,
                "orders_prev_7d": 41,
                "conversion_rate_pct": 14.2,
                "rank_in_locality": 2,
                "total_merchants_in_locality": 18,
            },
            "offers": [
                {
                    "offer_id": "o_001",
                    "title": "Dental Check-Up Package",
                    "price_inr": 299,
                    "original_price_inr": 799,
                    "discount_pct": 63,
                    "service_name": "Dental Check Up",
                    "valid_till": "2026-05-31",
                    "is_active": True,
                    "redemptions": 12,
                    "max_redemptions": 50,
                }
            ],
        },
    }
    ok("store merchant", client.post("/v1/context", json=merchant_payload))

    print("\n=== 3. Store trigger context ===")
    trigger_payload = {
        "scope": "trigger",
        "context_id": "t_smoke_spike",
        "version": 1,
        "payload": {
            "trigger_id": "t_smoke_spike",
            "trigger_type": "spike",
            "search_term": "Dental Check Up",
            "search_volume": 190,
            "urgency": "high",
        },
    }
    ok("store trigger", client.post("/v1/context", json=trigger_payload))

    print("\n=== 4. Tick — compose message ===")
    tick_payload = {
        "merchant_id": "m_smoke_drmeera",
        "trigger_id": "t_smoke_spike",
        "category": "dentists",
    }
    tick_data = ok("tick", client.post("/v1/tick", json=tick_payload))

    compose = tick_data.get("compose", {})
    message = compose.get("message", "")
    cta = compose.get("cta", "")
    rationale = compose.get("rationale", "")
    session_id = tick_data.get("session_id", "")

    print(f"\n  Message  : {message}")
    print(f"  CTA      : {cta}")
    print(f"  Rationale: {rationale[:200]}...")
    print(f"  Session  : {session_id}")

    # Verify grounding — message should contain real numbers
    checks = {
        "190 in message": "190" in message,
        "299 in message": "299" in message or "299" in cta,
        "Koramangala in message": "Koramangala" in message,
        "rationale non-empty": len(rationale) > 30,
    }
    print("\n=== 5. Grounding checks ===")
    all_ok = True
    for check, passed in checks.items():
        status = "PASS" if passed else "WARN"
        print(f"  {status}  {check}")
        if not passed:
            all_ok = False

    print("\n=== 6. Reply flow ===")
    reply_payload = {
        "session_id": session_id,
        "merchant_id": "m_smoke_drmeera",
        "reply_text": "Yes, go ahead and send it!",
        "reply_from": "merchant",
    }
    reply_data = ok("reply", client.post("/v1/reply", json=reply_payload))
    intent = reply_data.get("compose", {}).get("intent_detected", "?")
    print(f"  Intent detected: {intent}")
    assert intent == "approved", f"Expected 'approved', got {intent!r}"
    print("  PASS  intent=approved")

    print(f"\n{'='*50}")
    if all_ok:
        print("ALL CHECKS PASSED ✓ — Vera is ready for submission.")
    else:
        print("SOME GROUNDING CHECKS FAILED — tune the prompts if numbers are missing.")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
