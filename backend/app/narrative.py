
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import AnalyticsReport, NarrativeResponse, ReconciliationReport, TracedFigure

NUMBER_PATTERN = re.compile(r"\d[\d,]*\.?\d*")


def paise_to_rupees(paise: int) -> float:
    return round(paise / 100, 2)


def format_rupees(paise: int) -> str:
    rupees = paise_to_rupees(paise)
    if rupees == int(rupees):
        return f"₹{int(rupees):,}"
    return f"₹{rupees:,.2f}"


@dataclass
class WhitelistEntry:
    label: str
    display: str  # canonical text as it should appear in the narrative
    numeric_value: Optional[float]  # rupee value used for grounding checks, if numeric


def _build_whitelist(
    recon: ReconciliationReport, analytics: AnalyticsReport
) -> Dict[str, WhitelistEntry]:
    entries: Dict[str, WhitelistEntry] = {
        "total_billed_paise": WhitelistEntry(
            "Total billed", format_rupees(recon.total_billed_paise), paise_to_rupees(recon.total_billed_paise)
        ),
        "total_collected_paise": WhitelistEntry(
            "Total collected", format_rupees(recon.total_collected_paise), paise_to_rupees(recon.total_collected_paise)
        ),
        "total_outstanding_paise": WhitelistEntry(
            "Outstanding", format_rupees(recon.total_outstanding_paise), paise_to_rupees(recon.total_outstanding_paise)
        ),
        "total_refunds_paise": WhitelistEntry(
            "Refunds", format_rupees(recon.total_refunds_paise), paise_to_rupees(recon.total_refunds_paise)
        ),
        "total_visits": WhitelistEntry(
            "Total visits", str(recon.total_visits), float(recon.total_visits)
        ),
        "outstanding_visit_count": WhitelistEntry(
            "Visits with outstanding balance",
            str(recon.outstanding_visit_count),
            float(recon.outstanding_visit_count),
        ),
        "refund_count": WhitelistEntry(
            "Refund count", str(recon.refund_count), float(recon.refund_count)
        ),
    }

    if recon.total_billed_paise > 0:
        pct = round(recon.total_collected_paise / recon.total_billed_paise * 100)
        entries["collection_rate_pct"] = WhitelistEntry(
            "Collection rate", f"{pct}%", float(pct)
        )

    if analytics.peak_hour is not None:
        entries["peak_hour_label"] = WhitelistEntry(
            "Peak hour", analytics.peak_hour.label, None
        )
        entries["peak_hour_revenue_paise"] = WhitelistEntry(
            "Peak hour revenue",
            format_rupees(analytics.peak_hour.revenue_paise),
            paise_to_rupees(analytics.peak_hour.revenue_paise),
        )

    for i, drug in enumerate(analytics.top_drugs_by_qty, start=1):
        entries[f"top_drug_by_qty_{i}_name"] = WhitelistEntry(
            f"#{i} drug by quantity", drug.drug_name, None
        )
        entries[f"top_drug_by_qty_{i}_qty"] = WhitelistEntry(
            f"#{i} drug quantity", f"{drug.qty} units", float(drug.qty)
        )

    for i, drug in enumerate(analytics.top_drugs_by_revenue, start=1):
        entries[f"top_drug_by_revenue_{i}_name"] = WhitelistEntry(
            f"#{i} drug by revenue", drug.drug_name, None
        )
        entries[f"top_drug_by_revenue_{i}_revenue"] = WhitelistEntry(
            f"#{i} drug revenue", format_rupees(drug.revenue_paise), paise_to_rupees(drug.revenue_paise)
        )

    return entries


def _extract_numbers(text: str) -> List[float]:
    found = []
    for match in NUMBER_PATTERN.finditer(text):
        raw = match.group().replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        found.append(value)
    return found


def _allowed_numbers(whitelist: Dict[str, WhitelistEntry]) -> set:
    """
    Every number the narrative is allowed to contain.

    Numeric whitelist entries (money, counts) contribute their value
    directly. Text-only entries (drug names, the peak-hour label like
    "1pm-2pm") contribute any digits embedded in their own display text —
    e.g. the "1" and "2" in "1pm-2pm" are safe because that exact string is
    itself a whitelisted, verbatim value; nothing narrower is exempted.
    This deliberately does NOT grant a blanket pass to small numbers in
    general, so an invented "3 visits" is still caught even though 3 is a
    small number.
    """
    allowed = set()
    for entry in whitelist.values():
        if entry.numeric_value is not None:
            allowed.add(entry.numeric_value)
        else:
            for match in NUMBER_PATTERN.finditer(entry.display):
                try:
                    allowed.add(float(match.group().replace(",", "")))
                except ValueError:
                    continue
    return allowed


def _find_ungrounded_numbers(text: str, whitelist: Dict[str, WhitelistEntry]) -> List[float]:
    allowed = _allowed_numbers(whitelist)
    bad = []
    for n in _extract_numbers(text):
        if n in allowed or round(n, 2) in allowed:
            continue
        bad.append(n)
    return bad


def _is_grounded(text: str, whitelist: Dict[str, WhitelistEntry]) -> bool:
    return len(_find_ungrounded_numbers(text, whitelist)) == 0


def _touches_before(text: str, idx: int) -> bool:
    if idx == 0:
        return False
    ch = text[idx - 1]
    if ch.isdigit():
        return True
    if ch in ",." and idx - 2 >= 0 and text[idx - 2].isdigit():
        return True
    if ch == "₹":
        return True
    return False


def _touches_after(text: str, idx: int) -> bool:
    if idx >= len(text):
        return False
    ch = text[idx]
    if ch.isdigit():
        return True
    if ch in ",." and idx + 1 < len(text) and text[idx + 1].isdigit():
        return True
    if ch == "%":
        return True
    return False


def _find_standalone(text: str, needle: str) -> int:
    """Index of the first occurrence of `needle` in `text` that isn't fused
    onto a larger number/currency token, or -1 if there is none."""
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            return -1
        after_idx = idx + len(needle)
        if not _touches_before(text, idx) and not _touches_after(text, after_idx):
            return idx
        start = idx + 1


def _trace_figures(text: str, whitelist: Dict[str, WhitelistEntry]) -> List[TracedFigure]:
    traced = []
    seen_fields = set()
    # order by first appearance in the text so the panel reads top-to-bottom
    hits = []
    for field, entry in whitelist.items():
        idx = _find_standalone(text, entry.display)
        if idx != -1:
            hits.append((idx, field, entry))
    for _, field, entry in sorted(hits, key=lambda x: x[0]):
        if field in seen_fields:
            continue
        seen_fields.add(field)
        traced.append(TracedFigure(label=entry.label, value_display=entry.display, source_field=field))
    return traced


def _deterministic_fallback(
    recon: ReconciliationReport, analytics: AnalyticsReport, whitelist: Dict[str, WhitelistEntry]
) -> str:
    lines = []
    lines.append(f"Good evening! Here's today's summary for {recon.clinic_id}:")
    lines.append("")
    lines.append(
        f"{whitelist['total_billed_paise'].display} billed across "
        f"{whitelist['total_visits'].display} visits, "
        f"{whitelist['total_collected_paise'].display} collected"
        + (f" ({whitelist['collection_rate_pct'].display})." if "collection_rate_pct" in whitelist else ".")
    )
    if recon.total_outstanding_paise > 0:
        lines.append(
            f"{whitelist['total_outstanding_paise'].display} is still outstanding across "
            f"{whitelist['outstanding_visit_count'].display} visit(s)."
        )
    if recon.total_refunds_paise > 0:
        lines.append(
            f"{whitelist['total_refunds_paise'].display} was refunded across "
            f"{whitelist['refund_count'].display} visit(s)."
        )
    if "peak_hour_label" in whitelist:
        lines.append("")
        lines.append(
            f"Busiest hour: {whitelist['peak_hour_label'].display}, with "
            f"{whitelist['peak_hour_revenue_paise'].display} in revenue."
        )
    if "top_drug_by_qty_1_name" in whitelist:
        lines.append("")
        lines.append(
            f"Top mover by quantity: {whitelist['top_drug_by_qty_1_name'].display} "
            f"({whitelist['top_drug_by_qty_1_qty'].display})."
        )
    if "top_drug_by_revenue_1_name" in whitelist:
        lines.append(
            f"Top by revenue: {whitelist['top_drug_by_revenue_1_name'].display} "
            f"({whitelist['top_drug_by_revenue_1_revenue'].display})."
        )
    lines.append("")
    lines.append(
        "Note: cost data wasn't available today, so this is revenue, not profit — "
        "flagging rather than estimating."
    )
    return "\n".join(lines)


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _call_llm(prompt: str) -> Optional[str]:
    """
    Returns raw text from the model, or None if no key/SDK/network is
    available — the caller treats None exactly like "LLM unavailable" and
    falls back to the deterministic narrative. This function must never
    raise: a bad API key, a network blip, a rate limit, or a malformed HTTP
    response from Groq all collapse to the same safe `None` return, so an
    LLM outage can never turn into a 500 for this endpoint.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        import httpx
    except ImportError:
        return None

    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    try:
        resp = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.3,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return text.strip() if isinstance(text, str) else None
    except Exception:
        # Network error, auth error, rate limit, unexpected response shape,
        # timeout, etc. — all treated as "no model available right now".
        return None


def _build_prompt(recon: ReconciliationReport, analytics: AnalyticsReport) -> str:
    report_json = json.dumps(
        {
            "clinic_id": recon.clinic_id,
            "total_visits": recon.total_visits,
            "total_billed": paise_to_rupees(recon.total_billed_paise),
            "total_collected": paise_to_rupees(recon.total_collected_paise),
            "total_outstanding": paise_to_rupees(recon.total_outstanding_paise),
            "total_refunds": paise_to_rupees(recon.total_refunds_paise),
            "outstanding_visit_count": recon.outstanding_visit_count,
            "refund_count": recon.refund_count,
            "peak_hour": analytics.peak_hour.label if analytics.peak_hour else None,
            "peak_hour_revenue": paise_to_rupees(analytics.peak_hour.revenue_paise)
            if analytics.peak_hour
            else None,
            "top_drugs_by_qty": [
                {"drug": d.drug_name, "qty": d.qty} for d in analytics.top_drugs_by_qty
            ],
            "top_drugs_by_revenue": [
                {"drug": d.drug_name, "revenue": paise_to_rupees(d.revenue_paise)}
                for d in analytics.top_drugs_by_revenue
            ],
        },
        indent=2,
    )
    return f"""You are writing a short end-of-day billing summary for a clinic owner, to be
read on WhatsApp. You will ONLY be given the JSON report below. All figures
are already in rupees.

Rules:
- Use ONLY the numbers in this JSON. Do not calculate, round, or invent any
  number that isn't present here.
- If something isn't in the data (e.g. profit — cost price isn't provided),
  say plainly that it can't be computed. Do not approximate it as revenue or
  anything else and present it as fact.
- Keep it short (5-8 short lines), warm, plain language, WhatsApp-appropriate.
- Amounts should use the ₹ symbol with comma grouping, e.g. ₹42,850.
- Write in plain prose sentences. Do NOT use numbered lists or bullet points
  (e.g. "1.", "2)", "-") — a stray list marker digit is indistinguishable
  from an invented figure to the automated checker reading this text.
- Output ONLY the narrative text. No JSON, no markdown, no preamble.

Report:
{report_json}
"""


def generate_narrative(
    recon: ReconciliationReport, analytics: AnalyticsReport
) -> NarrativeResponse:
    whitelist = _build_whitelist(recon, analytics)
    notes: List[str] = []

    llm_text = _call_llm(_build_prompt(recon, analytics))

    if llm_text is None:
        notes.append(
            "No LLM configured (set GROQ_API_KEY) or the LLM call failed — "
            "used the deterministic fallback narrative."
        )
        final_text = _deterministic_fallback(recon, analytics, whitelist)
        grounded = True
        ungrounded_removed = 0
    elif not llm_text.strip():
        notes.append("Model returned an empty response — used the deterministic fallback narrative.")
        final_text = _deterministic_fallback(recon, analytics, whitelist)
        grounded = True
        ungrounded_removed = 0
    else:
        ungrounded = _find_ungrounded_numbers(llm_text, whitelist)

        if ungrounded:
            notes.append(
                f"Model narrative contained {len(ungrounded)} number(s) not traceable to the "
                "report — discarded it and used the deterministic fallback narrative instead."
            )
            final_text = _deterministic_fallback(recon, analytics, whitelist)
            grounded = True
            ungrounded_removed = len(ungrounded)
        else:
            final_text = llm_text.strip()
            grounded = True
            ungrounded_removed = 0

    traced = _trace_figures(final_text, whitelist)

    return NarrativeResponse(
        narrative=final_text,
        traced_figures=traced,
        grounded=grounded,
        ungrounded_claims_removed=ungrounded_removed,
        notes=notes,
    )
