import argparse
import json
import math
from pathlib import Path


NHGRI_METHOD_URL = "https://www.genome.gov/about-genomics/fact-sheets/DNA-Sequencing-Costs-Data"
TRANSITION_PERIOD = "2008-01"


def month_index(period: str) -> int:
    year_text, month_text = period.split("-", 1)
    year = int(year_text)
    month = int(month_text)
    if month < 1 or month > 12:
        raise ValueError(f"invalid period: {period}")
    return year * 12 + month - 1


def log_linear_fit(records: list[dict]) -> dict:
    if len(records) < 2:
        raise ValueError("at least two observations are required")

    ordered = sorted(records, key=lambda row: row["period"])
    origin = month_index(ordered[0]["period"])
    x = [(month_index(row["period"]) - origin) / 12.0 for row in ordered]
    y = [math.log(float(row["value"])) for row in ordered]
    if any(float(row["value"]) <= 0 for row in ordered):
        raise ValueError("sequencing cost must be positive")

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
    r_squared = 1.0 - ss_residual / ss_total if ss_total else 1.0

    annual_factor = math.exp(slope)
    return {
        "observation_count": len(ordered),
        "first_period": ordered[0]["period"],
        "last_period": ordered[-1]["period"],
        "log_slope_per_year": slope,
        "annual_cost_change_percent": (annual_factor - 1.0) * 100.0,
        "annual_cost_reduction_percent": (1.0 - annual_factor) * 100.0,
        "r_squared": r_squared,
    }


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

        pre_transition = [row for row in metric_records if row["period"] < TRANSITION_PERIOD]
        post_transition = [row for row in metric_records if row["period"] >= TRANSITION_PERIOD]
        if len(pre_transition) < 2 or len(post_transition) < 2:
            raise ValueError(f"insufficient observations around {TRANSITION_PERIOD}: {metric}")

        source_hashes = sorted({row.get("source_sha256") for row in metric_records})
        if None in source_hashes or "" in source_hashes:
            raise ValueError(f"missing source_sha256 for metric: {metric}")

        results.append(
            {
                "metric": metric,
                "unit": metric_records[0].get("unit"),
                "source_sha256": source_hashes,
                "endpoint_summary": endpoint_summary(metric_records),
                "log_linear_fit_all": log_linear_fit(metric_records),
                "log_linear_fit_sanger_through_2007_10": log_linear_fit(pre_transition),
                "log_linear_fit_second_generation_from_2008_01": log_linear_fit(post_transition),
            }
        )

    return {
        "analysis": "NHGRI DNA sequencing cost decline",
        "method": "Ordinary least squares of natural-log cost against elapsed years, plus endpoint annualized decline. Descriptive only; no causal estimate.",
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
