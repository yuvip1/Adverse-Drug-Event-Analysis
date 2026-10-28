from datetime import date
from unittest.mock import patch

import pytest

import app


def test_build_query_kwargs_omits_disabled_date_filter():
    kwargs = app.build_query_kwargs(
        use_date_filter=False,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31),
        drug_name="",
        reaction_name="HEADACHE",
        country_code="",
        serious_only=False,
        limit=25,
    )

    assert kwargs == {
        "start_date": None,
        "end_date": None,
        "drug_name": None,
        "reaction_name": "HEADACHE",
        "country_code": None,
        "serious_only": False,
        "limit": 25,
    }


def test_build_query_kwargs_preserves_enabled_filters():
    kwargs = app.build_query_kwargs(
        use_date_filter=True,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31),
        drug_name=" ASPIRIN ",
        reaction_name=" HEADACHE ",
        country_code="us",
        serious_only=True,
        limit=100,
    )

    assert kwargs["start_date"] == date(2020, 1, 1)
    assert kwargs["end_date"] == date(2020, 12, 31)
    assert kwargs["drug_name"] == " ASPIRIN "
    assert kwargs["reaction_name"] == " HEADACHE "
    assert kwargs["country_code"] == "us"
    assert kwargs["serious_only"] is True


def test_validate_date_range_accepts_enabled_range():
    with patch.object(app.st, "error") as error:
        assert app._validate_date_range(
            use_date_filter=True,
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
        )

    error.assert_not_called()


def test_validate_date_range_rejects_reversed_enabled_range():
    with patch.object(app.st, "error") as error:
        assert not app._validate_date_range(
            use_date_filter=True,
            start_date=date(2021, 1, 1),
            end_date=date(2020, 12, 31),
        )

    error.assert_called_once_with("Start date must be on or before end date.")


def test_validate_date_range_ignores_values_when_filter_disabled():
    with patch.object(app.st, "error") as error:
        assert app._validate_date_range(
            use_date_filter=False,
            start_date=date(2021, 1, 1),
            end_date=date(2020, 12, 31),
        )

    error.assert_not_called()


def test_download_frame_contains_aggregate_columns_only():
    payload = app._download_frame([
        {"drug_name": "ASPIRIN", "report_count": 3, "serious_count": 2}
    ])

    assert payload == b"drug_name,report_count,serious_count\nASPIRIN,3,2\n"
    assert b"report_key" not in payload
    assert b"safetyreportid" not in payload
    assert b"companynumb" not in payload


def test_render_results_handles_empty_summary_without_chart_calls():
    result = {
        "summary": {"report_count": 0, "serious_count": 0, "serious_pct": None},
        "monthly_series": [],
        "top_drugs": [],
        "top_reactions": [],
    }
    with patch.object(app.st, "info") as info, patch.object(app.st, "subheader"):
        app._render_results(result)

    info.assert_called_once_with("No reports matched the selected filters.")


def test_service_errors_are_known_ui_errors():
    error = RuntimeError("SQL Server unavailable")
    with (
        patch.object(app, "get_reporting_summary", side_effect=error),
        pytest.raises(RuntimeError, match="SQL Server unavailable"),
    ):
        app.get_reporting_summary()


def test_app_module_does_not_query_on_import():
    with patch.object(app, "get_reporting_summary") as service:
        __import__("importlib").reload(app)

    service.assert_not_called()


def test_navigation_exposes_all_functional_pages():
    with patch.object(app.st.sidebar, "radio", return_value="Signal explorer") as radio:
        page = app._render_navigation()

    assert page == "Signal explorer"
    radio.assert_called_once()
    assert radio.call_args.args[1] == app.PAGE_OPTIONS
