
import json
import sys
from pathlib import Path

import httpx

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"
API_BASE = "http://localhost:8000"

FILES = {
    "billing_log_2026-07-25.json": "2026-07-25",
    "billing_log_2026-07-26.json": "2026-07-26",
    "billing_log_2026-07-27.json": "2026-07-27",
}


def main() -> None:
    for filename, log_date in FILES.items():
        path = DATASET_DIR / filename
        if not path.exists():
            print(f"skip (not found): {path}")
            continue
        payload = json.loads(path.read_text())
        resp = httpx.post(
            f"{API_BASE}/api/ingest",
            params={"log_date": log_date},
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            print(f"FAILED {filename}: {resp.status_code} {resp.text}")
            sys.exit(1)
        data = resp.json()
        print(
            f"ingested {filename} -> clinic={data['clinic_id']} date={log_date} "
            f"accepted={data['accepted_row_count']} rejected={data['rejected_row_count']}"
        )


if __name__ == "__main__":
    main()
