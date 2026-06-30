"""
Fast regression — Fase B hotfix: pypdfium2 NON è thread-safe.

La parallelizzazione di Phase 1 faceva chiamare pypdfium da più worker
contemporaneamente → Segmentation fault (munmap_chunk: invalid pointer),
osservato in produzione su ECOMAR. Il fix è un lock che serializza il parsing
nativo pypdfium (`_PDFIUM_LOCK` in extraction.py), tenendo l'OCR di rete fuori
dal lock.

Questi test riproducono lo scenario di crash (estrazione PDF concorrente):
SENZA il lock segfaultano il processo; CON il lock passano. Usano un PDF nativo
reale del repo (niente OCR/Azure), e si skippano se il file non c'è.
"""
from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path

import pytest

import compliance.pipeline as pipeline
from compliance.extraction import extract_document

_PDF = (
    Path(__file__).resolve().parents[2]
    / "knowledgecompliance"
    / "Master ISO 9001 14001 45001 Compliance Knowledge Base & Audit Blueprint.pdf"
)
_skip = pytest.mark.skipif(not _PDF.exists(), reason="sample native PDF not available")


@_skip
def test_concurrent_pdf_extraction_no_segfault():
    raw = _PDF.read_bytes()
    results: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker():
        try:
            out = extract_document("sample.pdf", raw)
            with lock:
                results.append(out)
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"estrazione concorrente ha sollevato: {errors[:3]}"
    assert len(results) == 12
    assert all(r.strip() for r in results)        # testo estratto
    assert len(set(results)) == 1                 # stesso PDF → stesso output


@_skip
def test_parallel_pipeline_pdf_no_segfault(monkeypatch):
    raw = _PDF.read_bytes()
    # 8 PDF "distinti" (suffisso commento → bytes diversi, no dedup sha256).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(8):
            zf.writestr(f"doc_{i:02d}.pdf", raw + f"\n%distinct-{i}".encode())

    monkeypatch.setattr(pipeline, "EXTRACT_MAX_WORKERS", 8)
    docs = pipeline._extract_documents(buf.getvalue(), lambda *_a, **_k: None)

    assert len(docs) == 8
    assert all(d["content"].strip() for d in docs)
    # ordine preservato
    assert [d["filename"] for d in docs] == [f"doc_{i:02d}.pdf" for i in range(8)]
