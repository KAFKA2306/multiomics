#!/usr/bin/env python3
"""Refresh FDA oncology approval notifications into canonical data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multiomics-v1.json"
RAW = ROOT / "data" / "raw" / "fda" / "oncology-approvals"
LIST_URL = "https://www.fda.gov/drugs/resources-information-approved-drugs/oncology-cancerhematologic-malignancies-approval-notifications"
USER_AGENT = "KAFKA2306-multiomics/1.0 (+https://github.com/KAFKA2306/multiomics)"
DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
HEADER_RE = re.compile(
    r"^On ([A-Z][a-z]+ \d{1,2}, \d{4}), the Food and Drug Administration "
    r"(granted accelerated approval|granted traditional approval|approved)(?: to)? "
    r"(.+?) \(([^,()]+), (.+?)\)(.*)$"
)
MODALITY_RE = re.compile(r"^,\s*(?:an?|the) (.+?), for (.+)$")
SUMMARY_END_MARKERS = (
    " Full prescribing information",
    " Today, the FDA also approved",
    " Efficacy was evaluated",
    " The prescribing information",
)


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        final_host = urlparse(response.geturl()).hostname
        if final_host != "www.fda.gov":
            raise ValueError(f"unexpected FDA redirect host: {final_host}")
        return response.read()


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[list[str], str | None]] = []
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._parts: list[str] = []
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._in_row = True
            self._cells = []
            self._href = None
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._parts = []
        elif self._in_row and tag == "a" and self._href is None:
            href = dict(attrs).get("href")
            if href:
                self._href = href

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_row and tag in {"td", "th"} and self._in_cell:
            self._cells.append(" ".join("".join(self._parts).split()))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            self.rows.append((self._cells, self._href))
            self._in_row = False


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def dated_detail_urls(list_html: bytes) -> list[tuple[datetime, str]]:
    parser = _TableParser()
    parser.feed(list_html.decode("utf-8", errors="strict"))
    candidates: dict[str, datetime] = {}
    for cells, href in parser.rows:
        if not href or not href.startswith("/drugs/resources-information-approved-drugs/"):
            continue
        dates = [cell for cell in cells if DATE_RE.fullmatch(cell)]
        if not dates:
            continue
        date = datetime.strptime(dates[-1], "%m/%d/%Y")
        url = urljoin(LIST_URL, href)
        previous = candidates.get(url)
        if previous is not None and previous != date:
            raise ValueError(f"FDA oncology approval link has conflicting dates: {url}")
        candidates[url] = date
    if not candidates:
        raise ValueError("FDA oncology approval table did not contain a dated approval detail link")
    return sorted(((date, url) for url, date in candidates.items()), key=lambda item: (item[0], item[1]))


def _approval_summary(detail_html: bytes) -> str:
    parser = _TextParser()
    parser.feed(detail_html.decode("utf-8", errors="strict"))
    text = " ".join(" ".join(parser.parts).split())
    start_match = re.search(r"On [A-Z][a-z]+ \d{1,2}, \d{4}, the Food and Drug Administration ", text)
    if not start_match:
        raise ValueError("FDA approval detail page did not contain a canonical approval sentence")
    summary = text[start_match.start():]
    ends = [summary.find(marker) for marker in SUMMARY_END_MARKERS if summary.find(marker) > 0]
    if ends:
        summary = summary[: min(ends)]
    return summary.strip()


def extract_approval(detail_html: bytes, source_url: str, retrieved_at: str, source_sha256: str, raw_path: str) -> dict[str, object]:
    summary = _approval_summary(detail_html)
    match = HEADER_RE.match(summary)
    if not match:
        raise ValueError("FDA approval detail page did not match the canonical approval sentence")

    date_text, action, generic_name, brand_name, sponsor, remainder = match.groups()
    generic_name = generic_name.strip()
    brand_name = brand_name.strip()
    sponsor = sponsor.strip()
    if not all((generic_name, brand_name, sponsor)):
        raise ValueError("FDA approval detail page contained an empty required product field")

    modality: str | None = None
    indication: str | None = None
    modality_match = MODALITY_RE.match(remainder.strip())
    if modality_match:
        modality, indication = modality_match.groups()
        modality = modality.strip()
        indication = indication.strip().rstrip(".")
    else:
        normalized_remainder = remainder.strip().lstrip(":,").strip()
        for_token = " for "
        if normalized_remainder.count(for_token) == 1:
            _, indication = normalized_remainder.split(for_token, 1)
            indication = indication.strip().rstrip(".")

    approval_date = datetime.strptime(date_text, "%B %d, %Y").date().isoformat()
    pathway = {
        "granted accelerated approval": "accelerated approval",
        "granted traditional approval": "traditional approval",
        "approved": "approval",
    }[action]
    slug = re.sub(r"[^a-z0-9]+", "-", generic_name.lower()).strip("-")
    return {
        "id": f"fda-{approval_date}-{slug}",
        "authority": "U.S. Food and Drug Administration",
        "approval_date": approval_date,
        "pathway": pathway,
        "generic_name": generic_name,
        "brand_name": brand_name,
        "sponsor": sponsor,
        "modality": modality,
        "indication": indication,
        "approval_summary": summary,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "source_sha256": source_sha256,
        "raw_path": raw_path,
    }


def refresh(data_path: Path = DATA, raw_dir: Path = RAW) -> list[dict[str, object]]:
    list_html = fetch_bytes(LIST_URL)
    candidates = dated_detail_urls(list_html)
    canonical = json.loads(data_path.read_text(encoding="utf-8"))
    approvals = canonical.get("approvals")
    if not isinstance(approvals, list):
        raise ValueError("canonical approvals must be an array")

    existing_urls = {row.get("source_url") for row in approvals}
    if approvals:
        baseline = min(datetime.fromisoformat(row["approval_date"]) for row in approvals)
        candidates = [(date, url) for date, url in candidates if date >= baseline]
    missing = [(date, url) for date, url in candidates if url not in existing_urls]
    if not missing:
        return []

    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    records: list[dict[str, object]] = []
    for listed_date, source_url in missing:
        detail_html = fetch_bytes(source_url)
        digest = hashlib.sha256(detail_html).hexdigest()
        raw_path = raw_dir / f"{digest}.html"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if not raw_path.exists():
            raw_path.write_bytes(detail_html)
        relative_raw_path = raw_path.relative_to(ROOT).as_posix() if raw_dir == RAW else raw_path.as_posix()
        record = extract_approval(detail_html, source_url, retrieved_at, digest, relative_raw_path)
        if datetime.fromisoformat(record["approval_date"]) != listed_date:
            raise ValueError(f"FDA list/detail date mismatch for {source_url}")
        if any(row.get("id") == record["id"] for row in approvals):
            raise ValueError(f"FDA approval identity already exists with a different source URL: {record['id']}")
        approvals.append(record)
        records.append(record)

    approvals.sort(key=lambda row: (row["approval_date"], row["id"]))
    canonical["retrieved_at"] = retrieved_at
    data_path.write_text(json.dumps(canonical, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    args = parser.parse_args()
    records = refresh(args.data, args.raw_dir)
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
