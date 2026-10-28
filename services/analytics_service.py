from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import pandas as pd

from services.db import fetch_dataframe

MAX_LIMIT = 1000
FetchDataFrame = Callable[[str, Sequence[object]], pd.DataFrame]


def _normalize_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if field_name == "country_code" and len(normalized) != 2:
        raise ValueError("country_code must contain exactly two characters")
    return normalized


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and not isinstance(start_date, date):
        raise TypeError("start_date must be a date or None")
    if end_date is not None and not isinstance(end_date, date):
        raise TypeError("end_date must be a date or None")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date cannot be later than end_date")


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")


def _filter_cte(
    *,
    start_date: date | None,
    end_date: date | None,
    drug_name: str | None,
    reaction_name: str | None,
    country_code: str | None,
    serious_only: bool | None,
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
        conditions.append("country.iso2_code = ?")
        params.append(country_code)
    if serious_only is True:
        conditions.append("fr.is_serious = 1")
    elif serious_only is not None and not isinstance(serious_only, bool):
        raise TypeError("serious_only must be a boolean or None")
    if drug_name is not None:
        conditions.append("""
            EXISTS (
                SELECT 1
                FROM dbo.fact_drug fd_filter
                JOIN dbo.dim_drug drug_filter
                    ON drug_filter.drug_key = fd_filter.drug_key_dim
                WHERE fd_filter.report_key = fr.report_key
                  AND drug_filter.drug_name = ?
            )
        """)
        params.append(drug_name)
    if reaction_name is not None:
        conditions.append("""
            EXISTS (
                SELECT 1
                FROM dbo.fact_reaction rx_filter
                JOIN dbo.dim_reaction reaction_filter
                    ON reaction_filter.reaction_key = rx_filter.reaction_key_dim
                WHERE rx_filter.report_key = fr.report_key
                  AND reaction_filter.reaction_meddra_apt = ?
            )
        """)
        params.append(reaction_name)

    cte = f"""
        WITH filtered_reports AS (
            SELECT fr.report_key, fr.is_serious, d.year, d.month
            FROM dbo.fact_report fr
            JOIN dbo.dim_date d ON d.date_key = fr.date_key
            JOIN dbo.dim_country country ON country.country_key = fr.country_key
            WHERE {" AND ".join(conditions)}
        )
    """
    return cte, params


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.to_dict(orient="records")


def _with_serious_percentage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        report_count = int(row["report_count"])
        serious_count = int(row["serious_count"])
        row["report_count"] = report_count
        row["serious_count"] = serious_count
        row["serious_pct"] = (
            round(100.0 * serious_count / report_count, 2) if report_count else None
        )
    return rows


def get_reporting_summary(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    drug_name: str | None = None,
    reaction_name: str | None = None,
    country_code: str | None = None,
    serious_only: bool | None = None,
    limit: int = 100,
    fetcher: FetchDataFrame = fetch_dataframe,
) -> dict[str, Any]:
    """Return aggregate reporting analytics for the receivedate population."""
    _validate_dates(start_date, end_date)
    _validate_limit(limit)
    if serious_only is not None and not isinstance(serious_only, bool):
        raise TypeError("serious_only must be a boolean or None")

    normalized_drug = _normalize_text(drug_name, "drug_name")
    normalized_reaction = _normalize_text(reaction_name, "reaction_name")
    normalized_country = _normalize_text(country_code, "country_code")
    cte, filter_params = _filter_cte(
        start_date=start_date,
        end_date=end_date,
        drug_name=normalized_drug,
        reaction_name=normalized_reaction,
        country_code=normalized_country,
        serious_only=serious_only,
    )

    summary = fetcher(
        cte + """
            SELECT COUNT(*) AS report_count,
                   COALESCE(SUM(CAST(is_serious AS INT)), 0) AS serious_count
            FROM filtered_reports
        """,
        filter_params,
    )
    report_count = int(summary.iloc[0]["report_count"]) if not summary.empty else 0
    serious_count = int(summary.iloc[0]["serious_count"]) if not summary.empty else 0

    monthly = fetcher(
        cte + """
            SELECT year, month, COUNT(*) AS report_count,
                   COALESCE(SUM(CAST(is_serious AS INT)), 0) AS serious_count
            FROM filtered_reports
            GROUP BY year, month
            ORDER BY year, month
        """,
        filter_params,
    )
    monthly_rows = [
        {
            "year": int(row["year"]),
            "month": int(row["month"]),
            "report_count": int(row["report_count"]),
            "serious_count": int(row["serious_count"]),
        }
        for row in _records(monthly)
    ]

    top_drugs = fetcher(
        cte + """
            SELECT TOP (?) drug.drug_name,
                   COUNT(DISTINCT filtered_reports.report_key) AS report_count,
                   COUNT(DISTINCT CASE WHEN filtered_reports.is_serious = 1
                       THEN filtered_reports.report_key END) AS serious_count
            FROM filtered_reports
            JOIN dbo.fact_drug fd ON fd.report_key = filtered_reports.report_key
            JOIN dbo.dim_drug drug ON drug.drug_key = fd.drug_key_dim
            WHERE fd.is_suspect = 1
            GROUP BY drug.drug_name
            ORDER BY report_count DESC, drug.drug_name
        """,
        [*filter_params, limit],
    )
    top_reactions = fetcher(
        cte + """
            SELECT TOP (?) reaction.reaction_meddra_apt AS reaction,
                   COUNT(DISTINCT filtered_reports.report_key) AS report_count,
                   COUNT(DISTINCT CASE WHEN filtered_reports.is_serious = 1
                       THEN filtered_reports.report_key END) AS serious_count
            FROM filtered_reports
            JOIN dbo.fact_reaction rx
                ON rx.report_key = filtered_reports.report_key
            JOIN dbo.dim_reaction reaction
                ON reaction.reaction_key = rx.reaction_key_dim
            GROUP BY reaction.reaction_meddra_apt
            ORDER BY report_count DESC, reaction.reaction_meddra_apt
        """,
        [*filter_params, limit],
    )

    return {
        "filters": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "drug_name": normalized_drug,
            "reaction_name": normalized_reaction,
            "country_code": normalized_country,
            "serious_only": serious_only,
            "limit": limit,
            "reporting_date": "fact_report.date_key -> dim_date.full_date (FAERS receivedate)",
        },
        "summary": {
            "report_count": report_count,
            "serious_count": serious_count,
            "serious_pct": round(100.0 * serious_count / report_count, 2)
            if report_count
            else None,
        },
        "monthly_series": monthly_rows,
        "top_drugs": _with_serious_percentage(_records(top_drugs)),
        "top_reactions": _with_serious_percentage(_records(top_reactions)),
    }
