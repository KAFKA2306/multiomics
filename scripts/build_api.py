#!/usr/bin/env python3
"""Build deterministic API views from canonical Multiomics data."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

try:
    import refresh_drugsfda
except ModuleNotFoundError:
    from scripts import refresh_drugsfda

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multiomics-v1.json"
DRUGSFDA_MANIFEST = ROOT / "data" / "drugsfda-source.json"
API = ROOT / "api" / "v1" / "multiomics"


def load() -> dict[str, Any]:
    value = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("canonical data must be an object")
    return value


def _table_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = refresh_drugsfda._decode_table(archive.read(name))
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def build_drugsfda_crosswalk(data: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads(DRUGSFDA_MANIFEST.read_text(encoding="utf-8"))
    raw_path = ROOT / manifest["raw_path"]
    if not raw_path.exists():
        raise ValueError("Drugs@FDA raw ZIP is missing")

    with zipfile.ZipFile(raw_path) as archive:
        products = _table_rows(archive, "Products.txt")
        applications = _table_rows(archive, "Applications.txt")
        submissions = _table_rows(archive, "Submissions.txt")
        joins = _table_rows(archive, "Join_Submission_ActionTypes_Lookup.txt")
        action_types = _table_rows(archive, "ActionTypes_Lookup.txt")
        documents = _table_rows(archive, "ApplicationDocs.txt")
        document_types = _table_rows(archive, "ApplicationsDocsType_Lookup.txt")

    application_by_number = {row["ApplNo"].strip(): row for row in applications}
    action_type_by_id = {row["ActionTypes_LookupID"].strip(): row for row in action_types}
    document_type_by_id = {
        row["ApplicationDocsType_Lookup_ID"].strip(): row["ApplicationDocsType_Lookup_Description"].strip()
        for row in document_types
    }

    product_apps_by_name: dict[str, set[str]] = {}
    for row in products:
        drug_name = row["DrugName"].strip().casefold()
        if drug_name:
            product_apps_by_name.setdefault(drug_name, set()).add(row["ApplNo"].strip())

    rows: list[dict[str, Any]] = []
    for approval in sorted(data["approvals"], key=lambda row: (row["approval_date"], row["id"])):
        brand_name = approval["brand_name"]
        application_numbers = sorted(product_apps_by_name.get(brand_name.strip().casefold(), set())) if brand_name else []
        matched_applications: list[dict[str, Any]] = []
        for application_number in application_numbers:
            application = application_by_number.get(application_number)
            matching_products = [
                {
                    "product_number": row["ProductNo"].strip(),
                    "drug_name": row["DrugName"].strip() or None,
                    "active_ingredient": row["ActiveIngredient"].strip() or None,
                    "form": row["Form"].strip() or None,
                    "strength": row["Strength"].strip() or None,
                }
                for row in products
                if row["ApplNo"].strip() == application_number
                and row["DrugName"].strip().casefold() == brand_name.strip().casefold()
            ]
            matching_submissions: list[dict[str, Any]] = []
            for submission in submissions:
                if submission["ApplNo"].strip() != application_number:
                    continue
                status_date = submission["SubmissionStatusDate"].strip()
                if not status_date or status_date[:10] != approval["approval_date"]:
                    continue
                submission_type = submission["SubmissionType"].strip()
                submission_number = submission["SubmissionNo"].strip()
                actions = []
                for join in joins:
                    if (
                        join["ApplNo"].strip() == application_number
                        and join["SubmissionType"].strip() == submission_type
                        and join["SubmissionNo"].strip() == submission_number
                    ):
                        action = action_type_by_id.get(join["ActionTypes_LookupID"].strip())
                        actions.append(
                            {
                                "action_type_id": join["ActionTypes_LookupID"].strip(),
                                "description": action["ActionTypes_LookupDescription"].strip() if action else None,
                            }
                        )
                actions.sort(key=lambda row: row["action_type_id"])
                docs = []
                for document in documents:
                    if (
                        document["ApplNo"].strip() == application_number
                        and document["SubmissionType"].strip() == submission_type
                        and document["SubmissionNo"].strip() == submission_number
                    ):
                        docs.append(
                            {
                                "document_type": document_type_by_id.get(document["ApplicationDocsTypeID"].strip()),
                                "document_date": document["ApplicationDocsDate"].strip()[:10] or None,
                                "document_url": document["ApplicationDocsURL"].strip() or None,
                            }
                        )
                docs.sort(key=lambda row: (row["document_date"] or "", row["document_type"] or "", row["document_url"] or ""))
                matching_submissions.append(
                    {
                        "submission_type": submission_type,
                        "submission_number": submission_number,
                        "submission_status": submission["SubmissionStatus"].strip() or None,
                        "submission_status_date": status_date[:10],
                        "submission_class_code_id": submission["SubmissionClassCodeID"].strip() or None,
                        "review_priority": submission["ReviewPriority"].strip() or None,
                        "action_types": actions,
                        "documents": docs,
                    }
                )
            matching_submissions.sort(key=lambda row: (row["submission_type"], int(row["submission_number"])))
            matched_applications.append(
                {
                    "application_number": application_number,
                    "application_type": application["ApplType"].strip() if application else None,
                    "sponsor_name": (application["SponsorName"].strip() or None) if application else None,
                    "products": matching_products,
                    "submissions_on_notification_date": matching_submissions,
                }
            )
        rows.append(
            {
                "approval_id": approval["id"],
                "approval_date": approval["approval_date"],
                "brand_name": brand_name,
                "generic_name": approval["generic_name"],
                "notification_source_url": approval["source_url"],
                "notification_source_sha256": approval.get("source_sha256"),
                "applications": matched_applications,
            }
        )

    return {
        "schema_version": 1,
        "authority": "U.S. Food and Drug Administration",
        "dataset": "Drugs@FDA Data Files",
        "source_page_url": manifest["source_page_url"],
        "source_sha256": manifest["source_sha256"],
        "source_retrieved_at": manifest["retrieved_at"],
        "canonical_approval_path": "data/multiomics-v1.json",
        "approvals": rows,
    }


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
        "drugsfda_oncology_crosswalk_path": "api/v1/multiomics/drugsfda-oncology-crosswalk.json",
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
    data = load()
    index, metrics = build(data)
    crosswalk = build_drugsfda_crosswalk(data)
    API.mkdir(parents=True, exist_ok=True)
    (API / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (API / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (API / "drugsfda-oncology-crosswalk.json").write_text(json.dumps(crosswalk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
