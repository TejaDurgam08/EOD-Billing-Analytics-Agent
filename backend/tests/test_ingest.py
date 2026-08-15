from app.ingest import parse_billing_log


def test_valid_rows_are_parsed(busy_day):
    records, rejected = parse_billing_log(busy_day)
    # 19 rows in the file, 1 is missing payment_mode -> 18 valid, 1 rejected
    assert len(records) == 18
    assert len(rejected) == 1


def test_missing_payment_mode_is_rejected_with_specific_reason(busy_day):
    _, rejected = parse_billing_log(busy_day)
    bad = rejected[0]
    assert bad.visit_id == "V-20260727-019"
    assert any("payment_mode" in e for e in bad.errors)


def test_empty_day_produces_no_records_and_no_errors(empty_day):
    records, rejected = parse_billing_log(empty_day)
    assert records == []
    assert rejected == []


def test_refund_only_day_parses_cleanly(refund_only_day):
    records, rejected = parse_billing_log(refund_only_day)
    assert len(records) == 3
    assert rejected == []
    assert all(r.is_refund for r in records)


def test_top_level_non_list_payload_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_billing_log({"not": "a list"})


def test_row_missing_required_field_is_rejected():
    records, rejected = parse_billing_log([{"clinic_id": "C1"}])
    assert records == []
    assert len(rejected) == 1
    assert "missing required field" in rejected[0].errors[0]


def test_negative_amount_on_non_refund_row_is_rejected():
    row = {
        "clinic_id": "C1",
        "visit_id": "V1",
        "timestamp": "2026-01-01T10:00:00Z",
        "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 100}],
        "payment_mode": "cash",
        "amount_paid_paise": -100,
        "discount_paise": 0,
        "is_refund": False,
    }
    records, rejected = parse_billing_log([row])
    assert records == []
    assert len(rejected) == 1
    assert "negative on a non-refund row" in rejected[0].errors[0]


def test_refund_true_with_positive_amount_is_rejected():
    row = {
        "clinic_id": "C1",
        "visit_id": "V1",
        "timestamp": "2026-01-01T10:00:00Z",
        "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 100}],
        "payment_mode": "cash",
        "amount_paid_paise": 100,
        "discount_paise": 0,
        "is_refund": True,
    }
    records, rejected = parse_billing_log([row])
    assert records == []
    assert len(rejected) == 1
    assert "is_refund is true" in rejected[0].errors[0]


def test_discount_exceeding_line_total_is_rejected():
    """A discount larger than the line-item total would make the billed
    amount negative — that's not a valid state and must be rejected with a
    specific reason, not silently produce a negative bill."""
    row = {
        "clinic_id": "C1",
        "visit_id": "V1",
        "timestamp": "2026-01-01T10:00:00Z",
        "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 1000}],
        "payment_mode": "cash",
        "amount_paid_paise": 0,
        "discount_paise": 5000,
        "is_refund": False,
    }
    records, rejected = parse_billing_log([row])
    assert records == []
    assert len(rejected) == 1
    assert "discount_paise" in rejected[0].errors[0]
    assert "exceeds" in rejected[0].errors[0]


def test_non_object_row_is_rejected_not_fatal():
    records, rejected = parse_billing_log(["not-an-object", {"clinic_id": "C1"}])
    assert records == []
    assert len(rejected) == 2
    assert "expected an object" in rejected[0].errors[0]
