"""
Pytest fixtures shared by all Amisys QHSE test files.

The fast suite (-m "not slow") relies only on synthetic in-memory fixtures
and never touches Azure or Gemini. The slow suite (-m slow) requires:
  - the CONSORZIO JEOCON 14001.zip on disk at CONSORZIO_ZIP_PATH (env or default)
  - working Azure OpenAI credentials in backend/.env

Fast tests are the regression net we keep green during day-to-day work.
Slow tests are run on demand before a release or after a major refactor.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Make `backend/` importable as a package root for tests
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Sprint R7 — the slow suite needs the Azure/Gemini credentials documented in
# backend/.env; load them here so `pytest -m slow` works without manual export.
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env", override=False)
except ImportError:
    pass


# ── Fast fixtures (no LLM) ───────────────────────────────────────────────────

@pytest.fixture
def mock_company_context():
    """A valid CompanyContext used by parser / floor / cite-or-fail tests."""
    from compliance.schemas import CompanyContext
    return CompanyContext(
        company_name="Test Manufacturing Ltd",
        sector="Manufacturing",
        employee_range="11-50",
        certified="No",
        sites_count="2-5",
        norms=["ISO 9001:2015"],
    )


@pytest.fixture
def mock_evidence_cards() -> List[Dict[str, Any]]:
    """Five card-shaped dicts with deliberate variety in doc_type and expiry."""
    return [
        {
            "evidence_id": "ev_001_manual",
            "file_name":   "quality_manual_v3.pdf",
            "readable":    True,
            "doc_type":    "quality_manual",
            "iso_clause_primary": "ISO 9001 §7.5",
            "iso_clauses_secondary": ["ISO 9001 §4.4"],
            "gap_signal":  False,
            "expiry_date": None,
            "signed_by":   "Quality Manager Anna Bianchi",
            "summary":     "Quality manual revision 3, full coverage of §7.5.",
            "excerpts":    [{"pages": [1], "text": "Documented information ...", "relevance": "Direct clause coverage"}],
            "confidence":  0.9,
        },
        {
            "evidence_id": "ev_002_dvr_expired",
            "file_name":   "DVR_old.pdf",
            "readable":    True,
            "doc_type":    "risk_assessment",
            "iso_clause_primary": "ISO 45001 §6.1.2",
            "gap_signal":  True,
            "expiry_date": "2024-09-15",       # ~600 days overdue at any 2026 date
            "signed_by":   "RSPP Mario Rossi",
            "summary":     "Expired risk assessment from 2022.",
            "excerpts":    [],
            "confidence":  0.8,
        },
        {
            "evidence_id": "ev_003_training",
            "file_name":   "training_cert_smith.pdf",
            "readable":    True,
            "doc_type":    "training_record",
            "iso_clause_primary": "ISO 45001 §7.2",
            "gap_signal":  False,
            "expiry_date": "2026-08-15",       # ~3 months in the future
            "signed_by":   None,
            "summary":     "Training certificate for safety operator.",
            "excerpts":    [],
            "confidence":  0.7,
        },
        {
            "evidence_id": "ev_004_supplier",
            "file_name":   "supplier_list.xlsx",
            "readable":    True,
            "doc_type":    "supplier_document",
            "iso_clause_primary": "ISO 9001 §8.4",
            "gap_signal":  True,
            "expiry_date": None,
            "signed_by":   None,
            "summary":     "Approved supplier list, last review unclear.",
            "excerpts":    [],
            "confidence":  0.6,
        },
        {
            "evidence_id": "ev_005_audit",
            "file_name":   "internal_audit_2025.pdf",
            "readable":    True,
            "doc_type":    "audit_report",
            "iso_clause_primary": "ISO 9001 §9.2",
            "gap_signal":  False,
            "expiry_date": None,
            "signed_by":   "Lead Auditor",
            "summary":     "Internal audit report 2025 with one finding.",
            "excerpts":    [],
            "confidence":  0.85,
        },
    ]


@pytest.fixture
def sample_clause_critical() -> Dict[str, Any]:
    """A critical clause (is_spof=True, will get severity_floor MAJOR)."""
    return {
        "id":               "9001_7_5",
        "title":            "7.5 Documented information",
        "area":             "Support",
        "is_spof":          True,
        "critical_sectors": ["Manufacturing", "Construction"],
        "typical_ncs":      ["No master document list", "No version control"],
        "evidence_keywords": ["documented information", "document control"],
        "remediation_template": {
            "what": "Implement document control procedure",
            "who":  "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    }


@pytest.fixture
def sample_clause_passing() -> Dict[str, Any]:
    """A passing (context) clause — severity_floor None."""
    return {
        "id":               "9001_4_1",
        "title":            "4.1 Understanding the organisation and its context",
        "area":             "Context",
        "is_spof":          False,
        "critical_sectors": [],
        "typical_ncs":      [],
        "evidence_keywords": ["context", "external issues"],
        "remediation_template": {
            "what": "Document SWOT analysis",
            "who":  "Quality Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "LOW",
        },
    }


# ── Slow fixtures (require CONSORZIO ZIP) ────────────────────────────────────

@pytest.fixture
def consorzio_zip_path() -> Path:
    """Path to the validation ZIP. Override via CONSORZIO_ZIP_PATH env."""
    default = r"C:\Users\user\Desktop\ANTIGRAVITY\ISO14001\CONSORZIO JEOCON 14001.zip"
    return Path(os.environ.get("CONSORZIO_ZIP_PATH", default))


@pytest.fixture
def consorzio_zip_bytes(consorzio_zip_path: Path) -> bytes:
    """Read the CONSORZIO ZIP from disk. Skips the test if not present."""
    if not consorzio_zip_path.exists():
        pytest.skip(f"CONSORZIO ZIP not found at {consorzio_zip_path}")
    return consorzio_zip_path.read_bytes()


@pytest.fixture
def mini_zip_bytes(consorzio_zip_path: Path, tmp_path: Path) -> bytes:
    """
    Build a 5-file mini ZIP by picking the first 5 PDFs from CONSORZIO.

    Built on the fly to avoid committing several MB of fixture data.
    Skipped when CONSORZIO is not on disk.
    """
    if not consorzio_zip_path.exists():
        pytest.skip(f"CONSORZIO ZIP not found at {consorzio_zip_path}")

    import zipfile
    import io
    src = consorzio_zip_path.read_bytes()
    picked: List[tuple] = []
    with zipfile.ZipFile(io.BytesIO(src)) as zin:
        for info in zin.infolist():
            if info.filename.lower().endswith(".pdf") and not info.filename.startswith("__MACOSX"):
                # Skip ridiculously large files; we want the test to run fast
                if info.file_size > 2_000_000:
                    continue
                picked.append((info.filename.split("/")[-1], zin.read(info.filename)))
                if len(picked) >= 5:
                    break
    if not picked:
        pytest.skip("No suitable PDFs found in CONSORZIO ZIP")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, payload in picked:
            zout.writestr(name, payload)
    return out.getvalue()
