"""
Fast regression — DMS unificato: ingest analisi → DMS (cartella = azienda).

Pin: un'analisi popola una cartella-azienda nel DMS riusando il testo già estratto
(no re-OCR), classifica engine dalle card, collega la provenienza; la ri-analisi
versiona i file cambiati e aggiunge i nuovi; i file identici vengono dedupati.
DB + storage redirezionati a tmp_path (niente effetti sul DB reale).
"""
from __future__ import annotations

import io
import zipfile

import pytest

import modules.db_manager as dbm
import modules.dms_manager as dms
import modules.dms_ingest as ingest


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(dbm, "DB_FILE", db_file)
    monkeypatch.setattr(dbm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dbm, "CORPUS_DIR", tmp_path / "corpus")
    monkeypatch.setattr(dms, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dms, "DMS_DIR", tmp_path / "dms")
    (tmp_path / "dms").mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus").mkdir(parents=True, exist_ok=True)
    dbm.init_compliance_tables()
    dms.init_dms_tables()
    return tmp_path


def _zip(files: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return b.getvalue()


_CARD = (
    '# ── DOC 1 ──\nevidence_id: "ev_001"\nfile_name: "ACME/policy.pdf"\n'
    'readable: true\ndoc_type: "policy"\niso_clause_primary: ""\n'
    'iso_clauses_secondary: []\ngap_signal: false\nsummary: |\n  x\n'
    'excerpts: []\nconfidence: 0.5\n'
)


def test_ingest_creates_company_folder_and_docs(temp_env):
    aid = "analysis_test_1"
    dbm.save_analysis_corpus(aid, [
        {"filename": "ACME/policy.pdf", "content": "Quality policy text"},
        {"filename": "ACME/dvr.pdf", "content": "Risk assessment text"},
    ])
    zip_bytes = _zip({"ACME/policy.pdf": b"PDFBYTES1", "ACME/dvr.pdf": b"PDFBYTES2"})

    stats = ingest.ingest_analysis("alice", "ACME", zip_bytes, aid, _CARD)
    assert stats["created"] == 2

    folders = dms.list_all_folders("alice")
    assert len(folders) == 1 and folders[0]["name"] == "ACME"
    fid = folders[0]["id"]
    docs = {d["filename"]: d for d in dms.list_documents("alice", fid)}
    assert set(docs) == {"policy.pdf", "dvr.pdf"}
    # testo riusato (no re-OCR)
    assert dms.read_document_text(docs["policy.pdf"]["id"]) == "Quality policy text"
    # doc_type engine dalla card
    assert docs["policy.pdf"]["doc_type"] == "policy"
    assert docs["policy.pdf"]["doc_type_source"] == "engine"
    # provenance link su analysis_documents
    linked = [d for d in dbm.load_analysis_corpus(aid) if d.get("document_id")]
    assert len(linked) == 2


def test_reanalysis_versions_changed_and_adds_new(temp_env):
    aid1 = "a_v1"
    dbm.save_analysis_corpus(aid1, [{"filename": "ACME/policy.pdf", "content": "v1 text"}])
    ingest.ingest_analysis("alice", "ACME", _zip({"ACME/policy.pdf": b"V1"}), aid1, "")
    fid = dms.list_all_folders("alice")[0]["id"]
    doc_id = dms.list_documents("alice", fid)[0]["id"]
    assert dms.get_document(doc_id)["current_version"] == 1

    aid2 = "a_v2"
    dbm.save_analysis_corpus(aid2, [
        {"filename": "ACME/policy.pdf", "content": "v2 text"},
        {"filename": "ACME/new.pdf", "content": "new doc"},
    ])
    stats = ingest.ingest_analysis(
        "alice", "ACME",
        _zip({"ACME/policy.pdf": b"V2CHANGED", "ACME/new.pdf": b"NEW"}), aid2, "",
    )
    # stessa cartella riusata, policy versionata, new creato
    assert len(dms.list_all_folders("alice")) == 1
    assert stats["versioned"] == 1 and stats["created"] == 1
    assert dms.get_document(doc_id)["current_version"] == 2
    assert dms.read_document_text(doc_id) == "v2 text"


def test_identical_file_is_deduped(temp_env):
    aid1 = "d1"
    dbm.save_analysis_corpus(aid1, [{"filename": "X/f.pdf", "content": "t"}])
    ingest.ingest_analysis("alice", "X", _zip({"X/f.pdf": b"SAME"}), aid1, "")
    aid2 = "d2"
    dbm.save_analysis_corpus(aid2, [{"filename": "X/f.pdf", "content": "t"}])
    stats = ingest.ingest_analysis("alice", "X", _zip({"X/f.pdf": b"SAME"}), aid2, "")
    assert stats["versioned"] == 0 and stats["skipped"] >= 1
    assert dms.get_document(dms.list_documents("alice", dms.list_all_folders("alice")[0]["id"])[0]["id"])["current_version"] == 1


def test_empty_company_name_fallback_folder(temp_env):
    aid = "e1"
    dbm.save_analysis_corpus(aid, [{"filename": "f.pdf", "content": "txt"}])
    ingest.ingest_analysis("alice", "", _zip({"f.pdf": b"B"}), aid, "")
    folders = dms.list_all_folders("alice")
    assert len(folders) == 1 and folders[0]["name"].startswith("Imported ")
