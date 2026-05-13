"""
Slow E2E smoke for the full compliance pipeline.

These tests require:
  - the CONSORZIO JEOCON 14001.zip on disk (skipped if missing)
  - working Azure OpenAI credentials in backend/.env

Run with:    pytest tests/ -m slow
Skip with:   pytest tests/ -m "not slow"  (default during day-to-day work)
"""
from __future__ import annotations

import pytest

from compliance.pipeline import run_compliance_pipeline


pytestmark = pytest.mark.slow


def test_full_pipeline_on_mini_zip(mini_zip_bytes, mock_company_context):
    """
    Smallest E2E. Mini ZIP has 5 PDFs from CONSORZIO; this exercises
    every phase (extract → evidence → expiry → gap → executive summary)
    without paying for the full 28-doc run.
    """
    progress: list = []

    def emit(pct: float, msg: str) -> None:
        progress.append((pct, msg))

    outcome = run_compliance_pipeline(
        zip_bytes=mini_zip_bytes,
        company_context=mock_company_context,
        emitter=emit,
    )

    assert outcome["success"] is True, f"Pipeline failed: {outcome.get('error')!r}"
    result = outcome["result"]

    # Phase 1
    assert result.documents_analyzed >= 1
    # Phase 3
    assert len(result.norms) == 1
    assert result.norms[0].norm == "ISO 9001:2015"
    assert len(result.norms[0].clauses) > 0
    # Each verdict has a recognised severity
    for clause in result.norms[0].clauses:
        assert clause.severity in ("MAJOR", "MINOR", "OBSERVATION", "CONFORMANT")
    # Progress emitter was used
    assert any("Phase" in msg or "batch" in msg.lower() or "Embedded" in msg for _, msg in progress)
