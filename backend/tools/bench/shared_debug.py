"""
shared_debug.py — banco di misura: applica la rilettura tra norme (SHARED_EVIDENCE,
Fase 3) a un'esecuzione già salvata da run_pack.py e scrive un nuovo result.json,
senza rifare la pipeline. Le altre regole (gravità, azioni, KB) seguono gli
interruttori registrati nei meta dell'esecuzione.

Uso:
  python tools/bench/shared_debug.py <cartella_esecuzione> <cartella_uscita>

Lo Stage B qui non ha l'indice semantico: legge i documenti citati e quelli condivisi.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND, ".env"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src, dst = sys.argv[1], sys.argv[2]
    with open(os.path.join(src, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    for name in meta.get("features") or []:          # stessi interruttori dell'esecuzione
        os.environ[name] = "1"
    os.environ["SHARED_EVIDENCE"] = "1"

    from compliance import shared_evidence
    from compliance.context_intake import build_context_prompt_block
    from compliance.deep_verifier import _norm_name
    from compliance.gap_analyzer import _call_llm, _parse_evidence_yaml
    from compliance.schemas import CompanyContext, ComplianceAnalysisResult
    from reapply_rules import _effective_clauses

    with open(os.path.join(src, "result.json"), encoding="utf-8") as f:
        result = ComplianceAnalysisResult(**json.load(f))
    with gzip.open(os.path.join(src, "corpus.json.gz"), "rt", encoding="utf-8") as f:
        docs = json.load(f)
    with open(os.path.join(src, "evidence.yaml"), encoding="utf-8") as f:
        cards = _parse_evidence_yaml(f.read())
    docs_by_name = {_norm_name(str(d.get("filename") or "")): str(d.get("content") or "") for d in docs}
    cards_by_id = {str(c.get("evidence_id")): c for c in cards if c.get("evidence_id")}
    context_block = build_context_prompt_block(CompanyContext(**meta["context"]))
    clauses_by_norm = {n.norm: _effective_clauses(n.norm, meta) for n in result.norms}

    reports, log = shared_evidence.reconcile(
        result.norms, clauses_by_norm, docs_by_name, cards_by_id, None, context_block,
        lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens, deep=True))
    print(f"{len(log)} clausole rilette")
    for line in log:
        print("  " + line)
    result.norms = reports
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(dst, "result.json"), "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=1))
    meta["features"] = sorted(set(meta.get("features") or []) | {"SHARED_EVIDENCE"})
    meta["reapplied"] = {"from": src, "features": ["SHARED_EVIDENCE"]}
    with open(os.path.join(dst, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    shutil.copy(os.path.join(src, "evidence.yaml"), os.path.join(dst, "evidence.yaml"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
