"""
Fast regression for the upload-time document classifier (Fase C).

Heuristic only (no LLM): pins doc_type vocabulary alignment, a few
filename/content classifications, and the labelled-expiry detector — which
must stay conservative (an unlabelled date is NOT an expiry).
"""
from __future__ import annotations

from compliance.doc_classifier import classify, detect_expiry, VALID_DOC_TYPES


def test_classify_returns_vocabulary_member():
    for fn in ("Quality Manual.pdf", "weird name.pdf", "QP-01.docx"):
        assert classify(fn, "") in VALID_DOC_TYPES


def test_classify_common_documents():
    assert classify("Quality Manual rev3.pdf", "") == "quality_manual"
    assert classify("Risk Assessment 2026.xlsx", "risk register 5x5") == "risk_assessment"
    assert classify("Internal Audit Programme 2025.docx", "") == "audit_report"
    assert classify("attestato.pdf", "attestato di formazione antincendio") == "training_record"
    assert classify("Management Review Minutes.docx", "riesame della direzione") == "management_review"
    assert classify("totally-unknown.bin", "lorem ipsum") == "other"


def test_detect_expiry_requires_label():
    assert detect_expiry("Certificate valid until 31/12/2027.") == "2027-12-31"
    assert detect_expiry("Scadenza: 15-06-2026") == "2026-06-15"
    assert detect_expiry("Issued 2024-01-10, next review 2026-01-10") == "2026-01-10"
    # unlabelled date must NOT be treated as expiry
    assert detect_expiry("Meeting held on 14/03/2026") is None
    assert detect_expiry("no dates at all") is None


def test_detect_expiry_picks_furthest_future():
    txt = "valid until 31/12/2026 and renewal date 31/12/2028"
    assert detect_expiry(txt) == "2028-12-31"


def test_detect_expiry_rejects_invalid_date():
    assert detect_expiry("expiry 31/02/2026") is None  # Feb 31 invalid
