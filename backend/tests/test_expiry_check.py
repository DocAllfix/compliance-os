"""
Fast regression for the Phase 2.5 expiry check.

The module is 100% Python (no LLM), so these tests are entirely deterministic
and never touch Azure / Gemini.
"""
from __future__ import annotations

from datetime import date

from compliance.expiry_check import (
    run_expiry_check, _severity_for_days, _parse_iso_date, _doc_type_to_clauses,
)


def test_severity_ladder():
    assert _severity_for_days(200)  == "MAJOR"        # >180 days overdue
    assert _severity_for_days(180)  == "MINOR"        # ≥30 and ≤180
    assert _severity_for_days(31)   == "MINOR"
    assert _severity_for_days(29)   == "OBSERVATION"
    assert _severity_for_days(0)    == "OBSERVATION"
    assert _severity_for_days(-15)  == "OBSERVATION"  # expires within 30 days
    assert _severity_for_days(-60)  == "INFO"         # expires within 90 days
    assert _severity_for_days(-100) is None           # outside reporting window


def test_parse_iso_date_handles_multiple_formats():
    assert _parse_iso_date("2026-05-13") == date(2026, 5, 13)
    assert _parse_iso_date("2026-05")    == date(2026, 5, 1)
    assert _parse_iso_date("2026")       == date(2026, 1, 1)
    assert _parse_iso_date("null")       is None
    assert _parse_iso_date("")           is None
    assert _parse_iso_date("garbage")    is None


def test_doc_type_to_clauses_known_mappings():
    """A few canonical mappings used by the report and chat layers."""
    assert "ISO 45001 §7.2" in _doc_type_to_clauses("training_record")
    assert "ISO 9001 §7.1.5" in _doc_type_to_clauses("calibration_record")
    assert "ISO 45001 §6.1.2" in _doc_type_to_clauses("risk_assessment")
    assert _doc_type_to_clauses("other") == []
    assert _doc_type_to_clauses("unknown_category") == []


# ── End-to-end on synthetic YAML ──────────────────────────────────────────────

_AUDIT_DATE = date(2026, 5, 13)


def _yaml_three_docs() -> str:
    # Build with a non-em-dash placeholder then substitute to avoid console quirks
    body = """---
meta:
  total_docs: 3
  readable_docs: 3
  unreadable_docs: 0
  processing_notes: "test"

# DOC1
evidence_id: "ev_001_expired"
file_name: "old_dvr.pdf"
readable: true
doc_type: "risk_assessment"
iso_clause_primary: "ISO 45001 §6.1.2"
gap_signal: true
expiry_date: "2024-09-15"
summary: |
  Old DVR.

# DOC2
evidence_id: "ev_002_future"
file_name: "training_cert.pdf"
readable: true
doc_type: "training_record"
iso_clause_primary: "ISO 45001 §7.2"
gap_signal: false
expiry_date: "2026-08-01"
summary: |
  Future training certificate.

# DOC3
evidence_id: "ev_003_no_expiry"
file_name: "visura.pdf"
readable: true
doc_type: "other"
iso_clause_primary: "ISO 9001 §4.1"
gap_signal: false
expiry_date: null
summary: |
  Company registry, no expiry.
"""
    return body.replace("# DOC1", "# ── DOC 1 ──") \
               .replace("# DOC2", "# ── DOC 2 ──") \
               .replace("# DOC3", "# ── DOC 3 ──")


def test_run_expiry_check_classifies_three_docs():
    report = run_expiry_check(_yaml_three_docs(), audit_date=_AUDIT_DATE)
    assert report["audit_date"] == "2026-05-13"

    expired = report["expired_documents"]
    expiring = report["expiring_soon"]
    assert len(expired) == 1
    assert len(expiring) == 1

    # 1st doc: 2024-09-15 → 605 days overdue → MAJOR
    assert expired[0]["file_name"] == "old_dvr.pdf"
    assert expired[0]["days_overdue"] >= 600
    assert expired[0]["severity"] == "MAJOR"

    # 2nd doc: 2026-08-01 → ~80 days in future → INFO (within 90 days)
    assert expiring[0]["file_name"] == "training_cert.pdf"
    assert expiring[0]["days_overdue"] < 0
    assert expiring[0]["severity"] == "INFO"

    # 3rd doc: no expiry → counted in no_expiry_information
    assert report["no_expiry_information"] == 1


def test_run_expiry_check_empty_yaml():
    report = run_expiry_check("", audit_date=_AUDIT_DATE)
    assert report["expired_documents"] == []
    assert report["expiring_soon"] == []
    assert report["no_expiry_information"] == 0
