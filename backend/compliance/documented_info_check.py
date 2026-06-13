"""
Amisys QHSE — Phase 2.6: Documented Information Coverage Check (Sprint R3).

Verifies that the documented information the standards OBLIGE the organisation
to maintain/retain actually exists somewhere in the analysed corpus.
Registry derived from the MAINTAIN/RETAIN columns of the audit checklists
(checklistevidence/TEMPLATE14001.docx) extended to all three norms with the
standards' own documented-information requirements.

Design — "deterministic" means the REGISTRY and the VERDICT RULES, never
filename matching. Recognition is semantic, in cascade:

  L1 — metadata match: Phase 2 already classified every document by READING
       it (doc_type, iso_clause_primary, summary). A file called
       "VDR_rev3_DEFINITIVO.pdf" is found as a risk_assessment regardless of
       its name.
  L2 — semantic match: query the chunk index with bilingual descriptors;
       above-threshold hits become FOUND_WEAK (candidate), never a verdict.
  L3 — absence confirmation: an item becomes ABSENT only after an LLM pass
       received the corpus summaries and answered "could any document serve
       as X under another name?" (defence against the false-negative
       "no risk assessments of any sort" scenario).

Output feeds: the result payload (DocumentedInfoReport), the per-clause
verdict context in Phase 3, and the report/UI.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger("compliance.documented_info")


# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry: what the norm requires to exist as documented information.
#   item:                human-readable name (UK English, used in report/UI)
#   clause_id:           internal clause id the item belongs to
#   retain_or_maintain:  "MAINTAIN" (living document) | "RETAIN" (record)
#   expected_doc_types:  Phase 2 whitelist values that satisfy the item
#   expected_clauses:    iso_clause_primary values (prefix match, e.g. "§5.2")
#   semantic_descriptors: EN+IT phrases for the L2 semantic query
#   risk_if_missing:     severity pull when ABSENT

_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    "ISO 9001:2015": [
        {
            "item": "Quality policy",
            "clause_id": "9001_5_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["policy"],
            "expected_clauses": ["§5.2"],
            "semantic_descriptors": ["quality policy statement commitment", "politica per la qualità impegno"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "QMS scope",
            "clause_id": "9001_4_3",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["quality_manual"],
            "expected_clauses": ["§4.3", "§4"],
            "semantic_descriptors": ["scope of the quality management system boundaries exclusions", "campo di applicazione del sistema di gestione qualità"],
            "risk_if_missing": "MINOR",
        },
        {
            "item": "Quality objectives",
            "clause_id": "9001_6_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["objective_plan"],
            "expected_clauses": ["§6.2"],
            "semantic_descriptors": ["quality objectives targets KPI indicators measurable goals", "obiettivi per la qualità traguardi indicatori"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Risk and opportunity register",
            "clause_id": "9001_6_1",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["risk_assessment"],
            "expected_clauses": ["§6.1"],
            "semantic_descriptors": ["risk register risks and opportunities assessment mitigation", "registro rischi e opportunità valutazione"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Competence / training records",
            "clause_id": "9001_7_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["training_record"],
            "expected_clauses": ["§7.2"],
            "semantic_descriptors": ["training records competence evidence qualification certificates", "registri formazione attestati competenze"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Monitoring and measurement results",
            "clause_id": "9001_9_1",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["record"],
            "expected_clauses": ["§9.1"],
            "semantic_descriptors": ["monitoring measurement results KPI report performance data", "risultati monitoraggio misurazione indicatori"],
            "risk_if_missing": "MINOR",
        },
        {
            "item": "Internal audit programme and reports",
            "clause_id": "9001_9_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["audit_report"],
            "expected_clauses": ["§9.2"],
            "semantic_descriptors": ["internal audit programme audit report findings", "programma audit interni rapporto verifica ispettiva"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Management review minutes",
            "clause_id": "9001_9_3",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["management_review"],
            "expected_clauses": ["§9.3"],
            "semantic_descriptors": ["management review minutes inputs outputs decisions", "riesame della direzione verbale"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Nonconformity and corrective action records",
            "clause_id": "9001_10_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["nonconformity_record"],
            "expected_clauses": ["§10.2"],
            "semantic_descriptors": ["nonconformity corrective action record root cause", "non conformità azioni correttive registro"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Supplier evaluation records",
            "clause_id": "9001_8_4",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["supplier_document"],
            "expected_clauses": ["§8.4"],
            "semantic_descriptors": ["approved supplier list supplier evaluation qualification", "elenco fornitori qualificati valutazione fornitori"],
            "risk_if_missing": "MINOR",
        },
    ],
    "ISO 14001:2015": [
        {
            "item": "Environmental policy",
            "clause_id": "14001_5_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["policy"],
            "expected_clauses": ["§5.2"],
            "semantic_descriptors": ["environmental policy commitment pollution prevention", "politica ambientale impegno prevenzione inquinamento"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Significant environmental aspects register",
            "clause_id": "14001_6_1_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["risk_assessment"],
            "expected_clauses": ["§6.1.2", "§6.1"],
            "semantic_descriptors": ["environmental aspects impacts register significance evaluation", "aspetti ambientali impatti registro significatività"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Compliance obligations register",
            "clause_id": "14001_6_1_3",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["legal_register"],
            "expected_clauses": ["§6.1.3"],
            "semantic_descriptors": ["legal register compliance obligations environmental legislation", "registro prescrizioni legali obblighi conformità normativa ambientale"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Environmental objectives",
            "clause_id": "14001_6_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["objective_plan"],
            "expected_clauses": ["§6.2"],
            "semantic_descriptors": ["environmental objectives targets programme indicators", "obiettivi ambientali traguardi programma"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Emergency preparedness and response plan",
            "clause_id": "14001_8_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["emergency_plan"],
            "expected_clauses": ["§8.2"],
            "semantic_descriptors": ["emergency preparedness response plan drill", "piano di emergenza prove di evacuazione"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Monitoring results and compliance evaluation",
            "clause_id": "14001_9_1",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["record"],
            "expected_clauses": ["§9.1"],
            "semantic_descriptors": ["environmental monitoring results compliance evaluation", "monitoraggio ambientale valutazione conformità"],
            "risk_if_missing": "MINOR",
        },
        {
            "item": "Internal audit programme and reports",
            "clause_id": "14001_9_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["audit_report"],
            "expected_clauses": ["§9.2"],
            "semantic_descriptors": ["internal audit programme report EMS", "programma audit interni ambientale rapporto"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Management review minutes",
            "clause_id": "14001_9_3",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["management_review"],
            "expected_clauses": ["§9.3"],
            "semantic_descriptors": ["management review minutes environmental performance", "riesame della direzione verbale ambientale"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Nonconformity and corrective action records",
            "clause_id": "14001_10_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["nonconformity_record"],
            "expected_clauses": ["§10.2"],
            "semantic_descriptors": ["nonconformity corrective action environmental record", "non conformità ambientali azioni correttive"],
            "risk_if_missing": "MAJOR",
        },
    ],
    "ISO 45001:2018": [
        {
            "item": "OH&S policy",
            "clause_id": "45001_5_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["policy"],
            "expected_clauses": ["§5.2"],
            "semantic_descriptors": ["health and safety policy commitment injury prevention", "politica salute sicurezza impegno prevenzione infortuni"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Hazard identification and OH&S risk assessment",
            "clause_id": "45001_6_1_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["risk_assessment"],
            "expected_clauses": ["§6.1.2", "§6.1"],
            "semantic_descriptors": ["hazard identification risk assessment occupational safety DVR", "valutazione dei rischi DVR pericoli mansioni"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Legal and other requirements register",
            "clause_id": "45001_6_1_3",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["legal_register"],
            "expected_clauses": ["§6.1.3"],
            "semantic_descriptors": ["legal requirements register health safety legislation", "registro prescrizioni legali sicurezza D.Lgs 81"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "OH&S objectives",
            "clause_id": "45001_6_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["objective_plan"],
            "expected_clauses": ["§6.2"],
            "semantic_descriptors": ["OH&S objectives safety targets accident rate KPI", "obiettivi sicurezza indicatori infortuni"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Worker consultation and participation records",
            "clause_id": "45001_5_4",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["communication_record", "record"],
            "expected_clauses": ["§5.4"],
            "semantic_descriptors": ["worker consultation participation safety committee minutes RLS", "consultazione partecipazione lavoratori riunione periodica RLS"],
            "risk_if_missing": "MINOR",
        },
        {
            "item": "Emergency preparedness and response plan",
            "clause_id": "45001_8_2",
            "retain_or_maintain": "MAINTAIN",
            "expected_doc_types": ["emergency_plan"],
            "expected_clauses": ["§8.2"],
            "semantic_descriptors": ["emergency plan evacuation first aid fire drill", "piano emergenza evacuazione antincendio primo soccorso"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Competence / training records",
            "clause_id": "45001_7_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["training_record"],
            "expected_clauses": ["§7.2"],
            "semantic_descriptors": ["safety training records certificates competence", "attestati formazione sicurezza registri"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Internal audit programme and reports",
            "clause_id": "45001_9_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["audit_report"],
            "expected_clauses": ["§9.2"],
            "semantic_descriptors": ["internal audit programme OH&S report", "programma audit interni sicurezza rapporto"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Management review minutes",
            "clause_id": "45001_9_3",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["management_review"],
            "expected_clauses": ["§9.3"],
            "semantic_descriptors": ["management review minutes OH&S performance", "riesame della direzione verbale sicurezza"],
            "risk_if_missing": "MAJOR",
        },
        {
            "item": "Incident, nonconformity and corrective action records",
            "clause_id": "45001_10_2",
            "retain_or_maintain": "RETAIN",
            "expected_doc_types": ["nonconformity_record"],
            "expected_clauses": ["§10.2"],
            "semantic_descriptors": ["incident report near miss nonconformity corrective action", "registro infortuni near miss non conformità azioni correttive"],
            "risk_if_missing": "MAJOR",
        },
    ],
}

# L2 semantic distance threshold (cosine distance — lower is closer). Hits
# above this are not credible enough even for FOUND_WEAK.
_SEMANTIC_DISTANCE_MAX = 0.95


# ── Public API ────────────────────────────────────────────────────────────────

def run_documented_info_check(
    cards: List[Dict[str, Any]],
    norms: List[str],
    evidence_service=None,
    llm_call: Optional[Callable[[List[Dict[str, str]]], str]] = None,
    emitter: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Phase 2.6 entry point.

    Args:
        cards:            parsed Phase 2 evidence cards
        norms:            norms under assessment (registry keys)
        evidence_service: optional EvidenceService over the chunk index (L2)
        llm_call:         optional callable(messages) -> str for L3 absence
                          confirmation (gap_analyzer._call_llm signature)
        emitter:          optional SSE progress callback

    Returns a dict serialisable to schemas.DocumentedInfoReport.
    """
    def emit(pct: float, msg: str) -> None:
        if emitter:
            try:
                emitter(pct, msg)
            except Exception:
                pass

    items: List[Dict[str, Any]] = []
    for norm in norms:
        for entry in _REGISTRY.get(norm, []):
            items.append({**entry, "norm": norm})

    emit(39.0, f"Phase 2.6: checking {len(items)} required documented-information items…")

    results: List[Dict[str, Any]] = []
    absent_candidates: List[Dict[str, Any]] = []

    for entry in items:
        match = _match_l1_metadata(entry, cards)
        if match is not None:
            results.append(_result_row(entry, "FOUND", match, "metadata"))
            continue

        if evidence_service is not None:
            match = _match_l2_semantic(entry, evidence_service)
            if match is not None:
                results.append(_result_row(entry, "FOUND_WEAK", match, "semantic"))
                continue

        # L3 candidate — absence must be confirmed before being declared.
        absent_candidates.append(entry)

    if absent_candidates:
        confirmed_absent, rescued = _confirm_absences_l3(
            absent_candidates, cards, llm_call,
        )
        for entry, match in rescued:
            results.append(_result_row(entry, "FOUND_WEAK", match, "llm_rescued"))
        for entry in confirmed_absent:
            results.append(_result_row(entry, "ABSENT", None, "llm_confirmed_absent" if llm_call else "not_found"))

    found = sum(1 for r in results if r["status"] == "FOUND")
    weak = sum(1 for r in results if r["status"] == "FOUND_WEAK")
    absent = sum(1 for r in results if r["status"] == "ABSENT")
    emit(41.0, f"Phase 2.6 complete: {found} found, {weak} weak matches, {absent} absent.")

    return {
        "items": results,
        "found_count": found,
        "weak_count": weak,
        "absent_count": absent,
    }


def absent_items_by_clause(report: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Group ABSENT items by clause_id — consumed by Phase 3 verdict context."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in report.get("items", []):
        if row.get("status") == "ABSENT":
            out.setdefault(str(row.get("clause_id", "")), []).append(row)
    return out


# ── Matchers ──────────────────────────────────────────────────────────────────

def _match_l1_metadata(
    entry: Dict[str, Any],
    cards: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    L1 — match on the LLM-derived classification of each card. Two signals,
    both content-derived (never filenames):
      a) doc_type in expected_doc_types
      b) iso_clause_primary/secondary matching expected_clauses for the norm
    """
    norm_label = entry["norm"].rsplit(":", 1)[0]  # "ISO 9001:2015" → "ISO 9001"

    for card in cards:
        if not card.get("readable", True):
            continue
        doc_type = str(card.get("doc_type", "") or "").lower().strip()
        if doc_type in entry["expected_doc_types"]:
            return card

    for card in cards:
        if not card.get("readable", True):
            continue
        clauses = [str(card.get("iso_clause_primary", "") or "")]
        clauses += [str(c) for c in (card.get("iso_clauses_secondary") or [])]
        for ref in clauses:
            if norm_label not in ref:
                continue
            if any(exp in ref for exp in entry["expected_clauses"]):
                return card
    return None


def _match_l2_semantic(entry: Dict[str, Any], evidence_service) -> Optional[Dict[str, Any]]:
    """L2 — bilingual semantic query over the chunk index."""
    try:
        query = " ".join(entry["semantic_descriptors"])
        hits = evidence_service.get_evidences_similar_to(query, n=3)
    except Exception:
        return None
    for hit in hits or []:
        if float(hit.get("distance", 99.0)) <= _SEMANTIC_DISTANCE_MAX:
            return hit
    return None


def _confirm_absences_l3(
    candidates: List[Dict[str, Any]],
    cards: List[Dict[str, Any]],
    llm_call: Optional[Callable[[List[Dict[str, str]]], str]],
):
    """
    L3 — single LLM call: present the corpus (file_name, doc_type, one-line
    summary per card) and the candidate items; ask whether any document could
    serve each item under another name. Items the LLM maps to a real
    evidence_id are rescued as FOUND_WEAK; the rest are confirmed ABSENT.

    Without an llm_call (tests, offline), all candidates are returned absent.
    """
    if not llm_call or not candidates or not cards:
        return candidates, []

    corpus_lines = []
    by_eid = {}
    for c in cards:
        eid = str(c.get("evidence_id", "") or "")
        if not eid:
            continue
        by_eid[eid] = c
        summary = str(c.get("summary", "") or "").replace("\n", " ")[:160]
        corpus_lines.append(
            f"- {eid} | {c.get('file_name','')} | {c.get('doc_type','other')} | {summary}"
        )

    items_lines = [
        f'- "{e["item"]}" (norm {e["norm"]}) — typical forms: {", ".join(e["semantic_descriptors"])}'
        for e in candidates
    ]

    sys_prompt = (
        "You are a compliance documentation analyst. You receive (1) the list "
        "of documents found in a company's documentation package, each with an "
        "id, original file name, classified type and a one-line summary, and "
        "(2) a list of REQUIRED documented-information items that an initial "
        "automated match did not find.\n\n"
        "Organisations name documents in many different ways. For each required "
        "item, decide whether any document in the list could plausibly serve as "
        "that item under another name, based on the summaries and types — never "
        "on wishful thinking. Respond ONLY with a JSON object mapping each "
        "required item name to either the evidence id of the matching document "
        "or null. No markdown fences, no commentary."
    )
    user_prompt = (
        "## Documents in the package\n" + "\n".join(corpus_lines)
        + "\n\n## Required items not yet matched\n" + "\n".join(items_lines)
        + "\n\nReturn: {\"<item name>\": \"<evidence_id or null>\", ...}"
    )

    try:
        raw = llm_call([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ])
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        mapping = json.loads(text)
        if not isinstance(mapping, dict):
            raise ValueError("not a dict")
    except Exception as e:
        _log.warning("[Phase 2.6] L3 absence confirmation failed: %s", e)
        return candidates, []

    confirmed: List[Dict[str, Any]] = []
    rescued: List[tuple] = []
    for entry in candidates:
        eid = mapping.get(entry["item"])
        card = by_eid.get(str(eid)) if eid else None
        if card is not None:
            rescued.append((entry, card))
        else:
            confirmed.append(entry)
    return confirmed, rescued


# ── Row builder ───────────────────────────────────────────────────────────────

def _result_row(
    entry: Dict[str, Any],
    status: str,
    match: Optional[Dict[str, Any]],
    method: str,
) -> Dict[str, Any]:
    return {
        "item":                entry["item"],
        "clause_id":           entry["clause_id"],
        "norm":                entry["norm"],
        "retain_or_maintain":  entry["retain_or_maintain"],
        "status":              status,
        "matched_evidence_id": str(match.get("evidence_id", "")) if match else None,
        "matched_file_name":   str(match.get("file_name", "")) if match else None,
        "match_method":        method,
        "risk_if_missing":     entry["risk_if_missing"],
    }
