import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.refresh_sequencing_costs import build_records, find_excel_url, refresh


class SequencingCostsRefreshTest(unittest.TestCase):
    def test_finds_official_excel_link(self):
        html = b'<a href="/sites/default/files/Sequencing_Cost_Data_Table_May2022.xls">Sequencing Costs 2022</a>'
        self.assertEqual(
            find_excel_url(html),
            "https://www.genome.gov/sites/default/files/Sequencing_Cost_Data_Table_May2022.xls",
        )

    def test_builds_two_observations_per_period(self):
        records = build_records(
            [("2021-08", 0.006, 562.0), ("2021-11", 0.006, 552.0)],
            source_url="https://www.genome.gov/example.xls",
            retrieved_at="2026-09-02T19:40:00Z",
            source_sha256="a" * 64,
            raw_path="data/raw/nhgri/sequencing-costs/a.xls",
        )
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0]["period"], "2021-08")
        self.assertEqual(records[0]["metric"], "cost_per_megabase")
        self.assertEqual(records[0]["value"], 0.006)
        self.assertEqual(records[1]["metric"], "cost_per_genome")
        self.assertEqual(records[1]["value"], 562.0)
        self.assertTrue(all(row["source_sha256"] == "a" * 64 for row in records))

    def test_unchanged_workbook_does_not_rewrite_canonical_data(self):
        raw = b"official workbook bytes"
        digest = hashlib.sha256(raw).hexdigest()
        source_url = "https://www.genome.gov/Sequencing_Cost_Data_Table_May2022.xls"
        existing = [
            {
                "id": "nhgri-2022-05-cost-per-genome",
                "period": "2022-05",
                "metric": "cost_per_genome",
                "value": 525,
                "unit": "USD_per_human_genome",
                "source_url": source_url,
                "retrieved_at": "2026-09-02T19:40:00Z",
                "source_sha256": digest,
                "raw_path": f"data/raw/nhgri/sequencing-costs/{digest}.xls",
            }
        ]
        canonical = {"schema_version": "1.0.0", "retrieved_at": "2026-09-02T19:40:00Z", "sequencing_costs": existing}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "multiomics-v1.json"
            raw_dir = root / "raw"
            original = json.dumps(canonical, indent=2) + "\n"
            data_path.write_text(original, encoding="utf-8")

            with patch(
                "scripts.refresh_sequencing_costs.fetch_bytes",
                side_effect=[
                    f'<a href="{source_url}">Sequencing Cost Data</a>'.encode(),
                    raw,
                ],
            ):
                result = refresh(data_path, raw_dir)

            self.assertEqual(result, existing)
            self.assertEqual(data_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
