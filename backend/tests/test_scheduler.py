"""
Fast regression for the scheduler + notifications (Fase E, PRD §1.3.3).

Pins: expiry notifications fire at the right threshold with the right severity,
idempotency (a second scan does not duplicate), unread accounting, and the
retention sweep boundary. DB + DMS storage redirected to tmp_path.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import modules.db_manager as dbm
import modules.dms_manager as dms
import modules.notifications_manager as nm
import scheduler


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(dbm, "DB_FILE", db_file)
    monkeypatch.setattr(dms, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dms, "DMS_DIR", tmp_path / "dms")
    (tmp_path / "dms").mkdir(parents=True, exist_ok=True)
    dbm.init_compliance_tables()
    dms.init_dms_tables()
    nm.init_notifications_tables()
    return tmp_path


def _doc_expiring_in(days: int, owner="alice", name="cert.pdf"):
    fid = dms.create_folder(owner, "F")
    exp = (date.today() + timedelta(days=days)).isoformat()
    return dms.create_document(owner, fid, name, b"x", "text",
                               doc_type="certificate", expiry_date=exp)["document_id"]


def test_expiry_severity_buckets(temp_env):
    _doc_expiring_in(5, name="a.pdf")    # ≤7 → MAJOR
    _doc_expiring_in(20, name="b.pdf")   # ≤30 → MINOR
    _doc_expiring_in(50, name="c.pdf")   # ≤60 → OBSERVATION
    _doc_expiring_in(120, name="d.pdf")  # >60 → no notification
    created = scheduler.expiry_scan()
    assert created == 3
    items = {n["title"].split()[0]: n["severity"] for n in nm.list_notifications("alice")}
    assert items["a.pdf"] == "MAJOR"
    assert items["b.pdf"] == "MINOR"
    assert items["c.pdf"] == "OBSERVATION"


def test_expiry_scan_is_idempotent(temp_env):
    _doc_expiring_in(10)
    assert scheduler.expiry_scan() == 1
    assert scheduler.expiry_scan() == 0  # dedup on second pass
    assert nm.unread_count("alice") == 1


def test_overdue_document_notifies_major(temp_env):
    _doc_expiring_in(-3, name="expired.pdf")
    assert scheduler.expiry_scan() == 1
    n = nm.list_notifications("alice")[0]
    assert n["severity"] == "MAJOR" and "expired" in n["title"].lower()


def test_mark_read_and_unread_count(temp_env):
    _doc_expiring_in(10)
    scheduler.expiry_scan()
    items = nm.list_notifications("alice")
    assert nm.unread_count("alice") == 1
    assert nm.mark_read(items[0]["id"], "alice")
    assert nm.unread_count("alice") == 0


def test_notifications_are_per_owner(temp_env):
    _doc_expiring_in(10, owner="alice")
    _doc_expiring_in(10, owner="bob")
    scheduler.expiry_scan()
    assert nm.unread_count("alice") == 1
    assert nm.unread_count("bob") == 1
    assert len(nm.list_notifications("alice")) == 1


def test_retention_sweep_soft_deletes_past_policy(temp_env):
    fid = dms.create_folder("alice", "Short", retention_days=10)
    did = dms.create_document("alice", fid, "old.pdf", b"x", "text")["document_id"]
    # backdate updated_at beyond retention
    conn = dbm.get_connection()
    old = (date.today() - timedelta(days=40)).isoformat()
    conn.execute("UPDATE dms_documents SET updated_at = ? WHERE id = ?", (old, did))
    conn.commit(); conn.close()

    res = scheduler.retention_sweep()
    assert res["soft_deleted"] == 1
    assert dms.get_document(did) is None  # filtered out (deleted)


def test_retention_leaves_fresh_documents(temp_env):
    fid = dms.create_folder("alice", "Short", retention_days=10)
    did = dms.create_document("alice", fid, "fresh.pdf", b"x", "text")["document_id"]
    res = scheduler.retention_sweep()
    assert res["soft_deleted"] == 0
    assert dms.get_document(did) is not None
