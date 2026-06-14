"""
Amisys QHSE — Phase 3 Stage B: Deep Verification (Sprint R4).

The screening pass (Stage A, batched) judges every clause on retrieved chunk
excerpts. This module re-verifies the clauses that matter on the FULL TEXT of
their most relevant documents, producing per-requirement PRESENT/PARTIAL/
ABSENT checks with verbatim quotes and real page numbers.

This is what makes the engine's promises literally true:
  P2 — risk criteria applied vs declared
  P3 — MR minutes mapped against §9.3 required inputs/outputs
  P4 — policy commitments verified in the wording
  P5 — objectives checked for metric/target/deadline
  P9 — hedged verdicts instead of forced matches

Selection policy (decision: quality first):
  - every clause with `atomic_requirements`, plus
  - every critical/SPoF clause, plus
  - any Stage A verdict with confidence below DEEP_CONFIDENCE_THRESHOLD.

Failure policy: a failed deep verification NEVER degrades the Stage A
verdict — the gap simply keeps `deep_verified=False`.
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from compliance.clause_helpers import get_criticality_tier
from compliance.schemas import ClauseGap, RequirementCheck, TraceabilityLink

_log = logging.getLogger("compliance.deep_verifier")


# ── Tuning ────────────────────────────────────────────────────────────────────

# 6 worker × 3 norme in parallelo ≈ 18 call concorrenti da ~15-25k token:
# in-flight ~450k token, dentro la quota 3M TPM del deployment gpt-4.1
# (Data Zone EU). Override via env per quote diverse.
DEEP_MAX_WORKERS = int(os.environ.get("DEEP_MAX_WORKERS", "6"))
DEEP_MAX_DOCS = 3                 # full documents per clause prompt
DEEP_MAX_DOC_CHARS = 60_000       # per-document cap inside the prompt
DEEP_MAX_OUTPUT_TOKENS = 3000
DEEP_CONFIDENCE_THRESHOLD = 0.6   # Stage A confidence below this → deep pass

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "compliance" / "deep_verification.md"


def _sample_long_doc(text: str, cap: int = DEEP_MAX_DOC_CHARS) -> str:
    """Hardening 2026 (raffinamento) — testa+coda per i documenti molto lunghi.

    La deep-verification prendeva solo i primi `cap` caratteri di ogni documento:
    per un DVR da 224k char vedeva il ~27% e la CODA (registri rischi, conclusioni,
    obiettivi, azioni) non entrava mai nell'analisi. Per i doc oltre il cap prendiamo
    testa (60%) + coda (40%) con un marcatore, così l'intero arco del documento
    informa la verifica. I doc sotto il cap restano integri.
    """
    text = text or ""
    if len(text) <= cap:
        return text
    head = int(cap * 0.6)
    tail = cap - head
    return (text[:head].rstrip()
            + "\n\n[… omitted middle section — head and tail shown …]\n\n"
            + text[-tail:].lstrip())


# ── Selection ─────────────────────────────────────────────────────────────────

def should_deep_verify(clause: Dict[str, Any], gap: ClauseGap) -> bool:
    """Quality-first selection: atomic_requirements OR critical OR uncertain.

    Le clausole SENZA atomic_requirements (periferiche) non vengono deep-verificate:
    i loro verdotti vengono confinati nella banda media da
    `gap_analyzer._confine_peripheral_clause` (Hardening 2026 #1) — i verdetti forti
    (MAJOR/CONFORMANT) sono riservati alle clausole con checklist curata, dove la
    deep-verification + il credito parziale li giustificano.
    """
    if clause.get("atomic_requirements"):
        return True
    if clause.get("is_spof") or get_criticality_tier(clause) == "critical":
        return True
    if gap.confidence is not None and gap.confidence < DEEP_CONFIDENCE_THRESHOLD:
        return True
    return False


# ── Partial credit (calibrazione 2026-06-14, Opzione B) ───────────────────────

# Copertura minima degli atomic requirements (PRESENT pesa 1, PARTIAL 0.5) per
# concedere il declassamento MAJOR→MINOR. Un requisito pienamente PRESENT
# declassa sempre (il processo è dimostrato); altrimenti basta una copertura
# ≥ soglia. Solo le assenze sostanziali restano MAJOR.
PARTIAL_CREDIT_MIN_COVERAGE = 0.10


def _apply_partial_credit(gap: "ClauseGap") -> "ClauseGap":
    """Opzione B — credito parziale, applicato DOPO il severity_floor.

    Quando gli atomic requirements mostrano un processo ALMENO parzialmente
    evidenziato (≥1 PRESENT/PARTIAL e copertura ≥ soglia), un verdetto MAJOR
    derivante solo dall'assenza di documenti-di-sistema viene declassato a
    MINOR, con score reattivo alla copertura. Distingue 'processo inesistente'
    (resta MAJOR) da 'record presenti ma procedura non documentata/non caricata'
    (MINOR). Le assenze totali (0 PRESENT, 0 PARTIAL, o copertura < soglia)
    restano MAJOR.

    Non tocca i verdetti già ≤ MINOR; non promuove mai oltre MINOR (no falsi
    positivi al contrario)."""
    checks = gap.requirement_checks or []
    if gap.severity != "MAJOR" or not checks:
        return gap

    present = sum(1 for c in checks if getattr(c, "status", "") == "PRESENT")
    partial = sum(1 for c in checks if getattr(c, "status", "") == "PARTIAL")
    total = len(checks)
    if total == 0 or (present + partial) == 0:
        return gap  # assenza totale → resta MAJOR

    coverage = (present + 0.5 * partial) / total
    # Un requisito pienamente PRESENT declassa sempre; altrimenti serve la
    # copertura minima (evita che 1 PARTIAL su 15 salvi una clausola quasi vuota).
    if present == 0 and coverage < PARTIAL_CREDIT_MIN_COVERAGE:
        return gap  # processo quasi inesistente → resta MAJOR

    # Declassa a MINOR con score reattivo alla copertura (banda 32-59).
    gap.severity = "MINOR"
    gap.score = max(gap.score, min(59, 32 + round(coverage * 27)))
    gap.hedged = True
    note = ("Process partially evidenced (some requirements demonstrated): "
            "downgraded from major to minor. Provide the governing documented "
            "procedure to close the gap.")
    gap.hedge_note = (gap.hedge_note + " " + note).strip() if gap.hedge_note else note
    return gap


# ── Public entry point ────────────────────────────────────────────────────────

def run_deep_verification(
    norm: str,
    gaps: List[ClauseGap],
    clauses: Dict[str, Dict[str, Any]],
    docs_by_name: Dict[str, str],
    cards_by_id: Dict[str, Dict[str, Any]],
    evidence_service,
    context_block: str,
    llm_call: Callable[[List[Dict[str, str]], int], str],
    apply_floor: Callable[[ClauseGap, Dict[str, Any], List], ClauseGap],
    emit: Optional[Callable[[float, str], None]] = None,
    pct_base: float = 0.0,
    pct_budget: float = 0.0,
    risk_register_text: str = "",
    tagged_docs_by_clause: Optional[Dict[str, List[str]]] = None,
) -> List[ClauseGap]:
    """
    Re-verify the selected gaps in place. Returns the (same) list with
    deep-verified gaps replaced.

    Args:
        norm:            norm label ("ISO 9001:2015")
        gaps:            Stage A ClauseGap list for this norm
        clauses:         the norm's clause registry
        docs_by_name:    normalised file name → full extracted text
        cards_by_id:     evidence_id → Phase 2 card
        evidence_service: chunk retrieval (used to pick documents when the
                          Stage A citations are too thin)
        context_block:   company context block for the system prompt
        llm_call:        callable(messages, max_tokens) -> raw text
        apply_floor:     gap_analyzer._apply_severity_floor (avoids circular import)
        emit/pct_*:      SSE progress
    """
    if not docs_by_name:
        _log.info("[Deep] No document texts available — skipping Stage B for %s", norm)
        return gaps

    def _emit(pct: float, msg: str) -> None:
        if emit:
            try:
                emit(pct, msg)
            except Exception:
                pass

    try:
        prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        _log.warning("[Deep] prompt missing (%s) — skipping Stage B", e)
        return gaps

    system_prompt = prompt_template.replace("{company_context}", context_block)

    # Map evidence_id → file name and build the file-name lookup used to
    # resolve citations back to evidence ids.
    eid_to_fname: Dict[str, str] = {
        eid: str(card.get("file_name", "") or "")
        for eid, card in cards_by_id.items()
    }
    fname_to_eid: Dict[str, str] = {
        _norm_name(fn): eid for eid, fn in eid_to_fname.items() if fn
    }

    targets = [
        (i, gap) for i, gap in enumerate(gaps)
        if gap.clause_id in clauses and should_deep_verify(clauses[gap.clause_id], gap)
    ]
    if not targets:
        return gaps

    total = len(targets)
    _emit(pct_base, f"{norm}: deep verification on {total} clauses…")

    done = [0]

    def _verify_one(idx: int, gap: ClauseGap) -> None:
        clause = clauses[gap.clause_id]
        try:
            new_gap = _deep_verify_clause(
                clause=clause,
                gap=gap,
                docs_by_name=docs_by_name,
                fname_to_eid=fname_to_eid,
                evidence_service=evidence_service,
                system_prompt=system_prompt,
                llm_call=llm_call,
                risk_register_text=risk_register_text,
                tagged_docs=(tagged_docs_by_clause or {}).get(gap.clause_id, []),
            )
            if new_gap is not None:
                gaps[idx] = _apply_partial_credit(apply_floor(new_gap, clause, []))
        except Exception as e:
            _log.warning("[Deep] %s failed (%s) — keeping Stage A verdict",
                         gap.clause_id, str(e)[:200])
        done[0] += 1
        if pct_budget:
            _emit(pct_base + pct_budget * done[0] / total,
                  f"{norm}: deep verification {done[0]}/{total}…")

    with ThreadPoolExecutor(max_workers=min(DEEP_MAX_WORKERS, total)) as pool:
        futures = [pool.submit(_verify_one, idx, gap) for idx, gap in targets]
        for f in futures:
            f.result()

    return gaps


# ── Single-clause verification ────────────────────────────────────────────────

def _deep_verify_clause(
    clause: Dict[str, Any],
    gap: ClauseGap,
    docs_by_name: Dict[str, str],
    fname_to_eid: Dict[str, str],
    evidence_service,
    system_prompt: str,
    llm_call: Callable,
    risk_register_text: str = "",
    tagged_docs: Optional[List[str]] = None,
) -> Optional[ClauseGap]:
    doc_names = _select_documents(clause, gap, docs_by_name, evidence_service, tagged_docs)
    if not doc_names:
        return None  # nothing to read in full — keep Stage A verdict

    user_prompt = _build_user_prompt(clause, gap, doc_names, docs_by_name)

    # Sprint R8 (P2) — risk-planning clauses also receive the structured
    # register extracted in Phase 2.7, so "criteria applied vs declared" is
    # judged on per-entry data, not impressions.
    if risk_register_text and _is_risk_clause(clause):
        user_prompt = risk_register_text + "\n\n" + user_prompt
    raw = llm_call(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        DEEP_MAX_OUTPUT_TOKENS,
    )

    data = _parse_json(raw)
    if data is None:
        # One re-ask before giving up (mirrors Stage A policy).
        raw = llm_call(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            DEEP_MAX_OUTPUT_TOKENS,
        )
        data = _parse_json(raw)
        if data is None:
            _log.warning("[Deep] %s: unparseable response twice — keeping Stage A",
                         clause.get("id"))
            return None

    return _merge_verdict(clause, gap, data, doc_names, fname_to_eid)


def _select_documents(
    clause: Dict[str, Any],
    gap: ClauseGap,
    docs_by_name: Dict[str, str],
    evidence_service,
    tagged_docs: Optional[List[str]] = None,
) -> List[str]:
    """
    Pick up to DEEP_MAX_DOCS documents to read in full, in priority order:
      1. documents the Phase 2 cards TAGGED on this clause (iso_clause_primary/
         secondary) — the most reliably clause-relevant (Hardening 2026 #3 raffin.);
      2. documents already cited by Stage A;
      3. chunk-retrieval hits for breadth.
    Per le clausole genuinamente assenti non esistono card taggate → si ricade su
    (2)+(3), comportamento invariato. Returns normalised keys present in docs_by_name.
    """
    chosen: List[str] = []

    def _add(fname: Any) -> bool:
        key = _norm_name(str(fname or ""))
        if key in docs_by_name and key not in chosen:
            chosen.append(key)
        return len(chosen) >= DEEP_MAX_DOCS

    for fn in (tagged_docs or []):
        if _add(fn):
            return chosen

    for src in gap.sources:
        if _add(src.file_name):
            return chosen

    if evidence_service is not None and len(chosen) < DEEP_MAX_DOCS:
        try:
            hits = evidence_service.get_evidences_for_clause(clause, n=8)
        except Exception:
            hits = []
        for hit in hits:
            if _add(hit.get("file_name", "")):
                break

    return chosen


def _build_user_prompt(
    clause: Dict[str, Any],
    gap: ClauseGap,
    doc_names: List[str],
    docs_by_name: Dict[str, str],
) -> str:
    parts: List[str] = [
        f"## Clause to verify: {clause['id']}",
        f"- title: {clause['title']}",
        f"- area: {clause.get('area', '')}",
        f"- is_spof: {clause.get('is_spof', False)}",
        "",
        "## Atomic requirements (verify each one)",
    ]
    atomic = clause.get("atomic_requirements") or []
    if atomic:
        for req in atomic:
            parts.append(f"- id: {req.get('id', '')}")
            parts.append(f"  text: {req.get('text', '')}")
            hint = req.get("verification_hint", "")
            if hint:
                parts.append(f"  verification_hint: {hint}")
            parts.append(f"  risk_if_missing: {req.get('risk_if_missing', 'MINOR')}")
    else:
        parts.append(
            "(no atomic checklist for this clause — derive 3-6 verifiable "
            "requirements from the clause itself, give them ids "
            f"'{clause['id']}.derived.N', and verify those)"
        )

    parts += [
        "",
        "## Screening verdict (context only — you may overturn it)",
        f"- severity: {gap.severity}, score: {gap.score}",
        f"- finding: {gap.finding[:300]}",
        "",
        f"## Documents ({len(doc_names)} full texts)",
    ]
    for key in doc_names:
        text = _sample_long_doc(docs_by_name.get(key, ""), DEEP_MAX_DOC_CHARS)
        parts.append(f"### DOCUMENT: {key}")
        parts.append(text)
        parts.append("")

    parts.append(
        "Apply the verification protocol and return the JSON object as instructed."
    )
    return "\n".join(parts)


# ── Verdict merge ─────────────────────────────────────────────────────────────

_VALID_SEVERITIES = ("MAJOR", "MINOR", "OBSERVATION", "CONFORMANT")
_VALID_CHECK_STATUS = ("PRESENT", "PARTIAL", "ABSENT")


def _merge_verdict(
    clause: Dict[str, Any],
    stage_a: ClauseGap,
    data: Dict[str, Any],
    doc_names: List[str],
    fname_to_eid: Dict[str, str],
) -> ClauseGap:
    """Build the deep-verified ClauseGap, citing only the documents provided."""
    severity = str(data.get("severity", "")).upper()
    if severity not in _VALID_SEVERITIES:
        severity = stage_a.severity
    score = max(0, min(100, int(data.get("score", stage_a.score))))

    confidence = data.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = None

    # Requirement checks — cite-or-fail on file names: quotes may only come
    # from the documents we actually provided.
    valid_keys = set(doc_names)
    requirements_by_id = {
        str(r.get("id", "")): r for r in (clause.get("atomic_requirements") or [])
    }
    checks: List[RequirementCheck] = []
    wording_downgrades: List[tuple] = []  # (requirement_id, risk_if_missing)
    for item in (data.get("requirement_checks") or []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).upper()
        if status not in _VALID_CHECK_STATUS:
            continue
        fname = item.get("file_name")
        fkey = _norm_name(str(fname)) if fname else None
        if fkey is not None and fkey not in valid_keys:
            _log.warning("[Deep] %s: check cites unknown document %r — dropping quote",
                         clause.get("id"), fname)
            fname, fkey = None, None
            item["evidence_quote"] = None
            item["pages"] = []
        pages = [int(p) for p in (item.get("pages") or []) if str(p).isdigit() or isinstance(p, int)]
        quote = item.get("evidence_quote")
        req_id = str(item.get("requirement_id", "") or f"{clause['id']}.unnamed")
        note = str(item.get("note"))[:200] if item.get("note") else None

        # Sprint R7 — deterministic wording verification. The LLM can be
        # confidently wrong here (observed: improvement commitment marked
        # PRESENT quoting the objectives-framework sentence). When the
        # requirement declares `wording_keywords`, a PRESENT/PARTIAL status
        # must be backed by a quote containing ≥1 term from EVERY group;
        # otherwise the check is downgraded to ABSENT — Python decides, not
        # the model. Same philosophy as cite-or-fail.
        requirement = requirements_by_id.get(req_id)
        if (
            requirement is not None
            and requirement.get("wording_keywords")
            and status == "PRESENT"
        ):
            if not _quote_satisfies_wording(quote, requirement["wording_keywords"]):
                _log.warning(
                    "[Deep] %s: %s marked PRESENT but the supporting quote does "
                    "not contain the required wording — downgrading to PARTIAL",
                    clause.get("id"), req_id,
                )
                status = "PARTIAL"
                note = (
                    "The quoted evidence does not appear to contain the required "
                    "commitment wording — review the document text directly."
                )
                wording_downgrades.append(
                    (req_id, str(requirement.get("risk_if_missing", "MINOR")))
                )

        checks.append(RequirementCheck(
            requirement_id=req_id,
            status=status,
            evidence_quote=(str(quote)[:300] if quote else None),
            pages=pages,
            file_name=(str(fname) if fname else None),
            note=note,
        ))

    # Severity re-derivation after wording downgrades. The verifier caught the
    # model citing text that does not contain the prescribed commitment: the
    # verdict can no longer claim full conformity on that item. Taxonomy: the
    # document exists, one prescribed element is unconfirmed — punctual gap
    # (MINOR when the item is MAJOR-risk, OBSERVATION otherwise), hedged so
    # the manager knows to read the wording personally.
    if wording_downgrades:
        worst = "MAJOR" if any(r == "MAJOR" for _, r in wording_downgrades) else "MINOR"
        if severity in ("CONFORMANT", "OBSERVATION"):
            severity = "MINOR" if worst == "MAJOR" else "OBSERVATION"
        score = min(score, 59 if severity == "MINOR" else 84)
        if confidence is not None:
            confidence = min(confidence, 0.7)
        data["hedged"] = True
        downgraded_names = ", ".join(rid.split(".", 1)[-1].replace("_", " ")
                                     for rid, _ in wording_downgrades)
        existing_hn = str(data.get("hedge_note") or "").strip()
        data["hedge_note"] = (existing_hn + (" " if existing_hn else "") + (
            f"The evidence cited for '{downgraded_names}' does not clearly "
            f"contain the required commitment wording — verify the document "
            f"text directly."
        )).strip()

    # Sources: documents that supported at least one PRESENT/PARTIAL check.
    sources: List[TraceabilityLink] = []
    seen_files: set = set()
    for chk in checks:
        if chk.status == "ABSENT" or not chk.file_name:
            continue
        fkey = _norm_name(chk.file_name)
        if fkey in seen_files:
            continue
        seen_files.add(fkey)
        sources.append(TraceabilityLink(
            evidence_id=fname_to_eid.get(fkey, f"doc::{fkey}"),
            file_name=chk.file_name,
            pages=chk.pages,
            excerpt=(chk.evidence_quote or "")[:280],
            relevance_score=confidence if confidence is not None else 0.7,
            summary=None,
        ))
    # Hardening 2026 #6 — fonti oneste: ripieghiamo sulle citazioni Stage A SOLO se
    # la deep-verification non ha prodotto alcun check (Stage B non ha potuto
    # giudicare). Se invece i check esistono e sono TUTTI ABSENT, è un'assenza
    # genuina → nessuna fonte (prima ereditava le citazioni Stage A, spesso vicini
    # semantici irrilevanti allegati a un finding "nulla trovato").
    if not sources and not checks:
        sources = stage_a.sources

    # Two-level remediation (PRD 1.4.7) with template fallbacks.
    rem = data.get("remediation") or {}
    template = clause.get("remediation_template", {})
    when_fallback = template.get("when_major") if severity == "MAJOR" else template.get("when_minor")
    correction = str(rem.get("correction") or "").strip() or None
    corrective = str(rem.get("corrective_action") or "").strip() or None
    remediation = stage_a.remediation.model_copy(update={
        "what": corrective or correction or stage_a.remediation.what,
        "who": str(rem.get("who") or "").strip() or stage_a.remediation.who,
        "when": str(rem.get("when") or "").strip() or when_fallback or stage_a.remediation.when,
        "effort": str(rem.get("effort") or "").strip().upper() or stage_a.remediation.effort,
        "correction": correction,
        "corrective_action": corrective,
    })
    if remediation.effort not in ("LOW", "MEDIUM", "HIGH"):
        remediation.effort = stage_a.remediation.effort

    finding = str(data.get("finding") or "").strip()[:900] or stage_a.finding

    hedged = bool(data.get("hedged", False))
    hedge_note = data.get("hedge_note")
    hedge_note = str(hedge_note)[:300] if hedged and hedge_note else None

    return ClauseGap(
        clause_id=stage_a.clause_id,
        clause_title=stage_a.clause_title,
        score=score,
        severity=severity,
        is_spof=bool(clause.get("is_spof", False)) and severity == "MAJOR",
        finding=finding,
        sources=sources,
        remediation=remediation,
        confidence=confidence,
        requirement_checks=checks,
        hedged=hedged,
        hedge_note=hedge_note,
        deep_verified=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_RISK_CLAUSE_RE = re.compile(r"_6_1(?:_[12])?$")


def _is_risk_clause(clause: Dict[str, Any]) -> bool:
    """§6.1 / 6.1.1 / 6.1.2 of any norm — the risk-planning clauses."""
    return bool(_RISK_CLAUSE_RE.search(str(clause.get("id", ""))))


def _quote_satisfies_wording(quote: Any, keyword_groups: List[List[str]]) -> bool:
    """
    Sprint R7 — sanity net for wording-type requirements, NOT a recognition
    mechanism. The LLM reads the whole document semantically and selects the
    quote; this function only validates that the quote it cited as proof of a
    prescribed commitment plausibly contains that commitment (≥1 stem from
    every group, case-insensitive, EN+IT stems). It can only flag a suspect
    PRESENT for review — it never creates a match by keywords.
    """
    if not quote or not str(quote).strip():
        return False
    text = str(quote).lower()
    for group in keyword_groups:
        if not any(str(kw).lower() in text for kw in group):
            return False
    return True


def _norm_name(name: str) -> str:
    n = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\s+", " ", n).strip().lower()


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.rstrip())
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
