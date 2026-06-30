"""
Amisys QHSE — Azure Document Intelligence OCR.

Called by pipeline._read_file_content for scanned PDFs and images. Entry points:

  - ocr_pdf_bytes(raw)            → whole-document OCR (legacy path, kept for
                                    fully scanned PDFs and as a fallback)
  - ocr_pdf_pages(raw, [2, 5, 6]) → Sprint R1: per-page OCR for MIXED PDFs
                                    (native cover + scanned body). Only the
                                    pages with no native text are sent to DI,
                                    keeping cost bounded.
  - ocr_image_bytes(raw)          → OCR of an image (jpg/png/tiff/…) via the
                                    same prebuilt-read model.

Resilienza (hardening 2026 — parallelizzazione Fase 1): le chiamate OCR ora
girano in parallelo (un worker per documento). Per evitare che un 429/timeout
transitorio faccia SPARIRE in silenzio il testo di un documento, ogni chiamata
ha retry con backoff esponenziale sui SOLI errori transitori; gli errori non
recuperabili tornano vuoto (comportamento storico). Il client Azure DI è un
singleton riusato da tutti i worker (thread-safe per richieste concorrenti).

Falls back silently (empty result) if the SDK or keys are missing.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, List, Optional

_log = logging.getLogger("compliance.azure_ocr")

# Retry sui SOLI errori transitori (429/throttling/timeout/5xx). 3 tentativi,
# backoff 2 → 4 → (cap 8) secondi. Gli errori fatali (auth, payload) non si
# ritentano: tornano vuoto come prima.
_OCR_MAX_RETRIES = 3
_OCR_RETRY_BASE_DELAY = 2.0
_OCR_RETRY_MAX_DELAY = 8.0

# Singleton client riusato da tutti i thread (costruirne uno per chiamata era
# spreco; il client SDK è sicuro per richieste concorrenti).
_client_singleton = None
_client_lock = threading.Lock()


def _get_di_client():
    """Return a cached DocumentIntelligenceClient, or None when not configured.

    Logga il MOTIVO quando ritorna None (chiave assente o SDK mancante): prima
    falliva in silenzio e l'OCR risultava muto senza alcun segnale."""
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton

    endpoint = os.environ.get("AZURE_DI_ENDPOINT", "").strip()
    key = os.environ.get("AZURE_DI_KEY", "").strip()

    if not endpoint or not key or key in ("YOUR_DI_KEY_HERE", "placeholder"):
        _log.warning("[OCR] Azure DI non configurato (endpoint/key mancanti) — i PDF scansionati usciranno vuoti")
        return None

    with _client_lock:
        if _client_singleton is not None:
            return _client_singleton
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential

            _client_singleton = DocumentIntelligenceClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(key),
            )
            return _client_singleton
        except ImportError as e:
            _log.error("[OCR] SDK azure-ai-documentintelligence non installato (%s) — "
                       "`pip install azure-ai-documentintelligence`. OCR disattivato.", e)
            return None
        except Exception as e:
            _log.error("[OCR] impossibile creare il client Azure DI: %s", e)
            return None


def _is_transient_ocr_error(e: Exception) -> bool:
    """True per errori che vale la pena ritentare (throttling/timeout/5xx)."""
    status = getattr(e, "status_code", None)
    if status in (408, 429, 500, 502, 503, 504):
        return True
    msg = str(e).lower()
    return any(
        s in msg
        for s in (
            "429", "rate limit", "rate_limit", "too many requests",
            "timeout", "timed out", "temporarily", "throttl",
            "connection", "503", "service unavailable",
        )
    )


def _run_with_retry(fn, what: str):
    """Esegue `fn()` con retry/backoff sui soli errori transitori.

    Ritorna il risultato di `fn()`, oppure None se: errore non-transitiero, o
    retry esauriti. Non solleva mai (il chiamante traduce None in stringa/dict
    vuoto, preservando il comportamento storico)."""
    for attempt in range(_OCR_MAX_RETRIES):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — l'OCR non deve mai propagare
            transient = _is_transient_ocr_error(e)
            if not transient or attempt == _OCR_MAX_RETRIES - 1:
                _log.warning("[OCR] %s fallito (%s): %s",
                             what, "transient-esaurito" if transient else "fatale",
                             str(e)[:200])
                return None
            wait = min(_OCR_RETRY_BASE_DELAY * (2 ** attempt), _OCR_RETRY_MAX_DELAY)
            _log.warning("[OCR] %s transient (tentativo %d/%d) — retry in %.1fs: %s",
                         what, attempt + 1, _OCR_MAX_RETRIES, wait, str(e)[:160])
            time.sleep(wait)
    return None


def ocr_pdf_bytes(raw: bytes, filename: str = "") -> str:
    """
    Run Azure Document Intelligence prebuilt-read on raw PDF bytes.
    Returns extracted text, or empty string on any failure (con retry sui
    transitori).
    """
    client = _get_di_client()
    if client is None:
        return ""

    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    def _do():
        body = AnalyzeDocumentRequest(bytes_source=raw)
        poller = client.begin_analyze_document("prebuilt-read", body=body)
        return poller.result()

    result = _run_with_retry(_do, f"full-doc OCR {filename or '?'}")
    return (result.content or "") if result is not None else ""


def ocr_pdf_pages(raw: bytes, page_numbers: List[int], filename: str = "") -> Dict[int, str]:
    """
    Sprint R1 — OCR only the given pages (1-based) of a PDF.

    Returns {page_number: text} for the pages DI could read. Empty dict on
    any failure (con retry sui transitori; il chiamante decide se ritentare
    whole-document).
    """
    if not page_numbers:
        return {}

    client = _get_di_client()
    if client is None:
        return {}

    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    pages_param = ",".join(str(p) for p in sorted(set(page_numbers)))

    def _do():
        body = AnalyzeDocumentRequest(bytes_source=raw)
        poller = client.begin_analyze_document(
            "prebuilt-read", body=body, pages=pages_param,
        )
        return poller.result()

    result = _run_with_retry(_do, f"per-page OCR {filename or '?'}")
    if result is None:
        return {}

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


def ocr_image_bytes(raw: bytes, filename: str = "") -> str:
    """
    OCR di un'immagine (jpg/jpeg/png/tif/tiff/bmp/heic) via prebuilt-read.
    Azure DI accetta le immagini come `bytes_source` esattamente come i PDF.
    Returns extracted text, or empty string on any failure.
    """
    client = _get_di_client()
    if client is None:
        return ""

    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

    def _do():
        body = AnalyzeDocumentRequest(bytes_source=raw)
        poller = client.begin_analyze_document("prebuilt-read", body=body)
        return poller.result()

    result = _run_with_retry(_do, f"image OCR {filename or '?'}")
    return (result.content or "") if result is not None else ""
