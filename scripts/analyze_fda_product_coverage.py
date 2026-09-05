#!/usr/bin/env python3
"""Analyze FDA product coverage differences with official Drugs@FDA marketing status."""

from __future__ import annotations

import csv
import hashlib
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
MANIFEST_PATH = ROOT / "data" / "drugsfda-source.json"
CROSSCHECK_PATH = ROOT / "api" / "v1" / "multiomics" / "fda-product-identity-crosscheck.json"
PRIMARY_EVIDENCE_PATH = ROOT / "data" / "fda-orange-book-absence-primary-evidence.json"
OUTPUT_PATH = ROOT / "api" / "v1" / "multiomics" / "fda-product-coverage-analysis.json"
EVIDENCE_OUTPUT_PATH = ROOT / "api" / "v1" / "multiomics" / "fda-product-coverage-evidence.json"
ORANGE_BOOK_QA_URL = "https://www.fda.gov/media/160167/download"
ORANGE_BOOK_PREFACE_URL = "https://www.fda.gov/drugs/development-approval-process-drugs/orange-book-preface"
TENTATIVE_APPROVAL_STATUS = "None (Tentative Approval)"


def _normalize_number(value: str, width: int, label: str) -> str:
    text = value.strip()
    if not text or not text.isdigit() or len(text) > width:
        raise ValueError(f"invalid {label}: {value!r}")
    return text.zfill(width)


def _table_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = refresh_drugsfda._decode_table(archive.read(name))
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def _verified_drugsfda_raw() -> bytes:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw_path = ROOT / manifest["raw_path"]
    if not raw_path.exists():
        raise ValueError("Drugs@FDA raw ZIP is missing")
    raw_bytes = raw_path.read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != manifest["source_sha256"]:
        raise ValueError("Drugs@FDA raw ZIP sha256 does not match manifest")
    return raw_bytes


def _product_strength_by_identity() -> dict[tuple[str, str], str]:
    with zipfile.ZipFile(io.BytesIO(_verified_drugsfda_raw())) as archive:
        product_rows = _table_rows(archive, "Products.txt")

    strengths: dict[tuple[str, str], str] = {}
    for row in product_rows:
        identity = (
            _normalize_number(row["ApplNo"], 6, "application number"),
            _normalize_number(row["ProductNo"], 3, "product number"),
        )
        strength = row["Strength"].strip()
        if not strength:
            raise ValueError(f"Drugs@FDA product strength is empty for {identity}")
        previous = strengths.get(identity)
        if previous is not None and previous != strength:
            raise ValueError(f"conflicting Drugs@FDA product strength for {identity}")
        strengths[identity] = strength
    return strengths


def build() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    crosscheck = json.loads(CROSSCHECK_PATH.read_text(encoding="utf-8"))
    raw_bytes = _verified_drugsfda_raw()
    if crosscheck["drugsfda"]["source_sha256"] != manifest["source_sha256"]:
        raise ValueError("product crosscheck and Drugs@FDA manifest use different source revisions")

    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        status_rows = _table_rows(archive, "MarketingStatus.txt")
        lookup_rows = _table_rows(archive, "MarketingStatus_Lookup.txt")

    description_by_id = {
        row["MarketingStatusID"].strip(): row["MarketingStatusDescription"].strip()
        for row in lookup_rows
    }
    if not description_by_id or any(not key or not value for key, value in description_by_id.items()):
        raise ValueError("Drugs@FDA MarketingStatus lookup is incomplete")

    status_by_identity: dict[tuple[str, str], str] = {}
    for row in status_rows:
        application_number = _normalize_number(row["ApplNo"], 6, "application number")
        product_number = _normalize_number(row["ProductNo"], 3, "product number")
        status_id = row["MarketingStatusID"].strip()
        status = description_by_id.get(status_id)
        if status is None:
            raise ValueError(f"unknown Drugs@FDA MarketingStatusID: {status_id!r}")
        identity = (application_number, product_number)
        previous = status_by_identity.get(identity)
        if previous is not None and previous != status:
            raise ValueError(f"conflicting Drugs@FDA marketing status for {identity}")
        status_by_identity[identity] = status

    counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for product in crosscheck["drugsfda_only"]:
        identity = (product["application_number"], product["product_number"])
        status = status_by_identity.get(identity)
        if status is None:
            raise ValueError(f"marketing status missing for Drugs@FDA-only product {identity}")
        counts[status] = counts.get(status, 0) + 1
        rows.append({**product, "marketing_status": status})

    rows.sort(key=lambda row: (row["application_number"], row["product_number"]))
    total = len(rows)
    if sum(counts.values()) != total:
        raise ValueError("marketing-status counts do not cover all Drugs@FDA-only products")

    return {
        "schema_version": 1,
        "authority": "U.S. Food and Drug Administration",
        "scope": "Drugs@FDA NDA and ANDA products absent from the current Orange Book product file",
        "identity_fields": crosscheck["identity_fields"],
        "drugsfda_source_sha256": manifest["source_sha256"],
        "orange_book_source_sha256": crosscheck["orange_book"]["source_sha256"],
        "drugsfda_only_products": total,
        "marketing_status_counts": dict(sorted(counts.items())),
        "products": rows,
    }


def _verified_primary_evidence(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    source = json.loads(PRIMARY_EVIDENCE_PATH.read_text(encoding="utf-8"))
    if source.get("authority") != "U.S. Food and Drug Administration":
        raise ValueError("primary evidence authority must be U.S. Food and Drug Administration")

    products = {
        (row["application_number"], row["product_number"]): row
        for row in analysis["products"]
    }
    strengths = _product_strength_by_identity()
    verified: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in source.get("records", []):
        identity = (record["application_number"], record["product_number"])
        if identity in seen:
            raise ValueError(f"duplicate primary evidence for {identity}")
        seen.add(identity)
        product = products.get(identity)
        if product is None:
            raise ValueError(f"primary evidence identity is not a Drugs@FDA-only product: {identity}")
        if product["marketing_status"] == TENTATIVE_APPROVAL_STATUS:
            raise ValueError(f"primary evidence duplicates tentative-approval evidence: {identity}")
        if record["drug_name"] != product["drug_name"]:
            raise ValueError(f"primary evidence drug name does not match canonical product: {identity}")
        if "strength" in record:
            canonical_strength = strengths.get(identity)
            if canonical_strength is None:
                raise ValueError(f"Drugs@FDA product strength is missing for primary evidence: {identity}")
            if record["strength"] != canonical_strength:
                raise ValueError(
                    f"primary evidence strength does not match Drugs@FDA product {identity}: "
                    f"{record['strength']!r} != {canonical_strength!r}"
                )
        if not record["source_url"].startswith("https://www.federalregister.gov/"):
            raise ValueError(f"primary evidence must use the official Federal Register source: {identity}")
        verified.append({**record, "marketing_status": product["marketing_status"]})

    return sorted(verified, key=lambda row: (row["application_number"], row["product_number"]))


def build_absence_evidence(analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = analysis or build()
    counts = analysis["marketing_status_counts"]
    tentative_approval_count = counts.get(TENTATIVE_APPROVAL_STATUS, 0)
    remaining_counts = {
        status: count
        for status, count in sorted(counts.items())
        if status != TENTATIVE_APPROVAL_STATUS
    }
    verified = _verified_primary_evidence(analysis)
    for record in verified:
        status = record["marketing_status"]
        if remaining_counts.get(status, 0) <= 0:
            raise ValueError(f"primary evidence exceeds remaining count for {status}")
        remaining_counts[status] -= 1
    remaining_counts = {status: count for status, count in remaining_counts.items() if count}
    remaining_unverified = sum(remaining_counts.values())
    if tentative_approval_count + len(verified) + remaining_unverified != analysis["drugsfda_only_products"]:
        raise ValueError("Orange Book absence evidence does not cover all Drugs@FDA-only products")

    return {
        "schema_version": 2,
        "authority": "U.S. Food and Drug Administration",
        "scope": "Evidence for why Drugs@FDA NDA and ANDA products are absent from the current Orange Book product file",
        "drugsfda_source_sha256": analysis["drugsfda_source_sha256"],
        "orange_book_source_sha256": analysis["orange_book_source_sha256"],
        "drugsfda_only_products": analysis["drugsfda_only_products"],
        "fda_documented_absence": {
            "tentative_approval_products": tentative_approval_count,
            "source_url": ORANGE_BOOK_QA_URL,
            "basis": "FDA states that drug products with tentative approval are not listed in the Orange Book.",
            "product_specific_primary_evidence": verified,
        },
        "remaining_unverified_products": remaining_unverified,
        "remaining_marketing_status_counts": remaining_counts,
        "interpretation": {
            "source_url": ORANGE_BOOK_PREFACE_URL,
            "note": "Prescription, over-the-counter, or discontinued Marketing Status alone does not establish why a product is absent from the Orange Book; the Orange Book also contains discontinued products when its inclusion criteria are met.",
        },
    }


def write() -> None:
    result = build()
    evidence = build_absence_evidence(result)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EVIDENCE_OUTPUT_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
