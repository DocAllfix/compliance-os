"""
Fast regression for the Tasks waterfall (Fase F, PRD §1.3.4).

Pins: composition from nonconformities + DMS expiry + manual, deterministic
due dates (MAJOR +30 / MINOR +90), RAG buckets, write-through on completing an
nc:* task (closes the NC), and manual task lifecycle. DB + DMS redirected to tmp.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import modules.db_manager as dbm
import modules.dms_manager as dms
import modules.tasks_manager as tm


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(dbm, "DB_FILE", db_file)
    monkeypatch.setattr(dms, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dms, "DMS_DIR", tmp_path / "dms")
    (tmp_path / "dms").mkdir(parents=True, exist_ok=True)
    dbm.init_compliance_tables()
    dms.init_dms_tables()
    tm.init_tasks_tables()
    return tmp_path


def _seed_analysis_with_nc(analysis_date: str):
    conn = dbm.get_connection()
    conn.execute(
        "INSERT INTO compliance_analyses (id, user_id, company, result_json, analysis_date) "
        "VALUES ('an_t', 'alice', 'TestCo', '{}', ?)", (analysis_date,),
    )
    conn.commit()
    conn.close()
    # one MAJOR (open) + one MINOR (open) + one closed (excluded)
    result = {"norms": [{"norm": "ISO 9001:2015", "clauses": [
        {"clause_id": "9001_7_5", "clause_title": "7.5 Documented info", "severity": "MAJOR", "is_spof": False, "finding": "x"},
        {"clause_id": "9001_6_2", "clause_title": "6.2 Objectives", "severity": "MINOR", "is_spof": False, "finding": "y"},
    ]}]}
    dbm.sync_engine_nonconformities("an_t", result)


def test_tasks_from_nonconformities_due_dates(temp_env):
    _seed_analysis_with_nc("2026-01-01")
    tasks = tm.list_tasks("alice", today=date(2026, 1, 15))
    by_clause = {t["clause_id"]: t for t in tasks if t["source"] == "nonconformity"}
    assert by_clause["9001_7_5"]["due_date"] == "2026-01-31"   # MAJOR +30
    assert by_clause["9001_6_2"]["due_date"] == "2026-04-01"   # MINOR +90


def test_rag_buckets(temp_env):
    _seed_analysis_with_nc("2026-01-01")
    # today such that MAJOR (due 01-31) is overdue, MINOR (due 04-01) is green
    tasks = {t["clause_id"]: t for t in tm.list_tasks("alice", today=date(2026, 2, 10))
             if t["source"] == "nonconformity"}
    assert tasks["9001_7_5"]["rag"] == "red"
    assert tasks["9001_6_2"]["rag"] in ("amber", "green")


def test_expiry_and_manual_tasks(temp_env):
    fid = dms.create_folder("alice", "F")
    dms.create_document("alice", fid, "cert.pdf", b"x", "t",
                        doc_type="certificate", expiry_date="2026-06-30")
    tm.add_manual_task("alice", "Call the auditor", due_date="2026-03-01")
    tasks = tm.list_tasks("alice", today=date(2026, 1, 1))
    sources = {t["source"] for t in tasks}
    assert "expiry" in sources and "manual" in sources
    expiry = next(t for t in tasks if t["source"] == "expiry")
    assert expiry["due_date"] == "2026-06-30"


def test_complete_nc_task_writes_through(temp_env):
    _seed_analysis_with_nc("2026-01-01")
    tasks = tm.list_tasks("alice", today=date(2026, 1, 15))
    nc_task = next(t for t in tasks if t["clause_id"] == "9001_7_5")
    tm.set_task_done("alice", nc_task["task_key"], True)
    # the NC must now be closed → drops out of the open task list
    remaining = [t for t in tm.list_tasks("alice", today=date(2026, 1, 15))
                 if t.get("clause_id") == "9001_7_5" and not t["done"]]
    assert remaining == []
    ncs = {n["clause_id"]: n for n in dbm.get_nonconformities("an_t")}
    assert ncs["9001_7_5"]["status"] == "closed"


def test_snooze_moves_out_of_rag(temp_env):
    tm.add_manual_task("alice", "Later", due_date="2026-01-05")
    tasks = tm.list_tasks("alice", today=date(2026, 1, 10))
    key = tasks[0]["task_key"]
    assert tasks[0]["rag"] == "red"  # overdue
    tm.snooze_task("alice", key, "2026-02-01")
    after = {t["task_key"]: t for t in tm.list_tasks("alice", today=date(2026, 1, 10))}
    assert after[key]["rag"] == "snoozed"


def test_manual_task_delete(temp_env):
    tid = tm.add_manual_task("alice", "Temp")
    assert any(t["task_key"] == f"manual:{tid}" for t in tm.list_tasks("alice"))
    assert tm.delete_manual_task("alice", tid)
    assert not any(t["task_key"] == f"manual:{tid}" for t in tm.list_tasks("alice"))
