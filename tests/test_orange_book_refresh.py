import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import refresh_orange_book


class OrangeBookRefreshTest(unittest.TestCase):
    def _archive(self) -> bytes:
        buffer = io.BytesIO()
        tables = {
            "products.txt": ["Ingredient", "DF;Route", "Trade_Name", "Applicant", "Strength", "Appl_Type", "Appl_No", "Product_No", "TE_Code", "Approval_Date", "RLD", "RS", "Type", "Applicant_Full_Name"],
            "patent.txt": ["Appl_Type", "Appl_No", "Product_No", "Patent_No"],
            "exclusivity.txt": ["Appl_Type", "Appl_No", "Product_No", "Exclusivity_Code", "Exclusivity_Date"],
        }
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, (name, header) in enumerate(tables.items(), start=1):
                row = [str(index)] * len(header)
                archive.writestr(name, "~".join(header) + "\n" + "~".join(row) + "\n")
        return buffer.getvalue()

    def test_inspect_zip_keeps_headers_and_counts(self):
        tables = refresh_orange_book.inspect_zip(self._archive())
        self.assertEqual(len(tables), 3)
        products = next(row for row in tables if row["file_name"].lower() == "products.txt")
        self.assertIn("Approval_Date", products["header"])
        self.assertEqual(products["row_count"], 1)

    def test_refresh_is_content_addressed_and_does_not_rewrite_same_revision(self):
        payload = self._archive()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            manifest = root / "manifest.json"
            with patch.object(refresh_orange_book, "fetch_zip", return_value=payload):
                first = refresh_orange_book.refresh(raw_dir, manifest)
                second = refresh_orange_book.refresh(raw_dir, manifest)
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            saved = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(saved["table_count"], 3)
            self.assertTrue((raw_dir / f"{saved['source_sha256']}.zip").exists())

    def test_rejects_archive_when_table_set_changes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("products.txt", "A~B\n")
            archive.writestr("patent.txt", "A~B\n")
        with self.assertRaisesRegex(ValueError, "table set changed"):
            refresh_orange_book.inspect_zip(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
