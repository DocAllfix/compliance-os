"""
ISO 14001:2015 clause knowledge base.

SPoF per il PDF (§4.3):
- 6.1.2 Aspetti ambientali — assenza registro → perde base logica per controlli e obiettivi
- 6.1.3/9.1.2 Conformità legale — assenza valutazione → rischio sanzioni/regulatory breach
- 8.1 Tracciabilità rifiuti — assente o gravemente carente → rischio penale
- 8.2 Piani emergenza — inesistenti o non testati per scenari critici → SPoF risposta emergenziale

Cluster NC frequenti da audit reali (§4.1 PDF):
    6.1.2, 6.1.3, 8.1, 8.2, 4.3/7.5

Derived metadata (added by Sprint 0):
    Four extra fields are derived at read time by `backend.compliance.clause_helpers`
    (criticality_tier, severity_floor, weight, expiry_relevant). Any clause MAY
    override a derived field by setting it explicitly in the dict. See the
    docstring of iso9001_clauses.py for the full derivation rules.

Tier distribution for ISO 14001 (computed at runtime — see Sprint 0 validation):
    critical ≈ 6 clauses (the HIGH_FREQUENCY + SPoF entries)
    passing  ≈ 3-4 clauses (§4.x context)
    standard ≈ the rest
"""
from __future__ import annotations

from typing import Any, Dict

ISO14001_SEVERITY_RULES = [
    "MAJOR if environmental aspect register is completely absent — the entire EMS loses its logical foundation.",
    "MAJOR if legal compliance evaluation is absent or not demonstrably performed — direct regulatory breach risk.",
    "MAJOR if waste traceability is absent or systemically deficient for hazardous waste — criminal liability risk.",
    "MAJOR if emergency plans are absent for scenarios with significant environmental impact.",
    "Apply the same system vs punctual NC distinction as ISO 9001: system = process non-existent; punctual = isolated deviation.",
]

ISO14001_HIGH_FREQUENCY_CLAUSES = [
    "14001_6_1_2",   # Environmental aspects
    "14001_6_1_3",   # Compliance obligations
    "14001_8_1",     # Operational control (waste)
    "14001_8_2",     # Emergency preparedness
    "14001_4_3",     # Scope
    "14001_7_5",     # Documented information
]

ISO14001_CLAUSES: Dict[str, Dict[str, Any]] = {

    # ── Section 4: Context ──────────────────────────────────────────────────

    "14001_4_1": {
        "id": "14001_4_1",
        "title": "4.1 Understanding the organisation and its context",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No documented analysis of internal and external environmental issues",
            "Context analysis not linked to significant environmental aspects",
            "Issues not reviewed at management review",
        ],
        "evidence_keywords": [
            "context", "internal issues", "external issues", "environmental context",
            "SWOT", "PESTLE", "strategic direction",
        ],
        "remediation_template": {
            "what": "Document an analysis of internal and external issues relevant to the organisation's environmental purpose and strategic direction. Link to EMS scope and review at management review.",
            "who": "Environmental Manager / Quality Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "14001_4_2": {
        "id": "14001_4_2",
        "title": "4.2 Understanding the needs and expectations of interested parties",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": ["Energy", "Manufacturing", "Construction"],
        "typical_ncs": [
            "Interested parties limited to customers only; regulators and community not included",
            "Legal and regulatory requirements of environmental authorities not captured",
            "No process to monitor changes in stakeholder environmental requirements",
        ],
        "evidence_keywords": [
            "interested parties", "stakeholders", "regulatory bodies", "community",
            "environmental requirements", "compliance obligations", "neighbours",
        ],
        "remediation_template": {
            "what": "Identify all relevant interested parties including regulatory authorities, local community, and supply chain. Document their environmental requirements and establish a review cycle.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "LOW",
        },
    },

    "14001_4_3": {
        "id": "14001_4_3",
        "title": "4.3 Determining the scope of the environmental management system",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "EMS scope not documented or does not reflect actual activities, products, and services",
            "Scope excludes significant environmental aspects without justification",
            "Scope not available as documented information",
        ],
        "evidence_keywords": [
            "scope", "EMS scope", "boundaries", "activities", "products", "services",
            "documented information", "exclusions",
        ],
        # Sprint R8 — atomic_requirements (TEMPLATE14001.docx §4.3: scope
        # MAINTAIN obbligatorio, coerenza con cogenze e outsourcing).
        "atomic_requirements": [
            {
                "id": "14001_4_3.scope.documented",
                "text": "The EMS scope is maintained as documented information (mandatory documented information for 14001).",
                "verification_hint": "Scope statement in the EMS manual or standalone document, with sites and boundaries.",
                "expected_evidence": ["quality_manual", "policy", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_4_3.scope.coverage",
                "text": "The scope covers the actual activities, products and services with environmental impacts — no unjustified exclusions of significant aspects.",
                "verification_hint": "Cross-check scope wording against the aspect register and the actual operations described in other documents.",
                "expected_evidence": ["quality_manual", "risk_assessment"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_4_3.scope.coherence",
                "text": "The scope is coherent with the compliance obligations and the internal/external context, and considers the organisation's ability to influence outsourced activities.",
                "verification_hint": "Scope references compliance obligations/context; outsourced processes addressed (checklist 4.3: capacità di influenza sull'outsourcing).",
                "expected_evidence": ["quality_manual", "legal_register"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_4_3.scope.available",
                "text": "The scope is available to interested parties.",
                "verification_hint": "Statement of availability (website, on request) or distribution evidence.",
                "expected_evidence": ["quality_manual", "communication_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define and document the EMS scope covering all sites, activities, products, and services with significant environmental impacts. Justify any exclusions.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    "14001_4_4": {
        "id": "14001_4_4",
        "title": "4.4 Environmental management system",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "EMS processes not defined or interactions not documented",
            "No life cycle perspective applied to products and services",
            "Process ownership not assigned for environmental processes",
        ],
        "evidence_keywords": [
            "EMS", "process map", "life cycle", "process interaction",
            "process owner", "environmental process",
        ],
        "remediation_template": {
            "what": "Map all EMS processes, define process interactions, assign ownership, and apply life cycle perspective to products and services.",
            "who": "Environmental Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 5: Leadership ────────────────────────────────────────────────

    "14001_5_1": {
        "id": "14001_5_1",
        "title": "5.1 Leadership and commitment",
        "area": "Leadership",
        "is_spof": True,
        "critical_sectors": ["Energy", "Manufacturing", "Construction", "Logistics"],
        "typical_ncs": [
            "No evidence of top management involvement in EMS",
            "Environmental policy not communicated or understood by staff",
            "Resources for EMS not allocated by top management",
        ],
        "evidence_keywords": [
            "top management", "leadership", "commitment", "environmental policy",
            "resources", "management review", "accountability",
        ],
        # Sprint R8 — atomic_requirements (TEMPLATE14001.docx §5.1 + ISO 14001
        # §5.1). Documentation-verifiable items; interview guidance excluded.
        "atomic_requirements": [
            {
                "id": "14001_5_1.policy_objectives.established",
                "text": "Top management has established the environmental policy and objectives, coherent with strategy, significant aspects and compliance obligations.",
                "verification_hint": "Signed policy; objectives traceable to significant aspects and strategic direction (checklist 5.1: strategie e obiettivi su business, AA significativi, obblighi).",
                "expected_evidence": ["policy", "objective_plan"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_5_1.resources.allocated",
                "text": "Evidence exists that top management provides adequate resources for the EMS.",
                "verification_hint": "Resource decisions in MR outputs, investments in environmental controls, appointments (environmental manager).",
                "expected_evidence": ["management_review", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_5_1.review.led",
                "text": "Top management participates in and leads the management review of the EMS.",
                "verification_hint": "MR minutes list top management among attendees; environmental performance discussed at that level.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_5_1.integration.evidence",
                "text": "EMS requirements are integrated into the organisation's business processes (not a parallel paper system).",
                "verification_hint": "Environmental requirements embedded in operational procedures, purchasing, planning documents.",
                "expected_evidence": ["procedure", "quality_manual"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish documented evidence of top management environmental commitment: signed environmental policy, resource allocation records, and management review minutes.",
            "who": "Managing Director / Environmental Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "14001_5_2": {
        "id": "14001_5_2",
        "title": "5.2 Environmental policy",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Environmental policy not documented or not signed by top management",
            "Policy does not commit to protection of the environment and pollution prevention",
            "Policy not communicated to all persons working under the organisation's control",
        ],
        "evidence_keywords": [
            "environmental policy", "policy statement", "pollution prevention",
            "commitment", "continual improvement", "communicated", "protect environment",
        ],
        # Sprint R3 — atomic_requirements from audit checklist guidance
        # (TEMPLATE14001.docx §5.2: policy MUST contain commitments to
        # protection of the environment, fulfilment of compliance obligations,
        # continual improvement; coherent with context and impacts) + ISO
        # 14001:2015 §5.2. Wording checks — promise P4.
        "atomic_requirements": [
            {
                "id": "14001_5_2.policy.documented",
                "text": "An environmental policy exists as documented information, identifiable as the current approved version (signed/dated by top management).",
                "verification_hint": "Policy document or EMS manual section; approval signature or issue date.",
                "expected_evidence": ["policy", "quality_manual"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_5_2.commitment.protection",
                "text": "The policy wording contains an explicit commitment to the protection of the environment, INCLUDING prevention of pollution.",
                "verification_hint": "Look in the text for wording equivalent to 'protection of the environment' AND 'prevention of pollution' — both elements are required by the standard.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                # Sprint R7 — deterministic wording check (EN+IT variants)
                "wording_keywords": [["protect", "protezion", "tutela", "salvaguard"], ["pollution", "inquinament"]],
            },
            {
                "id": "14001_5_2.commitment.compliance",
                "text": "The policy wording contains an explicit commitment to fulfil the organisation's compliance obligations (legal and other requirements).",
                "verification_hint": "Wording equivalent to 'fulfil compliance obligations' / 'comply with applicable legal and other requirements' in the policy text.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                "wording_keywords": [["compliance", "legal", "obblig", "conform", "prescrizion", "cogent"]],
            },
            {
                "id": "14001_5_2.commitment.improvement",
                "text": "The policy wording contains an explicit commitment to continual improvement of the environmental management system to enhance environmental performance.",
                "verification_hint": "Continual improvement of the EMS must be stated in the policy text itself.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                "wording_keywords": [["improv", "migliora", "enhanc", "perfezion", "ottimizz"]],
            },
            {
                "id": "14001_5_2.context.coherence",
                "text": "The policy is appropriate to the purpose and context of the organisation, coherent with the significant environmental impacts of its activities, products and services (commitments pertinent to the context — e.g. water, recycling, climate — not generic boilerplate).",
                "verification_hint": "Compare policy themes against the aspect register (6.1.2) and the context analysis; template text with no organisation-specific environmental themes fails.",
                "expected_evidence": ["policy", "risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_5_2.communicated",
                "text": "The policy is communicated within the organisation and available to interested parties.",
                "verification_hint": "Distribution/communication evidence; availability to external parties (website, on request).",
                "expected_evidence": ["communication_record", "policy"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Issue a signed, dated environmental policy including commitments to pollution prevention, compliance obligations, and continual improvement. Communicate to all staff and make available to interested parties.",
            "who": "Managing Director",
            "when_major": "14 days",
            "when_minor": "30 days",
            "effort": "LOW",
        },
    },

    "14001_5_3": {
        "id": "14001_5_3",
        "title": "5.3 Organisational roles, responsibilities and authorities",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No EMS management representative or environmental officer defined",
            "Roles and responsibilities for environmental processes not documented",
            "No organisation chart linking to environmental responsibilities",
        ],
        "evidence_keywords": [
            "environmental officer", "RSGA", "environmental manager",
            "roles", "responsibilities", "authorities", "organisation chart",
        ],
        "remediation_template": {
            "what": "Assign an EMS management representative. Document roles and responsibilities for all environmental functions and publish an updated organisation chart.",
            "who": "Managing Director / HR Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    # ── Section 6: Planning ──────────────────────────────────────────────────

    "14001_6_1_1": {
        "id": "14001_6_1_1",
        "title": "6.1.1 Actions to address risks and opportunities",
        "area": "Planning",
        "is_spof": False,
        "critical_sectors": ["Energy", "Manufacturing"],
        "typical_ncs": [
            "No environmental risk register linked to EMS processes",
            "Risks identified but no mitigation actions defined",
            "Opportunities for environmental improvement not considered",
        ],
        "evidence_keywords": [
            "risk", "opportunity", "environmental risk register", "risk assessment",
            "mitigation", "environmental risk", "risk-based thinking",
        ],
        # Sprint R3 — atomic_requirements (TEMPLATE14001.docx §6.1.1 + ISO
        # 14001 §6.1.1). Chain node for risk → operational control → monitoring.
        "atomic_requirements": [
            {
                "id": "14001_6_1_1.planning.process",
                "text": "The planning process determines risks and opportunities related to the environmental aspects, the compliance obligations and the context issues (4.1/4.2), covering performance improvement, compliance fulfilment and objective achievement.",
                "verification_hint": "Planning records linking risks/opportunities to aspects (6.1.2), compliance obligations (6.1.3) and context analysis.",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_1.prioritisation.applied",
                "text": "A methodology for assigning priority to risks is defined AND actually applied to the entries (not only declared).",
                "verification_hint": "Spot-check: register entries carry the score/class produced by the declared method.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_1.documented",
                "text": "Documented information on risks and opportunities and on the planning processes is maintained.",
                "verification_hint": "Maintained register or planning document with revision control (checklist: MAINTAIN + RETAIN required).",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_1.emergency.input",
                "text": "Potential emergency situations are identified among the planning inputs (link to emergency preparedness, 8.2).",
                "verification_hint": "Emergency scenarios referenced in the planning/risk documents, coherent with the emergency plan.",
                "expected_evidence": ["risk_assessment", "emergency_plan"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish an environmental risk and opportunity register. Define mitigation actions, assign owners, and review at management review.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "14001_6_1_2": {
        "id": "14001_6_1_2",
        "title": "6.1.2 Environmental aspects",
        "area": "Planning",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if no aspect register exists or aspects not identified for all activities including abnormal/emergency conditions; PUNCTUAL if register exists but secondary aspects missing or not updated after process changes",
        "critical_sectors": ["Energy", "Manufacturing", "Construction", "Logistics"],
        "typical_ncs": [
            "Aspects not identified for all activities including abnormal and emergency conditions",
            "Significance criteria not documented; significance matrix not updated",
            "Aspect register not updated after process or equipment changes",
            "Aspects identified but life cycle perspective not applied",
        ],
        "evidence_keywords": [
            "environmental aspects", "environmental impacts", "aspect register",
            "significance criteria", "significance matrix", "abnormal conditions",
            "emergency conditions", "life cycle", "aspect evaluation",
        ],
        # Sprint J — atomic_requirements derived from Master KB §4.2.1.
        "atomic_requirements": [
            {
                "id": "14001_6_1_2.register.exists",
                "text": "An environmental aspects register exists, covering all activities, products and services.",
                "verification_hint": "Register document present with rows per activity / aspect / impact.",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_2.conditions.normal",
                "text": "Aspects identified under normal operating conditions.",
                "verification_hint": "Register includes routine activities.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_2.conditions.abnormal",
                "text": "Aspects identified under abnormal conditions (start-up, shutdown, maintenance).",
                "verification_hint": "Register explicitly addresses non-routine operating states.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_2.conditions.emergency",
                "text": "Aspects identified under emergency scenarios (spill, fire, accident).",
                "verification_hint": "Register covers emergency-scenario aspects; cross-reference to emergency plan.",
                "expected_evidence": ["risk_assessment", "emergency_plan"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_2.significance.criteria",
                "text": "Documented criteria for significance evaluation (scoring methodology).",
                "verification_hint": "Significance matrix or scoring rubric included in or alongside the register.",
                "expected_evidence": ["procedure", "risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_2.lifecycle",
                "text": "Aspects identified using a life-cycle perspective (raw materials, use, end-of-life).",
                "verification_hint": "Register or methodology references upstream/downstream phases, not only direct operations.",
                "expected_evidence": ["risk_assessment", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_2.review.triggers",
                "text": "Register updated after process, product, equipment or layout changes.",
                "verification_hint": "Revision history shows updates following documented changes.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Issue or update procedure for environmental aspect identification covering normal, abnormal, and emergency conditions. Update aspect register. Formalise significance criteria (scoring) and implement periodic review schedule.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "14001_6_1_3": {
        "id": "14001_6_1_3",
        "title": "6.1.3 Compliance obligations",
        "area": "Planning",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if no legal register and no compliance evaluation performed; PUNCTUAL if register exists but some requirements not evaluated",
        "critical_sectors": ["Energy", "Manufacturing", "Construction", "Logistics", "Healthcare"],
        "typical_ncs": [
            "Incomplete legal register; no periodic compliance evaluation",
            "No demonstration of how the organisation knows its compliance status",
            "Regulatory authority requirements not captured in the register",
            "Register exists but some requirements not evaluated for compliance",
        ],
        "evidence_keywords": [
            "legal register", "compliance obligations", "regulatory requirements",
            "legal compliance", "permits", "licences", "compliance evaluation",
            "environmental law", "legislation", "regulation", "authority inspection",
        ],
        # Sprint J — atomic_requirements derived from Master KB §4.2.2.
        "atomic_requirements": [
            {
                "id": "14001_6_1_3.register.exists",
                "text": "A legal / compliance obligations register exists.",
                "verification_hint": "Register listing applicable environmental legal requirements; rows for laws, permits, licences.",
                "expected_evidence": ["legal_register"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_3.register.complete",
                "text": "Register covers all applicable environmental laws, permits and licences for the operating sectors.",
                "verification_hint": "Coverage cross-checked against the activities described in the aspect register (no major gap).",
                "expected_evidence": ["legal_register", "risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_3.status.tracked",
                "text": "Each requirement has a compliance-status field (compliant / partial / non-compliant) kept current.",
                "verification_hint": "Register includes a status column populated with explicit values, not blank.",
                "expected_evidence": ["legal_register"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_3.how_we_comply",
                "text": "Each requirement has a 'how we comply' field naming the relevant control / evidence.",
                "verification_hint": "Register column referencing procedures, records, or controls demonstrating compliance.",
                "expected_evidence": ["legal_register"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_1_3.evaluation.periodic",
                "text": "Periodic compliance evaluation is performed and recorded.",
                "verification_hint": "Compliance-evaluation reports or signed sign-offs dated within the planned interval.",
                "expected_evidence": ["legal_register", "audit_report"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_1_3.monitoring.updates",
                "text": "A process exists to monitor changes in environmental legislation.",
                "verification_hint": "Subscription, alert service, periodic legal review, or evidence of updates to the register following new legislation.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Structure a legal register with columns for compliance status and 'how we comply'. Plan periodic compliance evaluations and implement corrective actions for any legal gaps. Establish a legislative monitoring process.",
            "who": "Environmental Manager / Legal Advisor",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "14001_6_2": {
        "id": "14001_6_2",
        "title": "6.2 Environmental objectives and planning",
        "area": "Planning",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Environmental objectives not defined or not linked to significant aspects",
            "No action plan to achieve objectives with measurable targets",
            "Objectives not reviewed or updated",
        ],
        "evidence_keywords": [
            "environmental objectives", "targets", "KPI", "action plan",
            "measurable", "environmental performance", "improvement targets",
        ],
        # Sprint R3 — atomic_requirements from audit checklist guidance
        # (TEMPLATE14001.docx §6.2.1-6.2.2: objectives measurable/monitored/
        # communicated/updated; actions need interventi, risorse,
        # responsabilità, scadenze) + ISO 14001 §6.2. Promise P5 —
        # label-agnostic: objectives may appear as targets, KPIs, programmes.
        "atomic_requirements": [
            {
                "id": "14001_6_2.objectives.documented",
                "text": "Environmental objectives exist as documented information at relevant functions — regardless of the label used (objectives, targets, KPIs, environmental programmes).",
                "verification_hint": "Objective plan, environmental programme, KPI sheet or objectives embedded in the EMS manual / management review.",
                "expected_evidence": ["objective_plan", "record", "management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_2.objectives.measurable",
                "text": "Objectives are measurable (where practicable): each carries a metric AND a target value, not only a declared intention.",
                "verification_hint": "Per-entry check: number/threshold + measuring unit or defined indicator. Name the entries that are declared-only.",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_6_2.plan.defined",
                "text": "Planning to achieve each objective defines: actions (interventi), resources, responsibilities and deadlines, plus how results will be evaluated.",
                "verification_hint": "Action plan columns: what, who, resources, by when, evaluation indicator (checklist 6.2.2 requires all four elements).",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_2.coherence",
                "text": "Objectives are consistent with the environmental policy, the significant environmental aspects and the risks/opportunities output (6.1).",
                "verification_hint": "Cross-check objective themes against the policy commitments and the significant aspects in the register. Not every significant aspect needs an objective, but objectives must trace back to aspects/policy.",
                "expected_evidence": ["objective_plan", "policy", "risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_6_2.monitored",
                "text": "The implementation status of the objectives is monitored, communicated and updated.",
                "verification_hint": "Progress records, actual-vs-target tracking, objectives as a management review input, evidence of updates.",
                "expected_evidence": ["record", "management_review", "objective_plan"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define measurable environmental objectives linked to significant aspects and compliance obligations. Document an action plan with owners, timescales, and measurement criteria.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 7: Support ───────────────────────────────────────────────────

    "14001_7_2": {
        "id": "14001_7_2",
        "title": "7.2 Competence",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Energy", "Construction"],
        "typical_ncs": [
            "Staff handling significant environmental aspects not trained",
            "Competence requirements for environmental roles not defined",
            "No evidence of competence evaluation after environmental training",
        ],
        "evidence_keywords": [
            "environmental training", "competence", "training records",
            "environmental awareness", "qualifications", "RSPP", "RSGA",
        ],
        "remediation_template": {
            "what": "Define competence requirements for all roles affecting significant environmental aspects. Update training records and implement a competence evaluation process.",
            "who": "HR Manager / Environmental Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "14001_7_3": {
        "id": "14001_7_3",
        "title": "7.3 Awareness",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Staff unaware of significant environmental aspects relevant to their work",
            "No environmental awareness communication programme",
            "Personnel not aware of consequences of not conforming with EMS requirements",
        ],
        "evidence_keywords": [
            "environmental awareness", "significant aspects", "communication",
            "induction", "toolbox talk", "environmental briefing",
        ],
        "remediation_template": {
            "what": "Implement an environmental awareness programme covering significant aspects, policy, and consequences of non-conformance. Record evidence of communication.",
            "who": "Environmental Manager / HR Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    "14001_7_5": {
        "id": "14001_7_5",
        "title": "7.5 Documented information",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Environmental records not version-controlled or not approved",
            "Monitoring records incomplete or not retained for required period",
            "No document control procedure for EMS documents",
        ],
        "evidence_keywords": [
            "document control", "documented information", "records", "version control",
            "environmental records", "monitoring records", "retention",
        ],
        # Sprint R8 — atomic_requirements (ISO 14001 §7.5, mirroring the
        # 9001_7_5 checklist pattern with EMS-specific records).
        "atomic_requirements": [
            {
                "id": "14001_7_5.control.defined",
                "text": "A document control approach exists covering creation, approval, distribution, revision and obsolete-copy handling for EMS documents.",
                "verification_hint": "Procedure or manual section defining the lifecycle; applies to environmental procedures and registers.",
                "expected_evidence": ["procedure", "quality_manual"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_7_5.metadata.completeness",
                "text": "Controlled EMS documents carry version, date and approval identification.",
                "verification_hint": "Spot-check the aspect register, legal register, procedures: revision number, date, approver present.",
                "expected_evidence": ["procedure", "risk_assessment", "legal_register"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_7_5.records.retained",
                "text": "Environmental records required by the standard (monitoring results, compliance evaluations, training, communications) are retained and retrievable.",
                "verification_hint": "Records exist with dates; retention addressed.",
                "expected_evidence": ["record", "training_record", "communication_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_7_5.external.controlled",
                "text": "Documented information of external origin necessary for the EMS (permits, authorisations, legal texts) is identified and controlled.",
                "verification_hint": "Permits/authorisations referenced and current; external documents in the register.",
                "expected_evidence": ["legal_register", "certificate", "record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Implement document control for all EMS documents and records. Define retention periods for environmental monitoring records and ensure version control and approval.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 8: Operation ─────────────────────────────────────────────────

    "14001_8_1": {
        "id": "14001_8_1",
        "title": "8.1 Operational planning and control",
        "area": "Operation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if waste traceability is absent or systemic for hazardous waste; MINOR if isolated incomplete records but system exists",
        "critical_sectors": ["Manufacturing", "Construction", "Energy", "Logistics", "Healthcare"],
        "typical_ncs": [
            "Waste traceability absent from generation point to final destination",
            "Incomplete FIR (waste tracking forms); incorrect CER waste codes",
            "No operational criteria or work instructions for waste management",
            "Missing contracts with licensed waste disposal operators",
            "No training records for waste handling staff",
        ],
        "evidence_keywords": [
            "waste", "waste register", "FIR", "MUD", "CER code", "waste disposal",
            "waste contractor", "hazardous waste", "operational control",
            "work instruction", "waste management procedure",
        ],
        # Sprint J — atomic_requirements derived from Master KB §4.2.3.
        "atomic_requirements": [
            {
                "id": "14001_8_1.procedure",
                "text": "A documented waste management procedure exists with responsibilities and waste flow definition.",
                "verification_hint": "Procedure document covering segregation, storage, transport, disposal of all waste categories produced.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_1.register",
                "text": "A waste register is maintained, recording each waste stream and disposal event.",
                "verification_hint": "Register with rows per waste movement (date, type, quantity, CER code, destination).",
                "expected_evidence": ["record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_1.fir.completeness",
                "text": "FIR (formulari) records are complete, with valid destination and licensed waste operator.",
                "verification_hint": "Spot-check FIR forms: destination filled, CER code consistent with material, signed by transporter.",
                "expected_evidence": ["record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_1.contractor.licensed",
                "text": "Waste contractors are licensed and contracted; licence validity is tracked.",
                "verification_hint": "Contracts and authorisation copies retained; expiry dates of authorisations tracked.",
                "expected_evidence": ["supplier_document", "certificate"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_1.hazardous.tracked",
                "text": "Hazardous waste is identified and tracked separately with end-to-end traceability.",
                "verification_hint": "Hazardous waste codes (CER) appear with chain-of-custody documentation.",
                "expected_evidence": ["record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_1.training",
                "text": "Personnel handling waste have documented training.",
                "verification_hint": "Training records for waste-handling staff present and current.",
                "expected_evidence": ["training_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define or update waste management procedure with responsibilities and waste flows. Introduce electronic waste register. Implement mandatory training for waste handling staff. Conduct periodic audits of waste management area. Implement corrective actions for specific cases.",
            "who": "Environmental Manager / Operations Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "14001_8_2": {
        "id": "14001_8_2",
        "title": "8.2 Emergency preparedness and response",
        "area": "Operation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if no emergency plan exists for scenarios with significant environmental impact; MINOR if some scenarios not covered or drills not documented",
        "critical_sectors": ["Manufacturing", "Energy", "Construction", "Logistics"],
        "typical_ncs": [
            "Emergency plans absent for scenarios with significant environmental impact (spills, fires)",
            "No emergency drills conducted or drill results not documented",
            "No review of emergency plan adequacy after incidents or simulations",
            "SDS (Safety Data Sheets) for hazardous substances not available",
            "Emergency response plans not tested for specific critical scenarios",
        ],
        "evidence_keywords": [
            "emergency plan", "emergency response", "spill", "spillage",
            "emergency preparedness", "drill", "exercise", "fire",
            "hazardous substance", "SDS", "MSDS", "incident report",
            "emergency procedure", "environmental emergency",
        ],
        # Sprint J — atomic_requirements derived from Master KB §4.2.4.
        "atomic_requirements": [
            {
                "id": "14001_8_2.scenarios.identified",
                "text": "Emergency scenarios with potential environmental impact are identified.",
                "verification_hint": "List of scenarios (spill, fire, release) tied to the aspect register.",
                "expected_evidence": ["emergency_plan", "risk_assessment"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_2.plans.documented",
                "text": "Emergency plans exist for each identified scenario.",
                "verification_hint": "Plan documents per scenario, with roles, actions, equipment, communication.",
                "expected_evidence": ["emergency_plan"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_2.sds.available",
                "text": "Safety Data Sheets (SDS) are available for hazardous substances on site.",
                "verification_hint": "SDS register or files accessible to operating personnel.",
                "expected_evidence": ["record", "certificate"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_8_2.drills.performed",
                "text": "Emergency drills / exercises are performed and recorded.",
                "verification_hint": "Drill records dated within planned cadence; outcomes documented.",
                "expected_evidence": ["record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_8_2.evaluation.outcomes",
                "text": "Drill outcomes are evaluated and plans updated when weaknesses surface.",
                "verification_hint": "Post-drill evaluation reports; revision history on plans reflecting drill findings.",
                "expected_evidence": ["audit_report", "emergency_plan"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_8_2.communication",
                "text": "Plans include communication with external authorities and neighbouring sites where applicable.",
                "verification_hint": "Contacts and notification protocols included in the plan.",
                "expected_evidence": ["emergency_plan"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Draft or update emergency plans for all scenarios with significant environmental impact. Schedule and record emergency drills. Define evaluation criteria and record outcomes. Update plans based on drill results and incidents.",
            "who": "Environmental Manager / HSE Officer",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    # ── Section 9: Performance Evaluation ───────────────────────────────────

    "14001_9_1": {
        "id": "14001_9_1",
        "title": "9.1 Monitoring, measurement, analysis and evaluation",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Energy"],
        "typical_ncs": [
            "Environmental KPIs not defined or not monitored",
            "Monitoring equipment not calibrated or calibration records absent",
            "No analysis of environmental performance data",
        ],
        "evidence_keywords": [
            "environmental monitoring", "KPI", "measurement", "analysis",
            "calibration", "emissions monitoring", "discharge monitoring",
            "environmental performance indicators", "inspection records",
        ],
        "remediation_template": {
            "what": "Define environmental KPIs and monitoring frequency. Implement inspection and monitoring records. Ensure measurement equipment is calibrated. Link KPI results to management review.",
            "who": "Environmental Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "14001_9_1_2": {
        "id": "14001_9_1_2",
        "title": "9.1.2 Evaluation of compliance",
        "area": "Performance Evaluation",
        "is_spof": True,
        "critical_sectors": ["Manufacturing", "Energy", "Construction", "Logistics"],
        "typical_ncs": [
            "No periodic compliance evaluation performed",
            "Compliance evaluation not linked to legal register",
            "No records of how compliance status is determined",
        ],
        "evidence_keywords": [
            "compliance evaluation", "legal compliance", "regulatory compliance",
            "compliance status", "legal register review", "authority inspection",
        ],
        # Sprint R8 — atomic_requirements (TEMPLATE14001.docx §9.1.2: piano di
        # valutazione, esiti documentati [RETAIN SI], azioni su non conformità).
        "atomic_requirements": [
            {
                "id": "14001_9_1_2.evaluation.planned",
                "text": "Compliance evaluation is planned: frequency and method for evaluating fulfilment of compliance obligations are defined.",
                "verification_hint": "Evaluation plan/procedure with frequency; coverage of the obligations in the legal register.",
                "expected_evidence": ["procedure", "legal_register"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_9_1_2.results.documented",
                "text": "The results of compliance evaluations are documented and retained (mandatory record).",
                "verification_hint": "Dated evaluation reports or signed register sign-offs within the planned interval (checklist: RETAIN SI).",
                "expected_evidence": ["record", "legal_register", "audit_report"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_9_1_2.actions.on_noncompliance",
                "text": "Actions are taken and recorded when the evaluation finds non-fulfilment of an obligation.",
                "verification_hint": "Corrective actions linked to evaluation findings (checklist: azioni a fronte di mancata conformità).",
                "expected_evidence": ["nonconformity_record", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_9_1_2.knowledge.maintained",
                "text": "Knowledge and understanding of the current compliance status is maintained (status visible, fed to management review).",
                "verification_hint": "Compliance status column in the register; compliance evaluation among MR inputs.",
                "expected_evidence": ["legal_register", "management_review"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Implement a formal compliance evaluation process linked to the legal register. Define evaluation frequency (at minimum annually). Record outcomes and implement corrective actions for any gaps.",
            "who": "Environmental Manager / Legal Advisor",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "14001_9_2": {
        "id": "14001_9_2",
        "title": "9.2 Internal audit",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No environmental audit programme in place",
            "Audits not covering all significant environmental aspects",
            "Audit findings not followed up with corrective actions",
        ],
        "evidence_keywords": [
            "internal audit", "environmental audit", "audit programme",
            "audit report", "audit findings", "corrective action",
        ],
        "remediation_template": {
            "what": "Establish an annual environmental audit programme covering all significant aspects and EMS processes. Track findings through to closure.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "Next audit cycle",
            "effort": "MEDIUM",
        },
    },

    "14001_9_3": {
        "id": "14001_9_3",
        "title": "9.3 Management review",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Management review not conducted or not documented",
            "Environmental performance data not reviewed",
            "No actions defined from management review",
        ],
        "evidence_keywords": [
            "management review", "review minutes", "top management",
            "environmental performance", "review agenda", "review output",
        ],
        # Sprint R3 — atomic_requirements (ISO 14001:2015 §9.3 input/output
        # list + checklist guidance). Promise P3: the engine maps the MR
        # minutes against the required agenda items and names the missing ones.
        "atomic_requirements": [
            {
                "id": "14001_9_3.held.recorded",
                "text": "Management review is performed at planned intervals and documented (minutes or report with date and attendees including top management).",
                "verification_hint": "MR minutes/report; date, participants, periodicity consistent with the EMS planning.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_9_3.inputs.complete",
                "text": "The review covers the required inputs: status of previous actions; changes in internal/external issues, compliance obligations, significant aspects, risks/opportunities; environmental performance (NC/corrective actions, monitoring results, compliance evaluation, audit results); objectives achievement; adequacy of resources; communications from interested parties (incl. complaints); opportunities for improvement.",
                "verification_hint": "Map the minutes against the input list item by item. Name the items NOT discussed — that list is the finding.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_9_3.compliance.input",
                "text": "Compliance-obligation evaluation results and interested-party communications (including complaints) appear among the discussed inputs.",
                "verification_hint": "Specific mention of legal compliance status and external communications/complaints in the minutes.",
                "expected_evidence": ["management_review", "legal_register"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "14001_9_3.outputs.decisions",
                "text": "Outputs include conclusions on the continuing suitability, adequacy and effectiveness of the EMS, decisions on improvement opportunities, EMS changes and resources, plus actions where objectives are not achieved.",
                "verification_hint": "Decision/action section in the minutes with responsibilities and timescales assigned.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "14001_9_3.actions.followup",
                "text": "Actions from previous management reviews are tracked: their status is reported and open items carried forward.",
                "verification_hint": "Previous-actions status table or explicit follow-up discussion in the current minutes.",
                "expected_evidence": ["management_review", "record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Conduct and document formal management review including all required ISO 14001 §9.3 inputs. Record actions and decisions with owners and timescales.",
            "who": "Managing Director / Environmental Manager",
            "when_major": "30 days",
            "when_minor": "Next review cycle",
            "effort": "LOW",
        },
    },

    # ── Section 10: Improvement ──────────────────────────────────────────────

    "14001_10_2": {
        "id": "14001_10_2",
        "title": "10.2 Nonconformity and corrective action",
        "area": "Improvement",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No corrective action procedure for environmental nonconformities",
            "Root cause analysis not performed for environmental incidents",
            "Corrective actions not verified for effectiveness",
        ],
        "evidence_keywords": [
            "nonconformity", "corrective action", "environmental incident",
            "root cause", "CAPA", "environmental NCR", "effectiveness review",
        ],
        "remediation_template": {
            "what": "Implement a corrective action procedure for environmental nonconformities. Require root cause analysis (5 Whys) and effectiveness verification for all significant NCs.",
            "who": "Environmental Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "14001_10_3": {
        "id": "14001_10_3",
        "title": "10.3 Continual improvement",
        "area": "Improvement",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No evidence of proactive environmental improvement beyond corrective actions",
            "Improvement not linked to environmental performance review",
        ],
        "evidence_keywords": [
            "continual improvement", "environmental improvement", "innovation",
            "best practice", "improvement plan", "environmental performance",
        ],
        "remediation_template": {
            "what": "Establish an environmental continual improvement programme with documented objectives and outcomes. Review at management review.",
            "who": "Environmental Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },
}
