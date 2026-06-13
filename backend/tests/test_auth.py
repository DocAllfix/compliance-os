"""
Fast regression for auth_manager password handling (Fase 1 consolidamento).

change_password compared a freshly-salted bcrypt hash against the stored one,
so it ALWAYS failed. These tests pin the verify_password-based behaviour and
the bcrypt round-trip, using a temp users file (no touching config/users.json).
"""
from __future__ import annotations

import pytest

from modules import auth_manager
from modules.auth_manager import change_password, hash_password, verify_password


@pytest.fixture
def temp_users(tmp_path, monkeypatch):
    """Redirect USERS_FILE to a temp path with one known user."""
    users_file = tmp_path / "users.json"
    monkeypatch.setattr(auth_manager, "USERS_FILE", users_file)
    users = {
        "testuser": {
            "password": hash_password("oldpass123"),
            "name": "Test User",
            "role": "auditor",
        }
    }
    auth_manager.save_users(users)
    return users_file


def test_verify_password_roundtrip():
    hashed = hash_password("s3cret!")
    assert verify_password("s3cret!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_hash_password_salts_differ():
    """Two hashes of the same password differ (fresh salt) — the very property
    that made the old equality-based change_password always fail."""
    assert hash_password("same") != hash_password("same")


def test_change_password_with_correct_old(temp_users):
    ok, msg = change_password("testuser", "oldpass123", "newpass456")
    assert ok is True, msg
    users = auth_manager.load_users()
    assert verify_password("newpass456", users["testuser"]["password"])
    assert not verify_password("oldpass123", users["testuser"]["password"])


def test_change_password_rejects_wrong_old(temp_users):
    ok, msg = change_password("testuser", "WRONG", "newpass456")
    assert ok is False
    users = auth_manager.load_users()
    assert verify_password("oldpass123", users["testuser"]["password"])


def test_change_password_rejects_short_new(temp_users):
    ok, msg = change_password("testuser", "oldpass123", "abc")
    assert ok is False
