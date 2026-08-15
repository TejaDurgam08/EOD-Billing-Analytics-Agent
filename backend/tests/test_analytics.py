from app.analytics import build_analytics_report
from app.ingest import parse_billing_log


def test_peak_hour_and_revenue_by_hour(busy_day):
    records, _ = parse_billing_log(busy_day)
    report = build_analytics_report("CLN-KNP-014", records)

    by_hour = {h.hour_start: h.revenue_paise for h in report.revenue_by_hour}
    assert by_hour[9] == 9000
    assert by_hour[13] == 76000
    assert by_hour[14] == 3500

    assert report.peak_hour is not None
    assert report.peak_hour.hour_start == 13
    assert report.peak_hour.revenue_paise == 76000
    assert report.peak_hour.label == "1pm-2pm"


def test_top_drugs_by_quantity_and_revenue_are_distinct_rankings(busy_day):
    records, _ = parse_billing_log(busy_day)
    report = build_analytics_report("CLN-KNP-014", records)

    qty_order = [d.drug_name for d in report.top_drugs_by_qty]
    revenue_order = [d.drug_name for d in report.top_drugs_by_revenue]

    assert qty_order[0] == "OMEPRAZOLE"
    assert qty_order[1] == "METFORMIN"
    assert revenue_order[0] == "ATORVASTATIN"
    assert revenue_order[1] == "OMEPRAZOLE"

    # the two rankings must not be forced into the same order
    assert qty_order != revenue_order

    top_revenue_entry = report.top_drugs_by_revenue[0]
    assert top_revenue_entry.drug_name == "ATORVASTATIN"
    assert top_revenue_entry.revenue_paise == 120000


def test_misspelled_drug_name_is_not_silently_merged(busy_day):
    """PARACETMOL (typo) in the sample data must not be auto-corrected or
    merged into PARACETAMOL — the system doesn't invent a fix for dirty data,
    it reports what's there."""
    records, _ = parse_billing_log(busy_day)
    report = build_analytics_report("CLN-KNP-014", records)

    all_names = {d.drug_name for d in report.top_drugs_by_qty} | {
        d.drug_name for d in report.top_drugs_by_revenue
    }
    # both spellings should be able to appear as distinct entries somewhere
    # in the underlying counts (top_n may truncate PARACETMOL out, so check
    # the qty ranking directly for the low-volume misspelled entry too)
    full_qty = {d.drug_name: d.qty for d in build_analytics_report(
        "CLN-KNP-014", records, top_n=100
    ).top_drugs_by_qty}
    assert full_qty.get("PARACETMOL") == 2
    assert full_qty.get("PARACETAMOL") == 11


def test_refund_rows_are_excluded_from_analytics(refund_only_day):
    records, _ = parse_billing_log(refund_only_day)
    report = build_analytics_report("CLN-KNP-014", records)

    assert report.revenue_by_hour == []
    assert report.peak_hour is None
    assert report.top_drugs_by_qty == []
    assert report.top_drugs_by_revenue == []


def test_empty_day_analytics_is_empty_not_error(empty_day):
    records, _ = parse_billing_log(empty_day)
    report = build_analytics_report("CLN-KNP-014", records)

    assert report.revenue_by_hour == []
    assert report.peak_hour is None
    assert report.top_drugs_by_qty == []
    assert report.top_drugs_by_revenue == []
