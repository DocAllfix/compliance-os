"""
Fast regression for the DMS core (Fase C, PRD §1.2 / §1.3.2).

Pins: folder/document round-trip, versioning with sha256 dedup, version text
retrieval, scope resolution, soft-delete, and the anti-IDOR helpers
(_require_folder_access / _require_document_access) that protect every DMS
route. DB + binary storage redirected to tmp_path so nothing touches the real
audit.db or data/dms.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import modules.db_manager as dbm
import modules.dms_manager as dms
import api_deps


@pytest.fixture
def temp_dms(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(dbm, "DB_FILE", db_file)
    # Redirect DMS binary storage + the DATA_DIR used for relative paths.
    monkeypatch.setattr(dms, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dms, "DMS_DIR", tmp_path / "dms")
    (tmp_path / "dms").mkdir(parents=True, exist_ok=True)
    dbm.init_compliance_tables()
    dms.init_dms_tables()
    return tmp_path


def test_folder_round_trip(temp_dms):
    fid = dms.create_folder("alice", "Policies")
    f = dms.get_folder(fid)
    assert f and f["name"] == "Policies" and f["owner"] == "alice"
    assert [x["name"] for x in dms.list_all_folders("alice")] == ["Policies"]
    assert dms.rename_folder(fid, "QHSE Policies")
    assert dms.get_folder(fid)["name"] == "QHSE Policies"


def test_document_create_and_text(temp_dms):
    fid = dms.create_folder("alice", "Docs")
    res = dms.create_document(
        "alice", fid, "Quality Policy.pdf", b"%PDF data",
        "Quality policy full text", doc_type="policy", expiry_date="2027-12-31",
    )
    did = res["document_id"]
    doc = dms.get_document(did)
    assert doc["filename"] == "Quality Policy.pdf"
    assert doc["doc_type"] == "policy" and doc["expiry_date"] == "2027-12-31"
    assert doc["current_version"] == 1
    assert dms.read_document_text(did) == "Quality policy full text"
    raw, fname = dms.read_version_bytes(did)
    assert raw == b"%PDF data" and fname == "Quality Policy.pdf"


def test_versioning_and_sha_dedup(temp_dms):
    fid = dms.create_folder("alice", "Docs")
    did = dms.create_document("alice", fid, "p.pdf", b"v1", "text one")["document_id"]

    # identical bytes → dedup, no new version
    r = dms.add_version(did, b"v1", "text one")
    assert r["deduped"] is True and r["version"] == 1
    assert len(dms.get_document_versions(did)) == 1

    # new bytes → version 2, current pointer advances
    r2 = dms.add_version(did, b"v2", "text two", note="revised")
    assert r2["deduped"] is False and r2["version"] == 2
    assert dms.get_document(did)["current_version"] == 2
    assert dms.read_document_text(did) == "text two"
    assert dms.read_document_text(did, version=1) == "text one"
    assert len(dms.get_document_versions(did)) == 2


def test_manual_metadata_wins_over_backfill(temp_dms):
    fid = dms.create_folder("alice", "Docs")
    did = dms.create_document("alice", fid, "x.pdf", b"x", "t", doc_type="other")["document_id"]
    # manual PATCH sets source=manual
    assert dms.update_document_metadata(did, doc_type="policy", manual=True)
    assert dms.get_document(did)["doc_type_source"] == "manual"
    # engine backfill must NOT override a manual type
    assert dms.backfill_doc_type(did, "record") is False
    assert dms.get_document(did)["doc_type"] == "policy"


def test_scope_resolution_and_soft_delete(temp_dms):
    fa = dms.create_folder("alice", "A")
    fb = dms.create_folder("alice", "B")
    dms.create_document("alice", fa, "a1.pdf", b"a1", "alpha one")
    dms.create_document("alice", fb, "b1.pdf", b"b1", "bravo one")

    all_docs = dms.documents_for_scope("alice", scope="all")
    assert {d["filename"] for d in all_docs} == {"a1.pdf", "b1.pdf"}
    folder_docs = dms.documents_for_scope("alice", scope="folder", folder_id=fa)
    assert [d["filename"] for d in folder_docs] == ["a1.pdf"]

    # soft-delete folder A removes its doc from scope
    dms.soft_delete_folder(fa)
    remaining = dms.documents_for_scope("alice", scope="all")
    assert [d["filename"] for d in remaining] == ["b1.pdf"]


def test_owner_isolation_in_listing(temp_dms):
    fa = dms.create_folder("alice", "A")
    dms.create_document("alice", fa, "a.pdf", b"a", "alpha")
    dms.create_folder("bob", "B")
    assert [f["name"] for f in dms.list_all_folders("bob")] == ["B"]
    assert dms.list_all_documents("bob") == []


# ── anti-IDOR helpers (api_deps) ──────────────────────────────────────────────

def test_require_folder_access_blocks_other_user(temp_dms):
    fid = dms.create_folder("alice", "Private")
    # owner OK
    assert api_deps._require_folder_access(fid, {"username": "alice", "role": "member"})["id"] == fid
    # other user → 403
    with pytest.raises(HTTPException) as ei:
        api_deps._require_folder_access(fid, {"username": "bob", "role": "member"})
    assert ei.value.status_code == 403
    # admin bypass
    assert api_deps._require_folder_access(fid, {"username": "root", "role": "admin"})["id"] == fid
    # missing → 404
    with pytest.raises(HTTPException) as ei2:
        api_deps._require_folder_access(99999, {"username": "alice", "role": "member"})
    assert ei2.value.status_code == 404


def test_require_document_access_blocks_other_user(temp_dms):
    fid = dms.create_folder("alice", "Docs")
    did = dms.create_document("alice", fid, "d.pdf", b"d", "text")["document_id"]
    assert api_deps._require_document_access(did, {"username": "alice", "role": "member"})["id"] == did
    with pytest.raises(HTTPException) as ei:
        api_deps._require_document_access(did, {"username": "bob", "role": "member"})
    assert ei.value.status_code == 403


def test_register_and_pyramid(temp_dms):
    fid = dms.create_folder("alice", "All")
    dms.create_document("alice", fid, "QP.pdf", b"a", "t", doc_type="policy")
    dms.create_document("alice", fid, "Manual.pdf", b"b", "t", doc_type="quality_manual")
    dms.create_document("alice", fid, "Audit.pdf", b"c", "t", doc_type="audit_report")
    dms.create_document("alice", fid, "Cert.pdf", b"d", "t", doc_type="certificate")

    reg = dms.build_register("alice")
    tiers = {r["filename"]: r["tier"] for r in reg}
    assert tiers["QP.pdf"] == "Policy"
    assert tiers["Manual.pdf"] == "Manual"
    assert tiers["Audit.pdf"] == "Procedures"
    assert tiers["Cert.pdf"] == "Records"

    pyr = dms.build_pyramid("alice")
    by_tier = {t["tier"]: t["count"] for t in pyr["tiers"]}
    assert by_tier["Policy"] == 1 and by_tier["Manual"] == 1
    assert by_tier["Procedures"] == 1 and by_tier["Records"] == 1
    assert "Work Instructions" in pyr["empty_tiers"]

    xlsx = dms.register_to_xlsx("alice")
    assert xlsx[:2] == b"PK"  # xlsx is a zip container


def test_corpus_provenance_round_trip(temp_dms):
    """Fase D: analyze-dms salva la provenance DMS in analysis_documents e il
    re-analyse (load_analysis_corpus) la riporta indietro."""
    conn = dbm.get_connection()
    conn.execute(
        "INSERT INTO compliance_analyses (id, user_id, company, result_json) "
        "VALUES ('an_dms', 'alice', 'TestCo', '{}')"
    )
    conn.commit()
    conn.close()

    docs = [
        {"filename": "Policy.pdf", "content": "policy text", "document_id": 11, "version": 3},
        {"filename": "ZipOnly.pdf", "content": "no provenance"},  # ZIP-style, no DMS ids
    ]
    saved = dbm.save_analysis_corpus("an_dms", docs)
    assert saved == 2

    loaded = dbm.load_analysis_corpus("an_dms")
    by_name = {d["filename"]: d for d in loaded}
    assert by_name["Policy.pdf"]["document_id"] == 11
    assert by_name["Policy.pdf"]["version"] == 3
    assert "document_id" not in by_name["ZipOnly.pdf"]  # ZIP source stays clean
