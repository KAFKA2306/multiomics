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


if __name__ == "__main__":
    unittest.main()
