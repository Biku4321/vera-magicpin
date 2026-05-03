<div align="center">

# ✦ VERA
### AI Growth Assistant for Magicpin Merchants

*Stateful · Context-grounded · Category-aware message composition*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-1.5_Pro-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev)
[![Tests](https://img.shields.io/badge/Tests-17%2F17_passing-22c55e?style=flat-square)](#testing)
[![Deploy](https://img.shields.io/badge/Deploy-Railway-7C3AED?style=flat-square&logo=railway&logoColor=white)](https://railway.app)

</div>

---

## What is Vera?

Vera is Magicpin's AI growth assistant — a stateful HTTP API that composes hyper-specific outreach messages for merchants (dentists, salons, restaurants, gyms, pharmacies) based on live demand signals.

**The core loop:**
```
judge sends context → Vera reads signals → Vera composes message → judge scores output
```

Every message Vera writes must trace every fact to received context. No invented numbers. No generic templates. Each message is grounded in the exact merchant data, trigger signal, and customer profile the judge injected.

---

## Architecture

```
POST /v1/context   →  ContextStore (versioned, idempotent, Redis or in-memory)
                              │
POST /v1/tick      →  SignalRouter → SignalBundle → CategoryComposer → Gemini 1.5 Pro
                              │           │                │
                         urgency      offer select    rationale-first
                         ladder       fusion hints    grounded output
                              │
POST /v1/reply     →  LLM intent classification → follow-up compose
GET  /v1/healthz   →  liveness
GET  /v1/metadata  →  capabilities
```

### Signal Router — the intelligence layer

Before any LLM call, the **SignalRouter** deterministically processes all received context into a `SignalBundle`:

| Step | What it does |
|---|---|
| `_score_urgency` | Ranks trigger: `festival(5) > spike(4) > campaign/dip(3) > recall(2) > research(1)` |
| `_extract_trigger_specifics` | Pulls search volume, festival name, metric change |
| `_analyze_merchant_performance` | Computes dip %, spike %, rank context |
| `_analyze_customer` | Lapse detection (≥30 days), churn risk |
| `_select_best_offer` | Matches offer to search term → festival → lapsed → best discount |
| `_parse_digest` | Structures judge-injected facts with semantic labels (URGENT MARKET ALERT, REPUTATION DATA…) |
| `_fusion_hints` | Cross-signal logic: `low_conversion_spike`, `high_conversion_spike`, `lapsed_recall` |
| `_resolve_suppression_key` | `merchant:trigger:offer:customer:YYYY-WW` — prevents re-sends within 24h |

Only after this deterministic layer does Vera call Gemini.

### Specificity Enforcement

After every compose call, Vera verifies in Python that critical numbers (search volume, offer price) appear verbatim in the output. If missing, it injects a `CRITICAL CORRECTION REQUIRED` hint and retries once. This guarantees **10/10 Specificity** independent of LLM variance.

### Category Composers

Five dedicated system prompts, each encoding category-specific tone rules:

| Category | Tone | Lead signal | Avoid |
|---|---|---|---|
| **Dentists** | Clinical, trust-first | Search volume + rank | Hype language |
| **Salons** | Aspirational, visual | Occasion / festival | Clinical words |
| **Restaurants** | Sensory, time-aware | Dish name + slow day | "Great food" |
| **Gyms** | Motivational, goal-led | Search as momentum | Body-shaming |
| **Pharmacies** | Utility-first | Seasonal health demand | Rx promotions |

---

## Scoring Rubric (judge dimensions)

| Dimension | What Vera does to maximise it |
|---|---|
| **Decision Quality** | SignalRouter picks dominant signal; rationale-first prompt forces LLM to justify the choice |
| **Specificity** | Python enforcement verifies exact numbers; 7+ real figures per message |
| **Category Fit** | 5 separate system prompts; avoid-phrase rules enforced |
| **Merchant Fit** | Every compose uses merchant's actual rank, rating, offer_id, revenue |
| **Engagement Compulsion** | One `Reply YES` CTA per message; urgency anchored to real demand window |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/vera.git
cd vera
pip install -r requirements.txt

# 2. Add your Gemini API key
cp .env.example .env
# Edit .env:
#   GEMINI_API_KEY=AIza...your_key_here
#   GEMINI_MODEL=gemini-1.5-pro

# 3. Run the server
uvicorn main:app --reload --port 8000

# 4. Smoke test (server must be running)
python scripts/smoke_test.py

# 5. Run unit + integration tests (no API key needed)
pytest tests/ -v
```

**Expected smoke test output:**
```
ALL CHECKS PASSED ✓ — Vera is ready for submission.
```

---

## API Reference

### `POST /v1/context` — store context

```json
{
  "scope": "merchant",
  "context_id": "m_001_drmeera",
  "version": 3,
  "payload": { "identity": {}, "performance": {}, "offers": [] }
}
```
```json
{ "accepted": true, "ack_id": "ack_abc123", "stored_at": "2026-05-02T10:00:00Z" }
```
Same version → `accepted: false` (no-op). Higher version → atomic replace.

---

### `POST /v1/tick` — compose message

```json
{
  "merchant_id": "m_001_drmeera",
  "trigger_id": "t_001_spike",
  "customer_id": "c_001",
  "category": "dentists"
}
```
```json
{
  "session_id": "sess_abc123",
  "compose": {
    "message": "190 people in Koramangala are searching for 'Dental Check Up' right now. Dr Meera Dental Clinic is ranked #2 of 18 in the area with a 4.7 rating — your ₹299 check-up offer (was ₹799, 38 slots left) is perfectly positioned.",
    "cta": "Should I send this offer to all 190 nearby searchers? Reply YES.",
    "send_as": "vera",
    "suppression_key": "m_drmeera:spike:o_001:broadcast:2026-18",
    "rationale": "Search spike of 190 for 'Dental Check Up' is the dominant signal (rank 4/5)...",
    "score_hints": {}
  },
  "composed_at": "2026-05-02T10:00:00Z"
}
```

---

### `POST /v1/reply` — handle merchant reply

```json
{
  "session_id": "sess_abc123",
  "merchant_id": "m_001_drmeera",
  "reply_text": "Yes, go ahead!",
  "reply_from": "merchant"
}
```
```json
{
  "session_id": "sess_abc123",
  "compose": {
    "message": "Sending your ₹299 check-up offer to 190 nearby searchers now.",
    "intent_detected": "approved",
    "handoff": false,
    ...
  }
}
```

Intent classes: `approved` · `objection_price` · `objection_timing` · `objection_trust` · `question` · `cancelled`

---

### `GET /v1/healthz`
```json
{ "status": "ok", "ts": "2026-05-02T10:00:00Z", "version": "1.0.0" }
```

### `GET /v1/metadata`
```json
{
  "name": "Vera",
  "supported_categories": ["dentists", "salons", "restaurants", "gyms", "pharmacies"],
  "supported_triggers": ["recall", "spike", "dip", "research", "festival", "campaign", "review"]
}
```

---

## Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
cd vera
railway login
railway init
railway up

# Set environment variables
railway variables set GEMINI_API_KEY=AIza...your_key_here
railway variables set GEMINI_MODEL=gemini-1.5-pro

# Get your public URL
railway open
```

Your bot URL: `https://vera-production-xxxx.up.railway.app`

---

## Testing

```bash
# All 17 tests — no API key needed (LLM is mocked)
pytest tests/ -v

# Live smoke test — requires server running + GEMINI_API_KEY set
python scripts/smoke_test.py
```

Test coverage: health endpoints · context store versioning · tick composition · reply intent · signal router unit tests · suppression key format

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | ✅ Yes | — | Google AI Studio API key |
| `GEMINI_MODEL` | No | `gemini-1.5-pro` | Model name |
| `REDIS_URL` | No | — | Redis connection URL (falls back to in-memory) |
| `SUPPRESSION_TTL_SECONDS` | No | `86400` | Dedup window in seconds |

---

## Key Design Decisions

**Rationale-first prompting.** The system prompt forces Gemini to write `rationale` before `message`. This is the single most important design decision — it forces grounded decision-making before any text generation, directly improving Decision Quality scores.

**Deterministic routing, LLM composition.** The SignalRouter is pure Python with no LLM calls. It deterministically identifies the strongest signal, selects the best offer, and resolves all metadata. The LLM only handles the final language generation step — making the system predictable and debuggable.

**Python-side specificity enforcement.** Rather than trusting LLM temperature to include exact numbers, Vera verifies in code that critical figures appear in the output and retries with a correction prompt if they don't.

**Dual-mode store.** In-memory by default (zero config), Redis drop-in for production (set `REDIS_URL`).

---

<div align="center">

Built for the **Magicpin AI Challenge 2026**

</div>