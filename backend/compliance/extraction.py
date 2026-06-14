"""
Amisys QHSE — Document text extraction (Phase 1, reusable).

Estratto da `pipeline.py` (Fase B consolidamento) per essere riusabile sia
dalla pipeline ZIP sia dal DMS (upload per-documento). NON importa
`pipeline` né `gap_analyzer` → l'upload DMS non trascina ChromaDB.

API pubblica:
    extract_document(filename, raw) -> str   # dispatch per estensione
    _repair_zip_name(raw_name) -> str        # ripara nomi cp437/NFD dei ZIP

Formato output:
    PDF  → "[PAGE n]\\n<text>" per pagina (citazioni reali, OCR per-pagina sui misti)
    XLSX → '[SHEET "name"]\\n<rows pipe-separated>'
    DOCX → paragrafi + tabelle (pipe-separated)
"""
from __future__ import annotations

import io
import logging
import unicodedata
import zipfile
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

_log = logging.getLogger("compliance.extraction")


def _repair_zip_name(raw_name: str) -> str:
    """Sprint G.2 (rivisto): ripara nomi file ZIP letti con cp437 quando il
    contenuto vero era UTF-8.

    Casi gestiti:
    1. Nome già pulito (ASCII o UTF-8 valido) → ritornato as-is con NFC normalize.
    2. Nome corrotto (cp437 misread di bytes UTF-8): re-encode cp437 + decode
       utf-8. Se riesce e produce solo caratteri NFC validi senza combining
       residui, usiamo il risultato; altrimenti fallback al nome originale.

    Esempio (CTM 45001.zip):
        raw: "Idonieta╠Ç BRUNO.pdf"   (cp437 di b'\\xc3\\xa0')
        out: "Idonietà BRUNO.pdf"     (NFC riparato)

    Sempre normalizzato in NFC alla fine (gestisce anche il caso macOS NFD
    "a + U+0300" come precauzione aggiuntiva).
    """
    # Heuristic: i caratteri "spazzatura" tipici di cp437-misread di bytes
    # UTF-8 multibyte. Se troviamo uno di questi indizi, tentiamo il round-trip.
    suspicious_chars = set("╠╣╔═╗╚╝┌┐└┘├┤┬┴┼")
    has_suspicious = any(ch in suspicious_chars for ch in raw_name)

    if has_suspicious:
        try:
            repaired = raw_name.encode("cp437").decode("utf-8")
            # Verifichiamo che il risultato sia "ragionevole": nessun byte non stampabile
            if all(ord(ch) >= 32 or ch in "\t\n" for ch in repaired):
                return unicodedata.normalize("NFC", repaired)
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    # Default path: normalize NFC (gestisce anche NFD da macOS)
    return unicodedata.normalize("NFC", raw_name)


# ──────────────────────────────────────────────────────────────────────────────
# ZIP walking — ricorsivo sugli ZIP annidati, esclude SOLO il junk macOS
# ──────────────────────────────────────────────────────────────────────────────

# Tetto di sicurezza contro zip-bomb / nesting patologico.
_ZIP_MAX_DEPTH = 24
_ZIP_MAX_FILES = 5000


def _is_zip_junk(name: str) -> bool:
    """True per gli artefatti macOS che NON sono documenti reali:
    cartella `__MACOSX/`, file AppleDouble `._*`, `.DS_Store`. Tutto il resto
    (inclusi gli ZIP annidati) è contenuto valido."""
    base = name.rsplit("/", 1)[-1]
    return (
        "__MACOSX" in name.split("/")
        or base.startswith("._")
        or base == ".DS_Store"
        or base == ""
    )


def iter_zip_files(
    zip_bytes: bytes,
    *,
    _depth: int = 0,
    _prefix: str = "",
    on_warn: Optional[Callable[[str], None]] = None,
) -> Iterator[Tuple[str, bytes]]:
    """Cammina un archivio ZIP e produce `(percorso, bytes)` per OGNI file reale,
    **ricorrendo dentro gli ZIP annidati** a qualsiasi profondità (fino a
    `_ZIP_MAX_DEPTH`). Esclude solo il junk macOS (`__MACOSX/`, `._*`, `.DS_Store`).

    Il percorso restituito è il path interno completo (con prefisso dello zip
    annidato), così i nomi restano significativi e unici.
    """
    if _depth > _ZIP_MAX_DEPTH:
        if on_warn:
            on_warn(f"max ZIP nesting depth {_ZIP_MAX_DEPTH} superata a {_prefix}")
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as e:
        if on_warn:
            on_warn(f"non è un ZIP valido ({_prefix or 'root'}): {e}")
        return

    emitted = 0
    with zf:
        for raw_name in zf.namelist():
            if raw_name.endswith("/") or _is_zip_junk(raw_name):
                continue
            display = _repair_zip_name(raw_name)
            try:
                data = zf.read(raw_name)
            except Exception as e:
                if on_warn:
                    on_warn(f"illeggibile {display}: {e}")
                continue
            if raw_name.lower().endswith(".zip"):
                # ZIP annidato → ricorsione (i bytes sono già in memoria)
                yield from iter_zip_files(
                    data, _depth=_depth + 1, _prefix=f"{_prefix}{display}/",
                    on_warn=on_warn,
                )
            else:
                yield (f"{_prefix}{display}", data)
                emitted += 1
                if emitted > _ZIP_MAX_FILES:
                    if on_warn:
                        on_warn(f"oltre {_ZIP_MAX_FILES} file in {_prefix or 'root'} — troncato")
                    return


# Sprint R1 — a page is considered "scanned" (no usable native text) when its
# native extraction yields fewer than this many non-whitespace characters.
# 25 chars tolerates page numbers / headers on image-only pages while still
# catching genuinely scanned pages.
_PDF_PAGE_MIN_NATIVE_CHARS = 25


def extract_document(filename: str, raw: bytes) -> str:
    """Best-effort text extraction with page/sheet markers (Sprint R1).

    PDF output carries `[PAGE n]` markers so downstream page citations are
    real, not LLM-estimated. Spreadsheets carry `[SHEET "name"]` markers.
    """
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md", ".csv"):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    if ext == ".pdf":
        return _extract_pdf_text(raw, filename)

    if ext in (".xlsx", ".xlsm", ".xls"):
        return _extract_spreadsheet_text(raw, ext)

    if ext in (".docx", ".doc"):
        try:
            import io, docx  # type: ignore
            doc = docx.Document(io.BytesIO(raw))
            parts = [p.text for p in doc.paragraphs]
            # Sprint R1: DOCX tables were silently skipped before — registers,
            # objectives and MR minutes often live in tables.
            for table in doc.tables:
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            return "\n".join(parts)
        except Exception:
            return ""

    return ""


def _extract_pdf_text(raw: bytes, filename: str) -> str:
    """
    Sprint R1 — page-aware PDF extraction with per-page OCR cascade:

      1. pypdfium2 per page → native text with real page numbers.
      2. Pages below _PDF_PAGE_MIN_NATIVE_CHARS native chars → Azure DI OCR,
         only for those pages (fixes the mixed native+scanned bug where a
         native cover page suppressed OCR for the entire document).
      3. pypdfium2 unavailable/broken → pdfminer whole-document (no markers).
      4. Still nothing → whole-document OCR (fully scanned PDF).

    Output format: "[PAGE 1]\\n<text>\\n\\n[PAGE 2]\\n<text>…"
    """
    import io

    page_texts: Dict[int, str] = {}   # 1-based page number → text
    page_count = 0

    try:
        import pypdfium2 as pdfium  # type: ignore
        pdf = pdfium.PdfDocument(io.BytesIO(raw))
        try:
            page_count = len(pdf)
            for i in range(page_count):
                page = pdf[i]
                try:
                    textpage = page.get_textpage()
                    try:
                        text = textpage.get_text_bounded() or ""
                    finally:
                        textpage.close()
                finally:
                    page.close()
                page_texts[i + 1] = text
        finally:
            pdf.close()
    except Exception as e:
        _log.debug("[Phase 1] pypdfium2 failed on %s: %s", filename, e)
        page_texts = {}
        page_count = 0

    if page_texts:
        # Identify scanned pages (no usable native text) and OCR only those.
        scanned_pages = [
            n for n, t in page_texts.items()
            if len("".join(t.split())) < _PDF_PAGE_MIN_NATIVE_CHARS
        ]
        if scanned_pages:
            from compliance.azure_ocr import ocr_pdf_pages
            ocr_results = ocr_pdf_pages(raw, scanned_pages, filename=filename)
            if ocr_results:
                _log.info(
                    "[Phase 1] %s: OCR recovered %d/%d scanned page(s)",
                    filename, len(ocr_results), len(scanned_pages),
                )
            for n, t in ocr_results.items():
                page_texts[n] = t

        combined = "\n\n".join(
            f"[PAGE {n}]\n{page_texts[n].strip()}"
            for n in sorted(page_texts)
            if page_texts[n].strip()
        )
        if combined.strip():
            return combined

    # Fallback: pdfminer whole-document (no page markers, legacy behaviour)
    text = ""
    try:
        import pdfminer.high_level as pdfminer  # type: ignore
        text = pdfminer.extract_text(io.BytesIO(raw)) or ""
    except Exception:
        pass

    # Last resort: the whole PDF is scanned → full-document OCR
    if not text.strip():
        from compliance.azure_ocr import ocr_pdf_bytes
        text = ocr_pdf_bytes(raw, filename=filename)

    return text


def _extract_spreadsheet_text(raw: bytes, ext: str) -> str:
    """
    Sprint R1 — spreadsheet extraction (P7: objectives often live in Excel).

    Renders every sheet as pipe-separated rows under a `[SHEET "name"]`
    marker, so the LLM sees tabular content (objectives, targets, KPI
    registers) regardless of how the file is named.
    """
    import io

    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(
                io.BytesIO(raw), data_only=True, read_only=True,
            )
            parts: List[str] = []
            for ws in wb.worksheets:
                rows: List[str] = []
                for row in ws.iter_rows(values_only=True):
                    cells = [
                        str(c).strip() for c in row
                        if c is not None and str(c).strip()
                    ]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    parts.append(f'[SHEET "{ws.title}"]\n' + "\n".join(rows))
            wb.close()
            return "\n\n".join(parts)
        except Exception as e:
            _log.warning("[Phase 1] xlsx extraction failed: %s", e)
            return ""

    # Legacy .xls via xlrd
    try:
        import xlrd  # type: ignore
        wb = xlrd.open_workbook(file_contents=raw)
        parts = []
        for ws in wb.sheets():
            rows = []
            for rx in range(ws.nrows):
                cells = [
                    str(c.value).strip() for c in ws.row(rx)
                    if str(c.value).strip()
                ]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                parts.append(f'[SHEET "{ws.name}"]\n' + "\n".join(rows))
        return "\n\n".join(parts)
    except Exception as e:
        _log.warning("[Phase 1] xls extraction failed: %s", e)
        return ""
