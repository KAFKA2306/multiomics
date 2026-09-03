import argparse
import json
import math
from pathlib import Path


NHGRI_METHOD_URL = "https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data"
TRANSITION_PERIOD = "2008-01"
MIN_CHANGE_POINT_SEGMENT_OBSERVATIONS = 8


def month_index(period: str) -> int:
    year_text, month_text = period.split("-", 1)
    year = int(year_text)
    month = int(month_text)
    if month < 1 or month > 12:
        raise ValueError(f"invalid period: {period}")
    return year * 12 + month - 1


def _linear_components(records: list[dict]) -> dict:
    if len(records) < 2:
        raise ValueError("at least two observations are required")

    ordered = sorted(records, key=lambda row: row["period"])
    values = [float(row["value"]) for row in ordered]
    if any(value <= 0 for value in values):
        raise ValueError("sequencing cost must be positive")

    origin = month_index(ordered[0]["period"])
    x = [(month_index(row["period"]) - origin) / 12.0 for row in ordered]
    y = [math.log(value) for value in values]
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    ss_x = sum((value - x_mean) ** 2 for value in x)
    if ss_x == 0:
        raise ValueError("observations must span more than one period")

    slope = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y)) / ss_x
    intercept = y_mean - slope * x_mean
    predictions = [intercept + slope * xi for xi in x]
    ss_total = sum((yi - y_mean) ** 2 for yi in y)
    ss_residual = sum((yi - predicted) ** 2 for yi, predicted in zip(y, predictions))
    return {
        "ordered": ordered,
        "slope": slope,
        "intercept": intercept,
        "ss_total": ss_total,
        "ss_residual": ss_residual,
    }


def log_linear_fit(records: list[dict]) -> dict:
    components = _linear_components(records)
    ordered = components["ordered"]
    slope = components["slope"]
    ss_total = components["ss_total"]
    ss_residual = components["ss_residual"]
    r_squared = 1.0 - ss_residual / ss_total if ss_total else 1.0

    annual_factor = math.exp(slope)
    result = {
        "observation_count": len(ordered),
        "first_period": ordered[0]["period"],
        "last_period": ordered[-1]["period"],
        "log_slope_per_year": slope,
        "annual_cost_change_percent": (annual_factor - 1.0) * 100.0,
        "annual_cost_reduction_percent": (1.0 - annual_factor) * 100.0,
        "r_squared": r_squared,
    }
    if slope < 0:
        result["years_to_half_cost"] = math.log(0.5) / slope
        result["years_to_one_tenth_cost"] = math.log(0.1) / slope
    else:
        result["years_to_half_cost"] = None
        result["years_to_one_tenth_cost"] = None
    return result


def endpoint_summary(records: list[dict]) -> dict:
    if len(records) < 2:
        raise ValueError("at least two observations are required")
    ordered = sorted(records, key=lambda row: row["period"])
    first = ordered[0]
    last = ordered[-1]
    first_value = float(first["value"])
    last_value = float(last["value"])
    if first_value <= 0 or last_value <= 0:
        raise ValueError("sequencing cost must be positive")
    elapsed_years = (month_index(last["period"]) - month_index(first["period"])) / 12.0
    if elapsed_years <= 0:
        raise ValueError("observations must span more than one period")
    annual_factor = (last_value / first_value) ** (1.0 / elapsed_years)
    return {
        "first_period": first["period"],
        "first_value": first_value,
        "last_period": last["period"],
        "last_value": last_value,
        "elapsed_years": elapsed_years,
        "fold_reduction": first_value / last_value,
        "total_cost_reduction_percent": (1.0 - last_value / first_value) * 100.0,
        "annualized_cost_reduction_percent": (1.0 - annual_factor) * 100.0,
    }


def change_point_analysis(records: list[dict]) -> dict:
    ordered = sorted(records, key=lambda row: row["period"])
    minimum = MIN_CHANGE_POINT_SEGMENT_OBSERVATIONS
    if len(ordered) < minimum * 2:
        raise ValueError("insufficient observations for change-point analysis")

    single = _linear_components(ordered)
    n = len(ordered)
    single_rss = single["ss_residual"]
    if single_rss <= 0:
        raise ValueError("single-line residual sum of squares must be positive")

    best = None
    for split_index in range(minimum, n - minimum + 1):
        before = ordered[:split_index]
        after = ordered[split_index:]
        before_components = _linear_components(before)
        after_components = _linear_components(after)
        rss = before_components["ss_residual"] + after_components["ss_residual"]
        candidate = {
            "change_period": after[0]["period"],
            "residual_sum_of_squares": rss,
            "before": log_linear_fit(before),
            "after": log_linear_fit(after),
        }
        if best is None or rss < best["residual_sum_of_squares"]:
            best = candidate

    if best is None or best["residual_sum_of_squares"] <= 0:
        raise ValueError("unable to fit change-point model")

    # BIC for Gaussian residuals. The two-line model counts two intercepts,
    # two slopes and the selected change point (5 parameters); the single
    # line counts one intercept and one slope (2 parameters).
    single_bic = n * math.log(single_rss / n) + 2 * math.log(n)
    change_bic = n * math.log(best["residual_sum_of_squares"] / n) + 5 * math.log(n)
    best["single_line_residual_sum_of_squares"] = single_rss
    best["single_line_bic"] = single_bic
    best["change_point_bic"] = change_bic
    best["bic_improvement_vs_single_line"] = single_bic - change_bic
    best["minimum_observations_per_segment"] = minimum
    return best


def analyze(canonical: dict) -> dict:
    records = canonical.get("sequencing_costs")
    if not isinstance(records, list) or not records:
        raise ValueError("sequencing_costs must contain canonical observations")

    results = []
    for metric in ("cost_per_megabase", "cost_per_genome"):
        metric_records = [row for row in records if row.get("metric") == metric]
        if not metric_records:
            raise ValueError(f"missing metric: {metric}")
        if any("period" not in row or "value" not in row for row in metric_records):
            raise ValueError(f"missing period/value for metric: {metric}")

        periods = [row["period"] for row in metric_records]
        if len(periods) != len(set(periods)):
            raise ValueError(f"duplicate period for metric: {metric}")

        units = {row.get("unit") for row in metric_records}
        if len(units) != 1 or None in units or "" in units:
            raise ValueError(f"inconsistent or missing unit for metric: {metric}")

        source_hash_values = [row.get("source_sha256") for row in metric_records]
        if any(not isinstance(value, str) or not value for value in source_hash_values):
            raise ValueError(f"missing source_sha256 for metric: {metric}")
        source_hashes = sorted(set(source_hash_values))

        pre_transition = [row for row in metric_records if row["period"] < TRANSITION_PERIOD]
        post_transition = [row for row in metric_records if row["period"] >= TRANSITION_PERIOD]
        if len(pre_transition) < 2 or len(post_transition) < 2:
            raise ValueError(f"insufficient observations around {TRANSITION_PERIOD}: {metric}")

        results.append(
            {
                "metric": metric,
                "unit": next(iter(units)),
                "source_sha256": source_hashes,
                "endpoint_summary": endpoint_summary(metric_records),
                "log_linear_fit_all": log_linear_fit(metric_records),
                "log_linear_fit_sanger_through_2007_10": log_linear_fit(pre_transition),
                "log_linear_fit_second_generation_from_2008_01": log_linear_fit(post_transition),
                "change_point_analysis_second_generation": change_point_analysis(post_transition),
            }
        )

    return {
        "analysis": "NHGRI DNA sequencing cost decline",
        "method": "Ordinary least squares of natural-log cost against elapsed years, endpoint annualized decline, and an exhaustive single change-point search within second-generation observations. Descriptive only; no causal estimate or forecast.",
        "technology_transition_period": TRANSITION_PERIOD,
        "technology_transition_basis": "NHGRI states that 2001 through October 2007 represent Sanger-based sequencing and observations beginning January 2008 represent second-generation sequencing.",
        "method_source_url": NHGRI_METHOD_URL,
        "canonical_retrieved_at": canonical.get("retrieved_at"),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/multiomics-v1.json")
    parser.add_argument("--output", default="api/v1/multiomics/sequencing-cost-analysis.json")
    args = parser.parse_args()

    canonical = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = analyze(canonical)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
