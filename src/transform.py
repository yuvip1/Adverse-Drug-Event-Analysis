"""Stage 2: transform stg.* → dbo.dim_* → dbo.fact_*

Usage: .venv/Scripts/python src/transform.py
"""
from __future__ import annotations

import os
from datetime import date, datetime

import pyodbc
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["SQLSERVER_CONNECTION"]


def _parse_date(val: str | None) -> date | None:
    if not val or len(val) < 8:
        return None
    try:
        return datetime.strptime(val[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _parse_float(val: str | None) -> float | None:
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


_AGE_TO_YEARS = {"800": 1/12, "801": 1.0, "802": 1/52.18, "803": 1/365.25, "804": 1/8766}

def _age_to_years(age: str | None, unit: str | None) -> float | None:
    if not age or not unit:
        return None
    try:
        return round(float(age) * _AGE_TO_YEARS.get(unit, 1.0), 2)
    except ValueError:
        return None


_AGE_GROUPS = [
    (-1, "UNK", "Unknown",     None, None),
    ( 1, "N",   "Neonate",     0,    1),
    ( 2, "I",   "Infant",      1,    2),
    ( 3, "C",   "Child",       2,    11),
    ( 4, "A",   "Adolescent",  12,   17),
    ( 5, "ADU", "Adult",       18,   64),
    ( 6, "E",   "Elderly",     65,   None),
]


def _get_or_create_date(cur: pyodbc.Cursor, cache: dict, d: date | None) -> int:
    if d is None:
        return -1
    if d in cache:
        return cache[d]
    cur.execute("SELECT date_key FROM dbo.dim_date WHERE full_date = ?", d)
    row = cur.fetchone()
    if row:
        cache[d] = row[0]
        return row[0]
    cur.execute("""
        INSERT INTO dbo.dim_date (full_date, year, quarter, month, month_name, day_of_week, is_weekend)
        OUTPUT INSERTED.date_key
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, d, d.year, (d.month - 1) // 3 + 1, d.month,
        d.strftime("%B"), d.isoweekday(), 1 if d.isoweekday() >= 6 else 0)
    key = cur.fetchone()[0]
    cache[d] = key
    return key


def _get_or_create_country(cur: pyodbc.Cursor, cache: dict, code: str | None) -> int:
    iso = (code or "XX").upper()[:2]
    if iso in cache:
        return cache[iso]
    cur.execute("SELECT country_key FROM dbo.dim_country WHERE iso2_code = ?", iso)
    row = cur.fetchone()
    if row:
        cache[iso] = row[0]
        return row[0]
    cur.execute("""
        INSERT INTO dbo.dim_country (iso2_code, country_name)
        OUTPUT INSERTED.country_key
        VALUES (?, ?)
    """, iso, iso if iso != "XX" else "Unknown")
    key = cur.fetchone()[0]
    cache[iso] = key
    return key


def _get_or_create_drug(cur: pyodbc.Cursor, cache: dict, row) -> int:
    raw = row.openfda_generic_name or row.activesubstancename or row.medicinalproduct or "UNKNOWN"
    name = raw.strip().upper()[:512]
    if name in cache:
        return cache[name]
    cur.execute("SELECT drug_key FROM dbo.dim_drug WHERE drug_name = ?", name)
    r = cur.fetchone()
    if r:
        cache[name] = r[0]
        return r[0]
    cur.execute("""
        INSERT INTO dbo.dim_drug
            (drug_name, generic_name, substance_name, brand_name, manufacturer_name,
             dosage_form, route, is_suspect)
        OUTPUT INSERTED.drug_key
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, name,
        (row.openfda_generic_name or "").strip().upper() or None,
        (row.activesubstancename or "").strip().upper() or None,
        (row.openfda_brand_name or "").strip().upper() or None,
        (row.openfda_manufacturer_name or "").strip() or None,
        (row.drugdosageform or "").strip() or None,
        (row.drugadministrationroute or "").strip() or None,
        1 if row.drugcharacterization == "1" else 0)
    key = cur.fetchone()[0]
    cache[name] = key
    return key


def _get_or_create_reaction(cur: pyodbc.Cursor, cache: dict, meddra_pt: str | None) -> int:
    name = (meddra_pt or "UNKNOWN").strip().upper()
    if name in cache:
        return cache[name]
    cur.execute("SELECT reaction_key FROM dbo.dim_reaction WHERE reaction_meddra_apt = ?", name)
    r = cur.fetchone()
    if r:
        cache[name] = r[0]
        return r[0]
    cur.execute("""
        INSERT INTO dbo.dim_reaction (reaction_meddra_apt)
        OUTPUT INSERTED.reaction_key
        VALUES (?)
    """, name)
    key = cur.fetchone()[0]
    cache[name] = key
    return key


def _get_or_create_reporter(cur: pyodbc.Cursor, cache: dict, row) -> int:
    key_tuple = (
        row.sender_sendertype or "",
        (row.sender_senderorganization or "")[:255],
        row.primarysource_reportercountry or "",
        row.primarysource_qualification or "",
    )
    if key_tuple in cache:
        return cache[key_tuple]
    cur.execute("""
        SELECT reporter_key FROM dbo.dim_reporter
        WHERE reporter_type_code = ? AND organization = ? AND country = ? AND qualification = ?
    """, *key_tuple)
    r = cur.fetchone()
    if r:
        cache[key_tuple] = r[0]
        return r[0]
    cur.execute("""
        INSERT INTO dbo.dim_reporter (reporter_type_code, organization, country, qualification)
        OUTPUT INSERTED.reporter_key
        VALUES (?, ?, ?, ?)
    """, *key_tuple)
    key = cur.fetchone()[0]
    cache[key_tuple] = key
    return key


def transform() -> dict[str, int]:
    with pyodbc.connect(CONN_STR) as conn:
        conn.autocommit = False
        cur = conn.cursor()   # bulk inserts only
        dim = conn.cursor()   # dim lookups/inserts

        # ── Clear in FK order (DELETE because FKs block TRUNCATE) ────────────
        for tbl in ["dbo.fact_reaction", "dbo.fact_drug", "dbo.fact_report",
                    "dbo.dim_drug", "dbo.dim_reaction", "dbo.dim_reporter",
                    "dbo.dim_date", "dbo.dim_country", "dbo.dim_age_group"]:
            cur.execute(f"DELETE FROM {tbl}")
        conn.commit()

        # ── dim_age_group: static lookup (IDENTITY_INSERT to set keys) ───────
        cur.execute("SET IDENTITY_INSERT dbo.dim_age_group ON")
        for row in _AGE_GROUPS:
            cur.execute("""
                INSERT INTO dbo.dim_age_group
                    (age_group_key, age_group_code, age_group_label, age_min_years, age_max_years)
                VALUES (?, ?, ?, ?, ?)
            """, *row)
        cur.execute("SET IDENTITY_INSERT dbo.dim_age_group OFF")

        # ── Sentinel rows ────────────────────────────────────────────────────
        cur.execute("SET IDENTITY_INSERT dbo.dim_date ON")
        cur.execute("""
            INSERT INTO dbo.dim_date
                (date_key, full_date, year, quarter, month, month_name, day_of_week, is_weekend)
            VALUES (-1, '1900-01-01', 1900, 1, 1, 'January', 1, 0)
        """)
        cur.execute("SET IDENTITY_INSERT dbo.dim_date OFF")

        cur.execute("SET IDENTITY_INSERT dbo.dim_country ON")
        cur.execute("""
            INSERT INTO dbo.dim_country (country_key, iso2_code, country_name)
            VALUES (-1, 'XX', 'Unknown')
        """)
        cur.execute("SET IDENTITY_INSERT dbo.dim_country OFF")
        conn.commit()

        # ── Caches ───────────────────────────────────────────────────────────
        date_cache: dict = {None: -1}
        country_cache: dict = {"XX": -1}
        drug_cache: dict = {}
        reaction_cache: dict = {}
        reporter_cache: dict = {}
        age_map = {str(code): key for key, code, *_ in _AGE_GROUPS}

        # ── Build fact_report rows (dim lookups on `dim` cursor) ─────────────
        cur.execute("""
            SELECT safetyreportid, safetyreportversion, reporttype, serious, duplicate,
                   receivedate, receiptdate, transmissiondate,
                   primarysourcecountry, occurcountry,
                   sender_sendertype, sender_senderorganization,
                   primarysource_reportercountry, primarysource_qualification,
                   patientagegroup, patientsex, patientonsetage, patientonsetageunit,
                   patientweight, companynumb
            FROM stg.reports
        """)
        reports = cur.fetchall()

        fact_report_rows = []
        for r in reports:
            dk  = _get_or_create_date(dim, date_cache, _parse_date(r.receivedate))
            rdk = _get_or_create_date(dim, date_cache, _parse_date(r.receiptdate))
            tdk = _get_or_create_date(dim, date_cache, _parse_date(r.transmissiondate))
            ck  = _get_or_create_country(dim, country_cache, r.primarysourcecountry)
            ock = _get_or_create_country(dim, country_cache, r.occurcountry)
            repk = _get_or_create_reporter(dim, reporter_cache, r)
            agk = age_map.get(str(r.patientagegroup or ""), -1)
            fact_report_rows.append((
                r.safetyreportid, r.safetyreportversion,
                r.reporttype,
                1 if r.serious == "1" else 0,
                1 if r.duplicate == "1" else 0,
                dk, rdk, dk, tdk,
                ck, ock, repk, agk,
                r.patientsex,
                _age_to_years(r.patientonsetage, r.patientonsetageunit),
                _parse_float(r.patientweight),
                r.companynumb,
            ))

        cur.fast_executemany = True
        cur.executemany("""
            INSERT INTO dbo.fact_report
                (safetyreportid, safetyreportversion, report_type, is_serious, is_duplicate,
                 date_key, receipt_date_key, receive_date_key, transmission_date_key,
                 country_key, occur_country_key, reporter_key, age_group_key,
                 sex_code, onset_age_years, weight_kg, companynumb)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, fact_report_rows)
        cur.fast_executemany = False
        conn.commit()

        # Build report_key_map after insert
        cur.execute("SELECT report_key, safetyreportid, safetyreportversion FROM dbo.fact_report")
        report_key_map = {(sid, sver): rk for rk, sid, sver in cur.fetchall()}

        # ── fact_drug ────────────────────────────────────────────────────────
        cur.execute("""
            SELECT safetyreportid, safetyreportversion, medicinalproduct,
                   drugcharacterization, drugauthorizationnumb, drugindication,
                   drugdosageform, drugadministrationroute,
                   activesubstancename, openfda_brand_name, openfda_generic_name,
                   openfda_manufacturer_name
            FROM stg.drugs
        """)
        drug_rows = cur.fetchall()

        fact_drug_batch = []
        for d in drug_rows:
            rk = report_key_map.get((d.safetyreportid, d.safetyreportversion))
            if rk is None:
                continue
            dk = _get_or_create_drug(dim, drug_cache, d)
            fact_drug_batch.append((
                d.safetyreportid, d.safetyreportversion, rk, dk,
                1 if d.drugcharacterization == "1" else 0,
                d.drugcharacterization, d.drugauthorizationnumb, d.drugindication,
            ))

        cur.fast_executemany = True
        cur.executemany("""
            INSERT INTO dbo.fact_drug
                (safetyreportid, safetyreportversion, report_key, drug_key_dim,
                 is_suspect, drugcharacterization, drugauthorizationnumb, drugindication)
            VALUES (?,?,?,?,?,?,?,?)
        """, fact_drug_batch)
        cur.fast_executemany = False
        conn.commit()

        # ── fact_reaction ────────────────────────────────────────────────────
        cur.execute("""
            SELECT safetyreportid, safetyreportversion, reactionmeddrapt, reactionoutcome
            FROM stg.reactions
        """)
        rxn_rows = cur.fetchall()

        fact_rxn_batch = []
        for rx in rxn_rows:
            rk = report_key_map.get((rx.safetyreportid, rx.safetyreportversion))
            if rk is None:
                continue
            rxk = _get_or_create_reaction(dim, reaction_cache, rx.reactionmeddrapt)
            fact_rxn_batch.append((
                rx.safetyreportid, rx.safetyreportversion, rk, rxk, rx.reactionoutcome,
            ))

        cur.fast_executemany = True
        cur.executemany("""
            INSERT INTO dbo.fact_reaction
                (safetyreportid, safetyreportversion, report_key, reaction_key_dim, outcome_code)
            VALUES (?,?,?,?,?)
        """, fact_rxn_batch)
        conn.commit()

        # ── row counts ───────────────────────────────────────────────────────
        counts = {}
        for tbl in ["dbo.dim_date", "dbo.dim_country", "dbo.dim_age_group",
                    "dbo.dim_drug", "dbo.dim_reaction", "dbo.dim_reporter",
                    "dbo.fact_report", "dbo.fact_drug", "dbo.fact_reaction"]:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            counts[tbl] = cur.fetchone()[0]
        return counts


if __name__ == "__main__":
    counts = transform()
    print("Transform complete:")
    for tbl, n in counts.items():
        print(f"  {tbl}: {n:,}")
