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
