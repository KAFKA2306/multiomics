import unittest

from scripts import analyze_drugsfda_revisions


class DrugsFdaRevisionTest(unittest.TestCase):
    def test_compare_reports_add_remove_and_field_change(self):
        previous = {
            ("000001", "001"): {
                "application_type": "NDA",
                "application_number": "000001",
                "product_number": "001",
                "drug_name": "A",
                "active_ingredient": "A",
                "marketing_status": "Prescription",
            },
            ("000002", "001"): {
                "application_type": "ANDA",
                "application_number": "000002",
                "product_number": "001",
                "drug_name": "B",
                "active_ingredient": "B",
                "marketing_status": "Prescription",
            },
        }
        current = {
            ("000001", "001"): {
                **previous[("000001", "001")],
                "marketing_status": "None (Tentative Approval)",
            },
            ("000003", "001"): {
                "application_type": "ANDA",
                "application_number": "000003",
                "product_number": "001",
                "drug_name": "C",
                "active_ingredient": "C",
                "marketing_status": "Prescription",
            },
        }
        result = analyze_drugsfda_revisions._compare_states(previous, current)
        self.assertEqual(
            result["counts"],
            {
                "previous_products": 2,
                "current_products": 2,
                "added_products": 1,
                "removed_products": 1,
                "changed_products": 1,
            },
        )
        self.assertEqual(result["added"][0]["application_number"], "000003")
        self.assertEqual(result["removed"][0]["application_number"], "000002")
        self.assertEqual(
            result["changed"],
            [
                {
                    "application_number": "000001",
                    "product_number": "001",
                    "changes": {
                        "marketing_status": {
                            "before": "Prescription",
                            "after": "None (Tentative Approval)",
                        }
                    },
                }
            ],
        )

    def test_revision_pair_rolls_current_revision_forward(self):
        manifest = {"source_sha256": "new", "retrieved_at": "2026-09-05T00:00:00Z"}
        existing = {
            "previous_revision": {"source_sha256": "old", "retrieved_at": "2026-09-03T00:00:00Z"},
            "current_revision": {"source_sha256": "current", "retrieved_at": "2026-09-04T00:00:00Z"},
        }
        previous, current = analyze_drugsfda_revisions._revision_pair(manifest, existing)
        self.assertEqual(previous, existing["current_revision"])
        self.assertEqual(current, manifest)

    def test_revision_pair_rebuilds_same_pair_when_source_is_unchanged(self):
        manifest = {"source_sha256": "current", "retrieved_at": "2026-09-04T00:00:00Z"}
        existing = {
            "previous_revision": {"source_sha256": "old", "retrieved_at": "2026-09-03T00:00:00Z"},
            "current_revision": dict(manifest),
        }
        previous, current = analyze_drugsfda_revisions._revision_pair(manifest, existing)
        self.assertEqual(previous, existing["previous_revision"])
        self.assertEqual(current, manifest)


if __name__ == "__main__":
    unittest.main()
