import math
import unittest

from scripts.analyze_sequencing_costs import (
    analyze,
    change_point_analysis,
    change_point_sensitivity,
    continuous_segmented_regression,
    log_linear_fit,
)


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

    def _slowdown_records(self):
        records = []
        value = 1000.0
        for offset, year in enumerate(range(2000, 2024)):
            if offset:
                value *= 0.52 if year < 2011 else 0.91
            value *= 1.0 + 0.006 * math.sin(offset)
            records.append({"period": f"{year}-01", "value": value})
        return records

    def test_change_point_analysis_finds_sustained_slowdown(self):
        result = change_point_analysis(self._slowdown_records())
        self.assertGreater(result["bic_improvement_vs_single_line"], 0.0)
        self.assertGreater(
            result["before"]["annual_cost_reduction_percent"],
            result["after"]["annual_cost_reduction_percent"],
        )

    def test_change_point_sensitivity_keeps_slowdown_under_segment_constraints(self):
        result = change_point_sensitivity(self._slowdown_records())
        self.assertEqual(result["minimum_observations_tested"], [6, 8, 10, 12])
        self.assertTrue(result["all_bic_improvements_positive"])
        self.assertLessEqual(result["earliest_change_period"], result["latest_change_period"])
        for row in result["results"]:
            self.assertGreater(
                row["before_annual_cost_reduction_percent"],
                row["after_annual_cost_reduction_percent"],
            )

    def test_continuous_segmented_regression_finds_sustained_slowdown(self):
        result = continuous_segmented_regression(self._slowdown_records())
        self.assertGreater(result["bic_improvement_vs_single_line"], 0.0)
        self.assertGreater(
            result["before"]["annual_cost_reduction_percent"],
            result["after"]["annual_cost_reduction_percent"],
        )

    def test_analysis_uses_official_2008_transition_without_mixing_metrics(self):
        canonical = {
            "retrieved_at": "2026-09-02T19:50:03Z",
            "sequencing_costs": [],
        }
        for metric, unit, scale in (
            ("cost_per_megabase", "USD_per_megabase", 1.0),
            ("cost_per_genome", "USD_per_human_genome", 1000.0),
        ):
            for year in range(2000, 2008):
                canonical["sequencing_costs"].append(
                    {
                        "period": f"{year}-10",
                        "metric": metric,
                        "value": 100.0 * scale * (0.8 ** (year - 2000)),
                        "unit": unit,
                        "source_sha256": "a" * 64,
                    }
                )
            value = 40.0 * scale
            for offset, year in enumerate(range(2008, 2032)):
                if offset:
                    value *= 0.6 if year < 2018 else 0.9
                value *= 1.0 + 0.005 * math.sin(offset)
                canonical["sequencing_costs"].append(
                    {
                        "period": f"{year}-01",
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
            self.assertGreater(
                metric_result["change_point_analysis_second_generation"]["bic_improvement_vs_single_line"],
                0.0,
            )
            self.assertTrue(
                metric_result["change_point_sensitivity_second_generation"]["all_bic_improvements_positive"]
            )
            self.assertGreater(
                metric_result["continuous_segmented_regression_second_generation"][
                    "bic_improvement_vs_single_line"
                ],
                0.0,
            )


if __name__ == "__main__":
    unittest.main()
