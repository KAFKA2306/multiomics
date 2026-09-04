#!/usr/bin/env python3
"""Build cross-source decision support for FDA accelerated approvals and confirmatory trials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "multiomics-v1.json"
REQUIREMENTS = ROOT / "data" / "fda-confirmatory-trial-requirements.json"
OUTPUT = ROOT / "api" / "v1" / "multiomics" / "accelerated-approval-confirmatory-trials.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build(canonical: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    approvals = canonical.get("approvals")
    trials = canonical.get("clinical_trials")
    records = requirements.get("records")
    if not isinstance(approvals, list) or not isinstance(trials, list) or not isinstance(records, list):
        raise ValueError("required canonical arrays are missing")

    approval_index = {
        (row.get("approval_date"), row.get("generic_name"), row.get("sponsor")): row
        for row in approvals
    }
    trial_index = {row.get("nct_id"): row for row in trials}

    linked: list[dict[str, Any]] = []
    for requirement in records:
        key = (
            requirement.get("approval_date"),
            requirement.get("generic_name"),
            requirement.get("sponsor"),
        )
        approval = approval_index.get(key)
        if approval is None:
            raise ValueError(f"FDA accelerated approval is not present in canonical data: {key}")
        if approval.get("pathway") != "accelerated approval":
            raise ValueError(f"FDA approval is not accelerated approval: {key}")

        nct_id = requirement.get("nct_id")
        trial = trial_index.get(nct_id)
        if trial is None:
            raise ValueError(f"FDA confirmatory trial is not present in canonical data: {nct_id}")
        if trial.get("sponsor") != requirement.get("sponsor"):
            raise ValueError(f"FDA requirement and ClinicalTrials.gov sponsor differ for {nct_id}")
        if trial.get("phase") != requirement.get("trial_phase"):
            raise ValueError(f"FDA requirement and ClinicalTrials.gov phase differ for {nct_id}")
        if trial.get("enrollment_count") != requirement.get("planned_enrollment"):
            raise ValueError(f"FDA requirement and ClinicalTrials.gov enrollment differ for {nct_id}")

        linked.append(
            {
                "brand_name": requirement["brand_name"],
                "generic_name": requirement["generic_name"],
                "sponsor": requirement["sponsor"],
                "approval_date": requirement["approval_date"],
                "approval_pathway": approval["pathway"],
                "approval_source_url": approval["source_url"],
                "nct_id": nct_id,
                "trial_name": requirement["trial_name"],
                "trial_status": trial["status"],
                "trial_phase": trial["phase"],
                "trial_enrollment_count": trial["enrollment_count"],
                "trial_enrollment_type": trial["enrollment_type"],
                "trial_last_update_posted": trial["last_update_posted"],
                "trial_source_url": trial["source_url"],
                "primary_endpoint": requirement["primary_endpoint"],
                "postmarketing_requirement_due_date": requirement["postmarketing_requirement_due_date"],
                "requirement_summary": requirement["requirement_summary"],
            }
        )

    linked.sort(key=lambda row: (row["approval_date"], row["nct_id"]))
    return {
        "schema_version": 1,
        "authority": requirements["authority"],
        "source_dataset": requirements["dataset"],
        "source_url": requirements["source_url"],
        "source_retrieved_at": requirements["retrieved_at"],
        "canonical_data_path": "data/multiomics-v1.json",
        "linked_records": len(linked),
        "records": linked,
    }


def write() -> None:
    result = build(_load(CANONICAL), _load(REQUIREMENTS))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
