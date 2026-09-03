import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.refresh_fda_approvals import dated_detail_urls, extract_approval, refresh


AUG13_URL = "https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-iberdomide-daratumumab-and-hyaluronidase-fihj-and-dexamethasone"
AUG25_URL = "https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-zanidatamab-hrii-and-tislelizumab-jsgr-her2-positive-gastric-gastroesophageal-junction"
AUG26_URL = "https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-daraxonrasib-metastatic-pancreatic-adenocarcinoma"
AUG6_URL = "https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-vusolimogene-oderparepvec-wtpg-combination-nivolumab-melanoma"

LIST_HTML = b"""
<html><body><table><tbody>
<tr><td><a href="/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-vusolimogene-oderparepvec-wtpg-combination-nivolumab-melanoma">August 6</a></td><td>description</td><td>8/6/2026</td></tr>
<tr><td><a href="/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-iberdomide-daratumumab-and-hyaluronidase-fihj-and-dexamethasone">August 13</a></td><td>description</td><td>8/13/2026</td></tr>
<tr><td><a href="/drugs/resources-information-approved-drugs/fda-approves-zanidatamab-hrii-and-tislelizumab-jsgr-her2-positive-gastric-gastroesophageal-junction">August 25</a></td><td>description</td><td>8/25/2026</td></tr>
<tr><td><a href="/drugs/resources-information-approved-drugs/fda-approves-daraxonrasib-metastatic-pancreatic-adenocarcinoma">August 26</a></td><td>description</td><td>8/26/2026</td></tr>
</tbody></table></body></html>
"""
AUG13_HTML = b"""
<html><head><script type="application/ld+json">{"description":"On August 13, 2026, the Food and Drug Administration approved polluted metadata (WRONG, Wrong Sponsor), for wrong indication.","datePublished":"2026-08-13"}</script></head><body><main><p>On August 13, 2026, the Food and Drug Administration granted accelerated approval to iberdomide (Zenbexus, Bristol-Myers Squibb Company) in combination with daratumumab and hyaluronidase-fihj and dexamethasone for adults with multiple myeloma who have received at least one prior line of therapy including a proteasome inhibitor and an immunomodulatory agent.</p><p>Full prescribing information for Zenbexus will be posted.</p></main></body></html>
"""
AUG25_HTML = b"""
<html><body><main><p>On August 25, 2026, the Food and Drug Administration approved zanidatamab-hrii (Ziihera, Jazz Pharmaceuticals):</p><ul><li>in combination with fluoropyrimidine- and platinum-containing chemotherapy and tislelizumab-jsgr (Tevimbra, BeOne Medicines USA, Inc.), as first-line treatment for adults with HER2-positive unresectable locally advanced or metastatic gastric, gastroesophageal junction, or esophageal adenocarcinoma, and</li><li>in combination with fluoropyrimidine- and platinum-containing chemotherapy, as first-line treatment for adults with HER2-positive unresectable locally advanced or metastatic gastric, gastroesophageal junction, or esophageal adenocarcinoma.</li></ul><p>Today, the FDA also approved two companion diagnostic devices.</p></main></body></html>
"""
AUG26_HTML = b"""
<html><body><main><p>On August 26, 2026, the Food and Drug Administration approved daraxonrasib (RASONQUE, Revolution Medicines, Inc.), an inhibitor of the RAS GTPase family, for adults with metastatic pancreatic adenocarcinoma who have received at least one prior systemic therapy or who are not candidates for multiagent systemic therapy.</p></main></body></html>
"""


class FdaApprovalRefreshTest(unittest.TestCase):
    def test_dated_detail_urls_returns_all_rows_in_date_order(self):
        rows = dated_detail_urls(LIST_HTML)
        self.assertEqual([url for _, url in rows], [AUG6_URL, AUG13_URL, AUG25_URL, AUG26_URL])

    def test_extracts_simple_approval_fields(self):
        digest = hashlib.sha256(AUG26_HTML).hexdigest()
        record = extract_approval(
            AUG26_HTML,
            AUG26_URL,
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

    def test_approval_summary_uses_visible_main_content_not_json_ld(self):
        digest = hashlib.sha256(AUG13_HTML).hexdigest()
        record = extract_approval(AUG13_HTML, AUG13_URL, "2026-09-03T04:00:00Z", digest, "raw.html")
        self.assertEqual(record["generic_name"], "iberdomide")
        self.assertEqual(record["brand_name"], "Zenbexus")
        self.assertEqual(record["sponsor"], "Bristol-Myers Squibb Company")
        self.assertIn("multiple myeloma", record["indication"])
        self.assertTrue(record["approval_summary"].startswith("On August 13, 2026, the Food and Drug Administration granted accelerated approval"))
        self.assertNotIn("polluted metadata", record["approval_summary"])
        self.assertNotIn("datePublished", record["approval_summary"])

    def test_complex_multi_indication_page_preserves_official_summary_without_guessing(self):
        digest = hashlib.sha256(AUG25_HTML).hexdigest()
        record = extract_approval(AUG25_HTML, AUG25_URL, "2026-09-03T04:00:00Z", digest, "raw.html")
        self.assertEqual(record["approval_date"], "2026-08-25")
        self.assertEqual(record["generic_name"], "zanidatamab-hrii")
        self.assertEqual(record["brand_name"], "Ziihera")
        self.assertEqual(record["sponsor"], "Jazz Pharmaceuticals")
        self.assertIsNone(record["modality"])
        self.assertIsNone(record["indication"])
        self.assertIn("tislelizumab-jsgr", record["approval_summary"])
        self.assertIn("first-line treatment", record["approval_summary"])
        self.assertNotIn("companion diagnostic devices", record["approval_summary"])

    def test_refresh_backfills_missing_rows_between_existing_approvals(self):
        canonical = {
            "schema_version": "1.0.0",
            "retrieved_at": "2026-09-02T00:00:00Z",
            "sequencing_costs": [],
            "clinical_trials": [],
            "approvals": [
                {"id": "fda-2026-08-06-existing", "approval_date": "2026-08-06", "source_url": AUG6_URL},
                {"id": "fda-2026-08-26-existing", "approval_date": "2026-08-26", "source_url": AUG26_URL},
            ],
            "sources": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "multiomics-v1.json"
            raw_dir = root / "raw"
            data_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
            with patch("scripts.refresh_fda_approvals.fetch_bytes", side_effect=[LIST_HTML, AUG13_HTML, AUG25_HTML]):
                first = refresh(data_path, raw_dir)
            with patch("scripts.refresh_fda_approvals.fetch_bytes", return_value=LIST_HTML):
                second = refresh(data_path, raw_dir)

            persisted = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual([row["approval_date"] for row in persisted["approvals"]], ["2026-08-06", "2026-08-13", "2026-08-25", "2026-08-26"])
            self.assertEqual([row["approval_date"] for row in first], ["2026-08-13", "2026-08-25"])
            self.assertEqual(second, [])
            for record, html in zip(first, [AUG13_HTML, AUG25_HTML]):
                self.assertEqual((raw_dir / f"{record['source_sha256']}.html").read_bytes(), html)

    def test_refresh_repairs_existing_summary_from_persisted_raw(self):
        digest = hashlib.sha256(AUG13_HTML).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "multiomics-v1.json"
            raw_dir = root / "raw"
            raw_dir.mkdir()
            raw_path = raw_dir / f"{digest}.html"
            raw_path.write_bytes(AUG13_HTML)
            canonical = {
                "schema_version": "1.0.0",
                "retrieved_at": "2026-09-03T04:00:00Z",
                "sequencing_costs": [],
                "clinical_trials": [],
                "approvals": [{
                    "id": "fda-2026-08-13-iberdomide",
                    "authority": "U.S. Food and Drug Administration",
                    "approval_date": "2026-08-13",
                    "pathway": "accelerated approval",
                    "generic_name": "iberdomide",
                    "brand_name": "Zenbexus",
                    "sponsor": "Bristol-Myers Squibb Company",
                    "modality": None,
                    "indication": None,
                    "approval_summary": "polluted metadata",
                    "source_url": AUG13_URL,
                    "retrieved_at": "2026-09-03T04:00:00Z",
                    "source_sha256": digest,
                    "raw_path": raw_path.as_posix(),
                }],
                "sources": [],
            }
            data_path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
            one_row_list = LIST_HTML.replace(b'<tr><td><a href="/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-vusolimogene-oderparepvec-wtpg-combination-nivolumab-melanoma">August 6</a></td><td>description</td><td>8/6/2026</td></tr>', b'').replace(b'<tr><td><a href="/drugs/resources-information-approved-drugs/fda-approves-zanidatamab-hrii-and-tislelizumab-jsgr-her2-positive-gastric-gastroesophageal-junction">August 25</a></td><td>description</td><td>8/25/2026</td></tr>', b'').replace(b'<tr><td><a href="/drugs/resources-information-approved-drugs/fda-approves-daraxonrasib-metastatic-pancreatic-adenocarcinoma">August 26</a></td><td>description</td><td>8/26/2026</td></tr>', b'')
            with patch("scripts.refresh_fda_approvals.fetch_bytes", return_value=one_row_list):
                self.assertEqual(refresh(data_path, raw_dir), [])
            repaired = json.loads(data_path.read_text(encoding="utf-8"))["approvals"][0]
            self.assertIn("multiple myeloma", repaired["approval_summary"])
            self.assertNotIn("polluted metadata", repaired["approval_summary"])
            self.assertIn("multiple myeloma", repaired["indication"])
            self.assertEqual(repaired["source_sha256"], digest)

    def test_unparseable_detail_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "main content element"):
            extract_approval(b"<html><body>unexpected format</body></html>", AUG26_URL, "2026-09-03T04:00:00Z", "a" * 64, "raw.html")


if __name__ == "__main__":
    unittest.main()
