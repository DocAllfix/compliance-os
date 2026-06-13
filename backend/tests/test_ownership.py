"""
Fast regression for the Fase 3 anti-IDOR ownership checks.

Pins `_require_analysis_access`: 404 on missing analysis, 403 when the
analysis belongs to another user, pass-through for the owner and for admin.
Uses a monkeypatched DB row — no SQLite, no LLM.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import api_server
from api_server import _require_analysis_access


@pytest.fixture
def fake_row(monkeypatch):
    """get_compliance_analysis returns a row owned by 'alice'."""
    row = {"id": "analysis_x", "user_id": "alice", "result_json": "{}"}

    import modules.db_manager as dbm
    monkeypatch.setattr(dbm, "get_compliance_analysis", lambda _id: row if _id == "analysis_x" else None)
    return row


def _user(username: str, role: str = "auditor"):
    return {"username": username, "role": role}


def test_owner_can_access(fake_row):
    row = _require_analysis_access("analysis_x", _user("alice"))
    assert row["id"] == "analysis_x"


def test_owner_case_insensitive(fake_row):
    row = _require_analysis_access("analysis_x", _user("Alice"))
    assert row["id"] == "analysis_x"


def test_other_user_gets_403(fake_row):
    with pytest.raises(HTTPException) as exc:
        _require_analysis_access("analysis_x", _user("bob"))
    assert exc.value.status_code == 403


def test_admin_bypasses_ownership(fake_row):
    row = _require_analysis_access("analysis_x", _user("bob", role="admin"))
    assert row["id"] == "analysis_x"


def test_missing_analysis_gets_404(fake_row):
    with pytest.raises(HTTPException) as exc:
        _require_analysis_access("does_not_exist", _user("alice"))
    assert exc.value.status_code == 404
