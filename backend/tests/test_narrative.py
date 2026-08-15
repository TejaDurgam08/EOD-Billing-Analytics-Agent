from app.analytics import build_analytics_report
from app.ingest import parse_billing_log
from app.narrative import generate_narrative, _build_whitelist, _is_grounded, _trace_figures
from app.reconciliation import build_reconciliation_report


def _reports(rows):
    records, rejected = parse_billing_log(rows)
    recon = build_reconciliation_report("CLN-KNP-014", records, rejected)
    analytics = build_analytics_report("CLN-KNP-014", records)
    return recon, analytics


def test_no_llm_configured_uses_grounded_deterministic_fallback(busy_day, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    recon, analytics = _reports(busy_day)

    result = generate_narrative(recon, analytics)

    assert result.grounded is True
    assert result.ungrounded_claims_removed == 0
    # total_billed_paise=319000 -> ₹3,190
    assert "₹3,190" in result.narrative
    assert len(result.traced_figures) > 0
    assert any(f.source_field == "total_billed_paise" for f in result.traced_figures)


def test_narrative_never_calls_llm_layer_for_deterministic_data(busy_day, monkeypatch):
    """The deterministic reports themselves must never be affected by whether
    an LLM is available — same recon/analytics regardless."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    recon1, analytics1 = _reports(busy_day)
    recon2, analytics2 = _reports(busy_day)
    assert recon1 == recon2
    assert analytics1 == analytics2


def test_grounding_check_accepts_text_using_only_whitelisted_numbers(busy_day):
    recon, analytics = _reports(busy_day)
    whitelist = _build_whitelist(recon, analytics)
    text = f"Billed {whitelist['total_billed_paise'].display} today."
    assert _is_grounded(text, whitelist) is True


def test_grounding_check_rejects_invented_number(busy_day):
    recon, analytics = _reports(busy_day)
    whitelist = _build_whitelist(recon, analytics)
    text = "Profit today was ₹99,999 which is fantastic!"
    assert _is_grounded(text, whitelist) is False


def test_malformed_llm_response_falls_back_safely(busy_day, monkeypatch):
    """A model call that returns garbage/empty text must not crash the
    endpoint or corrupt the output — it should fall back to the deterministic
    narrative."""
    recon, analytics = _reports(busy_day)

    monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.narrative._call_llm", lambda prompt: "")

    result = generate_narrative(recon, analytics)
    assert result.grounded is True
    assert "₹3,190" in result.narrative


def test_ungrounded_llm_response_is_discarded_and_replaced(busy_day, monkeypatch):
    recon, analytics = _reports(busy_day)

    monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.narrative._call_llm",
        lambda prompt: "Great day! You made a profit of ₹12,345,678 which is amazing.",
    )

    result = generate_narrative(recon, analytics)
    assert result.grounded is True
    assert result.ungrounded_claims_removed >= 1
    assert "12,345,678" not in result.narrative
    assert "₹3,190" in result.narrative


def test_grounded_llm_response_is_kept_and_traced(busy_day, monkeypatch):
    recon, analytics = _reports(busy_day)
    whitelist = _build_whitelist(recon, analytics)

    honest_text = (
        f"Today's billed total was {whitelist['total_billed_paise'].display}, "
        f"with {whitelist['total_collected_paise'].display} collected."
    )

    monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.narrative._call_llm", lambda prompt: honest_text)

    result = generate_narrative(recon, analytics)
    assert result.grounded is True
    assert result.ungrounded_claims_removed == 0
    assert result.narrative == honest_text
    traced_fields = {f.source_field for f in result.traced_figures}
    assert "total_billed_paise" in traced_fields
    assert "total_collected_paise" in traced_fields


def test_traced_figures_only_include_numbers_actually_present_in_text(busy_day):
    recon, analytics = _reports(busy_day)
    whitelist = _build_whitelist(recon, analytics)
    text = f"Only mentioning {whitelist['total_refunds_paise'].display} here."
    traced = _trace_figures(text, whitelist)
    fields = {f.source_field for f in traced}
    assert fields == {"total_refunds_paise"}


def test_grounding_check_rejects_wrong_small_number(busy_day):
    """A small, plausible-looking but WRONG count (e.g. an invented visit
    count) must still be caught — small numbers are not given a blanket
    pass just because they're small. Only digits that are literally part of
    an already-whitelisted display string (like the peak-hour label) are
    exempt."""
    recon, analytics = _reports(busy_day)
    whitelist = _build_whitelist(recon, analytics)
    # real outstanding_visit_count is 3; claim 7 instead
    assert whitelist["outstanding_visit_count"].numeric_value == 3.0
    text = "7 visits still have an outstanding balance today."
    assert _is_grounded(text, whitelist) is False


def test_grounding_check_allows_true_peak_hour_label_digits(busy_day):
    """The digits inside the real peak-hour label (e.g. '1pm-2pm') must be
    allowed, since that exact string is itself a whitelisted value."""
    recon, analytics = _reports(busy_day)
    whitelist = _build_whitelist(recon, analytics)
    label = whitelist["peak_hour_label"].display
    assert label == "1pm-2pm"
    text = f"Busiest hour was {label}."
    assert _is_grounded(text, whitelist) is True


def test_narrative_notes_when_profit_not_computable(busy_day, monkeypatch):
    """The deterministic fallback must explicitly say profit isn't computable
    rather than silently omitting it or presenting revenue as profit."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    recon, analytics = _reports(busy_day)
    result = generate_narrative(recon, analytics)
    assert "profit" in result.narrative.lower()
    assert "revenue, not profit" in result.narrative.lower() or "not profit" in result.narrative.lower()
