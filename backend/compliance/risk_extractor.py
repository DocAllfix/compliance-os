"""
Amisys QHSE — Phase 2.7: Structured Risk Extraction (Sprint R8, promise P2).

The promise to Five Rise (14/05/2026) was explicit:

    "For risk-related documents (DVR, environmental aspects, risks and
     opportunities) it EXTRACTS the identified risks, the methodology used,
     the score assigned, the mitigation measures, the owner. Where the
     clause requires the criteria to be defined, it checks if they are
     really applied or only declared."

The deep verification pass (Stage B) VERIFIES; this module EXTRACTS: it reads
the full text of every document classified as a risk document and produces a
structured register — one entry per identified risk, with methodology, score,
mitigation and owner as data fields, each flagged when missing.

Consumers:
  - the result payload (`risk_register_extract`) — visible to UI/report/chat
  - the cross-clause pass (risk → control chains get the actual risk list,
    not just per-clause excerpts)
  - the §6.1 deep verification context (criteria applied vs declared, backed
    by per-entry extraction instead of impressions)
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger("compliance.risk_extractor")

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "compliance" / "risk_extraction.md"

RISK_DOC_TYPES = {"risk_assessment"}
RISK_MAX_WORKERS = int(os.environ.get("RISK_MAX_WORKERS", "4"))
RISK_MAX_DOC_CHARS = 60_000
RISK_MAX_OUTPUT_TOKENS = 3500


def run_risk_extraction(
    cards: List[Dict[str, Any]],
    docs_by_name: Dict[str, str],
    context_block: str,
    llm_call: Callable[[List[Dict[str, str]], int], str],
    emitter: Optional[Callable[[float, str], None]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Phase 2.7 entry point. Returns a dict serialisable to
    schemas.RiskRegisterExtract, or None when no risk documents exist.

    Args:
        cards:        Phase 2 evidence cards (used to find risk documents)
        docs_by_name: normalised file name → full extracted text
        context_block: company context for the system prompt
        llm_call:     callable(messages, max_tokens) -> raw text
    """
    def emit(pct: float, msg: str) -> None:
        if emitter:
            try:
                emitter(pct, msg)
            except Exception:
                pass

    risk_docs: List[tuple] = []  # (file_name_display, doc_key, evidence_id)
    for card in cards:
        if str(card.get("doc_type", "")).lower().strip() in RISK_DOC_TYPES:
            fname = str(card.get("file_name", "") or "")
            key = _norm_name(fname)
            if key in docs_by_name:
                risk_docs.append((fname, key, str(card.get("evidence_id", "") or "")))

    if not risk_docs:
        return None

    try:
        prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        _log.warning("[Risk] prompt missing (%s) — skipping Phase 2.7", e)
        return None
    system_prompt = prompt_template.replace("{company_context}", context_block)

    emit(0.0, f"Extracting structured risk register from {len(risk_docs)} document(s)…")

    results: List[Optional[Dict[str, Any]]] = [None] * len(risk_docs)

    def _extract_one(idx: int, fname: str, key: str, evidence_id: str) -> None:
        try:
            results[idx] = _extract_document(
                fname, docs_by_name[key], evidence_id, system_prompt, llm_call,
            )
        except Exception as e:
            _log.warning("[Risk] extraction failed for %s: %s", fname, str(e)[:200])

    with ThreadPoolExecutor(max_workers=min(RISK_MAX_WORKERS, len(risk_docs))) as pool:
        futures = [
            pool.submit(_extract_one, i, fname, key, eid)
            for i, (fname, key, eid) in enumerate(risk_docs)
        ]
        for f in futures:
            f.result()

    documents = [r for r in results if r is not None]
    if not documents:
        return None

    all_risks = [risk for doc in documents for risk in doc["risks"]]
    unscored = [r for r in all_risks if not r.get("score_present")]
    unmitigated = [r for r in all_risks if not r.get("mitigation_present")]
    unowned = [r for r in all_risks if not r.get("owner_present")]

    emit(100.0, (
        f"Risk register extracted: {len(all_risks)} risks across "
        f"{len(documents)} document(s); {len(unscored)} unscored, "
        f"{len(unmitigated)} without mitigation, {len(unowned)} without owner."
    ))

    return {
        "documents": documents,
        "total_risks": len(all_risks),
        "unscored_count": len(unscored),
        "unmitigated_count": len(unmitigated),
        "unowned_count": len(unowned),
    }


def _extract_document(
    fname: str,
    text: str,
    evidence_id: str,
    system_prompt: str,
    llm_call: Callable,
) -> Optional[Dict[str, Any]]:
    # Content-filter fix 2026-07-10: l'istruzione va PRIMA del documento.
    # Un documento che TERMINA con un'istruzione è la firma esatta di una
    # indirect prompt injection per gli Azure Prompt Shields → 400 deterministico
    # (riprodotto sul pack Fred). Contenuto identico, cambia solo la posizione.
    user_prompt = (
        "Extract the structured risk register from the document below, "
        "following the system instructions.\n\n"
        f"### DOCUMENT: {fname}\n"
        + text[:RISK_MAX_DOC_CHARS]
        + "\n\n--- END OF DOCUMENT ---"
    )
    raw = llm_call(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        RISK_MAX_OUTPUT_TOKENS,
    )
    data = _parse_json(raw)
    if data is None:
        # one re-ask, mirroring the deep pass policy
        raw = llm_call(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            RISK_MAX_OUTPUT_TOKENS,
        )
        data = _parse_json(raw)
        if data is None:
            _log.warning("[Risk] %s: unparseable twice — skipped", fname)
            return None

    methodology = str(data.get("methodology") or "").strip() or None
    risks_out: List[Dict[str, Any]] = []
    for item in (data.get("risks") or []):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip() or None
        description = str(item.get("description") or "").strip()
        if not description:
            continue
        score = str(item.get("score") or "").strip() or None
        mitigation = str(item.get("mitigation") or "").strip() or None
        owner = str(item.get("owner") or "").strip() or None
        pages = [int(p) for p in (item.get("pages") or [])
                 if isinstance(p, int) or str(p).isdigit()]

        # Deterministic presence flags — "to be defined" / "TBC" style
        # placeholders count as MISSING, exactly what the promise requires
        # the engine to catch.
        risks_out.append({
            "ref": ref,
            "description": description[:300],
            "category": (str(item.get("category") or "").strip() or None),
            "score": score,
            "score_present": _is_substantive(score),
            "mitigation": (mitigation[:300] if mitigation else None),
            "mitigation_present": _is_substantive(mitigation),
            "owner": owner,
            "owner_present": _is_substantive(owner),
            "pages": pages,
        })

    return {
        "file_name": fname,
        "evidence_id": evidence_id,
        "methodology": methodology,
        "methodology_declared": bool(methodology),
        "risks": risks_out,
    }


_PLACEHOLDER_RE = re.compile(
    r"^(?:n/?a|none|null|-+|tbd|tbc|to be (?:defined|confirmed|determined|assigned)"
    r"|da definir\w*|da confermar\w*|da assegnar\w*|non definit\w*)\.?$",
    re.IGNORECASE,
)


def _is_substantive(value: Optional[str]) -> bool:
    """True when the field carries real content, not a placeholder."""
    if not value or not str(value).strip():
        return False
    return not _PLACEHOLDER_RE.match(str(value).strip())


def format_register_for_prompt(extract: Dict[str, Any], max_risks: int = 25) -> str:
    """Compact text view of the extracted register for chain/deep prompts."""
    lines: List[str] = ["## Extracted risk register (Phase 2.7 — structured)"]
    for doc in extract.get("documents", []):
        lines.append(f"### {doc['file_name']}")
        lines.append(f"- methodology declared: {doc.get('methodology') or 'NONE'}")
        for r in doc.get("risks", [])[:max_risks]:
            lines.append(
                f"- [{r.get('ref') or '—'}] {r['description'][:120]}"
                f" | score: {r.get('score') if r.get('score_present') else 'MISSING'}"
                f" | mitigation: {('yes' if r.get('mitigation_present') else 'MISSING')}"
                f" | owner: {r.get('owner') if r.get('owner_present') else 'MISSING'}"
            )
    return "\n".join(lines)


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
