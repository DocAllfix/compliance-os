"""
Fast regression — raffinamenti Hardening 2026 sullo Stage B.

#2 copertura: _sample_long_doc prende testa+coda dei documenti molto lunghi (la
coda di un DVR lungo entra nella deep-verification).
#3 doc-selection: _select_documents dà priorità ai documenti TAGGATI dalla Phase 2
sulla clausola (più affidabili), poi citazioni Stage A, poi retrieval.
"""
from __future__ import annotations

from compliance.deep_verifier import _sample_long_doc, _select_documents, _norm_name, DEEP_MAX_DOCS
from compliance.schemas import ClauseGap, RemediationPlan, TraceabilityLink


# ── _sample_long_doc ─────────────────────────────────────────────────────────

def test_sample_short_doc_unchanged():
    assert _sample_long_doc("abc", 1000) == "abc"


def test_sample_long_doc_head_and_tail():
    txt = "HEADSTART" + "h" * 80_000 + "t" * 80_000 + "TAILEND"
    out = _sample_long_doc(txt, 60_000)
    assert out.startswith("HEADSTART")
    assert out.rstrip().endswith("TAILEND")
    assert "omitted middle" in out
    assert len(out) <= 60_000 + 80


# ── _select_documents ────────────────────────────────────────────────────────

def _gap(sources):
    return ClauseGap(
        clause_id="9001_8_4", clause_title="8.4", score=40, severity="MINOR",
        is_spof=False, finding="x", sources=sources,
        remediation=RemediationPlan(what="w", who="o", when="30d", effort="LOW"),
    )


def _src(fname):
    return TraceabilityLink(evidence_id="e", file_name=fname, pages=[1], excerpt="x", relevance_score=0.5)


def test_tagged_docs_take_priority():
    docs = {_norm_name("suppliers.pdf"): "x", _norm_name("stage_a_cite.pdf"): "y"}
    gap = _gap([_src("stage_a_cite.pdf")])
    chosen = _select_documents({"id": "9001_8_4"}, gap, docs, None,
                               tagged_docs=["suppliers.pdf"])
    assert chosen[0] == _norm_name("suppliers.pdf")  # taggato prima della citazione


def test_falls_back_to_stage_a_when_no_tagged():
    docs = {_norm_name("stage_a_cite.pdf"): "y"}
    gap = _gap([_src("stage_a_cite.pdf")])
    chosen = _select_documents({"id": "9001_8_4"}, gap, docs, None, tagged_docs=[])
    assert chosen == [_norm_name("stage_a_cite.pdf")]


def test_respects_max_docs_cap():
    docs = {_norm_name(f"d{i}.pdf"): "x" for i in range(10)}
    gap = _gap([])
    chosen = _select_documents({"id": "9001_8_4"}, gap, docs, None,
                               tagged_docs=[f"d{i}.pdf" for i in range(10)])
    assert len(chosen) == DEEP_MAX_DOCS


def test_absent_clause_no_tagged_no_sources_empty():
    chosen = _select_documents({"id": "9001_9_2"}, _gap([]), {_norm_name("x.pdf"): "y"},
                               None, tagged_docs=[])
    assert chosen == []  # nessun doc selezionabile → Stage B no-op → tiene Stage A
