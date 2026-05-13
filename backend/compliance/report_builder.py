"""
ComplianceOS — DOCX Report Builder.

Produces a manager-friendly gap analysis report using python-docx.

Structure (Sprint 4 — 7 sections):
  Cover page
  §1 Company Snapshot                      (from executive_summary.company_snapshot)
  §2 Executive Narrative                   (from executive_summary.executive_narrative)
  §3 Document Expiry Status                (from expiry_report)
  §4 Single Points of Failure              (if any)
  §5 Top 10 Priority Integrations          (from executive_summary.top_priority_integrations)
  §6 Detailed Clause Analysis              (per-norm: Critical Findings, Action Plan, Clause Matrix)
  §7 Methodology & Disclaimer

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
    ExpiredDocument,
    ExpiryReport,
    NormGapReport,
)


# ── Colour constants ──────────────────────────────────────────────────────────

C_MAJOR       = RGBColor(0xDC, 0x26, 0x26)
C_MINOR       = RGBColor(0xF9, 0x73, 0x16)
C_OBSERVATION = RGBColor(0xCA, 0x8A, 0x04)
C_CONFORMANT  = RGBColor(0x16, 0xA3, 0x4A)
C_SPOF        = RGBColor(0xEA, 0x58, 0x0C)
C_DARK        = RGBColor(0x1E, 0x29, 0x3B)
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

def build_docx_report(result: ComplianceAnalysisResult) -> bytes:
    """
    Build a DOCX report from a ComplianceAnalysisResult. Returns the raw
    bytes of the .docx file.

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

    _add_cover(doc, result)
    doc.add_page_break()

    # §1 Company Snapshot — only when the LLM produced an executive summary
    if result.executive_summary is not None:
        _add_company_snapshot(doc, result.executive_summary.company_snapshot)
        doc.add_page_break()

    # §2 Executive Narrative + legacy per-norm summary
    _add_executive_summary(doc, result)
    doc.add_page_break()

    # §3 Document Expiry Status — only when Phase 2.5 ran and produced output
    if result.expiry_report is not None and (
        result.expiry_report.expired_documents or result.expiry_report.expiring_soon
    ):
        _add_expiry_section(doc, result.expiry_report)
        doc.add_page_break()

    all_gaps = [g for norm in result.norms for g in norm.clauses]
    spof_gaps = [g for g in all_gaps if g.is_spof and g.severity == "MAJOR"]

    # §4 Single Points of Failure
    if spof_gaps:
        _add_spof_section(doc, spof_gaps)
        doc.add_page_break()

    # §5 Top 10 Priority Integrations — manager-friendly bullet list
    if result.executive_summary is not None and result.executive_summary.top_priority_integrations:
        _add_priority_integrations(doc, result.executive_summary.top_priority_integrations)
        doc.add_page_break()

    # §6 Detailed Clause Analysis
    major_gaps = [g for g in all_gaps if g.severity == "MAJOR"]
    if major_gaps:
        _add_critical_findings(doc, major_gaps)
        doc.add_page_break()

    actionable = [g for g in all_gaps if g.severity in ("MAJOR", "MINOR")]
    if actionable:
        _add_action_plan(doc, actionable)
        doc.add_page_break()

    for norm_report in result.norms:
        _add_clause_matrix(doc, norm_report)
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
    doc.add_paragraph()
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
    run2.font.color.rgb = C_MAJOR

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
    _add_centred(doc, f"Prepared for {result.company} by ComplianceOS", size=9, color=C_GREY, italic=True)
    _add_centred(doc, f"Documents analysed: {result.documents_analyzed}", size=9, color=C_GREY, italic=True)


# ── Executive Summary ─────────────────────────────────────────────────────────

def _add_executive_summary(doc: Document, result: ComplianceAnalysisResult) -> None:
    _h1(doc, "Executive Summary")

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

        # Top 3 risks
        top = sorted(
            [g for g in norm.clauses if g.severity in ("MAJOR", "MINOR")],
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

def _add_spof_section(doc: Document, spofs: List[ClauseGap]) -> None:
    _h1(doc, "Single Points of Failure")

    p = doc.add_paragraph()
    r = p.add_run("The following clauses represent Single Points of Failure (SPoF) — their absence or failure undermines the entire management system and must be addressed before any other non-conformity.")
    r.font.color.rgb = C_SPOF
    r.font.italic = True

    doc.add_paragraph()

    for gap in spofs:
        _h2(doc, f"⚠  {gap.clause_title}", color=C_SPOF)
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

def _add_critical_findings(doc: Document, majors: List[ClauseGap]) -> None:
    _h1(doc, "Critical Findings")

    for gap in majors:
        _h2(doc, gap.clause_title, color=C_MAJOR)

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
        add_row("Score", f"{gap.score}/100 — {gap.severity}", SEVERITY_COLOR.get(gap.severity))
        add_row("Finding", gap.finding)
        if gap.sources:
            sources_str = "; ".join(
                f"{s.file_name}{', p.' + str(s.pages[0]) if s.pages else ''}"
                for s in gap.sources[:3]
            )
            add_row("Evidence", sources_str)
        add_row("Action", gap.remediation.what)
        add_row("Responsible", gap.remediation.who)
        add_row("Deadline", gap.remediation.when)
        add_row("Effort", gap.remediation.effort)

        doc.add_paragraph()


# ── Action Plan table ─────────────────────────────────────────────────────────

def _add_action_plan(doc: Document, gaps: List[ClauseGap]) -> None:
    _h1(doc, "Action Plan")

    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_col_widths(table, [Inches(0.6), Inches(1.3), Inches(2.3), Inches(1.2), Inches(0.9), Inches(0.7)])

    headers = ["Priority", "Clause", "Action", "Responsible", "Deadline", "Effort"]
    hrow = table.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]
        cell.text = h
        p = cell.paragraphs[0]
        p.runs[0].font.bold  = True
        p.runs[0].font.size  = Pt(9)
        p.runs[0].font.color.rgb = C_WHITE
        _set_cell_bg(cell, "1E293B")

    sorted_gaps = sorted(gaps, key=lambda g: (0 if g.is_spof else 1, 0 if g.severity == "MAJOR" else 1, g.score))

    for i, gap in enumerate(sorted_gaps, 1):
        row = table.add_row()
        vals = [
            str(i),
            gap.clause_id.replace("_", " "),
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

def _add_clause_matrix(doc: Document, norm: NormGapReport) -> None:
    _h1(doc, f"Clause Matrix — {norm.norm}")

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
        _set_cell_bg(cell, "1E293B")

    sorted_clauses = sorted(norm.clauses, key=lambda g: (
        0 if g.is_spof and g.severity == "MAJOR" else 1,
        {"MAJOR": 0, "MINOR": 1, "OBSERVATION": 2, "CONFORMANT": 3}.get(g.severity, 9),
        g.score,
    ))

    for i, gap in enumerate(sorted_clauses):
        row = table.add_row()
        row.cells[0].text = gap.clause_id
        row.cells[1].text = gap.clause_title
        row.cells[2].text = str(gap.score)
        row.cells[3].text = f"{'⚠ SPoF + ' if gap.is_spof else ''}{gap.severity}"

        color = SEVERITY_COLOR.get(gap.severity, C_DARK)
        for cell in row.cells:
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
        row.cells[2].paragraphs[0].runs[0].font.color.rgb = color
        row.cells[3].paragraphs[0].runs[0].font.color.rgb = color
        if gap.is_spof:
            row.cells[3].paragraphs[0].runs[0].font.bold = True

        bg = "FEF2F2" if gap.severity == "MAJOR" else "FFF7ED" if gap.severity == "MINOR" else "F8FAFC" if i % 2 == 0 else "FFFFFF"
        for cell in row.cells:
            _set_cell_bg(cell, bg)


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    bottom.set(qn("w:color"), "1E293B")
    pBdr.append(bottom)
    pPr.append(pBdr)


# ── §1 Company Snapshot (Sprint 4) ───────────────────────────────────────────

def _add_company_snapshot(doc: Document, snap: CompanySnapshot) -> None:
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
    row("Standards", ", ".join(snap.certified_standards) if snap.certified_standards else "—")

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
        _set_cell_bg(cell, "1E293B")

    for idx, d in enumerate(docs):
        r = table.add_row()
        days_value = abs(d.days_overdue) if display_absolute else d.days_overdue
        vals = [
            _last_path_segment(d.file_name),
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


# ── §7 Methodology & Disclaimer (Sprint 4) ───────────────────────────────────

def _add_methodology(doc: Document, result: ComplianceAnalysisResult) -> None:
    _h1(doc, "§7  Methodology & Disclaimer")

    _h2(doc, "How this report was produced")
    _body(doc, (
        f"This analysis was generated by ComplianceOS, an advisory tool that "
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
        "ComplianceOS is an advisory tool, not a certification service. It "
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
