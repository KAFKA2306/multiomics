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
        tables = {
            "ActionTypes_Lookup.txt": [
                refresh_drugsfda.EXPECTED_HEADERS["ActionTypes_Lookup.txt"],
                ["1", "Original", "", ""],
            ],
            "Applications.txt": [
                refresh_drugsfda.EXPECTED_HEADERS["Applications.txt"],
                ["000001", "NDA", "", "Sponsor"],
            ],
            "Join_Submission_ActionType_Lookup.txt": [
                refresh_drugsfda.EXPECTED_HEADERS["Join_Submission_ActionType_Lookup.txt"],
                ["1", "1", "ORIG", "000001", "1"],
            ],
            "Products.txt": [
                refresh_drugsfda.EXPECTED_HEADERS["Products.txt"],
                ["000001", "001", "TABLET", "1 MG", "1", "DRUG", "INGREDIENT", "1"],
            ],
            "Submissions.txt": [
                refresh_drugsfda.EXPECTED_HEADERS["Submissions.txt"],
                ["000001", "", "ORIG", "1", "AP", "2026-01-01", "", "Priority"],
            ],
        }
        for index in range(7):
            tables[f"Other{index}.txt"] = [["id"], [str(index)]]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, rows in tables.items():
                text = "\n".join("\t".join(row) for row in rows) + "\n"
                archive.writestr(name, text.encode("utf-8"))
        return buffer.getvalue()

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

    def test_rejects_archive_with_wrong_table_count(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Applications.txt", "ApplNo\n")
        with self.assertRaisesRegex(ValueError, "expected 12"):
            refresh_drugsfda.inspect_zip(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
