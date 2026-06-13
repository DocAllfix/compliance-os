"""
Fast regression for Fase 6: corpus persistence + documents_override + chat
history block. Temp SQLite/filesystem, no LLM.
"""
from __future__ import annotations

import pytest

import modules.db_manager as dbm


@pytest.fixture
def temp_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(dbm, "DB_FILE", tmp_path / "c.db")
    monkeypatch.setattr(dbm, "CORPUS_DIR", tmp_path / "corpus")
    dbm.init_compliance_tables()
    conn = dbm.get_connection()
    conn.execute(
        "INSERT INTO compliance_analyses (id, user_id, company, result_json) "
        "VALUES ('an_c', 'alice', 'TestCo', '{}')"
    )
    conn.commit()
    conn.close()


def test_corpus_roundtrip(temp_corpus):
    docs = [
        {"filename": "Quality Policy.docx", "content": "[PAGE 1]\nWe are committed…"},
        {"filename": "Company KPIs 2026.xlsx", "content": '[SHEET "Targets"]\nT1 | 95%'},
        {"filename": "empty.txt", "content": "   "},  # scartato
    ]
    saved = dbm.save_analysis_corpus("an_c", docs)
    assert saved == 2

    loaded = dbm.load_analysis_corpus("an_c")
    assert len(loaded) == 2
    by_name = {d["filename"]: d["content"] for d in loaded}
    assert "[PAGE 1]" in by_name["Quality Policy.docx"]
    assert '[SHEET "Targets"]' in by_name["Company KPIs 2026.xlsx"]


def test_corpus_resave_replaces(temp_corpus):
    dbm.save_analysis_corpus("an_c", [{"filename": "a.txt", "content": "v1"}])
    dbm.save_analysis_corpus("an_c", [{"filename": "b.txt", "content": "v2"}])
    loaded = dbm.load_analysis_corpus("an_c")
    assert [d["filename"] for d in loaded] == ["b.txt"]


def test_load_missing_corpus_is_empty(temp_corpus):
    assert dbm.load_analysis_corpus("never_existed") == []


def test_pipeline_documents_override_skips_extraction(monkeypatch):
    """documents_override deve bypassare la Phase 1 (nessuna lettura ZIP)."""
    from compliance import pipeline as pl

    def _boom(*a, **k):
        raise AssertionError("Phase 1 extraction must not run with documents_override")
    monkeypatch.setattr(pl, "_extract_documents", _boom)

    # Stub delle fasi LLM per restare fast: evidence vuota → la pipeline
    # prosegue ma analyze_compliance riceve 0 cards; stubbiamo anche quello.
    monkeypatch.setattr(pl, "_extract_evidence", lambda docs, ctx, emit: "")

    captured = {}
    class _FakeResult:
        analysis_id = "an_fake"
        expiry_report = None
        executive_summary = None
        def model_dump(self): return {}
    def _fake_analyze(evidence_yaml, company_context, emitter=None, documents=None):
        captured["documents"] = documents
        return _FakeResult()
    monkeypatch.setattr(pl, "analyze_compliance", _fake_analyze)
    monkeypatch.setattr(pl, "generate_executive_summary", lambda r, evidence_yaml="": None)
    import modules.db_manager as dbm2
    monkeypatch.setattr(dbm2, "save_analysis_corpus", lambda aid, docs: len(docs))

    from compliance.schemas import CompanyContext
    ctx = CompanyContext(company_name="T", sector="Manufacturing",
                         employee_range="11-50", certified="no",
                         sites_count="1", norms=["ISO 9001:2015"])
    docs = [{"filename": "x.pdf", "content": "[PAGE 1]\nhello"}]
    outcome = pl.run_compliance_pipeline(
        zip_bytes=None, company_context=ctx, documents_override=docs,
    )
    assert outcome["success"] is True
    assert captured["documents"] == docs


def test_chat_history_block_rules():
    from api_server import _chat_history_block, ChatTurnIn

    assert _chat_history_block(None) == ""
    assert _chat_history_block([]) == ""

    msgs = [ChatTurnIn(role="user", content=f"q{i}") for i in range(10)]
    block = _chat_history_block(msgs)
    # solo gli ultimi 6 turni
    assert "q3" not in block and "q4" in block and "q9" in block
    assert "context only" in block
    assert block.rstrip().endswith("## Current question")
