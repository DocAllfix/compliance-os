"""
action_rules.py — Piano motore Fase 2 (ACTIONS_FROM_STATES): l'azione deriva
dallo stato dei requisiti, non dal template della clausola.

Banco 12/10/2026: 21 delle 33 clausole conformi o in osservazione proponevano
di "istituire" qualcosa che il rilievo stesso dava per presente ("Define and
document the QMS scope" su uno scope documentato; "Define environmental KPIs"
su KPI definiti) — 5 dei 25 errori segnati dall'auditor. Il verbo lo decide
Python dallo stato:

  conforme             → mantenere e riesaminare
  da verificare        → verificare e aggiungere l'evidenza al pacco
  parziale             → completare
  contraddetto         → correggere l'incoerenza (+ azione correttiva sulla causa)
  assente verificato   → istituire (l'unico caso in cui "istituire" è giusto)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from compliance.schemas import ClauseGap

_MAX_ITEMS = 4


def _title(gap: ClauseGap) -> str:
    return re.sub(r"^\d+(\.\d+)*\s*", "", gap.clause_title or "").strip() or gap.clause_id


def _req_text(kb: Dict[str, Dict[str, Any]], rid: str) -> str:
    return str((kb.get(rid) or {}).get("text") or rid).rstrip(".")


def _base(name: Any) -> str:
    return str(name or "").replace("\\", "/").rsplit("/", 1)[-1]


def _kb(gap: ClauseGap, clause: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Requisiti della KB più gli esiti della Fase 4 (requisiti che l'organizzazione si è data)."""
    kb = {str(r.get("id", "")): r for r in (clause.get("atomic_requirements") or [])}
    for c in gap.requirement_checks:
        if ".self." in c.requirement_id:
            kb[c.requirement_id] = {"text": c.requirement_text or c.requirement_id}
    return kb


def apply(gap: ClauseGap, clause: Dict[str, Any]) -> ClauseGap:
    kb = _kb(gap, clause)
    checks = [c for c in gap.requirement_checks if c.requirement_id in kb]
    rem = gap.remediation

    if gap.severity == "CONFORMANT":
        rem.what = f"Maintain the current arrangements for {_title(gap).lower()} and keep them under periodic review."
        rem.correction, rem.corrective_action = None, None
        return gap

    parts: List[str] = []
    # Buone pratiche (la norma non le chiede): un suggerimento, mai "istituisci".
    good = [c for c in checks if (kb.get(c.requirement_id) or {}).get("source") == "good_practice"
            and c.status in ("ABSENT", "PARTIAL")]
    checks = [c for c in checks if c not in good]
    contradicted = [c for c in checks if c.status == "CONTRADICTED"]
    not_found = [c for c in checks if c.status == "ABSENT" and c.searched]
    partial = [c for c in checks if c.status == "PARTIAL"]

    for c in contradicted[:_MAX_ITEMS]:
        if ".self." in c.requirement_id:
            parts.append(f"Resolve the inconsistency in the organisation's own records: {_req_text(kb, c.requirement_id)}.")
            continue
        where = " vs ".join(x for x in (_base(c.file_name), _base(c.counter_file_name)) if x)
        parts.append(f"Correct the inconsistency on: {_req_text(kb, c.requirement_id)}" + (f" ({where})." if where else "."))
    for c in not_found[:_MAX_ITEMS]:
        if ".self." in c.requirement_id:
            parts.append("Provide the record, or bring the document that declares it into line with practice: "
                         f"{_req_text(kb, c.requirement_id)}.")
            continue
        parts.append(f"Establish: {_req_text(kb, c.requirement_id)}.")
    for c in partial[:_MAX_ITEMS]:
        parts.append(f"Complete: {_req_text(kb, c.requirement_id)}" + (f" — {c.note.rstrip('.')}." if c.note else "."))
    if good:
        parts.append("Consider, as good practice beyond the standard: "
                     + "; ".join(_req_text(kb, c.requirement_id) for c in good[:_MAX_ITEMS]) + ".")
    if gap.to_verify:
        parts.append("Verify that the following is in place and add the evidence to the document pack: "
                     + "; ".join(t.rstrip(".") for t in gap.to_verify[:_MAX_ITEMS]) + ".")

    if parts:
        rem.what = " ".join(parts)
    elif gap.severity == "OBSERVATION":
        # Osservazione senza stati per requisito (solo screening): l'azione del
        # template ("Establish…", "Define…") contraddice un rilievo che dà
        # l'elemento per presente. Si migliora ciò che il rilievo indica.
        m = re.search(r"\bHowever,?\s+(.+?)(?:\.\s|\.$|$)", gap.finding or "", re.S)
        if m:
            rem.what = (f"Improve the arrangements for {_title(gap).lower()}: address the point that "
                        f"{m.group(1).strip().rstrip('.')}.")
        else:
            rem.what = f"Keep the arrangements for {_title(gap).lower()} under review and improve them where useful."
    if gap.severity == "OBSERVATION":
        rem.correction, rem.corrective_action = None, None
    elif contradicted and not rem.corrective_action:
        rem.corrective_action = ("Find out why the records disagree and change the way they are kept so that "
                                 "the inconsistency cannot recur.")
    return gap


_DETAILS_MAX = 5
_FINDING_MAX = 1400


def compose_finding(gap: ClauseGap, clause: Dict[str, Any]) -> ClauseGap:
    """Il rilievo nomina i difetti specifici. Con molti requisiti per clausola
    (KB v2) lo Stage B scrive un riassunto e i dettagli — il formatore non
    indicato, il certificato fallito — restavano nelle note dei controlli
    (banco Box: ENC riconosciute da 10-11 a 2-3). In coda al rilievo: le
    contraddizioni, le assenze verificate e i parziali, con la loro nota."""
    kb = _kb(gap, clause)
    checks = [c for c in gap.requirement_checks if c.requirement_id in kb]
    order = {"CONTRADICTED": 0, "ABSENT": 1, "PARTIAL": 2}
    items = []
    for c in sorted(checks, key=lambda c: order.get(c.status, 9)):
        if c.status == "CONTRADICTED":
            items.append(f"{_req_text(kb, c.requirement_id)} — contradicted: "
                         f"“{(c.evidence_quote or '')[:120]}” ({_base(c.file_name)}) vs "
                         f"“{(c.counter_quote or '')[:120]}” ({_base(c.counter_file_name)})")
        elif c.status == "ABSENT" and c.searched:
            items.append(f"{_req_text(kb, c.requirement_id)} — not found in the whole pack")
        elif c.status == "PARTIAL" and c.note:
            items.append(f"{_req_text(kb, c.requirement_id)} — {c.note.rstrip('.')}")
        if len(items) >= _DETAILS_MAX:
            break
    if items and "Details:" not in gap.finding:
        gap.finding = (gap.finding.rstrip() + " Details: " + "; ".join(items) + ".")[:_FINDING_MAX]
    return gap


def apply_all(gaps: List[ClauseGap], clauses: Dict[str, Dict[str, Any]]) -> List[ClauseGap]:
    out = []
    for g in gaps:
        clause = clauses.get(g.clause_id, {})
        out.append(compose_finding(apply(g, clause), clause))
    return out
