"""
ComplianceOS — Real Gap Analyser (Phase 3).

Pipeline:
  1. Parse evidence YAML → list of card dicts
  2. Index cards in ChromaDB (EvidenceEmbedder)
  3. For each norm → for each clause:
       a. Query ChromaDB for relevant evidence
       b. Build prompt (base + norm-specific)
       c. Call Azure GPT-4.1-mini (streaming, with Gemini fallback)
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

_log = logging.getLogger("compliance.gap_analyzer")


# ── Phase 3 tuning constants ─────────────────────────────────────────────────

GAP_BATCH_SIZE = 10            # clauses per LLM call (was: 1)
GAP_MAX_WORKERS = 3            # parallel batch workers per norm
GAP_BATCH_MAX_TOKENS = 4096    # output budget per batch
GAP_RETRIEVAL_TOP_K = 4        # evidence cards retrieved per clause

# Severity ordering used by the floor application
_SEVERITY_ORDER = {
    "CONFORMANT":  -1,
    "OBSERVATION":  0,
    "MINOR":        1,
    "MAJOR":        2,
}


# ── Prompt paths ──────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "compliance"
_BASE_GAP_PROMPT     = _PROMPTS_DIR / "gap_analysis_base.md"
_BATCH_GAP_PROMPT    = _PROMPTS_DIR / "gap_analysis_batch.md"
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
) -> ComplianceAnalysisResult:
    """
    Full gap analysis pipeline.

    Args:
        evidence_yaml:   Raw YAML string produced by Phase 1 (evidence extraction).
        company_context: Validated CompanyContext from the wizard.
        emitter:         Optional callable(pct, msg) for SSE progress streaming.

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
    indexed = embedder.index_evidence_cards(cards)
    emit(15.0, f"Embedded {indexed} cards. Starting gap analysis…")

    # Sprint 3.2 — wrap the embedder in an EvidenceService so retrieval goes
    # through the same typed API used by the chat endpoint and any future
    # post-audit query path. The service is non-owning: when we close it,
    # we still keep the embedder alive until the explicit close below.
    evidence_service = EvidenceService(analysis_id=analysis_id, embedder=embedder)

    context_block = build_context_prompt_block(company_context)
    # Phase 3 batches up to GAP_BATCH_SIZE clauses per LLM call — use the
    # batch-format prompt (gap_analysis_batch.md) so the model returns
    # `{"clauses": [...]}` instead of a single-clause JSON object.
    base_prompt   = _load_prompt(_BATCH_GAP_PROMPT, context_block)

    norms_to_analyse = [n for n in company_context.norms if n in _NORM_REGISTRY]
    emit(15.0, f"Running gap analysis for {len(norms_to_analyse)} norm(s) in parallel…")

    # Run norms in parallel using a thread pool (LLM calls are I/O-bound)
    norm_reports: List[NormGapReport] = _analyse_norms_parallel(
        norms=norms_to_analyse,
        base_prompt=base_prompt,
        evidence_service=evidence_service,
        company_context=company_context,
        emit=emit,
        cards_by_id=cards_by_id,
    )

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
) -> List[NormGapReport]:
    """
    Run gap analysis for all requested norms in parallel using a thread pool.
    Each norm gets its own thread; LLM calls within a norm remain sequential
    (one per clause) to avoid overwhelming the Azure rate limit.
    Max 3 workers — one per norm.
    """
    if not norms:
        return []

    if len(norms) == 1:
        norm = norms[0]
        norm_cfg = _NORM_REGISTRY[norm]
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
        )
        return [_build_norm_report(norm, gaps)]

    pct_per_norm = 70.0 / len(norms)
    results: Dict[str, NormGapReport] = {}

    def analyse_one(norm_idx: int, norm: str) -> None:
        norm_cfg    = _NORM_REGISTRY[norm]
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
        )
        results[norm] = _build_norm_report(norm, gaps)

    with ThreadPoolExecutor(max_workers=min(len(norms), 3)) as pool:
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
) -> List[ClauseGap]:
    clause_list = _sort_clauses_by_criticality(list(clauses.values()))

    # Build batches of GAP_BATCH_SIZE clauses each
    batches: List[List[Dict[str, Any]]] = [
        clause_list[i : i + GAP_BATCH_SIZE]
        for i in range(0, len(clause_list), GAP_BATCH_SIZE)
    ]
    total_batches = len(batches)
    if total_batches == 0:
        return []

    pct_per_batch = pct_budget / total_batches
    results: Dict[int, List[ClauseGap]] = {}

    def _process_batch(batch_idx: int, batch: List[Dict[str, Any]]) -> None:
        emit(
            pct_base + batch_idx * pct_per_batch,
            f"{norm}: batch {batch_idx + 1}/{total_batches} ({len(batch)} clauses)…",
        )

        # Retrieve evidences for every clause in the batch via the typed
        # EvidenceService (Sprint 3.2). Same retrieval semantics as before,
        # just routed through the typed API so chat and tests share it.
        clause_evidences: List[tuple] = [
            (clause, evidence_service.get_evidences_for_clause(clause, n=GAP_RETRIEVAL_TOP_K))
            for clause in batch
        ]

        gaps = _analyse_clauses_batched(
            clause_evidences=clause_evidences,
            norm_prompt=norm_prompt,
            cards_by_id=cards_by_id,
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
    return all_gaps


# ── Batch-level analysis (single LLM call per batch) ──────────────────────────

def _analyse_clauses_batched(
    clause_evidences: List[tuple],  # [(clause, [evidence]), …]
    norm_prompt: str,
    cards_by_id: Dict[str, Dict[str, Any]],
) -> List[ClauseGap]:
    """
    Send N clauses to the LLM in a single call. Parse the array response.
    Apply cite-or-fail strict filtering + severity_floor on each verdict.
    """
    if not clause_evidences:
        return []

    user_prompt = _build_batch_user_prompt(clause_evidences)
    messages = [
        {"role": "system", "content": norm_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    raw = _call_llm(messages, max_tokens=GAP_BATCH_MAX_TOKENS)

    try:
        data = json.loads(_strip_code_fences(raw))
        clauses_response = data.get("clauses") or []
    except Exception as e:
        _log.warning(f"Failed to parse batch JSON ({e!s}); falling back per clause.")
        return [_fallback_clause_gap(c, f"batch parse failed: {e!s}") for (c, _) in clause_evidences]

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


def _build_batch_user_prompt(clause_evidences: List[tuple]) -> str:
    parts: List[str] = [
        f"## Batch of {len(clause_evidences)} clauses to assess",
        "",
        "Assess each clause independently against ONLY its own `available_evidences` list. "
        "Return a JSON object `{\"clauses\": [...]}` with one verdict per clause, in the same order.",
        "",
    ]
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
                excerpt = str(ev.get("excerpt", ""))[:400].replace("\n", " ")
                parts.append(f"      excerpt: {excerpt}")
        else:
            parts.append("    []   # no evidence retrieved for this clause")
        parts.append("")

    return "\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(messages: List[Dict[str, str]], max_tokens: int = 1024) -> str:
    """
    Call Azure GPT-4.1-mini. Falls back to Gemini on rate limit or error.
    Returns raw text (expected: JSON string).

    max_tokens defaults to 1024 (legacy single-clause call); batched callers
    pass GAP_BATCH_MAX_TOKENS (4096) for multi-clause responses.
    """
    try:
        from v2.azure_openai_client_v2 import AzureOpenAIClientV2
        from v2.provider_profiles_v2 import PROFILES

        profile = PROFILES.get("gpt-4.1-mini-azure")
        if profile is None:
            raise ValueError("gpt-4.1-mini-azure profile not found")

        client = AzureOpenAIClientV2(profile=profile)
        stream = client.chat_stream(messages=messages, max_tokens=max_tokens)

        chunks: List[str] = []
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta   = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    chunks.append(content)

        return "".join(chunks)

    except Exception as e:
        import logging as _log
        _log.getLogger("compliance.gap_analyzer").warning(f"Azure LLM failed, falling back to Gemini: {e}")
        return _call_llm_gemini(messages)


def _call_llm_gemini(messages: List[Dict[str, str]]) -> str:
    """Gemini fallback for rate-limit or Azure unavailability."""
    try:
        from v2.gemini_client_v2 import GeminiClientV2, analyze_batch_streaming
        from v2.provider_profiles_v2 import PROFILES

        profile = PROFILES.get("gemini-2.5-flash")
        if profile is None:
            return json.dumps({"error": "no_gemini_profile"})

        sys_msg  = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msg = next((m["content"] for m in messages if m["role"] == "user"),   "")

        client = GeminiClientV2(profile=profile)
        result = analyze_batch_streaming(
            client=client,
            batch_docs=[{"filename": "gap_query", "content": user_msg}],
            universal_prompt=sys_msg,
        )
        return result.text or json.dumps({"error": "empty_gemini_response"})

    except Exception as e:
        return json.dumps({"error": str(e)})


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

    rem = data.get("remediation") or {}
    remediation = RemediationPlan(
        what=rem.get("what")   or clause["remediation_template"]["what"],
        who=rem.get("who")     or clause["remediation_template"]["who"],
        when=rem.get("when")   or clause["remediation_template"]["when_major"],
        effort=rem.get("effort") or clause["remediation_template"]["effort"],
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
    note = f"[severity floor applied — clause is {tier}] "
    gap.severity = floor
    gap.finding = (note + gap.finding)[:800]
    # Re-evaluate SPoF flag with the escalated severity
    gap.is_spof = bool(clause.get("is_spof", False)) and gap.severity == "MAJOR"
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

def _build_norm_report(norm: str, gaps: List[ClauseGap]) -> NormGapReport:
    total_score = sum(g.score for g in gaps)
    overall = round(total_score / len(gaps)) if gaps else 0

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
