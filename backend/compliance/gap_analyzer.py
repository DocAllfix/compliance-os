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
import time
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
# Fix retrieval (2026-06-14): cap della lista evidenze quando si fondono le card
# taggate alla clausola (Phase 2 `iso_clause_primary`) col retrieval semantico.
# Tiene il prompt limitato anche per clausole con molte card pertinenti.
GAP_RETRIEVAL_TAG_CAP = 12
# Piano motore Fase 1 (RETRIEVE_PER_REQUIREMENT): frammenti per query di
# requisito e tetto complessivo per clausola (batch da 10 clausole × 16 × 700
# caratteri ≈ 28k token, dentro i limiti della mini).
GAP_RETRIEVAL_PER_REQ_K = 2
GAP_RETRIEVAL_PER_REQ_CAP = 16

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
    _t0 = time.monotonic()
    indexed = embedder.index_corpus(cards, documents=documents)
    _log.info("[Timing] indexing: %.1fs (%d chunks)", time.monotonic() - _t0, indexed)
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

    # ── Piano motore Fase 2 (JURISDICTION_FILTER) — obblighi nazionali solo per
    # il paese giusto: per un'organizzazione non italiana la knowledge base
    # perde i requisiti solo italiani (DUVRI, FIR) e i nomi degli istituti
    # italiani diventano l'equivalente neutro (compliance/jurisdiction.py).
    from compliance import features
    # Piano motore Fase 2 (KB_V2): requisiti atomici da norma + checklist.
    if features.on("KB_V2") or features.on("KB_V2_FILL"):
        from compliance import kb_v2
        fill_only = not features.on("KB_V2")
        for _norm in list(effective_registry):
            if _norm in _NORM_REGISTRY:
                _cfg = effective_registry[_norm]
                effective_registry[_norm] = {**_cfg, "clauses": kb_v2.apply(_cfg["clauses"], fill_only=fill_only)}
    elif features.on("KB_STRENGTH"):
        # Solo la forza dei requisiti: buona pratica ≠ obbligo (la KB resta quella attuale).
        from compliance import kb_v2
        for _norm in list(effective_registry):
            if _norm in _NORM_REGISTRY:
                _cfg = effective_registry[_norm]
                effective_registry[_norm] = {**_cfg, "clauses": kb_v2.annotate(_cfg["clauses"])}
    if features.on("JURISDICTION_FILTER"):
        from compliance import jurisdiction
        country = getattr(company_context, "country", None)
        for _norm, _cfg in list(effective_registry.items()):
            effective_registry[_norm] = {**_cfg, "country": country,
                                         "clauses": jurisdiction.adapt_clauses(_cfg["clauses"], country)}

    # ── Phase 2.6 — documented-information coverage check (Sprint R3) ─────────
    # Registry of what the standards oblige to exist, matched in cascade:
    # metadata (L1) → semantic (L2) → LLM absence confirmation (L3).
    norms_to_analyse = [n for n in company_context.norms if n in effective_registry]
    documented_info_dict: Optional[Dict[str, Any]] = None
    absent_by_clause: Dict[str, List[Dict[str, Any]]] = {}
    _t0 = time.monotonic()
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
    _log.info("[Timing] phase 2.6 documented-info: %.1fs", time.monotonic() - _t0)

    context_block = build_context_prompt_block(company_context)
    # Phase 3 batches up to GAP_BATCH_SIZE clauses per LLM call — use the
    # batch-format prompt (gap_analysis_batch.md) so the model returns
    # `{"clauses": [...]}` instead of a single-clause JSON object.
    base_prompt   = _load_prompt(_BATCH_GAP_PROMPT, context_block)
    from compliance import features
    if features.on("SEVERITY_RULES"):
        base_prompt = _absence_wording_rules(base_prompt)
    if features.on("FACT_MODEL"):
        from compliance.facts import EVIDENCE_PROVENANCE_RULE
        base_prompt += EVIDENCE_PROVENANCE_RULE

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
    #
    # Overlap 2026-07: gira in PARALLELO allo Stage A. Il suo output non entra
    # mai nei prompt Stage A: è letto solo da Stage B e cross-clause, che
    # joinano il future prima di usarlo. Stessi input alle stesse chiamate —
    # cambia solo il momento di partenza (vincolo: output identico al serial).
    def _run_risk_extraction() -> tuple:
        rdict: Optional[Dict[str, Any]] = None
        rtext: str = ""
        _t = time.monotonic()
        if docs_by_name:
            try:
                from compliance.risk_extractor import (
                    run_risk_extraction, format_register_for_prompt,
                )
                rdict = run_risk_extraction(
                    cards=cards,
                    docs_by_name=docs_by_name,
                    context_block=context_block,
                    llm_call=lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens),
                    emitter=None,
                )
                if rdict:
                    rtext = format_register_for_prompt(rdict)
                    # Log-only: un emit qui arriverebbe a Stage A in corso e
                    # farebbe regredire la barra SSE (il frontend non clampa).
                    _log.info(
                        "Risk register: %s risks, %s unscored, %s without mitigation.",
                        rdict.get("total_risks"), rdict.get("unscored_count"),
                        rdict.get("unmitigated_count"),
                    )
            except Exception as e:
                _log.warning("Phase 2.7 risk extraction failed (non-blocking): %s", e)
        _log.info("[Timing] phase 2.7 risk extraction: %.1fs", time.monotonic() - _t)
        return rdict, rtext

    if docs_by_name:
        emit(18.5, "Extracting structured risk register…")
    _risk_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="risk-27")
    _risk_future = _risk_pool.submit(_run_risk_extraction)

    def _risk_text_provider() -> str:
        # Join point per Stage B/cross-clause: blocca finché la 2.7 è completa.
        return _risk_future.result()[1]

    emit(19.0, f"Running gap analysis for {len(norms_to_analyse)} norm(s) in parallel…")

    # Run norms in parallel using a thread pool (LLM calls are I/O-bound)
    _t0 = time.monotonic()
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
        risk_register_provider=_risk_text_provider,
        registry=effective_registry,
    )
    _log.info("[Timing] phase 3 stage A+B (%d norms): %.1fs",
              len(norms_to_analyse), time.monotonic() - _t0)

    # A questo punto la 2.7 è comunque completa (Stage B l'ha joinata; se non
    # c'erano documenti il future è immediato). Materializza per cross-clause
    # e per RiskRegisterExtract nel result.
    risk_register_dict, risk_register_text = _risk_future.result()
    _risk_pool.shutdown(wait=False)

    # ── Piano motore Fase 3 (SHARED_EVIDENCE) — un giudizio per un fatto condiviso ─
    # Clausola comune conforme in una norma e non conforme in un'altra solo per lo
    # screening: la seconda si rilegge per intero con i documenti della prima.
    if features.on("SHARED_EVIDENCE") and docs_by_name and len(norm_reports) > 1:
        _t0 = time.monotonic()
        try:
            from compliance import shared_evidence
            norm_reports, _shared_log = shared_evidence.reconcile(
                norm_reports, {n: effective_registry[n]["clauses"] for n in norms_to_analyse},
                docs_by_name, cards_by_id, evidence_service, context_block,
                lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens, deep=True), emit)
        except Exception as e:
            _log.warning("Rilettura tra norme fallita (non bloccante): %s", e)
        _log.info("[Timing] rilettura tra norme: %.1fs", time.monotonic() - _t0)

    # ── Piano motore Fase 4 (SELF_CONSISTENCY) — l'organizzazione contro sé stessa
    # Dichiarazioni (registri, procedure, verbali) → aspettative → confronti in
    # Python; gli esiti diventano controlli sulla clausola competente.
    self_checks: List[Dict[str, Any]] = []
    if features.on("SELF_CONSISTENCY") and documents:
        _t0 = time.monotonic()
        try:
            from compliance import self_consistency
            from compliance.absence_search import search_statement
            from compliance.facts import build as _build_facts
            emit(86.0, "Checking the organisation against its own records…")
            _facts = _build_facts(cards, documents)
            _deep = lambda messages, max_tokens: _call_llm(messages, max_tokens=max_tokens, deep=True)  # noqa: E731
            self_checks = self_consistency.run(
                documents, _facts, datetime.now().date(),
                lambda subject, quote, src: search_statement(subject, quote, src, docs_by_name,
                                                             evidence_service, _deep))
            norm_reports = self_consistency.attach(
                norm_reports, self_checks,
                {n: effective_registry[n]["clauses"] for n in norms_to_analyse})
        except Exception as e:
            _log.warning("Fase 4 self-consistency fallita (non bloccante): %s", e)
        _log.info("[Timing] fase 4 self-consistency: %.1fs (%d esiti)", time.monotonic() - _t0, len(self_checks))

    # ── Piano motore Fase 5 (SECTOR_EXPECTATIONS) — aspettative di settore ───
    # L'attività citata nei documenti del cliente fa attendere la registrazione
    # tipica (schede di sicurezza, documenti rifiuti, verifiche periodiche);
    # se manca è un punto da verificare, mai una non conformità.
    if features.on("SECTOR_EXPECTATIONS") and documents:
        try:
            from compliance import sector_expectations
            from compliance.facts import build as _build_facts
            _f5 = _build_facts(cards)
            _se = sector_expectations.evaluate(documents, _f5.is_external)
            norm_reports, _se_checks = sector_expectations.attach(
                norm_reports, _se, {n: effective_registry[n]["clauses"] for n in norms_to_analyse})
            norm_reports = [_build_norm_report(r.norm, r.clauses, effective_registry[r.norm]["clauses"])
                            for r in norm_reports]
            self_checks = self_checks + _se_checks
        except Exception as e:
            _log.warning("Fase 5 aspettative di settore fallita (non bloccante): %s", e)

    # ── Phase 3.5 — cross-clause coherence (Sprint R5, PRD 1.4.2c / P6) ───────
    cross_clause_findings: List[Any] = []
    _t0 = time.monotonic()
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
    _log.info("[Timing] phase 3.5 cross-clause: %.1fs", time.monotonic() - _t0)

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
    # Piano motore Fase 4: esiti "l'organizzazione contro sé stessa"
    result.self_checks = self_checks

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
    risk_register_provider: Optional[Callable[[], str]] = None,
) -> List[NormGapReport]:
    """
    Run gap analysis for all requested norms in parallel using a thread pool.
    Each norm gets its own thread; LLM calls within a norm remain sequential
    (one per clause) to avoid overwhelming the Azure rate limit.
    Max 3 workers — one per norm.

    Fase 7: `registry` è il registry EFFETTIVO (ISO + custom set); fallback
    al registry statico per i chiamanti legacy.

    Overlap 2026-07: `risk_register_provider` (se presente) vince su
    `risk_register_text` — è il join sul future della Phase 2.7, risolto da
    ogni norma al confine Stage A → Stage B (Stage A non usa il registro).
    """
    registry = registry or _NORM_REGISTRY
    if not norms:
        return []

    if len(norms) == 1:
        norm = norms[0]
        norm_cfg = registry[norm]
        norm_prompt = base_prompt + "\n\n" + _norm_prompt_text(norm_cfg)
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
            risk_register_provider=risk_register_provider,
        )
        return [_build_norm_report(norm, gaps, norm_cfg["clauses"])]

    pct_per_norm = 70.0 / len(norms)
    results: Dict[str, NormGapReport] = {}

    def analyse_one(norm_idx: int, norm: str) -> None:
        norm_cfg    = registry[norm]
        norm_prompt = base_prompt + "\n\n" + _norm_prompt_text(norm_cfg)
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
            risk_register_provider=risk_register_provider,
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


_CLAUSE_NUM_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")


def _clause_number_from_id(clause_id: str) -> str:
    """'9001_7_2' -> '7.2', '14001_6_1_2' -> '6.1.2'. Toglie il prefisso norma."""
    parts = str(clause_id or "").split("_")
    return ".".join(parts[1:]) if len(parts) > 1 else str(clause_id or "")


def _extract_clause_numbers(text: str) -> set:
    """Numeri di clausola in un `iso_clause_primary` LLM (es. 'ISO 9001 §7.2').
    Per un X.Y.Z aggiunge anche il padre X.Y, così una card §7.2.1 aggancia la
    clausola 7.2."""
    nums: set = set()
    for m in _CLAUSE_NUM_RE.findall(text or ""):
        nums.add(m)
        bits = m.split(".")
        if len(bits) == 3:
            nums.add(".".join(bits[:2]))
    return nums


def build_cards_by_clause(cards_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Mappa numero-clausola → card, dai tag della Phase 2. Riconnette la
    classificazione (ottima) al retrieval di Phase 3, che altrimenti la ignora.

    Usa SIA `iso_clause_primary` SIA `iso_clauses_secondary` (un documento può
    valere per più clausole — es. il registro fornitori è §8.4 primario ma anche
    §7.5 informazioni documentate e §9.1 monitoraggio). Le card primarie hanno
    priorità nell'ordine (vengono prima nel merge col semantico)."""
    primary: Dict[str, List[Dict[str, Any]]] = {}
    secondary: Dict[str, List[Dict[str, Any]]] = {}
    for card in cards_by_id.values():
        for num in _extract_clause_numbers(str(card.get("iso_clause_primary", ""))):
            primary.setdefault(num, []).append(card)
        for sec in (card.get("iso_clauses_secondary") or []):
            for num in _extract_clause_numbers(str(sec)):
                secondary.setdefault(num, []).append(card)

    out: Dict[str, List[Dict[str, Any]]] = {}
    for num in set(primary) | set(secondary):
        seen: set = set()
        merged: List[Dict[str, Any]] = []
        for card in primary.get(num, []) + secondary.get(num, []):
            eid = str(card.get("evidence_id", ""))
            if eid and eid not in seen:
                seen.add(eid)
                merged.append(card)
        out[num] = merged
    return out


def _card_to_evidence(card: Dict[str, Any]) -> Dict[str, Any]:
    """Converte una evidence card (Phase 2) in una entry della stessa forma dei
    risultati di retrieval, così si fonde col semantico e il prompt la rende
    identica. L'excerpt usa il summary inglese (segnale pulito)."""
    excerpts = card.get("excerpts") or []
    pages: List[int] = []
    if excerpts and isinstance(excerpts[0], dict):
        pages = [int(p) for p in (excerpts[0].get("pages") or []) if str(p).isdigit()]
    excerpt = str(card.get("summary", "") or "")
    if not excerpt and excerpts and isinstance(excerpts[0], dict):
        excerpt = str(excerpts[0].get("text", "") or "")
    return {
        "evidence_id":        str(card.get("evidence_id", "")),
        "file_name":          str(card.get("file_name", "")),
        "doc_type":           str(card.get("doc_type", "other")),
        "iso_clause_primary": str(card.get("iso_clause_primary", "")),
        "gap_signal":         bool(card.get("gap_signal", False)),
        "confidence":         float(card.get("confidence", 0.5) or 0.5),
        "chunk_kind":         "summary",
        "pages":              pages,
        "excerpt":            excerpt[:1500],
        "distance":           0.0,   # tag-match → priorità massima
    }


def _retrieve_with_fallback(
    evidence_service: EvidenceService,
    clause: Dict[str, Any],
    tagged_cards: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Retrieval ibrido (fix 2026-06-14): combina

      0. **Inclusione garantita per tag**: le card che la Phase 2 ha classificato
         su questa clausola (`iso_clause_primary`) sono SEMPRE incluse. Riconnette
         la classificazione al retrieval, che da solo (semantico puro) lasciava
         clausole con evidenza reale a 0-1 card → falsi MAJOR.

      1. Critical/SPoF clauses → finestra semantica più ampia (TOP_K=8 vs 4).

      2. Se tutto è vuoto → retry semantico con cap largo (anti "no evidence"
         da ranking sfortunato).

    Additivo: il semantico è invariato; le card taggate si aggiungono e
    de-duplicano per evidence_id. Se non esiste alcuna card taggata (assenza
    reale), il comportamento è identico a prima → MAJOR corretto.
    """
    is_critical = bool(
        clause.get("is_spof", False)
        or get_criticality_tier(clause) == "critical"
    )
    top_k = GAP_RETRIEVAL_TOP_K_CRITICAL if is_critical else GAP_RETRIEVAL_TOP_K

    # Sprint R2 — over-fetch e diversify: max 2 chunk per evidence_id.
    raw_results = evidence_service.get_evidences_for_clause(clause, n=top_k * 2)
    semantic = _diversify_chunks(raw_results, max_per_doc=2, cap=top_k)
    base_cap, tag_cap = top_k, GAP_RETRIEVAL_TAG_CAP

    # Piano motore Fase 1 (RETRIEVE_PER_REQUIREMENT) — una query per requisito
    # atomico (testo + indizio di verifica), oltre a quella per clausola: la query
    # unica titolo+parole chiave pescava 4-8 frammenti per clausole con fino a 15
    # requisiti, e i requisiti non "coperti" dalla query finivano ABSENT.
    from compliance import features
    reqs = clause.get("atomic_requirements") or []
    if reqs and features.on("RETRIEVE_PER_REQUIREMENT"):
        extra: List[Dict[str, Any]] = []
        for req in reqs:
            q = " ".join(x for x in (req.get("text"), req.get("verification_hint")) if x)
            extra.extend(evidence_service.get_evidences_similar_to(q, n=GAP_RETRIEVAL_PER_REQ_K))
        seen_chunks = {(str(r.get("evidence_id", "")), (r.get("excerpt") or "")[:120]) for r in semantic}
        fresh = []
        for r in sorted(extra, key=lambda r: r.get("distance", 9.0)):
            k = (str(r.get("evidence_id", "")), (r.get("excerpt") or "")[:120])
            if k not in seen_chunks:
                seen_chunks.add(k)
                fresh.append(r)
        base_cap = min(top_k + len(reqs), GAP_RETRIEVAL_PER_REQ_CAP)
        tag_cap = max(tag_cap, base_cap)
        semantic = _diversify_chunks(semantic + fresh, max_per_doc=3, cap=base_cap)

    # Fix 2026-06-14 — fusione con le card taggate alla clausola (prima, perché
    # garantite pertinenti), poi il semantico non già incluso (dedup evidence_id).
    tagged_cards = tagged_cards or []
    if tagged_cards:
        tag_entries = [_card_to_evidence(c) for c in tagged_cards if c.get("evidence_id")]
        seen = {e["evidence_id"] for e in tag_entries}
        merged = tag_entries + [r for r in semantic if str(r.get("evidence_id", "")) not in seen]
        cap = min(max(base_cap, len(tag_entries) + 2), tag_cap)
        results = _diversify_chunks(merged, max_per_doc=2, cap=cap)
    else:
        results = semantic

    # Fallback: se ancora vuoto, retry semantico con cap largo.
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


# Piano motore Fase 2 (SEVERITY_RULES) — il prompt dello Stage A diceva al
# modello "nessuna evidenza → MAJOR, scrivi che non è stata identificata
# documentazione": il testo arrivava al cliente come accusa anche quando le
# regole ne limitano la gravità. Lo screening vede pochi frammenti per clausola:
# ciò che non trova va descritto come non trovato nell'evidenza esaminata.
_ABSENCE_RULE_SWAPS = (
    ("1. **Requirement not implemented at all** (no process, no document, no evidence whatsoever in "
     "`available_evidences`) → MAJOR.",
     "1. **Nothing relevant in `available_evidences`** → OBSERVATION. You see only a few retrieved "
     "excerpts, not the whole pack: write that the evidence was not found in the excerpts reviewed and "
     "should be verified. Never state that the organisation has no document, process or record."),
    ("- **Evidence completely absent for a clause** (`available_evidences: []`): score 15, severity MAJOR "
     "(or OBSERVATION if the clause is purely contextual — §4.x), state that no documentation was identified.",
     "- **Evidence completely absent for a clause** (`available_evidences: []`): score 65, severity "
     "OBSERVATION; write that no evidence was found in the excerpts reviewed and that it should be "
     "verified — never that the organisation lacks it."),
)


def _absence_wording_rules(prompt: str) -> str:
    for old, new in _ABSENCE_RULE_SWAPS:
        if old in prompt:
            prompt = prompt.replace(old, new)
        else:
            _log.warning("[SEVERITY_RULES] regola del prompt non trovata, non sostituita: %s", old[:60])
    return prompt


def _calibrate_blob_severity(gap: ClauseGap) -> ClauseGap:
    """Calibrazione simmetrica per le clausole SENZA atomic_requirements.

    Le clausole con atomic_requirements ricevono il credito parziale in Stage B
    (MAJOR→MINOR se il processo è evidenziato). Le clausole senza atomic
    requirements vengono valutate solo dal punteggio "blob" di Stage A e possono
    restare MAJOR pur avendo evidenza citata — incoerente. Qui si applica lo
    stesso principio: se un MAJOR blob ha evidenza reale (≥1 citazione) →
    documentato-ma-incompleto → MINOR. Assenza vera (nessuna citazione) → MAJOR.

    Tocca SOLO i MAJOR senza requirement_checks: i verdetti con atomic checks e
    i non-MAJOR restano invariati.
    """
    if gap.severity != "MAJOR" or gap.requirement_checks:
        return gap
    if gap.sources:
        gap.severity = "MINOR"
        gap.score = max(gap.score, 35)
        gap.is_spof = False
        if not gap.hedged:
            gap.hedged = True
            note = ("Relevant documentation is present but does not fully cover "
                    "the clause: downgraded from major to minor.")
            gap.hedge_note = (gap.hedge_note + " " + note).strip() if gap.hedge_note else note
    return gap


def _confine_peripheral_clause(
    gap: ClauseGap,
    clauses: Dict[str, Dict[str, Any]],
) -> ClauseGap:
    """Hardening 2026, problema #1 — confinazione delle clausole periferiche.

    Solo le clausole con una checklist curata (`atomic_requirements`, ar≥4) hanno la
    macchina per giustificare un verdetto ESTREMO: deep-verification sul testo
    integrale + credito parziale calibrato. Le clausole SENZA atomic_requirements
    (contesto §4.x e periferiche §8.x ecc.) vengono giudicate dal solo screening
    Stage A, che su 3 documentazioni diverse oscilla CONFORMANT↔MINOR↔MAJOR sulla
    stessa realtà, e che (se instradato allo Stage B con requisiti derivati) tende a
    over-severità (tutto-ABSENT→MAJOR). Le confiniamo quindi nella banda media:
      - mai MAJOR  → MINOR (standard) / OBSERVATION (passing/contesto)
      - mai CONFORMANT → OBSERVATION
    I verdetti forti restano riservati alla spina dorsale curata (incl. 5.2 politica
    e 6.2 obiettivi, che sono 'standard' di tier ma hanno atomic_requirements → NON
    confinate). Rimuove insieme instabilità e over-severità sulle periferiche.

    Nota: nessuna clausola `critical` è ar=0 (tutte le critiche hanno
    atomic_requirements), quindi l'early-exit sotto le preserva tutte.
    """
    clause = clauses.get(gap.clause_id, {})
    if clause.get("atomic_requirements"):
        return gap  # clausola curata: intero spettro di severità consentito
    tier = get_criticality_tier(clause) if clause else "standard"

    if gap.severity == "MAJOR":
        if tier == "passing":
            gap.severity, lo, hi = "OBSERVATION", 60, 84
        else:
            gap.severity, lo, hi = "MINOR", 30, 59
        gap.is_spof = False
        gap.score = max(lo, min(hi, gap.score or lo + 10))
        _hedge_gap(gap, "Peripheral clause without a curated checklist: capped below "
                        "major (major findings are reserved for core QMS clauses).")
    elif gap.severity == "CONFORMANT":
        # Piano motore Fase 2 (SEVERITY_RULES): una conformità con citazioni valide
        # (cite-or-fail) resta conformità; declassarla d'ufficio era eccesso di
        # severità, e lasciava sull'osservazione l'azione "istituisci" del template.
        from compliance import features
        if features.on("SEVERITY_RULES") and gap.sources:
            return gap
        gap.severity = "OBSERVATION"
        gap.score = max(60, min(84, gap.score or 75))
        _hedge_gap(gap, "Full conformity is asserted only for core QMS clauses with a "
                        "curated checklist; reported here as a positive observation.")
    return gap


def _hedge_gap(gap: ClauseGap, note: str) -> None:
    """Marca il gap come hedged e accoda la nota (idempotente sul testo)."""
    gap.hedged = True
    gap.hedge_note = (gap.hedge_note + " " + note).strip() if gap.hedge_note else note


def _honest_sources(gap: ClauseGap) -> ClauseGap:
    """Hardening 2026 #6 — fonti oneste sulle assenze genuine.

    Un verdetto MAJOR di assenza non deve esibire 'fonti': se nessun
    requirement_check è PRESENT/PARTIAL (o non ci sono check), i documenti citati
    sono vicini semantici esaminati ma NON a supporto del finding ('nulla trovato').
    Mostrarli contraddice la conclusione e mina la credibilità. Le evidenze reali
    (PRESENT/PARTIAL) non vengono mai toccate.
    """
    if gap.severity != "MAJOR":
        return gap
    checks = gap.requirement_checks or []
    has_support = any(getattr(c, "status", "") in ("PRESENT", "PARTIAL") for c in checks)
    if not has_support:
        gap.sources = []
    return gap


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
    risk_register_provider: Optional[Callable[[], str]] = None,
) -> List[ClauseGap]:
    clause_list = _sort_clauses_by_criticality(list(clauses.values()))

    # Fix retrieval (2026-06-14) — indice numero-clausola → card dal tag
    # `iso_clause_primary` della Phase 2, per l'inclusione garantita nel retrieval.
    cards_by_clause = build_cards_by_clause(cards_by_id)

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
            (
                clause,
                _retrieve_with_fallback(
                    evidence_service, clause,
                    tagged_cards=cards_by_clause.get(_clause_number_from_id(clause["id"]), []),
                ),
            )
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
        # Overlap 2026-07: qui finisce lo Stage A e inizia lo Stage B — è il
        # punto dove il registro rischi serve davvero. Il provider joina il
        # future della 2.7 (no-op se è già completa).
        if risk_register_provider is not None:
            risk_register_text = risk_register_provider()
        try:
            from compliance.deep_verifier import run_deep_verification
            # Hardening 2026 (raffinamento #3) — doc-selection ibrida per lo Stage B:
            # i documenti che la Phase 2 ha TAGGATO sulla clausola (iso_clause_primary
            # /secondary) vengono letti in pieno con priorità, oltre alle citazioni
            # Stage A + retrieval. Stesso principio del fix retrieval Stage A; riduce
            # la varianza per cui una clausola curata (es. 8.1/8.4) diventa MAJOR
            # perché lo Stage B aveva letto i documenti sbagliati.
            tagged_docs_by_clause = {
                cid: [c.get("file_name", "")
                      for c in cards_by_clause.get(_clause_number_from_id(cid), [])
                      if c.get("file_name")]
                for cid in clauses
            }
            all_gaps = run_deep_verification(
                norm=norm,
                gaps=all_gaps,
                clauses=clauses,
                docs_by_name=docs_by_name,
                cards_by_id=cards_by_id,
                evidence_service=evidence_service,
                tagged_docs_by_clause=tagged_docs_by_clause,
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

    # ── Calibrazione finale uniforme (2026-06-14, Opzione B) ─────────────────
    # Principio unico: MAJOR = assenza vera di evidenza; documentato-ma-incompleto
    # = MINOR. Le clausole CON atomic_requirements sono già calibrate dal credito
    # parziale in Stage B; qui si chiude la simmetria sulle clausole SENZA atomic
    # requirements (blob-scored da Stage A), che altrimenti restano MAJOR pur
    # avendo evidenza. Le assenze vere (nessuna citazione) restano MAJOR.
    return finalise_gaps(all_gaps, clauses)


def finalise_gaps(all_gaps: List[ClauseGap], clauses: Dict[str, Dict[str, Any]]) -> List[ClauseGap]:
    """Calibrazioni finali di una norma (anche dopo la rilettura tra norme, cross_norm)."""
    all_gaps = [_calibrate_blob_severity(g) for g in all_gaps]

    # ── Fonti oneste sulle assenze (Hardening 2026, problema #6) ─────────────
    # Rimuove i vicini semantici irrilevanti dai MAJOR di assenza genuina, PRIMA
    # della confinazione (così agisce sui verdetti MAJOR originali).
    all_gaps = [_honest_sources(g) for g in all_gaps]

    # ── Confinazione clausole periferiche (Hardening 2026, problema #1) ───────
    # Le clausole senza atomic_requirements (ar=0) non possono ricevere verdetti
    # estremi: i verdetti forti sono riservati alla spina dorsale curata.
    all_gaps = [_confine_peripheral_clause(g, clauses) for g in all_gaps]

    # ── Piano motore Fase 2 (SEVERITY_RULES) — la gravità la decide Python ───
    # Per ultime, sopra ogni calibrazione: nessuna NC senza prova per requisito;
    # le assenze non verificate diventano punti "da verificare".
    from compliance import features
    if features.on("SEVERITY_RULES"):
        from compliance import severity_rules
        all_gaps = severity_rules.apply_all(all_gaps, clauses)
    # ── Fase 2 (ACTIONS_FROM_STATES) — il verbo dell'azione dagli stati ──────
    if features.on("ACTIONS_FROM_STATES"):
        from compliance import action_rules
        all_gaps = action_rules.apply_all(all_gaps, clauses)

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
        from compliance import features as _features
        if di_absent and _features.on("SEVERITY_RULES"):
            # Piano motore Fase 2: la 2.6 non cerca nel testo completo (e su un
            # errore del modello segna tutto assente): non è una prova.
            parts.append("- documented_info_check (NOT confirmed — matched on card metadata only; the item "
                         "may exist under another name or inside another document): these items were not "
                         "matched:")
        elif di_absent:
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
                # Piano motore Fase 3: un documento di un fornitore o di un ente non
                # prova il sistema del cliente (scope, politica, ruoli, registri).
                if ev.get("issuer"):
                    who = ev["issuer"] + (f" ({ev['issuer_name']})" if ev.get("issuer_name") else "")
                    parts.append(f"      issued_by: {who}")
                if ev.get("domain"):
                    parts.append(f"      domain: {ev['domain']}")
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
#
# Hardening 2026-07: i soli errori TRANSITORI hanno un budget separato e più
# paziente (6 tentativi, backoff fino a 60s + jitter). Ragione: con i worker
# deep alti (18/norma su Railway) un burst sopra i 3M TPM produce 429 a
# raffica; con 3 retry corti una clausola poteva esaurirli e ripiegare sul
# verdetto Stage A (= degradazione di precisione silenziosa). Aspettare e
# rimandare la STESSA richiesta (temp 0, seed 42) non cambia mai l'output.
GAP_LLM_MAX_RETRIES = 3            # risposte vuote / parse-fail (invariato)
GAP_LLM_TRANSIENT_RETRIES = 6      # 429 / timeout / connection
GAP_LLM_RETRY_BASE_DELAY = 2.0
GAP_LLM_RETRY_MAX_DELAY = 60.0


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

    import random as _random

    # Contatori separati (Hardening 2026-07): le risposte vuote mantengono il
    # budget storico di 3; gli errori transitori (429/timeout/connection) hanno
    # un budget di 6 con backoff esponenziale + jitter fino a 60s, così un
    # burst sopra quota ASPETTA invece di degradare al verdetto Stage A.
    empty_attempts = 0
    transient_attempts = 0
    while True:
        backoff_step = 0
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
            empty_attempts += 1
            _log.warning(
                "[Phase 3] Azure returned empty response (attempt %d/%d) — retrying",
                empty_attempts, GAP_LLM_MAX_RETRIES,
            )
            if empty_attempts >= GAP_LLM_MAX_RETRIES:
                break
            backoff_step = empty_attempts
        except Exception as e:
            msg = str(e).lower()
            is_transient = (
                "rate limit" in msg or "rate_limit" in msg
                or "429" in msg or "timeout" in msg
                or "connection" in msg
            )
            if not is_transient:
                _log.warning("[Phase 3] Azure failed (fatal): %s", str(e)[:200])
                break  # non-retryable
            transient_attempts += 1
            _log.warning(
                "[Phase 3] Azure attempt %d/%d failed (transient): %s",
                transient_attempts, GAP_LLM_TRANSIENT_RETRIES, str(e)[:200],
            )
            if transient_attempts >= GAP_LLM_TRANSIENT_RETRIES:
                break
            backoff_step = transient_attempts
        _time.sleep(min(
            GAP_LLM_RETRY_BASE_DELAY * (2 ** (backoff_step - 1)),
            GAP_LLM_RETRY_MAX_DELAY,
        ) * _random.uniform(0.8, 1.2))

    _log.error("[Phase 3] Azure exhausted (%d empty, %d transient) — no fallback configured",
               empty_attempts, transient_attempts)
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

    # Calibrazione 2026-06-14 (Opzione B) — floor softening: il floor NON forza
    # più MAJOR quando la clausola ha evidenza reale (almeno una citazione, o un
    # atomic requirement PRESENT/PARTIAL). Distingue "assenza vera" (nessuna
    # evidenza → MAJOR legittimo) da "processo evidenziato ma incompleto"
    # (→ al massimo MINOR). Il floor continua a escalare verso MINOR e resta
    # MAJOR solo dove non c'è nulla.
    if floor == "MAJOR":
        checks = gap.requirement_checks or []
        has_evidence = bool(gap.sources) or any(
            getattr(c, "status", "") in ("PRESENT", "PARTIAL") for c in checks
        )
        if has_evidence:
            floor = "MINOR"

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

def _norm_prompt_text(norm_cfg: Dict[str, Any]) -> str:
    """Prompt della norma; con JURISDICTION_FILTER adattato al paese (la chiave
    "country" esiste nel registry solo con l'interruttore acceso)."""
    text = _load_file(norm_cfg["prompt_path"])
    if "country" in norm_cfg:
        from compliance.jurisdiction import adapt_prompt
        text = adapt_prompt(text, norm_cfg.get("country"))
    return text


def _load_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_prompt(path: Path, context_block: str) -> str:
    text = _load_file(path)
    return text.replace("{company_context}", context_block)
