
from __future__ import annotations

from collections import defaultdict
from typing import List

from .models import BillingRecord, PaymentMode, PaymentModeBreakdown, ReconciliationReport, RejectedRow


def _line_item_total(record: BillingRecord) -> int:
    return sum(li.qty * li.unit_price_paise for li in record.line_items)


def build_reconciliation_report(
    clinic_id: str,
    records: List[BillingRecord],
    rejected_rows: List[RejectedRow],
) -> ReconciliationReport:
    per_mode = {
        mode: {
            "billed": 0,
            "collected": 0,
            "outstanding": 0,
            "refunds": 0,
            "visits": 0,
        }
        for mode in PaymentMode
    }

    total_billed = 0
    total_collected = 0
    total_outstanding = 0
    total_refunds = 0
    outstanding_visit_count = 0
    refund_count = 0

    for record in records:
        mode = record.payment_mode
        per_mode[mode]["visits"] += 1

        if record.is_refund:
            refund_amount = abs(record.amount_paid_paise)
            per_mode[mode]["refunds"] += refund_amount
            total_refunds += refund_amount
            refund_count += 1
            continue

        billed = _line_item_total(record) - record.discount_paise
        collected = record.amount_paid_paise
        outstanding = max(billed - collected, 0)

        per_mode[mode]["billed"] += billed
        per_mode[mode]["collected"] += collected
        per_mode[mode]["outstanding"] += outstanding

        total_billed += billed
        total_collected += collected
        total_outstanding += outstanding
        if outstanding > 0:
            outstanding_visit_count += 1

    breakdown = [
        PaymentModeBreakdown(
            payment_mode=mode,
            billed_paise=per_mode[mode]["billed"],
            collected_paise=per_mode[mode]["collected"],
            outstanding_paise=per_mode[mode]["outstanding"],
            refunds_paise=per_mode[mode]["refunds"],
            visit_count=per_mode[mode]["visits"],
        )
        for mode in PaymentMode
    ]

    return ReconciliationReport(
        clinic_id=clinic_id,
        total_visits=len(records),
        total_billed_paise=total_billed,
        total_collected_paise=total_collected,
        total_outstanding_paise=total_outstanding,
        total_refunds_paise=total_refunds,
        outstanding_visit_count=outstanding_visit_count,
        refund_count=refund_count,
        by_payment_mode=breakdown,
        rejected_rows=rejected_rows,
    )
