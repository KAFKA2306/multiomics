#!/usr/bin/env python3
"""Build deterministic API views from canonical Multiomics data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multiomics-v1.json"
API = ROOT / "api" / "v1" / "multiomics"


def load() -> dict[str, Any]:
    value = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("canonical data must be an object")
    return value


def build(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    source_urls: set[str] = set()

    metric_names = {
        "cost_per_genome": "sequencing_cost_per_genome_usd",
        "cost_per_megabase": "sequencing_cost_per_megabase_usd",
    }
    for row in data["sequencing_costs"]:
        source_urls.add(row["source_url"])
        observations.append(
            {
                "metric": metric_names[row["metric"]],
                "as_of": row["period"],
                "value": row["value"],
                "unit": row["unit"],
                "provider": "NHGRI",
                "product": "DNA sequencing costs",
                "source_url": row["source_url"],
            }
        )

    trials = data["clinical_trials"]
    if trials:
        as_of = max(row["last_update_posted"] for row in trials)
        source_urls.update(row["source_url"] for row in trials)
        source_url = sorted(row["source_url"] for row in trials)[0]
        for metric in ("clinical_trial_count", "multiomics_trial_count"):
            observations.append(
                {
                    "metric": metric,
                    "as_of": as_of,
                    "value": len(trials),
                    "unit": "studies",
                    "provider": "ClinicalTrials.gov",
                    "product": "canonical Multiomics tracked studies",
                    "qualifier": "tracked_repository_records",
                    "source_url": source_url,
                }
            )

    approvals = data["approvals"]
    if approvals:
        as_of = max(row["approval_date"] for row in approvals)
        source_urls.update(row["source_url"] for row in approvals)
        observations.append(
            {
                "metric": "fda_approval_count",
                "as_of": as_of,
                "value": len(approvals),
                "unit": "approvals",
                "provider": "U.S. Food and Drug Administration",
                "product": "canonical Multiomics tracked approvals",
                "qualifier": "tracked_repository_records",
                "source_url": sorted(row["source_url"] for row in approvals)[0],
            }
        )

    observations.sort(key=lambda row: (row["metric"], row["as_of"]))
    metrics = {
        "schema_version": 1,
        "retrieved_at": data["retrieved_at"],
        "observations": observations,
    }
    index = {
        "schema_version": 1,
        "retrieved_at": data["retrieved_at"],
        "canonical_data_path": "data/multiomics-v1.json",
        "metrics_path": "api/v1/multiomics/metrics.json",
        "source_urls": sorted(source_urls),
        "observation_counts": {
            "sequencing_costs": len(data["sequencing_costs"]),
            "clinical_trials": len(trials),
            "approvals": len(approvals),
            "metrics": len(observations),
        },
    }
    return index, metrics


def write() -> None:
    index, metrics = build(load())
    API.mkdir(parents=True, exist_ok=True)
    (API / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (API / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
