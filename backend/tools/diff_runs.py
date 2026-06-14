"""
diff_runs.py — strumento di confronto verdetti per-clausola tra run di analisi.

Usato dal piano "Hardening precisione motore": cattura una baseline delle run
esistenti e confronta una nuova run (post-fix) contro la baseline, clausola per
clausola, per misurare se abbiamo migliorato senza regressioni.

Uso:
  # snapshot delle run correnti (per id o per ultimo-per-company)
  python tools/diff_runs.py snapshot data/_baseline_3run.json \
      serapide Co.Energie "CONSORZIO ITALIA"

  # diff: baseline (file json o analysis_id) vs run nuova (id o company)
  python tools/diff_runs.py diff data/_baseline_3run.json "CONSORZIO ITALIA"
  python tools/diff_runs.py diff analysis_20260614_180204 analysis_20260615_xxxx

  # elenco run in DB
  python tools/diff_runs.py list
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.db_manager import get_connection  # noqa: E402

_SEV_RANK = {"MAJOR": 0, "MINOR": 1, "OBSERVATION": 2, "CONFORMANT": 3}


def list_runs():
    c = get_connection()
    rows = c.execute(
        "SELECT id, company, documents_analyzed, analysis_date "
        "FROM compliance_analyses ORDER BY analysis_date"
    ).fetchall()
    for r in rows:
        print(f"{r['id']} | {r['company']:18} | docs={r['documents_analyzed']} | {r['analysis_date']}")
    c.close()


def _resolve_id(token: str) -> str:
    """token può essere un analysis_id esatto o un nome company (ultimo per data)."""
    c = get_connection()
    row = c.execute("SELECT id FROM compliance_analyses WHERE id=?", (token,)).fetchone()
    if row:
        c.close()
        return token
    row = c.execute(
        "SELECT id FROM compliance_analyses WHERE lower(company)=lower(?) "
        "ORDER BY analysis_date DESC LIMIT 1", (token,)
    ).fetchone()
    c.close()
    if not row:
        raise SystemExit(f"Nessuna run trovata per '{token}' (né id né company).")
    return row["id"]


def load_run(token: str) -> dict:
    """Ritorna {meta, clauses:{clause_id:{severity,score,dv,n_sources}}}."""
    rid = _resolve_id(token)
    c = get_connection()
    r = c.execute(
        "SELECT id, company, documents_analyzed, result_json FROM compliance_analyses WHERE id=?",
        (rid,),
    ).fetchone()
    c.close()
    res = json.loads(r["result_json"])
    out = {
        "id": r["id"],
        "company": r["company"],
        "docs": r["documents_analyzed"],
        "norms": {},
    }
    for n in res.get("norms", []):
        clauses = {}
        for cl in n.get("clauses", []):
            clauses[cl["clause_id"]] = {
                "severity": cl.get("severity"),
                "score": cl.get("score"),
                "dv": bool(cl.get("deep_verified")),
                "n_sources": len(cl.get("sources") or []),
            }
        out["norms"][n.get("norm", "?")] = {
            "overall_score": n.get("overall_score"),
            "major": n.get("major_count"),
            "minor": n.get("minor_count"),
            "obs": n.get("observation_count"),
            "conf": n.get("conformant_count"),
            "clauses": clauses,
        }
    return out


def snapshot(out_path: str, tokens: list[str]):
    data = {t: load_run(t) for t in tokens}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Snapshot salvato: {out_path}")
    for t, run in data.items():
        for norm, nd in run["norms"].items():
            print(f"  {run['company']:18} {norm} score={nd['overall_score']} "
                  f"MAJ{nd['major']} MIN{nd['minor']} OBS{nd['obs']} CONF{nd['conf']}")


def _load_side(token: str) -> dict:
    """Carica un lato del diff: file json (snapshot) o run dal DB."""
    if token.endswith(".json") and os.path.exists(token):
        with open(token, encoding="utf-8") as f:
            return json.load(f)  # dict company->run oppure singola run
    return {"_": load_run(token)}


def _iter_runs(side: dict):
    # side può essere {token: run} (snapshot multi) o {"_": run}
    for run in side.values():
        if isinstance(run, dict) and "norms" in run:
            yield run


def diff(base_token: str, new_token: str):
    base_side = _load_side(base_token)
    new_side = _load_side(new_token)
    base_by_company = {r["company"].lower(): r for r in _iter_runs(base_side)}
    new_by_company = {r["company"].lower(): r for r in _iter_runs(new_side)}

    companies = [c for c in new_by_company if c in base_by_company] or list(base_by_company)
    for comp in companies:
        b = base_by_company.get(comp)
        n = new_by_company.get(comp)
        if not b or not n:
            continue
        print("=" * 78)
        print(f"AZIENDA: {b['company']}")
        for norm in b["norms"]:
            bn = b["norms"][norm]
            nn = n["norms"].get(norm)
            if not nn:
                continue
            print(f"-- {norm}: score {bn['overall_score']}→{nn['overall_score']} | "
                  f"MAJ {bn['major']}→{nn['major']} MIN {bn['minor']}→{nn['minor']} "
                  f"OBS {bn['obs']}→{nn['obs']} CONF {bn['conf']}→{nn['conf']}")
            bc = bn["clauses"]; nc = nn["clauses"]
            changed = 0
            for cid in sorted(set(bc) | set(nc), key=lambda x: x):
                bv = bc.get(cid); nv = nc.get(cid)
                if not bv or not nv:
                    print(f"   {cid:12} | {'(assente)' if not bv else bv['severity']} "
                          f"→ {'(assente)' if not nv else nv['severity']}")
                    changed += 1
                    continue
                if bv["severity"] != nv["severity"] or bv["dv"] != nv["dv"]:
                    flag = ""
                    if bv["severity"] != nv["severity"]:
                        flag = "  ⚠ SEV" if _SEV_RANK.get(nv["severity"], 9) < _SEV_RANK.get(bv["severity"], 9) else "  ↑ meno severo"
                    print(f"   {cid:12} | {bv['severity']:11}{bv['score']:>3} dv={bv['dv']:<1} "
                          f"→ {nv['severity']:11}{nv['score']:>3} dv={nv['dv']:<1}{flag}")
                    changed += 1
            if changed == 0:
                print("   (nessun cambiamento di severità/dv)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "list":
        list_runs()
    elif cmd == "snapshot":
        snapshot(sys.argv[2], sys.argv[3:])
    elif cmd == "diff":
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
