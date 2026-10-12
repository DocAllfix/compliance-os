"""
Fast — Piano motore Fase 2 (SEVERITY_RULES): la gravità la decide Python sulle prove.

Pin delle regole (compliance/severity_rules.py):
  - verdetto del solo screening → mai NC, al massimo osservazione + "da verificare";
  - requisito non trovato ma non cercato in tutto il pacco → da verificare, non NC;
  - "deve" in parte → osservazione, MINOR solo se il requisito pesa MAJOR;
  - assenza verificata o contraddizione → MINOR;
  - processo assente in tutto il pacco su clausola critica → MAJOR;
  - spenta di default: nessun effetto.
"""
from __future__ import annotations

from compliance import severity_rules as R
from compliance.schemas import ClauseGap, RemediationPlan, RequirementCheck


def _clause(critical=False, reqs=("a", "b", "c"), heavy=("a",)):
    return {
        "id": "9001_9_3", "title": "9.3", "is_spof": critical,
        "criticality_tier": "critical" if critical else "standard",
        "atomic_requirements": [{"id": f"9001_9_3.{r}", "text": f"Requirement {r}",
                                 "risk_if_missing": "MAJOR" if r in heavy else "MINOR"} for r in reqs],
    }


def _gap(severity="MAJOR", checks=(), deep=True, sources=False, finding="No evidence of X. More text."):
    return ClauseGap(
        clause_id="9001_9_3", clause_title="9.3 Management review", score=20, severity=severity,
        is_spof=False, finding=finding, sources=[], deep_verified=deep,
        remediation=RemediationPlan(what="Establish X", who="QM", when="30 days", effort="LOW"),
        requirement_checks=[RequirementCheck(requirement_id=f"9001_9_3.{r}", status=s, searched=searched)
                            for r, s, searched in checks],
    )


def test_screening_only_verdict_is_never_a_nonconformity():
    g = R.apply(_gap("MAJOR", deep=False), _clause())
    assert g.severity == "OBSERVATION" and g.to_verify == ["No evidence of X."]
    assert 60 <= g.score <= 84 and not g.is_spof


def test_unsearched_absence_is_to_verify():
    g = R.apply(_gap("MAJOR", [("a", "PRESENT", False), ("b", "ABSENT", False), ("c", "PRESENT", False)]), _clause())
    assert g.severity == "OBSERVATION"
    assert g.to_verify == ["Requirement b"]


def test_partial_on_heavy_requirement_is_minor_else_observation():
    heavy = R.apply(_gap("MAJOR", [("a", "PARTIAL", False), ("b", "PRESENT", False), ("c", "PRESENT", False)]), _clause())
    light = R.apply(_gap("MAJOR", [("a", "PRESENT", False), ("b", "PARTIAL", False), ("c", "PRESENT", False)]), _clause())
    assert heavy.severity == "MINOR" and light.severity == "OBSERVATION"


def test_verified_absence_or_contradiction_is_minor():
    g = R.apply(_gap("OBSERVATION", [("a", "PRESENT", False), ("b", "ABSENT", True), ("c", "PRESENT", False)]), _clause())
    assert g.severity == "MINOR" and g.to_verify == []
    g = R.apply(_gap("CONFORMANT", [("a", "CONTRADICTED", False), ("b", "PRESENT", False), ("c", "PRESENT", False)]), _clause())
    assert g.severity == "MINOR"


def test_process_absent_everywhere_on_critical_clause_is_major():
    checks = [("a", "ABSENT", True), ("b", "ABSENT", True), ("c", "ABSENT", True)]
    assert R.apply(_gap("MINOR", checks), _clause(critical=True)).severity == "MAJOR"
    assert R.apply(_gap("MINOR", checks), _clause(critical=False)).severity == "MINOR"


def test_all_present_is_conformant():
    g = R.apply(_gap("MINOR", [("a", "PRESENT", False), ("b", "PRESENT", False), ("c", "PRESENT", False)]), _clause())
    assert g.severity == "CONFORMANT" and g.score >= 85


def test_flag_off_by_default(monkeypatch):
    from compliance import features
    for v in ("SEVERITY_RULES", "ENGINE_PHASE2"):
        monkeypatch.delenv(v, raising=False)
    assert not features.on("SEVERITY_RULES")
    monkeypatch.setenv("ENGINE_PHASE2", "1")
    assert features.on("SEVERITY_RULES")


def _v2_clause():
    return {"id": "9001_9_3", "title": "9.3", "criticality_tier": "standard", "atomic_requirements": [
        {"id": "9001_9_3.r1", "text": "Minutes are retained", "source": "norm", "object": "record", "max_severity": "MINOR"},
        {"id": "9001_9_3.r2", "text": "Inputs considered", "source": "norm", "object": "process", "max_severity": "OBSERVATION"},
        {"id": "9001_9_3.r3", "text": "Leadership shown", "source": "norm", "object": "behaviour", "max_severity": "TO_VERIFY"},
        {"id": "9001_9_3.gp", "text": "Documented MR procedure", "source": "good_practice", "max_severity": "OBSERVATION"}]}


def _v2_gap(statuses):
    return ClauseGap(clause_id="9001_9_3", clause_title="9.3", score=20, severity="MAJOR", is_spof=False,
                     finding="x", sources=[], deep_verified=True,
                     remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"),
                     requirement_checks=[RequirementCheck(requirement_id=f"9001_9_3.{r}", status=s, searched=srch)
                                         for r, s, srch in statuses])


def test_v2_caps_and_good_practice():
    ok = [("r1", "PRESENT", False), ("r2", "PRESENT", False), ("r3", "PRESENT", False)]
    # una buona pratica assente non toglie la conformità
    assert R.apply(_v2_gap(ok + [("gp", "ABSENT", True)]), _v2_clause()).severity == "CONFORMANT"
    # assenza verificata di un obbligo con tetto osservazione → osservazione
    g = R.apply(_v2_gap([("r1", "PRESENT", False), ("r2", "ABSENT", True), ("r3", "PRESENT", False)]), _v2_clause())
    assert g.severity == "OBSERVATION"
    # un comportamento non dimostrabile non diventa mai NC: solo da verificare
    g = R.apply(_v2_gap([("r1", "PRESENT", False), ("r2", "PRESENT", False), ("r3", "ABSENT", True)]), _v2_clause())
    assert g.severity == "OBSERVATION" and g.to_verify == ["Leadership shown"]
    # registrazione richiesta assente e verificata → MINOR; parziale su registrazione → MINOR
    assert R.apply(_v2_gap([("r1", "ABSENT", True), ("r2", "PRESENT", False)]), _v2_clause()).severity == "MINOR"
    assert R.apply(_v2_gap([("r1", "PARTIAL", False), ("r2", "PRESENT", False)]), _v2_clause()).severity == "MINOR"
    assert R.apply(_v2_gap([("r1", "PRESENT", False), ("r2", "PARTIAL", False)]), _v2_clause()).severity == "OBSERVATION"


def test_strength_only_marks_good_practice(monkeypatch):
    # KB_STRENGTH: la KB resta quella attuale; ciò che il registro norma+checklist classifica
    # come buona pratica smette di valere da obbligo (resta un'opportunità di miglioramento).
    from compliance import kb_v2
    monkeypatch.setattr(kb_v2, "_DATA", {"9001_10_2": {"atomic_requirements": [
        {"id": "9001_10_2.capa.procedure", "source": "good_practice", "max_severity": "OBSERVATION"}]}})
    clauses = {"9001_10_2": {"id": "9001_10_2", "title": "10.2", "criticality_tier": "standard", "atomic_requirements": [
        {"id": "9001_10_2.capa.procedure", "text": "Documented CAPA procedure", "risk_if_missing": "MAJOR"},
        {"id": "9001_10_2.log", "text": "Nonconformity log retained", "risk_if_missing": "MAJOR"}]}}
    marked = kb_v2.annotate(clauses)
    reqs = {r["id"]: r for r in marked["9001_10_2"]["atomic_requirements"]}
    assert reqs["9001_10_2.capa.procedure"]["source"] == "good_practice" and "source" not in reqs["9001_10_2.log"]
    assert "source" not in clauses["9001_10_2"]["atomic_requirements"][0], "la KB originale non si tocca"

    def gap():
        return ClauseGap(clause_id="9001_10_2", clause_title="10.2", score=40, severity="MINOR", is_spof=False,
                         finding="x", sources=[], deep_verified=True,
                         remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"),
                         requirement_checks=[
                             RequirementCheck(requirement_id="9001_10_2.capa.procedure", status="ABSENT", searched=True),
                             RequirementCheck(requirement_id="9001_10_2.log", status="PRESENT")])
    assert R.apply(gap(), clauses["9001_10_2"]).severity == "MINOR"
    g = R.apply(gap(), marked["9001_10_2"])
    assert g.severity == "CONFORMANT" and "opportunity for improvement" in g.hedge_note


def test_point_to_verify_is_the_open_point_not_the_praise():
    # banco 12/10: "Organisational roles are clearly described" finiva tra i punti da verificare
    g = ClauseGap(clause_id="9001_5_3", clause_title="5.3 Roles", score=50, severity="MINOR", is_spof=False,
                  finding="Roles and reporting lines are clearly described in the manual. However, job descriptions "
                          "are referenced but not included.", sources=[],
                  remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"))
    out = R.apply(g, {"id": "9001_5_3"})
    assert out.severity == "OBSERVATION" and out.to_verify == ["Job descriptions are referenced but not included"]
