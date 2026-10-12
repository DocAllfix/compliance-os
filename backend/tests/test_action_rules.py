"""
Fast — Piano motore Fase 2 (ACTIONS_FROM_STATES): il verbo dell'azione dagli stati.

Pin: conforme → "Maintain…" (mai "establish"); da verificare → "Verify…";
parziale → "Complete…"; contraddetto → "Correct the inconsistency…" + azione
correttiva; assente verificato → "Establish…". Sulle osservazioni non restano
correzioni/azioni correttive del template.
"""
from __future__ import annotations

from compliance import action_rules as AR
from compliance.schemas import ClauseGap, RemediationPlan, RequirementCheck

CLAUSE = {"id": "14001_9_1", "title": "9.1", "atomic_requirements": [
    {"id": "14001_9_1.kpi", "text": "Environmental KPIs are defined"},
    {"id": "14001_9_1.cal", "text": "Monitoring equipment is calibrated"}]}


def _gap(severity, checks=(), to_verify=()):
    return ClauseGap(clause_id="14001_9_1", clause_title="9.1 Monitoring, measurement, analysis and evaluation",
                     score=70, severity=severity, is_spof=False, finding="x", sources=[],
                     to_verify=list(to_verify),
                     remediation=RemediationPlan(what="Define environmental KPIs and monitoring frequency.",
                                                 who="EM", when="90 days", effort="LOW",
                                                 correction="c", corrective_action="ca"),
                     requirement_checks=[RequirementCheck(**c) for c in checks])


def test_conformant_is_maintain_never_establish():
    g = AR.apply(_gap("CONFORMANT"), CLAUSE)
    assert g.remediation.what.startswith("Maintain") and "Define" not in g.remediation.what
    assert g.remediation.correction is None and g.remediation.corrective_action is None


def test_to_verify_and_partial():
    g = AR.apply(_gap("OBSERVATION", [dict(requirement_id="14001_9_1.kpi", status="PARTIAL", note="no targets")],
                      to_verify=["Monitoring equipment is calibrated"]), CLAUSE)
    w = g.remediation.what
    assert "Complete: Environmental KPIs are defined — no targets." in w and "Verify that" in w
    assert g.remediation.correction is None


def test_contradiction_and_verified_absence():
    g = AR.apply(_gap("MINOR", [
        dict(requirement_id="14001_9_1.cal", status="CONTRADICTED", file_name="a/IMS9 Register.xlsx",
             counter_file_name="NWC-2202.pdf"),
        dict(requirement_id="14001_9_1.kpi", status="ABSENT", searched=True)]), CLAUSE)
    w = g.remediation.what
    assert w.startswith("Correct the inconsistency on: Monitoring equipment is calibrated (IMS9 Register.xlsx vs NWC-2202.pdf).")
    assert "Establish: Environmental KPIs are defined." in w
    assert g.remediation.corrective_action == "ca"


def test_screening_only_observation_never_keeps_template_establish():
    g = _gap("OBSERVATION")
    g.finding = "Environmental KPIs are defined. However, targets are not set for water use."
    AR.apply(g, CLAUSE)
    assert g.remediation.what.startswith("Improve the arrangements for monitoring")
    assert "targets are not set for water use" in g.remediation.what and "Define" not in g.remediation.what


def test_finding_names_the_specific_defects():
    g = _gap("MINOR", [
        dict(requirement_id="14001_9_1.cal", status="CONTRADICTED", file_name="IMS9 Register.xlsx",
             evidence_quote="CAL-02 Passed", counter_file_name="NWC-2202.pdf", counter_quote="FAILED"),
        dict(requirement_id="14001_9_1.kpi", status="PARTIAL", note="trainer field blank on 8.2.24 sheet")])
    g.finding = "Monitoring is partly in place."
    AR.apply_all([g], {"14001_9_1": CLAUSE})
    assert "Details: Monitoring equipment is calibrated — contradicted" in g.finding
    assert "trainer field blank on 8.2.24 sheet" in g.finding


def test_own_record_findings_read_as_sentences():
    # Fase 4: il rilievo e' gia' una frase compiuta; "Establish: <frase>" non si legge
    g = AR.apply(_gap("MINOR", [
        dict(requirement_id="14001_9_1.self.1", status="ABSENT", searched=True,
             requirement_text="SOP5.docx says the organisation keeps committee minutes, but no such record is in the pack"),
        dict(requirement_id="14001_9_1.self.2", status="CONTRADICTED",
             requirement_text="Register.xlsx shows NWC-2202 as 'Pass', but the record says it failed")]), CLAUSE)
    w = g.remediation.what
    assert "Establish:" not in w and "Provide the record, or bring the document that declares it into line" in w
    assert "Resolve the inconsistency in the organisation's own records: Register.xlsx shows NWC-2202" in w


def test_good_practice_is_a_suggestion_never_establish():
    clause = {"id": "14001_9_1", "title": "9.1", "atomic_requirements": [
        {"id": "14001_9_1.kpi", "text": "Environmental KPIs are defined"},
        {"id": "14001_9_1.status", "text": "A status field is kept current", "source": "good_practice"}]}
    g = AR.apply(_gap("OBSERVATION", [dict(requirement_id="14001_9_1.status", status="ABSENT", searched=True),
                                      dict(requirement_id="14001_9_1.kpi", status="PARTIAL", note="no targets")]), clause)
    w = g.remediation.what
    assert "Establish" not in w and "Consider, as good practice beyond the standard: A status field is kept current." in w
