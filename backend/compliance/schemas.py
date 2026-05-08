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
    excerpt: str
    relevance_score: float


class RemediationPlan(BaseModel):
    what: str
    who: str    # es. "Quality Manager", "HSE Officer"
    when: str   # es. "30 days", "3 months"
    effort: str  # LOW / MEDIUM / HIGH


class ClauseGap(BaseModel):
    clause_id: str       # es. "9001_8_4"
    clause_title: str    # es. "8.4 Control of externally provided processes"
    score: int           # 0-100
    severity: str        # MAJOR / MINOR / OBSERVATION / CONFORMANT
    is_spof: bool
    finding: str         # max 150 words, plain language UK English
    sources: List[TraceabilityLink]
    remediation: RemediationPlan


class NormGapReport(BaseModel):
    norm: str            # "ISO 9001:2015"
    overall_score: int
    clauses: List[ClauseGap]
    major_count: int
    minor_count: int
    observation_count: int
    conformant_count: int
    spof_count: int


class ComplianceAnalysisResult(BaseModel):
    analysis_id: str
    company: str
    context: CompanyContext
    analysis_date: str
    norms: List[NormGapReport]
    documents_analyzed: int
    top_gaps: List[ClauseGap]  # top 5 Major/SPoF cross-norma
