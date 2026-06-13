"""
Fast regression for the Fase 4 NC register (PRD §1.4.8).

Pins: engine→register sync, real status round-trip (the old ncr_actions had
no UNIQUE and duplicated a row per click), manual NCs, dismiss/restore with
mandatory reason, and the legacy-table dedup migration. Temp SQLite per test.
"""
from __future__ import annotations

import sqlite3

import pytest

import modules.db_manager as dbm


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(dbm, "DB_FILE", db_file)
    dbm.init_compliance_tables()
    # riga analisi minima per il vincolo referenziale
    conn = dbm.get_connection()
    conn.execute(
        "INSERT INTO compliance_analyses (id, user_id, company, result_json) "
        "VALUES ('an_1', 'alice', 'TestCo', '{}')"
    )
    conn.commit()
    conn.close()
    return db_file


def _result_with_gaps():
    return {
        "norms": [{
            "norm": "ISO 9001:2015",
            "clauses": [
                {"clause_id": "9001_9_3", "clause_title": "9.3 Management review",
                 "severity": "MAJOR", "is_spof": False, "finding": "inputs missing"},
                {"clause_id": "9001_6_2", "clause_title": "6.2 Objectives",
                 "severity": "MINOR", "is_spof": False, "finding": "no deadlines"},
                {"clause_id": "9001_4_1", "clause_title": "4.1 Context",
                 "severity": "CONFORMANT", "is_spof": False, "finding": "ok"},
            ],
        }]
    }


def test_sync_creates_engine_rows_for_major_minor_only(temp_db):
    n = dbm.sync_engine_nonconformities("an_1", _result_with_gaps())
    assert n == 2
    ncs = dbm.get_nonconformities("an_1")
    assert {nc["clause_id"] for nc in ncs} == {"9001_9_3", "9001_6_2"}
    assert all(nc["source"] == "engine" for nc in ncs)
    assert {nc["severity"] for nc in ncs} == {"MAJOR", "MINOR"}


def test_sync_is_idempotent_and_preserves_user_state(temp_db):
    dbm.sync_engine_nonconformities("an_1", _result_with_gaps())
    dbm.update_ncr_status("an_1", "9001_9_3", "in_progress", "working on it")
    dbm.sync_engine_nonconformities("an_1", _result_with_gaps())  # re-run
    ncs = {nc["clause_id"]: nc for nc in dbm.get_nonconformities("an_1")}
    assert len(ncs) == 2, "sync must not duplicate rows"
    assert ncs["9001_9_3"]["status"] == "in_progress", "user state must survive sync"
    assert ncs["9001_9_3"]["notes"] == "working on it"


def test_status_roundtrip_no_duplicates(temp_db):
    dbm.sync_engine_nonconformities("an_1", _result_with_gaps())
    for status in ("in_progress", "closed", "open", "closed"):
        dbm.update_ncr_status("an_1", "9001_6_2", status)
    ncs = [nc for nc in dbm.get_nonconformities("an_1") if nc["clause_id"] == "9001_6_2"]
    assert len(ncs) == 1, "the old bug: one duplicate row per click"
    assert ncs[0]["status"] == "closed"


def test_manual_nc_and_dismiss_restore(temp_db):
    nc_id = dbm.add_manual_nonconformity(
        "an_1", "Forklift inspection overdue", "Found during walk-through",
        "MINOR", created_by="alice",
    )
    ncs = dbm.get_nonconformities("an_1")
    manual = next(nc for nc in ncs if nc["id"] == nc_id)
    assert manual["source"] == "manual" and manual["clause_id"] is None

    assert dbm.set_nonconformity_dismissed(nc_id, "an_1", True, "duplicate of NCR-12", "alice")
    nc = next(n for n in dbm.get_nonconformities("an_1") if n["id"] == nc_id)
    assert nc["dismissed"] == 1 and nc["dismiss_reason"] == "duplicate of NCR-12"

    assert dbm.set_nonconformity_dismissed(nc_id, "an_1", False)
    nc = next(n for n in dbm.get_nonconformities("an_1") if n["id"] == nc_id)
    assert nc["dismissed"] == 0 and nc["dismiss_reason"] == ""


def test_dismiss_wrong_analysis_is_rejected(temp_db):
    nc_id = dbm.add_manual_nonconformity("an_1", "X", "", "MINOR")
    assert dbm.set_nonconformity_dismissed(nc_id, "other_analysis", True, "r") is False


def test_legacy_ncr_actions_migration_dedups(tmp_path, monkeypatch):
    """Simula il DB pre-Fase-4 con righe duplicate e verifica la migrazione."""
    db_file = tmp_path / "legacy.db"
    monkeypatch.setattr(dbm, "DB_FILE", db_file)

    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE ncr_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id TEXT, clause_id TEXT, severity TEXT,
            is_spof INTEGER DEFAULT 0, status TEXT DEFAULT 'open',
            notes TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # tre click sulla stessa clausola = tre righe (il vecchio bug)
    conn.execute("INSERT INTO ncr_actions (analysis_id, clause_id, status, notes, updated_at) "
                 "VALUES ('an_9', '9001_8_4', 'open', '', '2026-06-01 10:00:00')")
    conn.execute("INSERT INTO ncr_actions (analysis_id, clause_id, status, notes, updated_at) "
                 "VALUES ('an_9', '9001_8_4', 'in_progress', '', '2026-06-02 10:00:00')")
    conn.execute("INSERT INTO ncr_actions (analysis_id, clause_id, status, notes, updated_at) "
                 "VALUES ('an_9', '9001_8_4', 'closed', 'done', '2026-06-03 10:00:00')")
    conn.commit()
    conn.close()

    dbm.init_compliance_tables()  # esegue la migrazione

    ncs = dbm.get_nonconformities("an_9")
    assert len(ncs) == 1, f"dedup fallita: {ncs}"
    assert ncs[0]["status"] == "closed" and ncs[0]["notes"] == "done"

    conn = dbm.get_connection()
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ncr_actions'"
    ).fetchone()
    conn.close()
    assert legacy is None, "la tabella legacy deve essere rimossa dopo la migrazione"
