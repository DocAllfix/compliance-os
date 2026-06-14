"""
Fast regression — Hardening 2026 problema #1 (instabilità clausole ar=0).

Principio: solo le clausole con checklist curata (`atomic_requirements`) possono
ricevere un verdetto ESTREMO (MAJOR/CONFORMANT). Le clausole periferiche (ar=0)
sono confinate nella banda media [OBSERVATION..MINOR] da _confine_peripheral_clause.
Questo preserva la spina dorsale (incl. 5.2/6.2 che sono 'standard' di tier ma
hanno atomic_requirements) e rimuove insieme instabilità e over-severità.
"""
from __future__ import annotations

from compliance.deep_verifier import should_deep_verify
from compliance.gap_analyzer import _confine_peripheral_clause
from compliance.schemas import ClauseGap, RemediationPlan


def _gap(severity, *, score=50, confidence=None, clause_id="9001_x_std", is_spof=False):
    return ClauseGap(
        clause_id=clause_id, clause_title="t", score=score, severity=severity,
        is_spof=is_spof, finding="x", sources=[],
        remediation=RemediationPlan(what="w", who="o", when="30d", effort="LOW"),
        confidence=confidence,
    )


# clausole sintetiche: tier deterministico (vedi clause_helpers) + presenza atomic
CL_STD_BARE = {"id": "9001_x_std", "title": "operational", "area": "Operation"}            # ar=0 standard
CL_PASSING_BARE = {"id": "9001_4_99", "title": "context item", "area": "Context"}          # ar=0 passing
CL_ATOMIC = {"id": "9001_x_at", "title": "core", "area": "Operation",                      # ar≥4
             "atomic_requirements": [{"id": "r1", "text": "x"}, {"id": "r2", "text": "y"}]}


def _clauses():
    return {c["id"]: c for c in (CL_STD_BARE, CL_PASSING_BARE, CL_ATOMIC)}


# ── _confine_peripheral_clause ───────────────────────────────────────────────

def test_bare_standard_major_to_minor():
    g = _confine_peripheral_clause(_gap("MAJOR", score=10, clause_id="9001_x_std"), _clauses())
    assert g.severity == "MINOR" and 30 <= g.score <= 59 and g.hedged


def test_bare_standard_major_without_sources_also_capped():
    # anche un'assenza vera su clausola periferica non diventa MAJOR
    g = _confine_peripheral_clause(_gap("MAJOR", score=0, clause_id="9001_x_std"), _clauses())
    assert g.severity == "MINOR"


def test_bare_passing_major_to_observation():
    g = _confine_peripheral_clause(_gap("MAJOR", score=20, clause_id="9001_4_99"), _clauses())
    assert g.severity == "OBSERVATION" and 60 <= g.score <= 84


def test_bare_conformant_to_observation():
    g = _confine_peripheral_clause(_gap("CONFORMANT", score=90, clause_id="9001_x_std"), _clauses())
    assert g.severity == "OBSERVATION" and 60 <= g.score <= 84


def test_bare_minor_unchanged():
    g = _confine_peripheral_clause(_gap("MINOR", score=45, clause_id="9001_x_std"), _clauses())
    assert g.severity == "MINOR" and g.score == 45


def test_bare_observation_unchanged():
    g = _confine_peripheral_clause(_gap("OBSERVATION", score=70, clause_id="9001_x_std"), _clauses())
    assert g.severity == "OBSERVATION"


def test_atomic_clause_major_preserved():
    # la spina dorsale curata mantiene il MAJOR
    g = _confine_peripheral_clause(_gap("MAJOR", score=0, clause_id="9001_x_at"), _clauses())
    assert g.severity == "MAJOR"


def test_atomic_clause_conformant_preserved():
    g = _confine_peripheral_clause(_gap("CONFORMANT", score=90, clause_id="9001_x_at"), _clauses())
    assert g.severity == "CONFORMANT"


# ── should_deep_verify (ripristinato: atomic OR critical OR confidence<0.6) ───

def test_atomic_clause_always_deep():
    assert should_deep_verify(CL_ATOMIC, _gap("MINOR", confidence=0.95)) is True


def test_bare_clause_highconf_skips_deep():
    assert should_deep_verify(CL_STD_BARE, _gap("MAJOR", confidence=0.95)) is False
    assert should_deep_verify(CL_STD_BARE, _gap("CONFORMANT", confidence=0.95)) is False


def test_bare_clause_lowconf_deep():
    assert should_deep_verify(CL_STD_BARE, _gap("MINOR", confidence=0.3)) is True
