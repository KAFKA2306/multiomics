#!/usr/bin/env python3
"""Build deterministic API views from canonical Multiomics data."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import refresh_drugsfda
    import refresh_orange_book
except ModuleNotFoundError:
    from scripts import refresh_drugsfda, refresh_orange_book

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multiomics-v1.json"
DRUGSFDA_MANIFEST = ROOT / "data" / "drugsfda-source.json"
ORANGE_BOOK_MANIFEST = ROOT / "data" / "orange-book-source.json"
API = ROOT / "api" / "v1" / "multiomics"


def load() -> dict[str, Any]:
    value = json.loads(DATA.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("canonical data must be an object")
    return value


def _table_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = refresh_drugsfda._decode_table(archive.read(name))
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def _verified_archive(manifest_path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_path = ROOT / manifest["raw_path"]
    if not raw_path.exists():
        raise ValueError(f"{label} raw ZIP is missing")
    raw_bytes = raw_path.read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != manifest["source_sha256"]:
        raise ValueError(f"{label} raw ZIP sha256 does not match manifest")
    return manifest, raw_bytes


def _normalize_fda_number(value: str, width: int, label: str) -> str:
    text = value.strip()
    if not text or not text.isdigit() or len(text) > width:
        raise ValueError(f"invalid {label}: {value!r}")
    return text.zfill(width)


def _orange_book_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    candidates = [entry for entry in archive.namelist() if Path(entry).name.lower() == name.lower()]
    if len(candidates) != 1:
        raise ValueError(f"Orange Book table not found exactly once: {name}")
    text = refresh_orange_book._decode_table(archive.read(candidates[0]))
    return list(csv.DictReader(io.StringIO(text), delimiter="~"))


def build_drugsfda_crosswalk(data: dict[str, Any]) -> dict[str, Any]:
    manifest, raw_bytes = _verified_archive(DRUGSFDA_MANIFEST, "Drugs@FDA")

    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
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
            brand_products = [
                row
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
                letter_urls = sorted(
                    document["ApplicationDocsURL"].strip()
                    for document in documents
                    if document["ApplNo"].strip() == application_number
                    and document["SubmissionType"].strip() == submission_type
                    and document["SubmissionNo"].strip() == submission_number
                    and document_type_by_id.get(document["ApplicationDocsTypeID"].strip()) == "Letter"
                    and document["ApplicationDocsURL"].strip()
                )
                matching_submissions.append(
                    {
                        "submission_type": submission_type,
                        "submission_number": submission_number,
                        "submission_status": submission["SubmissionStatus"].strip() or None,
                        "submission_status_date": status_date[:10],
                        "submission_class_code_id": submission["SubmissionClassCodeID"].strip() or None,
                        "review_priority": submission["ReviewPriority"].strip() or None,
                        "action_types": actions,
                        "letter_urls": letter_urls,
                    }
                )
            matching_submissions.sort(key=lambda row: (row["submission_type"], int(row["submission_number"])))
            matched_applications.append(
                {
                    "application_number": application_number,
                    "application_type": application["ApplType"].strip() if application else None,
                    "sponsor_name": (application["SponsorName"].strip() or None) if application else None,
                    "product_numbers": sorted({row["ProductNo"].strip() for row in brand_products}),
                    "active_ingredients": sorted({row["ActiveIngredient"].strip() for row in brand_products if row["ActiveIngredient"].strip()}),
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


def build_fda_product_identity_crosscheck() -> dict[str, Any]:
    drugs_manifest, drugs_raw = _verified_archive(DRUGSFDA_MANIFEST, "Drugs@FDA")
    orange_manifest, orange_raw = _verified_archive(ORANGE_BOOK_MANIFEST, "Orange Book")

    with zipfile.ZipFile(io.BytesIO(drugs_raw)) as archive:
        applications = _table_rows(archive, "Applications.txt")
        drugs_products = _table_rows(archive, "Products.txt")
    with zipfile.ZipFile(io.BytesIO(orange_raw)) as archive:
        orange_products = _orange_book_rows(archive, "products.txt")

    application_type_by_number: dict[str, str] = {}
    for row in applications:
        application_number = _normalize_fda_number(row["ApplNo"], 6, "Drugs@FDA application number")
        application_type = row["ApplType"].strip()
        previous = application_type_by_number.get(application_number)
        if previous is not None and previous != application_type:
            raise ValueError(f"Drugs@FDA application type conflicts for {application_number}")
        application_type_by_number[application_number] = application_type

    drugs_by_identity: dict[tuple[str, str], dict[str, str]] = {}
    for row in drugs_products:
        application_number = _normalize_fda_number(row["ApplNo"], 6, "Drugs@FDA application number")
        application_type = application_type_by_number.get(application_number)
        if application_type not in {"NDA", "ANDA"}:
            continue
        product_number = _normalize_fda_number(row["ProductNo"], 3, "Drugs@FDA product number")
        key = (application_number, product_number)
        if key in drugs_by_identity:
            raise ValueError(f"duplicate Drugs@FDA product identity: {key}")
        drugs_by_identity[key] = {
            "application_type": application_type,
            "application_number": application_number,
            "product_number": product_number,
            "drug_name": row["DrugName"].strip(),
            "active_ingredient": row["ActiveIngredient"].strip(),
        }

    orange_by_identity: dict[tuple[str, str], dict[str, str]] = {}
    pre_1982_count = 0
    dated_count = 0
    for row in orange_products:
        raw_application_type = row["Appl_Type"].strip()
        if raw_application_type == "N":
            application_type = "NDA"
        elif raw_application_type == "A":
            application_type = "ANDA"
        else:
            raise ValueError(f"unexpected Orange Book application type: {raw_application_type!r}")
        application_number = _normalize_fda_number(row["Appl_No"], 6, "Orange Book application number")
        product_number = _normalize_fda_number(row["Product_No"], 3, "Orange Book product number")
        approval_date = row["Approval_Date"].strip()
        if approval_date.casefold() == "approved prior to jan 1, 1982":
            pre_1982_count += 1
        else:
            try:
                datetime.strptime(approval_date, "%b %d, %Y")
            except ValueError as exc:
                raise ValueError(f"unexpected Orange Book Approval_Date: {approval_date!r}") from exc
            dated_count += 1
        key = (application_number, product_number)
        if key in orange_by_identity:
            raise ValueError(f"duplicate Orange Book product identity: {key}")
        orange_by_identity[key] = {
            "application_type": application_type,
            "application_number": application_number,
            "product_number": product_number,
            "trade_name": row["Trade_Name"].strip(),
            "ingredient": row["Ingredient"].strip(),
            "approval_date": approval_date,
        }

    orange_keys = set(orange_by_identity)
    drugs_keys = set(drugs_by_identity)
    overlap_keys = orange_keys & drugs_keys
    type_mismatch_keys = sorted(
        key
        for key in overlap_keys
        if orange_by_identity[key]["application_type"] != drugs_by_identity[key]["application_type"]
    )
    matched_keys = sorted(overlap_keys - set(type_mismatch_keys))
    orange_only_keys = sorted(orange_keys - drugs_keys)
    drugs_only_keys = sorted(drugs_keys - orange_keys)

    return {
        "schema_version": 1,
        "authority": "U.S. Food and Drug Administration",
        "scope": "NDA and ANDA product identity coverage",
        "identity_fields": ["application_number", "product_number"],
        "drugsfda": {
            "dataset": drugs_manifest["dataset"],
            "source_sha256": drugs_manifest["source_sha256"],
            "source_retrieved_at": drugs_manifest["retrieved_at"],
        },
        "orange_book": {
            "dataset": orange_manifest["dataset"],
            "source_sha256": orange_manifest["source_sha256"],
            "source_retrieved_at": orange_manifest["retrieved_at"],
        },
        "counts": {
            "orange_book_products": len(orange_by_identity),
            "orange_book_dated_products": dated_count,
            "orange_book_pre_1982_products": pre_1982_count,
            "drugsfda_nda_anda_products": len(drugs_by_identity),
            "identity_overlap_products": len(overlap_keys),
            "matched_application_type_products": len(matched_keys),
            "application_type_mismatch_products": len(type_mismatch_keys),
            "orange_book_only_products": len(orange_only_keys),
            "drugsfda_only_products": len(drugs_only_keys),
        },
        "application_type_mismatches": [
            {
                "application_number": key[0],
                "product_number": key[1],
                "orange_book_application_type": orange_by_identity[key]["application_type"],
                "drugsfda_application_type": drugs_by_identity[key]["application_type"],
            }
            for key in type_mismatch_keys
        ],
        "orange_book_only": [orange_by_identity[key] for key in orange_only_keys],
        "drugsfda_only": [drugs_by_identity[key] for key in drugs_only_keys],
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
        "fda_product_identity_crosscheck_path": "api/v1/multiomics/fda-product-identity-crosscheck.json",
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
    product_identity_crosscheck = build_fda_product_identity_crosscheck()
    API.mkdir(parents=True, exist_ok=True)
    (API / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (API / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (API / "drugsfda-oncology-crosswalk.json").write_text(json.dumps(crosswalk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (API / "fda-product-identity-crosscheck.json").write_text(
        json.dumps(product_identity_crosscheck, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write()
