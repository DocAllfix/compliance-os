"""
Amisys QHSE — Azure Document Intelligence OCR.

Called by pipeline._read_file_content for scanned PDFs. Two entry points:

  - ocr_pdf_bytes(raw)            → whole-document OCR (legacy path, kept for
                                    fully scanned PDFs and as a fallback)
  - ocr_pdf_pages(raw, [2, 5, 6]) → Sprint R1: per-page OCR for MIXED PDFs
                                    (native cover + scanned body). Only the
                                    pages with no native text are sent to DI,
                                    keeping cost bounded and fixing the bug
                                    where a native cover page suppressed OCR
                                    for the whole document.

Falls back silently (empty results) if the SDK or keys are missing.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional


def _get_di_client():
    """Build a DocumentIntelligenceClient, or None when not configured."""
    endpoint = os.environ.get("AZURE_DI_ENDPOINT", "").strip()
    key = os.environ.get("AZURE_DI_KEY", "").strip()

    if not endpoint or not key or key in ("YOUR_DI_KEY_HERE", "placeholder"):
        return None

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        return DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )
    except Exception:
        return None


def ocr_pdf_bytes(raw: bytes, filename: str = "") -> str:
    """
    Run Azure Document Intelligence prebuilt-read on raw PDF bytes.
    Returns extracted text, or empty string on any failure.
    """
    client = _get_di_client()
    if client is None:
        return ""

    try:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        body = AnalyzeDocumentRequest(bytes_source=raw)
        poller = client.begin_analyze_document("prebuilt-read", body=body)
        result = poller.result()
        return result.content or ""

    except Exception:
        return ""


def ocr_pdf_pages(raw: bytes, page_numbers: List[int], filename: str = "") -> Dict[int, str]:
    """
    Sprint R1 — OCR only the given pages (1-based) of a PDF.

    Returns {page_number: text} for the pages DI could read. Empty dict on
    any failure (caller decides whether to retry whole-document OCR).
    """
    if not page_numbers:
        return {}

    client = _get_di_client()
    if client is None:
        return {}

    try:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        pages_param = ",".join(str(p) for p in sorted(set(page_numbers)))
        body = AnalyzeDocumentRequest(bytes_source=raw)
        poller = client.begin_analyze_document(
            "prebuilt-read", body=body, pages=pages_param,
        )
        result = poller.result()

        out: Dict[int, str] = {}
        for page in (result.pages or []):
            page_no = getattr(page, "page_number", None)
            if page_no is None:
                continue
            lines = getattr(page, "lines", None) or []
            text = "\n".join(
                getattr(line, "content", "") for line in lines
            ).strip()
            if text:
                out[int(page_no)] = text
        return out

    except Exception:
        return {}
