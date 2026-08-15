
from __future__ import annotations

from typing import List

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import storage
from .analytics import build_analytics_report
from .ingest import parse_billing_log
from .models import AnalyticsReport, NarrativeResponse, ReconciliationReport
from .narrative import generate_narrative
from .reconciliation import build_reconciliation_report

app = FastAPI(title="SwasthiQ EOD Billing & Analytics Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # take-home scope: no auth/session model to protect
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    storage.init_db()


class IngestResponse(BaseModel):
    clinic_id: str
    log_date: str
    reconciliation: ReconciliationReport
    analytics: AnalyticsReport
    accepted_row_count: int
    rejected_row_count: int


@app.post("/api/ingest", response_model=IngestResponse)
def ingest_billing_log(payload: list = Body(...), log_date: str = Query(..., description="YYYY-MM-DD")):
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=422,
            detail=(
                "Billing log must be a JSON array of visit records "
                f"(got {type(payload).__name__}). "
                "See /docs for the expected schema."
            ),
        )

    try:
        records, rejected = parse_billing_log(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not records and not rejected:
        # Empty day (e.g. clinic closed) is valid, not an error — the schema
        # README explicitly calls this out as an edge case to handle, not reject.
        clinic_id = "UNKNOWN"
    else:
        clinic_id = (records[0].clinic_id if records else rejected[0].raw.get("clinic_id", "UNKNOWN"))

    recon = build_reconciliation_report(clinic_id, records, rejected)
    analytics = build_analytics_report(clinic_id, records)

    storage.save_ingestion(
        clinic_id=clinic_id,
        log_date=log_date,
        raw_log=payload,
        reconciliation_report=recon.model_dump(),
        analytics_report=analytics.model_dump(),
        rejected_row_count=len(rejected),
    )

    return IngestResponse(
        clinic_id=clinic_id,
        log_date=log_date,
        reconciliation=recon,
        analytics=analytics,
        accepted_row_count=len(records),
        rejected_row_count=len(rejected),
    )


class ReportsResponse(BaseModel):
    clinic_id: str
    log_date: str
    reconciliation: ReconciliationReport
    analytics: AnalyticsReport


@app.get("/api/reports/{clinic_id}/{log_date}", response_model=ReportsResponse)
def get_reports(clinic_id: str, log_date: str):
    row = storage.get_ingestion(clinic_id, log_date)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ingested billing log found for clinic '{clinic_id}' on {log_date}.",
        )
    return ReportsResponse(
        clinic_id=row["clinic_id"],
        log_date=row["log_date"],
        reconciliation=ReconciliationReport.model_validate(row["reconciliation_report"]),
        analytics=AnalyticsReport.model_validate(row["analytics_report"]),
    )


@app.get("/api/reports/{clinic_id}/{log_date}/narrative", response_model=NarrativeResponse)
def get_narrative(clinic_id: str, log_date: str):
    row = storage.get_ingestion(clinic_id, log_date)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ingested billing log found for clinic '{clinic_id}' on {log_date}.",
        )
    recon = ReconciliationReport.model_validate(row["reconciliation_report"])
    analytics = AnalyticsReport.model_validate(row["analytics_report"])
    return generate_narrative(recon, analytics)


class IngestionSummary(BaseModel):
    clinic_id: str
    log_date: str
    rejected_row_count: int
    updated_at: str


@app.get("/api/ingestions", response_model=List[IngestionSummary])
def list_ingestions():
    return storage.list_ingestions()


@app.get("/api/health")
def health():
    return {"status": "ok"}
