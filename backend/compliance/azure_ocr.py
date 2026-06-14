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

import logging
import os
from typing import Dict, List, Optional

_log = logging.getLogger("compliance.azure_ocr")


def _get_di_client():
    """Build a DocumentIntelligenceClient, or None when not configured.

    Logga il MOTIVO quando ritorna None (chiave assente o SDK mancante): prima
    falliva in silenzio e l'OCR risultava muto senza alcun segnale — gli ZIP
    di soli PDF scansionati uscivano vuoti."""
    endpoint = os.environ.get("AZURE_DI_ENDPOINT", "").strip()
    key = os.environ.get("AZURE_DI_KEY", "").strip()

    if not endpoint or not key or key in ("YOUR_DI_KEY_HERE", "placeholder"):
        _log.warning("[OCR] Azure DI non configurato (endpoint/key mancanti) — i PDF scansionati usciranno vuoti")
        return None

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        return DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )
    except ImportError as e:
        _log.error("[OCR] SDK azure-ai-documentintelligence non installato (%s) — "
                   "`pip install azure-ai-documentintelligence`. OCR disattivato.", e)
        return None
    except Exception as e:
        _log.error("[OCR] impossibile creare il client Azure DI: %s", e)
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

    except Exception as e:
        _log.warning("[OCR] full-doc OCR fallito per %s: %s", filename or "?", str(e)[:200])
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

    except Exception as e:
        _log.warning("[OCR] per-page OCR fallito per %s: %s", filename or "?", str(e)[:200])
        return {}
