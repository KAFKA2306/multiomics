#!/usr/bin/env python3
"""Persist the official Drugs@FDA ZIP and a deterministic source manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "fda" / "drugsatfda"
MANIFEST = ROOT / "data" / "drugsfda-source.json"
SOURCE_URL = "https://www.fda.gov/media/89850/download?attachment="
PAGE_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files"
USER_AGENT = "KAFKA2306-multiomics/1.0 (+https://github.com/KAFKA2306/multiomics)"
EXPECTED_HEADERS = {
    "ActionTypes_Lookup.txt": ["ActionTypes_LookupID", "ActionTypes_LookupDescription", "SupplCategoryLevel1Code", "SupplCategoryLevel2Code"],
    "ApplicationDocs.txt": ["ApplicationDocsID", "ApplicationDocsTypeID", "ApplNo", "SubmissionType", "SubmissionNo", "ApplicationDocsTitle", "ApplicationDocsURL", "ApplicationDocsDate"],
    "Applications.txt": ["ApplNo", "ApplType", "ApplPublicNotes", "SponsorName"],
    "ApplicationsDocsType_Lookup.txt": ["ApplicationDocsType_Lookup_ID", "ApplicationDocsType_Lookup_Description"],
    "Join_Submission_ActionTypes_Lookup.txt": ["SubmissionType", "j_submissionActionTypeID", "ApplNo", "SubmissionNo", "ActionTypes_LookupID"],
    "MarketingStatus.txt": ["MarketingStatusID", "ApplNo", "ProductNo"],
    "MarketingStatus_Lookup.txt": ["MarketingStatusID", "MarketingStatusDescription"],
    "Products.txt": ["ApplNo", "ProductNo", "Form", "Strength", "ReferenceDrug", "DrugName", "ActiveIngredient", "ReferenceStandard"],
    "SubmissionClass_Lookup.txt": ["SubmissionClassCodeID", "SubmissionClassCode", "SubmissionClassCodeDescription"],
    "SubmissionPropertyType.txt": ["ApplNo", "SubmissionType", "SubmissionNo", "SubmissionPropertyTypeCode", "SubmissionPropertyTypeID"],
    "Submissions.txt": ["ApplNo", "SubmissionClassCodeID", "SubmissionType", "SubmissionNo", "SubmissionStatus", "SubmissionStatusDate", "SubmissionsPublicNotes", "ReviewPriority"],
    "TE.txt": ["ApplNo", "ProductNo", "MarketingStatusID", "TECode"],
}


def fetch_zip(url: str = SOURCE_URL) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        final_host = urlparse(response.geturl()).hostname
        if final_host != "www.fda.gov":
            raise ValueError(f"unexpected Drugs@FDA redirect host: {final_host}")
        payload = response.read()
    if not payload.startswith(b"PK"):
        raise ValueError("Drugs@FDA response is not a ZIP archive")
    return payload


def _decode_table(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("Drugs@FDA table is neither UTF-8 nor Windows-1252 text")


def inspect_zip(payload: bytes) -> list[dict[str, object]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = sorted(name for name in archive.namelist() if not name.endswith("/"))
        basenames = [Path(name).name for name in names]
        if len(set(basenames)) != len(basenames):
            raise ValueError("Drugs@FDA archive contains duplicate table basenames")
        if set(basenames) != set(EXPECTED_HEADERS):
            raise ValueError(f"Drugs@FDA archive table set changed: {basenames!r}")

        tables: list[dict[str, object]] = []
        for name in names:
            raw = archive.read(name)
            text = _decode_table(raw)
            reader = csv.reader(io.StringIO(text), delimiter="\t")
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError(f"Drugs@FDA table is empty: {name}") from exc
            header = [value.strip().lstrip("\ufeff") for value in header]
            row_count = sum(1 for _ in reader)
            base = Path(name).name
            if header != EXPECTED_HEADERS[base]:
                raise ValueError(f"Drugs@FDA header mismatch for {base}: {header!r}")
            tables.append({"file_name": name, "header": header, "row_count": row_count, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)})
    return tables


def refresh(raw_dir: Path = RAW, manifest_path: Path = MANIFEST) -> dict[str, object] | None:
    payload = fetch_zip()
    digest = hashlib.sha256(payload).hexdigest()
    raw_path = raw_dir / f"{digest}.zip"
    tables = inspect_zip(payload)

    if manifest_path.exists():
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        if current.get("source_sha256") == digest:
            if not raw_path.exists():
                raise ValueError("Drugs@FDA manifest exists but raw ZIP is missing")
            return None

    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        raw_path.write_bytes(payload)
    relative_raw_path = raw_path.relative_to(ROOT).as_posix() if raw_dir == RAW else raw_path.as_posix()
    manifest = {
        "schema_version": 1,
        "authority": "U.S. Food and Drug Administration",
        "dataset": "Drugs@FDA Data Files",
        "source_page_url": PAGE_URL,
        "source_download_url": SOURCE_URL,
        "retrieved_at": retrieved_at,
        "source_sha256": digest,
        "raw_path": relative_raw_path,
        "archive_size_bytes": len(payload),
        "table_count": len(tables),
        "tables": tables,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    result = refresh(args.raw_dir, args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
