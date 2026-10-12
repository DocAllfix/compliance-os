"""
kb_v2.py — Piano motore Fase 2 (KB_V2): knowledge base ricostruita da norma + checklist.

I requisiti atomici di ogni clausola vengono da iso_clauses/kb_v2.json
(generato da tools/kb/generate_kb_v2.py): uno per ogni obbligo "deve" della
norma, riformulato in inglese con parole nostre, con forza, oggetto,
verificabilità e tetto di gravità; più le buone pratiche della KB precedente
(tetto: osservazione) e gli obblighi italiani (solo profilo Italia).
Il resto della clausola (titolo, area, SPoF, parole chiave, template) resta
quello della KB attuale.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger("compliance.kb_v2")
_PATH = Path(__file__).resolve().parent / "iso_clauses" / "kb_v2.json"
_DATA: Optional[Dict[str, Any]] = None


def _data() -> Dict[str, Any]:
    global _DATA
    if _DATA is None:
        try:
            _DATA = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            _log.warning("[KB_V2] %s non leggibile (%s): resta la KB attuale", _PATH.name, e)
            _DATA = {}
    return _DATA


def annotate(clauses: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """KB_STRENGTH: la KB attuale resta com'è; i suoi requisiti che il registro norma+checklist
    ha classificato come buona pratica (nessun "deve" della norma dietro) vengono marcati tali.
    Le regole di gravità li trattano da opportunità di miglioramento, mai da non conformità."""
    data = _data()
    # Solo le voci confermate dalla revisione (tools/kb/review_good_practice.py): la
    # classificazione automatica sbagliava circa una volta su due.
    good = {str(r.get("id")) for v2 in data.values() for r in v2.get("atomic_requirements", [])
            if r.get("source") == "good_practice" and r.get("review", "good_practice") == "good_practice"}
    out = {}
    for cid, clause in clauses.items():
        reqs = clause.get("atomic_requirements") or []
        if any(str(r.get("id")) in good for r in reqs):
            out[cid] = {**clause, "atomic_requirements": [
                {**r, "source": "good_practice", "max_severity": "OBSERVATION"} if str(r.get("id")) in good else r
                for r in reqs]}
        else:
            out[cid] = clause
    return out


def apply(clauses: Dict[str, Dict[str, Any]], fill_only: bool = False) -> Dict[str, Dict[str, Any]]:
    """fill_only (KB_V2_FILL): requisiti v2 solo nelle clausole che oggi non
    ne hanno. Banco 12/10: la KB v2 completa toglie le false assenze ma fa
    perdere i difetti puntuali che le clausole curate della KB attuale colgono;
    le false assenze residue nascono proprio nelle clausole senza requisiti."""
    data = _data()
    out = {}
    for cid, clause in clauses.items():
        v2 = data.get(cid)
        if v2 and not (fill_only and clause.get("atomic_requirements")):
            reqs = [{**r, "source": "checklist", "max_severity": "MINOR"}
                    if r.get("source") == "good_practice" and r.get("review") == "obligation" else r
                    for r in v2["atomic_requirements"]]
            out[cid] = {**clause, "atomic_requirements": reqs}
        else:
            out[cid] = clause
    return out
