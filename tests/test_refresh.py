import unittest

from scripts.refresh_clinical_trials import extract_trial


class ClinicalTrialsRefreshTest(unittest.TestCase):
    def test_extracts_required_trial_fields(self):
        study = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT06264180",
                    "briefTitle": "IGNYTE-3",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "lastUpdatePostDateStruct": {"date": "2026-05-15"},
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Replimune, Inc."},
                },
                "designModule": {"phases": ["PHASE3"]},
                "armsInterventionsModule": {
                    "interventions": [
                        {"name": "Vusolimogene Oderparepvec"},
                        {"name": "Nivolumab"},
                    ]
                },
            }
        }
        record = extract_trial(
            study,
            retrieved_at="2026-08-20T04:50:00Z",
            source_sha256="a" * 64,
            raw_path="data/raw/clinicaltrials/NCT06264180/a.json",
            api_data_timestamp="2026-08-20T14:00:00Z",
        )
        self.assertEqual(record["nct_id"], "NCT06264180")
        self.assertEqual(record["status"], "RECRUITING")
        self.assertEqual(record["phase"], "PHASE3")
        self.assertEqual(record["sponsor"], "Replimune, Inc.")
        self.assertEqual(record["interventions"], ["Vusolimogene Oderparepvec", "Nivolumab"])
        self.assertEqual(record["last_update_posted"], "2026-05-15")
        self.assertEqual(record["source_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
