import json
from pathlib import Path

import pytest

DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "dataset"


def load_dataset(filename: str) -> list:
    return json.loads((DATASET_DIR / filename).read_text())


@pytest.fixture
def refund_only_day():
    """25 Jul: every row is a refund. Total billed/collected should be zero;
    refunds should carry the full amount."""
    return load_dataset("billing_log_2026-07-25.json")


@pytest.fixture
def empty_day():
    """26 Jul: clinic closed, empty array. Must not error."""
    return load_dataset("billing_log_2026-07-26.json")


@pytest.fixture
def busy_day():
    """27 Jul: normal trading day, includes one row missing payment_mode
    and one row with a misspelled drug name (PARACETMOL) — both are edge
    cases the pipeline must handle without crashing."""
    return load_dataset("billing_log_2026-07-27.json")
