"""
Fast regression for cite-or-fail enforcement in _parse_batch_clause_gap.

The parser must:
  - discard evidence_id values not present in the evidence_list passed in
  - keep the valid ones
  - downgrade CONFORMANT to OBSERVATION when no valid citations survive
    and evidence was available (LLM cannot claim conformity it cannot cite)
"""
from __future__ import annotations

from compliance.gap_analyzer import _parse_batch_clause_gap


def _clause():
    return {
        "id": "9001_8_4",
        "title": "8.4 Control of externally provided processes",
        "remediation_template": {
            "what": "Implement supplier evaluation",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
        "is_spof": True,
    }


def _evidence_list():
    return [
        {"evidence_id": "ev_001", "file_name": "supplier.pdf", "excerpt": "supplier list"},
        {"evidence_id": "ev_002", "file_name": "audit.pdf",    "excerpt": "supplier audit"},
    ]


def test_hallucinated_ids_are_discarded():
    """LLM cites two real IDs + two fakes; only the real ones survive."""
    llm_response = {
        "clause_id": "9001_8_4",
        "score": 75,
        "severity": "OBSERVATION",
        "is_spof": False,
        "finding": "Some finding.",
        "evidence_used": ["ev_001", "ev_INVENTED_001", "ev_002", "ev_FAKE_002"],
        "remediation": {"what": "x", "who": "QM", "when": "30 days", "effort": "LOW"},
    }
    gap = _parse_batch_clause_gap(llm_response, _clause(), _evidence_list())
    cited_ids = [s.evidence_id for s in gap.sources]
    assert "ev_001" in cited_ids
    assert "ev_002" in cited_ids
    assert "ev_INVENTED_001" not in cited_ids
    assert "ev_FAKE_002" not in cited_ids
    assert len(gap.sources) == 2


def test_all_hallucinated_ids_with_conformant_downgrades_to_observation():
    """LLM claims CONFORMANT but every cited ID is invented → downgrade."""
    llm_response = {
        "clause_id": "9001_8_4",
        "score": 92,
        "severity": "CONFORMANT",
        "is_spof": False,
        "finding": "All good.",
        "evidence_used": ["ev_FAKE_001", "ev_FAKE_002"],
        "remediation": {"what": "x", "who": "QM", "when": "30 days", "effort": "LOW"},
    }
    gap = _parse_batch_clause_gap(llm_response, _clause(), _evidence_list())
    assert gap.severity == "OBSERVATION"  # downgraded by the post-LLM guard
    assert gap.sources == []


def test_legacy_sources_shape_is_also_accepted():
    """The parser must accept the older `sources: [{evidence_id: ...}]` shape."""
    llm_response = {
        "clause_id": "9001_8_4",
        "score": 60,
        "severity": "MINOR",
        "is_spof": False,
        "finding": "Some finding.",
        "sources": [
            {"evidence_id": "ev_001", "file_name": "supplier.pdf"},
            {"evidence_id": "ev_PHANTOM", "file_name": "ghost.pdf"},
        ],
        "remediation": {"what": "x", "who": "QM", "when": "30 days", "effort": "LOW"},
    }
    gap = _parse_batch_clause_gap(llm_response, _clause(), _evidence_list())
    cited_ids = [s.evidence_id for s in gap.sources]
    assert cited_ids == ["ev_001"]


def test_no_citations_with_no_evidence_is_fine():
    """LLM citing nothing when the evidence list was empty is normal MAJOR."""
    llm_response = {
        "clause_id": "9001_8_4",
        "score": 15,
        "severity": "MAJOR",
        "is_spof": True,
        "finding": "No evidence retrieved.",
        "evidence_used": [],
        "remediation": {"what": "x", "who": "QM", "when": "30 days", "effort": "HIGH"},
    }
    gap = _parse_batch_clause_gap(llm_response, _clause(), [])
    assert gap.severity == "MAJOR"
    assert gap.sources == []
    assert gap.is_spof is True
