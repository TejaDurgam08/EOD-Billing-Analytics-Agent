
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .models import AnalyticsReport, BillingRecord, DrugRanking, HourlyRevenue


def _hour_label(hour: int) -> str:
    def fmt(h: int) -> str:
        suffix = "am" if h < 12 else "pm"
        display = h % 12
        if display == 0:
            display = 12
        return f"{display}{suffix}"

    start = fmt(hour)
    end = fmt((hour + 1) % 24)
    return f"{start}-{end}"


def _parse_hour_utc(timestamp: str) -> int:
    ts = timestamp.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).hour


def build_analytics_report(
    clinic_id: str,
    records: List[BillingRecord],
    top_n: int = 5,
) -> AnalyticsReport:
    revenue_by_hour = {h: 0 for h in range(24)}
    qty_by_drug: dict[str, int] = {}
    revenue_by_drug: dict[str, int] = {}

    for record in records:
        if record.is_refund:
            continue

        line_total = sum(li.qty * li.unit_price_paise for li in record.line_items)
        billed = line_total - record.discount_paise

        hour = _parse_hour_utc(record.timestamp)
        revenue_by_hour[hour] += billed

        for li in record.line_items:
            qty_by_drug[li.drug_name] = qty_by_drug.get(li.drug_name, 0) + li.qty
            revenue_by_drug[li.drug_name] = (
                revenue_by_drug.get(li.drug_name, 0) + li.qty * li.unit_price_paise
            )

    hourly = [
        HourlyRevenue(hour_start=h, label=_hour_label(h), revenue_paise=revenue_by_hour[h])
        for h in range(24)
        if revenue_by_hour[h] > 0
    ]
    hourly.sort(key=lambda x: x.hour_start)

    peak_hour = max(hourly, key=lambda x: x.revenue_paise) if hourly else None

    top_qty = sorted(
        (DrugRanking(drug_name=name, qty=qty, revenue_paise=revenue_by_drug.get(name, 0))
         for name, qty in qty_by_drug.items()),
        key=lambda d: d.qty,
        reverse=True,
    )[:top_n]

    top_revenue = sorted(
        (DrugRanking(drug_name=name, qty=qty_by_drug.get(name, 0), revenue_paise=rev)
         for name, rev in revenue_by_drug.items()),
        key=lambda d: d.revenue_paise,
        reverse=True,
    )[:top_n]

    return AnalyticsReport(
        clinic_id=clinic_id,
        revenue_by_hour=hourly,
        peak_hour=peak_hour,
        top_drugs_by_qty=top_qty,
        top_drugs_by_revenue=top_revenue,
    )
