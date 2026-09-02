from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PagesContractTests(unittest.TestCase):
    def test_dashboard_reads_canonical_data_without_fallback(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("./data/multiomics-v1.json", html)
        self.assertIn("./api/v1/multiomics/sequencing-cost-analysis.json", html)
        self.assertIn("正準データまたは派生分析を取得できませんでした", html)
        self.assertNotIn("562 USD", html)
        self.assertNotIn("Tudriqev — accelerated approval", html)
        self.assertNotIn("181583", html)
        self.assertNotIn("44.3%", html)

    def test_dashboard_selects_latest_sequencing_period(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("b.period.localeCompare(a.period)", html)
        self.assertIn("x.period===latestPeriod", html)

    def test_dashboard_labels_sequencing_trend_as_descriptive(self):
        html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn("記述統計であり因果効果ではありません", html)
        self.assertIn("analysis.method_source_url", html)

    def test_readme_starts_with_canonical_production_url(self):
        first_line = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "https://kafka2306.github.io/multiomics/")


if __name__ == "__main__":
    unittest.main()
