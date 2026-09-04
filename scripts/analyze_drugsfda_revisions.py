#!/usr/bin/env python3
"""Compare the two latest persisted Drugs@FDA revisions at product identity level."""

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
RAW_DIR = ROOT / "data" / "raw" / "fda" / "drugsatfda"
OUTPUT_PATH = ROOT / "api" / "v1" / "multiomics" / "drugsfda-revision-changes.json"
TRACKED_FIELDS = ("application_type", "drug_name", "active_ingredient", "marketing_status")


def _normalize_number(value: str, width: int, label: str) -> str:
    text = value.strip()
    if not text or not text.isdigit() or len(text) > width:
        raise ValueError(f"invalid {label}: {value!r}")
    return text.zfill(width)


def _table_rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = refresh_drugsfda._decode_table(archive.read(name))
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def _verified_raw(source_sha256: str) -> bytes:
    raw_path = RAW_DIR / f"{source_sha256}.zip"
    if not raw_path.exists():
        raise ValueError(f"Drugs@FDA raw ZIP is missing for revision {source_sha256}")
    payload = raw_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source_sha256:
        raise ValueError(f"Drugs@FDA raw ZIP sha256 mismatch for revision {source_sha256}")
    return payload


def _product_state(payload: bytes) -> dict[tuple[str, str], dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        applications = _table_rows(archive, "Applications.txt")
        products = _table_rows(archive, "Products.txt")
        status_rows = _table_rows(archive, "MarketingStatus.txt")
        lookup_rows = _table_rows(archive, "MarketingStatus_Lookup.txt")

    application_type_by_number: dict[str, str] = {}
    for row in applications:
        application_number = _normalize_number(row["ApplNo"], 6, "application number")
        application_type = row["ApplType"].strip()
        previous = application_type_by_number.get(application_number)
        if previous is not None and previous != application_type:
            raise ValueError(f"conflicting application type for {application_number}")
        application_type_by_number[application_number] = application_type

    description_by_id = {
        row["MarketingStatusID"].strip(): row["MarketingStatusDescription"].strip()
        for row in lookup_rows
    }
    if not description_by_id or any(not key or not value for key, value in description_by_id.items()):
        raise ValueError("Drugs@FDA MarketingStatus lookup is incomplete")

    status_by_identity: dict[tuple[str, str], str] = {}
    for row in status_rows:
        identity = (
            _normalize_number(row["ApplNo"], 6, "application number"),
            _normalize_number(row["ProductNo"], 3, "product number"),
        )
        status = description_by_id.get(row["MarketingStatusID"].strip())
        if status is None:
            raise ValueError(f"unknown Drugs@FDA MarketingStatusID: {row['MarketingStatusID']!r}")
        previous = status_by_identity.get(identity)
        if previous is not None and previous != status:
            raise ValueError(f"conflicting marketing status for {identity}")
        status_by_identity[identity] = status

    state: dict[tuple[str, str], dict[str, str]] = {}
    for row in products:
        application_number = _normalize_number(row["ApplNo"], 6, "application number")
        application_type = application_type_by_number.get(application_number)
        if application_type not in {"NDA", "ANDA"}:
            continue
        product_number = _normalize_number(row["ProductNo"], 3, "product number")
        identity = (application_number, product_number)
        if identity in state:
            raise ValueError(f"duplicate Drugs@FDA product identity: {identity}")
        marketing_status = status_by_identity.get(identity)
        if marketing_status is None:
            raise ValueError(f"marketing status missing for Drugs@FDA product {identity}")
        state[identity] = {
            "application_type": application_type,
            "application_number": application_number,
            "product_number": product_number,
            "drug_name": row["DrugName"].strip(),
            "active_ingredient": row["ActiveIngredient"].strip(),
            "marketing_status": marketing_status,
        }
    return state


def _compare_states(
    previous: dict[tuple[str, str], dict[str, str]],
    current: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    previous_keys = set(previous)
    current_keys = set(current)
    added = [current[key] for key in sorted(current_keys - previous_keys)]
    removed = [previous[key] for key in sorted(previous_keys - current_keys)]
    changed: list[dict[str, Any]] = []
    for key in sorted(previous_keys & current_keys):
        field_changes = {
            field: {"before": previous[key][field], "after": current[key][field]}
            for field in TRACKED_FIELDS
            if previous[key][field] != current[key][field]
        }
        if field_changes:
            changed.append(
                {
                    "application_number": key[0],
                    "product_number": key[1],
                    "changes": field_changes,
                }
            )
    return {
        "counts": {
            "previous_products": len(previous),
            "current_products": len(current),
            "added_products": len(added),
            "removed_products": len(removed),
            "changed_products": len(changed),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _revision_pair(manifest: dict[str, Any], existing: dict[str, Any] | None) -> tuple[dict[str, str], dict[str, str]]:
    current = {
        "source_sha256": manifest["source_sha256"],
        "retrieved_at": manifest["retrieved_at"],
    }
    if existing is None:
        raise ValueError("Drugs@FDA revision output is missing; bootstrap with a verified previous revision")
    existing_current = existing.get("current_revision")
    existing_previous = existing.get("previous_revision")
    if not isinstance(existing_current, dict) or not isinstance(existing_previous, dict):
        raise ValueError("existing Drugs@FDA revision output lacks revision metadata")
    if existing_current.get("source_sha256") == current["source_sha256"]:
        previous = existing_previous
    else:
        previous = existing_current
    if not previous.get("source_sha256") or not previous.get("retrieved_at"):
        raise ValueError("previous Drugs@FDA revision metadata is incomplete")
    if previous["source_sha256"] == current["source_sha256"]:
        raise ValueError("Drugs@FDA revision comparison requires two distinct source revisions")
    return previous, current


def build(existing_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    existing = json.loads(existing_path.read_text(encoding="utf-8")) if existing_path.exists() else None
    previous_revision, current_revision = _revision_pair(manifest, existing)
    previous_state = _product_state(_verified_raw(previous_revision["source_sha256"]))
    current_state = _product_state(_verified_raw(current_revision["source_sha256"]))
    comparison = _compare_states(previous_state, current_state)
    return {
        "schema_version": 1,
        "authority": "U.S. Food and Drug Administration",
        "dataset": "Drugs@FDA Data Files",
        "scope": "NDA and ANDA product identity and marketing-status changes between the latest two persisted official Drugs@FDA revisions",
        "identity_fields": ["application_number", "product_number"],
        "previous_revision": previous_revision,
        "current_revision": current_revision,
        **comparison,
        "interpretation": "A changed record reports only fields that differ between official snapshots; it does not infer the regulatory cause of the change.",
    }


def write() -> None:
    result = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()
