# Summary statistics from FAERS star schema → results/stats.json
import json, os
from pathlib import Path
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CS = os.environ["SQLSERVER_CONNECTION"]
OUT = Path(__file__).resolve().parent.parent / "results" / "stats.json"

def q(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

with pyodbc.connect(CS) as conn:
    cur = conn.cursor()

    top_drugs = q(cur, """
        SELECT TOP 20 d.drug_name, COUNT(*) AS report_count
        FROM dbo.fact_drug fd JOIN dbo.dim_drug d ON fd.drug_key_dim = d.drug_key
        WHERE fd.is_suspect = 1
        GROUP BY d.drug_name ORDER BY report_count DESC
    """)

    top_reactions = q(cur, """
        SELECT TOP 20 r.reaction_meddra_apt, COUNT(*) AS report_count
        FROM dbo.fact_reaction fr JOIN dbo.dim_reaction r ON fr.reaction_key_dim = r.reaction_key
        GROUP BY r.reaction_meddra_apt ORDER BY report_count DESC
    """)

    serious = q(cur, """
        SELECT is_serious, COUNT(*) AS cnt FROM dbo.fact_report GROUP BY is_serious
    """)

    by_sex = q(cur, """
        SELECT ISNULL(sex_code,'unknown') AS sex_code, COUNT(*) AS cnt
        FROM dbo.fact_report GROUP BY sex_code ORDER BY cnt DESC
    """)

    by_age = q(cur, """
        SELECT a.age_group_label, COUNT(*) AS cnt
        FROM dbo.fact_report fr JOIN dbo.dim_age_group a ON fr.age_group_key = a.age_group_key
        GROUP BY a.age_group_label ORDER BY cnt DESC
    """)

    by_country = q(cur, """
        SELECT TOP 10 c.iso2_code, COUNT(*) AS cnt
        FROM dbo.fact_report fr JOIN dbo.dim_country c ON fr.country_key = c.country_key
        WHERE c.iso2_code <> 'XX'
        GROUP BY c.iso2_code ORDER BY cnt DESC
    """)

    outcomes = q(cur, """
        SELECT ISNULL(outcome_code,'unknown') AS outcome_code, COUNT(*) AS cnt
        FROM dbo.fact_reaction GROUP BY outcome_code ORDER BY cnt DESC
    """)

stats = {
    "top_suspect_drugs": top_drugs,
    "top_reactions": top_reactions,
    "serious_breakdown": serious,
    "by_sex": by_sex,
    "by_age_group": by_age,
    "top_countries": by_country,
    "outcome_distribution": outcomes,
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(stats, indent=2))
print(f"stats.py: saved {sum(len(v) for v in stats.values())} total rows to {OUT}")
