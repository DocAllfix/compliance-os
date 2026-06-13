"""
ISO 9001:2015 clause knowledge base.

Each entry defines the clause's identity, risk profile, sector criticality,
typical non-conformities, ChromaDB evidence keywords, and remediation templates.
Used by the gap analyser to score and triage findings.

Derived metadata (added by Sprint 0):
    Four extra fields are *derived at read time* by `backend.compliance.clause_helpers`
    rather than hard-coded here, to avoid bulk editing every clause dict:

      • criticality_tier  → "critical" if is_spof OR in ISO9001_HIGH_FREQUENCY_CLAUSES,
                            "passing" for §4.x context clauses, else "standard"
      • severity_floor    → "MAJOR" for critical, "MINOR" for standard, None for passing
      • weight            → 5 / 3 / 1 (critical / standard / passing)
      • expiry_relevant   → True if title/area mentions training, calibration,
                            internal audit, documented information, CAPA, etc.

    Any clause MAY override a derived field by setting it explicitly in the dict
    (e.g. `"severity_floor": "MAJOR"` to force a stricter floor on a non-SPoF
    clause). When present, the explicit value always wins over the derived one.

Tier distribution for ISO 9001 (computed at runtime — see Sprint 0 validation):
    critical ≈ 10 clauses (5.1, 6.1, 7.2, 7.3, 7.5, 8.4, 9.2, 9.3, 10.2 + the
              other HIGH_FREQUENCY entries)
    passing  ≈ 4 clauses (§4.1, §4.2, §4.3, §4.4)
    standard ≈ 13 clauses (the rest)
"""
from __future__ import annotations

from typing import Dict, Any

# Algorithmic classification rules from the Knowledge Base (§1.3)
# Used by gap_analyzer to upgrade/escalate severity programmatically.
ISO9001_SEVERITY_RULES = [
    "MAJOR if the requirement is not implemented at all (process non-existent, no document, no evidence).",
    "MAJOR if a procedure exists but the instance is non-conformant AND errors are repeated or diffuse across departments.",
    "MINOR if a procedure exists and this is an isolated, single instance of non-conformance.",
    "MAJOR (at minimum) if legal/regulatory violation or serious risk to persons, environment, or customers is involved.",
    "Escalate MINOR to MAJOR if the same NC was previously recorded and the corrective action was not effective.",
    "SPOF flag applies when a MAJOR NC affects a clause marked is_spof=True.",
]

# The top NC cluster frequency from real audit data (§3.1 of Knowledge Base)
# Used for weighting and prioritisation in the gap report.
ISO9001_HIGH_FREQUENCY_CLAUSES = [
    "9001_7_5",   # Document control
    "9001_9_2",   # Internal audit
    "9001_9_3",   # Management review
    "9001_10_2",  # Nonconformity and corrective action
    "9001_7_2",   # Competence
    "9001_7_3",   # Awareness
    "9001_6_1",   # Risk and opportunities
    "9001_8_4",   # Supplier management
]

ISO9001_CLAUSES: Dict[str, Dict[str, Any]] = {

    # ── Section 4: Context of the Organisation ──────────────────────────────

    "9001_4_1": {
        "id": "9001_4_1",
        "title": "4.1 Understanding the organisation and its context",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No documented analysis of internal and external issues",
            "SWOT or PESTLE analysis not linked to the QMS scope",
            "Issues not reviewed at management review",
        ],
        "evidence_keywords": [
            "context", "internal issues", "external issues", "SWOT", "PESTLE",
            "strategic direction", "organisational context",
        ],
        "remediation_template": {
            "what": "Document a structured analysis of internal and external issues relevant to the organisation's purpose. Link findings to QMS scope and review at management review.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "9001_4_2": {
        "id": "9001_4_2",
        "title": "4.2 Understanding the needs and expectations of interested parties",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": ["Construction", "Healthcare"],
        "typical_ncs": [
            "Interested parties not identified beyond customers",
            "Requirements of regulatory bodies not captured",
            "No process to monitor changes in stakeholder requirements",
        ],
        "evidence_keywords": [
            "interested parties", "stakeholders", "requirements", "expectations",
            "regulatory", "customers", "suppliers", "employees",
        ],
        "remediation_template": {
            "what": "Identify all relevant interested parties and their requirements. Document a register and establish a review cycle.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "LOW",
        },
    },

    "9001_4_3": {
        "id": "9001_4_3",
        "title": "4.3 Determining the scope of the quality management system",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Scope not documented or not maintained as documented information",
            "Exclusions not justified",
            "Scope does not reflect actual products and services",
        ],
        "evidence_keywords": [
            "scope", "QMS scope", "exclusions", "products and services",
            "documented information", "boundaries",
        ],
        "remediation_template": {
            "what": "Define and document the QMS scope, including boundaries, applicable standards, and any justified exclusions.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    "9001_4_4": {
        "id": "9001_4_4",
        "title": "4.4 Quality management system and its processes",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Process interactions not defined",
            "No process owner accountability",
            "Inputs and outputs of key processes not documented",
        ],
        "evidence_keywords": [
            "process", "process map", "turtle diagram", "inputs", "outputs",
            "process owner", "process interaction", "sequence",
        ],
        "remediation_template": {
            "what": "Map all QMS processes, define inputs/outputs, assign ownership, and document interactions between processes.",
            "who": "Quality Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 5: Leadership ────────────────────────────────────────────────

    "9001_5_1": {
        "id": "9001_5_1",
        "title": "5.1 Leadership and commitment",
        "area": "Leadership",
        "is_spof": True,
        "critical_sectors": ["Construction", "Manufacturing", "Healthcare", "Energy"],
        "typical_ncs": [
            "No evidence of top management involvement in QMS",
            "Quality policy not communicated or understood by staff",
            "Management review not conducted by top management",
        ],
        "evidence_keywords": [
            "top management", "leadership", "commitment", "management review",
            "quality policy", "accountability", "resources",
        ],
        # Sprint R8 — atomic_requirements (Template9001.docx §5.1.1 + ISO 9001
        # §5.1). Documentation-verifiable items only: interview-based checks
        # (PRD 1.7.3 — documentation audit) are out of scope by design.
        "atomic_requirements": [
            {
                "id": "9001_5_1.policy_objectives.established",
                "text": "Top management has established the quality policy and quality objectives, aligned with the strategic direction and the business of the certified products/services.",
                "verification_hint": "Signed policy + objectives traceable to strategy; coherent themes across policy, objectives and context analysis.",
                "expected_evidence": ["policy", "objective_plan", "quality_manual"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_5_1.objectives.cascaded",
                "text": "Objectives are cascaded within the organisation (declined to functions/departments) and their implementation status is verified.",
                "verification_hint": "Departmental targets, progress reviews, objective status discussed in records (checklist 5.1.1: declinazione + verifica stato di attuazione).",
                "expected_evidence": ["objective_plan", "record", "management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_5_1.resources.allocated",
                "text": "Evidence exists that top management ensures the availability of resources for the QMS (budget, people, infrastructure decisions).",
                "verification_hint": "Resource decisions in management review outputs, investment records, appointments.",
                "expected_evidence": ["management_review", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_5_1.review.led",
                "text": "Top management leads the management review and takes accountability for QMS effectiveness (participation documented).",
                "verification_hint": "MR minutes list top management among attendees; decisions signed off at that level.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_5_1.importance.communicated",
                "text": "The importance of effective quality management and of conforming to QMS requirements is communicated within the organisation.",
                "verification_hint": "Communications, inductions, briefings or policy distribution evidence referencing QMS importance.",
                "expected_evidence": ["communication_record", "training_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish documented evidence of top management engagement: signed quality policy, management review minutes, and resource allocation records.",
            "who": "Managing Director / CEO",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "9001_5_2": {
        "id": "9001_5_2",
        "title": "5.2 Policy",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Quality policy not available as documented information",
            "Policy not communicated to all relevant parties",
            "Policy does not include a commitment to continual improvement",
        ],
        "evidence_keywords": [
            "quality policy", "policy statement", "commitment", "continual improvement",
            "customer focus", "communicated",
        ],
        # Sprint R3 — atomic_requirements from audit checklist guidance
        # (checklistevidence/Template9001.docx §5.2) + ISO 9001:2015 §5.2 text.
        # These are WORDING checks: the policy must contain the commitments,
        # not merely exist as a document (promise P4).
        "atomic_requirements": [
            {
                "id": "9001_5_2.policy.documented",
                "text": "A quality policy exists as documented information, identifiable as the current approved version (signed and/or dated).",
                "verification_hint": "Policy document or section of the quality manual; approval signature or issue/revision date present.",
                "expected_evidence": ["policy", "quality_manual"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_5_2.commitment.requirements",
                "text": "The policy wording contains an explicit commitment to satisfy applicable requirements (customer, statutory and regulatory).",
                "verification_hint": "Look for the commitment IN THE TEXT itself — phrases equivalent to 'committed to meeting customer and applicable statutory/regulatory requirements'. A policy that only describes the business does not meet this.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                # Sprint R7 — deterministic wording check: the evidence quote
                # must contain ≥1 term from EVERY group (EN+IT variants).
                "wording_keywords": [["requirement", "requisit"], ["customer", "statutory", "regulatory", "applicable", "client", "cogent"]],
            },
            {
                "id": "9001_5_2.commitment.improvement",
                "text": "The policy wording contains an explicit commitment to continual improvement of the quality management system.",
                "verification_hint": "Wording equivalent to 'continual improvement of the QMS' must be present verbatim or near-verbatim in the policy text.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                "wording_keywords": [["improv", "migliora", "enhanc", "perfezion", "ottimizz"]],
            },
            {
                "id": "9001_5_2.framework.objectives",
                "text": "The policy provides a framework for setting quality objectives (objective themes are traceable to policy statements).",
                "verification_hint": "Cross-check: themes in the policy correspond to documented objectives (6.2) or the policy explicitly references objective setting.",
                "expected_evidence": ["policy", "objective_plan"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_5_2.context.coherence",
                "text": "The policy content is appropriate to the organisation's purpose and context — coherent with the context analysis, customer needs, strategy and interested-party requirements, not generic boilerplate.",
                "verification_hint": "Compare policy themes against the context analysis (4.1/4.2) and the actual products/services; sector-agnostic template text with no organisation-specific content fails this.",
                "expected_evidence": ["policy", "quality_manual"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_5_2.communicated",
                "text": "The policy is communicated within the organisation and available to relevant interested parties.",
                "verification_hint": "Distribution evidence: communication records, intranet/noticeboard reference, website availability, training/induction records mentioning the policy.",
                "expected_evidence": ["communication_record", "policy", "training_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Issue a signed, dated quality policy that includes commitment to customer requirements and continual improvement. Communicate to all staff and make available to interested parties.",
            "who": "Managing Director",
            "when_major": "14 days",
            "when_minor": "30 days",
            "effort": "LOW",
        },
    },

    "9001_5_3": {
        "id": "9001_5_3",
        "title": "5.3 Organisational roles, responsibilities and authorities",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No documented organisation chart or role descriptions",
            "QMS responsibilities not assigned to specific roles",
            "Management representative role not defined",
        ],
        "evidence_keywords": [
            "roles", "responsibilities", "authorities", "organisation chart",
            "job description", "management representative", "accountability",
        ],
        "remediation_template": {
            "what": "Document roles, responsibilities and authorities for QMS functions. Publish an organisation chart and assign a QMS management representative.",
            "who": "HR Manager / Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    # ── Section 6: Planning ──────────────────────────────────────────────────

    "9001_6_1": {
        "id": "9001_6_1",
        "title": "6.1 Actions to address risks and opportunities",
        "area": "Planning",
        "is_spof": True,
        "critical_sectors": ["Construction", "Manufacturing", "Logistics", "Energy"],
        "typical_ncs": [
            "No risk register linked to QMS processes",
            "Risks identified but no mitigation actions defined",
            "Opportunities not considered alongside risks",
        ],
        "evidence_keywords": [
            "risk", "opportunity", "risk register", "risk assessment",
            "mitigation", "preventive action", "risk-based thinking",
        ],
        # Sprint R3 — atomic_requirements from audit checklist guidance
        # (Template9001.docx §6.1) + ISO 9001:2015 §6.1. Core of promise P2:
        # the engine verifies that risk criteria are APPLIED, not just declared.
        "atomic_requirements": [
            {
                "id": "9001_6_1.risks.identified",
                "text": "Risks AND opportunities are determined, linked to the organisation's context (4.1) and interested-party requirements (4.2).",
                "verification_hint": "Risk register, FMEA, SWOT-derived register or equivalent; entries reference QMS objectives or context issues. Opportunities must appear, not only threats.",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_6_1.methodology.defined",
                "text": "A method and criteria for analysing and classifying risks are defined (e.g. probability x severity matrix, FMEA scoring, qualitative classes).",
                "verification_hint": "The document states HOW risks are scored or ranked: scales, thresholds, classification rules.",
                "expected_evidence": ["risk_assessment", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_6_1.criteria.applied",
                "text": "The declared criteria are actually APPLIED: each risk entry carries the score/class produced by the stated method — the methodology is not merely described.",
                "verification_hint": "Spot-check register entries: every risk has a value/class consistent with the declared scale. A methodology chapter followed by an unscored risk list fails this item.",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_6_1.actions.planned",
                "text": "Actions to address the identified risks and opportunities are planned, with an owner for each significant entry.",
                "verification_hint": "Mitigation/exploitation actions column or linked action plan; named role or person responsible.",
                "expected_evidence": ["risk_assessment", "objective_plan", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_6_1.integration",
                "text": "The planned actions are integrated into QMS processes and their effectiveness is evaluated (links to operational controls in 8.1 and monitoring in 9.1).",
                "verification_hint": "Actions reference the affected process/procedure; effectiveness review at management review or in monitoring records.",
                "expected_evidence": ["risk_assessment", "management_review", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_6_1.review.planned",
                "text": "The risk analysis is kept current: a revision need or review cadence is identified (e.g. reviewed at management review or on significant change).",
                "verification_hint": "Revision date/history on the register; risk review as a management review input.",
                "expected_evidence": ["risk_assessment", "management_review"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish a risk and opportunity register linked to QMS processes. Define mitigation actions, assign owners, and review at management review.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "9001_6_2": {
        "id": "9001_6_2",
        "title": "6.2 Quality objectives and planning to achieve them",
        "area": "Planning",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Quality objectives not documented or not measurable",
            "No action plan to achieve objectives",
            "Objectives not communicated to relevant functions",
        ],
        "evidence_keywords": [
            "quality objectives", "KPI", "targets", "measurable",
            "action plan", "monitoring", "performance indicators",
        ],
        # Sprint R3 — atomic_requirements from audit checklist guidance
        # (Template9001.docx §6.2.2: "obiettivi concreti e misurabili") + ISO
        # 9001:2015 §6.2. Core of promise P5: measurable (metric, target,
        # deadline) vs merely declared. Recognition is label-agnostic:
        # objectives may be called targets, KPIs, indicators, goals.
        "atomic_requirements": [
            {
                "id": "9001_6_2.objectives.documented",
                "text": "Quality objectives exist as documented information at relevant functions and levels — regardless of the label used (objectives, targets, KPIs, indicators, goals).",
                "verification_hint": "Objective plan, KPI sheet, balanced scorecard, strategic plan section, or objectives embedded in the manual / management review.",
                "expected_evidence": ["objective_plan", "record", "management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_6_2.objectives.measurable",
                "text": "Each objective is measurable: it carries a metric AND a target value, not only a declared intention ('improve customer satisfaction' without metric/target fails).",
                "verification_hint": "Per-objective check: is there a number/threshold and a measuring unit or defined indicator? Count how many entries are measurable vs declared-only and name the failures.",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_6_2.objectives.deadline",
                "text": "Each objective carries a timescale or deadline for achievement.",
                "verification_hint": "Date / quarter / 'by end of year' per entry. Objectives with metric and target but no time bound are PARTIAL.",
                "expected_evidence": ["objective_plan"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_6_2.plan.defined",
                "text": "Planning to achieve the objectives is defined: what will be done, resources required, who is responsible, and how results will be evaluated.",
                "verification_hint": "Action plan columns or linked actions: activity, owner, resources, evaluation method.",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_6_2.coherence",
                "text": "Objectives are consistent with the quality policy and take account of the risks and opportunities identified in 6.1.",
                "verification_hint": "Cross-check objective themes against policy commitments and risk register entries (strategies, market analysis, customer and statutory requirements, process and risk analysis).",
                "expected_evidence": ["objective_plan", "policy", "risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_6_2.monitored",
                "text": "Objectives are monitored and updated: status reviews exist (KPI dashboards, management review discussion, periodic progress records).",
                "verification_hint": "Evidence of actual values vs target over time; objectives as a management review input.",
                "expected_evidence": ["record", "management_review", "objective_plan"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define SMART quality objectives at relevant functions. Document an action plan with owners, timescales, and measurement criteria.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 7: Support ───────────────────────────────────────────────────

    "9001_7_1": {
        "id": "9001_7_1",
        "title": "7.1 Resources",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Healthcare"],
        "typical_ncs": [
            "No evidence of infrastructure suitability assessment",
            "Monitoring and measuring equipment not identified",
            "Organisational knowledge not captured",
        ],
        "evidence_keywords": [
            "resources", "infrastructure", "equipment", "monitoring",
            "measuring equipment", "calibration", "knowledge", "environment",
        ],
        "remediation_template": {
            "what": "Document resource requirements including infrastructure, monitoring equipment, and organisational knowledge. Establish a calibration schedule for measuring equipment.",
            "who": "Operations Manager / Quality Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "9001_7_2": {
        "id": "9001_7_2",
        "title": "7.2 Competence",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": ["Construction", "Healthcare", "Energy"],
        "typical_ncs": [
            "Training records incomplete or missing for key roles",
            "Competence requirements not defined for QMS-related roles",
            "No evidence of competence evaluation after training",
        ],
        "evidence_keywords": [
            "competence", "training", "training records", "skills",
            "qualifications", "awareness", "personnel", "evaluation",
        ],
        # Sprint R8 — atomic_requirements (Template9001.docx §7.2 + ISO 9001
        # §7.2). Key audit insight from the checklist: competence is broader
        # than training — define requirements per role, then evidence them.
        "atomic_requirements": [
            {
                "id": "9001_7_2.requirements.defined",
                "text": "Competence requirements are defined per role/activity affecting quality performance — not just generic training plans.",
                "verification_hint": "Job descriptions, competence matrices or role profiles stating the required knowledge/skills per activity.",
                "expected_evidence": ["procedure", "record", "training_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_7_2.evidence.retained",
                "text": "Documented evidence of competence is retained (training records, qualifications, certificates, experience records).",
                "verification_hint": "Training logs, attestati, certificates on file matching the people and roles in scope.",
                "expected_evidence": ["training_record", "certificate", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_7_2.external.covered",
                "text": "Competence control covers persons working under the organisation's control who are NOT employees (external workers, outsourcers) where they affect quality.",
                "verification_hint": "Supplier/contractor competence evidence or contractual competence requirements (checklist 7.2: 'sia interne, sia esterne').",
                "expected_evidence": ["supplier_document", "training_record", "contract_specification"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_7_2.effectiveness.evaluated",
                "text": "The effectiveness of actions taken to acquire competence is evaluated (not just attendance recorded).",
                "verification_hint": "Post-training evaluations, on-the-job verifications, qualification sign-offs.",
                "expected_evidence": ["training_record", "record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define competence requirements for all roles affecting quality. Update training records and implement a training matrix with competence evaluation.",
            "who": "HR Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "9001_7_3": {
        "id": "9001_7_3",
        "title": "7.3 Awareness",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Staff unaware of the quality policy",
            "No evidence of QMS awareness communication",
            "Personnel not aware of their contribution to QMS objectives",
        ],
        "evidence_keywords": [
            "awareness", "communication", "quality policy", "induction",
            "briefing", "toolbox talk", "staff", "contribution",
        ],
        # Sprint R8 — atomic_requirements (Template9001.docx §7.3 + ISO 9001
        # §7.3). Awareness covers employees AND external persons involved in
        # the organisation's processes.
        "atomic_requirements": [
            {
                "id": "9001_7_3.policy_objectives.awareness",
                "text": "Evidence exists that persons doing work under the organisation's control are made aware of the quality policy and the relevant quality objectives.",
                "verification_hint": "Induction packs, briefings, training content or communications covering policy and objectives.",
                "expected_evidence": ["training_record", "communication_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_7_3.contribution.awareness",
                "text": "Awareness activities cover each person's contribution to QMS effectiveness and the benefits of improved performance.",
                "verification_hint": "Induction/briefing content explaining roles' contribution, not only generic policy reading.",
                "expected_evidence": ["training_record", "communication_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_7_3.nc_implications.awareness",
                "text": "Awareness activities cover the implications of not conforming with QMS requirements.",
                "verification_hint": "Materials/communications addressing consequences of non-conformity for the organisation and the person's work.",
                "expected_evidence": ["training_record", "communication_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_7_3.external.included",
                "text": "Awareness extends to non-employee persons involved in the organisation's processes (contractors, outsourcers) where relevant.",
                "verification_hint": "Contractor induction evidence or contractual awareness requirements (checklist 7.3: 'comprensivo anche di fornitori ed outsourcers').",
                "expected_evidence": ["communication_record", "supplier_document"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Implement an awareness programme covering the quality policy, QMS objectives, and individual contributions. Record evidence of communication.",
            "who": "HR Manager / Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    "9001_7_4": {
        "id": "9001_7_4",
        "title": "7.4 Communication",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No documented communication plan",
            "External communication process not defined",
            "No records of internal QMS communications",
        ],
        "evidence_keywords": [
            "communication", "internal communication", "external communication",
            "communication plan", "stakeholder", "meeting minutes",
        ],
        "remediation_template": {
            "what": "Document a communication plan defining what, when, to whom, and how QMS-related information is communicated internally and externally.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    "9001_7_5": {
        "id": "9001_7_5",
        "title": "7.5 Documented information",
        "area": "Support",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if document control procedure absent or not extended to all processes; PUNCTUAL if isolated documents missing version/date/signature",
        "critical_sectors": ["Construction", "Manufacturing", "Healthcare", "Logistics"],
        "typical_ncs": [
            "Unstructured document system; no document control procedure extended to all processes",
            "Non-standardised templates; no version control or approval in critical areas",
            "Responsibilities for document management not assigned",
            "Multiple inconsistent copies of documents in circulation",
            "Fields marked 'n.d.' or blank in mandatory document fields",
        ],
        "evidence_keywords": [
            "document control", "documented information", "version control",
            "approval", "retention", "records", "document register",
            "revision history", "DMS", "quality manual", "procedure",
            "signed", "dated", "approved",
        ],
        # Sprint J — atomic_requirements derived from Master KB §3.2.1.
        "atomic_requirements": [
            {
                "id": "9001_7_5.procedure.exists",
                "text": "A documented procedure for document control exists, covering creation, approval, distribution, revision and obsolete-copy handling.",
                "verification_hint": "Procedure document referencing §7.5 or equivalent; defines lifecycle from draft to obsolete.",
                "expected_evidence": ["procedure", "quality_manual"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_7_5.metadata.completeness",
                "text": "Controlled documents carry mandatory metadata: version, date, author, approver.",
                "verification_hint": "Spot-check documents: presence of version, issue/revision date, signatures (or electronic equivalents).",
                "expected_evidence": ["procedure", "policy", "quality_manual"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_7_5.coverage.all_processes",
                "text": "Document control covers all key processes (not only a subset).",
                "verification_hint": "Document register / index spans the full management system scope.",
                "expected_evidence": ["record", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_7_5.obsolete_control",
                "text": "Obsolete documents are clearly identified and removed or marked as such.",
                "verification_hint": "Procedure references obsolete-copy handling; no draft/obsolete versions in active use.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_7_5.access_control",
                "text": "Access to documented information is controlled (viewing/editing rights defined).",
                "verification_hint": "Procedure or DMS configuration shows who can read, edit, approve which documents.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Issue or update procedure 7.5 with roles and workflow. Implement a centralised document management system (DMS) with versioning. Standardise templates with mandatory fields (date, version, author, approver). Conduct a mass purge of obsolete documents and a follow-up document control audit.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    # ── Section 8: Operation ─────────────────────────────────────────────────

    "9001_8_1": {
        "id": "9001_8_1",
        "title": "8.1 Operational planning and control",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Construction", "Logistics"],
        "typical_ncs": [
            "No documented criteria for operational processes",
            "Process controls not implemented as planned",
            "Changes to planned processes not controlled",
        ],
        "evidence_keywords": [
            "operational planning", "process criteria", "work instructions",
            "control", "planned changes", "outsourced processes",
        ],
        # Sprint R3 — atomic_requirements (Template9001.docx §8.1 + ISO 9001
        # §8.1). Chain node for the cross-clause check risk(6.1) → control(8.1)
        # → monitoring(9.1) — promise P6.
        "atomic_requirements": [
            {
                "id": "9001_8_1.criteria.defined",
                "text": "Criteria for the operational processes and for the acceptance of products/services are defined.",
                "verification_hint": "Procedures, work instructions or process sheets stating process parameters and acceptance criteria.",
                "expected_evidence": ["procedure", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_8_1.risk.linkage",
                "text": "Operational controls address the risks identified in 6.1: significant risks have a corresponding operational control or procedure.",
                "verification_hint": "Cross-check the risk register against procedures/work instructions: each significant risk should map to a control. An identified risk with no corresponding control is a broken chain.",
                "expected_evidence": ["risk_assessment", "procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_8_1.documented.confidence",
                "text": "Documented information is retained to the extent necessary to have confidence that processes are carried out as planned.",
                "verification_hint": "Completed records, checklists, logs corresponding to the planned controls.",
                "expected_evidence": ["record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_8_1.change.control",
                "text": "Planned changes are controlled and the consequences of unintended changes are reviewed (change management attention point in audit practice).",
                "verification_hint": "Change records, revision histories, review of change consequences.",
                "expected_evidence": ["record", "procedure"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Document operational planning criteria for key processes. Implement controls to ensure processes are carried out as planned and changes are managed.",
            "who": "Operations Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "9001_8_2": {
        "id": "9001_8_2",
        "title": "8.2 Requirements for products and services",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Construction", "Services"],
        "typical_ncs": [
            "Customer requirements not formally reviewed before acceptance",
            "No process for handling customer enquiries and contracts",
            "Changes to requirements not communicated to relevant staff",
        ],
        "evidence_keywords": [
            "customer requirements", "contract review", "order review",
            "tender", "specification", "customer communication", "enquiry",
        ],
        "remediation_template": {
            "what": "Implement a contract/order review process to capture, review, and confirm customer requirements before commitment. Document records of review.",
            "who": "Sales Manager / Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "9001_8_3": {
        "id": "9001_8_3",
        "title": "8.3 Design and development of products and services",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Construction", "Services"],
        "typical_ncs": [
            "Design process not documented",
            "Design review, verification, and validation not performed",
            "Design changes not controlled",
        ],
        "evidence_keywords": [
            "design", "development", "design review", "verification",
            "validation", "design inputs", "design outputs", "design changes",
        ],
        "remediation_template": {
            "what": "Establish a documented design and development process including inputs, outputs, review, verification, validation, and change control.",
            "who": "Engineering Manager / Quality Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "9001_8_4": {
        "id": "9001_8_4",
        "title": "8.4 Control of externally provided processes, products and services",
        "area": "Operation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if approved supplier list completely absent or critical purchases from unqualified suppliers; PUNCTUAL if single supplier not reviewed or not updated",
        "critical_sectors": ["Construction", "Manufacturing", "Logistics", "Healthcare", "Energy"],
        "typical_ncs": [
            "No formal qualification process and supplier review for critical suppliers",
            "Use of unapproved suppliers; no approved supplier list",
            "Absence of evaluation criteria and performance records",
            "Critical purchases from unqualified suppliers",
            "Single supplier not reviewed or annual review overdue",
        ],
        "evidence_keywords": [
            "supplier", "subcontractor", "approved supplier list", "vendor",
            "supplier evaluation", "supplier qualification", "purchasing",
            "externally provided", "procurement", "purchase order",
            "supplier assessment", "vendor rating", "supplier complaint",
            "nonconformity supplier", "critical supplier",
        ],
        # Sprint J — atomic_requirements derived from Master KB §3.2.2.
        "atomic_requirements": [
            {
                "id": "9001_8_4.qualification.procedure",
                "text": "A documented procedure for supplier qualification and evaluation exists.",
                "verification_hint": "Procurement procedure with criteria, thresholds and frequency for supplier qualification.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_8_4.approved_list",
                "text": "An approved supplier list (or equivalent register) exists and is current.",
                "verification_hint": "Approved supplier register present, kept up to date; matches actual suppliers used.",
                "expected_evidence": ["supplier_document", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_8_4.critical_identified",
                "text": "Critical suppliers are identified and subject to enhanced controls.",
                "verification_hint": "Distinction between routine and critical suppliers; deeper assessment for critical category.",
                "expected_evidence": ["supplier_document", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_8_4.performance.records",
                "text": "Supplier performance evaluation records exist (delivery, quality, complaints).",
                "verification_hint": "Periodic supplier scorecards, KPI reports, or evaluation forms.",
                "expected_evidence": ["supplier_document", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_8_4.review.periodic",
                "text": "Periodic supplier review is performed (at minimum annually for critical suppliers).",
                "verification_hint": "Review minutes or signed review records with dates; outcomes drive list updates.",
                "expected_evidence": ["audit_report", "supplier_document"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_8_4.no_unqualified_use",
                "text": "Critical purchases come only from qualified suppliers — no unqualified supplier usage.",
                "verification_hint": "Cross-check purchase orders / invoices against approved supplier list; flag mismatches.",
                "expected_evidence": ["supplier_document", "record"],
                "risk_if_missing": "MAJOR",
            },
        ],
        "remediation_template": {
            "what": "Define and update supplier qualification and review procedure (criteria, thresholds, frequency). Build a critical supplier register. Block transactions in ERP for unqualified suppliers. Implement extraordinary critical supplier review plan.",
            "who": "Quality Manager / Procurement Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "9001_8_5": {
        "id": "9001_8_5",
        "title": "8.5 Production and service provision",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Construction", "Healthcare"],
        "typical_ncs": [
            "No documented work instructions for key processes",
            "No traceability system for products",
            "Post-delivery activities not defined",
        ],
        "evidence_keywords": [
            "production", "service provision", "work instruction", "traceability",
            "identification", "preservation", "post-delivery", "controlled conditions",
        ],
        "remediation_template": {
            "what": "Implement documented work instructions for key production/service processes. Establish traceability and identification systems. Define post-delivery activities.",
            "who": "Operations Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "9001_8_6": {
        "id": "9001_8_6",
        "title": "8.6 Release of products and services",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Healthcare"],
        "typical_ncs": [
            "No inspection or testing records before product release",
            "Acceptance criteria not defined",
            "Products released without authorisation",
        ],
        "evidence_keywords": [
            "inspection", "testing", "release", "acceptance criteria",
            "final inspection", "certificate of conformity", "authorisation",
        ],
        "remediation_template": {
            "what": "Define acceptance criteria and implement documented inspection and testing records. Ensure products and services are only released after authorised approval.",
            "who": "Quality Manager / Production Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "9001_8_7": {
        "id": "9001_8_7",
        "title": "8.7 Control of nonconforming outputs",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Healthcare", "Construction"],
        "typical_ncs": [
            "No procedure for identifying and controlling nonconforming products",
            "Nonconformities not recorded or analysed",
            "Concessions granted without authorisation",
        ],
        "evidence_keywords": [
            "nonconforming", "nonconformity", "reject", "quarantine",
            "rework", "concession", "disposition", "segregation",
        ],
        "remediation_template": {
            "what": "Implement a nonconforming output procedure covering identification, segregation, disposition, and recording. Define authorisation for concessions.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 9: Performance Evaluation ───────────────────────────────────

    "9001_9_1": {
        "id": "9001_9_1",
        "title": "9.1 Monitoring, measurement, analysis and evaluation",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Customer satisfaction not measured",
            "No analysis of QMS performance data",
            "Monitoring and measurement methods not defined",
        ],
        "evidence_keywords": [
            "customer satisfaction", "monitoring", "measurement", "analysis",
            "evaluation", "KPI", "performance data", "survey",
        ],
        # Sprint R3 — atomic_requirements (Template9001.docx §9.1.1-9.1.3 +
        # ISO 9001 §9.1). Chain node for risk(6.1) → control(8.1) → monitoring(9.1).
        "atomic_requirements": [
            {
                "id": "9001_9_1.scope.defined",
                "text": "What needs to be monitored and measured is determined, together with methods and frequencies.",
                "verification_hint": "Monitoring plan / procedure naming the indicators, the technique and the control frequency for each monitored item.",
                "expected_evidence": ["procedure", "record", "objective_plan"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_1.results.retained",
                "text": "Documented results of monitoring and measurement are retained as evidence.",
                "verification_hint": "Filled KPI reports, dashboards, control logs with actual values and dates.",
                "expected_evidence": ["record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_1.chain.linkage",
                "text": "Monitoring covers the effectiveness of the actions on risks (6.1) and the progress of the quality objectives (6.2) — not only production metrics.",
                "verification_hint": "Cross-check: indicators exist for the significant risks' controls and for each objective. A risk action with no monitoring indicator breaks the 6.1→8.1→9.1 chain.",
                "expected_evidence": ["record", "risk_assessment", "objective_plan"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_1.customer.satisfaction",
                "text": "Customer satisfaction is monitored through direct methods (surveys, post-delivery calls) and/or indirect methods (complaint analysis, returns, repeat-order history, lost tenders).",
                "verification_hint": "Survey results, complaint statistics, returns analysis, order history reviews.",
                "expected_evidence": ["record", "communication_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_1.analysis.performed",
                "text": "Data from monitoring is analysed and evaluated (trends, conclusions), feeding the management review.",
                "verification_hint": "Analysis sections, trend charts or commentary on the data; analysis output appears among management review inputs.",
                "expected_evidence": ["record", "management_review"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define monitoring and measurement methods for QMS processes. Implement customer satisfaction measurement. Analyse and evaluate performance data at management review.",
            "who": "Quality Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "9001_9_2": {
        "id": "9001_9_2",
        "title": "9.2 Internal audit",
        "area": "Performance Evaluation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if total absence of audit programme or audits not executed at all; PUNCTUAL if some audits delayed or reports incomplete",
        "critical_sectors": ["Construction", "Manufacturing", "Healthcare", "Energy"],
        "typical_ncs": [
            "Audit programme non-existent or not covering all processes",
            "Audits not executed as planned; superficial reports without root cause",
            "Corrective actions from audit findings not followed up",
            "Internal auditors not competent or not independent from audited area",
        ],
        "evidence_keywords": [
            "internal audit", "audit programme", "audit schedule", "audit report",
            "audit findings", "corrective action", "auditor competence",
            "audit plan", "follow-up", "CAPA audit", "audit records",
        ],
        # Sprint J — atomic_requirements derived from Master KB §3.2.3.
        "atomic_requirements": [
            {
                "id": "9001_9_2.programme.exists",
                "text": "An annual internal-audit programme exists and covers all key processes.",
                "verification_hint": "Audit programme document listing processes, frequency, responsible auditors over the cycle.",
                "expected_evidence": ["audit_report", "procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_2.risk_based",
                "text": "Audit frequency is risk-based / process-criticality-based, not uniform.",
                "verification_hint": "Programme allocates more frequent audits to critical processes; rationale documented.",
                "expected_evidence": ["audit_report", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_2.execution.records",
                "text": "Planned audits are actually executed and recorded.",
                "verification_hint": "Audit reports exist for the planned audits; dates align with the schedule.",
                "expected_evidence": ["audit_report"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_2.findings.root_cause",
                "text": "Audit findings include root-cause analysis, not only symptom descriptions.",
                "verification_hint": "Reports show analysis of causes (5 Whys / Ishikawa) for non-conformances raised.",
                "expected_evidence": ["audit_report", "nonconformity_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_2.findings.followup",
                "text": "Corrective actions from audit findings are tracked to closure.",
                "verification_hint": "CAPA log with audit-finding references, owner, deadline, closure date.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_2.auditor.competence",
                "text": "Internal auditors are competent (trained on audit techniques) and independent from the area audited.",
                "verification_hint": "Auditor training records; assignment matrix shows independence from audited area.",
                "expected_evidence": ["training_record", "audit_report"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Issue or update annual audit programme based on risk and process criticality. Train internal auditors on audit techniques and 5 Whys root cause analysis. Use standard audit checklists. Implement CAPA effectiveness review process from audit findings.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "Next audit cycle",
            "effort": "MEDIUM",
        },
    },

    "9001_9_3": {
        "id": "9001_9_3",
        "title": "9.3 Management review",
        "area": "Performance Evaluation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if no review conducted in last 12 months or total absence of evidence; PUNCTUAL if minutes of some meetings present but some required inputs missing",
        "critical_sectors": ["Construction", "Manufacturing", "Healthcare"],
        "typical_ncs": [
            "Management review not conducted with required frequency; minutes missing or incomplete",
            "Required ISO 9001 §9.3 inputs not addressed (audit results, customer feedback, process performance)",
            "Actions and decisions not defined or not monitored",
            "Review conducted but not led by top management",
        ],
        "evidence_keywords": [
            "management review", "review meeting", "top management",
            "review agenda", "review minutes", "review output",
            "action list", "KPI", "customer complaints", "audit results",
            "strategic planning",
        ],
        # Sprint J — atomic_requirements derived from Master KB §3.2.4 and
        # the public ISO 9001 §9.3 reading: each item below maps to an input
        # or output the management review is expected to cover.
        # This is the clause where deterministic item-by-item verification
        # has the greatest impact, because §9.3 is intrinsically a checklist.
        "atomic_requirements": [
            {
                "id": "9001_9_3.frequency",
                "text": "Management review is conducted at planned intervals (at least annually).",
                "verification_hint": "Most recent review dated within the last 12 months; planned cadence documented.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_3.top_management",
                "text": "Review is led by top management (not delegated entirely).",
                "verification_hint": "Attendance list includes managing director / executive level; signed-off minutes.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.previous_actions",
                "text": "Input considered: status of actions from previous management reviews.",
                "verification_hint": "Agenda or minutes explicitly reference prior-review action status.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.changes",
                "text": "Input considered: changes in external and internal issues relevant to the QMS.",
                "verification_hint": "Discussion of context changes — market, regulatory, organisational.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.customer_satisfaction",
                "text": "Input considered: customer satisfaction and feedback.",
                "verification_hint": "Survey results, complaint metrics, NPS or equivalent presented.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.kpi",
                "text": "Input considered: process performance and conformity of products/services (KPI data).",
                "verification_hint": "KPI dashboard or performance summary in the review pack.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.nc_capa",
                "text": "Input considered: non-conformities and corrective actions.",
                "verification_hint": "NC / CAPA log summary presented; trends discussed.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.audit_results",
                "text": "Input considered: internal and external audit results.",
                "verification_hint": "Audit findings presented and discussed; status of corrective actions.",
                "expected_evidence": ["management_review", "audit_report"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.suppliers",
                "text": "Input considered: performance of external providers.",
                "verification_hint": "Supplier performance summary; critical-supplier review status.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.resources",
                "text": "Input considered: adequacy of resources for maintaining an effective QMS.",
                "verification_hint": "Minutes show a discussion of resource adequacy (people, equipment, infrastructure) — not merely investment decisions in the outputs.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.input.risks_opportunities",
                "text": "Input considered: effectiveness of actions to address risks and opportunities.",
                "verification_hint": "Risk register update or effectiveness review of risk responses.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.output.improvement",
                "text": "Output: decisions and actions related to improvement opportunities.",
                "verification_hint": "Documented action items addressing improvement, with owner and deadline.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_9_3.output.qms_changes",
                "text": "Output: decisions and actions related to any need for changes to the QMS.",
                "verification_hint": "Documented decisions on system changes (procedures, structure, resources).",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.output.resources",
                "text": "Output: decisions and actions related to resource needs.",
                "verification_hint": "Resource allocation decisions documented; budget or headcount implications captured.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_9_3.output.tracked",
                "text": "Outputs are tracked to closure via an action register with owners and deadlines.",
                "verification_hint": "Action tracker linked to the review; deadlines and statuses visible.",
                "expected_evidence": ["management_review", "nonconformity_record"],
                "risk_if_missing": "MAJOR",
            },
        ],
        "remediation_template": {
            "what": "Schedule management review at least annually. Define standard minutes template with all required ISO 9001 §9.3 inputs and outputs. Integrate an action tracker with responsibilities and deadlines. Link management review to strategic planning.",
            "who": "Managing Director / Quality Manager",
            "when_major": "30 days",
            "when_minor": "Next review cycle",
            "effort": "LOW",
        },
    },

    # ── Section 10: Improvement ──────────────────────────────────────────────

    "9001_10_1": {
        "id": "9001_10_1",
        "title": "10.1 General — Improvement",
        "area": "Improvement",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No evidence of systematic improvement activities",
            "Improvement opportunities not identified or acted upon",
        ],
        "evidence_keywords": [
            "improvement", "continual improvement", "improvement plan",
            "lessons learned", "best practice",
        ],
        "remediation_template": {
            "what": "Establish a systematic approach to identifying and acting on improvement opportunities. Link to management review outputs and corrective action process.",
            "who": "Quality Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "9001_10_2": {
        "id": "9001_10_2",
        "title": "10.2 Nonconformity and corrective action",
        "area": "Improvement",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if pattern of repeated NCs, no CAPA process, or failure to close previous NCs; PUNCTUAL if some CAPAs documented incompletely",
        "critical_sectors": ["Construction", "Manufacturing", "Healthcare", "Energy"],
        "typical_ncs": [
            "NCs recorded but corrective actions not defined or not based on root cause (no 5 Whys)",
            "Absence of effectiveness verification",
            "Repeated NCs — corrective actions ineffective or only symptomatic",
            "No CAPA process or failure to close previous NCs",
            "Some CAPAs documented incompletely",
        ],
        "evidence_keywords": [
            "nonconformity", "corrective action", "NCR", "root cause",
            "root cause analysis", "CAR", "CAPA", "effectiveness review",
            "5 whys", "Ishikawa", "incident", "complaint", "repeat NC",
            "corrective action register",
        ],
        # Sprint J — atomic_requirements derived from Master KB §3.2.5.
        "atomic_requirements": [
            {
                "id": "9001_10_2.procedure",
                "text": "A documented CAPA procedure exists with minimum requirements (root cause, correction, corrective action, effectiveness verification).",
                "verification_hint": "Procedure document defining the CAPA lifecycle and its mandatory fields.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_10_2.register",
                "text": "A nonconformity / CAPA register exists.",
                "verification_hint": "NC log present, used in practice; entries dated and indexed.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_10_2.rca.applied",
                "text": "Root-cause analysis is actually applied (5 Whys / Ishikawa) for each significant NC.",
                "verification_hint": "Each significant NC carries an RCA section, not just the symptom description.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_10_2.actions",
                "text": "Corrective actions are defined for each NC, with owner and deadline.",
                "verification_hint": "Action register columns: action, owner, deadline, status, closure date.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "9001_10_2.effectiveness",
                "text": "Effectiveness of corrective actions is verified after implementation.",
                "verification_hint": "Effectiveness-check entries on the CAPA log; signed-off verification.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "9001_10_2.no_repeat",
                "text": "No pattern of repeated NCs on the same requirement (would indicate ineffective CAPA).",
                "verification_hint": "Trend review or aggregate report shows no recurring same-cause NCs.",
                "expected_evidence": ["nonconformity_record", "management_review"],
                "risk_if_missing": "MAJOR",
            },
        ],
        "remediation_template": {
            "what": "Establish a CAPA procedure with minimum requirements (root cause analysis, correction, corrective action, effectiveness verification). Train staff on 5 Whys methodology. Implement periodic NC review to identify trends and systemic patterns.",
            "who": "Quality Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "9001_10_3": {
        "id": "9001_10_3",
        "title": "10.3 Continual improvement",
        "area": "Improvement",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No evidence of continual improvement activities beyond corrective actions",
            "Improvement not linked to suitability, adequacy, and effectiveness of QMS",
        ],
        "evidence_keywords": [
            "continual improvement", "improvement objectives", "benchmarking",
            "best practice", "innovation", "process improvement",
        ],
        "remediation_template": {
            "what": "Establish a continual improvement programme with documented objectives, methods, and outcomes. Review at management review.",
            "who": "Quality Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },
}
