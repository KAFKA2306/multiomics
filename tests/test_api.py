import json
import unittest
from pathlib import Path

from scripts import build_api

ROOT = Path(__file__).resolve().parents[1]


class MultiomicsApiTest(unittest.TestCase):
    def test_api_projection_matches_canonical_data(self):
        data = json.loads((ROOT / "data" / "multiomics-v1.json").read_text(encoding="utf-8"))
        index, metrics = build_api.build(data)

        self.assertEqual(
            {row["metric"] for row in metrics["observations"]},
            {
                "clinical_trial_count",
                "multiomics_trial_count",
                "fda_approval_count",
                "sequencing_cost_per_genome_usd",
                "sequencing_cost_per_megabase_usd",
            },
        )
        self.assertEqual(index["observation_counts"]["sequencing_costs"], len(data["sequencing_costs"]))
        self.assertEqual(index["observation_counts"]["clinical_trials"], len(data["clinical_trials"]))
        self.assertEqual(index["observation_counts"]["approvals"], len(data["approvals"]))
        self.assertEqual(index["observation_counts"]["metrics"], len(metrics["observations"]))
        count_rows = [
            row
            for row in metrics["observations"]
            if row["metric"] in {"clinical_trial_count", "multiomics_trial_count", "fda_approval_count"}
        ]
        self.assertTrue(all(row["qualifier"] == "tracked_repository_records" for row in count_rows))

        expected_sources = {row["source_url"] for row in data["sequencing_costs"]}
        expected_sources.update(row["source_url"] for row in data["clinical_trials"])
        expected_sources.update(row["source_url"] for row in data["approvals"])
        self.assertEqual(set(index["source_urls"]), expected_sources)

    def test_drugsfda_crosswalk_uses_current_real_records_without_collapsing_submissions(self):
        data = json.loads((ROOT / "data" / "multiomics-v1.json").read_text(encoding="utf-8"))
        crosswalk = build_api.build_drugsfda_crosswalk(data)
        by_brand = {row["brand_name"].upper(): row for row in crosswalk["approvals"]}

        self.assertEqual(by_brand["TUDRIQEV"]["applications"], [])
        self.assertEqual(by_brand["ZENBEXUS"]["applications"][0]["application_number"], "221075")
        self.assertEqual(by_brand["RASONQUE"]["applications"][0]["application_number"], "220910")
        ziihera = by_brand["ZIIHERA"]["applications"][0]
        self.assertEqual(ziihera["application_number"], "761416")
        self.assertEqual(
            [row["submission_number"] for row in ziihera["submissions_on_notification_date"]],
            ["2", "3"],
        )
        descriptions = {
            action["description"]
            for submission in ziihera["submissions_on_notification_date"]
            for action in submission["action_types"]
        }
        self.assertEqual(descriptions, {"Efficacy-New Indication", "Labeling-Package Insert"})
        print("DRUGSFDA_CROSSWALK=" + json.dumps(crosswalk, ensure_ascii=False, sort_keys=True))

    def test_committed_api_is_deterministic(self):
        data = json.loads((ROOT / "data" / "multiomics-v1.json").read_text(encoding="utf-8"))
        expected_index, expected_metrics = build_api.build(data)
        expected_crosswalk = build_api.build_drugsfda_crosswalk(data)
        committed_index = json.loads((ROOT / "api" / "v1" / "multiomics" / "index.json").read_text(encoding="utf-8"))
        committed_metrics = json.loads((ROOT / "api" / "v1" / "multiomics" / "metrics.json").read_text(encoding="utf-8"))
        crosswalk_path = ROOT / "api" / "v1" / "multiomics" / "drugsfda-oncology-crosswalk.json"
        committed_crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8")) if crosswalk_path.exists() else None
        self.assertEqual(committed_index, expected_index)
        self.assertEqual(committed_metrics, expected_metrics)
        self.assertEqual(committed_crosswalk, expected_crosswalk)


if __name__ == "__main__":
    unittest.main()
