from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import pandas as pd

from services.db import fetch_dataframe
from src.signal_analysis import calculate_signal

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


def _validate_nonnegative_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validate_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    if field_name == "limit" and value > MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")


def _signal_query(
    *,
    start_date: date | None,
    end_date: date | None,
    drug_name: str | None,
    reaction_name: str | None,
    country_code: str | None,
    serious_only: bool | None,
    min_pair_count: int,
    limit: int,
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

    candidate_conditions = ["pair_count >= ?"]
    candidate_params: list[object] = [min_pair_count]
    if drug_name is not None:
        candidate_conditions.append("d.drug_name = ?")
        candidate_params.append(drug_name)
    if reaction_name is not None:
        candidate_conditions.append("r.reaction_meddra_apt = ?")
        candidate_params.append(reaction_name)

    sql = f"""
        WITH filtered_reports AS (
            SELECT fr.report_key
            FROM dbo.fact_report fr
            JOIN dbo.dim_date d ON d.date_key = fr.date_key
            JOIN dbo.dim_country country ON country.country_key = fr.country_key
            WHERE {" AND ".join(conditions)}
        ),
        suspect AS (
            SELECT DISTINCT fd.report_key, fd.drug_key_dim
            FROM dbo.fact_drug fd
            JOIN filtered_reports fr ON fr.report_key = fd.report_key
            WHERE fd.is_suspect = 1
        ),
        reactions AS (
            SELECT DISTINCT rx.report_key, rx.reaction_key_dim
            FROM dbo.fact_reaction rx
            JOIN filtered_reports fr ON fr.report_key = rx.report_key
        ),
        pair_counts AS (
            SELECT s.drug_key_dim, rx.reaction_key_dim,
                   COUNT(DISTINCT s.report_key) AS pair_count
            FROM suspect s
            JOIN reactions rx ON rx.report_key = s.report_key
            GROUP BY s.drug_key_dim, rx.reaction_key_dim
        ),
        drug_totals AS (
            SELECT drug_key_dim, COUNT(DISTINCT report_key) AS drug_total
            FROM suspect
            GROUP BY drug_key_dim
        ),
        reaction_totals AS (
            SELECT reaction_key_dim, COUNT(DISTINCT report_key) AS reaction_total
            FROM reactions
            GROUP BY reaction_key_dim
        )
        SELECT TOP (?)
               d.drug_key,
               r.reaction_key,
               d.drug_name,
               r.reaction_meddra_apt AS reaction,
               pc.pair_count,
               dt.drug_total,
               rt.reaction_total,
               (SELECT COUNT(*) FROM filtered_reports) AS total_reports
        FROM pair_counts pc
        JOIN dbo.dim_drug d ON d.drug_key = pc.drug_key_dim
        JOIN dbo.dim_reaction r ON r.reaction_key = pc.reaction_key_dim
        JOIN drug_totals dt ON dt.drug_key_dim = pc.drug_key_dim
        JOIN reaction_totals rt ON rt.reaction_key_dim = pc.reaction_key_dim
        WHERE {" AND ".join(candidate_conditions)}
        ORDER BY pc.pair_count DESC, d.drug_name, r.reaction_meddra_apt
    """
    return sql, [*params, limit, *candidate_params]


def explore_signals(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    drug_name: str | None = None,
    reaction_name: str | None = None,
    country_code: str | None = None,
    serious_only: bool | None = None,
    min_pair_count: int = 3,
    min_prr: float = 2.0,
    min_chi_square: float = 4.0,
    limit: int = 100,
    fetcher: FetchDataFrame = fetch_dataframe,
) -> dict[str, Any]:
    """Return aggregate drug-reaction signals for one filtered report population."""
    _validate_dates(start_date, end_date)
    _validate_integer(min_pair_count, "min_pair_count")
    _validate_integer(limit, "limit")
    _validate_nonnegative_number(min_prr, "min_prr")
    _validate_nonnegative_number(min_chi_square, "min_chi_square")
    if serious_only is not None and not isinstance(serious_only, bool):
        raise TypeError("serious_only must be a boolean or None")

    normalized_drug = _normalize_text(drug_name, "drug_name")
    normalized_reaction = _normalize_text(reaction_name, "reaction_name")
    normalized_country = _normalize_text(country_code, "country_code")
    sql, params = _signal_query(
        start_date=start_date,
        end_date=end_date,
        drug_name=normalized_drug,
        reaction_name=normalized_reaction,
        country_code=normalized_country,
        serious_only=serious_only,
        min_pair_count=min_pair_count,
        limit=limit,
    )
    frame = fetcher(sql, params)
    if frame.empty:
        return {
            "filters": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "drug_name": normalized_drug,
                "reaction_name": normalized_reaction,
                "country_code": normalized_country,
                "serious_only": serious_only,
            },
            "total_reports": 0,
            "candidate_count": 0,
            "signal_count": 0,
            "signals": [],
        }

    total_reports = int(frame.iloc[0]["total_reports"])
    signals: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        metrics = calculate_signal(
            int(row.pair_count),
            int(row.drug_total),
            int(row.reaction_total),
            total_reports,
        )
        if (
            metrics.prr is None
            or metrics.prr < min_prr
            or metrics.chi_square is None
            or metrics.chi_square < min_chi_square
        ):
            continue
        signals.append({
            "drug_name": row.drug_name,
            "reaction": row.reaction,
            "pair_count": metrics.a,
            "drug_total": row.drug_total,
            "reaction_total": row.reaction_total,
            "total_reports": total_reports,
            "prr": metrics.prr,
            "prr_lower_95": metrics.prr_lower_95,
            "prr_upper_95": metrics.prr_upper_95,
            "ror": metrics.ror,
            "ror_lower_95": metrics.ror_lower_95,
            "ror_upper_95": metrics.ror_upper_95,
            "chi_square": metrics.chi_square,
        })

    signals.sort(
        key=lambda row: (row["chi_square"], row["prr"], row["pair_count"]),
        reverse=True,
    )
    return {
        "filters": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "drug_name": normalized_drug,
            "reaction_name": normalized_reaction,
            "country_code": normalized_country,
            "serious_only": serious_only,
        },
        "total_reports": total_reports,
        "candidate_count": len(frame),
        "signal_count": len(signals),
        "screening": {
            "minimum_pair_count": min_pair_count,
            "minimum_prr": min_prr,
            "minimum_chi_square": min_chi_square,
        },
        "signals": signals,
    }
