"""
shared_evidence.py — Piano motore Fase 3 (SHARED_EVIDENCE): un solo giudizio per un
fatto condiviso tra le norme.

In un sistema integrato le tre norme hanno le stesse clausole di struttura (4.x, 5.x,
7.x, 9.x, 10.x) e spesso gli stessi documenti le soddisfano (un manuale con
l'organigramma, un registro delle parti interessate). Ogni norma però era analizzata
per conto suo: una norma leggeva il documento giusto e dava "conforme", un'altra
vedeva pochi estratti nello screening e scriveva "manca l'organigramma" (banco Box:
errori F02, F04, F05 dell'auditor; clausole comuni con giudizi opposti in ogni
esecuzione).

Qui, dopo l'analisi delle norme: per ogni clausola comune giudicata CONFORME in una
norma e non conforme o in osservazione in un'altra solo sulla base dello screening
(senza lettura completa), la seconda viene riletta per intero con lo Stage B,
aggiungendo in testa i documenti che hanno sostenuto la prima. Il giudizio resta
dello Stage B e delle regole di gravità: la condivisione riguarda le prove, non
l'esito (un obiettivo di sicurezza non diventa un obiettivo di qualità).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from compliance.schemas import ClauseGap, NormGapReport

_log = logging.getLogger("compliance.shared_evidence")

MAX_REREADS = 12
MAX_WORKERS = 6


def _number(clause_id: str) -> str:
    return clause_id.split("_", 1)[1] if "_" in clause_id else clause_id


def _title_words(title: str) -> set:
    import re
    t = re.sub(r"^\d+(\.\d+)*\s*", "", title or "").lower()
    return {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", t)} - {"management", "system", "organization", "organisation"}


def _same_subject(a: ClauseGap, b: ClauseGap) -> bool:
    """Stesso numero non vuol dire stesso argomento (9001 §8.2 prodotti, 14001 §8.2 emergenze;
    9001 §9.1.2 soddisfazione del cliente, 14001 §9.1.2 valutazione della conformità)."""
    wa, wb = _title_words(a.clause_title), _title_words(b.clause_title)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def find_conflicts(norm_reports: List[NormGapReport]) -> List[Tuple[str, ClauseGap, List[Tuple[str, ClauseGap]]]]:
    """(norma, clausola da rileggere, [(norma, clausola conforme che la contraddice)])."""
    by_number: Dict[str, List[Tuple[str, ClauseGap]]] = {}
    for rep in norm_reports:
        for g in rep.clauses:
            by_number.setdefault(_number(g.clause_id), []).append((rep.norm, g))
    out = []
    for items in by_number.values():
        if len(items) < 2:
            continue
        support = [(n, g) for n, g in items if g.severity == "CONFORMANT" and g.sources]
        if not support:
            continue
        for n, g in items:
            if g.severity != "CONFORMANT" and not g.deep_verified:
                same = [(sn, sg) for sn, sg in support if sn != n and _same_subject(g, sg)]
                if same:
                    out.append((n, g, same))
    return out[:MAX_REREADS]


def reconcile(norm_reports: List[NormGapReport], clauses_by_norm: Dict[str, Dict[str, Dict[str, Any]]],
              docs_by_name: Dict[str, str], cards_by_id: Dict[str, Dict[str, Any]], evidence_service,
              context_block: str, llm_call: Callable,
              emit: Optional[Callable[[float, str], None]] = None) -> Tuple[List[NormGapReport], List[str]]:
    """Rilegge le clausole in conflitto. Ritorna i report ricalcolati e un registro leggibile."""
    from compliance import deep_verifier as D
    from compliance.gap_analyzer import _apply_severity_floor, _build_norm_report, finalise_gaps

    conflicts = find_conflicts(norm_reports)
    if not conflicts or not docs_by_name:
        return norm_reports, []
    if emit:
        emit(85.0, f"Re-reading {len(conflicts)} shared clause(s) judged differently across the standards…")
    system_prompt, doc_tags, fname_to_eid = D.prepare_stage_b(context_block, cards_by_id, docs_by_name)
    log: List[str] = []

    def one(item):
        norm, gap, support = item
        clause = clauses_by_norm.get(norm, {}).get(gap.clause_id)
        if not clause:
            return None
        shared = [s for _, sg in support for s in sg.sources]
        seen, sources = set(), []
        for s in shared + list(gap.sources):           # prima i documenti che hanno convinto l'altra norma
            key = D._norm_name(s.file_name)
            if key not in seen:
                seen.add(key)
                sources.append(s)
        probe = gap.model_copy(update={"sources": sources})
        try:
            new = D._deep_verify_clause(clause=clause, gap=probe, docs_by_name=docs_by_name,
                                        fname_to_eid=fname_to_eid, evidence_service=evidence_service,
                                        system_prompt=system_prompt, llm_call=llm_call, doc_tags=doc_tags)
        except Exception as e:
            _log.warning("[SharedEvidence] %s %s: %s", norm, gap.clause_id, str(e)[:160])
            return None
        if new is None:
            return None
        new = D._apply_partial_credit(_apply_severity_floor(new, clause, []))
        # Gli esiti "contro le proprie registrazioni" già agganciati restano (in pipeline
        # la rilettura precede la Fase 4; serve quando si riapplica a un'analisi salvata).
        own = [c for c in gap.requirement_checks if ".self." in c.requirement_id]
        if own:
            new.requirement_checks = list(new.requirement_checks) + own
        new = finalise_gaps([new], clauses_by_norm[norm])[0]
        others = ", ".join(sorted({sn for sn, _ in support}))
        note = (f"Re-read in full with the documents that support the same clause in {others}: one judgment "
                f"for evidence shared by the standards.")
        new.hedge_note = f"{new.hedge_note} {note}".strip() if new.hedge_note else note
        return norm, gap.clause_id, gap.severity, new

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(conflicts))) as ex:
        results = [r for r in ex.map(one, conflicts) if r]

    replaced = {(n, cid): new for n, cid, _, new in results}
    for n, cid, before, new in results:
        log.append(f"{n} {cid}: {before} -> {new.severity}")
    out = []
    for rep in norm_reports:
        gaps = [replaced.get((rep.norm, g.clause_id), g) for g in rep.clauses]
        out.append(_build_norm_report(rep.norm, gaps, clauses_by_norm.get(rep.norm)) if gaps != rep.clauses else rep)
    _log.info("[SharedEvidence] %d clausole rilette: %s", len(results), "; ".join(log))
    return out, log
