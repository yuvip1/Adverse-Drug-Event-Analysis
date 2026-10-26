# Cycle-time analysis: date lags between receive/receipt/transmission
# Operational-excellence metric (Lean/Opex) per the roadmap.
# Outputs results/cycle_time.json
import json, os
from pathlib import Path
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CS = os.environ["SQLSERVER_CONNECTION"]
OUT = Path(__file__).resolve().parent.parent / "results" / "cycle_time.json"

def q(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

with pyodbc.connect(CS) as conn:
    cur = conn.cursor()

    # Overall lag stats: receivedate → receiptdate, by year
    # Dates stored as YYYYMMDD strings in stg.reports; use dim_date for clean dates.
    # receive_date_key and receipt_date_key are in fact_report joined to dim_date.
    overall = q(cur, """
        SELECT
            dd_recv.year                                                AS year,
            COUNT(*)                                                    AS report_count,
            AVG(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))    AS avg_recv_to_rcpt_days,
            -- P50 via percentile_cont is not available in T-SQL without window; use AVG as proxy
            MIN(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))    AS min_lag_days,
            MAX(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))    AS max_lag_days,
            -- P90 approximation: count rows with lag <= nth percentile cutoff would need subquery;
            -- store raw for Python-side percentile instead
            STDEV(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))  AS stdev_lag_days
        FROM dbo.fact_report fr
        JOIN dbo.dim_date dd_recv ON fr.receive_date_key  = dd_recv.date_key
        JOIN dbo.dim_date dd_rcpt ON fr.receipt_date_key  = dd_rcpt.date_key
        WHERE dd_recv.date_key <> -1 AND dd_rcpt.date_key <> -1
          AND dd_recv.full_date >= '1990-01-01'
          AND dd_rcpt.full_date >= '1990-01-01'
        GROUP BY dd_recv.year
        ORDER BY dd_recv.year
    """)

    # Lag by reporter type (sender_sendertype via dim_reporter)
    by_reporter = q(cur, """
        SELECT
            ISNULL(rp.reporter_type_code, 'unknown')                    AS reporter_type,
            COUNT(*)                                                     AS report_count,
            AVG(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))     AS avg_recv_to_rcpt_days,
            MIN(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))     AS min_lag_days,
            MAX(DATEDIFF(day, dd_recv.full_date, dd_rcpt.full_date))     AS max_lag_days
        FROM dbo.fact_report fr
        JOIN dbo.dim_date     dd_recv ON fr.receive_date_key = dd_recv.date_key
        JOIN dbo.dim_date     dd_rcpt ON fr.receipt_date_key = dd_rcpt.date_key
        JOIN dbo.dim_reporter rp      ON fr.reporter_key     = rp.reporter_key
        WHERE dd_recv.date_key <> -1 AND dd_rcpt.date_key <> -1
          AND dd_recv.full_date >= '1990-01-01'
          AND dd_rcpt.full_date >= '1990-01-01'
        GROUP BY rp.reporter_type_code
        ORDER BY avg_recv_to_rcpt_days DESC
    """)

    # Receipt → transmission lag (FDA processing time proxy)
    rcpt_to_trans = q(cur, """
        SELECT
            dd_rcpt.year                                                AS year,
            COUNT(*)                                                    AS report_count,
            AVG(DATEDIFF(day, dd_rcpt.full_date, dd_trans.full_date))   AS avg_rcpt_to_trans_days
        FROM dbo.fact_report fr
        JOIN dbo.dim_date dd_rcpt  ON fr.receipt_date_key       = dd_rcpt.date_key
        JOIN dbo.dim_date dd_trans ON fr.transmission_date_key  = dd_trans.date_key
        WHERE dd_rcpt.date_key  <> -1 AND dd_trans.date_key <> -1
          AND dd_rcpt.full_date  >= '1990-01-01'
          AND dd_trans.full_date >= '1990-01-01'
        GROUP BY dd_rcpt.year
        ORDER BY dd_rcpt.year
    """)

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps({
    "receive_to_receipt_by_year": overall,
    "receive_to_receipt_by_reporter": by_reporter,
    "receipt_to_transmission_by_year": rcpt_to_trans,
}, indent=2))

total_rows = len(overall) + len(by_reporter) + len(rcpt_to_trans)
print(f"cycle_time.py: {total_rows} result rows saved to {OUT}")
if overall:
    avg_all = sum(r["avg_recv_to_rcpt_days"] or 0 for r in overall) / len(overall)
    print(f"  Overall avg receive->receipt lag across years: {avg_all:.1f} days")
