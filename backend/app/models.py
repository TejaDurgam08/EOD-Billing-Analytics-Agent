
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class PaymentMode(str, Enum):
    cash = "cash"
    card = "card"
    upi = "upi"


class LineItem(BaseModel):
    drug_name: str
    qty: int
    unit_price_paise: int

    @field_validator("drug_name")
    @classmethod
    def drug_name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("drug_name must not be blank")
        return v.strip()

    @field_validator("qty")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("qty must be a positive integer")
        return v

    @field_validator("unit_price_paise")
    @classmethod
    def price_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("unit_price_paise must not be negative")
        return v


class BillingRecord(BaseModel):
    """A single validated visit row from the billing log."""

    clinic_id: str
    visit_id: str
    timestamp: str  # kept as raw ISO-8601 string; parsed separately for hour bucketing
    doctor_id: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    payment_mode: PaymentMode
    amount_paid_paise: int
    discount_paise: int = 0
    is_refund: bool = False

    @field_validator("discount_paise")
    @classmethod
    def discount_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("discount_paise must not be negative")
        return v

    @field_validator("clinic_id", "visit_id")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class RejectedRow(BaseModel):
    """A row that failed validation, with a specific, actionable reason."""

    index: int
    visit_id: Optional[str] = None
    errors: List[str]
    raw: dict


class PaymentModeBreakdown(BaseModel):
    payment_mode: PaymentMode
    billed_paise: int
    collected_paise: int
    outstanding_paise: int
    refunds_paise: int
    visit_count: int


class ReconciliationReport(BaseModel):
    clinic_id: str
    total_visits: int
    total_billed_paise: int
    total_collected_paise: int
    total_outstanding_paise: int
    total_refunds_paise: int
    outstanding_visit_count: int
    refund_count: int
    by_payment_mode: List[PaymentModeBreakdown]
    rejected_rows: List[RejectedRow] = Field(default_factory=list)


class HourlyRevenue(BaseModel):
    hour_start: int  # 0-23, UTC
    label: str  # e.g. "12pm-1pm"
    revenue_paise: int


class DrugRanking(BaseModel):
    drug_name: str
    qty: int
    revenue_paise: int


class AnalyticsReport(BaseModel):
    clinic_id: str
    revenue_by_hour: List[HourlyRevenue]
    peak_hour: Optional[HourlyRevenue] = None
    top_drugs_by_qty: List[DrugRanking]
    top_drugs_by_revenue: List[DrugRanking]


class TracedFigure(BaseModel):
    label: str
    value_display: str
    source_field: str


class NarrativeResponse(BaseModel):
    narrative: str
    traced_figures: List[TracedFigure]
    grounded: bool
    ungrounded_claims_removed: int = 0
    notes: List[str] = Field(default_factory=list)
