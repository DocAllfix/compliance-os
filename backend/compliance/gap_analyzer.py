"""
Amisys QHSE — Real Gap Analyser (Phase 3).

Pipeline:
  1. Parse evidence YAML → list of card dicts
  2. Index cards in ChromaDB (EvidenceEmbedder)
  3. For each norm → for each clause:
       a. Query ChromaDB for relevant evidence
       b. Build prompt (base + norm-specific)
       c. Call Azure GPT-4.1-mini (streaming, retry/backoff, Azure-only)
       d. Parse JSON response → ClauseGap (Pydantic)
  4. Aggregate into NormGapReport → ComplianceAnalysisResult
  5. Emit SSE progress events throughout

Emitter contract:
  emitter(pct: float, msg: str)  — simple callable or None
  (The SSE endpoint wraps a real SSEEmitter; stubs pass a plain lambda)
"""
from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from compliance.clause_helpers import (
    get_criticality_tier,
    get_severity_floor,
)
from compliance.embedder import EvidenceEmbedder
from compliance.evidence_service import EvidenceService
from compliance.iso_clauses.iso9001_clauses import (
    ISO9001_CLAUSES,
    ISO9001_HIGH_FREQUENCY_CLAUSES,
)
from compliance.iso_clauses.iso14001_clauses import (
    ISO14001_CLAUSES,
    ISO14001_HIGH_FREQUENCY_CLAUSES,
)
from compliance.iso_clauses.iso45001_clauses import (
    ISO45001_CLAUSES,
    ISO45001_HIGH_FREQUENCY_CLAUSES,
)
from compliance.schemas import (
    ClauseGap,
    CompanyContext,
    ComplianceAnalysisResult,
    NormGapReport,
    RemediationPlan,
    TraceabilityLink,
)
from compliance.context_intake import build_context_prompt_block

import logging
import os as _os

_log = logging.getLogger("compliance.gap_analyzer")


# ── Phase 3 tuning constants ─────────────────────────────────────────────────

GAP_BATCH_SIZE = 10            # clauses per LLM call (was: 1)
# 6 worker × 3 norme = 18 batch concorrenti sulla mini (16M TPM): in-flight
# ~200k token. Il batch size resta 10 — la qualità non dipende dai worker.
GAP_MAX_WORKERS = int(_os.environ.get("GAP_MAX_WORKERS", "6"))
GAP_BATCH_MAX_TOKENS = 4096    # output budget per batch
GAP_RETRIEVAL_TOP_K = 4        # evidence cards retrieved per clause (standard)
# Sprint I.C — critical clauses (is_spof / high-frequency) get a wider retrieval
# window so we don't false-negative them when the top-4 happen to be irrelevant.
GAP_RETRIEVAL_TOP_K_CRITICAL = 8
# When the initial retrieval returns zero evidences for a clause, retry with the
# whole collection so we don't declare "no evidence" just because the top-K
# missed the relevant cards. The expanded retrieval cap protects us against
# very large card sets (e.g. >100 docs).
GAP_RETRIEVAL_FALLBACK_CAP = 20

# Severity ordering used by the floor application
_SEVERITY_ORDER = {
    "CONFORMANT":  -1,
    "OBSERVATION":  0,
    "MINOR":        1,
    "MAJOR":        2,
}


# ── Prompt paths ──────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "compliance"
_BATCH_GAP_PROMPT    = _PROMPTS_DIR / "gap_analysis_batch.md"
_CUSTOM_GAP_PROMPT   = _PROMPTS_DIR / "custom_criteria_gap.md"   # Fase 7 (PRD §1.4.4b)
_ISO9001_GAP_PROMPT  = _PROMPTS_DIR / "iso9001_gap.md"
_ISO14001_GAP_PROMPT = _PROMPTS_DIR / "iso14001_gap.md"
_ISO45001_GAP_PROMPT = _PROMPTS_DIR / "iso45001_gap.md"


# ── Norm registry ─────────────────────────────────────────────────────────────

_NORM_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ISO 9001:2015": {
        "clauses":     ISO9001_CLAUSES,
        "prompt_path": _ISO9001_GAP_PROMPT,
        "high_freq":   set(ISO9001_HIGH_FREQUENCY_CLAUSES),
    },
    "ISO 14001:2015": {
        "clauses":     ISO14001_CLAUSES,
        "prompt_path": _ISO14001_GAP_PROMPT,
        "high_freq":   set(ISO14001_HIGH_FREQUENCY_CLAUSES),
    },
    "ISO 45001:2018": {
        "clauses":     ISO45001_CLAUSES,
        "prompt_path": _ISO45001_GAP_PROMPT,
        "high_freq":   set(ISO45001_HIGH_FREQUENCY_CLAUSES),
    },
}


# ── Public entry point ────────────────────────────────────────────────────────

def analyze_compliance(
    evidence_yaml: str,
    company_context: CompanyContext,
    emitter: Optional[Callable[[float, str], None]] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
) -> ComplianceAnalysisResult:
    """
    Full gap analysis pipeline.

    Args:
        evidence_yaml:   Raw YAML string produced by Phase 2 (evidence extraction).
        company_context: Validated CompanyContext from the wizard.
        emitter:         Optional callable(pct, msg) for SSE progress streaming.
        documents:       Sprint R2 — the Phase 1 list of {"filename", "content"}
                         dicts with full extracted text (page markers included).
                         When provided, retrieval runs on content chunks instead
                         of card summaries only, and the deep verification pass
                         can read whole documents.

    Returns:
        ComplianceAnalysisResult with NormGapReport per norm.
    """
    def emit(pct: float, msg: str) -> None:
        if emitter:
            try:
                emitter(pct, msg)
            except Exception:
                pass

    analysis_id = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    emit(5.0, "Parsing evidence cards…")

    cards = _parse_evidence_yaml(evidence_yaml)
    emit(10.0, f"Indexed {len(cards)} evidence cards. Embedding…")

    # Sprint H.1: keep an evidence_id → card map so that TraceabilityLink can
    # surface the *verbatim* excerpts[0].text and the LLM summary distinctly,
    # rather than the concatenated blob that ChromaDB indexes for retrieval.
    cards_by_id: Dict[str, Dict[str, Any]] = {
        str(c.get("evidence_id", "")): c for c in cards if c.get("evidence_id")
    }

    embedder = EvidenceEmbedder(analysis_id)
    # Sprint R2: index content chunks (page-aware, original language) plus the
    # card summaries (UK English bridge). Falls back to summary-only when the
    # caller has no document texts (e.g. tests, legacy callers).
    indexed = embedder.index_corpus(cards, documents=documents)
    emit(15.0, f"Indexed {indexed} evidence chunks. Starting gap analysis…")

    # Sprint 3.2 — wrap the embedder in an EvidenceService so retrieval goes
    # through the same typed API used by the chat endpoint and any future
    # post-audit query path. The service is non-owning: when we close it,
    # we still keep the embedder alive until the explicit close below.
    evidence_service = EvidenceService(analysis_id=analysis_id, embedder=embedder)

    # ── Fase 7 (PRD §1.4.4b) — registry effettivo: ISO + criteri custom ───────
    # I nomi in company_context.norms che non sono standard ISO vengono risolti
    # come custom requirement set (data/requirement_sets/*.yaml); il motore li
    # processa con lo stesso identico Stage A + Stage B.
    effective_registry: Dict[str, Dict[str, Any]] = dict(_NORM_REGISTRY)
    for requested in company_context.norms:
        if requested in effective_registry:
            continue
        try:
            from compliance.custom_requirements import load_requirement_set_by_label
            custom = load_requirement_set_by_label(requested)
        except Exception as e:
            _log.warning("Custom requirement set %r non caricabile: %s", requested, e)
            custom = None
        if custom:
            effective_registry[requested] = {
                "clauses": custom["clauses"],
                "prompt_path": _CUSTOM_GAP_PROMPT,
                "high_freq": set(),
            }
            emit(14.0, f"Loaded operating criteria set: {requested} "
                       f"({len(custom['clauses'])} requirements).")
        else:
            _log.warning("Norm/set %r sconosciuto — ignorato", requested)

    # ── Phase 2.6 — documented-information coverage check (Sprint R3) ─────────
    # Registry of what the standards oblige to exist, matched in cascade:
    # metadata (L1) → semantic (L2) → LLM absence confirmation (L3).
    norms_to_analyse = [n for n in company_context.norms if n in effective_registry]
    documented_info_dict: Optional[Dict[str, Any]] = None
    absent_by_clause: Dict[str, List[Dict[str, Any]]] = {}
    try:
        from compliance.documented_info_check import (
            run_documented_info_check, absent_items_by_clause,
        )
        emit(16.0, "Checking mandatory documented information coverage…")
        documented_info_dict = run_documented_info_check(
            cards=cards,
            norms=norms_to_analyse,
            evidence_service=evidence_service,
            llm_call=_call_llm,
            emitter=None,  # progress handled here, on this scope's scale
        )
        absent_by_clause = absent_items_by_clause(documented_info_dict)
        emit(18.0, (
            f"Documented information: {documented_info_dict['found_count']} found, "
            f"{documented_info_dict['weak_count']} weak, "
            f"{documented_info_dict['absent_count']} absent."
        ))
    except Exception as e:
        _log.warning("Phase 2.6 documented-info check failed (non-blocking): %s", e)

    context_block = build_context_prompt_block(company_context)
    # Phase 3 batches up to GAP_BATCH_SIZE clauses per LLM call — use the
    # batch-format prompt (gap_analysis_batch.md) so the model returns
    # `{"clauses": [...]}` instead of a single-clause JSON object.
    base_prompt   = _load_prompt(_BATCH_GAP_PROMPT, context_block)

    # Sprint R4 — full document texts keyed by normalised file name, used by
    # the Stage B deep verification pass to read whole documents.
    docs_by_name: Dict[str, str] = {}
    for doc in (documents or []):
        fname = str(doc.get("filename", "") or "")
        content = str(doc.get("content", "") or "")
        if fname and content.strip():
            from compliance.deep_verifier import _norm_name as _dv_norm
            docs_by_name[_dv_norm(fname)] = content

    # ── Phase 2.7 — structured risk extraction (Sprint R8, promise P2) ────────
    # Reads every risk document IN FULL and extracts the register as data:
    # risks, methodology, score, mitigation, owner — with per-entry presence
    # flags. Feeds the §6.1 deep verification and the risk→control chains.
    risk_register_dict: Optional[Dict[str, Any]] = None
    risk_register_text: str = ""
    if docs_by_name:
        try:
            from compliance.risk_extractor import (
                run_risk_extraction, format_register_for_prompt,
            )
            emit(18.5, "Extracting structured risk register…")
            risk_register_dict = run_risk_extraction(
                cards=cards,
                docs_by_name=docs_by_name,
                context_block=context_block,
                llm_call=lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens),
                emitter=None,
            )
            if risk_register_dict:
                risk_register_text = format_register_for_prompt(risk_register_dict)
                emit(19.0, (
                    f"Risk register: {risk_register_dict['total_risks']} risks, "
                    f"{risk_register_dict['unscored_count']} unscored, "
                    f"{risk_register_dict['unmitigated_count']} without mitigation."
                ))
        except Exception as e:
            _log.warning("Phase 2.7 risk extraction failed (non-blocking): %s", e)

    emit(19.0, f"Running gap analysis for {len(norms_to_analyse)} norm(s) in parallel…")

    # Run norms in parallel using a thread pool (LLM calls are I/O-bound)
    norm_reports: List[NormGapReport] = _analyse_norms_parallel(
        norms=norms_to_analyse,
        base_prompt=base_prompt,
        evidence_service=evidence_service,
        company_context=company_context,
        emit=emit,
        cards_by_id=cards_by_id,
        absent_by_clause=absent_by_clause,
        docs_by_name=docs_by_name,
        context_block=context_block,
        risk_register_text=risk_register_text,
        registry=effective_registry,
    )

    # ── Phase 3.5 — cross-clause coherence (Sprint R5, PRD 1.4.2c / P6) ───────
    cross_clause_findings: List[Any] = []
    try:
        from compliance.cross_clause import run_cross_clause_checks
        gaps_by_norm = {r.norm: r.clauses for r in norm_reports}
        cross_clause_findings = run_cross_clause_checks(
            gaps_by_norm=gaps_by_norm,
            context_block=context_block,
            llm_call=lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens, deep=True),
            emit=emit,
            pct_base=86.0,
            pct_budget=4.0,
            risk_register_text=risk_register_text,
        )
    except Exception as e:
        _log.warning("Phase 3.5 cross-clause pass failed (non-blocking): %s", e)

    evidence_service.close()  # no-op when non-owning (see EvidenceService docs)
    embedder.close()
    emit(90.0, "Compiling report…")

    all_gaps = [g for r in norm_reports for g in r.clauses]
    top_gaps = _select_top_gaps(all_gaps)

    result = ComplianceAnalysisResult(
        analysis_id=analysis_id,
        company=company_context.company_name,
        context=company_context,
        analysis_date=datetime.now().isoformat(),
        norms=norm_reports,
        documents_analyzed=len(cards),
        top_gaps=top_gaps,
    )

    # Attach the Phase 2.6 documented-info coverage report (Sprint R3)
    if documented_info_dict is not None:
        try:
            from compliance.schemas import DocumentedInfoReport
            result.documented_info_report = DocumentedInfoReport(**documented_info_dict)
        except Exception as e:
            _log.warning("DocumentedInfoReport validation failed: %s — continuing without it", e)

    # Attach the Phase 3.5 cross-clause findings (Sprint R5)
    result.cross_clause_findings = cross_clause_findings

    # Attach the Phase 2.7 structured risk register (Sprint R8, P2)
    if risk_register_dict is not None:
        try:
            from compliance.schemas import RiskRegisterExtract
            result.risk_register_extract = RiskRegisterExtract(**risk_register_dict)
        except Exception as e:
            _log.warning("RiskRegisterExtract validation failed: %s — continuing without it", e)

    emit(100.0, "Analysis complete.")
    return result


# ── Parallel norm analysis ────────────────────────────────────────────────────

def _analyse_norms_parallel(
    norms: List[str],
    base_prompt: str,
    evidence_service: EvidenceService,
    company_context: CompanyContext,
    emit: Callable,
    cards_by_id: Dict[str, Dict[str, Any]],
    absent_by_clause: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    docs_by_name: Optional[Dict[str, str]] = None,
    context_block: str = "",
    risk_register_text: str = "",
    registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[NormGapReport]:
    """
    Run gap analysis for all requested norms in parallel using a thread pool.
    Each norm gets its own thread; LLM calls within a norm remain sequential
    (one per clause) to avoid overwhelming the Azure rate limit.
    Max 3 workers — one per norm.

    Fase 7: `registry` è il registry EFFETTIVO (ISO + custom set); fallback
    al registry statico per i chiamanti legacy.
    """
    registry = registry or _NORM_REGISTRY
    if not norms:
        return []

    if len(norms) == 1:
        norm = norms[0]
        norm_cfg = registry[norm]
        norm_prompt = base_prompt + "\n\n" + _load_file(norm_cfg["prompt_path"])
        gaps = _analyse_norm(
            norm=norm,
            clauses=norm_cfg["clauses"],
            norm_prompt=norm_prompt,
            evidence_service=evidence_service,
            company_context=company_context,
            emit=emit,
            pct_base=15.0,
            pct_budget=70.0,
            cards_by_id=cards_by_id,
            absent_by_clause=absent_by_clause,
            docs_by_name=docs_by_name,
            context_block=context_block,
            risk_register_text=risk_register_text,
        )
        return [_build_norm_report(norm, gaps, norm_cfg["clauses"])]

    pct_per_norm = 70.0 / len(norms)
    results: Dict[str, NormGapReport] = {}

    def analyse_one(norm_idx: int, norm: str) -> None:
        norm_cfg    = registry[norm]
        norm_prompt = base_prompt + "\n\n" + _load_file(norm_cfg["prompt_path"])
        emit(15.0 + norm_idx * pct_per_norm, f"Analysing {norm}…")
        gaps = _analyse_norm(
            norm=norm,
            clauses=norm_cfg["clauses"],
            norm_prompt=norm_prompt,
            evidence_service=evidence_service,
            company_context=company_context,
            emit=emit,
            pct_base=15.0 + norm_idx * pct_per_norm,
            pct_budget=pct_per_norm,
            cards_by_id=cards_by_id,
            absent_by_clause=absent_by_clause,
            docs_by_name=docs_by_name,
            context_block=context_block,
            risk_register_text=risk_register_text,
        )
        results[norm] = _build_norm_report(norm, gaps, norm_cfg["clauses"])

    # Cap 5: 3 ISO + eventuali set custom tutti in parallelo (le quote France
    # Central reggono; il collo era il vecchio limite 200K TPM).
    with ThreadPoolExecutor(max_workers=min(len(norms), 5)) as pool:
        futures = [pool.submit(analyse_one, i, norm) for i, norm in enumerate(norms)]
        for f in futures:
            f.result()  # propagate exceptions

    return [results[n] for n in norms if n in results]


# ── Norm-level analysis (batched) ─────────────────────────────────────────────

def _sort_clauses_by_criticality(clause_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort critical → standard → passing.

    Two reasons:
      1. If a batch fails mid-way, we have already produced verdicts for the
         clauses that matter most.
      2. The LLM sees the most important clauses first, which empirically
         improves consistency on the rest of the batch.
    """
    tier_rank = {"critical": 0, "standard": 1, "passing": 2}
    return sorted(
        clause_list,
        key=lambda c: (tier_rank.get(get_criticality_tier(c), 1), c.get("id", "")),
    )


def _retrieve_with_fallback(
    evidence_service: EvidenceService,
    clause: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Sprint I.C — retrieval that defends against the two main false-negative
    patterns observed in production:

      1. Critical/SPoF clauses get a wider retrieval window (TOP_K=8 vs 4) so
         that, when the top-4 by cosine similarity happen to be irrelevant,
         the next 4 still have a chance to surface the truly pertinent cards.

      2. If retrieval returns zero results AT ALL, we retry with a much larger
         window (up to GAP_RETRIEVAL_FALLBACK_CAP cards). This handles the
         pathological "ChromaDB returned nothing usable" case where the first
         pass missed the relevant evidence purely on similarity ranking.
    """
    is_critical = bool(
        clause.get("is_spof", False)
        or get_criticality_tier(clause) == "critical"
    )
    top_k = GAP_RETRIEVAL_TOP_K_CRITICAL if is_critical else GAP_RETRIEVAL_TOP_K

    # Sprint R2 — with chunk-level indexing the top-K can be saturated by
    # several chunks of the same document. Over-fetch and diversify: keep at
    # most 2 chunks per evidence_id so the LLM sees breadth AND depth.
    raw_results = evidence_service.get_evidences_for_clause(clause, n=top_k * 2)
    results = _diversify_chunks(raw_results, max_per_doc=2, cap=top_k)

    # Fallback: if first pass returned nothing, retry with the broader cap.
    # Doing this only on empty results keeps the cost bounded — we don't pay
    # the wider retrieval on every clause, only on the ones that would
    # otherwise be wrongly marked "no evidence".
    if not results:
        raw_results = evidence_service.get_evidences_for_clause(
            clause, n=GAP_RETRIEVAL_FALLBACK_CAP,
        )
        results = _diversify_chunks(
            raw_results, max_per_doc=2, cap=GAP_RETRIEVAL_FALLBACK_CAP,
        )
        if results:
            _log.info(
                "Clause %s: fallback retrieval rescued %d evidence(s) "
                "after empty first pass",
                clause.get("id", "?"),
                len(results),
            )

    return results


def _diversify_chunks(
    results: List[Dict[str, Any]],
    max_per_doc: int,
    cap: int,
) -> List[Dict[str, Any]]:
    """Keep at most `max_per_doc` chunks per evidence_id, preserving rank."""
    per_doc: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for ev in results:
        eid = str(ev.get("evidence_id", "") or ev.get("file_name", ""))
        if per_doc.get(eid, 0) >= max_per_doc:
            continue
        per_doc[eid] = per_doc.get(eid, 0) + 1
        out.append(ev)
        if len(out) >= cap:
            break
    return out


def _analyse_norm(
    norm: str,
    clauses: Dict[str, Dict[str, Any]],
    norm_prompt: str,
    evidence_service: EvidenceService,
    company_context: CompanyContext,
    emit: Callable,
    pct_base: float,
    pct_budget: float,
    cards_by_id: Dict[str, Dict[str, Any]],
    absent_by_clause: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    docs_by_name: Optional[Dict[str, str]] = None,
    context_block: str = "",
    risk_register_text: str = "",
) -> List[ClauseGap]:
    clause_list = _sort_clauses_by_criticality(list(clauses.values()))

    # Sprint R4 — pct budget split: Stage A (batched screening) takes 55%,
    # Stage B (deep verification on full documents) the remaining 45%.
    stage_a_budget = pct_budget * 0.55 if docs_by_name else pct_budget
    stage_b_budget = pct_budget - stage_a_budget

    # Build batches of GAP_BATCH_SIZE clauses each
    batches: List[List[Dict[str, Any]]] = [
        clause_list[i : i + GAP_BATCH_SIZE]
        for i in range(0, len(clause_list), GAP_BATCH_SIZE)
    ]
    total_batches = len(batches)
    if total_batches == 0:
        return []

    pct_per_batch = stage_a_budget / total_batches
    results: Dict[int, List[ClauseGap]] = {}

    def _process_batch(batch_idx: int, batch: List[Dict[str, Any]]) -> None:
        emit(
            pct_base + batch_idx * pct_per_batch,
            f"{norm}: batch {batch_idx + 1}/{total_batches} ({len(batch)} clauses)…",
        )

        # Sprint I.C — retrieve evidences with two anti-false-negative measures:
        #   (1) critical / SPoF clauses get a wider retrieval window (TOP_K=8)
        #       so the top-4-irrelevant-cards trap doesn't false-negative them
        #   (2) if the initial retrieval returns zero, we retry with a much
        #       larger n so we don't declare "no evidence" just because the
        #       semantic similarity ranking happened to miss the relevant cards
        clause_evidences: List[tuple] = [
            (clause, _retrieve_with_fallback(evidence_service, clause))
            for clause in batch
        ]

        gaps = _analyse_clauses_batched(
            clause_evidences=clause_evidences,
            norm_prompt=norm_prompt,
            cards_by_id=cards_by_id,
            absent_by_clause=absent_by_clause,
        )
        results[batch_idx] = gaps

    # Parallel batch execution, capped by GAP_MAX_WORKERS
    with ThreadPoolExecutor(max_workers=min(GAP_MAX_WORKERS, total_batches)) as pool:
        futures = [pool.submit(_process_batch, idx, batch) for idx, batch in enumerate(batches)]
        for f in futures:
            f.result()  # propagate exceptions

    # Reassemble in original (sorted) order
    all_gaps: List[ClauseGap] = []
    for idx in range(total_batches):
        all_gaps.extend(results.get(idx, []))

    # ── Stage B — deep verification on full documents (Sprint R4) ────────────
    if docs_by_name:
        try:
            from compliance.deep_verifier import run_deep_verification
            all_gaps = run_deep_verification(
                norm=norm,
                gaps=all_gaps,
                clauses=clauses,
                docs_by_name=docs_by_name,
                cards_by_id=cards_by_id,
                evidence_service=evidence_service,
                context_block=context_block,
                llm_call=lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens, deep=True),
                apply_floor=_apply_severity_floor,
                emit=emit,
                pct_base=pct_base + stage_a_budget,
                pct_budget=stage_b_budget,
                risk_register_text=risk_register_text,
            )
        except Exception as e:
            _log.warning("[Deep] Stage B failed for %s (%s) — Stage A verdicts kept",
                         norm, str(e)[:200])

    return all_gaps


# ── Batch-level analysis (single LLM call per batch) ──────────────────────────

def _analyse_clauses_batched(
    clause_evidences: List[tuple],  # [(clause, [evidence]), …]
    norm_prompt: str,
    cards_by_id: Dict[str, Dict[str, Any]],
    absent_by_clause: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[ClauseGap]:
    """
    Send N clauses to the LLM in a single call. Parse the array response.
    Apply cite-or-fail strict filtering + severity_floor on each verdict.
    """
    if not clause_evidences:
        return []

    user_prompt = _build_batch_user_prompt(clause_evidences, absent_by_clause)
    messages = [
        {"role": "system", "content": norm_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    # Sprint R0 — re-ask on parse failure. Before this, a single malformed JSON
    # response marked ALL clauses in the batch MAJOR/score 0 via the fallback,
    # devastating the report on one transient glitch. Now we re-ask the LLM
    # once (fresh call) before resorting to the catastrophic fallback.
    clauses_response = None
    parse_error = ""
    for ask_attempt in range(2):
        raw = _call_llm(messages, max_tokens=GAP_BATCH_MAX_TOKENS)
        try:
            data = json.loads(_strip_code_fences(raw))
            clauses_response = data.get("clauses") or []
            break
        except Exception as e:
            parse_error = str(e)
            _log.warning(
                "Failed to parse batch JSON (attempt %d/2: %s)%s",
                ask_attempt + 1, parse_error,
                " — re-asking" if ask_attempt == 0 else " — falling back per clause",
            )

    if clauses_response is None:
        return [
            _fallback_clause_gap(c, f"batch parse failed: {parse_error}")
            for (c, _) in clause_evidences
        ]

    # Build a lookup: clause_id → (clause, [evidence])
    by_id = {c["id"]: (c, ev) for (c, ev) in clause_evidences}

    gaps: List[ClauseGap] = []
    # Iterate in input order so we always emit one gap per input clause
    for clause, evidence_list in clause_evidences:
        cid = clause["id"]
        # Find the LLM's verdict for this clause_id (do not trust ordering blindly)
        item = next(
            (item for item in clauses_response if str(item.get("clause_id", "")) == cid),
            None,
        )
        if item is None:
            _log.warning(f"Batch response missing verdict for {cid}; using fallback")
            gaps.append(_fallback_clause_gap(clause, "clause missing from batch response"))
            continue

        gap = _parse_batch_clause_gap(item, clause, evidence_list, cards_by_id)
        gap = _apply_severity_floor(gap, clause, evidence_list)
        gaps.append(gap)

    return gaps


def _build_batch_user_prompt(
    clause_evidences: List[tuple],
    absent_by_clause: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> str:
    parts: List[str] = [
        f"## Batch of {len(clause_evidences)} clauses to assess",
        "",
        "Assess each clause independently against ONLY its own `available_evidences` list. "
        "Return a JSON object `{\"clauses\": [...]}` with one verdict per clause, in the same order.",
        "",
    ]
    absent_by_clause = absent_by_clause or {}
    for idx, (clause, evidence_list) in enumerate(clause_evidences, start=1):
        parts.append(f"### Clause {idx}/{len(clause_evidences)}: {clause['id']}")
        parts.append(f"- clause_id: {clause['id']}")
        parts.append(f"- title: {clause['title']}")
        parts.append(f"- area: {clause.get('area', '')}")
        parts.append(f"- is_spof: {clause.get('is_spof', False)}")
        parts.append(f"- criticality_tier: {get_criticality_tier(clause)}")
        crit_sectors = ", ".join(clause.get("critical_sectors", []) or []) or "none"
        parts.append(f"- critical_sectors: {crit_sectors}")
        parts.append("- typical_ncs:")
        for nc in clause.get("typical_ncs", []) or []:
            parts.append(f"    - {nc}")

        # Sprint J — atomic_requirements: when the clause carries an explicit
        # verifiable checklist, present it to the LLM so the verdict is
        # grounded item-by-item rather than on general clause knowledge. This
        # is the strongest single change to engine accuracy on critical
        # clauses (e.g. Management Review §9.3, Hazard ID §6.1.2).
        atomic_reqs = clause.get("atomic_requirements") or []
        if atomic_reqs:
            parts.append("- atomic_requirements (verify each item against the evidence):")
            for req in atomic_reqs:
                parts.append(f"    - id: {req.get('id', '')}")
                parts.append(f"      text: {req.get('text', '')}")
                hint = req.get("verification_hint", "")
                if hint:
                    parts.append(f"      verification_hint: {hint}")
                expected = req.get("expected_evidence", []) or []
                if expected:
                    parts.append(f"      expected_evidence: {', '.join(expected)}")
                risk = req.get("risk_if_missing", "")
                if risk:
                    parts.append(f"      risk_if_missing: {risk}")

        # Sprint R3 — Phase 2.6 documented-info check result for this clause.
        # The deterministic coverage check (registry + 3-level matcher, with
        # LLM absence confirmation) found these REQUIRED items missing from
        # the corpus — strong, pre-verified evidence of absence.
        di_absent = absent_by_clause.get(clause["id"], [])
        if di_absent:
            parts.append("- documented_info_check (deterministic, pre-verified): "
                         "the following REQUIRED documented information was NOT found "
                         "anywhere in the document package:")
            for row in di_absent:
                parts.append(f"    - {row.get('item', '')} "
                             f"({row.get('retain_or_maintain', '')}; "
                             f"risk_if_missing: {row.get('risk_if_missing', '')})")

        rem = clause.get("remediation_template", {})
        parts.append("- remediation_template:")
        parts.append(f"    what: {rem.get('what', '')}")
        parts.append(f"    who: {rem.get('who', '')}")
        parts.append(f"    when_major: {rem.get('when_major', '')}")
        parts.append(f"    when_minor: {rem.get('when_minor', '')}")
        parts.append(f"    effort: {rem.get('effort', '')}")

        parts.append("- available_evidences:")
        if evidence_list:
            for ev in evidence_list:
                parts.append("    -")
                parts.append(f"      evidence_id: {ev.get('evidence_id', '')}")
                parts.append(f"      file_name: {ev.get('file_name', '')}")
                parts.append(f"      doc_type: {ev.get('doc_type', '')}")
                parts.append(f"      iso_clause_primary: {ev.get('iso_clause_primary', '')}")
                parts.append(f"      gap_signal: {ev.get('gap_signal', False)}")
                # Sprint R2: chunks carry real page numbers from Phase 1 markers
                pages = ev.get("pages") or []
                if pages:
                    parts.append(f"      pages: {pages}")
                excerpt = str(ev.get("excerpt", ""))[:700].replace("\n", " ")
                parts.append(f"      excerpt: {excerpt}")
        else:
            parts.append("    []   # no evidence retrieved for this clause")
        parts.append("")

    return "\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────────────────

# Sprint R0 — Phase 3 retry tuning. Mirrors the Phase 2 batch retry policy:
# transient Azure errors (429 / timeout / connection) are retried with
# exponential backoff (Azure-only). Phase 3 previously had
# NO retry at all, so a single transient 429 silently degraded a whole batch.
GAP_LLM_MAX_RETRIES = 3
GAP_LLM_RETRY_BASE_DELAY = 2.0
GAP_LLM_RETRY_MAX_DELAY = 30.0


def _call_llm(messages: List[Dict[str, str]], max_tokens: int = 1024,
              deep: bool = False) -> str:
    """
    Call Azure with retry/backoff for transient errors.

    Fase 2 consolidamento: provider Azure-ONLY (decisione utente 2026-06-12 —
    la chiave Gemini non è utilizzabile e il fallback viene rimosso). Su
    esaurimento retry ritorna stringa vuota: i chiamanti hanno già la loro
    degradazione controllata (re-ask del batch, fallback gaps, carte
    sintetiche, 502 per la chat).

    deep=True instrada sul profilo COMPLIANCE_DEEP_PROVIDER (gpt-4.1 full)
    per le fasi di giudizio — Stage B e cross-clause; se non configurato,
    make_client degrada alla mini senza errori.

    max_tokens defaults to 1024 (legacy single-clause call); batched callers
    pass GAP_BATCH_MAX_TOKENS (4096) for multi-clause responses.
    """
    import time as _time

    try:
        from v2.azure_openai_client_v2 import make_client
        client = make_client(deep=deep)
    except Exception as e:
        _log.error(f"Azure client init failed — no fallback configured: {e}")
        return ""

    for attempt in range(GAP_LLM_MAX_RETRIES):
        try:
            stream = client.chat_stream(messages=messages, max_tokens=max_tokens)
            chunks: List[str] = []
            for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta   = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", None) if delta else None
                    if content:
                        chunks.append(content)
            raw = "".join(chunks)
            if raw.strip():
                return raw
            _log.warning(
                "[Phase 3] Azure returned empty response (attempt %d/%d) — retrying",
                attempt + 1, GAP_LLM_MAX_RETRIES,
            )
        except Exception as e:
            msg = str(e).lower()
            is_transient = (
                "rate limit" in msg or "rate_limit" in msg
                or "429" in msg or "timeout" in msg
                or "connection" in msg
            )
            _log.warning(
                "[Phase 3] Azure attempt %d/%d failed (%s): %s",
                attempt + 1, GAP_LLM_MAX_RETRIES,
                "transient" if is_transient else "fatal",
                str(e)[:200],
            )
            if not is_transient:
                break  # non-retryable
        if attempt < GAP_LLM_MAX_RETRIES - 1:
            _time.sleep(min(
                GAP_LLM_RETRY_BASE_DELAY * (2 ** attempt),
                GAP_LLM_RETRY_MAX_DELAY,
            ))

    _log.error("[Phase 3] Azure exhausted after %d attempts — no fallback configured",
               GAP_LLM_MAX_RETRIES)
    return ""


# ── Response parsing (batch verdict per clause) ──────────────────────────────

def _parse_batch_clause_gap(
    data: Dict[str, Any],
    clause: Dict[str, Any],
    evidence_list: List[Dict[str, Any]],
    cards_by_id: Dict[str, Dict[str, Any]],
) -> ClauseGap:
    """
    Parse one clause verdict from the batch response.

    Implements **cite-or-fail strict**: every `evidence_id` cited by the LLM
    must exist in this clause's `evidence_list`. IDs not found are discarded
    and a warning is logged. If filtering empties the citation list, the
    severity is escalated to at least the clause's severity_floor.

    Sprint H.1: TraceabilityLink.excerpt now carries the verbatim quote from
    the document (Q12: `card.excerpts[0].text`) and TraceabilityLink.summary
    carries the LLM descriptive summary (Q11: `card.summary`). Both are
    truncated with word-safe boundaries so they never end mid-word.
    """
    from compliance._text_utils import truncate_word_safe
    # Build the verifier set from the evidence we actually passed in
    valid_ids = {ev.get("evidence_id", "") for ev in evidence_list if ev.get("evidence_id")}

    # Pull citations from the LLM. Tolerate both new and legacy shapes:
    # - new (batch prompt): evidence_used: ["ev_001", "ev_007"]
    # - legacy (single prompt): sources: [{evidence_id: "..."}]
    cited_ids: List[str] = []
    if isinstance(data.get("evidence_used"), list):
        cited_ids = [str(x) for x in data["evidence_used"] if isinstance(x, str)]
    elif isinstance(data.get("sources"), list):
        cited_ids = [
            str(s.get("evidence_id", ""))
            for s in data["sources"]
            if isinstance(s, dict) and s.get("evidence_id")
        ]

    valid_citations = [cid for cid in cited_ids if cid in valid_ids]
    hallucinated = [cid for cid in cited_ids if cid and cid not in valid_ids]
    if hallucinated:
        _log.warning(
            f"Clause {clause['id']}: LLM hallucinated {len(hallucinated)} evidence_id(s): "
            f"{hallucinated[:5]}{'…' if len(hallucinated) > 5 else ''}"
        )

    # Build TraceabilityLink only for valid citations.
    # Sprint H.1: hydrate from the ORIGINAL card (cards_by_id) so we can show
    # the verbatim excerpt (Q12) and the LLM summary (Q11) as distinct fields,
    # not the concatenated blob ChromaDB indexes for retrieval.
    ev_by_id = {ev.get("evidence_id", ""): ev for ev in evidence_list}
    sources: List[TraceabilityLink] = []
    for eid in valid_citations:
        ev = ev_by_id.get(eid, {})
        card = cards_by_id.get(eid, {})

        # Verbatim quote: prefer the first card.excerpts[].text (Q12), fall
        # back to whatever the retrieval brought back if the card has none.
        verbatim_raw = ""
        card_excerpts = card.get("excerpts") or []
        if card_excerpts and isinstance(card_excerpts[0], dict):
            verbatim_raw = str(card_excerpts[0].get("text", "") or "")
        if not verbatim_raw:
            verbatim_raw = str(ev.get("excerpt", "") or "")

        # Pages: prefer the card excerpts[0].pages, fall back to retrieval meta
        pages = []
        if card_excerpts and isinstance(card_excerpts[0], dict):
            pages = list(card_excerpts[0].get("pages", []) or [])
        if not pages:
            pages = list(ev.get("pages", []) or [])

        # LLM summary (Q11): only attach if non-empty and not "no gap" boilerplate
        summary_raw = str(card.get("summary", "") or "").strip()
        summary_clean = truncate_word_safe(summary_raw, 280) if summary_raw else None

        sources.append(TraceabilityLink(
            evidence_id=eid,
            file_name=str(ev.get("file_name", "") or card.get("file_name", "")),
            pages=pages,
            excerpt=truncate_word_safe(verbatim_raw, 280),
            relevance_score=float(ev.get("relevance_score", 0.5)),
            summary=summary_clean,
        ))

    # Severity normalisation
    severity = str(data.get("severity", "OBSERVATION")).upper()
    if severity not in ("MAJOR", "MINOR", "OBSERVATION", "CONFORMANT"):
        severity = "OBSERVATION"

    # Cite-or-fail: if the LLM cited nothing valid but evidence was available,
    # the verdict is suspect — never let it claim CONFORMANT with zero sources.
    if not sources and severity == "CONFORMANT" and evidence_list:
        _log.warning(
            f"Clause {clause['id']}: LLM declared CONFORMANT with no valid citations; "
            f"downgrading to OBSERVATION (severity_floor will apply if applicable)"
        )
        severity = "OBSERVATION"

    score = max(0, min(100, int(data.get("score", 50))))
    is_spof = bool(data.get("is_spof", False)) and clause.get("is_spof", False) and severity == "MAJOR"

    # Sprint R4 — Stage A verdict confidence (drives deep-pass selection and
    # is surfaced to the user per PRD 1.4.6).
    confidence: Optional[float] = None
    try:
        if data.get("confidence") is not None:
            confidence = max(0.0, min(1.0, float(data["confidence"])))
    except (TypeError, ValueError):
        confidence = None

    rem = data.get("remediation") or {}
    # Sprint R0 — the `when` fallback must follow the verdict severity:
    # MAJOR gets the tight deadline (when_major), anything else the standard
    # one (when_minor). Previously when_major was applied unconditionally.
    template = clause["remediation_template"]
    when_fallback = template["when_major"] if severity == "MAJOR" else template["when_minor"]
    remediation = RemediationPlan(
        what=rem.get("what")   or template["what"],
        who=rem.get("who")     or template["who"],
        when=rem.get("when")   or when_fallback,
        effort=rem.get("effort") or template["effort"],
    )

    finding = str(data.get("finding", "No finding generated."))[:800]

    return ClauseGap(
        clause_id=clause["id"],
        clause_title=clause["title"],
        score=score,
        severity=severity,
        is_spof=is_spof,
        finding=finding,
        sources=sources,
        remediation=remediation,
        confidence=confidence,
    )


def _apply_severity_floor(
    gap: ClauseGap,
    clause: Dict[str, Any],
    evidence_list: List[Dict[str, Any]],
) -> ClauseGap:
    """
    Enforce the clause's severity floor (from clause_helpers.get_severity_floor):

      - critical clauses (is_spof or HIGH_FREQUENCY): floor = MAJOR
      - standard clauses:                              floor = MINOR
      - passing (context) clauses:                     floor = None (no floor)

    Never escalates a CONFORMANT verdict that already has valid sources — that
    is a positive finding worth preserving.

    Sprint I.B — coherence fix:
      * No longer prepends "[severity floor applied …]" to gap.finding (was a
        debug marker leaking into the user-facing text).
      * When severity is escalated, score is realigned into the new severity
        band so that the UI never shows "score 70 / MAJOR" (contradictory).
      * The original LLM-assigned score is preserved in server-side logging
        for audit/debugging, never in the visible finding.
    """
    floor = get_severity_floor(clause)
    if floor is None:
        return gap

    # Preserve genuine CONFORMANT verdicts (must have at least one cited source)
    if gap.severity == "CONFORMANT" and gap.sources:
        return gap

    current_rank = _SEVERITY_ORDER.get(gap.severity, 0)
    floor_rank = _SEVERITY_ORDER.get(floor, 0)
    if current_rank >= floor_rank:
        return gap

    tier = get_criticality_tier(clause)
    original_severity = gap.severity
    original_score = gap.score

    # Escalate severity to the floor
    gap.severity = floor

    # Realign score into the new severity band so the two numbers don't
    # contradict each other in the UI. Bands from gap_analysis_batch.md:
    #   MAJOR:       0-29
    #   MINOR:       30-59
    #   OBSERVATION: 60-84
    #   CONFORMANT:  85-100
    _SEVERITY_SCORE_CEILING = {
        "MAJOR":       29,
        "MINOR":       59,
        "OBSERVATION": 84,
        "CONFORMANT":  100,
    }
    ceiling = _SEVERITY_SCORE_CEILING.get(floor, gap.score)
    if gap.score > ceiling:
        gap.score = ceiling

    # Re-evaluate SPoF flag with the escalated severity
    gap.is_spof = bool(clause.get("is_spof", False)) and gap.severity == "MAJOR"

    # Sprint R0 — keep the remediation deadline coherent with the escalated
    # severity: if we floored to MAJOR but the deadline is still the relaxed
    # when_minor template value, tighten it to when_major.
    template = clause.get("remediation_template", {})
    if (
        gap.severity == "MAJOR"
        and template.get("when_major")
        and gap.remediation.when == template.get("when_minor")
    ):
        gap.remediation.when = template["when_major"]

    _log.info(
        "Severity floor applied to clause %s (%s): LLM verdict %s/%d -> floored to %s/%d",
        clause.get("id", "?"),
        tier,
        original_severity,
        original_score,
        gap.severity,
        gap.score,
    )
    return gap


def _fallback_clause_gap(clause: Dict[str, Any], error: str) -> ClauseGap:
    rem = clause["remediation_template"]
    return ClauseGap(
        clause_id=clause["id"],
        clause_title=clause["title"],
        score=0,
        severity="MAJOR",
        is_spof=clause.get("is_spof", False),
        finding=f"Analysis could not be completed for this clause. Error: {error[:200]}",
        sources=[],
        remediation=RemediationPlan(
            what=rem["what"], who=rem["who"],
            when=rem["when_major"], effort=rem["effort"],
        ),
    )


# ── Aggregation ───────────────────────────────────────────────────────────────

def _build_norm_report(
    norm: str,
    gaps: List[ClauseGap],
    clause_registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> NormGapReport:
    # Sprint R0 — weighted average using clause_helpers.get_weight (5 critical /
    # 3 standard / 1 passing). Previously the mean was unweighted, so a context
    # clause (§4.1) influenced the overall score as much as an SPoF clause.
    # Fase 7: il clause_registry arriva dal registry effettivo (ISO o custom).
    from compliance.clause_helpers import get_weight

    if clause_registry is None:
        clause_registry = _NORM_REGISTRY.get(norm, {}).get("clauses", {})
    weighted_sum = 0.0
    weight_total = 0
    for g in gaps:
        clause = clause_registry.get(g.clause_id, {})
        w = get_weight(clause) if clause else 3  # unknown clause → standard weight
        weighted_sum += g.score * w
        weight_total += w
    overall = round(weighted_sum / weight_total) if weight_total else 0

    return NormGapReport(
        norm=norm,
        overall_score=overall,
        clauses=gaps,
        major_count=sum(1 for g in gaps if g.severity == "MAJOR"),
        minor_count=sum(1 for g in gaps if g.severity == "MINOR"),
        observation_count=sum(1 for g in gaps if g.severity == "OBSERVATION"),
        conformant_count=sum(1 for g in gaps if g.severity == "CONFORMANT"),
        spof_count=sum(1 for g in gaps if g.is_spof),
    )


def _select_top_gaps(all_gaps: List[ClauseGap], n: int = 5) -> List[ClauseGap]:
    def priority(g: ClauseGap) -> int:
        if g.is_spof and g.severity == "MAJOR": return 0
        if g.severity == "MAJOR":               return 1
        if g.severity == "MINOR":               return 2
        if g.severity == "OBSERVATION":         return 3
        return 4
    return sorted(all_gaps, key=lambda g: (priority(g), g.score))[:n]


# ── YAML parsing ──────────────────────────────────────────────────────────────

def _parse_evidence_yaml(evidence_yaml: str) -> List[Dict[str, Any]]:
    if not evidence_yaml or not evidence_yaml.strip():
        return []

    # Multi-card output uses `# ── DOC N ──` separators between consecutive
    # block-style mappings. yaml.safe_load on the whole string would silently
    # collapse them into one dict (later keys override earlier ones), so when
    # we detect ≥2 markers we go straight to the per-block split.
    doc_markers = re.findall(r"#\s*──\s*DOC\s*\d+\s*──", evidence_yaml)
    if len(doc_markers) >= 2:
        cards: List[Dict[str, Any]] = []
        blocks = re.split(r"#\s*──\s*DOC\s*\d+\s*──", evidence_yaml)
        for block in blocks[1:]:
            try:
                card = yaml.safe_load(block.strip())
                if isinstance(card, dict) and card.get("evidence_id"):
                    cards.append(card)
            except Exception:
                continue
        return cards

    try:
        raw = yaml.safe_load(evidence_yaml)
        if isinstance(raw, list):
            return [c for c in raw if isinstance(c, dict)]
        if isinstance(raw, dict):
            return [raw]
    except yaml.YAMLError:
        pass

    # Fallback for malformed multi-card input without proper headers
    cards: List[Dict[str, Any]] = []
    blocks = re.split(r"#\s*──\s*DOC\s*\d+\s*──", evidence_yaml)
    for block in blocks[1:]:
        try:
            card = yaml.safe_load(block.strip())
            if isinstance(card, dict) and card.get("evidence_id"):
                cards.append(card)
        except Exception:
            continue
    return cards


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers that some LLMs add."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.rstrip())
    return text.strip()


# ── File helpers ──────────────────────────────────────────────────────────────

def _load_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_prompt(path: Path, context_block: str) -> str:
    text = _load_file(path)
    return text.replace("{company_context}", context_block)
