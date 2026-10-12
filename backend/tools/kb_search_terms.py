"""
kb_search_terms.py — genera i termini di ricerca EN/IT per ogni requisito
atomico della knowledge base (Piano motore Fase 2, ricerca esaustiva).

Prima di dichiarare "non c'è", il motore cerca il requisito in TUTTO il pacco
anche per parole: l'embedding in uso (MiniLM) è solo inglese e non trova un
"verbale di riesame" con la query "management review minutes". I termini sono
derivati dalla sola knowledge base (nessun dato cliente), generati una volta,
salvati in compliance/iso_clauses/search_terms.json e rivedibili a mano. A
runtime nessuna chiamata LLM per i termini.

Uso:
  python tools/kb_search_terms.py            # genera i mancanti
  python tools/kb_search_terms.py --all      # rigenera tutto
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND, ".env"))

from compliance.gap_analyzer import _NORM_REGISTRY  # noqa: E402

OUT = os.path.join(_BACKEND, "compliance", "iso_clauses", "search_terms.json")

PROMPT = (
    "You build search terms to find EVIDENCE of ISO management-system requirements inside a company's "
    "document pack. Documents may be in English (UK) or Italian. For each requirement give 6-12 English "
    "and 6-12 Italian terms: names of the documents or records that would show it (e.g. 'training "
    "matrix', 'matrice delle competenze', 'verbale di riesame'), column headings, and short distinctive "
    "phrases that would appear in the text. Lowercase, no generic words like 'document' or 'process' "
    "alone, no clause numbers.\n"
    'Return JSON: {"terms": {"<requirement id>": {"en": [...], "it": [...]}}}\n\nREQUIREMENTS:\n'
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    from v2.azure_openai_client_v2 import make_client
    client = make_client(deep=True)

    existing = {}
    if os.path.exists(OUT) and not args.all:
        with open(OUT, encoding="utf-8") as f:
            existing = json.load(f)
    reqs = []
    clause_sets = [cfg["clauses"] for cfg in _NORM_REGISTRY.values()]
    try:   # anche i requisiti della KB v2 (Piano motore Fase 2)
        from compliance import kb_v2
        clause_sets += [kb_v2.apply(cfg["clauses"]) for cfg in _NORM_REGISTRY.values()]
    except Exception:
        pass
    for clauses in clause_sets:
        for clause in clauses.values():
            for r in clause.get("atomic_requirements") or []:
                if any(r["id"] == x[0] for x in reqs):
                    continue
                if r["id"] not in existing:
                    reqs.append((r["id"], clause.get("title", ""), r.get("text", ""),
                                 r.get("verification_hint", ""), r.get("expected_evidence", [])))
    print(f"requisiti da generare: {len(reqs)}")
    out = dict(existing)
    for i in range(0, len(reqs), 10):
        chunk = reqs[i:i + 10]
        body = "\n".join(f"- id: {rid}\n  clause: {title}\n  requirement: {text}\n  how verified: {hint}\n"
                         f"  expected evidence: {', '.join(ev)}" for rid, title, text, hint, ev in chunk)
        for attempt in range(3):
            try:
                r = client._sdk.chat.completions.create(
                    model=client.deployment, temperature=0.0, seed=42, max_tokens=4000,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": PROMPT + body}])
                terms = json.loads(r.choices[0].message.content)["terms"]
                break
            except Exception as e:
                print(f"  ritento ({e})")
                terms = {}
        for rid, *_ in chunk:
            t = terms.get(rid) or {}
            out[rid] = {"en": sorted({s.strip().lower() for s in t.get("en", []) if s.strip()}),
                        "it": sorted({s.strip().lower() for s in t.get("it", []) if s.strip()})}
        print(f"  {min(i + 10, len(reqs))}/{len(reqs)}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items())), f, ensure_ascii=False, indent=1)
    print(f"scritto {OUT}: {len(out)} requisiti")
    return 0


if __name__ == "__main__":
    sys.exit(main())
