import json
import unittest
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multiomics-v1.json"
SCHEMA = ROOT / "schema" / "multiomics-v1.schema.json"


class MultiomicsDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_versioned_data_shape(self):
        self.assertEqual(self.data["schema_version"], "1.0.0")
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], "1.0.0")
        self.assertGreaterEqual(len(self.data["sequencing_costs"]), 2)
        self.assertGreaterEqual(len(self.data["clinical_trials"]), 1)
        self.assertGreaterEqual(len(self.data["approvals"]), 1)
        self.assertGreaterEqual(len(self.data["sources"]), 3)

    def test_nhgri_sequencing_cost_observations(self):
        costs = self.data["sequencing_costs"]
        by_key = {(row["period"], row["metric"]): row for row in costs}
        self.assertEqual(len(by_key), len(costs))

        mb = by_key[("2021-08", "cost_per_megabase")]
        genome = by_key[("2021-08", "cost_per_genome")]
        self.assertGreater(mb["value"], 0)
        self.assertEqual(mb["unit"], "USD_per_megabase")
        self.assertGreater(genome["value"], 0)
        self.assertEqual(genome["unit"], "USD_per_human_genome")
        self.assertTrue(all(urlparse(row["source_url"]).hostname == "www.genome.gov" for row in costs))

        metric_counts = Counter(row["metric"] for row in costs)
        self.assertEqual(metric_counts["cost_per_megabase"], metric_counts["cost_per_genome"])
        periods = sorted({row["period"] for row in costs})
        self.assertEqual(len(costs), 2 * len(periods))
        self.assertTrue(all(len(period) == 7 for period in periods))

    def test_clinical_trial_observation_contract(self):
        trial = next(row for row in self.data["clinical_trials"] if row["nct_id"] == "NCT06264180")
        self.assertTrue(trial["status"])
        self.assertTrue(trial["phase"])
        self.assertTrue(trial["sponsor"])
        self.assertTrue(trial["title"])
        self.assertGreaterEqual(len(trial["interventions"]), 1)
        self.assertEqual(urlparse(trial["source_url"]).hostname, "clinicaltrials.gov")

        last_update = date.fromisoformat(trial["last_update_posted"])
        retrieved = datetime.fromisoformat(trial["retrieved_at"].replace("Z", "+00:00")).date()
        self.assertLessEqual(last_update, retrieved)

    def test_first_fda_approval_observation(self):
        approval = self.data["approvals"][0]
        self.assertEqual(approval["approval_date"], "2026-08-06")
        self.assertEqual(approval["generic_name"], "vusolimogene oderparepvec-wtpg")
        self.assertEqual(approval["brand_name"], "Tudriqev")
        self.assertEqual(approval["sponsor"], "Replimune, Inc.")
        self.assertEqual(approval["pathway"], "accelerated approval")
        self.assertEqual(approval["modality"], "genetically modified oncolytic viral therapy")
        self.assertEqual(approval["combination_with"], ["nivolumab"])
        self.assertEqual(approval["evidence_basis"], ["objective response rate", "duration of response"])
        self.assertTrue(approval["confirmatory_trial_required"])
        self.assertEqual(urlparse(approval["source_url"]).hostname, "www.fda.gov")

    def test_source_registry_uses_primary_sources(self):
        hosts = {urlparse(source["url"]).hostname for source in self.data["sources"]}
        self.assertEqual(hosts, {"www.genome.gov", "clinicaltrials.gov", "www.fda.gov"})


if __name__ == "__main__":
    unittest.main()
