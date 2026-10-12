"""
reapply_rules.py — riapplica le regole di gravità e delle azioni (SEVERITY_RULES,
ACTIONS_FROM_STATES) a
un'esecuzione già fatta, senza rilanciare il motore.

Le regole lavorano solo sui verdetti (stati dei requisiti, Stage A/B, KB):
applicarle a result.json esistenti misura il loro effetto a costo zero e a
parità di tutto il resto (stesse schede, stessi testi, stessi rilievi).

Uso:
  python tools/bench/reapply_rules.py <cartella_esecuzione> <cartella_uscita>
"""
from __future__ import annotations

import json
import os
import shutil
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BACKEND)

from compliance import action_rules, severity_rules  # noqa: E402
from compliance.gap_analyzer import _NORM_REGISTRY, _build_norm_report  # noqa: E402
from compliance.schemas import ClauseGap  # noqa: E402


def _effective_clauses(norm: str, meta: dict) -> dict:
    """La stessa KB che ha usato l'esecuzione: v2 e filtro per paese se erano accesi."""
    clauses = _NORM_REGISTRY.get(norm, {}).get("clauses", {})
    feats = set(meta.get("features") or [])
    if "KB_V2" in feats or "KB_V2_FILL" in feats:
        from compliance import kb_v2
        clauses = kb_v2.apply(clauses, fill_only="KB_V2" not in feats)
    elif "KB_STRENGTH" in feats:
        from compliance import kb_v2
        clauses = kb_v2.annotate(clauses)
    if "JURISDICTION_FILTER" in feats:
        from compliance import jurisdiction
        clauses = jurisdiction.adapt_clauses(clauses, (meta.get("context") or {}).get("country"))
    return clauses


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    extra_features = sys.argv[3:]          # es. KB_STRENGTH: misura un interruttore senza rifare la pipeline
    with open(os.path.join(src, "result.json"), encoding="utf-8") as f:
        result = json.load(f)
    meta = {}
    if os.path.exists(os.path.join(src, "meta.json")):
        with open(os.path.join(src, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
    meta["features"] = sorted(set(meta.get("features") or []) | set(extra_features))
    for i, n in enumerate(result["norms"]):
        clauses = _effective_clauses(n["norm"], meta)
        gaps = severity_rules.apply_all([ClauseGap(**c) for c in n["clauses"]], clauses)
        gaps = action_rules.apply_all(gaps, clauses)
        result["norms"][i] = _build_norm_report(n["norm"], gaps, clauses).model_dump()
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(dst, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    meta_src = os.path.join(src, "meta.json")
    if os.path.exists(meta_src):
        with open(meta_src, encoding="utf-8") as f:
            meta = json.load(f)
        meta["features"] = sorted(set(meta.get("features") or []) | set(extra_features))
        meta["reapplied"] = {"from": src, "features": ["SEVERITY_RULES", "ACTIONS_FROM_STATES"] + extra_features}
        with open(os.path.join(dst, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    for extra in ("evidence.yaml",):
        if os.path.exists(os.path.join(src, extra)):
            shutil.copy(os.path.join(src, extra), os.path.join(dst, extra))
    print(f"regole riapplicate: {src} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
