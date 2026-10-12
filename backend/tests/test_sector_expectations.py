"""
Fast — Piano motore Fase 5 (SECTOR_EXPECTATIONS): aspettative di settore.

Pin: un'attività citata nei documenti del cliente fa attendere la sua
registrazione tipica; se manca è solo "da verificare" (mai NC); i termini brevi
non scattano dentro altre parole; i documenti esterni non attivano aspettative.
"""
from __future__ import annotations

from compliance import sector_expectations as SE


def _docs():
    return [
        {"filename": "RA1 Welding.docx", "content": "Substances: zinc-rich primer, cutting fluid. Lifting with the 5-tonne overhead crane."},
        {"filename": "Waste Carrier Licence.pdf", "content": "Hazardous waste carrier licence"},
        {"filename": "Manual.docx", "content": "We are thinking about the first aid kit."},
    ]


def test_activity_triggers_expectation_and_missing_record_is_to_verify():
    out = {r["profile"]: r for r in SE.evaluate(_docs(), lambda n: n.endswith("Licence.pdf"))}
    assert out["hazardous_substances"]["status"] == "TO_VERIFY"
    assert out["lifting"]["status"] == "TO_VERIFY"
    assert "waste" not in out, "un documento esterno non attiva l'aspettativa"


def test_record_present_is_consistent():
    docs = _docs() + [{"filename": "SDS cutting fluid.pdf", "content": "Safety data sheet. Section 1: identification"}]
    out = {r["profile"]: r for r in SE.evaluate(docs, lambda n: False)}
    assert out["hazardous_substances"]["status"] == "CONSISTENT"


def test_short_terms_need_word_boundaries():
    assert SE._hits(SE._fold("We are thinking about the first aid kit"), ["ink", "fir", "flt"]) == []
    assert SE._hits(SE._fold("Inks and FLTs"), ["ink", "flt"]) == ["ink", "flt"]


def test_attach_never_creates_a_nonconformity():
    from compliance.schemas import ClauseGap, NormGapReport, RemediationPlan
    gap = ClauseGap(clause_id="45001_8_1", clause_title="8.1", score=90, severity="CONFORMANT", is_spof=False,
                    finding="ok", sources=[], remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"))
    rep = NormGapReport(norm="ISO 45001:2018", overall_score=90, clauses=[gap], major_count=0, minor_count=0,
                        observation_count=0, conformant_count=1, spof_count=0)
    res = SE.evaluate(_docs(), lambda n: False)
    reports, checks = SE.attach([rep], res, {"ISO 45001:2018": {"45001_8_1": {}}})
    assert gap.severity == "CONFORMANT" and gap.to_verify and all(c["status"] == "TO_VERIFY" for c in checks)
