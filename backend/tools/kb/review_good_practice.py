"""
review_good_practice.py — revisione dei requisiti che il registro norma+checklist ha
classificato come "buona pratica" (nessun "deve" della norma dietro).

La classificazione automatica sbagliava circa una voce su due (es. gli impegni della
politica 14001 §5.2, gli input del riesame §9.3, la consultazione dei lavoratori 45001
§5.4 risultavano buone pratiche). Qui la decisione, voce per voce, verificata sul testo
della norma; scrive il campo "review" in iso_clauses/kb_v2.json:
  - "good_practice": nessun obbligo dietro, oppure il verbo è "considerare" / "per quanto
    appropriato" → al massimo osservazione;
  - "obligation": c'è un "deve" della norma (anche in un'altra clausola) → resta un obbligo.

Uso: python tools/kb/review_good_practice.py
"""
from __future__ import annotations

import json
from pathlib import Path

KB = Path(__file__).resolve().parents[2] / "compliance" / "iso_clauses" / "kb_v2.json"

# Restano buona pratica: la motivazione è con parole nostre, numero di clausola.
GOOD_PRACTICE = {
    "9001_6_1.methodology.defined": "6.1 asks to determine risks, not to use a scoring method",
    "9001_6_1.criteria.applied": "no scoring method is required, so none has to be applied",
    "9001_6_1.review.planned": "no review cadence is required for the risk analysis",
    "9001_7_5.coverage.all_processes": "extent of documented information is the organisation's choice (7.5.1 b)",
    "9001_7_5.obsolete_control": "the 2015 edition has no explicit requirement on obsolete documents",
    "9001_8_4.approved_list": "an approved supplier list is a common way, not a requirement",
    "9001_8_4.critical_identified": "classifying suppliers by criticality is not required",
    "9001_9_2.findings.root_cause": "root cause belongs to 10.2, not to the audit findings",
    "9001_9_3.output.tracked": "an action register is a way to do it, not a requirement",
    "9001_10_2.procedure": "no documented procedure is required for corrective action",
    "9001_10_2.no_repeat": "an inference on effectiveness, not a requirement in itself",
    "14001_4_3.scope.coherence": "the standard asks to consider these when determining the scope",
    "14001_6_1_1.prioritisation.applied": "no prioritisation method is required",
    "14001_6_1_3.status.tracked": "a status field is a way to record compliance, not a requirement",
    "14001_6_1_3.monitoring.updates": "a dedicated monitoring process is not required in 6.1.3",
    "14001_8_1.training": "specific training records for waste handlers are not required by 8.1",
    "14001_8_2.sds.available": "safety data sheets are a legal matter, not a 14001 requirement",
    "14001_8_2.communication": "information to interested parties is required only as appropriate",
    "45001_6_1_2.methodology.applied": "scores and ranking are not required, only a defined method",
    "45001_6_1_2.review.frequency": "no review frequency is required",
    "45001_8_1_4.briefing.records": "a documented briefing is a way to do it, not a requirement",
    "45001_8_1_4.monitoring": "monitoring contractor performance is not explicit in 8.1.4",
    "45001_9_1.kpi.leading_and_lagging": "the mix of leading and lagging indicators is good practice",
}


def main() -> int:
    data = json.loads(KB.read_text(encoding="utf-8"))
    counts = {"good_practice": 0, "obligation": 0}
    seen = set()
    for clause in data.values():
        for r in clause["atomic_requirements"]:
            if r.get("source") != "good_practice":
                continue
            seen.add(r["id"])
            if r["id"] in GOOD_PRACTICE:
                r["review"], r["review_note"] = "good_practice", GOOD_PRACTICE[r["id"]]
            else:
                r["review"] = "obligation"
                r["review_note"] = "a requirement of the standard stands behind it (reviewed 2026-10-12)"
            counts[r["review"]] += 1
    unknown = set(GOOD_PRACTICE) - seen
    assert not unknown, f"voci inesistenti: {unknown}"
    KB.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
