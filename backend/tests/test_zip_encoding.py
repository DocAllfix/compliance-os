"""
Sprint G.2 regression: ZIP nomi file in UTF-8 NFD (macOS) devono uscire
da _extract_documents() in NFC.

Costruiamo un ZIP in-memory con un nome che contiene una sequenza
combining (`a` + U+0300 = `à`). Senza NFC normalize, il name che arriva
in docs[0]["filename"] sarebbe ancora decomposto e la sequenza combining
si vedrebbe corrotta nel frontend. Con il fix dello Sprint G.2, il nome
arriva precomposto.

Test fast — niente Azure, niente LLM, niente PDF. Solo zipfile + asserzioni.
"""
from __future__ import annotations

import io
import unicodedata
import zipfile


def _build_zip_with_nfd_name() -> bytes:
    """Crea uno ZIP con un .txt il cui nome è in UTF-8 NFD."""
    nfd_name = "Idoneità GRAMAZIO.txt"  # "a" + U+0300 = "à" decomposta
    # Verifichiamo che la stringa di partenza sia effettivamente decomposta
    assert unicodedata.normalize("NFC", nfd_name) != nfd_name, "Setup error: name è già NFC"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(nfd_name, b"contenuto di test per il file con accento.")
    return buf.getvalue()


def test_extract_documents_normalises_filenames_to_nfc():
    """_extract_documents deve emettere filename in NFC, non in NFD."""
    from compliance.pipeline import _extract_documents

    zip_bytes = _build_zip_with_nfd_name()
    emissions: list = []

    def emit(pct: float, msg: str) -> None:
        emissions.append((pct, msg))

    docs = _extract_documents(zip_bytes, emit)

    assert len(docs) == 1, f"Expected 1 doc, got {len(docs)}"
    filename = docs[0]["filename"]
    # Il nome estratto deve essere già NFC (la "à" come singolo char U+00E0)
    assert filename == unicodedata.normalize("NFC", filename), (
        f"Filename non normalizzato in NFC: {filename!r}"
    )
    # Sanity: nessun carattere combining residuo nel range U+0300-U+036F
    for ch in filename:
        assert not (0x0300 <= ord(ch) <= 0x036F), (
            f"Combining diacritic residuo in filename: {filename!r}"
        )
    # E il contenuto è stato letto correttamente (.txt → UTF-8 decode)
    assert "contenuto di test" in docs[0]["content"]


def test_extract_documents_handles_ascii_names_unchanged():
    """Regression: i nomi ASCII normali non devono essere alterati."""
    from compliance.pipeline import _extract_documents

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("simple_name.txt", b"hello world")

    docs = _extract_documents(buf.getvalue(), emit=lambda *_a, **_k: None)
    assert len(docs) == 1
    assert docs[0]["filename"] == "simple_name.txt"
