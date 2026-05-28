"""
Fast regression for _apply_severity_floor and clause_helpers derivations.

The floor must:
  - escalate OBSERVATION → MAJOR for critical clauses with no evidence
  - escalate OBSERVATION → MINOR for standard clauses
  - NEVER apply to passing (context) clauses
  - NEVER downgrade an already-strict verdict
  - NEVER override a genuine CONFORMANT verdict that has sources
"""
from __future__ import annotations

from compliance.clause_helpers import (
    get_criticality_tier, get_severity_floor, get_weight, is_expiry_relevant,
)
from compliance.gap_analyzer import _apply_severity_floor
from compliance.schemas import ClauseGap, RemediationPlan, TraceabilityLink


def _make_gap(severity: str, with_sources: bool = False, finding: str = "test") -> ClauseGap:
    sources = []
    if with_sources:
        sources = [TraceabilityLink(
            evidence_id="ev_001", file_name="x.pdf", pages=[1],
            excerpt="exc", relevance_score=0.8,
        )]
    return ClauseGap(
        clause_id="test_clause",
        clause_title="Test clause",
        score=50,
        severity=severity,
        is_spof=False,
        finding=finding,
        sources=sources,
        remediation=RemediationPlan(what="x", who="QM", when="30 days", effort="LOW"),
    )


def test_critical_clause_tier_floor_and_weight(sample_clause_critical):
    """is_spof=True clauses are classified critical, floor MAJOR, weight 5."""
    assert get_criticality_tier(sample_clause_critical) == "critical"
    assert get_severity_floor(sample_clause_critical) == "MAJOR"
    assert get_weight(sample_clause_critical) == 5


def test_passing_clause_tier_floor_and_weight(sample_clause_passing):
    """§4.x context clauses are passing, no floor, weight 1."""
    assert get_criticality_tier(sample_clause_passing) == "passing"
    assert get_severity_floor(sample_clause_passing) is None
    assert get_weight(sample_clause_passing) == 1


def test_floor_escalates_observation_to_major_on_critical(sample_clause_critical):
    """Sprint I.B: floor escalates severity AND realigns score into the new band.
    The leaked debug marker '[severity floor applied …]' is NOT emitted into the
    user-facing finding anymore — that information now goes to server logs only.
    """
    gap = _make_gap("OBSERVATION")
    gap.score = 70  # in OBSERVATION band, contradicts MAJOR after floor
    result = _apply_severity_floor(gap, sample_clause_critical, evidence_list=[])
    assert result.severity == "MAJOR"
    # Marker MUST NOT leak into the visible finding text anymore.
    assert "severity floor applied" not in result.finding
    # Score MUST be realigned into the MAJOR band (0-29) so UI doesn't show
    # the contradiction "score 70 / MAJOR".
    assert result.score <= 29
    # Original finding text is preserved untouched.
    assert result.finding == "test"


def test_floor_does_not_apply_to_passing_clause(sample_clause_passing):
    gap = _make_gap("OBSERVATION")
    result = _apply_severity_floor(gap, sample_clause_passing, evidence_list=[])
    assert result.severity == "OBSERVATION"
    assert "severity floor applied" not in result.finding


def test_floor_never_downgrades_major(sample_clause_critical):
    """If LLM already says MAJOR, floor cannot lower it."""
    gap = _make_gap("MAJOR")
    result = _apply_severity_floor(gap, sample_clause_critical, evidence_list=[])
    assert result.severity == "MAJOR"


def test_floor_preserves_conformant_with_sources(sample_clause_critical):
    """CONFORMANT with at least one source must not be escalated."""
    gap = _make_gap("CONFORMANT", with_sources=True)
    result = _apply_severity_floor(gap, sample_clause_critical, evidence_list=[])
    assert result.severity == "CONFORMANT"


def test_expiry_relevant_detection(sample_clause_critical, sample_clause_passing):
    """Clauses about documented information / training are expiry-relevant."""
    # §7.5 documented information → expiry-relevant
    assert is_expiry_relevant(sample_clause_critical) is True
    # §4.1 context → not expiry-relevant
    assert is_expiry_relevant(sample_clause_passing) is False
