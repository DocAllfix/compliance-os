"""
Amisys QHSE — Phase 3.5: Cross-Clause Coherence Pass (Sprint R5).

Per-clause verdicts cannot see the connective tissue of a management system:
a risk identified in 6.1 must have an operational control in 8.1 and a
monitoring indicator in 9.1; objectives in 6.2 must be measured in 9.1 and
reviewed in 9.3. This module verifies those declarative CHAINS with one LLM
call per chain, grounded exclusively on the evidence already cited by the
per-clause analysis (Stage A + Stage B).

Satisfies PRD §1.4.2c ("logical contextual linkages between documentation and
data") and promise P6 (cross-clause checks 6.1 → 8.1 → 9.1).
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from compliance.schemas import ClauseGap, CrossClauseFinding, TraceabilityLink

_log = logging.getLogger("compliance.cross_clause")

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "compliance" / "cross_clause_prompt.md"

# 9 chain, una call piccola ciascuna → tutte in parallelo (quota 3M TPM deep).
CROSS_MAX_WORKERS = int(os.environ.get("CROSS_MAX_WORKERS", "9"))
CROSS_MAX_OUTPUT_TOKENS = 800


# ── Chain registry (declarative — data, not code) ─────────────────────────────

CHAINS: List[Dict[str, Any]] = [
    {
        "chain_id": "9001_risk_to_control",
        "norm": "ISO 9001:2015",
        "title": "Risk → operational control → monitoring",
        "clause_ids": ["9001_6_1", "9001_8_1", "9001_9_1"],
        "question": (
            "Do the risks identified in 6.1 have corresponding operational "
            "controls (8.1), and are those controls covered by monitoring "
            "indicators (9.1)?"
        ),
    },
    {
        "chain_id": "9001_objectives_loop",
        "norm": "ISO 9001:2015",
        "title": "Objectives → measurement → management review",
        "clause_ids": ["9001_6_2", "9001_9_1", "9001_9_3"],
        "question": (
            "Are the quality objectives (6.2) actually measured (9.1) and is "
            "their achievement reviewed at management review (9.3)?"
        ),
    },
    {
        "chain_id": "9001_nc_to_mr",
        "norm": "ISO 9001:2015",
        "title": "Nonconformities → corrective action → management review",
        "clause_ids": ["9001_10_2", "9001_9_3"],
        "question": (
            "Do nonconformities and corrective actions (10.2) appear among the "
            "management review inputs (9.3)?"
        ),
    },
    {
        "chain_id": "14001_aspects_to_control",
        "norm": "ISO 14001:2015",
        "title": "Significant aspects → operational control → monitoring",
        "clause_ids": ["14001_6_1_2", "14001_8_1", "14001_9_1"],
        "question": (
            "Do the significant environmental aspects (6.1.2) have "
            "corresponding operational controls (8.1), and are those aspects "
            "covered by environmental monitoring (9.1)?"
        ),
    },
    {
        "chain_id": "14001_objectives_loop",
        "norm": "ISO 14001:2015",
        "title": "Environmental objectives → monitoring → management review",
        "clause_ids": ["14001_6_2", "14001_9_1", "14001_9_3"],
        "question": (
            "Are the environmental objectives (6.2) actually monitored with "
            "indicators (9.1) and is their achievement reviewed at management "
            "review (9.3)?"
        ),
    },
    {
        "chain_id": "14001_legal_loop",
        "norm": "ISO 14001:2015",
        "title": "Compliance obligations → compliance evaluation",
        "clause_ids": ["14001_6_1_3", "14001_9_1_2"],
        "question": (
            "Are the compliance obligations recorded in the legal register "
            "(6.1.3) actually evaluated for compliance (9.1.2)?"
        ),
    },
    {
        "chain_id": "45001_hazard_to_control",
        "norm": "ISO 45001:2018",
        "title": "Hazards → operational control → monitoring",
        "clause_ids": ["45001_6_1_2", "45001_8_1", "45001_9_1"],
        "question": (
            "Do the hazards identified in the risk assessment (6.1.2) have "
            "corresponding operational controls (8.1), and are those risks "
            "covered by OH&S monitoring (9.1)?"
        ),
    },
    {
        "chain_id": "45001_objectives_loop",
        "norm": "ISO 45001:2018",
        "title": "OH&S objectives → monitoring → management review",
        "clause_ids": ["45001_6_2", "45001_9_1", "45001_9_3"],
        "question": (
            "Are the OH&S objectives (6.2) actually monitored with indicators "
            "(9.1) and is their achievement reviewed at management review (9.3)?"
        ),
    },
    {
        "chain_id": "45001_consultation_loop",
        "norm": "ISO 45001:2018",
        "title": "Worker consultation → risk assessment → management review",
        "clause_ids": ["45001_5_4", "45001_6_1_2", "45001_9_3"],
        "question": (
            "Are workers consulted in hazard identification and risk "
            "assessment (5.4 → 6.1.2), and do consultation outcomes reach the "
            "management review (9.3)?"
        ),
    },
]


# ── Public entry point ────────────────────────────────────────────────────────

def run_cross_clause_checks(
    gaps_by_norm: Dict[str, List[ClauseGap]],
    context_block: str,
    llm_call: Callable[[List[Dict[str, str]], int], str],
    emit: Optional[Callable[[float, str], None]] = None,
    pct_base: float = 88.0,
    pct_budget: float = 4.0,
    risk_register_text: str = "",
) -> List[CrossClauseFinding]:
    """
    Run every chain whose norm was analysed. Returns CrossClauseFinding list.

    Args:
        gaps_by_norm: norm label → ClauseGap list (post Stage A+B)
        context_block: company context for the system prompt
        llm_call:      callable(messages, max_tokens) -> raw text
    """
    def _emit(pct: float, msg: str) -> None:
        if emit:
            try:
                emit(pct, msg)
            except Exception:
                pass

    try:
        prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        _log.warning("[CrossClause] prompt missing (%s) — skipping Phase 3.5", e)
        return []

    system_prompt = prompt_template.replace("{company_context}", context_block)

    # Index gaps by clause_id for quick lookup
    gaps_by_id: Dict[str, ClauseGap] = {}
    for norm, gaps in gaps_by_norm.items():
        for g in gaps:
            gaps_by_id[g.clause_id] = g

    chains = [c for c in CHAINS if c["norm"] in gaps_by_norm]
    if not chains:
        return []

    _emit(pct_base, f"Cross-clause coherence: checking {len(chains)} chains…")

    findings: List[Optional[CrossClauseFinding]] = [None] * len(chains)

    def _run_one(idx: int, chain: Dict[str, Any]) -> None:
        try:
            findings[idx] = _check_chain(
                chain, gaps_by_id, system_prompt, llm_call,
                risk_register_text=risk_register_text,
            )
        except Exception as e:
            _log.warning("[CrossClause] chain %s failed: %s",
                         chain["chain_id"], str(e)[:200])

    with ThreadPoolExecutor(max_workers=min(CROSS_MAX_WORKERS, len(chains))) as pool:
        futures = [pool.submit(_run_one, i, c) for i, c in enumerate(chains)]
        for f in futures:
            f.result()

    out = [f for f in findings if f is not None]
    _emit(pct_base + pct_budget,
          f"Cross-clause coherence complete: "
          f"{sum(1 for f in out if f.status == 'LINKED')} linked, "
          f"{sum(1 for f in out if f.status == 'PARTIAL')} partial, "
          f"{sum(1 for f in out if f.status == 'BROKEN')} broken.")
    return out


# ── Single-chain check ────────────────────────────────────────────────────────

_VALID_STATUS = ("LINKED", "PARTIAL", "BROKEN", "NOT_ASSESSABLE")


def _check_chain(
    chain: Dict[str, Any],
    gaps_by_id: Dict[str, ClauseGap],
    system_prompt: str,
    llm_call: Callable,
    risk_register_text: str = "",
) -> Optional[CrossClauseFinding]:
    maybe_gaps = [gaps_by_id.get(cid) for cid in chain["clause_ids"]]
    node_gaps: List[ClauseGap] = [g for g in maybe_gaps if g is not None]
    if len(node_gaps) < 2:
        return None  # chain not meaningful for this analysis

    # Deterministic short-circuit: upstream node with zero evidence at all →
    # NOT_ASSESSABLE without an LLM call (do not guess).
    upstream = node_gaps[0]
    if not upstream.sources and upstream.severity == "MAJOR":
        return CrossClauseFinding(
            chain_id=chain["chain_id"],
            norm=chain["norm"],
            title=chain["title"],
            status="NOT_ASSESSABLE",
            narrative=(
                f"The chain cannot be evaluated: no usable evidence was found "
                f"for {upstream.clause_title}, the upstream step of this chain. "
                f"Address that gap first."
            ),
            clause_ids=chain["clause_ids"],
            sources=[],
        )

    user_prompt = _build_chain_prompt(chain, node_gaps)

    # Sprint R8 (P2) — risk chains receive the structured register so the
    # linkage check can name the SPECIFIC risks lacking a control, instead of
    # reasoning on per-clause excerpts alone.
    if risk_register_text and any(
        _RISK_NODE_RE.search(cid) for cid in chain["clause_ids"]
    ):
        user_prompt = risk_register_text + "\n\n" + user_prompt

    raw = llm_call(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        CROSS_MAX_OUTPUT_TOKENS,
    )
    data = _parse_json(raw)
    if data is None:
        _log.warning("[CrossClause] %s: unparseable response", chain["chain_id"])
        return None

    status = str(data.get("status", "")).upper()
    if status not in _VALID_STATUS:
        status = "NOT_ASSESSABLE"

    # Verify cited files against the evidence we actually provided.
    provided_files = {
        _norm_name(s.file_name): s
        for g in node_gaps for s in g.sources if s.file_name
    }
    sources: List[TraceabilityLink] = []
    for fname in (data.get("evidence_files") or []):
        link = provided_files.get(_norm_name(str(fname)))
        if link is not None and all(s.file_name != link.file_name for s in sources):
            sources.append(link)

    narrative = str(data.get("narrative", "") or "").strip()[:900]
    if not narrative:
        narrative = "No narrative produced for this chain."

    return CrossClauseFinding(
        chain_id=chain["chain_id"],
        norm=chain["norm"],
        title=chain["title"],
        status=status,
        narrative=narrative,
        clause_ids=chain["clause_ids"],
        sources=sources,
    )


def _build_chain_prompt(chain: Dict[str, Any], node_gaps: List[ClauseGap]) -> str:
    parts: List[str] = [
        f"## Chain: {chain['chain_id']}",
        f"- title: {chain['title']}",
        f"- norm: {chain['norm']}",
        f"- question: {chain['question']}",
        "",
        "## Per-clause analysis results (in chain order)",
    ]
    for g in node_gaps:
        parts.append(f"### {g.clause_id} — {g.clause_title}")
        parts.append(f"- severity: {g.severity} (score {g.score})")
        parts.append(f"- finding: {g.finding[:400]}")
        if g.requirement_checks:
            parts.append("- requirement_checks:")
            for chk in g.requirement_checks[:8]:
                parts.append(
                    f"    - {chk.requirement_id}: {chk.status}"
                    + (f" — {chk.note}" if chk.note else "")
                )
        if g.sources:
            parts.append("- cited evidence:")
            for s in g.sources[:4]:
                pages = f", p.{','.join(str(p) for p in s.pages)}" if s.pages else ""
                excerpt = (s.excerpt or "").replace("\n", " ")[:250]
                parts.append(f"    - [{s.file_name}{pages}] \"{excerpt}\"")
        else:
            parts.append("- cited evidence: none")
        parts.append("")

    parts.append("Evaluate the chain and return the JSON object as instructed.")
    return "\n".join(parts)


# ── Helpers ───────────────────────────────────────────────────────────────────

_RISK_NODE_RE = re.compile(r"_6_1(?:_[12])?$")


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
