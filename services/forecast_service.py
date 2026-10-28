from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import pandas as pd

from services.db import fetch_dataframe
from src.forecast import _forecast_series

MAX_HORIZON = 24
FetchDataFrame = Callable[[str, Sequence[object]], pd.DataFrame]


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and not isinstance(start_date, date):
        raise TypeError("start_date must be a date or None")
    if end_date is not None and not isinstance(end_date, date):
        raise TypeError("end_date must be a date or None")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date cannot be later than end_date")


def _validate_horizon(horizon: int) -> None:
    if isinstance(horizon, bool) or not isinstance(horizon, int):
        raise TypeError("horizon must be an integer")
    if not 1 <= horizon <= MAX_HORIZON:
        raise ValueError(f"horizon must be between 1 and {MAX_HORIZON}")


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _complete_months(frame: pd.DataFrame) -> list[dict[str, int]]:
    if frame.empty:
        return []
    values = {
        (int(row.year), int(row.month)): {
            "year": int(row.year),
            "month": int(row.month),
            "total_count": int(row.total_count),
            "serious_count": int(row.serious_count),
        }
        for row in frame.itertuples(index=False)
    }
    first = min(values)
    last = max(values)
    months: list[dict[str, int]] = []
    for index in range(_month_index(*first), _month_index(*last) + 1):
        year, month = divmod(index, 12)
        months.append(values.get(
            (year, month + 1),
            {"year": year, "month": month + 1, "total_count": 0, "serious_count": 0},
        ))
    return months


def _query_monthly(
    *,
    start_date: date | None,
    end_date: date | None,
    country_code: str | None,
) -> tuple[str, list[object]]:
    conditions = ["d.date_key <> -1"]
    params: list[object] = []
    if start_date is not None:
        conditions.append("d.full_date >= ?")
        params.append(start_date)
    if end_date is not None:
        conditions.append("d.full_date <= ?")
        params.append(end_date)
    if country_code is not None:
        if len(country_code) != 2:
            raise ValueError("country_code must contain exactly two characters")
        conditions.append("country.iso2_code = ?")
        params.append(country_code.strip().upper())
    return f"""
        SELECT d.year, d.month,
               COUNT(DISTINCT fr.report_key) AS total_count,
               COUNT(DISTINCT CASE WHEN fr.is_serious = 1 THEN fr.report_key END)
                   AS serious_count
        FROM dbo.fact_report fr
        JOIN dbo.dim_date d ON d.date_key = fr.date_key
        JOIN dbo.dim_country country ON country.country_key = fr.country_key
        WHERE {" AND ".join(conditions)}
        GROUP BY d.year, d.month
        ORDER BY d.year, d.month
    """, params


def forecast_reporting_volume(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    country_code: str | None = None,
    horizon: int = 12,
    fetcher: FetchDataFrame = fetch_dataframe,
) -> dict[str, Any]:
    """Forecast total and serious monthly report counts from aggregate history."""
    _validate_dates(start_date, end_date)
    _validate_horizon(horizon)
    normalized_country = country_code.strip().upper() if country_code else None
    sql, params = _query_monthly(
        start_date=start_date,
        end_date=end_date,
        country_code=normalized_country,
    )
    monthly = _complete_months(fetcher(sql, params))
    if len(monthly) <= 1:
        raise ValueError("At least two monthly observations are required")

    training = monthly[:-1]
    cutoff_label = f"{training[-1]['year']}-{training[-1]['month']:02d}"
    output: dict[str, Any] = {
        "filters": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "country_code": normalized_country,
        },
        "historical": [
            {
                "year_month": f"{row['year']}-{row['month']:02d}",
                "total_count": row["total_count"],
                "serious_count": row["serious_count"],
            }
            for row in monthly
        ],
        "training_cutoff": cutoff_label,
        "excluded_latest_month_as_potentially_incomplete": True,
        "horizon_months": horizon,
    }
    for label, key in (("total_reports", "total_count"), ("serious_reports", "serious_count")):
        values = [row[key] for row in training]
        if len(values) < 12:
            raise ValueError(
                f"At least 12 monthly observations are required for {label}"
            )
        output[label] = _forecast_series(
            values,
            label,
            cutoff_label,
            horizon=horizon,
        )
    return output
