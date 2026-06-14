"""
Fast regression — Hardening 2026 problema #4 (campionamento Phase 2 testa+coda).

Pin: i documenti sotto il cap restano integri; quelli oltre il cap vengono
campionati testa+coda (così la card riflette anche la coda del documento), entro
il budget di caratteri.
"""
from __future__ import annotations

from compliance.pipeline import _sample_doc_text, EVIDENCE_DOC_CHAR_CAP


def test_short_doc_unchanged():
    txt = "abc " * 100
    assert _sample_doc_text(txt, EVIDENCE_DOC_CHAR_CAP) == txt


def test_long_doc_head_and_tail():
    head = "HEADSTART" + "h" * 50_000
    tail = "t" * 50_000 + "TAILEND"
    txt = head + tail
    out = _sample_doc_text(txt, EVIDENCE_DOC_CHAR_CAP)
    assert out.startswith("HEADSTART")          # testa preservata
    assert out.rstrip().endswith("TAILEND")     # coda preservata (prima persa)
    assert "omitted middle section" in out
    # entro il budget (+ marcatore)
    assert len(out) <= EVIDENCE_DOC_CHAR_CAP + 60


def test_exact_cap_unchanged():
    txt = "x" * EVIDENCE_DOC_CHAR_CAP
    assert _sample_doc_text(txt, EVIDENCE_DOC_CHAR_CAP) == txt
