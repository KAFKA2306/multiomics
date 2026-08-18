import json
import unittest
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
        self.assertIsInstance(self.data["sequencing_costs"], list)
        self.assertIsInstance(self.data["clinical_trials"], list)
        self.assertIsInstance(self.data["approvals"], list)
        self.assertGreaterEqual(len(self.data["sources"]), 3)

    def test_first_fda_approval_observation(self):
        self.assertEqual(len(self.data["approvals"]), 1)
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

    def test_unmaterialized_classes_are_empty(self):
        self.assertEqual(self.data["sequencing_costs"], [])
        self.assertEqual(self.data["clinical_trials"], [])

    def test_source_registry_uses_primary_sources(self):
        hosts = {urlparse(source["url"]).hostname for source in self.data["sources"]}
        self.assertEqual(hosts, {"www.genome.gov", "clinicaltrials.gov", "www.fda.gov"})


if __name__ == "__main__":
    unittest.main()
