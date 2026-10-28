from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pyodbc
import streamlit as st

from services.analytics_service import get_reporting_summary
from services.classifier_service import (
    categorical_values,
    classify_new_report,
    load_classifier,
)
from services.forecast_service import MAX_HORIZON, forecast_reporting_volume
from services.signal_service import explore_signals

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
DEFAULT_START_DATE = date(2015, 1, 1)
PAGE_OPTIONS = (
    "Reporting overview",
    "Signal explorer",
    "Forecasting",
    "Classifier",
)
ReportingSidebar = tuple[bool, date, date, str, str, str, bool, int, bool]


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --faers-ink: #17324d;
            --faers-muted: #60758a;
            --faers-blue: #1d5f91;
            --faers-border: #d7e2eb;
            --faers-surface: #ffffff;
        }
        .stApp {
            background: #f5f8fb;
        }
        [data-testid="stHeader"] {
            background: rgba(245, 248, 251, 0.92);
        }
        [data-testid="stSidebar"] {
            background: #eef4f8;
            border-right: 1px solid var(--faers-border);
        }
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--faers-ink);
        }
        .faers-eyebrow {
            color: var(--faers-blue);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }
        .faers-title {
            color: var(--faers-ink);
            font-size: clamp(2rem, 4vw, 3.2rem);
            font-weight: 760;
            letter-spacing: -0.045em;
            line-height: 1.05;
            margin: 0;
        }
        .faers-subtitle {
            color: var(--faers-muted);
            font-size: 0.98rem;
            line-height: 1.55;
            max-width: 760px;
            margin: 0.65rem 0 1.4rem;
        }
        [data-testid="stMetric"] {
            background: var(--faers-surface);
            border: 1px solid var(--faers-border);
            border-radius: 0.65rem;
            padding: 1rem 1.1rem;
        }
        [data-testid="stMetricLabel"] {
            color: var(--faers-muted);
        }
        [data-testid="stMetricValue"] {
            color: var(--faers-ink);
            font-variant-numeric: tabular-nums;
        }
        div.stButton > button[kind="primary"],
        div[data-testid="stFormSubmitButton"] button {
            background: var(--faers-blue);
            border-color: var(--faers-blue);
        }
        div.stButton > button[kind="primary"]:hover,
        div[data-testid="stFormSubmitButton"] button:hover {
            background: #154b73;
            border-color: #154b73;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="faers-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="faers-title">{title}</h1>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="faers-subtitle">{subtitle}</p>',
        unsafe_allow_html=True,
    )


def _render_navigation() -> str:
    st.sidebar.markdown("## FAERS analytics")
    st.sidebar.caption("Read-only pharmacovigilance intelligence")
    return st.sidebar.radio(
        "Workspace",
        PAGE_OPTIONS,
        index=0,
        key="active_page",
    )


def _render_reporting_sidebar() -> ReportingSidebar:
    st.sidebar.markdown("### Overview filters")
    use_date_filter = st.sidebar.checkbox(
        "Filter by receivedate",
        value=False,
        key="overview_date_filter",
    )
    with st.sidebar.form("reporting_filters"):
        start_date = st.date_input(
            "Start date",
            value=DEFAULT_START_DATE,
            disabled=not use_date_filter,
            key="overview_start_date",
        )
        end_date = st.date_input(
            "End date",
            value=date.today(),
            disabled=not use_date_filter,
            key="overview_end_date",
        )
        drug_name = st.text_input(
            "Drug name",
            placeholder="Exact normalized name",
            key="overview_drug_name",
        )
        reaction_name = st.text_input(
            "Reaction",
            placeholder="Exact MedDRA PT",
            key="overview_reaction_name",
        )
        country_code = st.text_input(
            "Primary-source country",
            max_chars=2,
            placeholder="US",
            key="overview_country_code",
        )
        serious_only = st.checkbox(
            "Serious reports only",
            value=False,
            key="overview_serious_only",
        )
        limit = st.slider(
            "Rows per aggregate table",
            1,
            MAX_LIMIT,
            DEFAULT_LIMIT,
            key="overview_limit",
        )
        submitted = st.form_submit_button(
            "Refresh overview",
            type="primary",
            width="stretch",
        )
    st.sidebar.caption("Filters apply to the overview query only.")
    return (
        use_date_filter,
        start_date,
        end_date,
        drug_name,
        reaction_name,
        country_code,
        serious_only,
        limit,
        submitted,
    )


def build_query_kwargs(
    *,
    use_date_filter: bool,
    start_date: date,
    end_date: date,
    drug_name: str,
    reaction_name: str,
    country_code: str,
    serious_only: bool,
    limit: int,
) -> dict[str, Any]:
    """Convert page controls into the analytics-service contract."""
    return {
        "start_date": start_date if use_date_filter else None,
        "end_date": end_date if use_date_filter else None,
        "drug_name": drug_name or None,
        "reaction_name": reaction_name or None,
        "country_code": country_code or None,
        "serious_only": serious_only,
        "limit": limit,
    }


def _format_percentage(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


def _download_frame(rows: list[dict[str, Any]]) -> bytes:
    """Serialize aggregate rows only for a download button."""
    return pd.DataFrame(rows).to_csv(index=False, lineterminator="\n").encode("utf-8")


def _render_aggregate_table(
    rows: list[dict[str, Any]],
    *,
    key: str,
    page_size: int = 25,
) -> None:
    """Render a searchable, paginated aggregate-only table."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        st.info("No aggregate rows are available.")
        return

    search = st.text_input(
        "Search table",
        placeholder="Search names or values",
        key=f"{key}_search",
    ).strip().lower()
    if search:
        searchable = frame.astype(str).apply(
            lambda column: column.str.lower().str.contains(search, regex=False)
        )
        frame = frame[searchable.any(axis=1)]

    total_pages = max(1, (len(frame) + page_size - 1) // page_size)
    page_key = f"{key}_page"
    current_page = max(1, min(int(st.session_state.get(page_key, 1)), total_pages))
    st.session_state[page_key] = current_page
    page = st.number_input(
        "Table page",
        min_value=1,
        max_value=total_pages,
        value=current_page,
        step=1,
        key=page_key,
    )
    start = (int(page) - 1) * page_size
    first_row = min(start + 1, len(frame))
    last_row = min(start + page_size, len(frame))
    st.caption(f"Showing {first_row:,}–{last_row:,} of {len(frame):,} rows")
    st.dataframe(
        frame.iloc[start : start + page_size],
        hide_index=True,
        width="stretch",
    )


def _validate_date_range(
    *,
    use_date_filter: bool,
    start_date: date,
    end_date: date,
) -> bool:
    if use_date_filter and start_date > end_date:
        st.error("Start date must be on or before end date.")
        return False
    return True


def _render_results(result: dict[str, Any]) -> None:
    summary = result["summary"]
    st.subheader("Reporting snapshot")
    kpi_columns = st.columns(3)
    kpi_columns[0].metric("Distinct reports", f"{summary['report_count']:,}")
    kpi_columns[1].metric("Serious reports", f"{summary['serious_count']:,}")
    kpi_columns[2].metric("Serious-report rate", _format_percentage(summary["serious_pct"]))

    if summary["report_count"] == 0:
        st.info("No reports matched the selected filters.")
        return

    monthly_rows = result["monthly_series"]
    monthly = pd.DataFrame(monthly_rows)
    if not monthly.empty:
        monthly["year_month"] = (
            monthly["year"].astype(str)
            + "-"
            + monthly["month"].astype(str).str.zfill(2)
        )
        monthly_chart = monthly.set_index("year_month")[["report_count", "serious_count"]]
        st.subheader("Monthly reporting trend")
        st.line_chart(monthly_chart)
        st.download_button(
            "Download monthly aggregates",
            _download_frame(monthly_rows),
            "faers_monthly_aggregates.csv",
            "text/csv",
            width="content",
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Top suspect drugs")
        drug_rows = result["top_drugs"]
        if not drug_rows:
            st.info("No suspect-drug aggregates are available.")
        else:
            drugs = pd.DataFrame(drug_rows)
            st.bar_chart(drugs.set_index("drug_name")[["report_count"]])
            _render_aggregate_table(drug_rows, key="overview_drugs")
            st.download_button(
                "Download top drugs",
                _download_frame(drug_rows),
                "faers_top_drugs.csv",
                "text/csv",
                width="content",
            )

    with right:
        st.subheader("Top reactions")
        reaction_rows = result["top_reactions"]
        if not reaction_rows:
            st.info("No reaction aggregates are available.")
        else:
            reactions = pd.DataFrame(reaction_rows)
            st.bar_chart(reactions.set_index("reaction")[["report_count"]])
            _render_aggregate_table(reaction_rows, key="overview_reactions")
            st.download_button(
                "Download top reactions",
                _download_frame(reaction_rows),
                "faers_top_reactions.csv",
                "text/csv",
                width="content",
            )


def _render_signal_results(result: dict[str, Any]) -> None:
    st.subheader("Screened signals")
    st.caption(
        f"{result['signal_count']:,} screened signals from "
        f"{result['candidate_count']:,} candidates "
        f"({result['total_reports']:,} filtered reports)."
    )
    signal_rows = result["signals"]
    if not signal_rows:
        st.info("No signals matched the configured screening thresholds.")
        return
    _render_aggregate_table(signal_rows, key="signals")
    st.download_button(
        "Download signal aggregates",
        _download_frame(signal_rows),
        "faers_signal_aggregates.csv",
        "text/csv",
        width="content",
    )


def _render_signal_explorer() -> None:
    _render_page_header(
        "Phase 3 · disproportionality",
        "Drug safety signal explorer",
        "Aggregate-only drug-reaction disproportionality screening using "
        "report-level PRR, ROR, confidence intervals, and Yates-corrected chi-square."
    )
    signal_date_filter = st.checkbox(
        "Filter signals by receivedate",
        value=False,
        key="signal_date_filter",
    )
    with st.form("signal_filters"):
        signal_date_columns = st.columns(2)
        with signal_date_columns[0]:
            signal_start_date = st.date_input(
                "Signal start date",
                value=DEFAULT_START_DATE,
                disabled=not signal_date_filter,
                key="signal_start_date",
            )
        with signal_date_columns[1]:
            signal_end_date = st.date_input(
                "Signal end date",
                value=date.today(),
                disabled=not signal_date_filter,
                key="signal_end_date",
            )

        filter_columns = st.columns(3)
        with filter_columns[0]:
            signal_drug = st.text_input(
                "Signal drug",
                placeholder="Optional exact normalized name",
                key="signal_drug",
            )
        with filter_columns[1]:
            signal_reaction = st.text_input(
                "Signal reaction",
                placeholder="Optional exact MedDRA PT",
                key="signal_reaction",
            )
        with filter_columns[2]:
            signal_country = st.text_input(
                "Signal country",
                max_chars=2,
                key="signal_country",
            )

        serious_signals = st.checkbox(
            "Serious reports only",
            value=False,
            key="signal_serious_only",
        )
        threshold_columns = st.columns(3)
        with threshold_columns[0]:
            min_pair_count = st.number_input(
                "Minimum pair reports",
                min_value=1,
                max_value=MAX_LIMIT,
                value=3,
                step=1,
            )
        with threshold_columns[1]:
            min_prr = st.number_input(
                "Minimum PRR",
                min_value=0.0,
                value=2.0,
                step=0.1,
            )
        with threshold_columns[2]:
            min_chi_square = st.number_input(
                "Minimum chi-square",
                min_value=0.0,
                value=4.0,
                step=0.5,
            )
        signal_limit = st.slider(
            "Maximum signal results",
            1,
            MAX_LIMIT,
            DEFAULT_LIMIT,
            key="signal_limit",
        )
        signal_submitted = st.form_submit_button(
            "Explore signals",
            type="primary",
        )

    if not signal_submitted:
        st.info("Choose signal filters and select Explore signals.")
        return
    if not _validate_date_range(
        use_date_filter=signal_date_filter,
        start_date=signal_start_date,
        end_date=signal_end_date,
    ):
        return

    try:
        with st.spinner("Calculating aggregate drug-reaction signals..."):
            result = explore_signals(
                start_date=signal_start_date if signal_date_filter else None,
                end_date=signal_end_date if signal_date_filter else None,
                drug_name=signal_drug or None,
                reaction_name=signal_reaction or None,
                country_code=signal_country or None,
                serious_only=serious_signals,
                min_pair_count=int(min_pair_count),
                min_prr=float(min_prr),
                min_chi_square=float(min_chi_square),
                limit=int(signal_limit),
            )
    except ValueError as error:
        st.error(f"Invalid signal filter: {error}")
        return
    except (RuntimeError, pyodbc.Error) as error:
        st.error(f"The signal database query failed: {error}")
        return
    _render_signal_results(result)


def _render_forecasting_page() -> None:
    _render_page_header(
        "Phase 4 · time series",
        "Reporting-volume forecasting",
        "Monthly aggregate forecasts for total and serious reports. "
        "The latest month is excluded from model training as potentially incomplete.",
    )
    forecast_date_filter = st.checkbox(
        "Filter forecast history by receivedate",
        value=False,
        key="forecast_date_filter",
    )
    with st.form("forecast_filters"):
        forecast_dates = st.columns(2)
        with forecast_dates[0]:
            forecast_start = st.date_input(
                "Forecast start date",
                value=DEFAULT_START_DATE,
                disabled=not forecast_date_filter,
                key="forecast_start_date",
            )
        with forecast_dates[1]:
            forecast_end = st.date_input(
                "Forecast end date",
                value=date.today(),
                disabled=not forecast_date_filter,
                key="forecast_end_date",
            )
        forecast_country = st.text_input(
            "Forecast primary-source country",
            max_chars=2,
            key="forecast_country",
        )
        forecast_horizon = st.slider(
            "Forecast horizon (months)",
            1,
            MAX_HORIZON,
            12,
            key="forecast_horizon",
        )
        forecast_submitted = st.form_submit_button(
            "Generate forecast",
            type="primary",
        )

    if not forecast_submitted:
        st.info("Choose forecast filters and select Generate forecast.")
        return
    if not _validate_date_range(
        use_date_filter=forecast_date_filter,
        start_date=forecast_start,
        end_date=forecast_end,
    ):
        return
    try:
        with st.spinner("Fitting aggregate reporting forecasts..."):
            result = forecast_reporting_volume(
                start_date=forecast_start if forecast_date_filter else None,
                end_date=forecast_end if forecast_date_filter else None,
                country_code=forecast_country or None,
                horizon=int(forecast_horizon),
            )
    except ValueError as error:
        st.error(f"Forecast input or history is not sufficient: {error}")
        return
    except pyodbc.Error as error:
        st.error(f"The forecast database query failed: {error}")
        return
    except RuntimeError as error:
        st.error(f"Forecast models could not be fitted: {error}")
        return
    except (np.linalg.LinAlgError, KeyError) as error:
        st.error(f"A forecast model could not be fitted: {error}")
        return

    historical = pd.DataFrame(result["historical"]).set_index("year_month")
    st.subheader("Historical monthly reports")
    st.line_chart(historical[["total_count", "serious_count"]])
    for label, title in (
        ("total_reports", "Total-report forecast"),
        ("serious_reports", "Serious-report forecast"),
    ):
        forecast = pd.DataFrame(result[label]["forecast"]).set_index("year_month")
        forecast_plot = forecast[["predicted_count", "lower_95", "upper_95"]].rename(
            columns={
                "predicted_count": "forecast",
                "lower_95": "approx_lower_95",
                "upper_95": "approx_upper_95",
            }
        )
        series = pd.concat([
            historical[["total_count" if label == "total_reports" else "serious_count"]]
            .rename(columns={("total_count" if label == "total_reports" else "serious_count"): "historical"}),
            forecast_plot,
        ])
        st.subheader(title)
        st.line_chart(series)
        st.caption(
            f"Selected model: {result[label]['selected_model']}. "
            "Shaded intervals are approximate 95% residual-based intervals."
        )
        _render_aggregate_table(
            forecast.reset_index().to_dict(orient="records"),
            key=f"{label}_forecast",
        )
        st.download_button(
            f"Download {label} forecast",
            _download_frame(result[label]["forecast"]),
            f"faers_{label}_forecast.csv",
            "text/csv",
        )
        metrics = result[label]["backtest"]
        st.dataframe(
            pd.DataFrame(metrics).T.reset_index(names="model"),
            hide_index=True,
            width="stretch",
        )


@st.cache_resource(show_spinner=False)
def _cached_classifier() -> Any:
    return load_classifier()


def _render_classifier_page() -> None:
    _render_page_header(
        "Phase 5 · in-memory inference",
        "Seriousness classification",
        "Predict the recorded-seriousness category for a hypothetical report "
        "using the persisted Stage 8 classifier.",
    )
    try:
        model = _cached_classifier()
        categories = categorical_values(model)
    except (FileNotFoundError, RuntimeError, TypeError) as error:
        st.error(f"The classifier model is unavailable: {error}")
        return
    with st.form("classifier_form"):
        numeric_columns = st.columns(2)
        with numeric_columns[0]:
            onset_age = st.number_input(
                "Onset age in years (optional)",
                min_value=0.0,
                max_value=150.0,
                value=None,
                placeholder="Leave blank if unknown",
            )
            weight = st.number_input(
                "Weight in kg (optional)",
                min_value=0.0,
                max_value=1000.0,
                value=None,
                placeholder="Leave blank if unknown",
            )
            report_year = st.number_input(
                "Report year",
                min_value=1900,
                max_value=2100,
                value=2024,
                step=1,
            )
            report_month = st.number_input(
                "Report month",
                min_value=1,
                max_value=12,
                value=1,
                step=1,
            )
        with numeric_columns[1]:
            drug_count = st.number_input(
                "Total drug count",
                min_value=0,
                max_value=1000,
                value=1,
                step=1,
            )
            suspect_drug_count = st.number_input(
                "Suspect drug count",
                min_value=0,
                max_value=1000,
                value=1,
                step=1,
            )
            reaction_count = st.number_input(
                "Reaction count",
                min_value=0,
                max_value=1000,
                value=1,
                step=1,
            )
        categorical_columns = st.columns(2)
        with categorical_columns[0]:
            sex_code = st.selectbox("Sex code", categories["sex_code"])
            report_type = st.selectbox("Report type", categories["report_type"])
        with categorical_columns[1]:
            country_code = st.selectbox("Country code", categories["country_code"])
            qualification_values = categories["reporter_qualification"]
            reporter_qualification = st.selectbox(
                "Reporter qualification",
                qualification_values,
                format_func=lambda value: value or "(blank / unknown)",
            )
        classify_submitted = st.form_submit_button(
            "Predict hypothetical report",
            type="primary",
        )
    if not classify_submitted:
        st.info("Enter the proposed report features and choose Predict hypothetical report.")
        return

    try:
        with st.spinner("Running the persisted classifier..."):
            prediction = classify_new_report(
                {
                    "onset_age_years": onset_age,
                    "weight_kg": weight,
                    "sex_code": sex_code,
                    "report_type": report_type,
                    "country_code": country_code,
                    "reporter_qualification": reporter_qualification,
                    "report_year": int(report_year),
                    "report_month": int(report_month),
                    "drug_count": int(drug_count),
                    "suspect_drug_count": int(suspect_drug_count),
                    "reaction_count": int(reaction_count),
                },
                model=model,
            )
    except FileNotFoundError as error:
        st.error(f"The classifier model artifact is unavailable: {error}")
        return
    except (RuntimeError, TypeError, ValueError, KeyError) as error:
        st.error(f"The hypothetical report could not be classified: {error}")
        return

    predicted_label = "Serious" if prediction["predicted_class"] else "Not serious"
    st.subheader("Prediction")
    st.metric("Predicted seriousness class", predicted_label)
    if "serious_probability" in prediction:
        st.metric(
            "Predicted probability of serious",
            f"{prediction['serious_probability']:.2%}",
        )
    st.info(
        "This is an in-memory prediction of the label the historical model would "
        "assign to these features. It is not a diagnosis, clinical determination, "
        "proof of drug causality, or estimate of clinical harm. Missing age and "
        "weight are handled by the fitted pipeline's existing imputers. The "
        "model's existing evaluation metrics are reported in results/ml_metrics.json."
    )


def main() -> None:
    st.set_page_config(
        page_title="FAERS Reporting Analytics",
        page_icon=":material/monitoring:",
        layout="wide",
    )
    _inject_styles()
    active_page = _render_navigation()

    if active_page == "Reporting overview":
        (
            date_filter,
            start_date,
            end_date,
            drug_name,
            reaction_name,
            country_code,
            serious_only,
            limit,
            submitted,
        ) = _render_reporting_sidebar()
        _render_page_header(
            "FAERS · reporting intelligence",
            "Reporting overview",
            "A filtered view of report volume, seriousness, suspect drugs, and "
            "reactions. All outputs are aggregate-only.",
        )
        if not submitted:
            st.info(
                "Set filters in the sidebar and select Refresh overview to query "
                "the warehouse."
            )
            return
        if not _validate_date_range(
            use_date_filter=date_filter,
            start_date=start_date,
            end_date=end_date,
        ):
            return
        query_kwargs = build_query_kwargs(
            use_date_filter=date_filter,
            start_date=start_date,
            end_date=end_date,
            drug_name=drug_name,
            reaction_name=reaction_name,
            country_code=country_code,
            serious_only=serious_only,
            limit=limit,
        )
        try:
            with st.spinner("Querying aggregate reporting analytics..."):
                result = get_reporting_summary(**query_kwargs)
        except ValueError as error:
            st.error(f"Invalid filter: {error}")
            return
        except (RuntimeError, pyodbc.Error) as error:
            st.error(f"The reporting database could not be queried: {error}")
            return
        _render_results(result)
    elif active_page == "Signal explorer":
        st.sidebar.info(
            "Signal filters apply only to report-level drug-reaction screening."
        )
        _render_signal_explorer()
    elif active_page == "Forecasting":
        st.sidebar.info(
            "Forecast filters apply only to the monthly volume history and models."
        )
        _render_forecasting_page()
    else:
        st.sidebar.info(
            "Classifier inputs are hypothetical and are not written to the warehouse."
        )
        _render_classifier_page()


if __name__ == "__main__":
    main()
