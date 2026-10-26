"""Stage 2: clean stg.* in-place and populate stg.quarantine + stg.data_quality_log.

Rules applied (each logged with before/after counts):
  1. date_valid     – reject reports where receivedate is NULL or not a valid YYYYMMDD
  2. date_range     – reject reports where receivedate is before 1900-01-01 or after today
  3. age_clean      – null out patientonsetage/unit where age > 120 years or age < 0
  4. weight_clean   – null out patientweight where weight <= 0 or weight > 500 (kg)
  5. dedup_version  – delete older versions, keep only MAX(safetyreportversion) per safetyreportid
  6. drug_name_map  – measure % of drug rows that resolved to an openfda generic name

Usage: .venv/Scripts/python src/clean.py
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["SQLSERVER_CONNECTION"]
RESULTS = Path(__file__).resolve().parent.parent / "results"
RESULTS.mkdir(exist_ok=True)

TODAY = date.today()
MIN_DATE = date(1900, 1, 1)

# Age unit codes → years multiplier
_AGE_TO_YEARS = {"800": 1/12, "801": 1.0, "802": 1/52.18, "803": 1/365.25, "804": 1/8766}

BATCH_ID = 2  # cleaning runs as batch 2


def _log(cur: pyodbc.Cursor, check: str, before: int, after: int, note: str = "") -> None:
    cur.execute("""
        INSERT INTO stg.data_quality_log (batch_id, check_name, before_count, after_count, note)
        VALUES (?, ?, ?, ?, ?)
    """, BATCH_ID, check, before, after, note or None)


def _quarantine(cur: pyodbc.Cursor, sid: str, sver: str, etype: str,
                code: str, detail: str, raw: str = "") -> None:
    cur.execute("""
        INSERT INTO stg.quarantine
            (safetyreportid, safetyreportversion, element_type, reason_code, reason_detail, raw_json, batch_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, sid, sver, etype, code, detail, raw or None, BATCH_ID)


def _parse_date(val: str | None) -> date | None:
    if not val or len(val) < 8:
        return None
    try:
        return datetime.strptime(val[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _age_to_years(age: str | None, unit: str | None) -> float | None:
    if not age or not unit:
        return None
    try:
        return float(age) * _AGE_TO_YEARS.get(unit, 1.0)
    except ValueError:
        return None


def clean() -> dict:
    metrics: dict = {}

    with pyodbc.connect(CONN_STR) as conn:
        conn.autocommit = False
        cur = conn.cursor()

        # ── 1 & 2: date_valid + date_range ──────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM stg.reports")
        total_before = cur.fetchone()[0]

        cur.execute("""
            SELECT safetyreportid, safetyreportversion, receivedate
            FROM stg.reports
        """)
        rows = cur.fetchall()

        bad_date_ids = []
        for r in rows:
            d = _parse_date(r.receivedate)
            if d is None:
                bad_date_ids.append((r.safetyreportid, r.safetyreportversion, "NULL_DATE",
                                     f"receivedate={r.receivedate!r}"))
            elif d < MIN_DATE or d > TODAY:
                bad_date_ids.append((r.safetyreportid, r.safetyreportversion, "DATE_OUT_OF_RANGE",
                                     f"receivedate={r.receivedate}"))

        for sid, sver, code, detail in bad_date_ids:
            _quarantine(cur, sid, sver, "report", code, detail)
            cur.execute("""
                DELETE FROM stg.reports
                WHERE safetyreportid = ? AND safetyreportversion = ?
            """, sid, sver)

        cur.execute("SELECT COUNT(*) FROM stg.reports")
        after_date = cur.fetchone()[0]
        _log(cur, "date_valid_range", total_before, after_date,
             f"Removed {len(bad_date_ids)} reports with invalid or out-of-range receivedate")
        metrics["date_rejected"] = len(bad_date_ids)
        conn.commit()

        # ── 3: age_clean ─────────────────────────────────────────────────────
        cur.execute("""
            SELECT safetyreportid, safetyreportversion, patientonsetage, patientonsetageunit
            FROM stg.reports
            WHERE patientonsetage IS NOT NULL
        """)
        age_rows = cur.fetchall()

        nulled_age = 0
        for r in age_rows:
            age_yrs = _age_to_years(r.patientonsetage, r.patientonsetageunit)
            if age_yrs is None:
                continue
            if age_yrs < 0 or age_yrs > 120:
                cur.execute("""
                    UPDATE stg.reports
                    SET patientonsetage = NULL, patientonsetageunit = NULL
                    WHERE safetyreportid = ? AND safetyreportversion = ?
                """, r.safetyreportid, r.safetyreportversion)
                _quarantine(cur, r.safetyreportid, r.safetyreportversion, "report",
                            "IMPLAUSIBLE_AGE",
                            f"age={r.patientonsetage} unit={r.patientonsetageunit} -> {age_yrs:.1f} yrs")
                nulled_age += 1

        _log(cur, "age_clean", len(age_rows), len(age_rows) - nulled_age,
             f"Nulled {nulled_age} implausible ages (< 0 or > 120 years)")
        metrics["age_nulled"] = nulled_age
        conn.commit()

        # ── 4: weight_clean ──────────────────────────────────────────────────
        cur.execute("""
            SELECT safetyreportid, safetyreportversion, patientweight
            FROM stg.reports
            WHERE patientweight IS NOT NULL
        """)
        wt_rows = cur.fetchall()

        nulled_wt = 0
        for r in wt_rows:
            try:
                w = float(r.patientweight)
            except ValueError:
                w = -1.0
            if w <= 0 or w > 500:
                cur.execute("""
                    UPDATE stg.reports SET patientweight = NULL
                    WHERE safetyreportid = ? AND safetyreportversion = ?
                """, r.safetyreportid, r.safetyreportversion)
                _quarantine(cur, r.safetyreportid, r.safetyreportversion, "report",
                            "IMPLAUSIBLE_WEIGHT", f"weight={r.patientweight}")
                nulled_wt += 1

        _log(cur, "weight_clean", len(wt_rows), len(wt_rows) - nulled_wt,
             f"Nulled {nulled_wt} implausible weights (<= 0 or > 500 kg)")
        metrics["weight_nulled"] = nulled_wt
        conn.commit()

        # ── 5: dedup_version ─────────────────────────────────────────────────
        # For each safetyreportid, keep only the row with MAX(safetyreportversion).
        cur.execute("SELECT COUNT(*) FROM stg.reports")
        before_dedup = cur.fetchone()[0]

        cur.execute("""
            DELETE r
            FROM stg.reports r
            WHERE r.safetyreportversion < (
                SELECT MAX(r2.safetyreportversion)
                FROM stg.reports r2
                WHERE r2.safetyreportid = r.safetyreportid
            )
        """)
        dedup_deleted = cur.rowcount

        cur.execute("SELECT COUNT(*) FROM stg.reports")
        after_dedup = cur.fetchone()[0]
        _log(cur, "dedup_version", before_dedup, after_dedup,
             f"Removed {dedup_deleted} older-version duplicates")
        metrics["dedup_deleted"] = dedup_deleted
        conn.commit()

        # Cascade-delete orphaned drug/reaction rows
        cur.execute("""
            DELETE FROM stg.drugs
            WHERE NOT EXISTS (
                SELECT 1 FROM stg.reports r
                WHERE r.safetyreportid = stg.drugs.safetyreportid
                  AND r.safetyreportversion = stg.drugs.safetyreportversion
            )
        """)
        orphan_drugs = cur.rowcount
        cur.execute("""
            DELETE FROM stg.reactions
            WHERE NOT EXISTS (
                SELECT 1 FROM stg.reports r
                WHERE r.safetyreportid = stg.reactions.safetyreportid
                  AND r.safetyreportversion = stg.reactions.safetyreportversion
            )
        """)
        orphan_rxns = cur.rowcount
        metrics["orphan_drugs_deleted"] = orphan_drugs
        metrics["orphan_reactions_deleted"] = orphan_rxns
        conn.commit()

        # ── 6: drug_name_map rate ────────────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM stg.drugs")
        total_drugs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM stg.drugs WHERE openfda_generic_name IS NOT NULL")
        mapped_drugs = cur.fetchone()[0]
        pct_mapped = round(100.0 * mapped_drugs / total_drugs, 1) if total_drugs else 0
        _log(cur, "drug_name_map", total_drugs, mapped_drugs,
             f"{pct_mapped}% of drug rows have openfda_generic_name")
        metrics["drug_rows_total"] = total_drugs
        metrics["drug_rows_openfda_mapped"] = mapped_drugs
        metrics["drug_openfda_pct"] = pct_mapped
        conn.commit()

        # ── final counts ─────────────────────────────────────────────────────
        for tbl in ["stg.reports", "stg.drugs", "stg.reactions",
                    "stg.quarantine", "stg.data_quality_log"]:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            metrics[tbl.replace(".", "_")] = cur.fetchone()[0]

        # ── missingness on key columns ───────────────────────────────────────
        miss_cols = ["patientsex", "patientonsetage", "patientweight",
                     "primarysourcecountry", "occurcountry", "companynumb"]
        cur.execute(f"SELECT COUNT(*) FROM stg.reports")
        n = cur.fetchone()[0]
        missing = {}
        for col in miss_cols:
            cur.execute(f"SELECT COUNT(*) FROM stg.reports WHERE {col} IS NULL")
            null_n = cur.fetchone()[0]
            missing[col] = {"null_count": null_n, "null_pct": round(100.0 * null_n / n, 1) if n else 0}
        metrics["missingness"] = missing
        metrics["final_report_count"] = n

    (RESULTS / "data_quality.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    m = clean()
    print(f"Stage 2 cleaning complete:")
    print(f"  Reports:       {m['stg_reports']:,}  (removed {m['date_rejected']} bad-date, {m['dedup_deleted']} older-version)")
    print(f"  Age nulled:    {m['age_nulled']}")
    print(f"  Weight nulled: {m['weight_nulled']}")
    print(f"  Orphan drugs/reactions removed: {m['orphan_drugs_deleted']}/{m['orphan_reactions_deleted']}")
    print(f"  Drug openfda map rate: {m['drug_openfda_pct']}%")
    print(f"  Quarantine rows: {m['stg_quarantine']:,}")
    print(f"\nMissingness (post-clean):")
    for col, v in m["missingness"].items():
        print(f"  {col}: {v['null_pct']}% null ({v['null_count']:,}/{m['final_report_count']:,})")
