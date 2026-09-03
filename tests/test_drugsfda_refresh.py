import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import refresh_drugsfda


class DrugsFdaRefreshTest(unittest.TestCase):
    def _archive(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, (name, header) in enumerate(refresh_drugsfda.EXPECTED_HEADERS.items(), start=1):
                row = [str(index)] * len(header)
                text = "\t".join(header) + "\n" + "\t".join(row) + "\n"
                archive.writestr(name, text.encode("utf-8"))
        return buffer.getvalue()

    def _rows(self, archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
        text = refresh_drugsfda._decode_table(archive.read(name))
        return list(csv.DictReader(io.StringIO(text), delimiter="\t"))

    def test_inspect_zip_keeps_real_headers_and_counts(self):
        tables = refresh_drugsfda.inspect_zip(self._archive())
        self.assertEqual(len(tables), 12)
        applications = next(row for row in tables if row["file_name"] == "Applications.txt")
        self.assertEqual(applications["header"], refresh_drugsfda.EXPECTED_HEADERS["Applications.txt"])
        self.assertEqual(applications["row_count"], 1)

    def test_refresh_is_content_addressed_and_does_not_rewrite_same_revision(self):
        payload = self._archive()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            manifest = root / "manifest.json"
            with patch.object(refresh_drugsfda, "fetch_zip", return_value=payload):
                first = refresh_drugsfda.refresh(raw_dir, manifest)
                second = refresh_drugsfda.refresh(raw_dir, manifest)
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(saved["table_count"], 12)
            self.assertTrue((raw_dir / f"{saved['source_sha256']}.zip").exists())

    def test_rejects_archive_when_table_name_changes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, header in refresh_drugsfda.EXPECTED_HEADERS.items():
                if name == "TE.txt":
                    name = "Unexpected.txt"
                archive.writestr(name, "\t".join(header) + "\n")
        with self.assertRaisesRegex(ValueError, "table set changed"):
            refresh_drugsfda.inspect_zip(buffer.getvalue())

    def test_rejects_archive_when_header_changes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, header in refresh_drugsfda.EXPECTED_HEADERS.items():
                if name == "MarketingStatus.txt":
                    header = list(reversed(header))
                archive.writestr(name, "\t".join(header) + "\n")
        with self.assertRaisesRegex(ValueError, "header mismatch for MarketingStatus.txt"):
            refresh_drugsfda.inspect_zip(buffer.getvalue())

    def test_canonical_archive_target_records_are_inspectable(self):
        manifest = json.loads(refresh_drugsfda.MANIFEST.read_text(encoding="utf-8"))
        raw_path = refresh_drugsfda.ROOT / manifest["raw_path"]
        self.assertTrue(raw_path.exists())
        targets = {"ZENBEXUS", "ZIIHERA", "RASONQUE"}
        with zipfile.ZipFile(raw_path) as archive:
            products = self._rows(archive, "Products.txt")
            applications = self._rows(archive, "Applications.txt")
            submissions = self._rows(archive, "Submissions.txt")
            joins = self._rows(archive, "Join_Submission_ActionTypes_Lookup.txt")
            action_types = self._rows(archive, "ActionTypes_Lookup.txt")
        app_by_no = {row["ApplNo"]: row for row in applications}
        action_by_id = {row["ActionTypes_LookupID"]: row for row in action_types}
        matched_products = [row for row in products if row["DrugName"].strip().upper() in targets]
        target_apps = sorted({row["ApplNo"] for row in matched_products})
        result = []
        for app_no in target_apps:
            app_submissions = [row for row in submissions if row["ApplNo"] == app_no]
            app_joins = [row for row in joins if row["ApplNo"] == app_no]
            join_details = []
            for row in app_joins:
                detail = dict(row)
                action = action_by_id.get(row["ActionTypes_LookupID"])
                detail["ActionTypes_LookupDescription"] = action["ActionTypes_LookupDescription"] if action else None
                join_details.append(detail)
            result.append({
                "application": app_by_no.get(app_no),
                "products": [row for row in matched_products if row["ApplNo"] == app_no],
                "submissions": app_submissions,
                "actions": join_details,
            })
        print("DRUGSFDA_TARGET_RECORDS=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
        self.assertIn("761416", target_apps)


if __name__ == "__main__":
    unittest.main()
