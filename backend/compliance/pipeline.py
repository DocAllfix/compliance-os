"""
ComplianceOS — Compliance Pipeline Orchestrator.

Four-phase pipeline:
    Phase 1: ZIP extraction → text extraction per document
    Phase 2: Evidence extraction (LLM) → YAML evidence cards (batched + parallel)
    Phase 3: ChromaDB embedding + gap analysis per clause (LLM)
    Phase 4: Result persistence + SSE done event

SSE emitter contract:
    emitter(pct: float, msg: str)
    The FastAPI endpoint wraps an asyncio queue; this module stays sync.
    Call from a thread so as not to block the event loop.

Never raises: all errors are caught, emitted via SSE, and returned as
a dict with success=False so the endpoint can close the stream cleanly.
"""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from compliance.gap_analyzer import analyze_compliance
from compliance.schemas import CompanyContext, ComplianceAnalysisResult

_log = logging.getLogger("compliance.pipeline")


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 helper — text extraction from ZIP
# ──────────────────────────────────────────────────────────────────────────────

def _extract_documents(zip_bytes: bytes, emit: Callable) -> List[Dict[str, Any]]:
    """
    Extract and read text from all files in a ZIP archive.
    Returns a list of {filename, content} dicts.
    Uses the existing v2 text_extractor infrastructure where available.
    """
    emit(5.0, "Extracting documents from archive…")
    docs: List[Dict[str, Any]] = []

    try:
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            emit(8.0, f"Found {len(names)} files in archive.")

            for name in names:
                try:
                    raw = zf.read(name)
                    content = _read_file_content(name, raw)
                    if content:
                        docs.append({"filename": name, "content": content})
                except Exception as e:
                    emit(8.0, f"Warning: could not read {name}: {e}")

    except Exception as e:
        emit(5.0, f"Archive extraction failed: {e}")

    return docs


def _read_file_content(filename: str, raw: bytes) -> str:
    """Best-effort text extraction. Falls back to v2 text_extractor for PDFs."""
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md", ".csv"):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    if ext == ".pdf":
        # Try native text extraction first (fast, free)
        text = ""
        try:
            import io
            import pdfminer.high_level as pdfminer  # type: ignore
            text = pdfminer.extract_text(io.BytesIO(raw)) or ""
        except Exception:
            pass

        # If no text extracted, the PDF is likely scanned — use Azure DI OCR
        if not text.strip():
            from compliance.azure_ocr import ocr_pdf_bytes
            text = ocr_pdf_bytes(raw, filename=filename)

        return text

    if ext in (".docx", ".doc"):
        try:
            import io, docx  # type: ignore
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""

    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 helper — evidence extraction via LLM
# ──────────────────────────────────────────────────────────────────────────────

# ── Phase 2 tuning ─────────────────────────────────────────────────────────
# Batch size chosen for GPT-4.1-mini "needle-in-haystack" sweet spot:
#   - 5 docs/batch = ~95% per-doc completion quality
#   - With 6 parallel workers and Azure 200K TPM, max in-flight ~144K input tokens
#     leaving ~30% safety margin to avoid 429.
#   - Scales: 28 docs = 1 wave, 100 docs = 4 waves (~50s), 200 docs = 7 waves (~85s).
EVIDENCE_BATCH_SIZE = 5
EVIDENCE_MAX_WORKERS = 6
EVIDENCE_MAX_OUTPUT_TOKENS = 8000
EVIDENCE_DOC_CHAR_CAP = 15_000

# Retry config for transient 429 / connection errors (per single batch).
EVIDENCE_MAX_RETRIES = 3
EVIDENCE_RETRY_BASE_DELAY = 2.0
EVIDENCE_RETRY_MAX_DELAY = 30.0


def _extract_evidence(
    docs: List[Dict[str, Any]],
    company_context: CompanyContext,
    emit: Callable,
) -> str:
    """
    Phase 2 — Evidence extraction.

    Splits the documents into batches of EVIDENCE_BATCH_SIZE and processes them
    in parallel (max EVIDENCE_MAX_WORKERS threads) via Azure GPT-4.1-mini.
    Each batch is independent: per-doc YAML cards. Results are concatenated and
    DOC markers + evidence_id are renumbered globally so the existing fallback
    parser (`gap_analyzer._parse_evidence_yaml`) can read the merged output.

    Returns the concatenated raw YAML string (signature unchanged for compat).
    Failed batches contribute synthetic `readable: false` cards so the document
    set is preserved end-to-end.
    """
    from compliance.context_intake import build_context_prompt_block

    prompt_path = (
        Path(__file__).resolve().parent.parent
        / "prompts" / "compliance" / "evidence_extraction_prompt.md"
    )
    try:
        prompt_template = prompt_path.read_text(encoding="utf-8")
    except Exception:
        prompt_template = "Extract evidence cards from the following documents as YAML."

    context_block = build_context_prompt_block(company_context)
    system_prompt = prompt_template.replace("{company_context}", context_block)

    total = len(docs)
    if total == 0:
        return ""

    # Lazy single-client construction so all workers reuse one Azure SDK instance.
    azure_client = _build_evidence_azure_client()

    # Build batches preserving original document order.
    batches: List[List[Dict[str, Any]]] = [
        docs[i : i + EVIDENCE_BATCH_SIZE]
        for i in range(0, total, EVIDENCE_BATCH_SIZE)
    ]

    emit(20.0, f"Running evidence extraction on {total} documents in {len(batches)} batches…")

    # Index → (raw_yaml_or_None, batch_docs)
    batch_results: Dict[int, Optional[str]] = {}

    def _run_one(batch_idx: int, batch_docs: List[Dict[str, Any]]) -> tuple[int, Optional[str]]:
        raw = _call_llm_for_batch(
            azure_client=azure_client,
            system_prompt=system_prompt,
            batch_docs=batch_docs,
            batch_idx=batch_idx,
            total_batches=len(batches),
        )
        return batch_idx, raw

    workers = max(1, min(EVIDENCE_MAX_WORKERS, len(batches)))
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_run_one, idx, batch)
            for idx, batch in enumerate(batches)
        ]
        for fut in as_completed(futures):
            try:
                batch_idx, raw = fut.result()
                batch_results[batch_idx] = raw
            except Exception as e:
                _log.warning("[Phase 2] Batch failed irrecoverably: %s", e)
            completed += 1
            pct = 20.0 + (10.0 * completed / len(batches))
            emit(pct, f"Evidence extraction: {completed}/{len(batches)} batches done…")

    # Reconstruct in original order, filling failures with synthetic cards.
    # Strip meta/preamble before each batch so the fallback parser doesn't
    # choke on inter-batch `---` markers and `meta:` blocks (the parser splits
    # on `# ── DOC N ──`; anything between two markers must be parseable YAML).
    parts: List[str] = []
    for idx, batch in enumerate(batches):
        raw = batch_results.get(idx)
        if raw and raw.strip():
            parts.append(_strip_meta_block(raw))
        else:
            _log.warning(
                "[Phase 2] Batch %d/%d returned empty — emitting %d synthetic cards",
                idx + 1, len(batches), len(batch),
            )
            parts.append(_synthetic_yaml_for_batch(batch))

    combined = "\n\n".join(parts)

    # Renumber DOC markers and evidence_id globally so the parser sees a single
    # contiguous set instead of N batches each starting at 1.
    combined = _renumber_doc_markers(combined)
    combined = _renumber_evidence_ids(combined)

    # Sprint 2.2 — Post-LLM card validation (telemetry only; never mutates the
    # YAML string returned downstream).
    _validate_evidence_cards(combined)

    emit(35.0, "Evidence extraction complete. Indexing…")
    return combined


# ── Post-Phase-2 card validation (Sprint 2.2) ────────────────────────────────

_REQUIRED_CARD_FIELDS = ("evidence_id", "file_name", "iso_clause_primary", "gap_signal", "readable")
_VALID_DOC_TYPES = {
    "quality_manual", "procedure", "policy", "record", "audit_report",
    "training_record", "supplier_document", "risk_assessment",
    "calibration_record", "nonconformity_record", "management_review",
    "objective_plan", "legal_register", "emergency_plan",
    "communication_record", "contract_specification", "certificate", "other",
}


def _validate_evidence_cards(combined_yaml: str) -> None:
    """
    Telemetry-only Phase 2 validator.

    Parses the merged YAML, walks every card, and logs warnings for:
      - missing required fields
      - unknown doc_type values (will be silently treated as 'other' downstream)

    Does NOT mutate the input. Downstream parsing already tolerates missing
    fields with safe defaults; this function exists so we can spot prompt
    regressions early via logs / counters.
    """
    import logging as _log
    log = _log.getLogger("compliance.pipeline.phase2_validator")
    try:
        # Reuse the canonical parser to stay in sync with downstream behaviour
        from compliance.gap_analyzer import _parse_evidence_yaml
        cards = _parse_evidence_yaml(combined_yaml)
    except Exception as e:
        log.warning(f"Phase 2 validator: could not parse YAML for inspection: {e!s}")
        return

    missing_field_counts: Dict[str, int] = {}
    unknown_doc_types: Dict[str, int] = {}
    for card in cards:
        for field in _REQUIRED_CARD_FIELDS:
            if field not in card or card.get(field) in (None, ""):
                missing_field_counts[field] = missing_field_counts.get(field, 0) + 1
        dt = str(card.get("doc_type", "") or "").lower().strip()
        if dt and dt not in _VALID_DOC_TYPES:
            unknown_doc_types[dt] = unknown_doc_types.get(dt, 0) + 1

    if missing_field_counts:
        log.warning(
            f"Phase 2: {len(cards)} cards parsed; missing required fields counts: "
            f"{missing_field_counts}"
        )
    if unknown_doc_types:
        log.warning(
            f"Phase 2: {sum(unknown_doc_types.values())} cards have unknown doc_type "
            f"(will be treated as 'other' downstream): {unknown_doc_types}"
        )
    if not missing_field_counts and not unknown_doc_types:
        log.info(f"Phase 2: all {len(cards)} cards passed validation.")


# ── Helpers Phase 2 ──────────────────────────────────────────────────────────

def _build_evidence_azure_client():
    """Build a single Azure client to share across worker threads.

    Returns None if Azure is unreachable (caller falls back to Gemini per-batch).
    """
    try:
        from v2.azure_openai_client_v2 import AzureOpenAIClientV2
        from v2.provider_profiles_v2 import PROFILES
        profile = PROFILES.get("gpt-4.1-mini-azure")
        if profile is None:
            return None
        return AzureOpenAIClientV2(profile=profile)
    except Exception as e:
        _log.warning("[Phase 2] Azure client init failed: %s — batches will fall back", e)
        return None


def _build_user_prompt_for_batch(batch_docs: List[Dict[str, Any]]) -> str:
    """Build the user message listing the docs in this batch (with doc cap)."""
    parts: List[str] = []
    for i, doc in enumerate(batch_docs, 1):
        content = (doc.get("content") or "")[:EVIDENCE_DOC_CHAR_CAP]
        parts.append(f"### DOCUMENT {i}: {doc.get('filename', 'unknown')}\n{content}")
    return (
        f"## DOCUMENTS TO ANALYSE ({len(batch_docs)} files)\n\n"
        + "\n\n".join(parts)
        + "\n\n---\n\nAnalyse all documents following the instructions. "
          "Produce a complete YAML output with meta block and one card per document."
    )


def _call_llm_for_batch(
    azure_client,
    system_prompt: str,
    batch_docs: List[Dict[str, Any]],
    batch_idx: int,
    total_batches: int,
) -> Optional[str]:
    """
    Call Azure on a single batch with retry/backoff for 429.
    Returns raw YAML on success, None on irrecoverable failure (caller emits
    synthetic cards). Falls back to Gemini on Azure exhaustion.
    """
    user_prompt = _build_user_prompt_for_batch(batch_docs)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Try Azure with local retry/backoff for transient errors.
    if azure_client is not None:
        for attempt in range(EVIDENCE_MAX_RETRIES):
            try:
                stream = azure_client.chat_stream(
                    messages=messages,
                    max_tokens=EVIDENCE_MAX_OUTPUT_TOKENS,
                )
                chunks: List[str] = []
                for chunk in stream:
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", None) if delta else None
                    if content:
                        chunks.append(content)
                raw = "".join(chunks)
                if raw.strip():
                    return raw
                _log.warning(
                    "[Phase 2] Batch %d/%d Azure returned empty (attempt %d) — retrying",
                    batch_idx + 1, total_batches, attempt + 1,
                )
            except Exception as e:
                msg = str(e).lower()
                is_transient = (
                    "rate limit" in msg or "rate_limit" in msg
                    or "429" in msg or "timeout" in msg
                    or "connection" in msg
                )
                _log.warning(
                    "[Phase 2] Batch %d/%d Azure attempt %d failed (%s): %s",
                    batch_idx + 1, total_batches, attempt + 1,
                    "transient" if is_transient else "fatal",
                    str(e)[:200],
                )
                if not is_transient:
                    break  # non-retryable → fall through to Gemini
            # Backoff before next attempt
            if attempt < EVIDENCE_MAX_RETRIES - 1:
                wait = min(
                    EVIDENCE_RETRY_BASE_DELAY * (2 ** attempt),
                    EVIDENCE_RETRY_MAX_DELAY,
                )
                time.sleep(wait)

    # Azure exhausted or unavailable → try Gemini fallback per batch.
    try:
        from compliance.gap_analyzer import _call_llm_gemini
        raw = _call_llm_gemini(messages)
        if raw and raw.strip():
            return raw
    except Exception as e:
        _log.warning(
            "[Phase 2] Batch %d/%d Gemini fallback failed: %s",
            batch_idx + 1, total_batches, e,
        )

    return None


def _synthetic_yaml_for_batch(batch_docs: List[Dict[str, Any]]) -> str:
    """
    Emit fallback YAML cards when an entire batch fails so we don't lose the
    documents from the analysis: each card has readable=false and a clear
    failure note. evidence_id is a placeholder; it will be renumbered globally.
    """
    parts: List[str] = []
    for i, doc in enumerate(batch_docs, 1):
        fname = (doc.get("filename") or "unknown").replace('"', "'")
        parts.append(
            f"# ── DOC {i} ──\n"
            f'evidence_id: "ev_999_failed"\n'
            f'file_name: "{fname}"\n'
            f"readable: false\n"
            f'language: "und"\n'
            f'doc_type: "other"\n'
            f"doc_date: null\n"
            f"page_count: null\n"
            f'iso_clause_primary: ""\n'
            f"iso_clauses_secondary: []\n"
            f"gap_signal: false\n"
            f"summary: |\n"
            f"  Evidence extraction failed for this document. "
            f"It was readable from the archive but the analysis could not complete.\n"
            f"excerpts: []\n"
            f"gap_detail: |\n"
            f"  Document not analysed. Re-run the analysis to retry.\n"
            f"confidence: 0.0\n"
        )
    return "\n".join(parts)


_DOC_MARKER_RE = re.compile(r"#\s*──\s*DOC\s*\d+\s*──")
_EVIDENCE_ID_RE = re.compile(r'evidence_id:\s*"?ev_\d+(_[A-Za-z0-9_]*)?"?')


def _strip_meta_block(raw_yaml: str) -> str:
    """
    Remove the leading `---\\nmeta: …` block and any preamble before the first
    `# ── DOC N ──` marker. Each batch returns its own meta header and we don't
    want them concatenated into the merged stream (the fallback parser splits
    on DOC markers and any meta block falling between two markers would break
    YAML parsing of the previous card).

    If no DOC marker is found the raw text is returned unchanged.
    """
    if not raw_yaml:
        return raw_yaml
    m = _DOC_MARKER_RE.search(raw_yaml)
    if not m:
        return raw_yaml
    return raw_yaml[m.start():]


def _renumber_doc_markers(text: str) -> str:
    """Replace each `# ── DOC N ──` with progressive global numbering."""
    counter = [0]
    def repl(_m):
        counter[0] += 1
        return f"# ── DOC {counter[0]} ──"
    return _DOC_MARKER_RE.sub(repl, text)


def _renumber_evidence_ids(text: str) -> str:
    """Replace each `evidence_id: ev_NNN[_xxx]` with progressive numbering.

    Preserves the optional `_slug` suffix produced by the LLM. Always quotes
    the value in the output for parser safety.
    """
    counter = [0]
    def repl(m):
        counter[0] += 1
        suffix = m.group(1) or ""
        return f'evidence_id: "ev_{counter[0]:03d}{suffix}"'
    return _EVIDENCE_ID_RE.sub(repl, text)


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_compliance_pipeline(
    zip_bytes: bytes,
    company_context: CompanyContext,
    emitter: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Full four-phase compliance pipeline.

    Args:
        zip_bytes:       Raw bytes of the uploaded ZIP archive.
        company_context: Validated CompanyContext from wizard Step 0.
        emitter:         Optional callable(pct, msg) for SSE streaming.

    Returns:
        dict with keys: success, analysis_id, result (ComplianceAnalysisResult as dict), error
    """
    def emit(pct: float, msg: str) -> None:
        if emitter:
            try:
                emitter(pct, msg)
            except Exception:
                pass

    start = time.monotonic()

    try:
        # ── Phase 1: Extract documents from ZIP ──────────────────────────────
        docs = _extract_documents(zip_bytes, emit)
        if not docs:
            emit(100.0, "No readable documents found in archive.")
            return {"success": False, "error": "no_documents", "analysis_id": None, "result": None}

        # ── Phase 2: Evidence extraction (LLM) ───────────────────────────────
        evidence_yaml = _extract_evidence(docs, company_context, emit)

        # ── Phase 2.5: Expiry check (deterministic, Python-only) ─────────────
        from compliance.expiry_check import run_expiry_check
        from compliance.schemas import ExpiryReport
        from datetime import datetime as _dt
        expiry_dict = run_expiry_check(
            evidence_yaml=evidence_yaml,
            audit_date=_dt.utcnow().date(),
            emitter=emit,
        )

        # ── Phase 3: Gap analysis (ChromaDB + LLM per clause) ────────────────
        result: ComplianceAnalysisResult = analyze_compliance(
            evidence_yaml=evidence_yaml,
            company_context=company_context,
            emitter=lambda pct, msg: emit(35.0 + pct * 0.55, msg),
        )

        # Attach Phase 2.5 output to the final result
        try:
            result.expiry_report = ExpiryReport(**expiry_dict)
        except Exception as e:
            # Schema validation failure shouldn't kill the analysis — log and skip
            import logging as _log
            _log.getLogger("compliance.pipeline").warning(
                f"ExpiryReport schema validation failed: {e!s} — continuing without it"
            )

        elapsed = round(time.monotonic() - start, 1)
        emit(100.0, f"Pipeline complete in {elapsed}s.")

        return {
            "success":     True,
            "analysis_id": result.analysis_id,
            "result":      result,
            "error":       None,
        }

    except Exception as e:
        emit(100.0, f"Pipeline error: {e}")
        return {
            "success":     False,
            "analysis_id": None,
            "result":      None,
            "error":       str(e),
        }
