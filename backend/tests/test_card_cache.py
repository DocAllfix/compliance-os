"""
Fast regression — Piano motore Fase 0: schede di evidenza salvate e riusate.

Pin:
  - spenta di default: comportamento identico a prima (nessuna scrittura);
  - accesa: seconda analisi dello stesso pacco → zero chiamate al modello e
    schede identiche; cambia un documento → si rischeda solo quello;
  - cambia la domanda al modello (contesto aziendale, deployment) → niente riuso;
  - le schede sintetiche di fallback e i nomi file ambigui non si salvano mai.
"""
from __future__ import annotations

import pytest

import compliance.pipeline as P
from compliance import card_cache
from compliance.gap_analyzer import _parse_evidence_yaml
from compliance.schemas import CompanyContext


def _card_yaml(idx: int, filename: str, summary: str) -> str:
    return (
        f"# ── DOC {idx} ──\n"
        f'evidence_id: "ev_{idx:03d}"\n'
        f'file_name: "{filename}"\n'
        f"readable: true\n"
        f'doc_type: "other"\n'
        f'iso_clause_primary: ""\n'
        f"iso_clauses_secondary: []\n"
        f"gap_signal: false\n"
        f"summary: |\n  {summary}\n"
        f"excerpts: []\n"
        f"confidence: 0.5\n"
    )


def _ctx(name: str = "T"):
    return CompanyContext(company_name=name, sector="s", employee_range="1-9",
                          certified="no", sites_count="1", norms=["ISO 9001:2015"])


def _docs(n):
    return [{"filename": f"folder/doc{i}.pdf", "content": f"text {i}"} for i in range(n)]


@pytest.fixture
def fake_llm(monkeypatch):
    """LLM finto: la scheda riporta un contatore, così si vede se è stata rigenerata."""
    state = {"calls": 0, "docs": 0, "fail": set()}

    def fake(azure_client, system_prompt, batch_docs, batch_idx, total_batches):
        state["calls"] += 1
        state["docs"] += len(batch_docs)
        if any(d["filename"] in state["fail"] for d in batch_docs):
            return None   # batch fallito → schede sintetiche
        return "\n".join(_card_yaml(i, d["filename"], f"gen{state['calls']} {d['content']}")
                         for i, d in enumerate(batch_docs, 1))
    monkeypatch.setattr(P, "_build_evidence_azure_client", lambda: object())
    monkeypatch.setattr(P, "_call_llm_for_batch", fake)
    return state


@pytest.fixture
def cache_on(monkeypatch, tmp_path):
    monkeypatch.setenv("EVIDENCE_CARD_CACHE", "1")
    monkeypatch.setenv("EVIDENCE_CARD_CACHE_DIR", str(tmp_path))
    return tmp_path


def _summaries(yaml: str) -> dict:
    return {c["file_name"]: str(c.get("summary", "")).strip() for c in _parse_evidence_yaml(yaml)}


def _run(docs, ctx=None):
    return P._extract_evidence(docs, ctx or _ctx(), lambda *a, **k: None)


def test_off_by_default_regenerates_and_writes_nothing(fake_llm, monkeypatch, tmp_path):
    monkeypatch.delenv("EVIDENCE_CARD_CACHE", raising=False)
    monkeypatch.setenv("EVIDENCE_CARD_CACHE_DIR", str(tmp_path))
    docs = _docs(7)
    _run(docs)
    first = fake_llm["docs"]
    _run(docs)
    assert first == 7 and fake_llm["docs"] == 14
    assert not any(tmp_path.rglob("*.yaml"))


def test_second_run_reuses_every_card(fake_llm, cache_on):
    docs = _docs(7)
    y1 = _run(docs)
    calls = fake_llm["calls"]
    y2 = _run(docs)
    assert fake_llm["calls"] == calls, "seconda analisi: nessuna chiamata al modello"
    assert _summaries(y1) == _summaries(y2)
    assert len(_parse_evidence_yaml(y2)) == 7


def test_only_changed_document_is_regenerated(fake_llm, cache_on):
    docs = _docs(7)
    _run(docs)
    before = fake_llm["docs"]
    docs[3] = {"filename": "folder/doc3.pdf", "content": "text 3 revised"}
    y = _run(docs)
    assert fake_llm["docs"] - before == 1
    assert "text 3 revised" in _summaries(y)["folder/doc3.pdf"]


def test_different_company_context_is_a_miss(fake_llm, cache_on):
    docs = _docs(3)
    _run(docs, _ctx("A"))
    before = fake_llm["docs"]
    _run(docs, _ctx("B"))
    assert fake_llm["docs"] - before == 3


def test_synthetic_cards_are_never_cached(fake_llm, cache_on):
    docs = _docs(2)
    fake_llm["fail"] = {"folder/doc0.pdf"}
    _run(docs)
    fake_llm["fail"] = set()
    before = fake_llm["docs"]
    y = _run(docs)
    assert fake_llm["docs"] - before >= 1, "il documento fallito va ritentato"
    assert all(c.get("readable") is True for c in _parse_evidence_yaml(y))


def test_ambiguous_basenames_are_not_cached(fake_llm, cache_on):
    docs = [{"filename": "a/same.pdf", "content": "one"},
            {"filename": "b/same.pdf", "content": "two"}]
    _run(docs)
    assert not any(cache_on.rglob("*.yaml"))


def test_key_depends_on_deployment_prompt_name_and_text():
    base = card_cache.key_for("sys", "gpt-4.1-mini", "x/doc.pdf", "text")
    assert base == card_cache.key_for("sys", "gpt-4.1-mini", "y/DOC.pdf", "text")  # basename
    assert base != card_cache.key_for("sys", "other-deployment", "x/doc.pdf", "text")
    assert base != card_cache.key_for("sys2", "gpt-4.1-mini", "x/doc.pdf", "text")
    assert base != card_cache.key_for("sys", "gpt-4.1-mini", "x/other.pdf", "text")
    assert base != card_cache.key_for("sys", "gpt-4.1-mini", "x/doc.pdf", "text!")
