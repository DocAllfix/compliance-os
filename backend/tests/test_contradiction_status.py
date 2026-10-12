"""
Fast — Piano motore Fase 2 (CONTRADICTION_STATUS): la violazione provata.

Pin: uno Stage B che dichiara CONTRADICTED viene accettato solo se le due
citazioni si ritrovano nei documenti forniti (cite-or-fail su entrambe);
altrimenti decade a PARTIAL. Le due fonti entrano nel rilievo. A interruttore
spento CONTRADICTED non vale come prova. Con le regole di gravità una
contraddizione verificata è una MINOR.
"""
from __future__ import annotations

import pytest

from compliance import severity_rules
from compliance.deep_verifier import _merge_verdict
from compliance.schemas import ClauseGap, RemediationPlan

CLAUSE = {"id": "9001_7_1_5", "title": "7.1.5", "atomic_requirements": [
    {"id": "9001_7_1_5.status", "text": "Instruments fit for use", "risk_if_missing": "MAJOR"}]}
DOCS = {"ims9 calibration register.xlsx": "Row 9: ID: CAL007 | Result: Passed | Next due: 2027-01-01",
        "nwc-2202.pdf": "[PAGE 1]\nCertificate NWC-2202. Result: FAILED. Instrument must not be used."}
NAMES = list(DOCS)


def _stage_a():
    return ClauseGap(clause_id="9001_7_1_5", clause_title="7.1.5", score=70, severity="OBSERVATION",
                     is_spof=False, finding="x", sources=[],
                     remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"))


def _data(counter_quote="Result: FAILED. Instrument must not be used"):
    return {"severity": "MINOR", "score": 40, "requirement_checks": [{
        "requirement_id": "9001_7_1_5.status", "status": "CONTRADICTED",
        "file_name": "IMS9 Calibration Register.xlsx", "evidence_quote": "ID: CAL007 | Result: Passed",
        "counter_file_name": "NWC-2202.pdf", "counter_quote": counter_quote}]}


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv("CONTRADICTION_STATUS", "1")


def test_verified_contradiction_keeps_both_sources(flag_on):
    g = _merge_verdict(CLAUSE, _stage_a(), _data(), NAMES, {}, DOCS)
    chk = g.requirement_checks[0]
    assert chk.status == "CONTRADICTED" and chk.counter_file_name == "NWC-2202.pdf"
    assert {s.file_name for s in g.sources} == {"IMS9 Calibration Register.xlsx", "NWC-2202.pdf"}
    g.deep_verified = True
    assert severity_rules.apply(g, CLAUSE).severity == "MINOR"


def test_unverifiable_counter_quote_falls_back_to_partial(flag_on):
    g = _merge_verdict(CLAUSE, _stage_a(), _data("Result: PASSED with margin"), NAMES, {}, DOCS)
    assert g.requirement_checks[0].status == "PARTIAL"


def test_flag_off_does_not_accept_contradiction(monkeypatch):
    monkeypatch.delenv("CONTRADICTION_STATUS", raising=False)
    monkeypatch.delenv("ENGINE_PHASE2", raising=False)
    g = _merge_verdict(CLAUSE, _stage_a(), _data(), NAMES, {}, DOCS)
    assert g.requirement_checks[0].status == "PARTIAL"
