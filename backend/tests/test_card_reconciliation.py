"""
Fast regression — Hardening 2026 problema #2 (perdita silenziosa card Phase 2).

Pin: se un batch torna con N-1 card su N doc, il documento scoperto viene
ri-tentato in isolamento; se il retry lo recupera la card è reale, altrimenti
riceve una card sintetica per-doc. Nessun documento sparisce dalla Phase 2.
"""
from __future__ import annotations

import compliance.pipeline as P
from compliance.gap_analyzer import _parse_evidence_yaml
from compliance.schemas import CompanyContext


def _card_yaml(idx: int, filename: str, readable: bool = True) -> str:
    return (
        f"# ── DOC {idx} ──\n"
        f'evidence_id: "ev_{idx:03d}"\n'
        f'file_name: "{filename}"\n'
        f"readable: {str(readable).lower()}\n"
        f'doc_type: "other"\n'
        f'iso_clause_primary: ""\n'
        f"iso_clauses_secondary: []\n"
        f"gap_signal: false\n"
        f"summary: |\n  ok\n"
        f"excerpts: []\n"
        f"confidence: 0.5\n"
    )


def _ctx():
    return CompanyContext(company_name="T", sector="s", employee_range="1-9",
                          certified="no", sites_count="1", norms=["ISO 9001:2015"])


def _docs(n):
    return [{"filename": f"doc{i}.pdf", "content": f"text {i}"} for i in range(n)]


def _install_fake_llm(monkeypatch, *, drop_in_full=True, recover_on_retry=True):
    """Mock _call_llm_for_batch: salta 'doc_DROP.pdf' nel batch pieno; lo restituisce
    (o no) quando ri-tentato isolato."""
    def fake(azure_client, system_prompt, batch_docs, batch_idx, total_batches):
        is_full = len(batch_docs) > 1
        parts = []
        for i, d in enumerate(batch_docs, 1):
            if is_full and drop_in_full and d["filename"] == "doc_DROP.pdf":
                continue  # simula card persa nel batch pieno
            if (not is_full) and (not recover_on_retry) and d["filename"] == "doc_DROP.pdf":
                continue  # il retry isolato fallisce anch'esso
            parts.append(_card_yaml(i, d["filename"]))
        return "\n".join(parts)
    monkeypatch.setattr(P, "_build_evidence_azure_client", lambda: object())
    monkeypatch.setattr(P, "_call_llm_for_batch", fake)


def test_dropped_card_recovered_by_retry(monkeypatch):
    _install_fake_llm(monkeypatch, drop_in_full=True, recover_on_retry=True)
    docs = _docs(4) + [{"filename": "doc_DROP.pdf", "content": "x"}]
    yaml = P._extract_evidence(docs, _ctx(), lambda *a, **k: None)
    cards = _parse_evidence_yaml(yaml)
    by_name = {(c.get("file_name") or "").split("/")[-1]: c for c in cards}
    assert "doc_DROP.pdf" in by_name, "il doc scoperto deve essere recuperato dal retry"
    assert by_name["doc_DROP.pdf"].get("readable") is True
    assert len(cards) == 5  # nessun documento perso


def test_dropped_card_falls_back_to_synthetic(monkeypatch):
    _install_fake_llm(monkeypatch, drop_in_full=True, recover_on_retry=False)
    docs = _docs(4) + [{"filename": "doc_DROP.pdf", "content": "x"}]
    yaml = P._extract_evidence(docs, _ctx(), lambda *a, **k: None)
    cards = _parse_evidence_yaml(yaml)
    by_name = {(c.get("file_name") or "").split("/")[-1]: c for c in cards}
    assert "doc_DROP.pdf" in by_name, "se il retry fallisce, serve la card sintetica"
    assert by_name["doc_DROP.pdf"].get("readable") is False
    assert len(cards) == 5  # comunque nessun documento perso


def test_no_missing_no_retry(monkeypatch):
    calls = {"n": 0}
    def fake(azure_client, system_prompt, batch_docs, batch_idx, total_batches):
        calls["n"] += 1
        return "\n".join(_card_yaml(i, d["filename"]) for i, d in enumerate(batch_docs, 1))
    monkeypatch.setattr(P, "_build_evidence_azure_client", lambda: object())
    monkeypatch.setattr(P, "_call_llm_for_batch", fake)
    docs = _docs(5)
    yaml = P._extract_evidence(docs, _ctx(), lambda *a, **k: None)
    assert len(_parse_evidence_yaml(yaml)) == 5
    assert calls["n"] == 1  # un solo batch, nessun retry


# ── unit: _docs_without_card ─────────────────────────────────────────────────

def test_docs_without_card_basename_match():
    docs = [{"filename": "a/x.pdf"}, {"filename": "b/y.pdf"}]
    y = _card_yaml(1, "x.pdf")
    missing = P._docs_without_card(docs, y)
    assert [d["filename"] for d in missing] == ["b/y.pdf"]


def test_docs_without_card_basename_collision_multiset():
    # due doc stesso basename, una sola card → uno mancante
    docs = [{"filename": "a/dvr.pdf"}, {"filename": "b/dvr.pdf"}]
    y = _card_yaml(1, "dvr.pdf")
    missing = P._docs_without_card(docs, y)
    assert len(missing) == 1


def test_renumber_preserves_dated_evidence_id():
    # root cause #2: uno slug con DATA (trattini) non deve corrompere lo YAML
    # (prima: ev_002_dvr_rev02_2024-09-26 → ev_..._2024"-09-26" → card persa)
    y = ('# ── DOC 1 ──\n'
         'evidence_id: "ev_009_dvr_rev02_2024-09-26"\n'
         'file_name: "x/DVR.docx"\nreadable: true\ndoc_type: "risk_assessment"\n'
         'iso_clause_primary: ""\niso_clauses_secondary: []\ngap_signal: false\n'
         'summary: |\n  ok\nexcerpts: []\nconfidence: 0.5\n')
    out = P._renumber_evidence_ids(P._renumber_doc_markers(y))
    cards = _parse_evidence_yaml(out)
    assert len(cards) == 1 and cards[0].get("readable") is True
    assert cards[0].get("file_name", "").endswith("DVR.docx")
