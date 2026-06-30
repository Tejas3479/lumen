# Lumen — AI Pipeline

## Overview

The Lumen AI pipeline automatically classifies each newly submitted civic issue into one of six categories, assigns a severity level, and produces a confidence score — all asynchronously so the user receives an immediate response from the API without waiting for AI processing.

---

## Pipeline Architecture

```
POST /issues (FastAPI)
        │
        ├─ 201 Created → client gets IssueOut immediately
        │
        └─ categorize_issue_task.delay(issue_id, image_path, description)
                │
                ▼
        Celery Worker (Redis broker)
                │
                ├─ 1. Load image from disk → base64 encode
                ├─ 2. Build prompt (system + user message with image_url part)
                ├─ 3. Call Google Gemini 3.5 Flash (primary)
                │     └─ on error → Fallback: OpenAI GPT-4o (vision/text)
                │                   └─ on error → Default fallback result (confidence=0.0)
                ├─ 4. Parse JSON response
                ├─ 5. Update Issue row in DB
                │     (ai_category, ai_severity, ai_confidence, ai_explanation, ai_summary, ai_reasoning, ai_alternatives)
                ├─ 6. Write Redis cache: lumen:ai_result:{issue_id} (TTL 5 min)
                └─ 7. Publish ai_result event to Redis pub/sub channel
                        │
                        ▼
                FastAPI startup subscriber (asyncio task)
                        │
                        └─ emit ai_result Socket.IO event → connected client
                                │
                                ▼
                        Client UI updates AIExplanationCard
```

---

## Google AI Integration

Lumen uses Google AI as the primary intelligence layer:

### Primary: Google Gemini 3.5 Flash
- Model: gemini-3.5-flash
- Used for: Issue categorization from images and text
- Why Gemini: Fast (sub-2s), multimodal, cost-effective, supports JSON mode
- Prompt: Chain-of-thought with 3 few-shot examples
- JSON mode (responseMimeType): Forces clean JSON output without markdown fences

### Primary Embeddings: Google text-embedding-004
- Used for: Semantic duplicate detection
- Why text-embedding-004: Optimised for English + Indian language text — better than sentence-transformers for civic descriptions that mix English with local place names and street terms

### Fallbacks (OpenAI)
- If Gemini is unavailable: GPT-4o handles classification
- If Gemini embeddings fail: sentence-transformers handles similarity
- Final fallback: Jaccard word overlap

---

## Model Selection Rationale

| Model | Role | Trigger Condition |
|-------|------|-------------------|
| **Gemini 3.5 Flash** (`gemini-3.5-flash`) | Primary | Always attempted first |
| **GPT-4o** (`gpt-4o`) | Fallback | Gemini call fails (timeout, rate limit, API error) |

**Why Gemini 3.5 Flash as primary?**
- Highly cost-effective and extremely fast visual reasoning (typically sub-2s).
- Native structured JSON output mode (via `responseMimeType: "application/json"`).
- Large context window enabling robust few-shot prompting.

**Why OpenAI GPT-4o as fallback?**
- Serves as a highly reliable fallback for classification if the Gemini service is unavailable.
- Deep visual and text understanding provides true vendor redundancy.

**Default fallback:**
- If both APIs fail, the pipeline falls back to a zero-confidence ("other", confidence=0.0) placeholder to alert administrators.

---

## Prompt Design

### System Prompt

The system prompt is fixed and version-controlled in `app/services/ai_categorizer.py`:

```
You are a civic infrastructure analyst for an Indian city.
Analyze the submitted image and/or description to classify a community issue.

Categories (use ONLY one of these exact values):
- pothole          → road surface damage, cracks, depressions
- water_leakage    → pipe bursts, leaks, water on road, flooding from pipes
- streetlight      → broken, dark, or dangerously damaged street lights
- garbage          → uncollected waste, illegal dumping, overflowing bins
- drainage         → blocked drains, stormwater flooding, open manholes
- other            → footpath damage, road markings, trees, other infrastructure

Severity (use ONLY one of these exact values):
- low      → minor inconvenience, no immediate risk
- medium   → significant issue affecting daily life
- high     → dangerous or affecting many people
- critical → immediate safety risk, life-threatening, or causing accidents
```

### Six Categories

| Category | Trigger Keywords | Common Visual Signatures |
|----------|-----------------|--------------------------|
| `pothole` | road damage, crater, depression | Broken asphalt, exposed aggregate |
| `water_leakage` | leak, burst pipe, flooding | Standing water, pipe spray |
| `streetlight` | dark, broken light, lamp post | Tilted poles, shattered housings |
| `garbage` | waste, dumping, bins overflowing | Scattered debris, black bags |
| `drainage` | drain blocked, flooding, manhole | Open manholes, waterlogged roads |
| `other` | footpath, road marking, tree, other | Everything else |

### Four Severity Levels

| Level | Definition | Example |
|-------|------------|---------|
| `low` | Minor inconvenience, no immediate risk | Faded road marking |
| `medium` | Affects daily life, not an emergency | Partially blocked drain |
| `high` | Dangerous or affecting many people | Large pothole on busy road |
| `critical` | Immediate safety risk / life-threatening | Open deep manhole at night |

### Response Contract

The AI is instructed to return **only** valid JSON matching the schema, with explicit chain-of-thought reasoning and alternatives considered:

```json
{
  "category": "pothole",
  "severity": "high",
  "confidence": 0.91,
  "explanation": "Road surface shows a 45cm depression with exposed aggregate material on a high-traffic lane.",
  "summary": "Large pothole on road",
  "reasoning": "Visible sub-base exposure and crack patterns around the depression suggest active asphalt erosion from heavy traffic.",
  "alternative_categories": {
    "road_damage": 0.12
  },
  "is_emergency": false
}
```

---

## Response Parsing and Fallback Behaviour

`_parse_ai_response(raw: str) → dict` handles:

1. **Happy path**: raw string is valid JSON → `json.loads(raw)`.
2. **Markdown fences**: AI wraps response in ` ```json ... ``` ` → strip fences, then parse.
3. **Invalid JSON**: Log warning, return default safe response:
   ```json
   {
     "category": "other",
     "severity": "medium",
     "confidence": 0.0,
     "explanation": "AI classification failed — please review manually.",
     "summary": "Classification unavailable",
     "reasoning": "",
     "alternative_categories": {},
     "is_emergency": false
   }
   ```
4. **Category not in allowed list**: Coerce to `"other"`.
5. **Severity not in allowed list**: Coerce to `"medium"`.

This ensures the database always receives a valid, parseable AI result with all reasoning and alternatives fields populated even when the model misbehaves.

---

## User Correction Flow (RLHF-Lite)

When a user disagrees with the AI result, they can submit a correction:

```
POST /ai/feedback
{
  "issue_id": "uuid",
  "corrected_category": "water_leakage",
  "corrected_severity": "critical",
  "user_comment": "This is not a pothole, it's a burst water main"
}
```

**Server actions:**
1. Load issue from DB.
2. Capture before-state (`ai_category`, `ai_severity`, `category_id`, `severity`).
3. Resolve `corrected_category` name → `category_id` UUID in DB.
4. Update `issue.category_id` and `issue.severity` (user correction is authoritative).
5. Set `issue.user_correction = True`.
6. Write `IssueAuditLog` entry with `action="ai_correction"` and full before/after state.
7. Return `{status: "correction_logged"}`.

**Future fine-tuning:**
The audit log is queryable to extract `(original_category, corrected_category, image_path)` triplets for supervised fine-tuning of a custom model. No model retraining occurs in v1.

---

## Redis Bridge: Celery → Socket.IO

Celery workers run in a separate process from the FastAPI application and cannot directly call Socket.IO methods. The bridge uses Redis pub/sub:

```
Celery Worker:
  redis_client.publish("lumen:socket_events", json.dumps({
      "event": "ai_result",
      "room": f"issue_{issue_id}",
      "data": {...}
  }))

FastAPI startup (asyncio task):
  async with redis.subscribe("lumen:socket_events") as channel:
      async for message in channel:
          payload = json.loads(message)
          await sio.emit(payload["event"], payload["data"], room=payload["room"])
```

This pattern is used for all Celery-generated events: `ai_result`, `leaderboard_update`, `hotspot_update`.

---

## Frontend Polling Fallback (60-Second Timeout)

To handle cases where WebSocket connections fail or are blocked by client firewalls:
1. When a client submits an issue, it listens to the `ai_result` Socket.IO event.
2. Simultaneously, a fallback timer starts.
3. If no WebSocket event is received within **60 seconds**, the frontend falls back to polling `GET /ai/status/{issue_id}`.
4. It polls every 5 seconds up to 3 times. If the classification is still pending, the UI displays a "AI analysis temporarily busy" state, allowing manual category entry.

---

## Future: Fine-Tuning Roadmap

| Phase | Target | Milestone |
|-------|--------|-----------|
| **Data collection** | 10,000 labelled triplets from correction logs | 6 months post-launch |
| **Baseline evaluation** | Measure GPT-4V accuracy on held-out set | Before training starts |
| **Fine-tune Gemini Flash** | Cheaper, faster, tunable via Google AI Studio | Q3 after launch |
| **A/B test** | Route 20% of submissions to fine-tuned model | 2 weeks |
| **Full rollout** | Fine-tuned model becomes primary, GPT-4V becomes fallback | On accuracy ≥ 95% |
| **Domain-specific model** | Dedicated civic image classifier (open-source base + LoRA) | Year 2 |
