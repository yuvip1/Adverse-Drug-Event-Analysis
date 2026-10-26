"""Stream JSON from zip, bulk-load into staging tables.

Usage: .venv/Scripts/python src/ingest.py C:/path/to/drug-event-*.json.zip
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import ijson
import pyodbc
from dotenv import load_dotenv
import os

load_dotenv()
CONN_STR = os.environ["SQLSERVER_CONNECTION"]

def ingest(zip_path: Path, batch_id: int = 1) -> dict[str, int]:
    with zipfile.ZipFile(zip_path) as zf:
        json_name = [n for n in zf.namelist() if n.endswith(".json")][0]
        with zf.open(json_name) as f:
            reports, drugs, reactions = [], [], []
            for report in ijson.items(f, "results.item"):
                rid = report.get("safetyreportid")
                rver = report.get("safetyreportversion")
                if not rid:
                    continue

                # stg.reports row
                reports.append((
                    rid, rver, report.get("companynumb"),
                    report.get("primarysourcecountry"), report.get("occurcountry"),
                    report.get("transmissiondateformat"), report.get("transmissiondate"),
                    report.get("reporttype"), report.get("serious"),
                    report.get("seriousnessdeath"), report.get("seriousnesslifethreatening"),
                    report.get("seriousnesshospitalization"), report.get("seriousnessdisabling"),
                    report.get("seriousnesscongenitalanomali"), report.get("seriousnessother"),
                    report.get("receivedateformat"), report.get("receivedate"),
                    report.get("receiptdateformat"), report.get("receiptdate"),
                    report.get("fulfillexpeditecriteria"), report.get("duplicate"),
                    report.get("patient", {}).get("patientsex"),
                    report.get("patient", {}).get("patientagegroup"),
                    report.get("patient", {}).get("patientonsetage"),
                    report.get("patient", {}).get("patientonsetageunit"),
                    report.get("patient", {}).get("patientweight"),
                    report.get("primarysource", {}).get("reportercountry"),
                    report.get("primarysource", {}).get("qualification"),
                    report.get("sender", {}).get("sendertype"),
                    report.get("sender", {}).get("senderorganization"),
                    report.get("receiver", {}).get("receivertype"),
                    report.get("receiver", {}).get("receiverorganization"),
                    batch_id
                ))

                # stg.drugs rows
                for drug in report.get("patient", {}).get("drug", []):
                    openfda = drug.get("openfda", {})
                    drugs.append((
                        rid, rver, drug.get("medicinalproduct"),
                        drug.get("drugcharacterization"), drug.get("drugauthorizationnumb"),
                        drug.get("drugseparatedosagenumb"), drug.get("drugdosageform"),
                        drug.get("drugadministrationroute"), drug.get("drugindication"),
                        drug.get("activesubstance", {}).get("activesubstancename"),
                        openfda.get("brand_name", [None])[0] if openfda.get("brand_name") else None,
                        openfda.get("generic_name", [None])[0] if openfda.get("generic_name") else None,
                        openfda.get("manufacturer_name", [None])[0] if openfda.get("manufacturer_name") else None,
                        batch_id
                    ))

                # stg.reactions rows
                for rxn in report.get("patient", {}).get("reaction", []):
                    reactions.append((
                        rid, rver, rxn.get("reactionmeddrapt"),
                        rxn.get("reactionmeddraversionpt"), rxn.get("reactionoutcome"),
                        batch_id
                    ))

    with pyodbc.connect(CONN_STR) as conn:
        conn.autocommit = False
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.execute("TRUNCATE TABLE stg.reactions")
        cur.execute("TRUNCATE TABLE stg.drugs")
        cur.execute("TRUNCATE TABLE stg.reports")

        cur.executemany("""
            INSERT INTO stg.reports (safetyreportid, safetyreportversion, companynumb,
                primarysourcecountry, occurcountry, transmissiondateformat, transmissiondate,
                reporttype, serious, seriousnessdeath, seriousnesslifethreatening,
                seriousnesshospitalization, seriousnessdisabling, seriousnesscongenitalanomali,
                seriousnessother, receivedateformat, receivedate, receiptdateformat, receiptdate,
                fulfillexpeditecriteria, duplicate, patientsex, patientagegroup, patientonsetage,
                patientonsetageunit, patientweight, primarysource_reportercountry,
                primarysource_qualification, sender_sendertype, sender_senderorganization,
                receiver_receivertype, receiver_receiverorganization, batch_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, reports)

        cur.executemany("""
            INSERT INTO stg.drugs (safetyreportid, safetyreportversion, medicinalproduct,
                drugcharacterization, drugauthorizationnumb, drugseparatedosagenumb,
                drugdosageform, drugadministrationroute, drugindication, activesubstancename,
                openfda_brand_name, openfda_generic_name, openfda_manufacturer_name, batch_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, drugs)

        cur.executemany("""
            INSERT INTO stg.reactions (safetyreportid, safetyreportversion, reactionmeddrapt,
                reactionmeddraversionpt, reactionoutcome, batch_id)
            VALUES (?,?,?,?,?,?)
        """, reactions)

        conn.commit()

    return {"reports": len(reports), "drugs": len(drugs), "reactions": len(reactions)}

if __name__ == "__main__":
    zip_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Users/yuvra/Downloads/drug-event-0001-of-0031.json.zip")
    counts = ingest(zip_file)
    print(f"Loaded: {counts['reports']:,} reports, {counts['drugs']:,} drugs, {counts['reactions']:,} reactions")
