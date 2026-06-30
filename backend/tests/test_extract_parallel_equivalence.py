"""
Fast regression — Fase B (parallelizzazione Phase 1).

Garanzia ANTI-CONFUSIONE: l'estrazione parallela deve produrre un output
**byte-identico** al sequenziale — stessi documenti, stesso ordine, stesso
contenuto. Se questa identità regge, nessun documento può associarsi alla card
sbagliata (il binding a valle è comunque per filename/evidence_id).

Usa solo file .txt → nessuna dipendenza da Azure DI (gira nella fast suite).
"""
from __future__ import annotations

import io
import zipfile

import compliance.pipeline as pipeline
from compliance.pipeline import _extract_documents


def _noop(*_a, **_k) -> None:
    pass


def _make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files:
            zf.writestr(name, text)
    return buf.getvalue()


def _run_with_workers(zip_bytes, n, monkeypatch):
    monkeypatch.setattr(pipeline, "EXTRACT_MAX_WORKERS", n)
    return _extract_documents(zip_bytes, _noop)


def test_parallel_equals_sequential_order_and_content(monkeypatch):
    # Nomi NON ordinati alfabeticamente + contenuto distinto e di lunghezza
    # variabile (i worker finiscono in ordine diverso dal sottomesso).
    files = [
        (f"dir{i % 3}/doc_{i:02d}_{50 - i}.txt", f"CONTENT-{i}\n" + ("riga\n" * (i + 1)))
        for i in range(30)
    ]
    zip_bytes = _make_zip(files)

    seq = _run_with_workers(zip_bytes, 1, monkeypatch)   # sequenziale
    par = _run_with_workers(zip_bytes, 8, monkeypatch)   # parallelo

    # Ordine dei filename identico
    assert [d["filename"] for d in seq] == [d["filename"] for d in par]
    # Filename + contenuto identici (dict completi)
    assert seq == par
    # Tutti i 30 documenti presenti
    assert len(seq) == 30
    # Ogni contenuto è legato al PROPRIO documento (no scambi)
    for d in par:
        idx = int(d["filename"].split("doc_")[1][:2])
        assert d["content"].startswith(f"CONTENT-{idx}\n")


def test_parallel_skip_semantics_match_sequential(monkeypatch):
    # Mix: file con testo, file vuoto (skippato), estensione ignota (skippata).
    files = [
        ("a_real.txt", "hello world"),
        ("b_empty.txt", "   "),            # solo whitespace → skip
        ("c_unknown.bin", "binarystuff"),  # estensione non gestita → "" → skip
        ("d_real.txt", "second document"),
    ]
    zip_bytes = _make_zip(files)

    seq = _run_with_workers(zip_bytes, 1, monkeypatch)
    par = _run_with_workers(zip_bytes, 8, monkeypatch)

    assert seq == par
    # Solo i due .txt con testo sopravvivono, in ordine
    assert [d["filename"] for d in par] == ["a_real.txt", "d_real.txt"]
