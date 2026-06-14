"""
Fast regression for partial-credit calibration (Opzione B, 2026-06-14).

Pins: un MAJOR derivante solo dall'assenza di documenti-di-sistema, ma con il
processo parzialmente evidenziato dagli atomic requirements, viene declassato a
MINOR; le assenze totali (o copertura sotto soglia) restano MAJOR; i verdetti
già ≤ MINOR non vengono toccati.
"""
from __future__ import annotations

from compliance.deep_verifier import _apply_partial_credit, PARTIAL_CREDIT_MIN_COVERAGE
from compliance.gap_analyzer import _calibrate_blob_severity
from compliance.schemas import ClauseGap, RequirementCheck, RemediationPlan, TraceabilityLink


def _src():
    return [TraceabilityLink(evidence_id="ev1", file_name="f.pdf", pages=[1],
                             excerpt="x", relevance_score=0.5)]


def _blob_gap(severity, checks, sources):
    return ClauseGap(
        clause_id="9001_8_2", clause_title="8.2", score=20, severity=severity,
        is_spof=False, finding="x", sources=sources,
        remediation=RemediationPlan(what="w", who="o", when="30d", effort="LOW"),
        requirement_checks=checks,
    )


def test_blob_major_with_evidence_downgraded():
    g = _calibrate_blob_severity(_blob_gap("MAJOR", [], _src()))
    assert g.severity == "MINOR" and g.score >= 35


def test_blob_major_without_evidence_stays_major():
    g = _calibrate_blob_severity(_blob_gap("MAJOR", [], []))
    assert g.severity == "MAJOR"


def test_blob_calibration_ignores_clauses_with_atomic_checks():
    # ha requirement_checks → gestita dal credito parziale, non da questa leva
    g = _calibrate_blob_severity(_blob_gap("MAJOR",
        [RequirementCheck(requirement_id="r", status="ABSENT")], _src()))
    assert g.severity == "MAJOR"


def test_blob_calibration_ignores_non_major():
    g = _calibrate_blob_severity(_blob_gap("MINOR", [], _src()))
    assert g.severity == "MINOR"


def _gap(severity, score, checks):
    return ClauseGap(
        clause_id="9001_8_4", clause_title="8.4", score=score, severity=severity,
        is_spof=True, finding="x", sources=[],
        remediation=RemediationPlan(what="w", who="o", when="30d", effort="LOW"),
        requirement_checks=[RequirementCheck(requirement_id=f"r{i}", status=s)
                            for i, s in enumerate(checks)],
    )


def test_major_with_present_requirements_downgraded_to_minor():
    g = _apply_partial_credit(_gap("MAJOR", 15, ["PRESENT", "PARTIAL", "PARTIAL", "ABSENT", "ABSENT", "ABSENT"]))
    assert g.severity == "MINOR"
    assert 30 <= g.score <= 59
    assert g.hedged is True


def test_total_absence_stays_major():
    g = _apply_partial_credit(_gap("MAJOR", 0, ["ABSENT", "ABSENT", "ABSENT", "ABSENT"]))
    assert g.severity == "MAJOR"


def test_below_coverage_threshold_stays_major():
    # 1 PARTIAL su 15 → coverage 0.033 < soglia (0.10), nessun PRESENT → MAJOR
    g = _apply_partial_credit(_gap("MAJOR", 10, ["PARTIAL"] + ["ABSENT"] * 14))
    assert g.severity == "MAJOR"


def test_single_partial_above_threshold_downgrades():
    # 1 PARTIAL su 4 → coverage 0.125 ≥ soglia (0.10) → MINOR
    g = _apply_partial_credit(_gap("MAJOR", 20, ["PARTIAL", "ABSENT", "ABSENT", "ABSENT"]))
    assert g.severity == "MINOR"


def test_any_present_always_downgrades():
    # 1 PRESENT anche con copertura bassa → MINOR (processo dimostrato)
    g = _apply_partial_credit(_gap("MAJOR", 0, ["PRESENT"] + ["ABSENT"] * 9))
    assert g.severity == "MINOR"
    assert PARTIAL_CREDIT_MIN_COVERAGE == 0.10


def test_score_responsive_to_coverage():
    low = _apply_partial_credit(_gap("MAJOR", 0, ["PRESENT", "ABSENT", "ABSENT", "ABSENT"]))      # cov .25
    high = _apply_partial_credit(_gap("MAJOR", 0, ["PRESENT", "PRESENT", "PRESENT", "ABSENT"]))   # cov .75
    assert high.score > low.score  # più copertura → score più alto


def test_non_major_untouched():
    g = _apply_partial_credit(_gap("MINOR", 50, ["PRESENT", "ABSENT"]))
    assert g.severity == "MINOR" and g.score == 50


def test_no_checks_untouched():
    g = ClauseGap(clause_id="9001_5_2", clause_title="5.2", score=0, severity="MAJOR",
                  is_spof=False, finding="absent", sources=[],
                  remediation=RemediationPlan(what="w", who="o", when="30d", effort="LOW"),
                  requirement_checks=[])
    assert _apply_partial_credit(g).severity == "MAJOR"
