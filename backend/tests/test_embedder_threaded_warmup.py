"""
Fast regression — embedder parallelo (commit 1c36fd2) crashava su Railway con
`[ONNXRuntimeError] NO_SUCHFILE: model.onnx ... File doesn't exist`.

Root cause: su un container FREDDO la cache onnx (`~/.cache/chroma`) è vuota.
La `cached_property model` di ChromaDB costruisce solo la InferenceSession dal
file su disco e DÀ PER SCONTATO che esista — il download avviene unicamente in
`_download_model_if_not_exists()`. Il warm-up del thread-pool faceva
`_ = self.model` SENZA prima scaricare → la sessione veniva costruita su un file
inesistente → crash. In locale non si vedeva: il modello era già in cache.

Fix: il warm-up ora chiama `_download_model_if_not_exists()` PRIMA di toccare
`model`/`tokenizer`, replicando la precondizione del base `__call__`.

Questo test prova l'ORDINE (download → sessione) senza rete né onnxruntime
reale: col vecchio codice order[0] sarebbe "model" e fallirebbe.
"""
from __future__ import annotations

import numpy as np
import pytest

from compliance.embedder import (
    ONNXMiniLM_L6_V2,
    _EMBED_MIN_PARALLEL,
    _ThreadedONNXMiniLM,
)

pytestmark = pytest.mark.skipif(
    ONNXMiniLM_L6_V2 is None, reason="chromadb onnx EF not importable"
)


def test_threaded_embedder_downloads_before_session(monkeypatch):
    order: list[str] = []

    class _Probe(_ThreadedONNXMiniLM):  # type: ignore[misc,valid-type]
        def __init__(self):
            # Bypassa l'__init__ pesante: ci servono solo i worker e il path.
            self._workers = 4
            self._preferred_providers = None

        def _download_model_if_not_exists(self):  # type: ignore[override]
            order.append("download")

        @property
        def model(self):  # type: ignore[override]
            order.append("model")
            return object()

        @property
        def tokenizer(self):  # type: ignore[override]
            order.append("tokenizer")
            return object()

    # Le chiamate base per-fetta non devono fare inferenza reale.
    monkeypatch.setattr(
        ONNXMiniLM_L6_V2,
        "_forward",
        lambda self, docs, batch_size=32: np.zeros((len(docs), 4), dtype=np.float32),
    )

    n = _EMBED_MIN_PARALLEL * 2  # sopra soglia → percorso parallelo
    out = _Probe()([f"d{i}" for i in range(n)])

    # Tutti i vettori prodotti, in ordine.
    assert len(out) == n
    # La precondizione critica: il download precede QUALSIASI accesso alla
    # sessione/tokenizer (altrimenti NO_SUCHFILE su container freddo).
    assert order, "il warm-up non è stato eseguito"
    assert order[0] == "download", f"download non per primo: {order[:4]}"
    assert "model" in order[:3] and "tokenizer" in order[:3]
