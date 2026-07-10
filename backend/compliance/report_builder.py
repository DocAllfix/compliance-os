"""
Amisys QHSE — DOCX Report Builder.

Produces a manager-friendly gap analysis report using python-docx.

Structure (rev. 2026-07 — multi-norm):
  Cover page + Contents (static index)
  §1  Company Snapshot                     (from executive_summary.company_snapshot)
  §2  Executive Summary                    (integrated overview table + executive_narrative + per-norm blocks)
  §3  Document Expiry Status               (from expiry_report)
  §3B Required Documented Information      (Phase 2.6)
  §3C Cross-Clause Coherence               (Phase 3.5)
  §3D Risk Register (as extracted)         (Phase 2.7)
  §4  Single Points of Failure             (norm-labelled)
  §5  Top 10 Priority Integrations         (from executive_summary.top_priority_integrations)
  §6  Critical Findings / §6B Action Plan (Standard column) / §6C Manual NCs
  §6D Clause Matrix per norm / §6E Set-aside Findings
  §7  Methodology & Disclaimer

Sections backed by optional fields (executive_summary, expiry_report)
are skipped silently when those fields are None — older analyses that
predate Sprint 2/4 still produce a coherent document.

Severity colours (as per DESIGN.md):
  MAJOR       #DC2626  (red)
  MINOR       #F97316  (orange)
  OBSERVATION #CA8A04  (amber)
  CONFORMANT  #16A34A  (green)
  SPOF        #EA580C  (dark orange)
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor, Cm

from compliance.schemas import (
    ClauseGap,
    CompanySnapshot,
    ComplianceAnalysisResult,
    CrossClauseFinding,
    DocumentedInfoReport,
    ExpiredDocument,
    ExpiryReport,
    NormGapReport,
    RiskRegisterExtract,
)


# ── Colour constants ──────────────────────────────────────────────────────────

C_MAJOR       = RGBColor(0xDC, 0x26, 0x26)
C_MINOR       = RGBColor(0xF9, 0x73, 0x16)
C_OBSERVATION = RGBColor(0xCA, 0x8A, 0x04)
C_CONFORMANT  = RGBColor(0x16, 0xA3, 0x4A)
C_SPOF        = RGBColor(0xEA, 0x58, 0x0C)
C_DARK        = RGBColor(0x1B, 0x29, 0x44)   # brand navy
C_ACCENT      = RGBColor(0xE0, 0x8A, 0x1E)   # brand orange (Amisys)
C_GREY        = RGBColor(0x64, 0x74, 0x8B)
C_WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
C_LIGHT_BG    = RGBColor(0xF8, 0xFA, 0xFC)

SEVERITY_COLOR = {
    "MAJOR":       C_MAJOR,
    "MINOR":       C_MINOR,
    "OBSERVATION": C_OBSERVATION,
    "CONFORMANT":  C_CONFORMANT,
}

SEVERITY_HEX = {
    "MAJOR":       "DC2626",
    "MINOR":       "F97316",
    "OBSERVATION": "CA8A04",
    "CONFORMANT":  "16A34A",
}


# ── Public entry point ────────────────────────────────────────────────────────

def build_docx_report(
    result: ComplianceAnalysisResult,
    register: Optional[List[dict]] = None,
) -> bytes:
    """
    Build a DOCX report from a ComplianceAnalysisResult. Returns the raw
    bytes of the .docx file.

    Fase 4 (PRD §1.4.8) — `register` è la lista NC dal registro persistente:
    i finding dismissed escono dalle sezioni operative (Top Priority
    Findings, SPoF, Critical Findings, Action Plan) e finiscono
    nell'appendice "Set-aside findings" con motivazione; le NC manuali
    hanno la loro sezione. La Clause Matrix resta lo snapshot integrale
    (trasparenza) ma marca le righe messe da parte come "Set aside".

    Section order (Sprint 4):
      Cover page
      §1 Company Snapshot               — executive_summary.company_snapshot
      §2 Executive Narrative            — executive_summary.executive_narrative
                                        + legacy per-norm summary block
      §3 Document Expiry Status         — expiry_report
      §4 Single Points of Failure       — gaps with is_spof and MAJOR
      §5 Top 10 Priority Integrations   — executive_summary.top_priority_integrations
      §6 Detailed Clause Analysis       — Critical Findings, Action Plan, Clause Matrix
      §7 Methodology & Disclaimer
    """
    doc = Document()
    _configure_document(doc)

    # Registro NC: clausole messe da parte + NC manuali
    register = register or []
    dismissed_rows = [nc for nc in register if nc.get("dismissed")]
    dismissed_ids = {nc.get("clause_id") for nc in dismissed_rows if nc.get("clause_id")}
    manual_ncs = [nc for nc in register if nc.get("source") == "manual" and not nc.get("dismissed")]

    # Multi-norm 2026-07 — mappa clause_id → norma di appartenenza: le sezioni
    # che mischiano norme (SPoF, Critical Findings, Action Plan) etichettano
    # ogni finding col suo standard, altrimenti "10.2" di 9001 e 45001 sono
    # indistinguibili per chi legge il report offline.
    norm_of = {g.clause_id: nr.norm for nr in result.norms for g in nr.clauses}

    _add_cover(doc, result)
    doc.add_page_break()

    # Indice statico — le voci rispecchiano ESATTAMENTE le condizioni con cui
    # le sezioni vengono aggiunte sotto (tenere sincronizzati).
    _all_gaps_toc = [g for nr in result.norms for g in nr.clauses]
    _operative_toc = [g for g in _all_gaps_toc if g.clause_id not in dismissed_ids]
    toc_entries: List[str] = []
    if result.executive_summary is not None:
        toc_entries.append("§1  Company Snapshot")
    toc_entries.append("§2  Executive Summary")
    if result.expiry_report is not None and (
        result.expiry_report.expired_documents or result.expiry_report.expiring_soon
    ):
        toc_entries.append("§3  Document Expiry Status")
    if result.documented_info_report is not None and (
        result.documented_info_report.absent_count > 0
        or result.documented_info_report.weak_count > 0
    ):
        toc_entries.append("§3B  Required Documented Information")
    if result.cross_clause_findings:
        toc_entries.append("§3C  Cross-Clause Coherence")
    if result.risk_register_extract is not None and result.risk_register_extract.total_risks > 0:
        toc_entries.append("§3D  Risk Register (as extracted)")
    if any(g.is_spof and g.severity == "MAJOR" for g in _operative_toc):
        toc_entries.append("§4  Single Points of Failure")
    if result.executive_summary is not None and result.executive_summary.top_priority_integrations:
        toc_entries.append("§5  Top Priority Integrations")
    if any(g.severity == "MAJOR" for g in _operative_toc):
        toc_entries.append("§6  Critical Findings")
    if any(g.severity in ("MAJOR", "MINOR") for g in _operative_toc):
        toc_entries.append("§6B  Action Plan")
    if manual_ncs:
        toc_entries.append("§6C  Manually Recorded Nonconformities")
    for nr in result.norms:
        toc_entries.append(f"§6D  Clause Matrix — {nr.norm}")
    if dismissed_rows:
        toc_entries.append("§6E  Set-aside Findings")
    toc_entries.append("§7  Methodology & Disclaimer")
    _add_toc(doc, toc_entries)
    doc.add_page_break()

    # §1 Company Snapshot — only when the LLM produced an executive summary
    if result.executive_summary is not None:
        _add_company_snapshot(
            doc, result.executive_summary.company_snapshot,
            assessed_norms=list(result.context.norms or []),
        )
        doc.add_page_break()

    # §2 Executive Narrative + per-norm summary
    _add_executive_summary(doc, result, dismissed_ids)
    doc.add_page_break()

    # §3 Document Expiry Status — only when Phase 2.5 ran and produced output
    if result.expiry_report is not None and (
        result.expiry_report.expired_documents or result.expiry_report.expiring_soon
    ):
        _add_expiry_section(doc, result.expiry_report)
        doc.add_page_break()

    # §3b Required Documented Information (Phase 2.6 — Sprint R6)
    if result.documented_info_report is not None and (
        result.documented_info_report.absent_count > 0
        or result.documented_info_report.weak_count > 0
    ):
        _add_documented_info_section(doc, result.documented_info_report)
        doc.add_page_break()

    # §3c Cross-Clause Coherence (Phase 3.5 — Sprint R6)
    if result.cross_clause_findings:
        _add_cross_clause_section(doc, result.cross_clause_findings)
        doc.add_page_break()

    # §3D Risk Register (Phase 2.7) — parità col frontend: il registro
    # estratto coi flag deterministici sui campi mancanti (2026-07)
    if result.risk_register_extract is not None and result.risk_register_extract.total_risks > 0:
        _add_risk_register_section(doc, result.risk_register_extract)
        doc.add_page_break()

    all_gaps = [g for norm in result.norms for g in norm.clauses]
    # Fase 4: i finding messi da parte escono dalle sezioni operative
    operative_gaps = [g for g in all_gaps if g.clause_id not in dismissed_ids]
    spof_gaps = [g for g in operative_gaps if g.is_spof and g.severity == "MAJOR"]

    # §4 Single Points of Failure
    if spof_gaps:
        _add_spof_section(doc, spof_gaps, norm_of=norm_of)
        doc.add_page_break()

    # §5 Top 10 Priority Integrations — manager-friendly bullet list
    if result.executive_summary is not None and result.executive_summary.top_priority_integrations:
        _add_priority_integrations(doc, result.executive_summary.top_priority_integrations)
        doc.add_page_break()

    # §6 Detailed Clause Analysis
    major_gaps = [g for g in operative_gaps if g.severity == "MAJOR"]
    if major_gaps:
        _add_critical_findings(doc, major_gaps, norm_of=norm_of)
        doc.add_page_break()

    actionable = [g for g in operative_gaps if g.severity in ("MAJOR", "MINOR")]
    if actionable:
        _add_action_plan(doc, actionable, norm_of=norm_of)
        doc.add_page_break()

    # §6b Manually recorded nonconformities (Fase 4)
    if manual_ncs:
        _add_manual_ncs_section(doc, manual_ncs)
        doc.add_page_break()

    for norm_report in result.norms:
        _add_clause_matrix(doc, norm_report, dismissed_ids)
        doc.add_page_break()

    # §6c Set-aside findings (Fase 4 — dismissed, con motivazione)
    if dismissed_rows:
        _add_set_aside_section(doc, dismissed_rows)
        doc.add_page_break()

    # §7 Methodology & Disclaimer (always last)
    _add_methodology(doc, result)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Document setup ────────────────────────────────────────────────────────────

def _configure_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width  = Inches(8.27)   # A4
    section.page_height = Inches(11.69)
    section.left_margin   = Inches(1.0)
    section.right_margin  = Inches(1.0)
    section.top_margin    = Inches(0.9)
    section.bottom_margin = Inches(0.9)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.font.color.rgb = C_DARK


# ── Cover page ────────────────────────────────────────────────────────────────

def _add_cover(doc: Document, result: ComplianceAnalysisResult) -> None:
    brand = doc.add_paragraph()
    brand.alignment = WD_ALIGN_PARAGRAPH.CENTER
    b1 = brand.add_run("Amisys")
    b1.font.size = Pt(14)
    b1.font.bold = True
    b1.font.color.rgb = C_ACCENT
    b2 = brand.add_run("  qhse")
    b2.font.size = Pt(11)
    b2.font.color.rgb = C_GREY

    doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("ISO COMPLIANCE GAP ANALYSIS")
    run.font.size  = Pt(22)
    run.font.bold  = True
    run.font.color.rgb = C_DARK

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = p2.add_run("REPORT")
    run2.font.size  = Pt(22)
    run2.font.bold  = True
    run2.font.color.rgb = C_ACCENT

    doc.add_paragraph()

    _add_centred(doc, result.company, size=16, bold=True)
    _add_centred(doc, result.context.sector, size=11, color=C_GREY)

    doc.add_paragraph()
    _add_centred(doc, "Standards assessed:", size=10, color=C_GREY)
    _add_centred(doc, "  ·  ".join(result.context.norms), size=11, bold=True)

    doc.add_paragraph()
    date_str = datetime.fromisoformat(result.analysis_date).strftime("%d %B %Y") if result.analysis_date else datetime.today().strftime("%d %B %Y")
    _add_centred(doc, date_str, size=10, color=C_GREY)

    doc.add_paragraph()
    doc.add_paragraph()
    _add_centred(doc, f"Prepared for {result.company} by Amisys QHSE", size=9, color=C_GREY, italic=True)
    _add_centred(doc, f"Documents analysed: {result.documents_analyzed}", size=9, color=C_GREY, italic=True)


# ── Executive Summary ─────────────────────────────────────────────────────────

def _add_executive_summary(
    doc: Document, result: ComplianceAnalysisResult, dismissed_ids: set | None = None
) -> None:
    _h1(doc, "§2  Executive Summary")
    dismissed_ids = dismissed_ids or set()

    # Colpo d'occhio integrato (2026-07): una riga per standard, prima di
    # qualsiasi prosa — la prima cosa che un manager cerca in uno scan multi-norma.
    if len(result.norms) >= 1:
        table = doc.add_table(rows=1, cols=7)
        table.style = "Table Grid"
        _set_col_widths(table, [Inches(1.7), Inches(0.8), Inches(0.7), Inches(0.7), Inches(0.9), Inches(0.9), Inches(0.6)])
        for i, h in enumerate(["Standard", "Score", "Major", "Minor", "Observations", "Conformant", "SPoF"]):
            cell = table.rows[0].cells[i]
            cell.text = h
            run = cell.paragraphs[0].runs[0]
            run.font.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = C_WHITE
            _set_cell_bg(cell, "1B2944")
        for norm in result.norms:
            r = table.add_row()
            vals = [
                norm.norm,
                f"{norm.overall_score}/100",
                str(norm.major_count),
                str(norm.minor_count),
                str(norm.observation_count),
                str(norm.conformant_count),
                str(norm.spof_count),
            ]
            for j, v in enumerate(vals):
                r.cells[j].text = v
                run = r.cells[j].paragraphs[0].runs[0]
                run.font.size = Pt(9)
            score = norm.overall_score
            score_color = C_CONFORMANT if score >= 75 else C_MINOR if score >= 50 else C_MAJOR
            r.cells[1].paragraphs[0].runs[0].font.bold = True
            r.cells[1].paragraphs[0].runs[0].font.color.rgb = score_color
            if norm.major_count:
                r.cells[2].paragraphs[0].runs[0].font.color.rgb = C_MAJOR
                r.cells[2].paragraphs[0].runs[0].font.bold = True
            if norm.spof_count:
                r.cells[6].paragraphs[0].runs[0].font.color.rgb = C_SPOF
                r.cells[6].paragraphs[0].runs[0].font.bold = True
        doc.add_paragraph()

    # Narrative manageriale del Phase 4 (2026-07: prima veniva scartata —
    # esisteva solo nel frontend, mai nel DOCX).
    if result.executive_summary is not None:
        narrative = (result.executive_summary.executive_narrative or "").strip()
        if narrative:
            for para in [p.strip() for p in narrative.split("\n") if p.strip()]:
                _body(doc, para)
            doc.add_paragraph()

    for norm in result.norms:
        _h2(doc, norm.norm)

        score = norm.overall_score
        score_color = C_CONFORMANT if score >= 75 else C_MINOR if score >= 50 else C_MAJOR

        p = doc.add_paragraph()
        p.add_run("Overall Compliance Score: ").font.bold = True
        r = p.add_run(f"{score}/100")
        r.font.bold  = True
        r.font.color.rgb = score_color
        r.font.size  = Pt(14)

        _body(doc, f"The analysis identified {norm.major_count} Major non-conformit{'y' if norm.major_count == 1 else 'ies'}, {norm.minor_count} Minor, {norm.observation_count} Observation{'s' if norm.observation_count != 1 else ''}, and {norm.conformant_count} conformant clause{'s' if norm.conformant_count != 1 else ''}.")

        if norm.spof_count > 0:
            p_spof = doc.add_paragraph()
            r_spof = p_spof.add_run(f"⚠  {norm.spof_count} Single Point{'s' if norm.spof_count > 1 else ''} of Failure identified — these require immediate attention.")
            r_spof.font.color.rgb = C_SPOF
            r_spof.font.bold = True

        # Top 3 risks — i finding messi da parte non sono prioritari
        top = sorted(
            [g for g in norm.clauses
             if g.severity in ("MAJOR", "MINOR") and g.clause_id not in dismissed_ids],
            key=lambda g: (0 if g.is_spof else 1, g.score)
        )[:3]

        if top:
            _h3(doc, "Top Priority Findings")
            for i, g in enumerate(top, 1):
                p = doc.add_paragraph(style="List Number")
                r = p.add_run(f"{g.clause_title}  ")
                r.font.bold = True
                badge = p.add_run(f"[{g.severity}]")
                badge.font.color.rgb = SEVERITY_COLOR.get(g.severity, C_DARK)
                badge.font.bold = True
                p.add_run(f"  —  Score {g.score}/100")

        doc.add_paragraph()


# ── SPoF section ──────────────────────────────────────────────────────────────

def _add_spof_section(
    doc: Document, spofs: List[ClauseGap], norm_of: Optional[dict] = None
) -> None:
    _h1(doc, "§4  Single Points of Failure")
    norm_of = norm_of or {}

    p = doc.add_paragraph()
    r = p.add_run("The following clauses represent Single Points of Failure (SPoF) — their absence or failure undermines the entire management system and must be addressed before any other non-conformity.")
    r.font.color.rgb = C_SPOF
    r.font.italic = True

    doc.add_paragraph()

    for gap in spofs:
        norm_label = norm_of.get(gap.clause_id, "")
        prefix = f"[{_short_norm(norm_label)}]  " if norm_label else ""
        _h2(doc, f"⚠  {prefix}{gap.clause_title}", color=C_SPOF)
        _body(doc, gap.finding)

        p = doc.add_paragraph()
        p.add_run("Required action: ").font.bold = True
        p.add_run(gap.remediation.what)

        p2 = doc.add_paragraph()
        p2.add_run(f"Responsible: {gap.remediation.who}   ·   Deadline: {gap.remediation.when}   ·   Effort: {gap.remediation.effort}")
        p2.runs[0].font.color.rgb = C_GREY
        p2.runs[0].font.size = Pt(9)

        if gap.sources:
            p3 = doc.add_paragraph()
            p3.add_run("Evidence: ").font.bold = True
            for s in gap.sources[:2]:
                pages = ", ".join(f"p.{pg}" for pg in s.pages) if s.pages else ""
                p3.add_run(f"{s.file_name}{' ' + pages if pages else ''}")

        doc.add_paragraph()


# ── Critical Findings ─────────────────────────────────────────────────────────

def _add_critical_findings(
    doc: Document, majors: List[ClauseGap], norm_of: Optional[dict] = None
) -> None:
    _h1(doc, "§6  Critical Findings")
    norm_of = norm_of or {}

    for gap in majors:
        norm_label = norm_of.get(gap.clause_id, "")
        prefix = f"[{_short_norm(norm_label)}]  " if norm_label else ""
        _h2(doc, f"{prefix}{gap.clause_title}", color=C_MAJOR)

        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        _set_col_widths(table, [Inches(1.4), Inches(5.1)])

        def add_row(label: str, value: str, val_color: Optional[RGBColor] = None) -> None:
            row = table.add_row()
            row.cells[0].text = label
            row.cells[0].paragraphs[0].runs[0].font.bold = True
            row.cells[0].paragraphs[0].runs[0].font.color.rgb = C_GREY
            row.cells[0].paragraphs[0].runs[0].font.size = Pt(9)
            row.cells[1].text = value
            if val_color:
                row.cells[1].paragraphs[0].runs[0].font.color.rgb = val_color

        # Remove the empty first row
        table._tbl.remove(table.rows[0]._tr)

        add_row("Clause", gap.clause_title)
        if norm_label:
            add_row("Standard", norm_label)
        score_label = f"{gap.score}/100 — {gap.severity}"
        if gap.confidence is not None:
            score_label += f"   (confidence {round(gap.confidence * 100)}%)"
        add_row("Score", score_label, SEVERITY_COLOR.get(gap.severity))
        add_row("Finding", gap.finding)
        if gap.hedged and gap.hedge_note:
            add_row("Caution", gap.hedge_note, C_GREY)
        # Sprint R6 — per-requirement verification from the deep pass
        if gap.requirement_checks:
            checks_str = "\n".join(
                f"[{chk.status}] {chk.requirement_id.split('.', 1)[-1].replace('_', ' ')}"
                + (f" — {chk.note}" if chk.note else "")
                for chk in gap.requirement_checks
            )
            add_row("Checks", checks_str)
        if gap.sources:
            sources_str = "; ".join(
                f"{s.file_name}{', p.' + str(s.pages[0]) if s.pages else ''}"
                for s in gap.sources[:3]
            )
            add_row("Evidence", sources_str)
        # Sprint R6 (PRD 1.4.7) — two-level remediation when available
        if gap.remediation.correction or gap.remediation.corrective_action:
            if gap.remediation.correction:
                add_row("Correction", gap.remediation.correction)
            if gap.remediation.corrective_action:
                add_row("Corrective action", gap.remediation.corrective_action)
        else:
            add_row("Action", gap.remediation.what)
        add_row("Responsible", gap.remediation.who)
        add_row("Deadline", gap.remediation.when)
        add_row("Effort", gap.remediation.effort)

        doc.add_paragraph()


# ── Action Plan table ─────────────────────────────────────────────────────────

def _add_action_plan(
    doc: Document, gaps: List[ClauseGap], norm_of: Optional[dict] = None
) -> None:
    _h1(doc, "§6B  Action Plan")
    norm_of = norm_of or {}

    table = doc.add_table(rows=1, cols=7)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_col_widths(table, [Inches(0.5), Inches(0.9), Inches(0.6), Inches(2.1), Inches(1.1), Inches(0.8), Inches(0.5)])

    headers = ["Priority", "Standard", "Clause", "Action", "Responsible", "Deadline", "Effort"]
    hrow = table.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]
        cell.text = h
        p = cell.paragraphs[0]
        p.runs[0].font.bold  = True
        p.runs[0].font.size  = Pt(9)
        p.runs[0].font.color.rgb = C_WHITE
        _set_cell_bg(cell, "1B2944")

    sorted_gaps = sorted(gaps, key=lambda g: (0 if g.is_spof else 1, 0 if g.severity == "MAJOR" else 1, g.score))

    for i, gap in enumerate(sorted_gaps, 1):
        row = table.add_row()
        vals = [
            str(i),
            _short_norm(norm_of.get(gap.clause_id, "")) or "—",
            _clause_display(gap.clause_id),
            gap.remediation.what[:120] + ("…" if len(gap.remediation.what) > 120 else ""),
            gap.remediation.who,
            gap.remediation.when,
            gap.remediation.effort,
        ]
        for j, val in enumerate(vals):
            row.cells[j].text = val
            p = row.cells[j].paragraphs[0]
            for run in p.runs:
                run.font.size = Pt(9)
                if j == 0:
                    run.font.bold = True
                    run.font.color.rgb = SEVERITY_COLOR.get(gap.severity, C_DARK)

        bg = "F8FAFC" if i % 2 == 0 else "FFFFFF"
        for cell in row.cells:
            _set_cell_bg(cell, bg)

    doc.add_paragraph()


# ── Full Clause Matrix ────────────────────────────────────────────────────────

def _add_clause_matrix(
    doc: Document, norm: NormGapReport, dismissed_ids: set | None = None
) -> None:
    _h1(doc, f"§6D  Clause Matrix — {norm.norm}")
    dismissed_ids = dismissed_ids or set()

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    _set_col_widths(table, [Inches(1.4), Inches(2.8), Inches(0.7), Inches(1.6)])

    for i, h in enumerate(["Clause", "Title", "Score", "Severity"]):
        cell = table.rows[0].cells[i]
        cell.text = h
        p = cell.paragraphs[0]
        p.runs[0].font.bold  = True
        p.runs[0].font.size  = Pt(9)
        p.runs[0].font.color.rgb = C_WHITE
        _set_cell_bg(cell, "1B2944")

    sorted_clauses = sorted(norm.clauses, key=lambda g: (
        0 if g.is_spof and g.severity == "MAJOR" else 1,
        {"MAJOR": 0, "MINOR": 1, "OBSERVATION": 2, "CONFORMANT": 3}.get(g.severity, 9),
        g.score,
    ))

    for i, gap in enumerate(sorted_clauses):
        set_aside = gap.clause_id in dismissed_ids
        row = table.add_row()
        row.cells[0].text = gap.clause_id
        row.cells[1].text = gap.clause_title
        row.cells[2].text = str(gap.score)
        if set_aside:
            row.cells[3].text = "Set aside"
        else:
            row.cells[3].text = f"{'⚠ SPoF + ' if gap.is_spof else ''}{gap.severity}"

        color = C_GREY if set_aside else SEVERITY_COLOR.get(gap.severity, C_DARK)
        for cell in row.cells:
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
        row.cells[2].paragraphs[0].runs[0].font.color.rgb = color
        row.cells[3].paragraphs[0].runs[0].font.color.rgb = color
        if gap.is_spof and not set_aside:
            row.cells[3].paragraphs[0].runs[0].font.bold = True

        if set_aside:
            bg = "F8FAFC"
        else:
            bg = "FEF2F2" if gap.severity == "MAJOR" else "FFF7ED" if gap.severity == "MINOR" else "F8FAFC" if i % 2 == 0 else "FFFFFF"
        for cell in row.cells:
            _set_cell_bg(cell, bg)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _short_norm(norm: str) -> str:
    """'ISO 9001:2015' → 'ISO 9001'; i set custom restano il loro label."""
    return norm.split(":")[0].strip() if ":" in norm else norm


_KNOWN_PREFIXES = {"9001", "14001", "45001"}


def _clause_display(clause_id: str) -> str:
    """'9001_10_2' → '10.2'; '45001_8_1_4' → '8.1.4'; id custom → invariato."""
    if "_" in clause_id:
        prefix, rest = clause_id.split("_", 1)
        if prefix in _KNOWN_PREFIXES and rest:
            return rest.replace("_", ".")
    return clause_id


def _add_toc(doc: Document, entries: List[str]) -> None:
    """Indice statico (senza numeri di pagina: i § sono la navigazione)."""
    _h1(doc, "Contents")
    for entry in entries:
        p = doc.add_paragraph(entry)
        p.runs[0].font.size = Pt(10)
        p.paragraph_format.space_after = Pt(2)


def _h1(doc: Document, text: str, color: RGBColor = C_DARK) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text.upper())
    run.font.size  = Pt(13)
    run.font.bold  = True
    run.font.color.rgb = color
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.keep_with_next = True
    _add_bottom_border(p)


def _h2(doc: Document, text: str, color: RGBColor = C_DARK) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size  = Pt(11)
    run.font.bold  = True
    run.font.color.rgb = color
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(2)
    p.paragraph_format.keep_with_next = True


def _h3(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size  = Pt(10)
    run.font.bold  = True
    run.font.color.rgb = C_GREY
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(2)


def _body(doc: Document, text: str) -> None:
    p = doc.add_paragraph(text)
    p.runs[0].font.size = Pt(10)
    p.paragraph_format.space_after = Pt(4)


def _add_centred(doc: Document, text: str, size: int = 11,
                 bold: bool = False, italic: bool = False,
                 color: RGBColor = C_DARK) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.italic = italic
    run.font.color.rgb = color


def _set_col_widths(table, widths) -> None:
    for row in table.rows:
        for i, width in enumerate(widths):
            if i < len(row.cells):
                row.cells[i].width = width


# ── PQQ / SQ export (Fase H, PRD §1.6.9) ──────────────────────────────────────

def build_pqq_docx(company: str, items: List[dict]) -> bytes:
    """DOCX delle risposte PQQ/SQ. Disclaimer 'Draft for review' in testa e in
    coda: è una bozza grounded sull'evidenza, MAI una submission."""
    doc = Document()
    _configure_document(doc)

    brand = doc.add_paragraph()
    brand.alignment = WD_ALIGN_PARAGRAPH.CENTER
    b1 = brand.add_run("Amisys"); b1.font.size = Pt(13); b1.font.bold = True; b1.font.color.rgb = C_ACCENT
    b2 = brand.add_run("  qhse"); b2.font.size = Pt(10); b2.font.color.rgb = C_GREY

    _add_centred(doc, "PRE-QUALIFICATION QUESTIONNAIRE — DRAFT", size=18, bold=True)
    if company:
        _add_centred(doc, company, size=13, color=C_GREY)
    doc.add_paragraph()

    warn = doc.add_paragraph()
    wr = warn.add_run(
        "DRAFT FOR REVIEW — NOT A SUBMISSION. These answers are generated from "
        "your documented evidence and must be reviewed, completed where marked "
        "'needs input', and approved before any tender submission."
    )
    wr.font.size = Pt(9.5); wr.font.italic = True; wr.font.color.rgb = C_MAJOR
    doc.add_paragraph()

    for i, item in enumerate(items, 1):
        _h2(doc, f"Q{i}. {str(item.get('question', '')).strip()}")
        if str(item.get("status")) == "needs_input":
            tag = doc.add_paragraph()
            t = tag.add_run("NEEDS INPUT")
            t.font.size = Pt(8.5); t.font.bold = True; t.font.color.rgb = C_MINOR
        _body(doc, str(item.get("answer", "")).strip() or "—")
        doc.add_paragraph()

    doc.add_paragraph()
    _add_centred(doc,
                 "Draft produced by Amisys QHSE. Review before submission.",
                 size=8.5, italic=True, color=C_GREY)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _set_cell_bg(cell, hex_color: str) -> None:
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)


def _add_bottom_border(paragraph) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"),   "single")
    bottom.set(qn("w:sz"),    "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "1B2944")
    pBdr.append(bottom)
    pPr.append(pBdr)


# ── §1 Company Snapshot (Sprint 4) ───────────────────────────────────────────

def _add_company_snapshot(
    doc: Document, snap: CompanySnapshot,
    assessed_norms: Optional[List[str]] = None,
) -> None:
    _h1(doc, "§1  Company Snapshot")

    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    _set_col_widths(table, [Inches(1.6), Inches(4.9)])

    def row(label: str, value: str) -> None:
        r = table.add_row()
        r.cells[0].text = label
        run = r.cells[0].paragraphs[0].runs[0]
        run.font.bold = True
        run.font.color.rgb = C_GREY
        run.font.size = Pt(9)
        _set_cell_bg(r.cells[0], "F8FAFC")
        r.cells[1].text = value or "—"
        r.cells[1].paragraphs[0].runs[0].font.size = Pt(10)

    row("Company",   snap.company_name)
    row("Sector",    snap.sector)
    row("Size",      snap.size)
    row("Sites",     snap.sites_summary)
    # 2026-07: "—" nudo era ambiguo. Se non risultano certificazioni, dirlo
    # esplicitamente e mostrare gli standard in valutazione (context.norms).
    if snap.certified_standards:
        row("Certified standards", ", ".join(snap.certified_standards))
    elif assessed_norms:
        row("Certified standards",
            "None evidenced — working towards: " + ", ".join(assessed_norms))
    else:
        row("Certified standards", "—")

    if snap.key_roles:
        r = table.add_row()
        r.cells[0].text = "Key roles"
        run = r.cells[0].paragraphs[0].runs[0]
        run.font.bold = True
        run.font.color.rgb = C_GREY
        run.font.size = Pt(9)
        _set_cell_bg(r.cells[0], "F8FAFC")
        cell = r.cells[1]
        cell.text = ""
        for role in snap.key_roles:
            p = cell.add_paragraph(f"•  {role}")
            p.runs[0].font.size = Pt(10)

    doc.add_paragraph()
    if snap.scope_observations:
        _h3(doc, "Scope observations")
        _body(doc, snap.scope_observations)


# ── §3 Document Expiry Status (Sprint 4) ─────────────────────────────────────

def _add_expiry_section(doc: Document, report: ExpiryReport) -> None:
    _h1(doc, "§3  Document Expiry Status")

    _body(doc, (
        f"As of {report.audit_date}, {len(report.expired_documents)} document"
        f"{'s' if len(report.expired_documents) != 1 else ''} have expired"
        f" and {len(report.expiring_soon)} are due to expire within 90 days."
        f" {report.no_expiry_information} document"
        f"{'s carry' if report.no_expiry_information != 1 else ' carries'}"
        f" no expiry information."
    ))

    if report.expired_documents:
        _h2(doc, "Expired documents", color=C_MAJOR)
        _add_expiry_table(doc, report.expired_documents, label="Days overdue")

    if report.expiring_soon:
        doc.add_paragraph()
        _h2(doc, "Expiring within 90 days", color=C_MINOR)
        _add_expiry_table(doc, report.expiring_soon, label="Days until expiry", display_absolute=True)


def _add_expiry_table(
    doc: Document,
    docs: List[ExpiredDocument],
    label: str,
    display_absolute: bool = False,
) -> None:
    """Render a list of ExpiredDocument as a coloured table.

    `display_absolute` flips negative days_overdue values (expiring_soon)
    into positive numbers for readability.
    """
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    _set_col_widths(table, [Inches(2.7), Inches(1.1), Inches(0.9), Inches(0.8), Inches(1.0)])

    headers = ["File", "Doc type", "Expiry", label, "Severity"]
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        run = cell.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = C_WHITE
        _set_cell_bg(cell, "1B2944")

    # 2026-07: file omonimi in cartelle diverse (es. due "SLC.pdf") vanno
    # disambiguati con la cartella padre, altrimenti la riga sembra duplicata.
    base_counts: dict = {}
    for d in docs:
        base_counts[_last_path_segment(d.file_name)] = base_counts.get(_last_path_segment(d.file_name), 0) + 1

    def _display_name(path: str) -> str:
        base = _last_path_segment(path)
        if base_counts.get(base, 0) <= 1:
            return base
        parts = (path or "").replace("\\", "/").rsplit("/", 2)
        return "/".join(parts[-2:]) if len(parts) >= 2 else base

    for idx, d in enumerate(docs):
        r = table.add_row()
        days_value = abs(d.days_overdue) if display_absolute else d.days_overdue
        vals = [
            _display_name(d.file_name),
            d.doc_type,
            d.expiry_date,
            str(days_value),
            d.severity,
        ]
        for j, v in enumerate(vals):
            r.cells[j].text = v
            run = r.cells[j].paragraphs[0].runs[0]
            run.font.size = Pt(9)

        sev_color = SEVERITY_COLOR.get(d.severity, C_DARK)
        # Severity cell highlighted
        r.cells[4].paragraphs[0].runs[0].font.bold = True
        r.cells[4].paragraphs[0].runs[0].font.color.rgb = sev_color

        # Row tint by severity
        row_bg = "FEF2F2" if d.severity == "MAJOR" else "FFF7ED" if d.severity == "MINOR" else "FEFCE8" if d.severity == "OBSERVATION" else "F8FAFC"
        for cell in r.cells:
            _set_cell_bg(cell, row_bg)


def _last_path_segment(path: str) -> str:
    """Trim 'CONSORZIO JEOCON 14001/ALLEGATI/foo.pdf' to 'foo.pdf' for the table."""
    if not path:
        return ""
    p = path.replace("\\", "/")
    return p.rsplit("/", 1)[-1] if "/" in p else p


# ── §3b Required Documented Information (Sprint R6) ─────────────────────────

def _add_documented_info_section(doc: Document, report: DocumentedInfoReport) -> None:
    _h1(doc, "§3b  Required Documented Information")

    _body(doc, (
        f"The standards oblige the organisation to maintain or retain specific "
        f"documented information. Of the {len(report.items)} required items "
        f"checked, {report.found_count} were found in the package, "
        f"{report.weak_count} matched only weakly, and {report.absent_count} "
        f"could not be found anywhere — including under alternative names. "
        f"This check classifies documents by their content, never by file name."
    ))

    rows = [i for i in report.items if i.status in ("ABSENT", "FOUND_WEAK")]
    if not rows:
        return

    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    _set_col_widths(table, [Inches(2.2), Inches(1.1), Inches(0.9), Inches(1.0), Inches(1.3)])

    for i, h in enumerate(["Required item", "Standard", "Kind", "Status", "Note"]):
        cell = table.rows[0].cells[i]
        cell.text = h
        run = cell.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = C_WHITE
        _set_cell_bg(cell, "1B2944")

    for item in rows:
        r = table.add_row()
        status_label = "Not found" if item.status == "ABSENT" else "Weak match"
        note = (
            item.matched_file_name or ""
            if item.status == "FOUND_WEAK"
            else f"risk if missing: {item.risk_if_missing}"
        )
        vals = [
            item.item,
            item.norm.rsplit(":", 1)[0],
            item.retain_or_maintain.lower(),
            status_label,
            note,
        ]
        for j, v in enumerate(vals):
            r.cells[j].text = v
            run = r.cells[j].paragraphs[0].runs[0]
            run.font.size = Pt(9)

        sev_color = C_MAJOR if (item.status == "ABSENT" and item.risk_if_missing == "MAJOR") \
            else C_MINOR if item.status == "ABSENT" else C_OBSERVATION
        r.cells[3].paragraphs[0].runs[0].font.bold = True
        r.cells[3].paragraphs[0].runs[0].font.color.rgb = sev_color

        row_bg = "FEF2F2" if (item.status == "ABSENT" and item.risk_if_missing == "MAJOR") \
            else "FFF7ED" if item.status == "ABSENT" else "FEFCE8"
        for cell in r.cells:
            _set_cell_bg(cell, row_bg)


# ── §3c Cross-Clause Coherence (Sprint R6) ───────────────────────────────────

_CHAIN_STATUS_COLOR = {
    "LINKED":         C_CONFORMANT,
    "PARTIAL":        C_MINOR,
    "BROKEN":         C_MAJOR,
    "NOT_ASSESSABLE": C_GREY,
}

_CHAIN_STATUS_LABEL = {
    "LINKED":         "Linked",
    "PARTIAL":        "Partial",
    "BROKEN":         "Broken",
    "NOT_ASSESSABLE": "Not assessable",
}


def _add_cross_clause_section(doc: Document, findings: List[CrossClauseFinding]) -> None:
    _h1(doc, "§3c  Cross-Clause Coherence")

    _body(doc, (
        "A management system is more than its individual clauses: a risk "
        "identified in planning must have a corresponding operational control "
        "and a monitoring indicator; objectives must be measured and reviewed. "
        "The following chains were verified across the cited evidence."
    ))

    order = {"BROKEN": 0, "PARTIAL": 1, "NOT_ASSESSABLE": 2, "LINKED": 3}
    for f in sorted(findings, key=lambda x: order.get(x.status, 9)):
        p = doc.add_paragraph()
        badge = p.add_run(f"[{_CHAIN_STATUS_LABEL.get(f.status, f.status)}]  ")
        badge.font.bold = True
        badge.font.color.rgb = _CHAIN_STATUS_COLOR.get(f.status, C_DARK)
        title = p.add_run(f.title)
        title.font.bold = True
        # 2026-07: id leggibili — "(ISO 14001: 6.1.2 → 8.1 → 9.1)" invece dei
        # clause_id grezzi "14001_6_1_2 → …".
        chain_ids = " → ".join(_clause_display(cid) for cid in f.clause_ids)
        chain_label = f"{_short_norm(f.norm)}: {chain_ids}" if f.norm else chain_ids
        chain = p.add_run(f"   ({chain_label})")
        chain.font.size = Pt(8)
        chain.font.color.rgb = C_GREY
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)

        _body(doc, f.narrative)

        if f.sources:
            p3 = doc.add_paragraph()
            p3.add_run("Evidence: ").font.bold = True
            refs = []
            for s in f.sources[:3]:
                pages = ", ".join(f"p.{pg}" for pg in s.pages) if s.pages else ""
                refs.append(f"{_last_path_segment(s.file_name)}{' ' + pages if pages else ''}")
            run = p3.add_run(";  ".join(refs))
            run.font.size = Pt(9)
            run.font.color.rgb = C_GREY


# ── §3D Risk Register (Phase 2.7 — 2026-07) ──────────────────────────────────

def _add_risk_register_section(doc: Document, extract: RiskRegisterExtract) -> None:
    """Parità col frontend: registro rischi estratto, con i campi mancanti
    (score/mitigazione/owner) marcati in severity color. I dati vengono dal
    Phase 2.7 (estrazione strutturata + flag deterministici)."""
    _h1(doc, "§3D  Risk Register (as extracted)")

    _body(doc, (
        f"The analysis extracted a structured risk register from the risk "
        f"documents in the package: {extract.total_risks} risk"
        f"{'s' if extract.total_risks != 1 else ''} across "
        f"{len(extract.documents)} document{'s' if len(extract.documents) != 1 else ''}. "
        f"Of these, {extract.unscored_count} carry no score (assessment criteria "
        f"declared but not applied), {extract.unmitigated_count} have no stated "
        f"mitigation, and {extract.unowned_count} have no named owner. "
        f"Missing fields are highlighted below exactly as found — placeholder "
        f"text such as 'to be defined' counts as missing."
    ))

    for rdoc in extract.documents:
        _h2(doc, _last_path_segment(rdoc.file_name))
        if rdoc.methodology_declared and rdoc.methodology:
            p = doc.add_paragraph()
            p.add_run("Methodology declared: ").font.bold = True
            run = p.add_run(rdoc.methodology)
            run.font.size = Pt(9)
        else:
            p = doc.add_paragraph()
            run = p.add_run("No assessment methodology declared in this document.")
            run.font.color.rgb = C_MAJOR
            run.font.size = Pt(9)

        if not rdoc.risks:
            continue

        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        _set_col_widths(table, [Inches(0.6), Inches(2.5), Inches(0.7), Inches(1.7), Inches(1.0)])
        for i, h in enumerate(["Ref", "Risk", "Score", "Mitigation", "Owner"]):
            cell = table.rows[0].cells[i]
            cell.text = h
            run = cell.paragraphs[0].runs[0]
            run.font.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = C_WHITE
            _set_cell_bg(cell, "1B2944")

        for idx, risk in enumerate(rdoc.risks):
            r = table.add_row()
            vals = [
                risk.ref or "—",
                risk.description,
                risk.score if risk.score_present and risk.score else "not scored",
                risk.mitigation if risk.mitigation_present and risk.mitigation else "missing",
                risk.owner if risk.owner_present and risk.owner else "missing",
            ]
            for j, v in enumerate(vals):
                r.cells[j].text = v
                run = r.cells[j].paragraphs[0].runs[0]
                run.font.size = Pt(9)
            # Campi mancanti in severity color (flag deterministici Phase 2.7)
            if not risk.score_present:
                r.cells[2].paragraphs[0].runs[0].font.color.rgb = C_MAJOR
                r.cells[2].paragraphs[0].runs[0].font.bold = True
            if not risk.mitigation_present:
                r.cells[3].paragraphs[0].runs[0].font.color.rgb = C_MAJOR
                r.cells[3].paragraphs[0].runs[0].font.bold = True
            if not risk.owner_present:
                r.cells[4].paragraphs[0].runs[0].font.color.rgb = C_MINOR
                r.cells[4].paragraphs[0].runs[0].font.bold = True

            incomplete = not (risk.score_present and risk.mitigation_present and risk.owner_present)
            bg = "FFF7ED" if incomplete else ("F8FAFC" if idx % 2 == 0 else "FFFFFF")
            for cell in r.cells:
                _set_cell_bg(cell, bg)

        doc.add_paragraph()


# ── §5 Top 10 Priority Integrations (Sprint 4) ───────────────────────────────

def _add_priority_integrations(doc: Document, integrations: List[str]) -> None:
    _h1(doc, "§5  Top Priority Integrations")

    _body(doc, (
        "The following actions, in order of priority, are the recommended next "
        "steps. Each item references the underlying clause or expired document."
    ))

    items = integrations[:10]
    for i, action in enumerate(items, 1):
        p = doc.add_paragraph()
        idx_run = p.add_run(f"{i}.  ")
        idx_run.font.bold = True
        idx_run.font.color.rgb = C_DARK
        idx_run.font.size = Pt(11)

        body_run = p.add_run(action)
        body_run.font.size = Pt(10)
        p.paragraph_format.space_after = Pt(6)


# ── §6b Manually recorded nonconformities (Fase 4) ───────────────────────────

def _add_manual_ncs_section(doc: Document, manual_ncs: List[dict]) -> None:
    _h1(doc, "§6C  Manually Recorded Nonconformities")
    _body(doc, (
        "The following items were recorded directly by the organisation, "
        "alongside the findings produced by the analysis."
    ))
    for nc in manual_ncs:
        sev = str(nc.get("severity", "") or "").upper()
        p = doc.add_paragraph()
        badge = p.add_run(f"[{sev or 'NOTE'}]  ")
        badge.font.bold = True
        badge.font.color.rgb = SEVERITY_COLOR.get(sev, C_DARK)
        title = p.add_run(str(nc.get("title", "")))
        title.font.bold = True
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        if nc.get("description"):
            _body(doc, str(nc["description"]))
        meta = doc.add_paragraph()
        run = meta.add_run(
            f"Recorded by {nc.get('created_by') or 'unknown'}"
            f"  ·  status: {nc.get('status', 'open')}"
        )
        run.font.size = Pt(9)
        run.font.color.rgb = C_GREY


# ── §6c Set-aside findings (Fase 4 — PRD §1.4.8) ─────────────────────────────

def _add_set_aside_section(doc: Document, dismissed_rows: List[dict]) -> None:
    _h1(doc, "§6E  Set-aside Findings")
    _body(doc, (
        "The organisation has chosen to set aside the following findings. "
        "They are excluded from the action plan above but remain on record "
        "with the stated rationale — set-aside items are never deleted."
    ))

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    _set_col_widths(table, [Inches(1.8), Inches(0.8), Inches(2.5), Inches(1.2)])
    for i, h in enumerate(["Finding", "Severity", "Reason given", "Set aside by"]):
        cell = table.rows[0].cells[i]
        cell.text = h
        run = cell.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = C_WHITE
        _set_cell_bg(cell, "1B2944")

    for nc in dismissed_rows:
        r = table.add_row()
        label = str(nc.get("title") or nc.get("clause_id") or "")
        sev = str(nc.get("severity", "") or "").upper()
        vals = [
            label,
            sev,
            str(nc.get("dismiss_reason", "") or ""),
            str(nc.get("created_by", "") or ""),
        ]
        for j, v in enumerate(vals):
            r.cells[j].text = v
            run = r.cells[j].paragraphs[0].runs[0]
            run.font.size = Pt(9)
        if sev in SEVERITY_COLOR:
            r.cells[1].paragraphs[0].runs[0].font.color.rgb = SEVERITY_COLOR[sev]
        for cell in r.cells:
            _set_cell_bg(cell, "F8FAFC")


# ── §7 Methodology & Disclaimer (Sprint 4) ───────────────────────────────────

def _add_methodology(doc: Document, result: ComplianceAnalysisResult) -> None:
    _h1(doc, "§7  Methodology & Disclaimer")

    _h2(doc, "How this report was produced")
    _body(doc, (
        f"This analysis was generated by Amisys QHSE, an advisory tool that "
        f"reads documentation packages and maps the evidence against the "
        f"requirements of selected ISO management system standards. "
        f"For this report, {result.documents_analyzed} document"
        f"{'s were' if result.documents_analyzed != 1 else ' was'} processed "
        f"across "
        f"{', '.join(n.norm for n in result.norms)}."
    ))
    _body(doc, (
        "The pipeline runs in five stages: document extraction (with OCR "
        "fallback for scanned files), structured evidence-card extraction, "
        "deterministic expiry checking, clause-by-clause gap analysis grounded "
        "on the retrieved evidence, and report composition. Every finding in "
        "this report is tied to the underlying evidence cards via traceable "
        "references; citations are verified against the index post-generation."
    ))

    _h2(doc, "Limits of this analysis")
    _body(doc, (
        "Amisys QHSE is an advisory tool, not a certification service. It "
        "summarises documented evidence in the package provided and flags "
        "where requirements appear unmet. It does not interview personnel, "
        "observe processes on site, or examine documents outside the package. "
        "Operational practice may differ from documentation; an accredited "
        "certification body remains the only authority on conformity."
    ))

    _h2(doc, "Severity ladder")
    _body(doc, (
        "MAJOR — requirement absent, or evidence so incomplete it cannot "
        "support conformity; or a Single Point of Failure with low score. "
        "MINOR — requirement partially met; documented but with material gaps. "
        "OBSERVATION — improvement opportunity, no mandatory action. "
        "CONFORMANT — evidence present, current, and complete."
    ))
