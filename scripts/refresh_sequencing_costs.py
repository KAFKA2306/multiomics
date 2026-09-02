#!/usr/bin/env python3
"""Refresh NHGRI DNA sequencing-cost observations from the official Excel table."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "multiomics-v1.json"
DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "nhgri" / "sequencing-costs"
SOURCE_PAGE = "https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data"
UA = "KAFKA2306-multiomics/1.0"


def fetch_bytes(url: str, accept: str = "*/*") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def find_excel_url(page_html: bytes) -> str:
    text = page_html.decode("utf-8")
    matches = re.findall(r'href=["\']([^"\']+\.(?:xls|xlsx))["\']', text, flags=re.IGNORECASE)
    candidates = [urllib.parse.urljoin(SOURCE_PAGE, value) for value in matches if "sequenc" in value.lower() and "cost" in value.lower()]
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one NHGRI sequencing-cost Excel link, found {len(candidates)}")
    url = candidates[0]
    if not url.lower().endswith(".xls"):
        raise ValueError(f"unsupported NHGRI workbook format: {url}")
    return url


def parse_xls(raw: bytes) -> list[tuple[str, float, float]]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd==2.0.2 is required to parse the official NHGRI .xls workbook") from exc

    workbook = xlrd.open_workbook(file_contents=raw)
    sheet = workbook.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(3)]
    if headers != ["Date", "Cost per Mb", "Cost per Genome"]:
        raise ValueError(f"unexpected NHGRI workbook headers: {headers}")

    rows: list[tuple[str, float, float]] = []
    for row_index in range(1, sheet.nrows):
        date_cell = sheet.cell(row_index, 0)
        if date_cell.ctype == xlrd.XL_CELL_DATE:
            observed = xlrd.xldate_as_datetime(date_cell.value, workbook.datemode)
            period = observed.strftime("%Y-%m")
        else:
            raw_period = str(date_cell.value).strip()
            try:
                observed = datetime.strptime(raw_period, "%b-%y")
            except ValueError as exc:
                raise ValueError(f"unexpected NHGRI period at row {row_index + 1}: {raw_period}") from exc
            period = observed.strftime("%Y-%m")

        cost_per_mb = float(sheet.cell_value(row_index, 1))
        cost_per_genome = float(sheet.cell_value(row_index, 2))
        if cost_per_mb <= 0 or cost_per_genome <= 0:
            raise ValueError(f"non-positive NHGRI cost at row {row_index + 1}")
        rows.append((period, cost_per_mb, cost_per_genome))

    periods = [row[0] for row in rows]
    if not rows or periods != sorted(periods) or len(periods) != len(set(periods)):
        raise ValueError("NHGRI periods must be non-empty, unique, and ascending")
    return rows


def build_records(
    rows: list[tuple[str, float, float]], *, source_url: str, retrieved_at: str, source_sha256: str, raw_path: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for period, cost_per_mb, cost_per_genome in rows:
        records.extend(
            [
                {
                    "id": f"nhgri-{period}-cost-per-megabase",
                    "period": period,
                    "metric": "cost_per_megabase",
                    "value": cost_per_mb,
                    "unit": "USD_per_megabase",
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "source_sha256": source_sha256,
                    "raw_path": raw_path,
                },
                {
                    "id": f"nhgri-{period}-cost-per-genome",
                    "period": period,
                    "metric": "cost_per_genome",
                    "value": cost_per_genome,
                    "unit": "USD_per_human_genome",
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "source_sha256": source_sha256,
                    "raw_path": raw_path,
                },
            ]
        )
    return records


def refresh(data_path: Path, raw_dir: Path) -> list[dict[str, Any]]:
    page_html = fetch_bytes(SOURCE_PAGE, "text/html")
    source_url = find_excel_url(page_html)
    raw = fetch_bytes(source_url, "application/vnd.ms-excel")
    digest = hashlib.sha256(raw).hexdigest()

    data = json.loads(data_path.read_text(encoding="utf-8"))
    existing = data.get("sequencing_costs", [])
    if existing and all(row.get("source_sha256") == digest for row in existing):
        return existing

    rows = parse_xls(raw)
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_path = raw_dir / f"{digest}.xls"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)

    records = build_records(
        rows,
        source_url=source_url,
        retrieved_at=retrieved_at,
        source_sha256=digest,
        raw_path=raw_path.relative_to(ROOT).as_posix(),
    )
    data["sequencing_costs"] = records
    data["retrieved_at"] = retrieved_at
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args()
    records = refresh(args.data, args.raw_dir)
    print(json.dumps({"observations": len(records), "latest_period": records[-1]["period"]}, sort_keys=True))


if __name__ == "__main__":
    main()
