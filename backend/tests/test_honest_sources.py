"""
Fast regression — Hardening 2026 problema #6 (fonti oneste sulle assenze).

Pin: un MAJOR senza alcun check PRESENT/PARTIAL non mostra fonti (i vicini semantici
irrilevanti vengono rimossi); le evidenze reali (PRESENT/PARTIAL) restano; i verdetti
non-MAJOR non vengono toccati.
"""
from __future__ import annotations

from compliance.gap_analyzer import _honest_sources
from compliance.schemas import ClauseGap, RemediationPlan, RequirementCheck, TraceabilityLink


def _src(n=1):
    return [TraceabilityLink(evidence_id=f"ev{i}", file_name=f"f{i}.pdf", pages=[1],
                             excerpt="x", relevance_score=0.5) for i in range(n)]


def _gap(severity, checks, sources):
    return ClauseGap(
        clause_id="9001_9_2", clause_title="9.2", score=0, severity=severity,
        is_spof=False, finding="nothing found", sources=sources,
        remediation=RemediationPlan(what="w", who="o", when="30d", effort="LOW"),
        requirement_checks=checks,
    )


def test_major_no_checks_clears_sources():
    g = _honest_sources(_gap("MAJOR", [], _src(3)))
    assert g.sources == []


def test_major_all_absent_clears_sources():
    checks = [RequirementCheck(requirement_id=f"r{i}", status="ABSENT") for i in range(4)]
    g = _honest_sources(_gap("MAJOR", checks, _src(2)))
    assert g.sources == []


def test_major_with_partial_keeps_sources():
    checks = [RequirementCheck(requirement_id="r1", status="PARTIAL"),
              RequirementCheck(requirement_id="r2", status="ABSENT")]
    g = _honest_sources(_gap("MAJOR", checks, _src(1)))
    assert len(g.sources) == 1


def test_minor_keeps_sources():
    g = _honest_sources(_gap("MINOR", [], _src(2)))
    assert len(g.sources) == 2


def test_conformant_keeps_sources():
    g = _honest_sources(_gap("CONFORMANT", [], _src(1)))
    assert len(g.sources) == 1
