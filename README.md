# SwasthiQ — EOD Billing & Analytics Agent

Ingests a clinic's daily billing log and produces:
1. A **deterministic** end-of-day reconciliation report (never touches an LLM).
2. **Deterministic** analytics (revenue by hour, top medicines by quantity and by revenue).
3. An **LLM-generated narrative** summary that is programmatically checked against the
   deterministic report, with a "Traced Figures" panel proving every number in the
   narrative is real.

```
/backend    Python REST API (FastAPI)
/frontend   React application (Vite)
/dataset    Sample billing logs used for local testing
```

## Quick start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Optional — enable the LLM narrative layer (otherwise a deterministic, template-based
fallback narrative is used, which is grounded by construction). This project uses
[Groq](https://console.groq.com) — get a free API key there:

```bash
export GROQ_API_KEY=gsk_...
export GROQ_MODEL=llama-3.3-70b-versatile   # optional, defaults to this; see
                                             # console.groq.com/docs/models for current options
```

Groq's chat-completions endpoint is OpenAI-compatible, so it's called directly over HTTP
with `httpx` in `app/narrative.py` — no extra SDK dependency.

Load the sample dataset once the server is running:

```bash
python seed_sample_data.py
```

Run tests:

```bash
pytest -v
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

By default the frontend calls the API at `http://localhost:8000`. Override with
`VITE_API_BASE` (e.g. in a `.env` file) when pointing at a deployed backend.

## API Contract

### `POST /api/ingest?log_date=YYYY-MM-DD`
Body: a raw JSON array of visit records (see schema below).

Validates every row independently. A malformed row (missing field, wrong type,
`is_refund`/`amount_paid_paise` sign mismatch, etc.) is **rejected with a specific
reason** and reported back — it never turns into a generic 500 and never silently
drops other valid rows in the same file. Only a structurally invalid payload (not a
JSON array at all) returns `422`.

Computes and **persists** (upsert, keyed on `clinic_id` + `log_date`) the
reconciliation and analytics reports.

```json
// Response
{
  "clinic_id": "CLN-KNP-014",
  "log_date": "2026-07-27",
  "reconciliation": { ... },
  "analytics": { ... },
  "accepted_row_count": 18,
  "rejected_row_count": 1
}
```

### `GET /api/reports/{clinic_id}/{log_date}`
Returns the previously computed `reconciliation` + `analytics` reports for an
already-ingested clinic-day. `404` if that clinic-day hasn't been ingested.

### `GET /api/reports/{clinic_id}/{log_date}/narrative`
Generates the grounded narrative + traced-figures panel for an ingested clinic-day.

```json
{
  "narrative": "Good evening! Here's today's summary...",
  "traced_figures": [
    { "label": "Total billed", "value_display": "₹3,190", "source_field": "total_billed_paise" }
  ],
  "grounded": true,
  "ungrounded_claims_removed": 0,
  "notes": []
}
```

### `GET /api/ingestions`
Lists every ingested clinic-day (used to populate the date picker in the UI).

### Billing log schema (input)

| Field | Type | Notes |
|---|---|---|
| `clinic_id` | string | single clinic per file |
| `visit_id` | string | unique per visit |
| `timestamp` | ISO 8601 UTC | used for hour-of-day bucketing |
| `doctor_id` | string | optional, unused by this service |
| `line_items` | array of `{drug_name, qty, unit_price_paise}` | |
| `payment_mode` | `"cash" \| "card" \| "upi"` | |
| `amount_paid_paise` | integer | negative on a refund row |
| `discount_paise` | integer | may be 0 |
| `is_refund` | boolean | if true, `amount_paid_paise` is negative |

All money is integer **paise** throughout the backend and the database. Rupee
formatting (`₹`, comma grouping) happens only at the presentation edge — the
`format_rupees` helper in `narrative.py` and `formatRupees` in the frontend's
`api.js` — never inside a computation.

## Technical explanation

### REST API structure
Four thin FastAPI route handlers in `app/main.py` sit on top of four independent,
individually-testable modules:

- `app/ingest.py` — parsing/validation only. Returns `(valid_records, rejected_rows)`
  instead of raising, so a bad row never aborts the whole request.
- `app/reconciliation.py` — pure function `build_reconciliation_report(...)`. No I/O,
  no LLM. This is the ground truth.
- `app/analytics.py` — pure function `build_analytics_report(...)`. Same rule.
- `app/narrative.py` — the only module allowed to call an LLM, and only ever
  downstream of the two reports above, never the raw log.
- `app/storage.py` — a thin SQLite layer, isolated behind `save_ingestion` /
  `get_ingestion` so the rest of the app never touches SQL directly.

Keeping the deterministic layer as pure functions of `(clinic_id, records) -> report`
(no database, no LLM, no request object) is what makes it possible to unit test
reconciliation and analytics completely independently of the API and of any LLM
availability — see `tests/test_reconciliation.py` and `tests/test_analytics.py`.

### Data consistency on update
Re-ingesting a clinic-day (e.g. the front desk corrects a row and re-uploads) is an
**UPSERT** keyed on `(clinic_id, log_date)`, done in a single SQL statement inside one
transaction (`storage.save_ingestion`, using `INSERT ... ON CONFLICT ... DO UPDATE`).
There is never a window where the reconciliation report and the analytics report on
disk reflect two different uploads for the same day — both are recomputed from the
same validated record set and written together in the same statement.

### Grounding the narrative (the part actually being evaluated)
Rather than trusting the model to self-report which numbers it used, the service:

1. Builds a whitelist of every number legitimately derivable from the two
   deterministic reports (`_build_whitelist` in `narrative.py`). Text-only entries
   (drug names, the peak-hour label like `"1pm-2pm"`) only make *their own* embedded
   digits safe — there's no blanket allowance for "small numbers in general", so an
   invented `"7 visits"` is still caught even though 7 is a small number.
2. Asks the LLM for a short summary, in rupees, from that data only (and explicitly
   told to avoid numbered/bulleted lists, so a stray `"1."` list marker can't be
   mistaken for an invented figure by the checker below).
3. **Independently re-scans** the returned text for every number-looking token and
   checks each one against the whitelist (`_is_grounded` / `_find_ungrounded_numbers`).
4. If *any* number fails that check — or the response is empty/unparseable/the LLM
   call fails outright (network error, missing key, rate limit) — the LLM output is
   discarded entirely and replaced with a deterministic, template-built fallback
   narrative that is grounded by construction. This is intentional: patching a
   partially-wrong sentence is fragile and hard to verify; replacing the whole
   narrative with something provably correct is not.
5. The "Traced Figures" panel is **never** built from the model's own citations
   either — it's built by scanning the *final* narrative text (whichever one shipped)
   for whitelist values that literally appear in it, using boundary-aware matching
   (`_find_standalone`) so e.g. a bare `refund_count` of `0` can't spuriously match
   the `0` inside an unrelated `₹0` figure. A figure can only show up as "traced" if
   it's both present in the text and derived straight from the report.

This also means the profit-not-computable requirement is handled structurally: the
deterministic fallback always states plainly that profit isn't computable (no cost
data), and the LLM prompt explicitly forbids approximating a missing metric as
something else and presenting it as fact.

### Edge cases in the sample dataset (and how they're handled)
- **`billing_log_2026-07-26.json` is `[]`** — an empty day (clinic closed) is valid,
  not an error. All totals compute to zero; every payment mode still appears in the
  breakdown table at ₹0.
- **`billing_log_2026-07-25.json` is refund-only** — billed/collected/outstanding are
  all zero; the full amount lands in the `refunds` bucket. Refund visits are excluded
  from analytics (they're money leaving, not a sale).
- **A row in `billing_log_2026-07-27.json` is missing `payment_mode`** — rejected with
  a specific "missing required field(s): payment_mode" error, `visit_id` preserved so
  the clinic can find and fix it. The other 18 rows in that file still ingest normally.
- **A row contains `"PARACETMOL"`** (misspelled) — treated as its own distinct drug
  name, not silently merged into `PARACETAMOL`. Fuzzy-matching drug names without a
  reference formulary would mean guessing, which the brief explicitly asks the LLM
  layer not to do — the same discipline is applied here in the deterministic layer.
- **A `discount_paise` larger than the line-item total** — would make the billed
  amount negative, which isn't a valid state. Rejected with a specific reason rather
  than silently producing a negative bill (not present in the sample data, but
  covered by a dedicated test, since it's the kind of bad input a real front desk
  could eventually type in).
