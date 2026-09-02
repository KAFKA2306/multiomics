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

    def test_committed_api_is_deterministic(self):
        data = json.loads((ROOT / "data" / "multiomics-v1.json").read_text(encoding="utf-8"))
        expected_index, expected_metrics = build_api.build(data)
        committed_index = json.loads((ROOT / "api" / "v1" / "multiomics" / "index.json").read_text(encoding="utf-8"))
        committed_metrics = json.loads((ROOT / "api" / "v1" / "multiomics" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(committed_index, expected_index)
        self.assertEqual(committed_metrics, expected_metrics)


if __name__ == "__main__":
    unittest.main()
