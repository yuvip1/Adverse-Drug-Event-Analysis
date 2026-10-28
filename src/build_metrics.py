"""Build the Stage 5 metrics file and results report from pipeline outputs.

Usage:
    .venv\\Scripts\\python src\\build_metrics.py

The analytical modules write focused JSON files. This module is the single
reporting step that combines those files without querying or modifying SQL
Server.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
METRICS_PATH = RESULTS_DIR / "metrics.json"
REPORT_PATH = ROOT / "docs" / "RESULTS.md"


def _read_json(name: str) -> Any:
    path = RESULTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Required pipeline output is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _top_rows(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return rows[:limit]


def _summary_metrics(
    stats: dict[str, Any],
    quality: dict[str, Any],
    pareto: dict[str, Any],
    cycle_time: dict[str, Any],
    trend: dict[str, Any],
    forecast: dict[str, Any],
    signals: dict[str, Any],
    ml_metrics: dict[str, Any],
) -> dict[str, Any]:
    serious = {str(row["is_serious"]).lower(): row["cnt"] for row in stats["serious_breakdown"]}
    total_reports = quality["final_report_count"]
    serious_reports = serious.get("true", 0)

    return {
        "dataset": {
            "reports_processed": total_reports,
            "source_total_reports": 370540,
            "scope": "One sample file: drug-event-0001-of-0031.json.zip",
            "scope_note": "The processed file contains 12,000 reports from the 370,540-report source set.",
        },
        "model": {
            "fact_drug_rows": quality["stg_drugs"],
            "fact_reaction_rows": quality["stg_reactions"],
            "dimensions": [
                "dim_date",
                "dim_country",
                "dim_age_group",
                "dim_drug",
                "dim_reaction",
                "dim_reporter",
            ],
            "facts": ["fact_report", "fact_drug", "fact_reaction"],
        },
        "data_quality": {
            "date_rejected": quality["date_rejected"],
            "age_nulled": quality["age_nulled"],
            "weight_nulled": quality["weight_nulled"],
            "dedup_deleted": quality["dedup_deleted"],
            "quarantine_rows": quality["stg_quarantine"],
            "quality_log_rows": quality["stg_data_quality_log"],
            "drug_openfda_mapped_rows": quality["drug_rows_openfda_mapped"],
            "drug_openfda_mapped_pct": quality["drug_openfda_pct"],
            "missingness": quality["missingness"],
        },
        "headline_analysis": {
            "serious_reports": serious_reports,
            "non_serious_reports": serious.get("false", 0),
            "serious_rate_pct": round(serious_reports / total_reports * 100, 2),
            "top_suspect_drugs": _top_rows(stats["top_suspect_drugs"]),
            "top_reactions": _top_rows(stats["top_reactions"]),
            "top_countries": _top_rows(stats["top_countries"]),
            "outcome_distribution": stats["outcome_distribution"],
        },
        "pareto": {
            "drug_80pct_cutoff": pareto["drugs_80pct_cutoff"],
            "reaction_80pct_cutoff": pareto["reactions_80pct_cutoff"],
            "manufacturer_80pct_cutoff": pareto["manufacturers_80pct_cutoff"],
            "top_suspect_drugs": _top_rows(pareto["drugs"]),
            "top_reactions": _top_rows(pareto["reactions"]),
            "top_manufacturers": _top_rows(pareto["manufacturers"]),
        },
        "cycle_time": {
            "receive_to_receipt_by_year": cycle_time["receive_to_receipt_by_year"],
            "receive_to_receipt_by_reporter": cycle_time["receive_to_receipt_by_reporter"],
            "receipt_to_transmission_by_year": cycle_time["receipt_to_transmission_by_year"],
        },
        "trend": {
            "month_count": len(trend["monthly_series"]),
            "polyfit_coefficients": trend["polyfit_coefficients"],
            "avg_receipt_to_receive_lag_days": trend["avg_receipt_to_receive_lag_days"],
        },
        "forecast": {
            "method": forecast["method"],
            "latest_observed_month": forecast["latest_observed_month"],
            "excluded_latest_month_as_potentially_incomplete": forecast[
                "excluded_latest_month_as_potentially_incomplete"
            ],
            "horizon_months": forecast["horizon_months"],
            "total": forecast["total"],
            "serious": forecast["serious"],
        },
        "signals": {
            "analysis_unit": signals["analysis_unit"],
            "top_drugs_limit": signals["top_drugs_limit"],
            "minimum_pair_count": signals["minimum_pair_count"],
            "screening": signals["screening"],
            "candidate_count": signals["candidate_count"],
            "signal_count": signals["signal_count"],
            "top_signals": signals["signals"][:5],
        },
        "ml_classifier": ml_metrics,
        "stage_status": {
            "stage_0_setup": "complete",
            "stage_1_ingest_and_model": "complete",
            "stage_2_cleaning_and_quality": "implemented; documentation completed in this report",
            "stage_3_sql_analysis": "complete",
            "stage_4_power_bi_package": "prepared",
            "stage_5_readme_and_results": "complete",
            "stage_6_signal_detection": "implemented; SQL-backed run completed",
            "stage_7_forecasting": "implemented; rolling-origin model comparison completed",
            "stage_8_ml_classifier": "implemented; time-based evaluation and local MLflow tracking completed",
        },
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _rows_table(rows: list[dict[str, Any]], name_key: str) -> str:
    lines = ["| Name | Reports |", "|---|---:|"]
    for row in rows:
        lines.append(f"| {row[name_key]} | {_fmt(row['report_count'])} |")
    return "\n".join(lines)


def _render_report(metrics: dict[str, Any]) -> str:
    dataset = metrics["dataset"]
    model = metrics["model"]
    quality = metrics["data_quality"]
    headline = metrics["headline_analysis"]
    pareto = metrics["pareto"]
    forecast = metrics["forecast"]
    signals = metrics["signals"]
    ml = metrics["ml_classifier"]

    missingness_lines = [
        f"| {field} | {_fmt(values['null_count'])} | {_fmt(values['null_pct'])}% |"
        for field, values in quality["missingness"].items()
    ]
    serious_rate = _fmt(headline["serious_rate_pct"])
    forecast_lines = "\n".join(
        f"| {row['year_month']} | {_fmt(row['predicted_count'])} | {_fmt(row['lower_95'])} | {_fmt(row['upper_95'])} |"
        for row in forecast["total"]["forecast"][:6]
    )
    model_lines = "\n".join(
        f"| {series} | {details['selected_model']} | "
        f"{_fmt(details['backtest'][details['selected_model']]['mae'])} | "
        f"{_fmt(details['backtest'][details['selected_model']]['rmse'])} | "
        f"{_fmt(details['backtest'][details['selected_model']]['smape'])}% |"
        for series, details in (("Total", forecast["total"]), ("Serious", forecast["serious"]))
    )

    return f"""# FAERS Adverse Drug Event Analysis — Stage 5 and 6 Results

Generated from [`results/metrics.json`](../results/metrics.json) by
[`src/build_metrics.py`](../src/build_metrics.py).

## 1. Scope and reproducibility

- **Reports processed:** {_fmt(dataset['reports_processed'])}
- **Source dataset total:** {_fmt(dataset['source_total_reports'])}
- **Scope:** {dataset['scope']}
- **Model:** {_fmt(model['fact_drug_rows'])} drug rows and {_fmt(model['fact_reaction_rows'])} reaction rows across three fact tables and six dimensions.

This report describes the sample file, not the complete FAERS source set. Re-running
the upstream SQL/Python pipeline and then `src/build_metrics.py` regenerates the
metrics and this report.

## 2. Headline findings

- **Serious reports:** {_fmt(headline['serious_reports'])} of {_fmt(dataset['reports_processed'])} ({serious_rate}%).
- **Non-serious reports:** {_fmt(headline['non_serious_reports'])}.
- **Top suspect drug:** {headline['top_suspect_drugs'][0]['drug_name']} ({_fmt(headline['top_suspect_drugs'][0]['report_count'])} rows).
- **Top reaction:** {headline['top_reactions'][0]['reaction_meddra_apt']} ({_fmt(headline['top_reactions'][0]['report_count'])} rows).

### Top suspect drugs

{_rows_table(headline['top_suspect_drugs'], 'drug_name')}

### Top reactions

{_rows_table(headline['top_reactions'], 'reaction_meddra_apt')}

## 3. Data quality

| Check | Result |
|---|---:|
| Invalid/out-of-range dates rejected | {_fmt(quality['date_rejected'])} |
| Implausible ages nulled | {_fmt(quality['age_nulled'])} |
| Implausible weights nulled | {_fmt(quality['weight_nulled'])} |
| Older report versions removed | {_fmt(quality['dedup_deleted'])} |
| Quarantine rows | {_fmt(quality['quarantine_rows'])} |
| OpenFDA drug mappings | {_fmt(quality['drug_openfda_mapped_rows'])} ({_fmt(quality['drug_openfda_mapped_pct'])}%) |

### Missingness

| Field | Null rows | Null percentage |
|---|---:|---:|
{chr(10).join(missingness_lines)}

## 4. Pareto analysis

The Pareto outputs use suspect drugs for drug counts and report the first item
where cumulative share reaches 80%. They are descriptive reporting patterns,
not causal safety conclusions.

- **Drugs needed to reach 80%:** {_fmt(pareto['drug_80pct_cutoff'])}
- **Reactions needed to reach 80%:** {_fmt(pareto['reaction_80pct_cutoff'])}
- **Manufacturers needed to reach 80%:** {_fmt(pareto['manufacturer_80pct_cutoff'])}

## 5. Cycle-time analysis

The current sample has a strong time-composition effect: older reports have much
larger receive-to-receipt lags, while the 2026 records average approximately
two days. This should not be interpreted as a causal process improvement without
controlling for reporting period and source mix.

The detailed yearly, reporter, and receipt-to-transmission results remain in
[`results/cycle_time.json`](../results/cycle_time.json).

## 6. Trend and forecast output

The Stage 7 forecast compares seasonal naive, ETS, and SARIMA using rolling-origin
one-step backtesting over the last 12 available origins. The latest observed
month ({forecast['latest_observed_month']}) is excluded from training as
potentially incomplete because FAERS reporting has a data-boundary lag.

| Series | Selected model | MAE | RMSE | sMAPE |
|---|---|---:|---:|---:|
{model_lines}

The selected model's first six total-report projections are:

| Month | Predicted reports | Lower 95% | Upper 95% |
|---|---:|---:|---:|
{forecast_lines}

The complete 12-month forecasts and all model comparison metrics are in
[`results/forecast.json`](../results/forecast.json). Prediction intervals use
the selected model's residual standard deviation and are approximate.

## 7. Stage 6 signal detection

Signal analysis uses the report as the unit of analysis and restricts candidates
to the top {signals['top_drugs_limit']} suspect drugs. The screening criteria are
pair count >= {signals['minimum_pair_count']}, PRR >= 2, and Yates-corrected
chi-square >= 4.

- **Candidates evaluated:** {_fmt(signals['candidate_count'])}
- **Screened signals:** {_fmt(signals['signal_count'])}

The calculations include PRR and ROR with approximate 95% log-scale confidence
intervals. These are disproportionality screening measures, not causal effects.
The complete output is in [`results/signals.json`](../results/signals.json).

## 8. Stage 8 seriousness classifier

The classifier predicts `fact_report.is_serious` using report-level demographics,
reporter fields, date features, and aggregated drug/reaction counts. The split
is chronological: earlier reporting periods are used for training and later
periods for testing.

| Model | ROC-AUC | Precision | Recall | Brier score | Calibration MAE |
|---|---:|---:|---:|---:|---:|
| Baseline | {_fmt(ml['evaluation']['baseline']['roc_auc'])} | {_fmt(ml['evaluation']['baseline']['precision'])} | {_fmt(ml['evaluation']['baseline']['recall'])} | {_fmt(ml['evaluation']['baseline']['brier_score'])} | {_fmt(ml['evaluation']['baseline']['calibration_mean_absolute_error'])} |
| Logistic regression | {_fmt(ml['evaluation']['logistic_regression']['roc_auc'])} | {_fmt(ml['evaluation']['logistic_regression']['precision'])} | {_fmt(ml['evaluation']['logistic_regression']['recall'])} | {_fmt(ml['evaluation']['logistic_regression']['brier_score'])} | {_fmt(ml['evaluation']['logistic_regression']['calibration_mean_absolute_error'])} |
| Gradient boosting | {_fmt(ml['evaluation']['gradient_boosting']['roc_auc'])} | {_fmt(ml['evaluation']['gradient_boosting']['precision'])} | {_fmt(ml['evaluation']['gradient_boosting']['recall'])} | {_fmt(ml['evaluation']['gradient_boosting']['brier_score'])} | {_fmt(ml['evaluation']['gradient_boosting']['calibration_mean_absolute_error'])} |

- **Training rows:** {_fmt(ml['train_rows'])}; **test rows:** {_fmt(ml['test_rows'])}
- **Selected model:** {ml['selected_model']}
- **Persisted model:** [`{ml['model_path']}`](../{ml['model_path']})
- **Tracking database:** `{ml['mlflow_tracking_uri']}`

The statsmodels logistic model also writes odds ratios and approximate 95%
confidence intervals to `results/ml_metrics.json` (the current fit reports
`converged: {ml['evaluation']['logistic_regression_statsmodels'].get('converged', False)}`;
interpret sparse-category estimates cautiously). The classifier is predictive
and should not be interpreted as a causal model or clinical decision tool.

## 9. Limitations and next stages

- FAERS is a spontaneous-reporting system; counts do not estimate incidence or causality.
- The project currently analyzes one 12,000-report sample rather than all 31 source files.
- Product and manufacturer results are quality/reporting analytics, not supply-chain or demand forecasts.
- API, Streamlit, Docker, CI, and broader automated tests remain later roadmap work.
"""


def main() -> None:
    stats = _read_json("stats.json")
    quality = _read_json("data_quality.json")
    pareto = _read_json("pareto.json")
    cycle_time = _read_json("cycle_time.json")
    trend = _read_json("trend.json")
    forecast = _read_json("forecast.json")
    signals = _read_json("signals.json")
    ml_metrics = _read_json("ml_metrics.json")
    metrics = _summary_metrics(stats, quality, pareto, cycle_time, trend, forecast, signals, ml_metrics)

    RESULTS_DIR.mkdir(exist_ok=True)
    REPORT_PATH.parent.mkdir(exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(_render_report(metrics), encoding="utf-8")
    print(f"Wrote {METRICS_PATH}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
