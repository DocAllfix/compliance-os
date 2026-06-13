from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class CompanyContext(BaseModel):
    company_name: str
    sector: str          # Construction / Manufacturing / Services / Logistics / Healthcare / Energy / Other
    employee_range: str  # "1-10" / "11-50" / "51-250" / "250+"
    certified: str       # "yes" / "no" / "in_progress"
    sites_count: str     # "1" / "2-5" / "5+"
    norms: List[str]     # ["ISO 9001", "ISO 14001", "ISO 45001"]


class TraceabilityLink(BaseModel):
    evidence_id: str
    file_name: str
    pages: List[int]
    excerpt: str                       # verbatim quote from the document (Q12)
    relevance_score: float
    summary: Optional[str] = None      # LLM descriptive summary of the document (Q11)


class RemediationPlan(BaseModel):
    what: str
    who: str    # es. "Quality Manager", "HSE Officer"
    when: str   # es. "30 days", "3 months"
    effort: str  # LOW / MEDIUM / HIGH
    # Sprint R4 (PRD 1.4.7) — two-level remediation:
    #   correction        = immediate fix for the specific instance
    #   corrective_action = wider systemic fix preventing recurrence
    # `what` remains the primary action text for backwards compatibility.
    correction: Optional[str] = None
    corrective_action: Optional[str] = None


class RequirementCheck(BaseModel):
    """Sprint R4 — one atomic requirement verified by the deep pass."""
    requirement_id: str            # e.g. "9001_9_3.inputs.complete"
    status: str                    # PRESENT / PARTIAL / ABSENT
    evidence_quote: Optional[str] = None   # verbatim quote supporting the status
    pages: List[int] = []
    file_name: Optional[str] = None
    note: Optional[str] = None     # e.g. "resource adequacy not discussed"


class ClauseGap(BaseModel):
    clause_id: str       # es. "9001_8_4"
    clause_title: str    # es. "8.4 Control of externally provided processes"
    score: int           # 0-100
    severity: str        # MAJOR / MINOR / OBSERVATION / CONFORMANT
    is_spof: bool
    finding: str         # max 150 words, plain language UK English
    sources: List[TraceabilityLink]
    remediation: RemediationPlan
    # Sprint R4 (PRD 1.4.6) — reasoning exposure
    confidence: Optional[float] = None          # 0.0-1.0 verdict confidence
    requirement_checks: List[RequirementCheck] = []
    hedged: bool = False                        # True when evidence ambiguous
    hedge_note: Optional[str] = None
    deep_verified: bool = False                 # True when Stage B ran


class NormGapReport(BaseModel):
    norm: str            # "ISO 9001:2015"
    overall_score: int
    clauses: List[ClauseGap]
    major_count: int
    minor_count: int
    observation_count: int
    conformant_count: int
    spof_count: int


class ExpiredDocument(BaseModel):
    """One entry in the Phase 2.5 expiry check report.

    `days_overdue > 0`  → document has already expired N days ago
    `days_overdue == 0` → expires today
    `days_overdue < 0`  → expires in |N| days (placed in `expiring_soon`)
    """
    file_name: str
    doc_type: str
    evidence_id: str
    expiry_date: str           # YYYY-MM-DD
    days_overdue: int
    severity: str              # MAJOR / MINOR / OBSERVATION / INFO
    linked_iso_clauses: List[str]


class ExpiryReport(BaseModel):
    """Output of Phase 2.5 — structured extraction of document expiries.

    Generated from the evidence cards that carry an `expiry_date` field,
    computed against the analysis date. Severity rules are deterministic
    (see backend/compliance/expiry_check.py).
    """
    audit_date: str                              # YYYY-MM-DD
    expired_documents: List[ExpiredDocument]     # days_overdue >= 0
    expiring_soon: List[ExpiredDocument]         # days_overdue < 0 and >= -90
    no_expiry_information: int                   # count of cards with no expiry_date


class DocumentedInfoItem(BaseModel):
    """Sprint R3 — one required documented-information item (Phase 2.6)."""
    item: str                      # e.g. "Management review minutes"
    clause_id: str                 # e.g. "9001_9_3"
    norm: str                      # e.g. "ISO 9001:2015"
    retain_or_maintain: str        # MAINTAIN / RETAIN
    status: str                    # FOUND / FOUND_WEAK / ABSENT
    matched_evidence_id: Optional[str] = None
    matched_file_name: Optional[str] = None
    match_method: str = "none"     # metadata / semantic / llm_rescued / llm_confirmed_absent / not_found
    risk_if_missing: str = "MINOR"


class DocumentedInfoReport(BaseModel):
    """Phase 2.6 output — coverage of the standards' mandatory documented info."""
    items: List[DocumentedInfoItem]
    found_count: int
    weak_count: int
    absent_count: int


class RiskItem(BaseModel):
    """Sprint R8 (P2) — one risk extracted from a risk document."""
    ref: Optional[str] = None            # document's own id, e.g. "R-03"
    description: str
    category: Optional[str] = None       # risk / opportunity / document's own
    score: Optional[str] = None          # as written in the document
    score_present: bool = False
    mitigation: Optional[str] = None
    mitigation_present: bool = False
    owner: Optional[str] = None
    owner_present: bool = False
    pages: List[int] = []


class RiskDocumentExtract(BaseModel):
    """Structured extraction of one risk document."""
    file_name: str
    evidence_id: str
    methodology: Optional[str] = None    # declared assessment method
    methodology_declared: bool = False
    risks: List[RiskItem] = []


class RiskRegisterExtract(BaseModel):
    """Phase 2.7 output — the structured risk register across all risk docs."""
    documents: List[RiskDocumentExtract]
    total_risks: int
    unscored_count: int                  # entries without a score (criteria not applied)
    unmitigated_count: int
    unowned_count: int


class CrossClauseFinding(BaseModel):
    """Sprint R5 — one cross-clause coherence verdict (Phase 3.5)."""
    chain_id: str                  # e.g. "9001_risk_to_control"
    norm: str
    title: str                     # e.g. "Risk → operational control → monitoring"
    status: str                    # LINKED / PARTIAL / BROKEN / NOT_ASSESSABLE
    narrative: str                 # plain-language explanation, UK English
    clause_ids: List[str] = []
    sources: List[TraceabilityLink] = []


class CompanySnapshot(BaseModel):
    """Section 1 of the manager-facing report (executive summary)."""
    company_name: str
    sector: str
    size: str
    sites_summary: str
    key_roles: List[str]              # e.g. ["RSPP: Mario Rossi", "Quality Manager: Anna Bianchi"]
    certified_standards: List[str]    # certified or under analysis
    scope_observations: str


class ExecutiveSummary(BaseModel):
    """Phase 4 LLM output, attached to ComplianceAnalysisResult."""
    company_snapshot: CompanySnapshot
    top_priority_integrations: List[str]   # ordered, max 10, action-verb sentences
    executive_narrative: str               # 3-4 paragraphs, UK English


class ComplianceAnalysisResult(BaseModel):
    analysis_id: str
    company: str
    context: CompanyContext
    analysis_date: str
    norms: List[NormGapReport]
    documents_analyzed: int
    top_gaps: List[ClauseGap]                            # top 5 Major/SPoF cross-norma
    expiry_report: Optional[ExpiryReport] = None         # Phase 2.5 output (optional)
    executive_summary: Optional[ExecutiveSummary] = None # Phase 4 LLM output (optional)
    documented_info_report: Optional[DocumentedInfoReport] = None  # Phase 2.6 (Sprint R3)
    cross_clause_findings: List[CrossClauseFinding] = []           # Phase 3.5 (Sprint R5)
    risk_register_extract: Optional[RiskRegisterExtract] = None    # Phase 2.7 (Sprint R8, P2)
