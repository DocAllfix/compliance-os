"""
ComplianceOS — Compliance Pipeline Orchestrator.

Four-phase pipeline:
    Phase 1: ZIP extraction → text extraction per document
    Phase 2: Evidence extraction (LLM) → YAML evidence cards
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

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from compliance.gap_analyzer import analyze_compliance
from compliance.schemas import CompanyContext, ComplianceAnalysisResult


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
        try:
            from v2.text_extractor import extract_text_from_pdf_bytes
            return extract_text_from_pdf_bytes(raw, filename=filename)
        except ImportError:
            try:
                import io
                import pdfminer.high_level as pdfminer  # type: ignore
                return pdfminer.extract_text(io.BytesIO(raw)) or ""
            except Exception:
                return ""

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

def _extract_evidence(
    docs: List[Dict[str, Any]],
    company_context: CompanyContext,
    emit: Callable,
) -> str:
    """
    Run Phase 1 LLM call: documents → YAML evidence cards.
    Returns raw YAML string.
    """
    from pathlib import Path as P
    from compliance.context_intake import build_context_prompt_block

    prompt_path = P(__file__).resolve().parent.parent / "prompts" / "compliance" / "evidence_extraction_prompt.md"
    try:
        prompt_template = prompt_path.read_text(encoding="utf-8")
    except Exception:
        prompt_template = "Extract evidence cards from the following documents as YAML."

    context_block = build_context_prompt_block(company_context)
    system_prompt = prompt_template.replace("{company_context}", context_block)

    # Build user message with all documents
    doc_parts = []
    for i, doc in enumerate(docs, 1):
        cap = 15_000
        content = doc.get("content", "")[:cap]
        doc_parts.append(f"### DOCUMENT {i}: {doc['filename']}\n{content}")

    user_prompt = (
        f"## DOCUMENTS TO ANALYSE ({len(docs)} files)\n\n"
        + "\n\n".join(doc_parts)
        + "\n\n---\n\nAnalyse all documents following the instructions. "
          "Produce a complete YAML output with meta block and one card per document."
    )

    emit(20.0, f"Running evidence extraction on {len(docs)} documents…")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    # Use the same LLM call pattern as gap_analyzer
    from compliance.gap_analyzer import _call_llm
    raw = _call_llm(messages)
    emit(35.0, "Evidence extraction complete. Indexing…")
    return raw


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

        # ── Phase 3: Gap analysis (ChromaDB + LLM per clause) ────────────────
        result: ComplianceAnalysisResult = analyze_compliance(
            evidence_yaml=evidence_yaml,
            company_context=company_context,
            emitter=lambda pct, msg: emit(35.0 + pct * 0.55, msg),
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
