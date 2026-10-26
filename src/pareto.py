# Pareto (80/20) analysis for drugs and reactions → results/pareto.json
import json, os
from pathlib import Path
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CS = os.environ["SQLSERVER_CONNECTION"]
OUT = Path(__file__).resolve().parent.parent / "results" / "pareto.json"

def pareto(rows, count_key):
    total = sum(r[count_key] for r in rows)
    cum = 0
    result = []
    cutoff = None
    for i, r in enumerate(rows):
        cum += r[count_key]
        pct = round(cum / total * 100, 2)
        result.append({**r, "cumulative_pct": pct})
        if cutoff is None and pct >= 80:
            cutoff = i + 1
    return result, cutoff

with pyodbc.connect(CS) as conn:
    cur = conn.cursor()

    cur.execute("""
        SELECT d.drug_name, COUNT(*) AS report_count
        FROM dbo.fact_drug fd JOIN dbo.dim_drug d ON fd.drug_key_dim = d.drug_key
        WHERE fd.is_suspect = 1
        GROUP BY d.drug_name ORDER BY report_count DESC
    """)
    drug_rows = [{"drug_name": r[0], "report_count": r[1]} for r in cur.fetchall()]

    cur.execute("""
        SELECT r.reaction_meddra_apt, COUNT(*) AS report_count
        FROM dbo.fact_reaction fr JOIN dbo.dim_reaction r ON fr.reaction_key_dim = r.reaction_key
        GROUP BY r.reaction_meddra_apt ORDER BY report_count DESC
    """)
    rxn_rows = [{"reaction": r[0], "report_count": r[1]} for r in cur.fetchall()]

    cur.execute("""
        SELECT ISNULL(d.manufacturer_name, 'unknown') AS manufacturer_name,
               COUNT(DISTINCT fd.report_key) AS report_count
        FROM dbo.fact_drug fd JOIN dbo.dim_drug d ON fd.drug_key_dim = d.drug_key
        WHERE fd.is_suspect = 1
        GROUP BY d.manufacturer_name ORDER BY report_count DESC
    """)
    mfr_rows = [{"manufacturer_name": r[0], "report_count": r[1]} for r in cur.fetchall()]

drug_pareto, drug_cutoff = pareto(drug_rows, "report_count")
rxn_pareto, rxn_cutoff = pareto(rxn_rows, "report_count")
mfr_pareto, mfr_cutoff = pareto(mfr_rows, "report_count")

OUT.write_text(json.dumps({
    "drugs": drug_pareto,
    "reactions": rxn_pareto,
    "manufacturers": mfr_pareto,
    "drugs_80pct_cutoff": drug_cutoff,
    "reactions_80pct_cutoff": rxn_cutoff,
    "manufacturers_80pct_cutoff": mfr_cutoff,
}, indent=2))
print(f"pareto.py: {drug_cutoff}/{len(drug_pareto)} drugs, {rxn_cutoff}/{len(rxn_pareto)} reactions, {mfr_cutoff}/{len(mfr_pareto)} manufacturers -> 80% of reports")
