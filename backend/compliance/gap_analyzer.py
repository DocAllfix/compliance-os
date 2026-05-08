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

from compliance.embedder import EvidenceEmbedder
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


# ── Prompt paths ──────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "compliance"
_BASE_GAP_PROMPT     = _PROMPTS_DIR / "gap_analysis_base.md"
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

    embedder = EvidenceEmbedder(analysis_id)
    indexed = embedder.index_evidence_cards(cards)
    emit(15.0, f"Embedded {indexed} cards. Starting gap analysis…")

    context_block = build_context_prompt_block(company_context)
    base_prompt   = _load_prompt(_BASE_GAP_PROMPT, context_block)

    norms_to_analyse = [n for n in company_context.norms if n in _NORM_REGISTRY]
    emit(15.0, f"Running gap analysis for {len(norms_to_analyse)} norm(s) in parallel…")

    # Run norms in parallel using a thread pool (LLM calls are I/O-bound)
    norm_reports: List[NormGapReport] = _analyse_norms_parallel(
        norms=norms_to_analyse,
        base_prompt=base_prompt,
        embedder=embedder,
        company_context=company_context,
        emit=emit,
    )

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
    embedder: EvidenceEmbedder,
    company_context: CompanyContext,
    emit: Callable,
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
            embedder=embedder,
            company_context=company_context,
            emit=emit,
            pct_base=15.0,
            pct_budget=70.0,
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
            embedder=embedder,
            company_context=company_context,
            emit=emit,
            pct_base=15.0 + norm_idx * pct_per_norm,
            pct_budget=pct_per_norm,
        )
        results[norm] = _build_norm_report(norm, gaps)

    with ThreadPoolExecutor(max_workers=min(len(norms), 3)) as pool:
        futures = [pool.submit(analyse_one, i, norm) for i, norm in enumerate(norms)]
        for f in futures:
            f.result()  # propagate exceptions

    return [results[n] for n in norms if n in results]


# ── Norm-level analysis ───────────────────────────────────────────────────────

def _analyse_norm(
    norm: str,
    clauses: Dict[str, Dict[str, Any]],
    norm_prompt: str,
    embedder: EvidenceEmbedder,
    company_context: CompanyContext,
    emit: Callable,
    pct_base: float,
    pct_budget: float,
) -> List[ClauseGap]:
    clause_list = list(clauses.values())
    gaps: List[ClauseGap] = []
    pct_per_clause = pct_budget / max(len(clause_list), 1)

    for i, clause in enumerate(clause_list):
        clause_pct = pct_base + i * pct_per_clause
        emit(clause_pct, f"Checking §{clause['title'].split(' ')[0]}…")

        evidence = embedder.query_for_clause(clause, n_results=4)
        gap = _analyse_clause(
            clause=clause,
            evidence=evidence,
            norm_prompt=norm_prompt,
            company_context=company_context,
        )
        gaps.append(gap)

    return gaps


# ── Clause-level analysis ─────────────────────────────────────────────────────

def _analyse_clause(
    clause: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    norm_prompt: str,
    company_context: CompanyContext,
) -> ClauseGap:
    user_prompt = _build_clause_user_prompt(clause, evidence)
    messages = [
        {"role": "system", "content": norm_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    raw_json = _call_llm(messages)

    try:
        data = json.loads(raw_json)
        return _parse_clause_gap(data, clause)
    except Exception as e:
        return _fallback_clause_gap(clause, str(e))


def _build_clause_user_prompt(
    clause: Dict[str, Any],
    evidence: List[Dict[str, Any]],
) -> str:
    parts = [
        "## Clause to assess",
        f"ID: {clause['id']}",
        f"Title: {clause['title']}",
        f"Area: {clause['area']}",
        f"is_spof: {clause['is_spof']}",
        f"Critical sectors: {', '.join(clause.get('critical_sectors', [])) or 'none'}",
        "",
        "Typical non-conformities for this clause:",
    ]
    for nc in clause.get("typical_ncs", []):
        parts.append(f"  - {nc}")

    rem = clause.get("remediation_template", {})
    parts += [
        "",
        "Remediation template (use as starting point):",
        f"  What: {rem.get('what', '')}",
        f"  Who: {rem.get('who', '')}",
        f"  When (major): {rem.get('when_major', '')}",
        f"  When (minor): {rem.get('when_minor', '')}",
        f"  Effort: {rem.get('effort', '')}",
    ]

    if evidence:
        parts += ["", "## Relevant evidence cards retrieved"]
        for ev in evidence:
            parts += [
                "---",
                f"evidence_id: {ev.get('evidence_id', '')}",
                f"file_name: {ev.get('file_name', '')}",
                f"doc_type: {ev.get('doc_type', '')}",
                f"iso_clause_primary: {ev.get('iso_clause_primary', '')}",
                f"gap_signal: {ev.get('gap_signal', False)}",
                f"excerpt: {ev.get('excerpt', '')[:400]}",
            ]
    else:
        parts += ["", "## No relevant evidence found",
                  "No documentation was retrieved for this clause."]

    return "\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(messages: List[Dict[str, str]]) -> str:
    """
    Call Azure GPT-4.1-mini. Falls back to Gemini on rate limit or error.
    Returns raw text (expected: JSON string).
    """
    try:
        from v2.azure_openai_client_v2 import AzureOpenAIClientV2, AzureRateLimitExhausted
        from v2.provider_profiles_v2 import PROVIDER_PROFILES

        profile = PROVIDER_PROFILES.get("gpt-4.1-mini")
        if profile is None:
            raise ValueError("gpt-4.1-mini profile not found")

        client = AzureOpenAIClientV2(profile=profile)
        stream = client.chat_stream(messages=messages, max_tokens=1024)

        chunks: List[str] = []
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta   = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    chunks.append(content)

        return "".join(chunks)

    except Exception:
        return _call_llm_gemini(messages)


def _call_llm_gemini(messages: List[Dict[str, str]]) -> str:
    """Gemini fallback for rate-limit or Azure unavailability."""
    try:
        from v2.gemini_client_v2 import GeminiClientV2, analyze_batch_streaming
        from v2.provider_profiles_v2 import PROVIDER_PROFILES

        profile = PROVIDER_PROFILES.get("gemini-2.5-flash")
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


# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_clause_gap(data: Dict[str, Any], clause: Dict[str, Any]) -> ClauseGap:
    sources = [
        TraceabilityLink(
            evidence_id=s.get("evidence_id", ""),
            file_name=s.get("file_name", ""),
            pages=s.get("pages", []),
            excerpt=str(s.get("excerpt", ""))[:300],
            relevance_score=float(s.get("relevance_score", 0.5)),
        )
        for s in (data.get("sources") or [])
    ]

    rem = data.get("remediation") or {}
    remediation = RemediationPlan(
        what=rem.get("what")   or clause["remediation_template"]["what"],
        who=rem.get("who")     or clause["remediation_template"]["who"],
        when=rem.get("when")   or clause["remediation_template"]["when_major"],
        effort=rem.get("effort") or clause["remediation_template"]["effort"],
    )

    severity = str(data.get("severity", "OBSERVATION")).upper()
    if severity not in ("MAJOR", "MINOR", "OBSERVATION", "CONFORMANT"):
        severity = "OBSERVATION"

    score = max(0, min(100, int(data.get("score", 50))))
    is_spof = bool(data.get("is_spof", False)) and clause.get("is_spof", False) and severity == "MAJOR"

    return ClauseGap(
        clause_id=clause["id"],
        clause_title=clause["title"],
        score=score,
        severity=severity,
        is_spof=is_spof,
        finding=str(data.get("finding", "No finding generated."))[:800],
        sources=sources,
        remediation=remediation,
    )


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

    try:
        raw = yaml.safe_load(evidence_yaml)
        if isinstance(raw, list):
            return [c for c in raw if isinstance(c, dict)]
        if isinstance(raw, dict):
            return [raw]
    except yaml.YAMLError:
        pass

    # Fallback: split on card delimiters and parse each block
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


# ── File helpers ──────────────────────────────────────────────────────────────

def _load_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_prompt(path: Path, context_block: str) -> str:
    text = _load_file(path)
    return text.replace("{company_context}", context_block)
