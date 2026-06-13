"""
Fred-simulation acceptance harness (Sprint R7).

Fast tests (default suite): the pack builds, every document is ingested with
the right format handler (XLSX included), the documented-info registry and
chain definitions are coherent with the clause registries.

Slow tests (-m slow, needs LLM credentials): the full pipeline runs on the
pack and the engine must catch the seeded gaps:

  G1  §9.3 MR inputs incomplete (resource adequacy / risk-action effectiveness)
  G2  §5.2 policy missing the continual-improvement commitment
  G3  §6.2 objectives in an xlsx (label-agnostic) with measurability gaps
  G4  §6.1 risk criteria declared but not applied to all entries
  G5  cross-clause risk→control chain not LINKED (R-03 has no control)
  G6  objectives evidence aggregated across files (xlsx + strategic plan)
  G7  no false MAJOR on the clean documents (§9.2 internal audit, §8.4 supplier)
plus: citation integrity — every cited file exists in the pack.
"""
from __future__ import annotations

import pytest

from tests.fred_simulation import build_documents, build_zip_bytes, company_context


# ── Fast: pack integrity and ingestion ───────────────────────────────────────

def test_pack_builds_with_all_documents():
    docs = build_documents()
    assert len(docs) == 7
    assert "Company KPIs 2026.xlsx" in docs
    zip_bytes = build_zip_bytes()
    assert len(zip_bytes) > 10_000


def test_pack_extraction_reads_every_format():
    """Phase 1 must read every file in the pack — including the XLSX (P7)."""
    from compliance.pipeline import _read_file_content

    docs = build_documents()
    for name, raw in docs.items():
        text = _read_file_content(name, raw)
        assert text.strip(), f"{name} produced no text"

    # The xlsx must surface its tabular content with the sheet marker
    kpi_text = _read_file_content("Company KPIs 2026.xlsx", docs["Company KPIs 2026.xlsx"])
    assert '[SHEET "Targets 2026"]' in kpi_text
    assert "on-time delivery" in kpi_text.lower()
    assert "95%" in kpi_text


def test_pack_zip_pipeline_phase1():
    """The ZIP path (Phase 1) must yield all 7 documents."""
    from compliance.pipeline import _extract_documents

    events = []
    docs = _extract_documents(build_zip_bytes(), lambda p, m: events.append(m))
    assert len(docs) == 7
    names = {d["filename"] for d in docs}
    assert "Company KPIs 2026.xlsx" in names


def test_chain_definitions_reference_real_clauses():
    """Every chain node must exist in its norm's clause registry."""
    from compliance.cross_clause import CHAINS
    from compliance.iso_clauses.iso9001_clauses import ISO9001_CLAUSES
    from compliance.iso_clauses.iso14001_clauses import ISO14001_CLAUSES
    from compliance.iso_clauses.iso45001_clauses import ISO45001_CLAUSES

    registries = {
        "ISO 9001:2015": ISO9001_CLAUSES,
        "ISO 14001:2015": ISO14001_CLAUSES,
        "ISO 45001:2018": ISO45001_CLAUSES,
    }
    for chain in CHAINS:
        registry = registries[chain["norm"]]
        for cid in chain["clause_ids"]:
            assert cid in registry, f"chain {chain['chain_id']} references unknown clause {cid}"


def test_documented_info_registry_references_real_clauses():
    from compliance.documented_info_check import _REGISTRY
    from compliance.iso_clauses.iso9001_clauses import ISO9001_CLAUSES
    from compliance.iso_clauses.iso14001_clauses import ISO14001_CLAUSES
    from compliance.iso_clauses.iso45001_clauses import ISO45001_CLAUSES

    registries = {
        "ISO 9001:2015": ISO9001_CLAUSES,
        "ISO 14001:2015": ISO14001_CLAUSES,
        "ISO 45001:2018": ISO45001_CLAUSES,
    }
    for norm, items in _REGISTRY.items():
        for item in items:
            assert item["clause_id"] in registries[norm], (
                f"documented-info item {item['item']!r} references unknown "
                f"clause {item['clause_id']}"
            )


# ── Slow: end-to-end acceptance (needs Azure/Gemini credentials) ─────────────

@pytest.fixture(scope="module")
def fred_result():
    """Run the full pipeline once for the whole slow module."""
    from compliance.pipeline import run_compliance_pipeline

    outcome = run_compliance_pipeline(
        zip_bytes=build_zip_bytes(),
        company_context=company_context(),
        emitter=None,
    )
    assert outcome["success"], f"pipeline failed: {outcome.get('error')}"
    return outcome["result"]


def _gap(result, clause_id):
    for norm in result.norms:
        for g in norm.clauses:
            if g.clause_id == clause_id:
                return g
    raise AssertionError(f"clause {clause_id} not in result")


@pytest.mark.slow
def test_g3_xlsx_objectives_recognised(fred_result):
    """The KPI xlsx must be ingested and cited for §6.2 despite never saying
    'objectives' (P7 — label-agnostic, Excel format)."""
    gap = _gap(fred_result, "9001_6_2")
    cited_files = " ".join(
        s.file_name.lower() for s in gap.sources
    ) + " " + " ".join(
        (c.file_name or "").lower() for c in gap.requirement_checks
    )
    assert "kpi" in cited_files or "targets" in gap.finding.lower() or "kpi" in gap.finding.lower(), (
        f"§6.2 verdict does not engage with the KPI spreadsheet: {gap.finding}"
    )


@pytest.mark.slow
def test_g3_measurability_gap_found(fred_result):
    """T3 (no deadline) and T4 (no measure/target) must pull §6.2 below
    CONFORMANT with a measurability-related finding (P5)."""
    gap = _gap(fred_result, "9001_6_2")
    assert gap.severity in ("MINOR", "OBSERVATION", "MAJOR"), gap.severity
    statuses = {c.requirement_id.split(".")[-1]: c.status for c in gap.requirement_checks}
    # At least one of the measurability checks must be non-PRESENT
    flagged = [s for k, s in statuses.items() if s in ("PARTIAL", "ABSENT")]
    assert flagged, f"no measurability item flagged: {statuses}"


@pytest.mark.slow
def test_g2_policy_improvement_commitment_absent(fred_result):
    """§5.2: the continual-improvement commitment is absent from the policy
    wording and must be named (P4)."""
    gap = _gap(fred_result, "9001_5_2")
    assert gap.severity != "CONFORMANT", gap.severity
    improvement_check = next(
        (c for c in gap.requirement_checks
         if "improvement" in c.requirement_id),
        None,
    )
    if improvement_check is not None:
        assert improvement_check.status in ("ABSENT", "PARTIAL"), improvement_check
    else:
        assert "improvement" in gap.finding.lower(), gap.finding


@pytest.mark.slow
def test_g1_mr_missing_inputs_named(fred_result):
    """§9.3: the minutes miss resource adequacy + risk-action effectiveness;
    at least one MR input check must be PARTIAL/ABSENT (P3 — agenda mapping)."""
    gap = _gap(fred_result, "9001_9_3")
    input_checks = [c for c in gap.requirement_checks if ".input." in c.requirement_id]
    assert input_checks, "no MR input requirement checks produced"
    flagged = [c for c in input_checks if c.status in ("PARTIAL", "ABSENT")]
    assert flagged, (
        "all MR inputs marked PRESENT despite seeded gaps "
        f"(resource adequacy, risk-action effectiveness): "
        f"{[(c.requirement_id, c.status) for c in input_checks]}"
    )
    assert gap.severity in ("MINOR", "MAJOR", "OBSERVATION")


@pytest.mark.slow
def test_g4_criteria_declared_not_applied(fred_result):
    """§6.1: R-03/R-04 carry no score despite the declared 5x5 matrix (P2)."""
    gap = _gap(fred_result, "9001_6_1")
    applied_check = next(
        (c for c in gap.requirement_checks if "applied" in c.requirement_id),
        None,
    )
    if applied_check is not None:
        assert applied_check.status in ("PARTIAL", "ABSENT"), applied_check
    else:
        assert gap.severity in ("MINOR", "MAJOR"), (
            f"§6.1 did not flag the unscored entries: {gap.finding}"
        )


@pytest.mark.slow
def test_g5_risk_to_control_chain_not_linked(fred_result):
    """Cross-clause: R-03 (welding subcontractors) has no control → the
    9001 risk→control chain cannot be LINKED (P6)."""
    chains = {f.chain_id: f for f in fred_result.cross_clause_findings}
    chain = chains.get("9001_risk_to_control")
    assert chain is not None, "risk_to_control chain was not assessed"
    assert chain.status in ("PARTIAL", "BROKEN", "NOT_ASSESSABLE"), chain.status


@pytest.mark.slow
def test_g6_scattered_evidence_aggregated(fred_result):
    """P8: the objectives evidence is split between the KPI xlsx and the
    Strategic Plan — the §6.2 verdict must engage with MORE THAN ONE document
    (aggregation across files, with per-source traceability)."""
    gap = _gap(fred_result, "9001_6_2")
    engaged_files = set()
    for s in gap.sources:
        engaged_files.add(s.file_name.replace("\\", "/").rsplit("/", 1)[-1].lower())
    for c in gap.requirement_checks:
        if c.file_name:
            engaged_files.add(c.file_name.replace("\\", "/").rsplit("/", 1)[-1].lower())
    assert len(engaged_files) >= 2, (
        f"§6.2 cites only {engaged_files or 'nothing'} — scattered objectives "
        f"evidence (xlsx + strategic plan) was not aggregated"
    )


@pytest.mark.slow
def test_p2_risk_register_extracted(fred_result):
    """P2: the risk document must yield a STRUCTURED register, with R-03/R-04
    flagged for missing scores (criteria declared but not applied)."""
    extract = fred_result.risk_register_extract
    assert extract is not None, "no structured risk register extracted"
    assert extract.total_risks >= 3, f"only {extract.total_risks} risks extracted"
    assert extract.unscored_count >= 1, (
        "no unscored risks flagged despite R-03/R-04 carrying no score"
    )
    # The placeholder mitigation 'to be defined' on R-03 must count as missing
    assert extract.unmitigated_count >= 1, "placeholder mitigations not flagged"


@pytest.mark.slow
def test_g7_no_false_majors_on_clean_documents(fred_result):
    """§9.2 (audit) and §8.4 (suppliers) are documented and complete — they
    must not come back MAJOR (anti-pessimism / false-positive control)."""
    for cid in ("9001_9_2", "9001_8_4"):
        gap = _gap(fred_result, cid)
        assert gap.severity != "MAJOR", (
            f"{cid} false MAJOR on clean evidence: {gap.finding}"
        )


@pytest.mark.slow
def test_citation_integrity(fred_result):
    """Every cited file name must exist in the pack; quotes carry no invented
    pages (PRD 1.4.6 traceability)."""
    pack_names = {n.lower() for n in build_documents().keys()}

    def _check_name(name: str, where: str):
        if not name:
            return
        short = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        assert short in pack_names, f"invented citation {name!r} in {where}"

    for norm in fred_result.norms:
        for g in norm.clauses:
            for s in g.sources:
                _check_name(s.file_name, g.clause_id)
            for c in g.requirement_checks:
                if c.file_name:
                    _check_name(c.file_name, f"{g.clause_id}/{c.requirement_id}")
    for f in fred_result.cross_clause_findings:
        for s in f.sources:
            _check_name(s.file_name, f.chain_id)
