"""
self_debug.py — banco di misura: riesegue SOLO le Fasi 4-5 (l'organizzazione
contro sé stessa, aspettative di settore) su un'esecuzione già salvata da
run_pack.py, senza rifare la pipeline. Serve a iterare sui confronti: mostra
cosa è stato estratto (fogli classificati, dichiarazioni) e gli esiti.

Uso:
  python tools/bench/self_debug.py <cartella_esecuzione> [--out trace.json]

La ricerca "esiste la registrazione dichiarata?" qui è solo lessicale (niente
indice semantico): gli esiti MISSING possono essere qualcuno in più rispetto
alla pipeline completa.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND, ".env"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--out", help="file JSON con la traccia completa (fuori dal repo)")
    ap.add_argument("--date", help="data dell'audit (YYYY-MM-DD); default oggi")
    args = ap.parse_args()

    from compliance import self_consistency, sector_expectations
    from compliance.gap_analyzer import _parse_evidence_yaml
    from compliance.absence_search import search_statement
    from compliance.facts import build
    from v2.azure_openai_client_v2 import make_client

    with gzip.open(os.path.join(args.run_dir, "corpus.json.gz"), "rt", encoding="utf-8") as f:
        docs = json.load(f)
    with open(os.path.join(args.run_dir, "evidence.yaml"), encoding="utf-8") as f:
        cards = _parse_evidence_yaml(f.read())
    facts = build(cards, docs)
    docs_by_name = {os.path.basename(str(d.get("filename") or "").replace("\\", "/")).lower(): d.get("content") or ""
                    for d in docs}
    deep = make_client(deep=True)

    def llm(messages, max_tokens):
        r = deep._sdk.chat.completions.create(model=deep.deployment, temperature=0.0, seed=42,
                                              max_tokens=max_tokens, messages=messages)
        return r.choices[0].message.content or ""

    trace: dict = {}
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    checks = self_consistency.run(docs, facts, day,
                                  lambda subject, quote, src: search_statement(subject, quote, src, docs_by_name, None, llm),
                                  trace=trace)
    sector = sector_expectations.evaluate(docs, facts.is_external)
    trace["checks"], trace["sector"] = checks, sector

    print(f"Fogli classificati: {len(trace['sheets'])}")
    for s in trace["sheets"]:
        print(f"  {s['file']} / {s['sheet']}: {s['spec'].get('kind')} ({s['rows']} righe)")
    print(f"\nDichiarazioni estratte: {len(trace['claims'])}")
    for c in trace["value_claims"]:
        print(f"  [{c.get('type')}] {c['file']}: {c.get('subject')} = {c.get('value')}"
              + (" (planned)" if c.get("planned") else ""))
    print(f"\nEsiti: {len(checks)}")
    for c in checks:
        print(f"  {c['status']:<12} {c['kind']:<20} {c['description'][:230]}")
    print(f"\nAspettative di settore: {len(sector)}")
    for x in sector:
        print("  " + json.dumps(x, ensure_ascii=False)[:230])
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
