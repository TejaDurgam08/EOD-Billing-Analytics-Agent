
from __future__ import annotations

from typing import List, Tuple

from pydantic import ValidationError

from .models import BillingRecord, RejectedRow

REQUIRED_FIELDS = [
    "clinic_id",
    "visit_id",
    "timestamp",
    "line_items",
    "payment_mode",
    "amount_paid_paise",
]


def _format_pydantic_errors(exc: ValidationError) -> List[str]:
    messages = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        messages.append(f"{loc}: {err['msg']}")
    return messages


def parse_billing_log(raw_rows: list) -> Tuple[List[BillingRecord], List[RejectedRow]]:
    """
    Validate every row in a raw billing log (already-parsed JSON array).

    Returns (valid_records, rejected_rows). Never raises for row-level issues —
    a bad row is reported, not fatal. Callers that need to fail the whole
    request on any bad row (there is no such requirement here) can check
    `len(rejected_rows) > 0` themselves.
    """
    if not isinstance(raw_rows, list):
        raise ValueError(
            "Billing log must be a JSON array of visit records; "
            f"got {type(raw_rows).__name__}"
        )

    valid: List[BillingRecord] = []
    rejected: List[RejectedRow] = []

    for i, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            rejected.append(
                RejectedRow(
                    index=i,
                    visit_id=None,
                    errors=[f"row is a {type(row).__name__}, expected an object"],
                    raw={"value": row},
                )
            )
            continue

        missing = [f for f in REQUIRED_FIELDS if f not in row]
        if missing:
            rejected.append(
                RejectedRow(
                    index=i,
                    visit_id=row.get("visit_id"),
                    errors=[f"missing required field(s): {', '.join(missing)}"],
                    raw=row,
                )
            )
            continue

        try:
            record = BillingRecord.model_validate(row)
        except ValidationError as exc:
            rejected.append(
                RejectedRow(
                    index=i,
                    visit_id=row.get("visit_id"),
                    errors=_format_pydantic_errors(exc),
                    raw=row,
                )
            )
            continue

        # Cross-field sanity checks that pydantic alone can't express.
        row_errors = []
        if record.is_refund and record.amount_paid_paise > 0:
            row_errors.append(
                "is_refund is true but amount_paid_paise is not negative "
                f"(got {record.amount_paid_paise})"
            )
        if not record.is_refund and record.amount_paid_paise < 0:
            row_errors.append(
                "amount_paid_paise is negative on a non-refund row "
                f"(got {record.amount_paid_paise})"
            )
        if not record.is_refund:
            line_total = sum(li.qty * li.unit_price_paise for li in record.line_items)
            if record.discount_paise > line_total:
                row_errors.append(
                    f"discount_paise ({record.discount_paise}) exceeds the line-item "
                    f"total ({line_total}) — this would make billed amount negative"
                )

        if row_errors:
            rejected.append(
                RejectedRow(index=i, visit_id=record.visit_id, errors=row_errors, raw=row)
            )
            continue

        valid.append(record)

    return valid, rejected
