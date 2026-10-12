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
import threading
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

_log = logging.getLogger("compliance.extraction")

# pypdfium2/PDFium NON è thread-safe (lo dichiara la doc upstream). Con la Fase 1
# parallela più worker chiamavano pdfium concorrentemente → Segmentation fault
# (munmap_chunk: invalid pointer). Questo lock serializza TUTTI gli accessi a
# pypdfium; il parsing nativo è veloce, mentre l'OCR di rete resta FUORI dal lock
# (concorrente) → lo speed-up è preservato.
_PDFIUM_LOCK = threading.Lock()


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

# Hardening 2026 #3 — quality gate. Some PDFs carry a broken/custom font encoding:
# pypdfium2 returns plenty of NON-whitespace characters, but they are control/glyph
# codes (\x02\x03…), not real text. The old "scanned = few non-ws chars" test saw a
# "full" page and suppressed OCR (observed: CO.ENERGIE visura, 19.7k chars of garbage
# → readable:false card → §4.1 starved). We now also treat a page/document as needing
# OCR when the ratio of *printable* characters is too low.
_PDF_MIN_QUALITY_RATIO = 0.60   # printable / non-whitespace below this → garbage
_PDF_QUALITY_MIN_CHARS = 40     # need a little text before judging by ratio


def _is_low_quality_text(text: str) -> bool:
    """True when `text` looks like font-encoding garbage rather than real text.

    Signal = RATIO of printable characters among non-whitespace (Hardening 2026 #3).
    The ratio distinguishes garbage (control-char glyphs, ratio ~0) from real text
    (ratio ~1) at ANY length, so a low `_PDF_QUALITY_MIN_CHARS` (40) catches the SHORT
    garbage pages (osservato: pagine oltre la 2 della visura CO.ENERGIE) WITHOUT
    false-positiving large clean documents that carry a few stray control chars
    (es. il DVR Serapide: 187k char, 42 control char, ratio 1.0 → NON garbage).
    An absolute control-char count was tried and rejected: it flags big clean docs.
    Conservative on legitimate text: str.isprintable() keeps accented Latin readable.
    """
    import re
    t = re.sub(r"\[PAGE\s+\d+\]", "", text or "")
    nonspace = [c for c in t if not c.isspace()]
    if len(nonspace) < _PDF_QUALITY_MIN_CHARS:
        return False
    readable = sum(1 for c in nonspace if c.isprintable())
    return (readable / len(nonspace)) < _PDF_MIN_QUALITY_RATIO


# Estensioni testuali semplici (decode diretto) e immagini (→ OCR Azure DI).
_TEXT_EXTS = (".txt", ".md", ".csv", ".log", ".tsv")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".heic", ".heif")


def extract_document(filename: str, raw: bytes) -> str:
    """Best-effort text extraction with page/sheet markers (Sprint R1).

    PDF output carries `[PAGE n]` markers so downstream page citations are
    real, not LLM-estimated. Spreadsheets carry `[SHEET "name"]` markers.

    Coverage estesa (Fase A): oltre a pdf/docx/xlsx/txt, gestisce doc legacy,
    rtf, pptx, odt/ods, html/xml, eml/msg, p7m e immagini (via OCR). Ogni
    handler è ADDITIVO e non solleva mai: i formati storici restano INVARIATI.
    """
    ext = Path(filename).suffix.lower()

    # ── Formati storici (INVARIATI) ──────────────────────────────────────────
    if ext in _TEXT_EXTS:
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    if ext == ".pdf":
        return _extract_pdf_text(raw, filename)

    if ext in (".xlsx", ".xlsm", ".xls"):
        return _extract_spreadsheet_text(raw, ext)

    if ext == ".docx":
        return _extract_docx_bytes(raw)

    # ── Coverage estesa (Fase A) — handler bytes-based, mai solleva ──────────
    if ext == ".doc":
        return _extract_doc_legacy(raw)
    if ext == ".rtf":
        return _extract_rtf(raw)
    if ext == ".pptx":
        return _extract_pptx(raw)
    if ext == ".odt":
        return _extract_odt(raw)
    if ext == ".ods":
        return _extract_ods(raw)
    if ext in (".html", ".htm"):
        return _extract_html(raw)
    if ext == ".xml":
        return _extract_xml(raw)
    if ext == ".eml":
        return _extract_eml(raw)
    if ext == ".msg":
        return _extract_msg(raw)
    if ext == ".p7m":
        return _extract_p7m(raw, filename)
    if ext in _IMAGE_EXTS:
        try:
            from compliance.azure_ocr import ocr_image_bytes
            return ocr_image_bytes(raw, filename=filename)
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
        # Serializza il parsing nativo pypdfium (non thread-safe). L'OCR di rete
        # più sotto resta fuori dal lock → concorrente fra i worker.
        with _PDFIUM_LOCK:
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
        # Identify pages needing OCR: either too little native text (scanned) OR
        # native text that is mostly non-printable garbage (broken font encoding,
        # Hardening 2026 #3) — both go to Azure DI for those pages only.
        scanned_pages = [
            n for n, t in page_texts.items()
            if len("".join(t.split())) < _PDF_PAGE_MIN_NATIVE_CHARS
            or _is_low_quality_text(t)
        ]
        if scanned_pages:
            from compliance.azure_ocr import ocr_pdf_pages
            ocr_results = ocr_pdf_pages(raw, scanned_pages, filename=filename)
            if ocr_results:
                _log.info(
                    "[Phase 1] %s: OCR recovered %d/%d low-text/garbage page(s)",
                    filename, len(ocr_results), len(scanned_pages),
                )
            for n, t in ocr_results.items():
                page_texts[n] = t

        combined = "\n\n".join(
            f"[PAGE {n}]\n{page_texts[n].strip()}"
            for n in sorted(page_texts)
            if page_texts[n].strip()
        )
        # Document-level backstop: if the combined native+per-page-OCR text is still
        # mostly garbage (per-page OCR didn't rescue it), fall through to full-document
        # OCR rather than returning unreadable glyph codes downstream.
        if combined.strip() and not _is_low_quality_text(combined):
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


# ── Piano motore Fase 1 — fogli di calcolo senza perdite (READ_SHEET_CELLS) ──
# Il rendering storico scartava le celle vuote: le colonne "scivolavano" (il
# valore della colonna 5 finiva sotto l'intestazione della 4) e una colonna
# obbligatoria vuota — es. il formatore non indicato — spariva senza traccia.
# Qui ogni riga dati porta i valori con la propria intestazione e le celle
# vuote restano visibili come "(blank)". Fogli enormi: formato compatto a
# colonne fisse, sempre con le celle vuote.

_SHEET_LABELLED_MAX_ROWS = 400
_SHEET_LABELLED_MAX_COLS = 40


def _cell_str(v: Any) -> str:
    import datetime as _dt
    if v is None:
        return ""
    if isinstance(v, _dt.datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _is_header_row(cells: List[str], raw: List[Any]) -> bool:
    filled = [(c, r) for c, r in zip(cells, raw) if c]
    if len(filled) < 2:
        return False
    import datetime as _dt
    return all(isinstance(r, str) and not isinstance(r, (_dt.date, _dt.datetime)) for _, r in filled)


def render_sheet_rows(raw_rows: List[List[Any]]) -> List[str]:
    """Rende le righe di un foglio con intestazioni e celle vuote esplicite."""
    rows = [[_cell_str(v) for v in r] for r in raw_rows]
    width = max((max((i for i, c in enumerate(r) if c), default=-1) for r in rows), default=-1) + 1
    if width <= 0:
        return []
    rows = [(r + [""] * width)[:width] for r in rows]
    raws = [(list(r) + [None] * width)[:width] for r in raw_rows]

    hi = next((i for i, (r, rr) in enumerate(zip(rows, raws)) if _is_header_row(r, rr)), None)
    if hi is None:
        return [" | ".join(r).rstrip(" |") for r in rows if any(r)]
    header = rows[hi]
    data_start = hi + 1
    # Intestazione su due righe (gruppi uniti sopra, sotto-colonne sotto): la
    # prima riga ha buchi dove la seconda ha nomi → nomi composti "Gruppo Sotto".
    # Indizio di gruppo: sotto-nomi ripetuti ("Data", "Scadenza" per ogni corso)
    # o prima colonna vuota nella riga dei gruppi; evita di fondere una riga dati.
    if data_start < len(rows) and _is_header_row(rows[data_start], raws[data_start]):
        sub = rows[data_start]
        gaps = [j for j in range(width) if not header[j] and sub[j]]
        sub_filled = [c for c in sub if c]
        grouped = len(set(sub_filled)) < len(sub_filled) or not header[0]
        if gaps and grouped and sum(1 for c in header if c) < len(sub_filled):
            group, names = "", []
            for j in range(width):
                if header[j]:
                    group = header[j]
                names.append(f"{group} {sub[j]}".strip() if sub[j] else header[j])
            header = names
            data_start += 1
    names = [h or f"Column {j + 1}" for j, h in enumerate(header)]

    out = [" | ".join(r).rstrip(" |") for r in rows[:hi] if any(r)]   # titoli sopra la tabella
    data = [(i, r) for i, r in enumerate(rows[data_start:], start=data_start + 1) if any(r)]
    if len(data) > _SHEET_LABELLED_MAX_ROWS or width > _SHEET_LABELLED_MAX_COLS:
        out.append("Columns: " + " | ".join(names))
        out += [" | ".join(c or "(blank)" for c in r) for _, r in data]
        return out
    out.append("Columns: " + " | ".join(names))
    for rownum, r in data:
        filled = [j for j, c in enumerate(r) if c]
        if len(filled) == 1 and filled[0] == 0 and width > 2:
            out.append(r[0])                        # riga-titolo di sezione
            continue
        cells = [f"{names[j]}: {r[j] or '(blank)'}" for j in range(width) if header[j] or r[j]]
        out.append(f"Row {rownum}: " + " | ".join(cells))
    return out


def _extract_spreadsheet_text(raw: bytes, ext: str) -> str:
    """
    Sprint R1 — spreadsheet extraction (P7: objectives often live in Excel).

    Renders every sheet as pipe-separated rows under a `[SHEET "name"]`
    marker, so the LLM sees tabular content (objectives, targets, KPI
    registers) regardless of how the file is named.
    """
    import io
    from compliance import features

    if features.on("READ_SHEET_CELLS"):
        return _extract_spreadsheet_labelled(raw, ext)

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


def _extract_spreadsheet_labelled(raw: bytes, ext: str) -> str:
    """Variante READ_SHEET_CELLS: stessi marcatori [SHEET], righe con intestazioni."""
    import io
    sheets: List[tuple] = []
    try:
        if ext in (".xlsx", ".xlsm"):
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
            for ws in wb.worksheets:
                sheets.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
            wb.close()
        else:
            import xlrd  # type: ignore
            wb = xlrd.open_workbook(file_contents=raw)
            for ws in wb.sheets():
                rows = []
                for rx in range(ws.nrows):
                    row = []
                    for c in ws.row(rx):
                        if c.ctype == xlrd.XL_CELL_DATE:
                            try:
                                row.append(xlrd.xldate_as_datetime(c.value, wb.datemode))
                                continue
                            except Exception:
                                pass
                        row.append(c.value if c.value != "" else None)
                    rows.append(row)
                sheets.append((ws.name, rows))
    except Exception as e:
        _log.warning("[Phase 1] spreadsheet extraction failed (%s): %s", ext, e)
        return ""
    parts = []
    for title, rows in sheets:
        lines = render_sheet_rows(rows)
        if lines:
            parts.append(f'[SHEET "{title}"]\n' + "\n".join(lines))
    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Coverage estesa (Fase A) — handler bytes-based. Mirroring AUDITORSEMI
# webapp/v2/text_handlers.py (sola lettura), adattati da path a bytes. Ogni
# handler NON solleva mai: su qualsiasi errore (libreria mancante, file
# corrotto) ritorna "" e il documento risulta semplicemente "senza testo".
# ──────────────────────────────────────────────────────────────────────────────

_DOCX_IMG_MIN_BYTES = 5_000          # sotto: icone, punti elenco, firme minuscole
_DOCX_IMG_MAX_PER_DOC = 8
_DOCX_IMG_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/tiff", "image/bmp", "image/gif")


def _extract_docx_ordered(raw: bytes) -> str:
    """Piano motore Fase 1 (READ_DOCX_IMAGES) — DOCX nell'ordine reale del corpo,
    con le immagini lette via OCR al loro posto.

    Banco Box: organigramma e mappa dei processi erano immagini dentro il
    manuale; il testo storico (paragrafi, poi tabelle) non li vedeva e il
    motore li dichiarava assenti in tutte e tre le norme. Solo il corpo del
    documento: intestazioni/piè di pagina (loghi) e miniatura di anteprima
    restano fuori.
    """
    import hashlib
    import docx  # type: ignore
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from compliance.azure_ocr import ocr_image_bytes

    doc = docx.Document(io.BytesIO(raw))
    seen: set = set()
    budget = [_DOCX_IMG_MAX_PER_DOC]

    def _images(el) -> List[str]:
        out: List[str] = []
        for rid in el.xpath(".//a:blip/@r:embed"):
            part = doc.part.related_parts.get(rid)
            if part is None or getattr(part, "content_type", "") not in _DOCX_IMG_TYPES:
                continue
            blob = part.blob
            digest = hashlib.sha1(blob).hexdigest()
            if len(blob) < _DOCX_IMG_MIN_BYTES or digest in seen or budget[0] <= 0:
                continue
            seen.add(digest)
            budget[0] -= 1
            name = str(part.partname).rsplit("/", 1)[-1]
            text = (ocr_image_bytes(blob, filename=name) or "").strip()
            out.append(f'[IMAGE "{name}"]\n{text}\n[/IMAGE]' if text
                       else f'[IMAGE "{name}" - no readable text]')
        return out

    parts: List[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            parts.append(Paragraph(child, doc).text)
            parts += _images(child)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells: List[str] = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and (not cells or cells[-1] != t):    # celle unite ripetute
                        cells.append(t)
                if cells:
                    parts.append(" | ".join(cells))
            parts += _images(child)
    return "\n".join(parts)


def _docx_header_footer_lines(raw: bytes) -> List[str]:
    """Piano motore Fase 1 (READ_DOCX_HEADERS) — testo di intestazioni e piè di
    pagina, una volta sola, in testa al documento.

    Banco Box: 23 Word su 49 portano lì codice, versione e data del documento
    ("QHSE Policy – Version 1 – 10/1/26") o il modello usato; il corpo non lo
    ripete e il motore giudicava il controllo dei documenti senza vederlo.
    Solo testo: i loghi restano fuori.
    """
    import docx  # type: ignore
    doc = docx.Document(io.BytesIO(raw))
    out: List[str] = []

    def _text(part) -> str:
        bits = [p.text.strip() for p in part.paragraphs if p.text.strip()]
        for t in part.tables:
            for row in t.rows:
                cells: List[str] = []
                for c in row.cells:
                    ct = c.text.strip()
                    if ct and (not cells or cells[-1] != ct):
                        cells.append(ct)
                if cells:
                    bits.append(" | ".join(cells))
        return " / ".join(bits)

    for s in doc.sections:
        for label, names in (("HEADER", ("first_page_header", "header", "even_page_header")),
                             ("FOOTER", ("first_page_footer", "footer", "even_page_footer"))):
            for n in names:
                try:
                    part = getattr(s, n)
                    if part.is_linked_to_previous:
                        continue
                    line = f"[{label}] {_text(part)}"
                except Exception:
                    continue
                if len(line) > len(label) + 3 and line not in out:
                    out.append(line[:600])
    return out


def _extract_docx_bytes(raw: bytes) -> str:
    """DOCX (paragrafi + tabelle). Output INVARIATO rispetto al branch storico."""
    from compliance import features
    if features.on("READ_DOCX_HEADERS"):
        try:
            head = _docx_header_footer_lines(raw)
        except Exception as e:
            _log.warning("[Phase 1] intestazioni docx non lette: %s", e)
            head = []
        body = _extract_docx_body(raw)
        return ("\n".join(head) + "\n" + body) if head and body else body
    return _extract_docx_body(raw)


def _extract_docx_body(raw: bytes) -> str:
    from compliance import features
    if features.on("READ_DOCX_IMAGES"):
        try:
            return _extract_docx_ordered(raw)
        except Exception as e:
            _log.warning("[Phase 1] docx ordinato/OCR fallito, ripiego sullo storico: %s", e)
    try:
        import io
        import docx  # type: ignore
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


def _doc_text_quality(text: str) -> float:
    """Punteggio 0..1 della 'leggibilità' di un testo estratto da .doc.

    Conta la frazione di caratteri che appartengono a parole plausibili
    (lettere/cifre/punteggiatura/spazi comuni) e premia la presenza di run
    alfabetici di lunghezza ≥3 (parole vere). Serve a scegliere la decodifica
    giusta: l'UTF-16LE letto come latin-1 produce 't\\x00e\\x00s\\x00t' →
    dopo lo strip diventa 't e s t', cioè pochissime parole vere → punteggio
    basso. La decodifica corretta produce parole intere → punteggio alto."""
    import re as _re
    if not text:
        return 0.0
    words = _re.findall(r"[A-Za-zÀ-ÿ]{3,}", text)
    word_chars = sum(len(w) for w in words)
    return word_chars / max(len(text), 1)


def _doc_via_antiword(raw: bytes) -> str:
    """Estrae .doc via `antiword` (come AUDITORSEMI su Linux): è il metodo di
    QUALITÀ. antiword è path-based → si scrivono i bytes in un file temporaneo.
    Ritorna "" se antiword non è installato o fallisce (→ il chiamante usa il
    fallback pure-Python). Su Railway va aggiunto al build (Nixpacks aptPkgs)."""
    import os
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("antiword"):
        return ""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tf:
            tf.write(raw)
            tmp_path = tf.name
        result = subprocess.run(
            ["antiword", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return ""
    except Exception:
        return ""
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _extract_doc_legacy(raw: bytes) -> str:
    """.doc legacy (OLE binario). Strategia a due livelli:

    1. **antiword** (se installato): metodo di qualità, identico ad AUDITORSEMI
       su Linux → testo pulito, niente poltiglia, niente retry a valle.
    2. **Fallback pure-Python** (olefile + multi-codec): i Word moderni salvano
       il testo in UTF-16LE; leggerlo come latin-1 (come prima) produceva
       't e s t' spaziato che il motore evidence non riusciva a cardare. Ora si
       provano più decodifiche (utf-16-le, cp1252, latin-1) e si tiene quella con
       più testo leggibile (`_doc_text_quality`). Funziona senza alcun binario."""
    # 1) antiword (qualità) — se presente e il testo è leggibile, vince.
    aw = _doc_via_antiword(raw)
    if aw and _doc_text_quality(aw) >= 0.3:
        return aw

    # 2) fallback pure-Python (olefile + scelta della decodifica migliore).
    try:
        import io
        import re as _re
        import olefile  # type: ignore
        bio = io.BytesIO(raw)
        if not olefile.isOleFile(bio):
            return ""
        ole = olefile.OleFileIO(bio)
        try:
            if not ole.exists("WordDocument"):
                return ""
            data = ole.openstream("WordDocument").read()
        finally:
            ole.close()

        def _clean(s: str) -> str:
            # Rimuovi sequenze di controllo lasciando il testo leggibile.
            s = _re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]+", " ", s)
            s = _re.sub(r"\s{3,}", "\n", s)
            return s.strip()

        # Candidate decodifiche: la UTF-16LE recupera i .doc moderni (PSGSSL),
        # cp1252/latin-1 i vecchi a 8 bit. Si sceglie per qualità misurata.
        candidates = []
        for codec in ("utf-16-le", "cp1252", "latin-1"):
            try:
                candidates.append(_clean(data.decode(codec, errors="ignore")))
            except Exception:
                continue
        if not candidates:
            return ""
        best = max(candidates, key=_doc_text_quality)
        return best
    except Exception:
        return ""


def _extract_rtf(raw: bytes) -> str:
    try:
        from striprtf.striprtf import rtf_to_text  # type: ignore
        s = raw.decode("utf-8", errors="ignore")
        return (rtf_to_text(s) or "").strip()
    except Exception:
        return ""


def _extract_pptx(raw: bytes) -> str:
    try:
        import io
        from pptx import Presentation  # type: ignore
        prs = Presentation(io.BytesIO(raw))
        parts: List[str] = []
        for i, slide in enumerate(prs.slides, 1):
            parts.append(f"[SLIDE {i}]")
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    for para in shape.text_frame.paragraphs:
                        line = "".join(run.text for run in para.runs)
                        if line.strip():
                            parts.append(line)
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        cells = [c.text.strip() for c in row.cells if c.text.strip()]
                        if cells:
                            parts.append(" | ".join(cells))
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _extract_odt(raw: bytes) -> str:
    try:
        import io
        from odf import teletype  # type: ignore
        from odf.opendocument import load  # type: ignore
        doc = load(io.BytesIO(raw))
        return (teletype.extractText(doc.text) or "").strip()
    except Exception:
        return ""


def _extract_ods(raw: bytes) -> str:
    try:
        import io
        from odf import opendocument, table, teletype  # type: ignore
        doc = opendocument.load(io.BytesIO(raw))
        parts: List[str] = []
        for sheet in doc.spreadsheet.getElementsByType(table.Table):
            parts.append(f'[SHEET "{sheet.getAttribute("name")}"]')
            for row in sheet.getElementsByType(table.TableRow):
                cells = []
                for cell in row.getElementsByType(table.TableCell):
                    t = teletype.extractText(cell).strip()
                    if t:
                        cells.append(t)
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _extract_html(raw: bytes) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            html = raw.decode("latin-1", errors="ignore")
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")  # fallback stdlib
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return ""


def _extract_xml(raw: bytes) -> str:
    try:
        import io
        from lxml import etree  # type: ignore
        tree = etree.parse(io.BytesIO(raw))
        parts: List[str] = []
        for elem in tree.getroot().iter():
            if elem.text and elem.text.strip():
                parts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                parts.append(elem.tail.strip())
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _extract_eml(raw: bytes) -> str:
    try:
        import email
        from email import policy
        msg = email.message_from_bytes(raw, policy=policy.default)
        parts: List[str] = []
        for h in ("From", "To", "Subject", "Date"):
            v = msg.get(h)
            if v:
                parts.append(f"{h}: {v}")
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is not None:
            content = body.get_content()
            if isinstance(content, str):
                if body.get_content_type() == "text/html":
                    content = _extract_html(content.encode("utf-8", errors="ignore"))
                parts.append(content)
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _extract_msg(raw: bytes) -> str:
    """.msg Outlook: extract_msg lavora su path → scrivo un file temporaneo."""
    try:
        import os as _os
        import tempfile
        import extract_msg  # type: ignore
        tmp = tempfile.NamedTemporaryFile(suffix=".msg", delete=False)
        try:
            tmp.write(raw)
            tmp.close()
            m = extract_msg.Message(tmp.name)
            parts: List[str] = []
            for label, val in (("From", m.sender), ("To", m.to),
                               ("Subject", m.subject), ("Date", m.date)):
                if val:
                    parts.append(f"{label}: {val}")
            if m.body:
                parts.append(m.body)
            m.close()
            return "\n".join(parts).strip()
        finally:
            try:
                _os.unlink(tmp.name)
            except OSError:
                pass
    except Exception:
        return ""


def _extract_p7m(raw: bytes, filename: str) -> str:
    """.p7m (PKCS#7): wrapper che incapsula un documento firmato (tipicamente
    PDF/DOCX). Best-effort: trova il file embedded e lo estrae ricorsivamente
    (bytes-native, niente file temporanei)."""
    try:
        pdf_start = raw.find(b"%PDF-")
        if pdf_start >= 0:
            pdf_end = raw.rfind(b"%%EOF")
            if pdf_end > pdf_start:
                return _extract_pdf_text(raw[pdf_start:pdf_end + 5], filename)
        zip_start = raw.find(b"PK\x03\x04")
        if zip_start >= 0:
            return _extract_docx_bytes(raw[zip_start:])
        return ""
    except Exception:
        return ""
