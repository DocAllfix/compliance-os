"""
Amisys QHSE — Ingest analisi → DMS (DMS unificato).

Dopo un'analisi da ZIP, popola automaticamente il DMS: una cartella = azienda, i
file dello ZIP come documenti, versionati ad ogni ri-analisi della stessa azienda.
Riusa il TESTO già estratto dall'analisi (corpus, OCR incluso) → **nessun re-OCR**;
i byte si ricavano ri-iterando lo ZIP (cheap, no OCR). Non-bloccante: gli errori
non rompono l'analisi (gira nel callback on_success, dopo il salvataggio).
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Dict, Optional, Tuple

import modules.dms_manager as dms
from modules.db_manager import load_analysis_corpus, set_corpus_dms_link

_log = logging.getLogger("compliance.dms_ingest")

# Default ON; disattivabile (es. nei test) con DMS_AUTOSAVE=0.
DMS_AUTOSAVE = os.environ.get("DMS_AUTOSAVE", "1") not in ("0", "false", "False")


def _basename(name: str) -> str:
    return str(name or "").replace("\\", "/").split("/")[-1]


def _resolve_company_folder(owner: str, company_name: str) -> int:
    """Cartella top-level = azienda. Match per nome (case-insensitive) tra le root
    dell'owner; altrimenti la crea. Fallback per nome vuoto."""
    name = (company_name or "").strip() or f"Imported {date.today().isoformat()}"
    for f in dms.list_all_folders(owner):
        if f.get("parent_id") is None and str(f.get("name", "")).strip().lower() == name.lower():
            return int(f["id"])
    return dms.create_folder(owner, name, parent_id=None)


def ingest_analysis(
    owner: str,
    company_name: str,
    zip_bytes: bytes,
    analysis_id: str,
    evidence_yaml: str = "",
) -> Dict[str, int]:
    """Popola il DMS dai documenti analizzati. Ritorna {created, versioned, skipped}."""
    from compliance.extraction import iter_zip_files
    from compliance.gap_analyzer import _parse_evidence_yaml
    from compliance.doc_classifier import classify

    created = versioned = skipped = 0
    folder_id = _resolve_company_folder(owner, company_name)

    # byte per nome (no OCR)
    name_to_bytes: Dict[str, bytes] = {}
    try:
        for path, data in iter_zip_files(zip_bytes):
            name_to_bytes[path] = data
    except Exception as e:
        _log.warning("[dms_ingest] iter_zip_files failed: %s", e)
        return {"created": 0, "versioned": 0, "skipped": 0}

    # mappa basename → bytes (fallback se il corpus ha il path completo)
    base_to_bytes: Dict[str, bytes] = {}
    for k, v in name_to_bytes.items():
        base_to_bytes.setdefault(_basename(k), v)

    # testo già estratto (OCR incluso) + tipi dalle evidence card (engine)
    corpus = load_analysis_corpus(analysis_id)  # [{filename, content}]
    type_by_name: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    if (evidence_yaml or "").strip():
        try:
            for card in _parse_evidence_yaml(evidence_yaml):
                fn = str(card.get("file_name", "") or "")
                if fn:
                    type_by_name[_basename(fn)] = (
                        str(card.get("doc_type", "") or "").strip() or None,
                        card.get("expiry_date") or None,
                    )
        except Exception:
            pass

    for doc in corpus:
        fname = doc["filename"]
        base = _basename(fname)
        raw = name_to_bytes.get(fname) or base_to_bytes.get(base)
        if raw is None:
            skipped += 1
            continue
        text = doc.get("content") or ""
        dtype, expiry = type_by_name.get(base, (None, None))
        if dtype:
            src = "engine"
        else:
            dtype, src = classify(base, text), "heuristic"
        try:
            existing = dms.find_document_by_name(owner, folder_id, base)
            if existing:
                res = dms.add_version(
                    existing["id"], raw, text, uploaded_by=owner,
                    note=f"from analysis {analysis_id}", doc_type=dtype, expiry_date=expiry,
                )
                versioned += 0 if res.get("deduped") else 1
                if res.get("deduped"):
                    skipped += 1
            else:
                res = dms.create_document(
                    owner=owner, folder_id=folder_id, filename=base, raw=raw,
                    extracted_text=text, doc_type=dtype, doc_type_source=src,
                    expiry_date=expiry, uploaded_by=owner,
                    note=f"from analysis {analysis_id}",
                )
                created += 1
            set_corpus_dms_link(analysis_id, fname, int(res["document_id"]), int(res["version"]))
        except ValueError as e:  # cap dimensione file
            _log.warning("[dms_ingest] skip %s: %s", base, e)
            skipped += 1
        except Exception as e:
            _log.warning("[dms_ingest] failed %s: %s", base, e)
            skipped += 1

    _log.info("[dms_ingest] analysis %s → DMS folder %s: created=%d versioned=%d skipped=%d",
              analysis_id, folder_id, created, versioned, skipped)
    return {"created": created, "versioned": versioned, "skipped": skipped}
