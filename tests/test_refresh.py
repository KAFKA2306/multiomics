import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.refresh_clinical_trials import build_change_evidence, extract_trial, refresh


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
                "designModule": {
                    "phases": ["PHASE3"],
                    "enrollmentInfo": {"count": 400, "type": "ESTIMATED"},
                },
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
        self.assertEqual(record["enrollment_count"], 400)
        self.assertEqual(record["enrollment_type"], "ESTIMATED")
        self.assertEqual(record["last_update_posted"], "2026-05-15")
        self.assertEqual(record["source_sha256"], "a" * 64)

    def test_missing_enrollment_fails(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT06264180", "briefTitle": "IGNYTE-3"},
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "lastUpdatePostDateStruct": {"date": "2026-05-15"},
                },
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Replimune, Inc."}},
                "designModule": {"phases": ["PHASE3"]},
                "armsInterventionsModule": {"interventions": [{"name": "Nivolumab"}]},
            }
        }
        with self.assertRaisesRegex(ValueError, "missing enrollment data"):
            extract_trial(
                study,
                retrieved_at="2026-08-20T04:50:00Z",
                source_sha256="a" * 64,
                raw_path="data/raw/clinicaltrials/NCT06264180/a.json",
                api_data_timestamp="2026-08-20T14:00:00Z",
            )

    def test_change_evidence_ignores_retrieval_metadata_only_changes(self):
        previous = {
            "nct_id": "NCT06264180",
            "status": "RECRUITING",
            "phase": "PHASE3",
            "sponsor": "Replimune, Inc.",
            "interventions": ["Nivolumab"],
            "enrollment_count": 400,
            "enrollment_type": "ESTIMATED",
            "last_update_posted": "2026-07-15",
            "source_url": "https://clinicaltrials.gov/study/NCT06264180",
            "retrieved_at": "2026-09-02T13:39:11Z",
            "source_sha256": "a" * 64,
            "api_data_timestamp": "2026-09-02T09:00:04",
        }
        current = dict(previous)
        current.update(
            retrieved_at="2026-09-03T15:42:39Z",
            source_sha256="b" * 64,
            api_data_timestamp="2026-09-03T09:00:05",
        )
        evidence = build_change_evidence(previous, current)
        self.assertEqual(evidence["changed_fields"], [])
        self.assertEqual(evidence["previous_source_sha256"], "a" * 64)
        self.assertEqual(evidence["current_source_sha256"], "b" * 64)

    def test_change_evidence_reports_monitored_field_changes(self):
        previous = {
            "nct_id": "NCT06264180",
            "status": "RECRUITING",
            "phase": "PHASE3",
            "sponsor": "Replimune, Inc.",
            "interventions": ["Nivolumab"],
            "enrollment_count": 400,
            "enrollment_type": "ESTIMATED",
            "last_update_posted": "2026-07-15",
            "source_url": "https://clinicaltrials.gov/study/NCT06264180",
            "retrieved_at": "2026-09-02T13:39:11Z",
            "source_sha256": "a" * 64,
            "api_data_timestamp": "2026-09-02T09:00:04",
        }
        current = dict(previous)
        current.update(status="ACTIVE_NOT_RECRUITING", enrollment_count=420, source_sha256="b" * 64)
        evidence = build_change_evidence(previous, current)
        self.assertEqual(evidence["changed_fields"], ["status", "enrollment_count"])

    def test_unchanged_source_does_not_rewrite_canonical_data(self):
        raw = b'{"protocolSection": {}}'
        digest = hashlib.sha256(raw).hexdigest()
        existing = {
            "nct_id": "NCT06264180",
            "source_sha256": digest,
            "retrieved_at": "2026-09-02T13:39:11Z",
            "api_data_timestamp": "2026-09-02T09:00:04",
        }
        canonical = {
            "schema_version": "1.0.0",
            "retrieved_at": "2026-09-02T13:39:11Z",
            "clinical_trials": [existing],
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "multiomics-v1.json"
            raw_dir = root / "raw"
            original = json.dumps(canonical, indent=2) + "\n"
            data_path.write_text(original, encoding="utf-8")

            with patch(
                "scripts.refresh_clinical_trials.fetch_json",
                side_effect=[({"dataTimestamp": "2026-09-03T09:00:00"}, b"{}"), ({"protocolSection": {}}, raw)],
            ):
                result = refresh("NCT06264180", data_path, raw_dir)

            self.assertEqual(result, existing)
            self.assertEqual(data_path.read_text(encoding="utf-8"), original)
            self.assertEqual((raw_dir / "NCT06264180" / f"{digest}.json").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
