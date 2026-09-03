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
OUTPUT_PATH = ROOT / "api" / "v1" / "multiomics" / "fda-product-coverage-analysis.json"


def _normalize_number(value: str, width: int, label: str) -> str:
    text = value.strip()
    if not text or not text.isdigit() or len(text) > width:
        raise ValueError(f"invalid {label}: {value!r}")
    return text.zfill(width)


def _table_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = refresh_drugsfda._decode_table(archive.read(name))
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def build() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    crosscheck = json.loads(CROSSCHECK_PATH.read_text(encoding="utf-8"))
    raw_path = ROOT / manifest["raw_path"]
    if not raw_path.exists():
        raise ValueError("Drugs@FDA raw ZIP is missing")
    raw_bytes = raw_path.read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != manifest["source_sha256"]:
        raise ValueError("Drugs@FDA raw ZIP sha256 does not match manifest")
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


def write() -> None:
    result = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
