"""
Fast regression for the Fase 5 delta engine (Compare).

Pins: improved/regressed/unchanged/new/removed directions, severity-change
detection at equal score, per-norm overall deltas, documented-info delta.
Temp SQLite, no LLM.
"""
from __future__ import annotations

import json

import pytest

import modules.db_manager as dbm
from compliance.delta_engine import compare_analyses


def _result(norm_scores: dict, clauses: list, di_absent: list | None = None) -> str:
    di = None
    if di_absent is not None:
        di = {
            "items": [
                {"norm": "ISO 9001:2015", "item": i, "status": "ABSENT",
                 "clause_id": "x", "retain_or_maintain": "MAINTAIN",
                 "match_method": "not_found", "risk_if_missing": "MAJOR"}
                for i in di_absent
            ],
            "found_count": 0, "weak_count": 0, "absent_count": len(di_absent),
        }
    return json.dumps({
        "company": "TestCo",
        "analysis_date": "2026-06-12T10:00:00",
        "norms": [
            {"norm": n, "overall_score": s, "clauses": [c for c in clauses if c["clause_id"].startswith(n.split(" ")[1].split(":")[0])]}
            for n, s in norm_scores.items()
        ],
        "documented_info_report": di,
    })


def _clause(cid, title, score, severity):
    return {"clause_id": cid, "clause_title": title, "score": score, "severity": severity}


@pytest.fixture
def two_analyses(tmp_path, monkeypatch):
    monkeypatch.setattr(dbm, "DB_FILE", tmp_path / "delta.db")
    dbm.init_compliance_tables()
    conn = dbm.get_connection()

    old_json = _result(
        {"ISO 9001:2015": 47},
        [
            _clause("9001_9_3", "9.3 MR", 20, "MAJOR"),
            _clause("9001_6_2", "6.2 Obj", 40, "MINOR"),
            _clause("9001_8_4", "8.4 Sup", 70, "OBSERVATION"),
            _clause("9001_7_5", "7.5 Doc", 55, "MINOR"),   # rimossa nella nuova
        ],
        di_absent=["Quality objectives", "Internal audit programme and reports"],
    )
    new_json = _result(
        {"ISO 9001:2015": 64},
        [
            _clause("9001_9_3", "9.3 MR", 65, "OBSERVATION"),   # improved (severity down)
            _clause("9001_6_2", "6.2 Obj", 40, "MAJOR"),        # regressed a score uguale!
            _clause("9001_8_4", "8.4 Sup", 70, "OBSERVATION"),  # unchanged
            _clause("9001_5_2", "5.2 Policy", 30, "MINOR"),     # new
        ],
        di_absent=["Internal audit programme and reports", "Management review minutes"],
    )
    for aid, rj in (("an_old", old_json), ("an_new", new_json)):
        conn.execute(
            "INSERT INTO compliance_analyses (id, user_id, company, result_json) VALUES (?, 'alice', 'TestCo', ?)",
            (aid, rj),
        )
    conn.commit()
    conn.close()


def test_directions_and_summary(two_analyses):
    d = compare_analyses("an_new", "an_old")
    assert "error" not in d
    by_id = {c["clause_id"]: c for c in d["clauses"]}

    assert by_id["9001_9_3"]["direction"] == "improved"
    assert by_id["9001_9_3"]["severity_changed"] is True

    # Fase 5: severity peggiorata DEVE essere regressed anche a score invariato
    assert by_id["9001_6_2"]["direction"] == "regressed"
    assert by_id["9001_6_2"]["delta"] == 0

    assert by_id["9001_8_4"]["direction"] == "unchanged"
    assert by_id["9001_5_2"]["direction"] == "new"
    assert by_id["9001_7_5"]["direction"] == "removed"

    s = d["summary"]
    assert s["improved"] == 1 and s["regressed"] == 1
    assert s["new"] == 1 and s["removed"] == 1
    assert s["severity_downgrades"] == 1 and s["severity_upgrades"] == 1


def test_per_norm_overall(two_analyses):
    d = compare_analyses("an_new", "an_old")
    norm = next(n for n in d["norms"] if n["norm"] == "ISO 9001:2015")
    assert norm["overall_old"] == 47 and norm["overall_new"] == 64
    assert norm["overall_delta"] == 17


def test_documented_info_delta(two_analyses):
    d = compare_analyses("an_new", "an_old")
    di = d["documented_info"]
    assert di is not None
    assert any("Quality objectives" in x for x in di["resolved"])
    assert any("Management review minutes" in x for x in di["newly_missing"])


def test_missing_analysis_returns_error(two_analyses):
    d = compare_analyses("an_new", "does_not_exist")
    assert "error" in d
