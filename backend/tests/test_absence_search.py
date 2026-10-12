"""
Fast — Piano motore Fase 2 (ABSENCE_SEARCH): prima di dire "non c'è", cercare in tutto il pacco.

Pin:
  - un requisito ABSENT che esiste in un foglio di un altro documento viene
    trovato (ricerca a parole EN/IT) e diventa PRESENT con la fonte;
  - NOT_FOUND → resta ABSENT ma searched=True con la nota della ricerca (prova);
  - citazione non verificabile o errore del modello → resta ABSENT non cercato
    (= da verificare): un errore non diventa mai un'accusa.
"""
from __future__ import annotations

import json

import pytest

from compliance import absence_search as A
from compliance.schemas import ClauseGap, RemediationPlan, RequirementCheck

CLAUSE = {"id": "9001_4_2", "title": "4.2 Interested parties", "atomic_requirements": [
    {"id": "9001_4_2.register", "text": "Interested parties and their requirements are identified.",
     "verification_hint": "Interested parties register"}]}

DOCS = {
    "manual.docx": "Quality manual. Scope: fabrication of steel. " * 20,
    "ims3 context register.xlsx": '[SHEET "Context"]\nRow 2: Issue: steel prices\n\n'
                                  '[SHEET "Interested Parties"]\nColumns: Interested party | Needs and expectations\n'
                                  "Row 2: Interested party: Customers | Needs and expectations: On-time delivery\n",
}


@pytest.fixture(autouse=True)
def _terms(monkeypatch):
    monkeypatch.setattr(A, "_TERMS", {"9001_4_2.register": {"en": ["interested parties register", "needs and expectations"],
                                                             "it": ["parti interessate"]}})
    A._index_cache.clear()


def _gap():
    return ClauseGap(clause_id="9001_4_2", clause_title="4.2", score=20, severity="MAJOR", is_spof=False,
                     finding="No register.", sources=[], deep_verified=True,
                     remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"),
                     requirement_checks=[RequirementCheck(requirement_id="9001_4_2.register", status="ABSENT")])


def _llm(answer):
    calls = []

    def call(messages, max_tokens):
        calls.append(messages[0]["content"])
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer)
    call.calls = calls
    return call


def test_found_in_another_document_sheet():
    llm = _llm({"status": "FOUND", "passage": "P1", "quote": "Interested party: Customers | Needs and expectations: On-time delivery"})
    g = A.resolve_absences(_gap(), CLAUSE, DOCS, None, llm, {})
    chk = g.requirement_checks[0]
    assert "Interested Parties" in llm.calls[0] and "ims3 context register.xlsx" in llm.calls[0]
    assert chk.status == "PRESENT" and chk.file_name == "ims3 context register.xlsx" and chk.searched
    assert g.sources and g.sources[0].file_name == "ims3 context register.xlsx"


def test_not_found_is_a_recorded_search():
    g = A.resolve_absences(_gap(), CLAUSE, DOCS, None, _llm({"status": "NOT_FOUND"}), {})
    chk = g.requirement_checks[0]
    assert chk.status == "ABSENT" and chk.searched and "Searched all 2 documents" in chk.search_note


def test_unverifiable_quote_stays_to_verify():
    g = A.resolve_absences(_gap(), CLAUSE, DOCS, None, _llm({"status": "FOUND", "passage": "P1", "quote": "text that is not there at all"}), {})
    chk = g.requirement_checks[0]
    assert chk.status == "ABSENT" and not chk.searched


def test_llm_error_stays_to_verify():
    g = A.resolve_absences(_gap(), CLAUSE, DOCS, None, _llm(RuntimeError("429")), {})
    assert not g.requirement_checks[0].searched


def test_rules_turn_verified_absence_into_minor_and_unsearched_into_to_verify():
    from compliance import severity_rules
    searched = A.resolve_absences(_gap(), CLAUSE, DOCS, None, _llm({"status": "NOT_FOUND"}), {})
    assert severity_rules.apply(searched, CLAUSE).severity == "MINOR"
    unsearched = A.resolve_absences(_gap(), CLAUSE, DOCS, None, _llm(RuntimeError("x")), {})
    g = severity_rules.apply(unsearched, CLAUSE)
    assert g.severity == "OBSERVATION" and g.to_verify
