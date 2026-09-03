import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.refresh_fda_approvals import extract_approval, latest_detail_url, refresh


LIST_HTML = b"""
<html><body><table><tbody>
<tr><td><a href="/drugs/resources-information-approved-drugs/fda-approves-old-drug">Older approval</a></td><td>description</td><td>8/13/2026</td></tr>
<tr><td><a href="/drugs/resources-information-approved-drugs/fda-approves-daraxonrasib-metastatic-pancreatic-adenocarcinoma">FDA approves daraxonrasib</a></td><td>description</td><td>8/26/2026</td></tr>
</tbody></table></body></html>
"""
DETAIL_URL = "https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-daraxonrasib-metastatic-pancreatic-adenocarcinoma"
DETAIL_HTML = b"""
<html><body><main><p>On August 26, 2026, the Food and Drug Administration approved daraxonrasib (RASONQUE, Revolution Medicines, Inc.), an inhibitor of the RAS GTPase family, for adults with metastatic pancreatic adenocarcinoma who have received at least one prior systemic therapy or who are not candidates for multiagent systemic therapy.</p></main></body></html>
"""


class FdaApprovalRefreshTest(unittest.TestCase):
    def test_latest_detail_url_uses_newest_dated_row(self):
        self.assertEqual(latest_detail_url(LIST_HTML), DETAIL_URL)

    def test_extracts_required_approval_fields(self):
        digest = hashlib.sha256(DETAIL_HTML).hexdigest()
        record = extract_approval(
            DETAIL_HTML,
            DETAIL_URL,
            "2026-09-03T04:00:00Z",
            digest,
            f"data/raw/fda/oncology-approvals/{digest}.html",
        )
        self.assertEqual(record["approval_date"], "2026-08-26")
        self.assertEqual(record["pathway"], "approval")
        self.assertEqual(record["generic_name"], "daraxonrasib")
        self.assertEqual(record["brand_name"], "RASONQUE")
        self.assertEqual(record["sponsor"], "Revolution Medicines, Inc.")
        self.assertEqual(record["modality"], "inhibitor of the RAS GTPase family")
        self.assertIn("metastatic pancreatic adenocarcinoma", record["indication"])
        self.assertEqual(record["source_sha256"], digest)

    def test_refresh_persists_raw_evidence_and_does_not_duplicate_same_source(self):
        canonical = {
            "schema_version": "1.0.0",
            "retrieved_at": "2026-09-02T00:00:00Z",
            "sequencing_costs": [],
            "clinical_trials": [],
            "approvals": [],
            "sources": [],
        }
        digest = hashlib.sha256(DETAIL_HTML).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "multiomics-v1.json"
            raw_dir = root / "raw"
            data_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
            with patch("scripts.refresh_fda_approvals.fetch_bytes", side_effect=[LIST_HTML, DETAIL_HTML]):
                first = refresh(data_path, raw_dir)
            with patch("scripts.refresh_fda_approvals.fetch_bytes", side_effect=[LIST_HTML, DETAIL_HTML]):
                second = refresh(data_path, raw_dir)

            persisted = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(len(persisted["approvals"]), 1)
            self.assertEqual(first["source_sha256"], digest)
            self.assertEqual(second["source_sha256"], digest)
            self.assertEqual((raw_dir / f"{digest}.html").read_bytes(), DETAIL_HTML)

    def test_unparseable_detail_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "canonical approval sentence"):
            extract_approval(b"<html><body>unexpected format</body></html>", DETAIL_URL, "2026-09-03T04:00:00Z", "a" * 64, "raw.html")


if __name__ == "__main__":
    unittest.main()
