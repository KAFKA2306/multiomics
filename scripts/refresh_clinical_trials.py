#!/usr/bin/env python3
"""Refresh canonical clinical-trial evidence from ClinicalTrials.gov API v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "multiomics-v1.json"
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "clinicaltrials"
API = "https://clinicaltrials.gov/api/v2"
UA = "KAFKA2306-multiomics/1.0"


def fetch_json(url: str) -> tuple[dict[str, Any], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object from {url}")
    return value, raw


def extract_trial(
    study: dict[str, Any],
    *,
    retrieved_at: str,
    source_sha256: str,
    raw_path: str,
    api_data_timestamp: str,
) -> dict[str, Any]:
    protocol = study["protocolSection"]
    identification = protocol["identificationModule"]
    status = protocol["statusModule"]
    sponsor = protocol["sponsorCollaboratorsModule"]
    design = protocol["designModule"]
    interventions = protocol["armsInterventionsModule"]["interventions"]

    nct_id = identification["nctId"]
    phases = design.get("phases", [])
    names = [row["name"] for row in interventions if row.get("name")]
    enrollment = design.get("enrollmentInfo")
    if not phases or not names:
        raise ValueError(f"missing phase or intervention data for {nct_id}")
    if not isinstance(enrollment, dict) or not isinstance(enrollment.get("count"), int) or not enrollment.get("type"):
        raise ValueError(f"missing enrollment data for {nct_id}")

    return {
        "nct_id": nct_id,
        "title": identification["briefTitle"],
        "status": status["overallStatus"],
        "phase": phases[0],
        "sponsor": sponsor["leadSponsor"]["name"],
        "interventions": names,
        "enrollment_count": enrollment["count"],
        "enrollment_type": enrollment["type"],
        "last_update_posted": status["lastUpdatePostDateStruct"]["date"],
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "retrieved_at": retrieved_at,
        "source_sha256": source_sha256,
        "raw_path": raw_path,
        "api_data_timestamp": api_data_timestamp,
    }


def refresh(nct_id: str, data_path: Path, raw_dir: Path) -> dict[str, Any]:
    version, _ = fetch_json(f"{API}/version")
    study, raw = fetch_json(f"{API}/studies/{nct_id}")
    digest = hashlib.sha256(raw).hexdigest()
    raw_path = raw_dir / nct_id / f"{digest}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)

    data = json.loads(data_path.read_text(encoding="utf-8"))
    existing = next((row for row in data["clinical_trials"] if row.get("nct_id") == nct_id), None)
    if existing is not None and existing.get("source_sha256") == digest:
        return existing

    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = extract_trial(
        study,
        retrieved_at=retrieved_at,
        source_sha256=digest,
        raw_path=raw_path.relative_to(ROOT).as_posix(),
        api_data_timestamp=str(version["dataTimestamp"]),
    )
    records = [row for row in data["clinical_trials"] if row.get("nct_id") != nct_id]
    records.append(record)
    data["clinical_trials"] = sorted(records, key=lambda row: row["nct_id"])
    data["retrieved_at"] = retrieved_at
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nct-id", default="NCT06264180")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args()
    print(json.dumps(refresh(args.nct_id, args.data, args.raw_dir), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
