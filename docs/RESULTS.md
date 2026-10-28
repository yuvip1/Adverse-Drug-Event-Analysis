# FAERS Adverse Drug Event Analysis — Stage 5 and 6 Results

Generated from [`results/metrics.json`](../results/metrics.json) by
[`src/build_metrics.py`](../src/build_metrics.py).

## 1. Scope and reproducibility

- **Reports processed:** 12,000
- **Source dataset total:** 370,540
- **Scope:** One sample file: drug-event-0001-of-0031.json.zip
- **Model:** 86,798 drug rows and 49,021 reaction rows across three fact tables and six dimensions.

This report describes the sample file, not the complete FAERS source set. Re-running
the upstream SQL/Python pipeline and then `src/build_metrics.py` regenerates the
metrics and this report.

## 2. Headline findings

- **Serious reports:** 7,022 of 12,000 (58.52%).
- **Non-serious reports:** 4,978.
- **Top suspect drug:** TIRZEPATIDE (3,325 rows).
- **Top reaction:** OFF LABEL USE (930 rows).

### Top suspect drugs

| Name | Reports |
|---|---:|
| TIRZEPATIDE | 3,325 |
| INFLIXIMAB | 1,247 |
| ABALOPARATIDE | 1,225 |
| DUPILUMAB | 1,035 |
| INFLIXIMAB-DYYB | 1,021 |

### Top reactions

| Name | Reports |
|---|---:|
| OFF LABEL USE | 930 |
| NAUSEA | 803 |
| FATIGUE | 707 |
| DRUG INEFFECTIVE | 700 |
| HEADACHE | 628 |

## 3. Data quality

| Check | Result |
|---|---:|
| Invalid/out-of-range dates rejected | 0 |
| Implausible ages nulled | 0 |
| Implausible weights nulled | 2 |
| Older report versions removed | 0 |
| Quarantine rows | 4 |
| OpenFDA drug mappings | 72,332 (83.30%) |

### Missingness

| Field | Null rows | Null percentage |
|---|---:|---:|
| patientsex | 1,979 | 16.50% |
| patientonsetage | 3,985 | 33.20% |
| patientweight | 9,413 | 78.40% |
| primarysourcecountry | 139 | 1.20% |
| occurcountry | 820 | 6.80% |
| companynumb | 1,341 | 11.20% |

## 4. Pareto analysis

The Pareto outputs use suspect drugs for drug counts and report the first item
where cumulative share reaches 80%. They are descriptive reporting patterns,
not causal safety conclusions.

- **Drugs needed to reach 80%:** 338
- **Reactions needed to reach 80%:** 686
- **Manufacturers needed to reach 80%:** 84

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
month (2026-03) is excluded from training as
potentially incomplete because FAERS reporting has a data-boundary lag.

| Series | Selected model | MAE | RMSE | sMAPE |
|---|---|---:|---:|---:|
| Total | ets | 331.50 | 589.23 | 53.67% |
| Serious | ets | 172.24 | 339.91 | 27.57% |

The selected model's first six total-report projections are:

| Month | Predicted reports | Lower 95% | Upper 95% |
|---|---:|---:|---:|
| 2026-03 | 2,893.50 | 2,677.66 | 3,109.34 |
| 2026-04 | 3,418.87 | 3,203.03 | 3,634.71 |
| 2026-05 | 3,997.38 | 3,781.55 | 4,213.22 |
| 2026-06 | 4,416.67 | 4,200.83 | 4,632.51 |
| 2026-07 | 4,926.90 | 4,711.06 | 5,142.74 |
| 2026-08 | 5,440.20 | 5,224.37 | 5,656.04 |

The complete 12-month forecasts and all model comparison metrics are in
[`results/forecast.json`](../results/forecast.json). Prediction intervals use
the selected model's residual standard deviation and are approximate.

## 7. Stage 6 signal detection

Signal analysis uses the report as the unit of analysis and restricts candidates
to the top 100 suspect drugs. The screening criteria are
pair count >= 3, PRR >= 2, and Yates-corrected
chi-square >= 4.

- **Candidates evaluated:** 6,617
- **Screened signals:** 5,125

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
| Baseline | 0.50 | 0.00 | 0.00 | 0.31 | 0.26 |
| Logistic regression | 0.86 | 0.82 | 0.83 | 0.15 | 0.07 |
| Gradient boosting | 0.86 | 0.85 | 0.77 | 0.15 | 0.04 |

- **Training rows:** 1,640; **test rows:** 10,360
- **Selected model:** gradient_boosting
- **Persisted model:** [`results\model\seriousness_classifier.joblib`](../results\model\seriousness_classifier.joblib)
- **Tracking database:** `sqlite:///C:/Users/yuvra/Desktop/FAERS-Adverse-Drug-Event-Analysis/results/mlflow.db`

The statsmodels logistic model also writes odds ratios and approximate 95%
confidence intervals to `results/ml_metrics.json` (the current fit reports
`converged: False`;
interpret sparse-category estimates cautiously). The classifier is predictive
and should not be interpreted as a causal model or clinical decision tool.

## 9. Limitations and next stages

- FAERS is a spontaneous-reporting system; counts do not estimate incidence or causality.
- The project currently analyzes one 12,000-report sample rather than all 31 source files.
- Product and manufacturer results are quality/reporting analytics, not supply-chain or demand forecasts.
- API, Streamlit, Docker, CI, and broader automated tests remain later roadmap work.
