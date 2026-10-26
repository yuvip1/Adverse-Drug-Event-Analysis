# Monthly trend + linear fit + receipt-to-receive lag → results/trend.json
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CS = os.environ["SQLSERVER_CONNECTION"]
OUT = Path(__file__).resolve().parent.parent / "results" / "trend.json"

with pyodbc.connect(CS) as conn:
    cur = conn.cursor()

    cur.execute("""
        SELECT d.year, d.month, COUNT(*) AS total_count,
               SUM(CAST(fr.is_serious AS INT)) AS serious_count
        FROM dbo.fact_report fr JOIN dbo.dim_date d ON fr.date_key = d.date_key
        WHERE d.date_key <> -1
        GROUP BY d.year, d.month ORDER BY d.year, d.month
    """)
    observed = {(r[0], r[1]): {"total_count": r[2], "serious_count": r[3] or 0} for r in cur.fetchall()}

    # Receipt-to-receive lag from stg.reports (already loaded strings)
    cur.execute("SELECT receiptdate, receivedate FROM stg.reports WHERE receiptdate IS NOT NULL AND receivedate IS NOT NULL")
    lags = []
    for receipt, receive in cur.fetchall():
        try:
            d1 = datetime.strptime(receipt[:8], "%Y%m%d")
            d2 = datetime.strptime(receive[:8], "%Y%m%d")
            delta = (d2 - d1).days
            if -3650 < delta < 3650:  # sanity: ±10 years
                lags.append(delta)
        except ValueError:
            pass
    avg_lag = round(sum(lags) / len(lags), 1) if lags else None

first_year, first_month = min(observed)
last_year, last_month = max(observed)
monthly = []
year, month = first_year, first_month
while (year, month) <= (last_year, last_month):
    values = observed.get((year, month), {"total_count": 0, "serious_count": 0})
    monthly.append({
        "year": year,
        "month": month,
        "count": values["total_count"],
        "total_count": values["total_count"],
        "serious_count": values["serious_count"],
    })
    month += 1
    if month == 13:
        month = 1
        year += 1

xs = list(range(len(monthly)))
ys = [m["count"] for m in monthly]
coeffs = np.polyfit(xs, ys, 1).tolist() if len(xs) >= 2 else [0, 0]

OUT.write_text(json.dumps({
    "monthly_series": monthly,
    "series_definition": {
        "total": "All reports grouped by date_key month",
        "serious": "Reports where fact_report.is_serious = 1 grouped by date_key month",
        "missing_months": "Inserted as zero between the first and last observed month",
    },
    "polyfit_coefficients": coeffs,  # [slope, intercept]
    "avg_receipt_to_receive_lag_days": avg_lag,
}, indent=2))

print(f"trend.py: {len(monthly)} months, slope={coeffs[0]:.1f} reports/month, avg lag={avg_lag} days")
for m in monthly:
    print(f"  {m['year']}-{m['month']:02d}: {m['count']} total, {m['serious_count']} serious")
