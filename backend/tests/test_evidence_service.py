"""
Fast regression for EvidenceService over an in-process ChromaDB index.

These tests touch ChromaDB but never call any LLM, so they remain fast
(< 5 s on a cold start, much less when chromadb is already imported).
"""
from __future__ import annotations

import uuid

import pytest

from compliance.evidence_service import EvidenceService


@pytest.fixture
def service(mock_evidence_cards):
    """Indexed EvidenceService scoped to a single test."""
    analysis_id = f"test_{uuid.uuid4().hex[:8]}"
    svc = EvidenceService.from_cards(analysis_id, mock_evidence_cards)
    yield svc
    svc.close()


def test_get_all_cards_returns_indexed_set(service, mock_evidence_cards):
    """Every card we indexed must come back via get_all_cards."""
    cards = service.get_all_cards()
    assert len(cards) == len(mock_evidence_cards)
    indexed_ids = {c.get("evidence_id") for c in cards}
    expected_ids = {c["evidence_id"] for c in mock_evidence_cards}
    assert indexed_ids == expected_ids


def test_get_evidences_by_doc_type(service):
    """Metadata filter returns cards of the requested doc_type only."""
    training = service.get_evidences_by_doc_type("training_record")
    assert len(training) == 1
    assert training[0]["evidence_id"] == "ev_003_training"


def test_get_evidences_for_clause_returns_relevant(service):
    """Semantic search on a §7.5 clause should rank the manual highly."""
    clause = {
        "title": "7.5 Documented information",
        "evidence_keywords": ["documented information", "document control"],
    }
    results = service.get_evidences_for_clause(clause, n=3)
    assert len(results) >= 1
    # The quality manual card is the obvious best match
    top_ids = {r.get("evidence_id") for r in results}
    assert "ev_001_manual" in top_ids


def test_get_evidences_similar_to_handles_freeform_query(service):
    """Free-text query path returns at least one result for a sensible question."""
    results = service.get_evidences_similar_to("training certificates and expiries", n=3)
    assert len(results) >= 1


def test_get_evidences_similar_to_empty_query_returns_nothing(service):
    """An empty query short-circuits to an empty list (no API call)."""
    assert service.get_evidences_similar_to("") == []
    assert service.get_evidences_similar_to("   \n  ") == []


def test_close_is_idempotent(service):
    """Calling close twice (or after the fixture's close) must not raise."""
    service.close()
    service.close()  # safe even on a freed service
