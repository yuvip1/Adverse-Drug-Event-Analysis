# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Pharmacovigilance analysts reviewing drug safety signals, clinical researchers exploring adverse event patterns, and regulatory affairs professionals preparing signal reports. Multiple audiences share the same tool; no single primary user was singled out.

## Product Purpose

FAERS adverse-event analysis covering three capabilities: (1) FDA signal detection with statistical reporting (PRR/ROR, confidence intervals, signal screening), (2) adverse-event trend forecasting with rolling-origin backtesting and prediction intervals, and (3) drug seriousness classification via ML. Success means a reviewer can go from raw FAERS reports to a screened, prioritized signal list with documented statistical evidence.

## Positioning

A single Streamlit workspace that combines signal detection, forecasting, and ML seriousness classification on the FAERS dataset, rather than three separate tools.

## Operating Context

Reviewers interact through a multi-page Streamlit app (pages/), backed by a SQL star schema (sql/) and a Python services layer (services/). Data is ingested from FAERS source files into SQL, then queried for reporting summaries, signal exploration, forecasting, and classification.

## Capabilities and Constraints

- Signal detection: PRR, ROR, confidence intervals, and signal screening
- Forecasting: seasonal naive, ETS, and SARIMA comparison with rolling-origin backtesting and prediction intervals
- Seriousness prediction: ML classifier for drug seriousness
- The existing SQL star schema and services layer must be preserved; future work should not break the services/ contracts or sql/ schema

## Brand Commitments

None recorded.

## Evidence on Hand

SQL schema files in sql/ define the star schema and views; services/ implements analytics, classifier, forecast, and signal logic; tests/ covers services and app behavior.

## Product Principles

- One workspace for detection, forecasting, and classification (no context switching between tools)
- Statistical evidence accompanies every signal (PRR/ROR with confidence intervals, not just raw counts)
- Preserve the SQL services contract; don't introduce a competing data layer

## Accessibility & Inclusion

Omitted — no product-specific requirement was established.
