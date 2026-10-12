"""
generate_kb_v2.py — Piano motore Fase 2: genera la knowledge base v2 dal registro.

Ingresso: registry_<norma>.json (build_registry.py, FUORI dal repo).
Uscita:   backend/compliance/iso_clauses/kb_v2.json — SOLO testo nostro in
inglese e attributi (nessun testo della norma), quindi versionabile.

Per ogni clausola della KB attuale i requisiti atomici diventano:
  - un requisito per ogni obbligo "deve" della norma (source=norm), con forza,
    oggetto, verificabilità, verbi e tetto di gravità calcolato in Python;
  - i requisiti della KB attuale senza obbligo dietro classificati come buona
    pratica (source=good_practice, tetto: osservazione) o obbligo italiano
    (jurisdiction=IT); i doppioni e gli "other" si tolgono.
Le parole di formula (wording_keywords) dei requisiti attuali si conservano
sul requisito di norma corrispondente.

Uso:
  python tools/kb/generate_kb_v2.py --kb-dir C:/Users/user/amisys-bench/kb
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BACKEND)

from compliance.gap_analyzer import _NORM_REGISTRY  # noqa: E402

NORMS = {"9001": "ISO 9001:2015", "14001": "ISO 14001:2015", "45001": "ISO 45001:2018"}
OUT = os.path.join(_BACKEND, "compliance", "iso_clauses", "kb_v2.json")
_EVIDENCE_BY_OBJECT = {"record": ["record"], "document": ["procedure", "policy", "quality_manual"],
                       "process": ["procedure", "record"], "outcome": ["record"], "behaviour": ["record"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-dir", required=True)
    args = ap.parse_args()
    import openpyxl
    unmatched = {}
    wb = openpyxl.load_workbook(os.path.join(args.kb_dir, "registry_review.xlsx"), read_only=True)
    for r in list(wb["KB without norm basis"].iter_rows(values_only=True))[1:]:
        unmatched[r[2]] = r[5]                         # id → classe
    out = {}
    stats = {"norm": 0, "good_practice": 0, "national_IT": 0, "dropped": 0}
    for norm, label in NORMS.items():
        kb = _NORM_REGISTRY[label]["clauses"]
        registry = json.load(open(os.path.join(args.kb_dir, f"registry_{norm}.json"), encoding="utf-8"))
        for cid, clause in kb.items():
            old = {q["id"]: q for q in clause.get("atomic_requirements") or []}
            reqs = []
            for r in registry:
                if r["kb_clause"] != cid or r["strength"] != "shall" or not r.get("en"):
                    continue
                matched = [old[m] for m in r.get("kb_match") or [] if m in old]
                ev = sorted({e for q in matched for e in q.get("expected_evidence") or []}) \
                    or _EVIDENCE_BY_OBJECT.get(r["object"], ["record"])
                req = {"id": f"{cid}.r{r['row_id'].rsplit('-', 1)[-1]}", "text": r["en"],
                       "verification_hint": r.get("checklist_how", ""), "expected_evidence": ev,
                       "risk_if_missing": "MINOR" if r["max_severity"] == "MINOR" else "OBSERVATION",
                       "source": "norm", "norm_ref": r["clause"], "strength": r["strength"],
                       "object": r["object"], "verifiable": r["verifiable"], "verbs": r["verbs"],
                       "max_severity": r["max_severity"], "kb_v1": [q["id"] for q in matched]}
                wk = [q["wording_keywords"] for q in matched if q.get("wording_keywords")]
                if wk:
                    req["wording_keywords"] = wk[0]
                reqs.append(req)
                stats["norm"] += 1
            for qid, q in old.items():
                cls = unmatched.get(qid)
                if cls == "good_practice":
                    reqs.append({**q, "risk_if_missing": "OBSERVATION", "source": "good_practice",
                                 "max_severity": "OBSERVATION"})
                    stats["good_practice"] += 1
                elif cls == "national_IT":
                    reqs.append({**q, "risk_if_missing": "MINOR", "source": "national", "jurisdiction": "IT",
                                 "max_severity": "MINOR"})
                    stats["national_IT"] += 1
                elif cls in ("duplicate", "other"):
                    stats["dropped"] += 1
            out[cid] = {"atomic_requirements": reqs}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"KB v2: {len(out)} clausole, requisiti {stats} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
