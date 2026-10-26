"""Stage 6 disproportionality signal calculations.

The analysis unit is a report. Suspect-drug/reaction pair counts are supplied
by dbo.vw_drug_reaction_pairs; this module calculates the 2x2 statistics and
optionally writes screened results/signals.json.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "signals.json"
Z = 1.96


@dataclass(frozen=True)
class SignalMetrics:
    a: int
    b: int
    c: int
    d: int
    prr: float | None
    prr_lower_95: float | None
    prr_upper_95: float | None
    ror: float | None
    ror_lower_95: float | None
    ror_upper_95: float | None
    chi_square: float | None


def _log_ci(value: float, standard_error: float) -> tuple[float, float]:
    centre = math.log(value)
    return math.exp(centre - Z * standard_error), math.exp(centre + Z * standard_error)


def calculate_signal(
    pair_count: int,
    drug_total: int,
    reaction_total: int,
    total_reports: int,
) -> SignalMetrics:
    """Calculate PRR, ROR, 95% CIs, and Yates-corrected chi-square.

    The cells are:
      a = reports with the drug and reaction
      b = reports with the drug and not the reaction
      c = reports with the reaction and not the drug
      d = reports with neither
    """
    a = pair_count
    b = drug_total - a
    c = reaction_total - a
    d = total_reports - drug_total - reaction_total + a
    cells = (a, b, c, d)
    if total_reports <= 0 or any(cell < 0 for cell in cells):
        raise ValueError(f"Invalid 2x2 table: {cells}, total_reports={total_reports}")

    prr = None
    prr_ci = (None, None)
    if a > 0 and drug_total > 0 and c > 0 and total_reports > drug_total:
        prr = (a / drug_total) / (c / (total_reports - drug_total))
        prr_se = math.sqrt(1 / a - 1 / drug_total + 1 / c - 1 / (total_reports - drug_total))
        prr_ci = _log_ci(prr, prr_se)

    ror = None
    ror_ci = (None, None)
    if a > 0 and b > 0 and c > 0 and d > 0:
        ror = (a * d) / (b * c)
        ror_se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
        ror_ci = _log_ci(ror, ror_se)

    chi_square = None
    expected_total = a + b + c + d
    if expected_total > 0:
        numerator = abs(a * d - b * c) - expected_total / 2
        chi_square = max(0.0, expected_total * numerator**2 / (
            (a + b) * (c + d) * (a + c) * (b + d)
        )) if all(value > 0 for value in (a + b, c + d, a + c, b + d)) else None

    return SignalMetrics(
        a=a,
        b=b,
        c=c,
        d=d,
        prr=prr,
        prr_lower_95=prr_ci[0],
        prr_upper_95=prr_ci[1],
        ror=ror,
        ror_lower_95=ror_ci[0],
        ror_upper_95=ror_ci[1],
        chi_square=chi_square,
    )


def _row_to_signal(row: Any, metrics: SignalMetrics) -> dict[str, Any]:
    result = {
        "drug_key": row.drug_key,
        "reaction_key": row.reaction_key,
        "drug_name": row.drug_name,
        "reaction": row.reaction_meddra_apt,
        "pair_count": row.pair_count,
        "drug_total": row.drug_total,
        "reaction_total": row.reaction_total,
        **asdict(metrics),
    }
    return result


def run(top_drugs: int = 100, min_pair_count: int = 3) -> dict[str, Any]:
    """Compute signals for the top suspect drugs and apply screening criteria."""
    load_dotenv()
    connection_string = os.environ["SQLSERVER_CONNECTION"]
    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.fact_report")
        total_reports = cursor.fetchone()[0]
        cursor.execute("""
            SELECT TOP (?) drug_key_dim, COUNT(DISTINCT report_key) AS drug_total
            FROM dbo.fact_drug
            WHERE is_suspect = 1
            GROUP BY drug_key_dim
            ORDER BY drug_total DESC, drug_key_dim
        """, top_drugs)
        drug_keys = [row.drug_key_dim for row in cursor.fetchall()]
        if not drug_keys:
            raise RuntimeError("No suspect drugs were found in dbo.fact_drug")

        placeholders = ",".join("?" for _ in drug_keys)
        cursor.execute(f"""
            SELECT drug_key, reaction_key, drug_name, reaction_meddra_apt,
                   pair_count, drug_total, reaction_total
            FROM dbo.vw_drug_reaction_pairs
            WHERE drug_key IN ({placeholders}) AND pair_count >= ?
        """, *drug_keys, min_pair_count)
        candidates = cursor.fetchall()

    all_signals = [
        _row_to_signal(row, calculate_signal(
            row.pair_count, row.drug_total, row.reaction_total, total_reports
        ))
        for row in candidates
    ]
    screened = [
        row for row in all_signals
        if row["prr"] is not None
        and row["prr"] >= 2
        and row["chi_square"] is not None
        and row["chi_square"] >= 4
    ]
    screened.sort(key=lambda row: (row["chi_square"], row["prr"]), reverse=True)
    output = {
        "analysis_unit": "report",
        "total_reports": total_reports,
        "top_drugs_limit": top_drugs,
        "minimum_pair_count": min_pair_count,
        "screening": {"pair_count": f">={min_pair_count}", "prr": ">=2", "chi_square": ">=4"},
        "candidate_count": len(all_signals),
        "signal_count": len(screened),
        "signals": screened,
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate FAERS PRR/ROR signals.")
    parser.add_argument("--top-drugs", type=int, default=100)
    parser.add_argument("--min-pair-count", type=int, default=3)
    args = parser.parse_args()
    output = run(args.top_drugs, args.min_pair_count)
    print(f"signal.py: {output['signal_count']} screened signals from {output['candidate_count']} candidates")


if __name__ == "__main__":
    main()
