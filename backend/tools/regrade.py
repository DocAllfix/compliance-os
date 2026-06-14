"""
regrade.py — ri-esegue SOLO la gap-analysis (Phase 3: Stage A + Stage B + clamp)
sui dati persistiti di una run (evidence cards + corpus testi), SENZA re-estrazione
(Phase 1) né re-carding (Phase 2).

Serve a misurare l'effetto dei fix di logica del motore (problemi #1/#4/#6) in
isolamento, riusando le stesse card/testi della baseline. NON scrive su DB.

Uso:
  python tools/regrade.py <analysis_id|company> [out.json]
Esempio:
  python tools/regrade.py "CONSORZIO ITALIA" data/_regrade_consorzio.json
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from modules.db_manager import get_connection, load_analysis_corpus  # noqa: E402
from compliance.gap_analyzer import analyze_compliance  # noqa: E402
from compliance.schemas import CompanyContext  # noqa: E402

_SEV = {"MAJOR": "major", "MINOR": "minor", "OBSERVATION": "obs", "CONFORMANT": "conf"}


def _resolve(token: str) -> str:
    c = get_connection()
    row = c.execute("SELECT id FROM compliance_analyses WHERE id=?", (token,)).fetchone()
    if not row:
        row = c.execute(
            "SELECT id FROM compliance_analyses WHERE lower(company)=lower(?) "
            "ORDER BY analysis_date DESC LIMIT 1", (token,)
        ).fetchone()
    c.close()
    if not row:
        raise SystemExit(f"Run non trovata: {token}")
    return row["id"]


def regrade(token: str) -> dict:
    rid = _resolve(token)
    c = get_connection()
    row = c.execute(
        "SELECT company, evidence_yaml FROM compliance_analyses WHERE id=?", (rid,)
    ).fetchone()
    c.close()
    docs = load_analysis_corpus(rid)
    ctx = CompanyContext(
        company_name=row["company"], sector="n/a", employee_range="n/a",
        certified="no", sites_count="1", norms=["ISO 9001:2015"],
    )
    print(f"Regrade {row['company']} ({rid}) — {len(docs)} doc, "
          f"{len(row['evidence_yaml'] or '')} byte di cards…")
    result = analyze_compliance(row["evidence_yaml"], ctx, None, docs)

    out_norms = {}
    for n in result.norms:
        clauses = {}
        counts = {"major": 0, "minor": 0, "obs": 0, "conf": 0}
        for cl in n.clauses:
            clauses[cl.clause_id] = {
                "severity": cl.severity, "score": cl.score,
                "dv": bool(cl.deep_verified), "n_sources": len(cl.sources or []),
            }
            if cl.severity in _SEV:
                counts[_SEV[cl.severity]] += 1
        out_norms[n.norm] = {
            "overall_score": n.overall_score,
            "major": counts["major"], "minor": counts["minor"],
            "obs": counts["obs"], "conf": counts["conf"],
            "clauses": clauses,
        }
    return {"id": rid + "_regrade", "company": row["company"],
            "docs": len(docs), "norms": out_norms}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    token = sys.argv[1]
    run = regrade(token)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    payload = {run["company"]: run}
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Salvato: {out}")
    for norm, nd in run["norms"].items():
        print(f"  {norm} score={nd['overall_score']} "
              f"MAJ{nd['major']} MIN{nd['minor']} OBS{nd['obs']} CONF{nd['conf']}")


if __name__ == "__main__":
    main()
