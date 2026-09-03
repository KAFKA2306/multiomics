from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PagesContractTests(unittest.TestCase):
    def test_dashboard_reads_canonical_data_without_fallback(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("./data/multiomics-v1.json", html)
        self.assertIn("./api/v1/multiomics/sequencing-cost-analysis.json", html)
        self.assertIn("./api/v1/multiomics/fda-product-coverage-evidence.json", html)
        self.assertIn("正準データまたは派生分析を取得できませんでした", html)
        self.assertNotIn("562 USD", html)
        self.assertNotIn("Tudriqev — accelerated approval", html)
        self.assertNotIn("181583", html)
        self.assertNotIn("44.3%", html)
        self.assertNotIn("1,424製品", html)
        self.assertNotIn("791 製品", html)

    def test_dashboard_selects_latest_sequencing_period(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("b.period.localeCompare(a.period)", html)
        self.assertIn("x.period===latestPeriod", html)

    def test_dashboard_labels_sequencing_trend_as_descriptive(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("記述統計であり因果効果ではありません", html)
        self.assertIn("analysis.method_source_url", html)

    def test_dashboard_labels_fda_source_scope(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("FDA Oncology approval notificationsの最新保存イベント", html)
        self.assertIn("FDA全承認の完全一覧ではありません", html)
        self.assertIn("対象: FDA Oncology approval notifications掲載イベント", html)

    def test_dashboard_keeps_fda_coverage_verified_and_unverified_separate(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Drugs@FDAとOrange Bookのcoverage差", html)
        self.assertIn("coverage.fda_documented_absence?.tentative_approval_products", html)
        self.assertIn("coverage.remaining_unverified_products", html)
        self.assertIn("推測で分類しません", html)
        self.assertIn("coverage.fda_documented_absence.source_url", html)

    def test_readme_starts_with_canonical_production_url(self):
        first_line = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "https://kafka2306.github.io/multiomics/")


if __name__ == "__main__":
    unittest.main()
