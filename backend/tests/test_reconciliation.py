from app.ingest import parse_billing_log
from app.reconciliation import build_reconciliation_report


def test_busy_day_totals(busy_day):
    records, rejected = parse_billing_log(busy_day)
    report = build_reconciliation_report("CLN-KNP-014", records, rejected)

    assert report.total_visits == 18
    assert report.total_billed_paise == 319000
    assert report.total_collected_paise == 317200
    assert report.total_outstanding_paise == 1800
    assert report.total_refunds_paise == 0
    assert report.outstanding_visit_count == 3
    assert report.refund_count == 0
    assert len(report.rejected_rows) == 1


def test_busy_day_payment_mode_breakdown(busy_day):
    records, rejected = parse_billing_log(busy_day)
    report = build_reconciliation_report("CLN-KNP-014", records, rejected)
    by_mode = {b.payment_mode.value: b for b in report.by_payment_mode}

    assert by_mode["cash"].billed_paise == 127500
    assert by_mode["cash"].collected_paise == 127000
    assert by_mode["cash"].outstanding_paise == 500
    assert by_mode["cash"].visit_count == 5

    assert by_mode["card"].billed_paise == 83500
    assert by_mode["card"].collected_paise == 82700
    assert by_mode["card"].outstanding_paise == 800
    assert by_mode["card"].visit_count == 7

    assert by_mode["upi"].billed_paise == 108000
    assert by_mode["upi"].collected_paise == 107500
    assert by_mode["upi"].outstanding_paise == 500
    assert by_mode["upi"].visit_count == 6

    # billed - collected must reconcile to outstanding, per mode and in total
    total_billed = sum(b.billed_paise for b in report.by_payment_mode)
    total_collected = sum(b.collected_paise for b in report.by_payment_mode)
    total_outstanding = sum(b.outstanding_paise for b in report.by_payment_mode)
    assert total_billed - total_collected == total_outstanding


def test_refund_only_day_is_all_refunds_no_billing(refund_only_day):
    """Non-happy-path day: every row is a refund. Billed/collected/outstanding
    must all be zero; the full amount must land in refunds."""
    records, rejected = parse_billing_log(refund_only_day)
    report = build_reconciliation_report("CLN-KNP-014", records, rejected)

    assert report.total_visits == 3
    assert report.total_billed_paise == 0
    assert report.total_collected_paise == 0
    assert report.total_outstanding_paise == 0
    assert report.refund_count == 3
    # 24000 + 22000 + 3000
    assert report.total_refunds_paise == 49000


def test_empty_day_reconciles_to_all_zero(empty_day):
    """Non-happy-path day: clinic closed, no rows at all."""
    records, rejected = parse_billing_log(empty_day)
    report = build_reconciliation_report("CLN-KNP-014", records, rejected)

    assert report.total_visits == 0
    assert report.total_billed_paise == 0
    assert report.total_collected_paise == 0
    assert report.total_outstanding_paise == 0
    assert report.total_refunds_paise == 0
    assert report.rejected_rows == []
    # every payment mode should still be represented, at zero
    assert len(report.by_payment_mode) == 3
    assert all(b.billed_paise == 0 for b in report.by_payment_mode)


def test_outstanding_is_clamped_per_visit_not_netted():
    """An overpayment on one visit must not offset a shortfall on another —
    each visit's outstanding is clamped at zero independently."""
    from app.ingest import parse_billing_log as parse

    rows = [
        {
            "clinic_id": "C1",
            "visit_id": "V1",
            "timestamp": "2026-01-01T09:00:00Z",
            "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 1000}],
            "payment_mode": "cash",
            "amount_paid_paise": 1500,  # overpaid by 500
            "discount_paise": 0,
            "is_refund": False,
        },
        {
            "clinic_id": "C1",
            "visit_id": "V2",
            "timestamp": "2026-01-01T10:00:00Z",
            "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 1000}],
            "payment_mode": "cash",
            "amount_paid_paise": 500,  # underpaid by 500
            "discount_paise": 0,
            "is_refund": False,
        },
    ]
    records, rejected = parse(rows)
    report = build_reconciliation_report("C1", records, rejected)
    # naive netting would give 0 outstanding; clamped-per-visit gives 500
    assert report.total_outstanding_paise == 500
    assert report.outstanding_visit_count == 1
