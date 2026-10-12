"""
severity_rules.py — Piano motore Fase 2 (SEVERITY_RULES): la gravità la decide Python.

Banco 12/10/2026: il motore partiva dalla gravità massima e scendeva solo se
trovava qualcosa (soglia minima automatica, "nessuna evidenza → MAJOR"): su Box
38-42 clausole su 71 in non conformità, sui pacchi italiani nessuna clausola
conforme. Un auditor ragiona al contrario: parte da "conforme" e scrive una
non conformità solo con l'evidenza oggettiva di un requisito non soddisfatto.

Regole (applicate per ultime, sopra ogni altra calibrazione):

| Situazione                                                          | Gravità                       |
|---------------------------------------------------------------------|-------------------------------|
| Assenza non verificata (nessuna ricerca esaustiva)                  | "da verificare", non è una NC |
| Requisito derivato dal modello (non nella knowledge base)           | mai NC: al massimo osservazione|
| Verdetto del solo screening (Stage A), senza prova per requisito    | al massimo osservazione       |
| "Deve" soddisfatto in parte                                         | osservazione, MINOR se il requisito è di peso MAJOR |
| "Deve" non soddisfatto con prova (contraddizione, assenza verificata)| MINOR                         |
| Come sopra, ma il processo manca in tutto il pacco su una clausola critica | MAJOR                  |

La mancanza di prove abbassa la certezza, non alza la gravità.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from compliance.clause_helpers import get_criticality_tier
from compliance.schemas import ClauseGap

BANDS = {"MAJOR": (0, 29), "MINOR": (30, 59), "OBSERVATION": (60, 84), "CONFORMANT": (85, 100)}
_RANK = {"CONFORMANT": 0, "OBSERVATION": 1, "MINOR": 2, "MAJOR": 3}


def _score(severity: str, coverage: float) -> int:
    lo, hi = BANDS[severity]
    return int(round(lo + max(0.0, min(1.0, coverage)) * (hi - lo)))


def _first_sentence(text: str, limit: int = 220) -> str:
    s = re.split(r"(?<=[.;])\s+", (text or "").strip(), maxsplit=1)[0]
    return s[:limit].rstrip()


def _note(gap: ClauseGap, text: str) -> None:
    gap.hedged = True
    gap.hedge_note = f"{gap.hedge_note} {text}".strip() if gap.hedge_note else text


def is_verified_failure(check: Any) -> bool:
    """Un requisito non soddisfatto CON prova: contraddizione verificata, oppure
    assenza confermata dalla ricerca esaustiva nel pacco (Fase 2, ricerca)."""
    status = getattr(check, "status", "")
    return status == "CONTRADICTED" or (status == "ABSENT" and bool(getattr(check, "searched", False)))


def _cap(req: Dict[str, Any]) -> str:
    """Tetto di gravità del requisito: KB v2 lo porta (max_severity), la KB
    precedente no (vale MINOR, come le regole hanno sempre fatto)."""
    return str(req.get("max_severity") or "MINOR")


def _heavy_partial(req: Dict[str, Any]) -> bool:
    """Un "deve" soddisfatto in parte pesa MINOR quando riguarda un documento o
    una registrazione richiesti (KB v2), o un requisito di peso MAJOR (KB precedente)."""
    if req.get("source") == "norm":
        return _cap(req) == "MINOR" and req.get("object") in ("record", "document")
    return str(req.get("risk_if_missing", "MINOR")) == "MAJOR"


def apply(gap: ClauseGap, clause: Dict[str, Any]) -> ClauseGap:
    kb_reqs = {str(r.get("id", "")): r for r in (clause.get("atomic_requirements") or [])}
    norm_ids = set(kb_reqs)
    # Fase 4: gli esiti "l'organizzazione contro sé stessa" sono requisiti che
    # l'organizzazione si è data (ISO 45001 §3.34 nota 1): tetto MINOR, già provati.
    for c in gap.requirement_checks:
        if ".self." in c.requirement_id:
            kb_reqs[c.requirement_id] = {"text": c.requirement_text or c.requirement_id, "source": "self",
                                         "max_severity": "MINOR", "object": "record"}
    kb_checks = [c for c in gap.requirement_checks if c.requirement_id in kb_reqs]
    norm_checks = [c for c in kb_checks if c.requirement_id in norm_ids]
    self_checks = [c for c in kb_checks if c.requirement_id not in norm_ids]

    # ── Nessuna prova per requisito: screening o requisiti inventati ─────────
    if not ((gap.deep_verified and norm_checks) or self_checks):
        if gap.severity in ("MAJOR", "MINOR"):
            item = _first_sentence(gap.finding) or gap.clause_title
            gap.to_verify = gap.to_verify or [item]
            gap.severity = "OBSERVATION"
            gap.score = max(BANDS["OBSERVATION"][0], min(BANDS["OBSERVATION"][1], gap.score or 65))
            gap.is_spof = False
            _note(gap, "Not confirmed requirement by requirement against the whole pack: reported as a point "
                       "to verify, not as a nonconformity.")
        # requisiti derivati dal modello rimasti ABSENT: da verificare
        derived_absent = [c for c in gap.requirement_checks
                          if c.requirement_id not in kb_reqs and c.status == "ABSENT" and c.note]
        for c in derived_absent:
            if c.note not in gap.to_verify:
                gap.to_verify.append(c.note[:200])
        return gap

    # KB v2: le buone pratiche non sono obblighi → non entrano nella gravità.
    obligations = [c for c in kb_checks if kb_reqs[c.requirement_id].get("source") != "good_practice"] or kb_checks
    present = sum(c.status == "PRESENT" for c in obligations)
    partial = [c for c in obligations if c.status == "PARTIAL"]
    failures = [c for c in obligations if is_verified_failure(c)]
    unverified = [c for c in obligations if c.status == "ABSENT" and not is_verified_failure(c)]
    coverage = (present + 0.5 * len(partial)) / max(1, len(obligations))

    # Tetto per requisito (KB v2: max_severity calcolato dal testo della norma —
    # "considerare", raccomandazioni, note → osservazione; comportamenti non
    # dimostrabili dai documenti → solo "da verificare").
    caps = {c.requirement_id: _cap(kb_reqs[c.requirement_id]) for c in obligations}
    unverified += [c for c in failures if caps[c.requirement_id] == "TO_VERIFY"]
    failures = [c for c in failures if caps[c.requirement_id] != "TO_VERIFY"]
    nc_failures = [c for c in failures if caps[c.requirement_id] == "MINOR"]

    if nc_failures:
        severity = "MINOR"
        # MAJOR di sistema: il processo manca in tutto il pacco — giudicato sui
        # soli requisiti della norma (un esito della Fase 4 da solo non basta).
        norm_obl = [c for c in obligations if c.requirement_id in norm_ids]
        if (get_criticality_tier(clause) == "critical" and norm_obl
                and not any(c.status in ("PRESENT", "PARTIAL") for c in norm_obl)
                and any(is_verified_failure(c) for c in norm_obl)):
            severity = "MAJOR"
    elif failures or partial:
        heavy = any(_heavy_partial(kb_reqs[c.requirement_id]) for c in partial)
        severity = "MINOR" if heavy else "OBSERVATION"
    elif unverified:
        severity = "OBSERVATION"
    else:
        severity = "CONFORMANT"

    # Una buona pratica non seguita non tocca la conformità (la norma non la chiede), ma il
    # rilievo lo dice: resta un'opportunità di miglioramento, così testo e gravità non si smentiscono.
    improvements = [c for c in kb_checks if kb_reqs[c.requirement_id].get("source") == "good_practice"
                    and c.status in ("PARTIAL", "ABSENT", "CONTRADICTED")]
    if improvements and obligations is not kb_checks:
        _note(gap, "Good practice beyond the requirements of the standard (opportunity for improvement, not a "
                   "nonconformity): "
                   + "; ".join(str(kb_reqs[c.requirement_id].get("text", ""))[:120].rstrip(".") for c in improvements[:3]) + ".")

    before = gap.severity
    gap.severity = severity
    gap.score = _score(severity, coverage if severity != "MAJOR" else 0.0)
    gap.is_spof = bool(clause.get("is_spof", False)) and severity == "MAJOR"
    gap.to_verify = [str(kb_reqs[c.requirement_id].get("text", c.requirement_id))[:220] for c in unverified]
    if gap.to_verify:
        _note(gap, "Some requirements were not found in the documents read: they are listed as points to "
                   "verify, not as nonconformities.")
    if _RANK.get(before, 0) > _RANK[severity]:
        _note(gap, f"Severity set from the requirement checks ({before.lower()} proposed by the screening).")
    return gap


def apply_all(gaps: List[ClauseGap], clauses: Dict[str, Dict[str, Any]]) -> List[ClauseGap]:
    return [apply(g, clauses.get(g.clause_id, {})) for g in gaps]
