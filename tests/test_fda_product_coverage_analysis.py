import json
import unittest
from pathlib import Path

from scripts import analyze_fda_product_coverage

ROOT = Path(__file__).resolve().parents[1]


class FdaProductCoverageAnalysisTest(unittest.TestCase):
    def test_real_drugsfda_only_products_have_official_marketing_status(self):
        result = analyze_fda_product_coverage.build()
        crosscheck = json.loads(
            (ROOT / "api" / "v1" / "multiomics" / "fda-product-identity-crosscheck.json").read_text(encoding="utf-8")
        )

        self.assertEqual(result["drugsfda_only_products"], crosscheck["counts"]["drugsfda_only_products"])
        self.assertEqual(sum(result["marketing_status_counts"].values()), result["drugsfda_only_products"])
        self.assertEqual(len(result["products"]), result["drugsfda_only_products"])
        self.assertTrue(all(row["marketing_status"] for row in result["products"]))
        self.assertEqual(result["drugsfda_source_sha256"], crosscheck["drugsfda"]["source_sha256"])
        self.assertEqual(result["orange_book_source_sha256"], crosscheck["orange_book"]["source_sha256"])

    def test_primary_evidence_reduces_only_matching_unverified_products(self):
        analysis = analyze_fda_product_coverage.build()
        evidence = analyze_fda_product_coverage.build_absence_evidence(analysis)
        documented = evidence["fda_documented_absence"]
        tentative = documented["tentative_approval_products"]
        verified = documented["product_specific_primary_evidence"]
        remaining = evidence["remaining_unverified_products"]

        self.assertEqual(tentative, analysis["marketing_status_counts"]["None (Tentative Approval)"])
        self.assertEqual(tentative + len(verified) + remaining, analysis["drugsfda_only_products"])
        self.assertEqual(len(verified), 5)
        identities = {
            (row["application_number"], row["product_number"], row["drug_name"])
            for row in verified
        }
        self.assertEqual(
            identities,
            {
                ("013056", "001", "PENTHRANE"),
                ("019415", "002", "METRODIN"),
                ("019415", "003", "METRODIN"),
                ("019415", "004", "FERTINEX"),
                ("019415", "005", "FERTINEX"),
            },
        )
        self.assertTrue(all(row["marketing_status"] == "Discontinued" for row in verified))
        self.assertEqual(remaining, 786)
        self.assertEqual(evidence["remaining_marketing_status_counts"]["Discontinued"], 207)
        self.assertTrue(all(row["source_url"].startswith("https://www.federalregister.gov/") for row in verified))
        self.assertNotIn("None (Tentative Approval)", evidence["remaining_marketing_status_counts"])
        self.assertEqual(sum(evidence["remaining_marketing_status_counts"].values()), remaining)

    def test_committed_analysis_is_deterministic_when_present(self):
        output = ROOT / "api" / "v1" / "multiomics" / "fda-product-coverage-analysis.json"
        if not output.exists():
            self.skipTest("derived analysis is produced by the refresh workflow after merge")
        committed = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(committed, analyze_fda_product_coverage.build())


if __name__ == "__main__":
    unittest.main()
