# Export FAERS star schema and analytical views to CSV for standalone Power BI Desktop usage
import os
from pathlib import Path
import pandas as pd
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CS = os.environ.get("SQLSERVER_CONNECTION")
EXPORT_DIR = Path(__file__).resolve().parent.parent / "powerbi" / "data"

TABLES_AND_VIEWS = [
    # Dimensions
    ("dbo.dim_date", "dim_date.csv"),
    ("dbo.dim_country", "dim_country.csv"),
    ("dbo.dim_age_group", "dim_age_group.csv"),
    ("dbo.dim_drug", "dim_drug.csv"),
    ("dbo.dim_reaction", "dim_reaction.csv"),
    ("dbo.dim_reporter", "dim_reporter.csv"),
    # Facts
    ("dbo.fact_report", "fact_report.csv"),
    ("dbo.fact_drug", "fact_drug.csv"),
    ("dbo.fact_reaction", "fact_reaction.csv"),
    # Analytical Views
    ("dbo.vw_top_drugs", "vw_top_drugs.csv"),
    ("dbo.vw_top_reactions", "vw_top_reactions.csv"),
    ("dbo.vw_serious_by_age", "vw_serious_by_age.csv"),
    ("dbo.vw_serious_by_sex", "vw_serious_by_sex.csv"),
    ("dbo.vw_serious_by_country", "vw_serious_by_country.csv"),
    ("dbo.vw_serious_by_reporter", "vw_serious_by_reporter.csv"),
    ("dbo.vw_outcomes", "vw_outcomes.csv"),
    ("dbo.vw_manufacturer_quality", "vw_manufacturer_quality.csv"),
    ("dbo.vw_dosage_route_quality", "vw_dosage_route_quality.csv"),
]

def main():
    if not CS:
        raise ValueError("SQLSERVER_CONNECTION not set in environment or .env")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with pyodbc.connect(CS) as conn:
        for source_name, filename in TABLES_AND_VIEWS:
            query = f"SELECT * FROM {source_name}"
            df = pd.read_sql_query(query, conn)
            out_path = EXPORT_DIR / filename
            df.to_csv(out_path, index=False)
            print(f"Exported {len(df)} rows from {source_name} -> {out_path.name}")

if __name__ == "__main__":
    main()
