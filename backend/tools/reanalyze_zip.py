"""
reanalyze_zip.py — re-analisi END-TO-END (Phase 1→4) di uno o più ZIP con il codice
corrente, per la validazione finale dell'Hardening 2026. Persiste su DB (così le run
compaiono nella UII) e salva il per-clausola nel formato diff per il confronto con la
baseline.

Uso:
  python tools/reanalyze_zip.py <label>=<zip_path> [<label>=<zip_path> ...] --out data/_after_3run.json
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from compliance.pipeline import run_compliance_pipeline  # noqa: E402
from compliance.schemas import CompanyContext  # noqa: E402
from modules.db_manager import save_compliance_analysis, sync_engine_nonconformities  # noqa: E402

_SEV = {"MAJOR": "major", "MINOR": "minor", "OBSERVATION": "obs", "CONFORMANT": "conf"}


def _run_one(label: str, zip_path: str) -> dict:
    with open(zip_path, "rb") as f:
        zip_bytes = f.read()
    ctx = CompanyContext(company_name=label, sector="n/a", employee_range="n/a",
                         certified="no", sites_count="1", norms=["ISO 9001:2015"])
    print(f"\n=== RE-ANALISI {label} ({len(zip_bytes)} byte) ===", flush=True)

    def emit(pct, msg):
        print(f"  [{pct:5.1f}%] {msg}", flush=True)

    outcome = run_compliance_pipeline(zip_bytes, ctx, emit)
    if not outcome.get("success"):
        print(f"  FALLITA: {outcome.get('error')}")
        return {"label": label, "error": outcome.get("error")}

    result = outcome["result"]
    result_dict = result.model_dump()
    # persisti (UI + audit)
    try:
        save_compliance_analysis(
            analysis_id=result.analysis_id, user_id="admin",
            result_json_str=json.dumps(result_dict),
            context_json_str=json.dumps(ctx.model_dump()),
            evidence_yaml=outcome.get("evidence_yaml") or "",
        )
        sync_engine_nonconformities(result.analysis_id, result_dict)
    except Exception as e:
        print(f"  (persistenza non bloccante fallita: {e})")

    out_norms = {}
    for n in result_dict.get("norms", []):
        clauses, counts = {}, {"major": 0, "minor": 0, "obs": 0, "conf": 0}
        for cl in n.get("clauses", []):
            clauses[cl["clause_id"]] = {
                "severity": cl.get("severity"), "score": cl.get("score"),
                "dv": bool(cl.get("deep_verified")), "n_sources": len(cl.get("sources") or []),
            }
            if cl.get("severity") in _SEV:
                counts[_SEV[cl["severity"]]] += 1
        out_norms[n.get("norm", "?")] = {
            "overall_score": n.get("overall_score"),
            "major": counts["major"], "minor": counts["minor"],
            "obs": counts["obs"], "conf": counts["conf"], "clauses": clauses,
        }
    docs_n = len(outcome.get("evidence_yaml", "").split("# ── DOC")) - 1
    print(f"  OK {result.analysis_id} — norms: " + ", ".join(
        f"{nm} score={nd['overall_score']} MAJ{nd['major']} MIN{nd['minor']} "
        f"OBS{nd['obs']} CONF{nd['conf']}" for nm, nd in out_norms.items()))
    return {"id": result.analysis_id, "company": label, "docs": docs_n, "norms": out_norms}


def main():
    out = None
    raw = sys.argv[1:]
    if "--out" in raw:
        i = raw.index("--out")
        out = raw[i + 1]
        raw = raw[:i] + raw[i + 2:]   # togli flag E valore
    args = [a for a in raw if not a.startswith("--")]
    payload = {}
    for a in args:
        label, _, zip_path = a.partition("=")
        run = _run_one(label, zip_path)
        payload[label] = run
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\nSalvato: {out}")


if __name__ == "__main__":
    main()
