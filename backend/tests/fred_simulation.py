"""
Fred-simulation acceptance pack builder (Sprint R7).

Generates an in-memory ZIP of UK English company documents with SEEDED GAPS
whose ground truth is known. This replicates the kind of test Five Rise will
run against the compliance engine, including Fred's own scenarios from the
14/05/2026 conversation (objectives in an Excel file never called
"objectives"; documents named unhelpfully; scattered evidence).

Seeded gaps (ground truth):
  G1  MR minutes missing two §9.3 inputs (resource adequacy, effectiveness of
      risk actions) — outputs/decisions present.
  G2  Quality policy WITHOUT the commitment to continual improvement
      (commitment to customer/statutory requirements present).
  G3  "Company KPIs 2026.xlsx" — never the word 'objectives'; 2 of 4 targets
      have no deadline; 1 has no target value (declared-only).
  G4  Risk register declares a 5x5 scoring methodology but half the entries
      carry no score (criteria declared, not applied).
  G5  Risk "Use of unqualified welding subcontractors" has NO corresponding
      operational control anywhere (chain 6.1 → 8.1 broken for it).
  G6  Objectives evidence scattered: two KPI targets live only in the
      Strategic Plan, progress discussion only in the MR minutes.
  G7  Clean documents that must NOT produce false MAJORs: a complete internal
      audit programme + report, and a complete supplier qualification
      procedure with approved supplier list.

Documents are DOCX (python-docx) and XLSX (openpyxl) — the same formats a UK
client would upload. File names are deliberately unhelpful where the scenario
requires it.
"""
from __future__ import annotations

import io
import zipfile
from typing import Dict


def _docx_bytes(paragraphs: list) -> bytes:
    import docx
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _xlsx_bytes(sheet_name: str, rows: list) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_documents() -> Dict[str, bytes]:
    """Return {filename: bytes} for the full pack."""
    docs: Dict[str, bytes] = {}

    # ── G1: MR minutes — missing resource adequacy + risk-action effectiveness
    docs["Management Review Minutes March 2026.docx"] = _docx_bytes([
        "HARTWELL ENGINEERING LTD — MANAGEMENT REVIEW MINUTES",
        "Date: 14 March 2026. Attendees: J. Hartwell (Managing Director), "
        "S. Price (Quality Manager), L. Okafor (Operations Manager).",
        "1. Status of actions from the previous review: action MR-2025-03 "
        "(update of the calibration schedule) closed in January 2026; action "
        "MR-2025-04 (supplier re-evaluation) closed.",
        "2. Changes in external and internal issues: new client requirement "
        "for PPAP documentation discussed; no changes to the regulatory "
        "framework noted.",
        "3. Customer feedback and satisfaction: the 2025 customer survey "
        "returned an average score of 4.2/5. Two complaints received, both "
        "resolved within SLA.",
        "4. Internal audit results: the 2025 audit cycle was completed; three "
        "minor findings raised, all corrective actions verified as closed.",
        "5. Nonconformities and corrective actions: 11 NCRs raised in 2025, "
        "9 closed, 2 in progress with target dates in April 2026.",
        "6. Achievement of quality objectives: on-time delivery improved to "
        "94% against the 95% target; scrap rate target met.",
        "7. Decisions and actions: the review concluded the QMS remains "
        "suitable, adequate and effective. Decision: invest in a second CMM "
        "(owner: Operations Manager, by Q3 2026). Decision: extend the "
        "supplier audit programme to logistics providers (owner: Quality "
        "Manager, by June 2026).",
    ])

    # ── G2: policy without continual improvement commitment
    docs["QP-01 rev4.docx"] = _docx_bytes([
        "HARTWELL ENGINEERING LTD — QUALITY POLICY",
        "Hartwell Engineering Ltd designs and manufactures precision "
        "machined components for the aerospace and energy sectors.",
        "We are committed to meeting customer requirements and all "
        "applicable statutory and regulatory requirements in everything "
        "we manufacture.",
        "This policy provides the framework for setting and reviewing our "
        "quality objectives, which are established at the annual management "
        "review and cascaded to every department.",
        "The policy is communicated to all employees at induction and is "
        "available to interested parties on request.",
        "Approved by J. Hartwell, Managing Director — 5 January 2026.",
    ])

    # ── G3: objectives in an xlsx never called "objectives"
    docs["Company KPIs 2026.xlsx"] = _xlsx_bytes("Targets 2026", [
        ["Ref", "Target", "Measure", "Target value", "Deadline", "Owner"],
        ["T1", "Improve on-time delivery", "% orders delivered on time", "95%", "31/12/2026", "Operations Manager"],
        ["T2", "Reduce internal scrap", "Scrap cost as % of turnover", "1.5%", "31/12/2026", "Production Lead"],
        ["T3", "Increase customer satisfaction", "Survey average score", "4.5 / 5", None, "Quality Manager"],
        ["T4", "Strengthen supplier quality culture", None, None, None, "Quality Manager"],
    ])

    # ── G4 + G5: risk register, methodology declared but not applied; one
    #            risk with no corresponding operational control anywhere.
    docs["ORR-2026 v2 FINAL.docx"] = _docx_bytes([
        "HARTWELL ENGINEERING LTD — OPERATIONAL RISK REVIEW 2026",
        "Methodology: each risk is assessed using a 5x5 matrix. Likelihood "
        "(1-5) is multiplied by impact (1-5) to produce a risk score; scores "
        "of 15 and above are classed High and require a mitigation plan with "
        "a named owner.",
        "R-01 — Loss of CMM calibration traceability. Likelihood 2, Impact 4, "
        "Score 8 (Medium). Mitigation: calibration schedule CP-7.1 with "
        "external UKAS laboratory. Owner: Quality Manager.",
        "R-02 — Single-source dependency for heat treatment. Likelihood 3, "
        "Impact 4, Score 12 (Medium). Mitigation: second supplier under "
        "qualification per procedure PP-8.4. Owner: Purchasing Lead.",
        "R-03 — Use of unqualified welding subcontractors on customer "
        "projects. Mitigation: to be defined. Owner: to be confirmed.",
        "R-04 — Key-person dependency in CNC programming. Mitigation: "
        "cross-training plan started.",
        "Opportunities: O-01 — automation of inspection reporting could "
        "reduce lead time by two days.",
    ])

    # ── G6: strategic plan carrying two further targets (scattered evidence)
    docs["Strategic Plan 2026-2028.docx"] = _docx_bytes([
        "HARTWELL ENGINEERING LTD — STRATEGIC PLAN 2026-2028",
        "Our growth strategy rests on operational excellence and supply "
        "chain resilience.",
        "Strategic target: achieve AS9100 readiness by the end of 2027, "
        "measured by a readiness assessment score of 85% or higher.",
        "Strategic target: reduce average quotation turnaround to 3 working "
        "days by December 2026, measured weekly by the sales dashboard.",
        "Progress against these targets is reviewed quarterly by the "
        "management team and reported at the management review.",
    ])

    # ── G7a: clean internal audit programme + report (no false MAJOR)
    docs["Internal Audit Programme and Report 2025.docx"] = _docx_bytes([
        "HARTWELL ENGINEERING LTD — INTERNAL AUDIT PROGRAMME 2025",
        "The annual programme covers all QMS processes. Frequency is "
        "risk-based: production and purchasing are audited twice yearly, "
        "support processes annually. Auditors are independent of the area "
        "audited and trained to ISO 19011 principles.",
        "Schedule: February — purchasing and supplier control (auditor: "
        "S. Price); May — production and inspection (auditor: external "
        "associate); September — document control and training (auditor: "
        "S. Price); November — management processes (auditor: external "
        "associate).",
        "AUDIT REPORT SUMMARY 2025: all four planned audits were executed "
        "on schedule. Three minor findings were raised: one missing signature "
        "on a router card, one outdated work instruction at the deburr "
        "station, one training record not yet filed. Root cause analysis "
        "(5 Whys) was completed for each finding and corrective actions were "
        "verified effective at the following audit.",
    ])

    # ── G7b: clean supplier procedure + approved list (no false MAJOR)
    docs["PP-8.4 Supplier Qualification Procedure.docx"] = _docx_bytes([
        "HARTWELL ENGINEERING LTD — PROCEDURE PP-8.4: SUPPLIER QUALIFICATION "
        "AND EVALUATION. Revision 3, approved 10 February 2026 by S. Price, "
        "Quality Manager.",
        "Purpose: to define the criteria and process for qualifying, "
        "evaluating and re-evaluating external providers.",
        "Qualification: new suppliers complete the questionnaire QF-8.4-01 "
        "and provide certification evidence. Critical suppliers (those "
        "delivering special processes or customer-designated items) also "
        "receive an on-site assessment before approval.",
        "Approved supplier list: register QR-8.4-02 lists all approved "
        "suppliers with scope, approval date and review date. Purchasing may "
        "only place orders with suppliers on the register.",
        "Evaluation: supplier performance (on-time delivery, quality "
        "rejects, complaint response) is scored quarterly. Critical "
        "suppliers are reviewed at least annually; the review outcome is "
        "recorded on the register and drives retain/remove decisions.",
        "APPROVED SUPPLIER REGISTER (QR-8.4-02, extract February 2026): "
        "Thermo Treatments Ltd — heat treatment — approved, critical, next "
        "review 02/2027. MetalStock UK — raw material — approved, next "
        "review 02/2027. Precision Coatings Ltd — surface treatment — "
        "approved, critical, next review 02/2027.",
    ])

    return docs


def build_zip_bytes() -> bytes:
    """Zip the pack in memory — ready for run_compliance_pipeline."""
    docs = build_documents()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in docs.items():
            zf.writestr(name, data)
    return buf.getvalue()


def company_context():
    """The CompanyContext Fred's test company would enter in the wizard."""
    from compliance.schemas import CompanyContext
    return CompanyContext(
        company_name="Hartwell Engineering Ltd",
        sector="Manufacturing",
        employee_range="51-250",
        certified="in_progress",
        sites_count="1",
        norms=["ISO 9001:2015"],
    )
