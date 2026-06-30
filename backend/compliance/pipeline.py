"""
Amisys QHSE — Compliance Pipeline Orchestrator.

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

# Fase B: Phase 1 extraction vive in compliance/extraction.py (riusabile dal
# DMS senza trascinare ChromaDB). Re-import con gli alias storici così il
# resto di pipeline.py e i test che importano da `compliance.pipeline`
# restano invariati.
from compliance.extraction import (
    extract_document as _read_file_content,
    _extract_pdf_text,
    _extract_spreadsheet_text,
    _repair_zip_name,
    _PDF_PAGE_MIN_NATIVE_CHARS,
)

_log = logging.getLogger("compliance.pipeline")


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 helper — text extraction from ZIP
# ──────────────────────────────────────────────────────────────────────────────

# Phase 1 parallelism — estrazione/OCR è I/O-bound (parse nativo + attesa rete
# Azure DI): il collo di bottiglia su pack scansionati. Il default 8 worker
# abbatte la wall-time SENZA toccare l'output. L'ordine dei documenti è
# PRESERVATO (ricostruzione index-keyed) → byte-identico al sequenziale, vedi
# test_extract_parallel_equivalence. Override via env per il deploy.
EXTRACT_MAX_WORKERS = int(os.environ.get("EXTRACT_MAX_WORKERS", "8"))


def _extract_documents(zip_bytes: bytes, emit: Callable) -> List[Dict[str, Any]]:
    """
    Estrae il testo da TUTTI i file di un archivio ZIP, **ricorrendo dentro gli
    ZIP annidati** a qualsiasi profondità (il junk macOS — `__MACOSX/`, `._*`,
    `.DS_Store` — è l'unica cosa esclusa). Ritorna una lista {filename, content}.

    Estrazione native-first: per ogni file `extract_document` prova il testo
    nativo (pypdfium/openpyxl/docx) e ricade su OCR Azure DI solo per i PDF
    senza testo nativo (scansionati). I file che non producono testo vengono
    saltati ma il problema resta visibile nei log.

    Estrazione PARALLELA (ThreadPoolExecutor): l'OCR è I/O-bound. L'ordine è
    preservato ricostruendo `docs` per indice originale → identico al
    sequenziale (nessuna confusione doc↔card: il binding a valle è comunque per
    filename/evidence_id, vedi embedder/gap_analyzer).
    """
    import hashlib
    from compliance.extraction import iter_zip_files

    emit(5.0, "Extracting documents from archive (nested archives included)…")
    warnings: List[str] = []

    # 1) raccogli tutti i file reali (ricorsione zip annidati)
    all_files = list(iter_zip_files(zip_bytes, on_warn=lambda m: warnings.append(m)))

    # 1b) DEDUP per contenuto (sha256): i pacchetti reali hanno spesso lo stesso
    # file sia "loose" sia dentro uno ZIP annidato (es. cartella PARTE II +
    # PARTE II.zip con gli stessi PDF). Tenere entrambe le copie generava
    # evidence_id/chunk-id duplicati → crash ChromaDB ("duplicated IDs"). Si
    # tiene la prima occorrenza; il dedup PRIMA dell'estrazione evita anche OCR
    # ripetuto sugli stessi bytes.
    files: List = []
    seen_hashes: set = set()
    dup_count = 0
    for name, raw in all_files:
        h = hashlib.sha256(raw).hexdigest()
        if h in seen_hashes:
            dup_count += 1
            continue
        seen_hashes.add(h)
        files.append((name, raw))
    total = len(files)
    emit(6.0, f"Found {total} unique files (nested ZIPs unpacked; "
              f"{dup_count} byte-identical duplicates skipped).")

    # 2) estrai il testo IN PARALLELO (native-first, OCR fallback). Ogni worker
    #    calcola il testo dai PROPRI bytes; i risultati sono indicizzati per
    #    posizione e `docs` è ricostruito in ordine originale (sotto). `emit()`
    #    resta sul thread principale (loop as_completed) per non avere race SSE.
    results: Dict[int, str] = {}
    errors: Dict[int, str] = {}

    def _extract_one(idx, name, raw):
        try:
            return idx, (_read_file_content(name, raw) or ""), None
        except Exception as e:  # mai propagare: si logga in fase di ricostruzione
            return idx, "", str(e)

    if total:
        workers = max(1, min(EXTRACT_MAX_WORKERS, total))
        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_extract_one, i, name, raw)
                for i, (name, raw) in enumerate(files)
            ]
            for fut in as_completed(futures):
                idx, content, err = fut.result()
                results[idx] = content
                if err:
                    errors[idx] = err
                completed += 1
                # Banda larga (6→18%) + emit ad OGNI documento: l'estrazione/OCR
                # è la parte lunga sui pack scansionati, dev'essere visibile che
                # avanza (prima stava schiacciata in 6→8% e sembrava bloccata).
                emit(6.0 + 12.0 * completed / total,
                     f"Reading documents… {completed}/{total}")

    # 3) RICOSTRUZIONE in ordine originale — stessa semantica skip/log del
    #    sequenziale: contenuto vuoto → saltato; eccezione → warning.
    docs: List[Dict[str, Any]] = []
    skipped = 0
    for idx, (name, raw) in enumerate(files):
        content = results.get(idx, "")
        if content and content.strip():
            docs.append({"filename": name, "content": content})
        else:
            skipped += 1
            if idx in errors:
                warnings.append(f"{name}: {errors[idx]}")
                _log.warning("[Phase 1] extraction failed for %s: %s", name, errors[idx])
            else:
                _log.info("[Phase 1] no text extracted from %s (scanned without OCR?)", name)

    for w in warnings[:20]:
        _log.warning("[Phase 1] %s", w)
    emit(18.0, f"Extraction complete: {len(docs)} documents with text "
               f"({skipped} without text, {dup_count} duplicates skipped).")
    return docs

# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 helper — evidence extraction via LLM
# ──────────────────────────────────────────────────────────────────────────────

# ── Phase 2 tuning ─────────────────────────────────────────────────────────
# Batch size chosen for GPT-4.1-mini "needle-in-haystack" sweet spot:
#   - 5 docs/batch = ~95% per-doc completion quality (NON cambia coi worker)
#   - 14 worker × ~24K token/batch ≈ 340K in-flight: ampio margine sulla
#     quota 16M TPM del deployment France Central. Override via env.
#   - Scales: 70 docs = 1 wave, 200 docs = 3 waves.
EVIDENCE_BATCH_SIZE = 5
EVIDENCE_MAX_WORKERS = int(os.environ.get("EVIDENCE_MAX_WORKERS", "14"))
# Hardening 2026 #2 — budget output alzato 8000→12000: con 5 card/batch e
# documenti ricchi (es. DVR), 8000 token erano stretti e l'LLM poteva troncare/
# saltare una card. Combinato con la riconciliazione doc↔card, evita la perdita
# silenziosa di documenti dalla Phase 2.
EVIDENCE_MAX_OUTPUT_TOKENS = 12000
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
    #
    # Hardening 2026 #2 — RICONCILIAZIONE doc↔card: il fallback sintetico storico
    # scattava solo se il batch tornava VUOTO. Se l'LLM tornava N-1 card su N doc
    # (saltava/troncava una card), il documento spariva in silenzio (osservato: il
    # DVR di CO.ENERGIE, 100k char, → nessuna card → §6.1 falso MAJOR). Ora, per
    # ogni batch non-vuoto, verifichiamo che OGNI doc abbia una card; i doc scoperti
    # vengono ri-tentati in isolamento e, se ancora mancanti, ricevono una card
    # sintetica per-doc. Nessun documento può più sparire senza traccia.
    # Assemble: synthetic cards only for FULLY-empty batches. Partial drops (LLM
    # skips a card) and parse corruptions are caught by the FINAL reconciliation
    # below, which runs AFTER the global renumber (so it sees exactly what the
    # downstream parser will see).
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

    # Hardening 2026 #2 — RICONCILIAZIONE FINALE doc↔card sul combined già renumerato.
    # Cattura QUALSIASI documento senza card valida nello yaml finale: sia il batch
    # parziale (LLM salta/tronca una card) sia una corruzione di parsing. I doc
    # scoperti vengono ri-tentati in isolamento; se ancora mancanti ricevono una card
    # sintetica. Nessun documento può sparire silenziosamente dalla Phase 2.
    missing = _docs_without_card(docs, combined)
    if missing:
        _log.warning(
            "[Phase 2] %d/%d doc senza card nel combined — retry: %s",
            len(missing), total, [d.get("filename", "?").split("/")[-1] for d in missing],
        )
        for i in range(0, len(missing), EVIDENCE_BATCH_SIZE):
            rec = _call_llm_for_batch(
                azure_client=azure_client, system_prompt=system_prompt,
                batch_docs=missing[i:i + EVIDENCE_BATCH_SIZE],
                batch_idx=0, total_batches=1,
            )
            if rec and rec.strip():
                combined = combined + "\n\n" + _strip_meta_block(rec)
        combined = _renumber_doc_markers(combined)
        combined = _renumber_evidence_ids(combined)
        still = _docs_without_card(docs, combined)
        if still:
            _log.warning(
                "[Phase 2] %d doc ancora senza card dopo retry — card sintetiche: %s",
                len(still), [d.get("filename", "?").split("/")[-1] for d in still],
            )
            combined = combined + "\n\n" + _synthetic_yaml_for_batch(still)
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
    log = logging.getLogger("compliance.pipeline.phase2_validator")
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

    Returns None if Azure is unreachable (caller emits synthetic cards per-batch).
    """
    try:
        from v2.azure_openai_client_v2 import make_client
        return make_client()  # provider standard (mini): alto volume, 1 call/doc
    except Exception as e:
        _log.warning("[Phase 2] Azure client init failed: %s — batches will fall back", e)
        return None


def _sample_doc_text(content: str, cap: int = EVIDENCE_DOC_CHAR_CAP) -> str:
    """Hardening 2026 #4 — campionamento testa+coda per i documenti lunghi.

    La card di Phase 2 veniva costruita SOLO sui primi `cap` caratteri: per un DVR
    da 224k char la card vedeva il ~7% (intro/metodologia), mancando i contenuti di
    coda (registri rischi, conclusioni, obiettivi). Per i documenti oltre il cap
    prendiamo testa (60%) + coda (40%) con un marcatore di omissione, così la card
    riflette l'intero documento. (Lo Stage B continua a leggere il testo integrale.)
    """
    content = content or ""
    if len(content) <= cap:
        return content
    head = int(cap * 0.6)
    tail = cap - head
    return (content[:head].rstrip()
            + "\n\n[… omitted middle section …]\n\n"
            + content[-tail:].lstrip())


def _build_user_prompt_for_batch(batch_docs: List[Dict[str, Any]]) -> str:
    """Build the user message listing the docs in this batch (with doc cap)."""
    parts: List[str] = []
    for i, doc in enumerate(batch_docs, 1):
        content = _sample_doc_text(doc.get("content") or "", EVIDENCE_DOC_CHAR_CAP)
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
    synthetic cards). Azure-only: niente fallback esterno.
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
                    break  # non-retryable
            # Backoff before next attempt
            if attempt < EVIDENCE_MAX_RETRIES - 1:
                wait = min(
                    EVIDENCE_RETRY_BASE_DELAY * (2 ** attempt),
                    EVIDENCE_RETRY_MAX_DELAY,
                )
                time.sleep(wait)

    # Fase 2 consolidamento: provider Azure-ONLY (fallback Gemini rimosso,
    # decisione utente 2026-06-12). Su esaurimento retry il chiamante emette
    # le carte sintetiche readable:false — i documenti non si perdono mai.
    _log.error(
        "[Phase 2] Batch %d/%d: Azure exhausted, no fallback configured — "
        "synthetic cards will be emitted",
        batch_idx + 1, total_batches,
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


def _basename(name: str) -> str:
    """Ultima componente di path, normalizzata, per il match doc↔card."""
    return str(name or "").replace("\\", "/").split("/")[-1].strip().lower()


def _docs_without_card(docs: List[Dict[str, Any]], batch_yaml: str) -> List[Dict[str, Any]]:
    """Riconciliazione doc↔card (Hardening 2026 #2).

    Parsa le card prodotte per un batch e ritorna i documenti del batch che NON
    hanno una card corrispondente (match per basename, multiset → robusto ai
    basename duplicati entro lo stesso batch). I documenti scoperti vanno ri-tentati.
    """
    from collections import Counter
    from compliance.gap_analyzer import _parse_evidence_yaml
    try:
        cards = _parse_evidence_yaml(batch_yaml)
    except Exception:
        cards = []
    card_bn = Counter(_basename(c.get("file_name", "")) for c in cards if c.get("file_name"))
    missing: List[Dict[str, Any]] = []
    for d in docs:
        bn = _basename(d.get("filename", ""))
        if card_bn.get(bn, 0) > 0:
            card_bn[bn] -= 1
        else:
            missing.append(d)
    return missing


_DOC_MARKER_RE = re.compile(r"#\s*──\s*DOC\s*\d+\s*──")
# Hardening 2026 #2 (root cause) — lo slug dell'evidence_id può contenere TRATTINI
# e PUNTI (l'LLM ci mette spesso la data del documento, es. ev_002_dvr_rev02_2024-09-26).
# Il pattern precedente `[A-Za-z0-9_]*` si fermava al trattino e lasciava testo
# penzolante (…2024"-09-26") che rompeva lo YAML → la card spariva nel parse finale.
# Ora lo slug assorbe l'intero token fino alla chiusura.
_EVIDENCE_ID_RE = re.compile(r'evidence_id:\s*"?ev_\d+(_[A-Za-z0-9_.\-]*)?"?')


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
    zip_bytes: Optional[bytes],
    company_context: CompanyContext,
    emitter: Optional[Callable[[float, str], None]] = None,
    documents_override: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Full compliance pipeline.

    Args:
        zip_bytes:          Raw bytes of the uploaded ZIP archive (None quando
                            si usa documents_override).
        company_context:    Validated CompanyContext from wizard Step 0.
        emitter:            Optional callable(pct, msg) for SSE streaming.
        documents_override: Fase 6 — lista {filename, content} già estratta
                            (corpus persistito): salta la Phase 1 e rilancia
                            l'analisi sulla stessa base documentale
                            (re-analyse, fondamento di PRD §1.4.3).

    Returns:
        dict with keys: success, analysis_id, result, evidence_yaml, error
    """
    def emit(pct: float, msg: str) -> None:
        if emitter:
            try:
                emitter(pct, msg)
            except Exception:
                pass

    start = time.monotonic()

    try:
        # ── Phase 1: Extract documents from ZIP (o riuso corpus salvato) ─────
        if documents_override is not None:
            docs = [d for d in documents_override if str(d.get("content", "")).strip()]
            emit(8.0, f"Reusing stored corpus: {len(docs)} documents (extraction skipped).")
        else:
            docs = _extract_documents(zip_bytes or b"", emit)
        if not docs:
            emit(100.0, "No readable documents found in archive.")
            return {"success": False, "error": "no_documents", "analysis_id": None, "result": None}

        # ── Phase 2: Evidence extraction (LLM) ───────────────────────────────
        evidence_yaml = _extract_evidence(docs, company_context, emit)

        # ── Phase 2.5: Expiry check (deterministic, Python-only) ─────────────
        from compliance.expiry_check import run_expiry_check
        from compliance.schemas import ExpiryReport
        from datetime import datetime as _dt, timezone as _tz
        expiry_dict = run_expiry_check(
            evidence_yaml=evidence_yaml,
            audit_date=_dt.now(_tz.utc).date(),
            emitter=emit,
        )

        # ── Phase 3: Gap analysis (ChromaDB + LLM per clause) ────────────────
        result: ComplianceAnalysisResult = analyze_compliance(
            evidence_yaml=evidence_yaml,
            company_context=company_context,
            emitter=lambda pct, msg: emit(35.0 + pct * 0.55, msg),
            documents=docs,  # Sprint R2: full texts for chunk index + deep pass
        )

        # Attach Phase 2.5 output to the final result
        try:
            result.expiry_report = ExpiryReport(**expiry_dict)
        except Exception as e:
            # Schema validation failure shouldn't kill the analysis — log and skip
            logging.getLogger("compliance.pipeline").warning(
                f"ExpiryReport schema validation failed: {e!s} — continuing without it"
            )

        # ── Phase 4: Executive summary (LLM) ─────────────────────────────────
        emit(92.0, "Phase 4: drafting executive summary…")
        try:
            from compliance.schemas import ExecutiveSummary
            es_dict = generate_executive_summary(result, evidence_yaml=evidence_yaml)
            if es_dict:
                result.executive_summary = ExecutiveSummary(**es_dict)
        except Exception as e:
            logging.getLogger("compliance.pipeline").warning(
                f"ExecutiveSummary generation failed: {e!s} — continuing without it"
            )

        # ── Fase 6: persisti il corpus estratto (abilita re-analyse) ─────────
        try:
            from modules.db_manager import save_analysis_corpus
            saved = save_analysis_corpus(result.analysis_id, docs)
            _log.info("Corpus persisted: %d documents for %s", saved, result.analysis_id)
        except Exception as e:
            _log.warning("Corpus persistence failed (non-blocking): %s", e)

        elapsed = round(time.monotonic() - start, 1)
        emit(100.0, f"Pipeline complete in {elapsed}s.")

        return {
            "success":       True,
            "analysis_id":   result.analysis_id,
            "result":        result,
            # Sprint R1: expose the full Phase 2 output so the endpoint can
            # persist it (chat over all documents, delta, re-scan scoping).
            "evidence_yaml": evidence_yaml,
            "error":         None,
        }

    except Exception as e:
        emit(100.0, f"Pipeline error: {e}")
        return {
            "success":     False,
            "analysis_id": None,
            "result":      None,
            "error":       str(e),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4 — Executive Summary generation (Sprint 4)
# ──────────────────────────────────────────────────────────────────────────────

def generate_executive_summary(
    result: "ComplianceAnalysisResult",
    evidence_yaml: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Build the executive summary for the manager-facing report.

    Calls the LLM with `executive_summary_prompt.md` + a compact JSON view of
    the analysis result, and parses the response into the schema documented
    in the prompt. Returns a dict ready to be validated by ExecutiveSummary,
    or None on unrecoverable failure.

    Lives in pipeline.py (not in a new module) because it composes the
    existing Phase 2/3 outputs into a Phase 4 narrative — keeping the
    orchestration boundary in one file.
    """
    import json as _json
    from pathlib import Path as _Path
    from compliance.context_intake import build_context_prompt_block

    prompt_path = _Path(__file__).resolve().parent.parent / "prompts" / "compliance" / "executive_summary_prompt.md"
    try:
        system_prompt = prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        logging.getLogger("compliance.pipeline").warning(f"executive_summary_prompt.md missing: {e}")
        return None

    context_block = build_context_prompt_block(result.context)
    system_prompt = system_prompt.replace("{company_context}", context_block)

    # Build a compact JSON view of the analysis — full ClauseGap objects are
    # too verbose for the prompt; we keep only the fields the prompt needs.
    compact: Dict[str, Any] = {
        "company": result.company,
        "context": result.context.model_dump() if hasattr(result.context, "model_dump") else dict(result.context),
        "documents_analyzed": result.documents_analyzed,
        "norms": [],
    }
    for norm in result.norms:
        compact["norms"].append({
            "norm":             norm.norm,
            "overall_score":    norm.overall_score,
            "major_count":      norm.major_count,
            "minor_count":      norm.minor_count,
            "observation_count": norm.observation_count,
            "conformant_count": norm.conformant_count,
            "spof_count":       norm.spof_count,
            "clauses": [
                {
                    "clause_id":   g.clause_id,
                    "severity":    g.severity,
                    "is_spof":     g.is_spof,
                    "finding":     g.finding[:300],
                    "sources":     [
                        {"file_name": s.file_name, "evidence_id": s.evidence_id}
                        for s in g.sources[:3]
                    ],
                    "remediation": {
                        "what":   g.remediation.what[:200],
                        "who":    g.remediation.who,
                        "when":   g.remediation.when,
                        "effort": g.remediation.effort,
                    },
                }
                for g in norm.clauses
            ],
        })
    compact["top_gaps"] = [
        {
            "clause_id": g.clause_id,
            "severity":  g.severity,
            "is_spof":   g.is_spof,
            "finding":   g.finding[:300],
        }
        for g in result.top_gaps
    ]
    if result.expiry_report is not None:
        compact["expiry_report"] = {
            "audit_date":           result.expiry_report.audit_date,
            "no_expiry_information": result.expiry_report.no_expiry_information,
            "expired_documents":    [d.model_dump() for d in result.expiry_report.expired_documents],
            "expiring_soon":        [d.model_dump() for d in result.expiry_report.expiring_soon],
        }

    # Sprint R8 — signatories from the evidence cards (Q9 `signed_by`), so the
    # prompt's key_roles rule can actually be satisfied. Before this fix the
    # compact JSON carried no signed_by at all and key_roles was unfillable.
    if evidence_yaml.strip():
        try:
            from compliance.gap_analyzer import _parse_evidence_yaml
            signatories = []
            for card in _parse_evidence_yaml(evidence_yaml):
                signer = str(card.get("signed_by") or "").strip()
                if signer and signer.lower() not in ("null", "none", "unknown"):
                    signatories.append({
                        "signed_by": signer[:120],
                        "file_name": str(card.get("file_name", ""))[:120],
                        "doc_type": str(card.get("doc_type", "other")),
                    })
            if signatories:
                compact["signatories"] = signatories[:20]
        except Exception:
            pass

    # Sprint R6 — give the narrative visibility of the new engine outputs
    if result.documented_info_report is not None:
        compact["documented_info"] = {
            "absent": [
                {"item": i.item, "norm": i.norm, "risk": i.risk_if_missing}
                for i in result.documented_info_report.items if i.status == "ABSENT"
            ],
            "found_count": result.documented_info_report.found_count,
        }
    if result.cross_clause_findings:
        compact["cross_clause"] = [
            {"title": f.title, "status": f.status, "narrative": f.narrative[:200]}
            for f in result.cross_clause_findings
            if f.status in ("BROKEN", "PARTIAL")
        ]

    user_prompt = (
        "## ComplianceAnalysisResult (compact JSON view)\n"
        "```json\n"
        + _json.dumps(compact, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "Produce the executive summary JSON object as instructed."
    )

    # Call Azure (Azure-only — fallback Gemini rimosso, decisione utente
    # 2026-06-12). deep=True: l'executive summary è user-facing per Fred e
    # usa il profilo deep quando configurato. Su errore il summary viene
    # saltato e l'analisi resta valida (campo opzionale).
    raw = ""
    try:
        from v2.azure_openai_client_v2 import make_client
        client = make_client(deep=True)
        stream = client.chat_stream(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=2500,
        )
        chunks: List[str] = []
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    chunks.append(content)
        raw = "".join(chunks).strip()
    except Exception as e:
        logging.getLogger("compliance.pipeline").error(
            f"Azure executive_summary failed — no fallback configured: {e}"
        )
        return None

    # Parse JSON (tolerate code fences)
    text = raw.strip()
    if text.startswith("```"):
        # strip first fence line
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()

    try:
        data = _json.loads(text)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        logging.getLogger("compliance.pipeline").warning(
            f"executive_summary JSON parse failed: {e!s} — raw[:200]={raw[:200]!r}"
        )
        return None
