import math
import unittest

from scripts.analyze_sequencing_costs import analyze, log_linear_fit


class SequencingCostAnalysisTest(unittest.TestCase):
    def test_log_linear_fit_recovers_known_annual_halving(self):
        records = [
            {"period": "2020-01", "value": 100.0},
            {"period": "2021-01", "value": 50.0},
            {"period": "2022-01", "value": 25.0},
        ]
        result = log_linear_fit(records)
        self.assertAlmostEqual(result["log_slope_per_year"], math.log(0.5), places=12)
        self.assertAlmostEqual(result["annual_cost_reduction_percent"], 50.0, places=12)
        self.assertAlmostEqual(result["years_to_half_cost"], 1.0, places=12)
        self.assertAlmostEqual(result["years_to_one_tenth_cost"], math.log(0.1) / math.log(0.5), places=12)
        self.assertAlmostEqual(result["r_squared"], 1.0, places=12)

    def test_log_linear_fit_does_not_claim_reduction_interval_when_cost_rises(self):
        records = [
            {"period": "2020-01", "value": 100.0},
            {"period": "2021-01", "value": 110.0},
        ]
        result = log_linear_fit(records)
        self.assertIsNone(result["years_to_half_cost"])
        self.assertIsNone(result["years_to_one_tenth_cost"])

    def test_analysis_uses_official_2008_transition_without_mixing_metrics(self):
        canonical = {
            "retrieved_at": "2026-09-02T19:50:03Z",
            "sequencing_costs": [],
        }
        for metric, unit, scale in (
            ("cost_per_megabase", "USD_per_megabase", 1.0),
            ("cost_per_genome", "USD_per_human_genome", 1000.0),
        ):
            for period, value in (
                ("2007-01", 100.0 * scale),
                ("2007-10", 80.0 * scale),
                ("2008-01", 40.0 * scale),
                ("2009-01", 20.0 * scale),
            ):
                canonical["sequencing_costs"].append(
                    {
                        "period": period,
                        "metric": metric,
                        "value": value,
                        "unit": unit,
                        "source_sha256": "a" * 64,
                    }
                )

        result = analyze(canonical)
        self.assertEqual(result["technology_transition_period"], "2008-01")
        self.assertEqual(len(result["results"]), 2)
        for metric_result in result["results"]:
            self.assertEqual(
                metric_result["log_linear_fit_sanger_through_2007_10"]["last_period"],
                "2007-10",
            )
            self.assertEqual(
                metric_result["log_linear_fit_second_generation_from_2008_01"]["first_period"],
                "2008-01",
            )
            self.assertEqual(metric_result["source_sha256"], ["a" * 64])


if __name__ == "__main__":
    unittest.main()
