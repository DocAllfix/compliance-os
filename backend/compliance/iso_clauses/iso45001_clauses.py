"""
ISO 45001:2018 clause knowledge base.

SPoF per il PDF (§5.3):
- 6.1.2 Hazard identification & risk assessment — principale SPoF dell'intero sistema OH&S,
  da cui derivano tutte le misure di controllo
- 10.2/6.1.1 Near miss management — assenza = perdita dell'"early warning" e generatore
  di incidenti ripetuti
- 8.1.4 Contractor management — SPoF perché molte aziende esternalizzano attività ad alto
  rischio (manutenzioni, lavori in quota, lavori elettrici)
- 9.1 KPI e monitoraggio strutturato — assenza = incapacità di misurare performance e migliorare

Cluster NC frequenti da audit reali (§5.1 PDF):
    6.1.2, 5.4/7.3, 8.1.4, 9.1, 10.2

Derived metadata (added by Sprint 0):
    Four extra fields are derived at read time by `backend.compliance.clause_helpers`
    (criticality_tier, severity_floor, weight, expiry_relevant). Any clause MAY
    override a derived field by setting it explicitly in the dict. See the
    docstring of iso9001_clauses.py for the full derivation rules.

Tier distribution for ISO 45001 (computed at runtime — see Sprint 0 validation):
    critical ≈ 6 clauses (the HIGH_FREQUENCY + SPoF entries)
    passing  ≈ 3-4 clauses (§4.x context)
    standard ≈ the rest
"""
from __future__ import annotations

from typing import Any, Dict

ISO45001_SEVERITY_RULES = [
    "MAJOR if hazard identification and risk assessment process is absent or does not cover non-routine activities, maintenance, and contractors.",
    "MAJOR if near miss reporting process is completely absent — this is the primary early warning system for serious incidents.",
    "MAJOR if high-risk activities (work at height, electrical, confined spaces) are outsourced to contractors with no OH&S controls.",
    "MAJOR if legal/regulatory OH&S requirements are not identified or evaluated for compliance.",
    "Apply the same system vs punctual NC distinction: system = process non-existent; punctual = isolated deviation in an otherwise functioning system.",
]

ISO45001_HIGH_FREQUENCY_CLAUSES = [
    "45001_6_1_2",   # Hazard identification and risk assessment
    "45001_5_4",     # Worker participation and consultation
    "45001_7_3",     # Awareness
    "45001_8_1_4",   # Contractor management
    "45001_9_1",     # Monitoring and measurement
    "45001_10_2",    # Incident, nonconformity and corrective action
]

ISO45001_CLAUSES: Dict[str, Dict[str, Any]] = {

    # ── Section 4: Context ──────────────────────────────────────────────────

    "45001_4_1": {
        "id": "45001_4_1",
        "title": "4.1 Understanding the organisation and its context",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No documented analysis of internal and external OH&S issues",
            "Context analysis not linked to OH&S hazards and risks",
            "Issues not reviewed at management review",
        ],
        "evidence_keywords": [
            "context", "internal issues", "external issues", "OH&S context",
            "occupational health", "safety context", "strategic direction",
        ],
        "remediation_template": {
            "what": "Document an analysis of internal and external issues relevant to the organisation's OH&S purpose and strategic direction. Link to OH&S management system scope.",
            "who": "HSE Manager / Quality Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "45001_4_2": {
        "id": "45001_4_2",
        "title": "4.2 Understanding the needs and expectations of workers and other interested parties",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy"],
        "typical_ncs": [
            "Workers not included as key interested party in OH&S system",
            "Legal and regulatory OH&S requirements not captured",
            "No process to monitor changes in worker OH&S requirements",
        ],
        "evidence_keywords": [
            "interested parties", "workers", "stakeholders", "regulatory bodies",
            "trade union", "OH&S requirements", "legal requirements", "worker needs",
        ],
        "remediation_template": {
            "what": "Identify all relevant interested parties including workers, worker representatives, regulatory authorities, and contractors. Document their OH&S requirements.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "LOW",
        },
    },

    "45001_4_3": {
        "id": "45001_4_3",
        "title": "4.3 Determining the scope of the OH&S management system",
        "area": "Context",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "OH&S scope not documented or does not reflect actual activities and worksites",
            "Scope excludes high-risk activities without justification",
            "Scope not available as documented information",
        ],
        "evidence_keywords": [
            "scope", "OH&S scope", "boundaries", "worksites", "activities",
            "documented information",
        ],
        "remediation_template": {
            "what": "Define and document the OH&S management system scope covering all sites, activities, and workers under the organisation's control.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    # ── Section 5: Leadership ────────────────────────────────────────────────

    "45001_5_1": {
        "id": "45001_5_1",
        "title": "5.1 Leadership and commitment",
        "area": "Leadership",
        "is_spof": True,
        "critical_sectors": ["Construction", "Manufacturing", "Energy", "Logistics"],
        "typical_ncs": [
            "No evidence of top management involvement in OH&S system",
            "OH&S policy not signed or communicated by top management",
            "Resources for OH&S not allocated by top management",
            "Top management not participating in incident investigations",
        ],
        "evidence_keywords": [
            "top management", "leadership", "commitment", "OH&S policy",
            "resources", "management review", "accountability", "accountability",
        ],
        # Sprint R8 — atomic_requirements (ISO 45001 §5.1). Documentation-
        # verifiable items; 45001 leadership carries OH&S-specific duties.
        "atomic_requirements": [
            {
                "id": "45001_5_1.policy_objectives.established",
                "text": "Top management has established the OH&S policy and objectives, coherent with the organisation's hazards, risks and strategic direction.",
                "verification_hint": "Signed policy; OH&S objectives traceable to the risk assessment and strategy.",
                "expected_evidence": ["policy", "objective_plan"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_5_1.accountability.documented",
                "text": "Top management takes overall responsibility and accountability for the prevention of work-related injury and ill health (documented accountability, e.g. organigramma, deleghe, policy signature).",
                "verification_hint": "Signed policy/appointments showing employer-level accountability (in Italy: datore di lavoro, deleghe ex D.Lgs 81/08).",
                "expected_evidence": ["policy", "record", "certificate"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_5_1.resources.allocated",
                "text": "Evidence exists that top management provides the resources needed for the OH&S management system.",
                "verification_hint": "Resource decisions in MR outputs, PPE/equipment investments, RSPP appointment and budget.",
                "expected_evidence": ["management_review", "record", "certificate"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_5_1.review.led",
                "text": "Top management leads the management review and oversees OH&S performance (participation documented).",
                "verification_hint": "MR minutes list top management; incident/performance data reviewed at that level.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_5_1.consultation.promoted",
                "text": "Top management demonstrably promotes worker consultation and participation (committees established, time/resources provided).",
                "verification_hint": "Safety committee constitution, riunione periodica records, RLS appointment.",
                "expected_evidence": ["communication_record", "record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish documented evidence of top management OH&S commitment: signed OH&S policy, resource allocation records, and management review minutes with top management participation.",
            "who": "Managing Director / HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "45001_5_2": {
        "id": "45001_5_2",
        "title": "5.2 OH&S policy",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "OH&S policy not documented or not signed by top management",
            "Policy does not commit to prevention of work-related injury and ill health",
            "Policy not communicated to all workers",
        ],
        "evidence_keywords": [
            "OH&S policy", "health and safety policy", "policy statement",
            "injury prevention", "commitment", "communicated", "workers",
        ],
        # Sprint R3 — atomic_requirements from ISO 45001:2018 §5.2 (the policy
        # commitments are prescribed verbatim by the standard) + audit
        # checklist guidance. Wording checks — promise P4. 45001 prescribes
        # MORE commitments than 9001/14001: safe and healthy working
        # conditions, hazard elimination, worker consultation.
        "atomic_requirements": [
            {
                "id": "45001_5_2.policy.documented",
                "text": "An OH&S policy exists as documented information, identifiable as the current approved version (signed/dated by top management).",
                "verification_hint": "Policy document or OH&S manual section; approval signature or issue date.",
                "expected_evidence": ["policy", "quality_manual"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_5_2.commitment.safe_conditions",
                "text": "The policy wording contains an explicit commitment to provide safe and healthy working conditions for the prevention of work-related injury and ill health, appropriate to the organisation's specific hazards.",
                "verification_hint": "Look for the commitment in the text; it must reference prevention of injury AND ill health, not a generic 'safety matters to us'.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                # Sprint R7 — deterministic wording check (EN+IT variants)
                "wording_keywords": [["safe", "sicur", "salubr"], ["injur", "ill health", "infortun", "malatt", "health"]],
            },
            {
                "id": "45001_5_2.commitment.eliminate_hazards",
                "text": "The policy wording contains an explicit commitment to eliminate hazards and reduce OH&S risks.",
                "verification_hint": "Wording equivalent to 'eliminate hazards and reduce OH&S risks' present in the policy text.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                "wording_keywords": [["hazard", "pericol", "risk", "risch"], ["elimin", "reduc", "ridu"]],
            },
            {
                "id": "45001_5_2.commitment.consultation",
                "text": "The policy wording contains an explicit commitment to consultation and participation of workers and, where they exist, workers' representatives.",
                "verification_hint": "Consultation/participation commitment stated in the text (45001-specific — frequently missing from generic HSE policies).",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                "wording_keywords": [["consult", "particip", "partecipa"]],
            },
            {
                "id": "45001_5_2.commitment.legal_improvement",
                "text": "The policy wording contains explicit commitments to fulfil legal and other requirements AND to continual improvement of the OH&S management system.",
                "verification_hint": "Both commitments must appear in the text; mark PARTIAL when only one of the two is present and name the missing one.",
                "expected_evidence": ["policy"],
                "risk_if_missing": "MAJOR",
                "wording_keywords": [["legal", "requirement", "normativ", "cogent", "requisit"], ["improv", "migliora", "enhanc", "perfezion", "ottimizz"]],
            },
            {
                "id": "45001_5_2.communicated",
                "text": "The policy is communicated within the organisation, available to workers and their representatives, and to interested parties.",
                "verification_hint": "Distribution evidence, noticeboards, induction/training records referencing the policy.",
                "expected_evidence": ["communication_record", "policy", "training_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Issue a signed, dated OH&S policy including commitments to prevention of injury and ill health, compliance with legal requirements, and worker consultation. Communicate to all staff.",
            "who": "Managing Director",
            "when_major": "14 days",
            "when_minor": "30 days",
            "effort": "LOW",
        },
    },

    "45001_5_3": {
        "id": "45001_5_3",
        "title": "5.3 Organisational roles, responsibilities and authorities",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No RSPP (or equivalent OH&S manager) formally appointed",
            "Roles and responsibilities for OH&S processes not documented",
            "Worker representative (RLS) not appointed or not consulted",
        ],
        "evidence_keywords": [
            "RSPP", "HSE manager", "safety officer", "roles", "responsibilities",
            "authorities", "RLS", "worker representative", "organisation chart",
        ],
        "remediation_template": {
            "what": "Formally appoint an RSPP or equivalent OH&S manager. Document roles and responsibilities for all OH&S functions. Appoint and consult a worker OH&S representative.",
            "who": "Managing Director / HR Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    "45001_5_4": {
        "id": "45001_5_4",
        "title": "5.4 Consultation and participation of workers",
        "area": "Leadership",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy"],
        "typical_ncs": [
            "Workers not consulted on hazard identification and risk assessment",
            "No mechanism for workers to report OH&S concerns",
            "Worker representative not involved in OH&S decisions",
            "No evidence of worker participation in incident investigations",
        ],
        "evidence_keywords": [
            "consultation", "participation", "workers", "worker representative",
            "RLS", "safety committee", "toolbox talk", "worker feedback",
            "hazard reporting", "near miss reporting mechanism",
        ],
        # Sprint R8 — atomic_requirements (ISO 45001 §5.4 — high-frequency NC
        # cluster in real audits; the consultation chain node).
        "atomic_requirements": [
            {
                "id": "45001_5_4.mechanisms.established",
                "text": "Formal mechanisms for worker consultation and participation exist (safety committee, periodic meetings, worker representative).",
                "verification_hint": "Committee constitution, riunione periodica minutes (D.Lgs 81/08 art. 35), RLS appointment.",
                "expected_evidence": ["communication_record", "record", "certificate"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_5_4.consultation.risk_assessment",
                "text": "Workers (or their representatives) are consulted on hazard identification and risk assessment — with evidence, not just declared.",
                "verification_hint": "RLS signature/participation on the DVR or risk assessment records; consultation minutes referencing the assessment.",
                "expected_evidence": ["risk_assessment", "communication_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_5_4.reporting.channel",
                "text": "Workers have a working channel to report hazards, near misses and OH&S concerns.",
                "verification_hint": "Near-miss/hazard report forms with actual entries, reporting procedure, suggestion records.",
                "expected_evidence": ["nonconformity_record", "record", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_5_4.participation.incidents",
                "text": "Workers participate in incident investigation and in the development of policy and objectives.",
                "verification_hint": "Investigation records listing worker/RLS involvement; consultation evidence on policy/objectives.",
                "expected_evidence": ["nonconformity_record", "communication_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish formal worker consultation mechanisms: safety committee meetings, hazard/near miss reporting system, and worker involvement in risk assessment reviews. Record evidence of participation.",
            "who": "HSE Manager / HR Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 6: Planning ──────────────────────────────────────────────────

    "45001_6_1_1": {
        "id": "45001_6_1_1",
        "title": "6.1.1 Actions to address risks and opportunities",
        "area": "Planning",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No OH&S risk and opportunity register",
            "Risks identified but no mitigation actions defined",
            "Opportunities for OH&S improvement not considered",
        ],
        "evidence_keywords": [
            "OH&S risk", "opportunity", "risk register", "risk assessment",
            "mitigation", "preventive action", "risk-based thinking",
        ],
        # Sprint R3 — atomic_requirements (ISO 45001 §6.1.1 + checklist
        # guidance). Chain node for risk → operational control → monitoring.
        "atomic_requirements": [
            {
                "id": "45001_6_1_1.planning.process",
                "text": "The planning process determines risks and opportunities from the context (4.1), worker and interested-party needs (4.2), the hazards identified (6.1.2) and the applicable legal requirements.",
                "verification_hint": "Planning records linking risks/opportunities to hazard assessment outcomes and legal requirements.",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_1_1.documented",
                "text": "Documented information on the risks and opportunities and on the planning processes is maintained.",
                "verification_hint": "Maintained register or planning document with revision control.",
                "expected_evidence": ["risk_assessment", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_1.worker_input",
                "text": "Workers (and their representatives) are consulted in the risk/opportunity planning process.",
                "verification_hint": "Consultation records, RLS signature on the risk documents, safety committee minutes feeding the planning.",
                "expected_evidence": ["communication_record", "risk_assessment", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_1.emergency.input",
                "text": "Potential emergency situations are identified among the planning inputs (link to emergency preparedness, 8.2).",
                "verification_hint": "Emergency scenarios referenced in the planning/risk documents, coherent with the emergency plan.",
                "expected_evidence": ["risk_assessment", "emergency_plan"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish an OH&S risk and opportunity register linked to hazard assessment outcomes. Define mitigation actions and assign owners.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "HIGH",
        },
    },

    "45001_6_1_2": {
        "id": "45001_6_1_2",
        "title": "6.1.2 Hazard identification and assessment of OH&S risks",
        "area": "Planning",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if process non-existent or does not cover non-routine activities, maintenance, and contractors; PUNCTUAL if single job roles or update missing after process change",
        "critical_sectors": ["Construction", "Manufacturing", "Energy", "Logistics", "Healthcare"],
        "typical_ncs": [
            "Hazard identification incomplete — non-routine activities, maintenance, and contractors not covered",
            "Risk assessments dated and never reviewed after process or equipment changes",
            "Methodologies not applied in practice despite formal documentation",
            "No reference to near miss events in risk assessment updates",
            "Job safety analysis absent for high-risk activities (work at height, confined spaces, electrical)",
        ],
        "evidence_keywords": [
            "hazard identification", "risk assessment", "DVR", "DUVRI",
            "job safety analysis", "risk matrix", "work at height",
            "confined space", "electrical work", "non-routine", "maintenance risk",
            "contractor risk", "near miss", "incident analysis",
        ],
        # Sprint J — atomic_requirements derived from Master KB §5.2.1 and
        # public audit-checklist references (AUVA, IAF MD 1, ISOQAR). These
        # are verified per-clause by the LLM, so the verdict is grounded on a
        # named checklist rather than the model's internal knowledge alone.
        "atomic_requirements": [
            {
                "id": "45001_6_1_2.scope.routine",
                "text": "Hazard identification covers routine work activities.",
                "verification_hint": "Risk assessment lists ordinary day-to-day tasks with associated hazards.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_1_2.scope.non_routine",
                "text": "Hazard identification covers non-routine work (maintenance, shutdowns, exceptional operations).",
                "verification_hint": "Risk assessment names non-ordinary activities; presence of maintenance JSA or permit-to-work references.",
                "expected_evidence": ["risk_assessment", "procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_1_2.scope.contractors",
                "text": "Hazard identification covers contractor and outsourced activities performed on-site.",
                "verification_hint": "DUVRI present, contractor risk assessment, or explicit reference to outsourced work in the DVR.",
                "expected_evidence": ["risk_assessment", "supplier_document"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_1_2.scope.emergency",
                "text": "Hazard identification covers emergency and abnormal scenarios (fire, spill, equipment failure).",
                "verification_hint": "Emergency scenarios appear in the risk register; cross-reference to emergency plan exists.",
                "expected_evidence": ["risk_assessment", "emergency_plan"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_1_2.methodology.documented",
                "text": "A documented methodology for risk evaluation exists (criteria, scoring, prioritisation).",
                "verification_hint": "DVR or annex describes how risks are scored (probability, severity, controls).",
                "expected_evidence": ["risk_assessment", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_2.methodology.applied",
                "text": "Methodology is actually applied — risks carry scores and prioritisation, not just qualitative narrative.",
                "verification_hint": "Each hazard has a numerical score / band; prioritisation drives control selection.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_2.review.frequency",
                "text": "Review frequency for the risk assessment is defined and respected.",
                "verification_hint": "Stated revision date in DVR (e.g. annual or after process change); evidence of timely update.",
                "expected_evidence": ["risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_2.review.triggers",
                "text": "Risk assessment is updated after significant changes (new equipment, process changes, incidents, near misses).",
                "verification_hint": "Change-trigger references, or recent revision date aligned with documented changes.",
                "expected_evidence": ["risk_assessment", "nonconformity_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_2.controls.hierarchy",
                "text": "Control measures follow the hierarchy of controls (elimination > substitution > engineering > admin > PPE).",
                "verification_hint": "Controls are not exclusively PPE; engineering or organisational measures appear.",
                "expected_evidence": ["risk_assessment", "procedure"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_1_2.worker_participation",
                "text": "Workers (or their representatives) are consulted during hazard identification.",
                "verification_hint": "RLS / worker signature on DVR; reference to consultation in revision history.",
                "expected_evidence": ["risk_assessment", "communication_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Update or design a formal hazard identification and risk assessment process covering all activities and conditions including non-routine and emergency scenarios. Define review frequency. Train RSPP/supervisors. Link outputs to operational controls and objectives.",
            "who": "RSPP / HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "45001_6_1_3": {
        "id": "45001_6_1_3",
        "title": "6.1.3 Determination of legal and other requirements",
        "area": "Planning",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy", "Healthcare"],
        "typical_ncs": [
            "No legal register for OH&S legislation (e.g. Health & Safety at Work Act, CDM Regulations)",
            "Legal requirements not linked to operational controls",
            "No process to monitor changes in OH&S legislation",
        ],
        "evidence_keywords": [
            "legal register", "OH&S legislation", "Health and Safety at Work Act",
            "CDM regulations", "COSHH", "PUWER", "legal requirements",
            "compliance obligations", "regulatory requirements",
        ],
        "remediation_template": {
            "what": "Establish an OH&S legal register identifying all applicable legislation and regulations. Link each requirement to operational controls. Implement a process to monitor legislative changes.",
            "who": "HSE Manager / Legal Advisor",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "45001_6_2": {
        "id": "45001_6_2",
        "title": "6.2 OH&S objectives and planning",
        "area": "Planning",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "OH&S objectives not defined or not linked to significant hazards",
            "No action plan to achieve objectives with measurable targets",
            "Objectives not reviewed or updated",
        ],
        "evidence_keywords": [
            "OH&S objectives", "safety targets", "KPI", "action plan",
            "measurable", "accident rate", "near miss rate", "improvement targets",
        ],
        # Sprint R3 — atomic_requirements (ISO 45001 §6.2 + checklist
        # guidance). Promise P5 — label-agnostic: objectives may appear as
        # safety targets, KPIs, improvement programmes.
        "atomic_requirements": [
            {
                "id": "45001_6_2.objectives.documented",
                "text": "OH&S objectives exist as documented information at relevant functions — regardless of the label used (objectives, safety targets, KPIs, improvement programmes).",
                "verification_hint": "Objective plan, safety programme, KPI sheet or objectives embedded in the OH&S manual / management review.",
                "expected_evidence": ["objective_plan", "record", "management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_2.objectives.measurable",
                "text": "Objectives are measurable (where practicable): each carries a metric AND a target value (e.g. accident frequency rate, near-miss reporting count), not only a declared intention.",
                "verification_hint": "Per-entry check: number/threshold + indicator. Name the entries that are declared-only.",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_6_2.plan.defined",
                "text": "Planning to achieve each objective defines: actions, resources, responsibilities, deadlines and how the results will be evaluated.",
                "verification_hint": "Action plan columns: what, who, resources, by when, evaluation indicator.",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_2.coherence",
                "text": "Objectives are consistent with the OH&S policy and take account of the risk assessment results (6.1.2), the legal requirements and the outcomes of worker consultation.",
                "verification_hint": "Cross-check objective themes against policy commitments, significant hazards and consultation outcomes.",
                "expected_evidence": ["objective_plan", "policy", "risk_assessment"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_6_2.monitored",
                "text": "The implementation status of the objectives is monitored, communicated and updated.",
                "verification_hint": "Progress records, actual-vs-target tracking, objectives as a management review input.",
                "expected_evidence": ["record", "management_review", "objective_plan"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define measurable OH&S objectives linked to significant hazards and legal requirements. Document an action plan with owners, timescales, and measurement criteria.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 7: Support ───────────────────────────────────────────────────

    "45001_7_2": {
        "id": "45001_7_2",
        "title": "7.2 Competence",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy", "Healthcare"],
        "typical_ncs": [
            "Workers performing high-risk tasks without documented competence",
            "Competence requirements for safety-critical roles not defined",
            "Training records exist but no competence evaluation performed",
            "RSPP qualification not current or not documented",
        ],
        "evidence_keywords": [
            "competence", "training", "training records", "safety training",
            "RSPP qualification", "first aid", "fire safety", "work at height training",
            "confined space training", "forklift licence",
        ],
        "remediation_template": {
            "what": "Define competence requirements for all roles involving significant OH&S hazards. Update training records and implement competence evaluation. Verify safety-critical certifications are current.",
            "who": "HR Manager / HSE Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "45001_7_3": {
        "id": "45001_7_3",
        "title": "7.3 Awareness",
        "area": "Support",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy"],
        "typical_ncs": [
            "Workers unaware of significant hazards relevant to their work",
            "No OH&S induction or awareness programme for new workers",
            "Contractors not briefed on site-specific OH&S hazards",
        ],
        "evidence_keywords": [
            "safety awareness", "induction", "toolbox talk", "safety briefing",
            "hazard awareness", "risk communication", "OH&S policy awareness",
        ],
        # Sprint R8 — atomic_requirements (ISO 45001 §7.3). Includes the
        # 45001-specific right to remove oneself from imminent danger.
        "atomic_requirements": [
            {
                "id": "45001_7_3.policy_hazards.awareness",
                "text": "Evidence exists that workers are made aware of the OH&S policy, the hazards and risks relevant to THEM, and the controls in place.",
                "verification_hint": "Induction records, toolbox talks, informazione/formazione ex D.Lgs 81/08 covering job-specific hazards.",
                "expected_evidence": ["training_record", "communication_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_7_3.incidents.communicated",
                "text": "Incident outcomes relevant to workers are communicated (lessons learned, safety alerts).",
                "verification_hint": "Safety alerts, briefing records following incidents/near misses.",
                "expected_evidence": ["communication_record", "nonconformity_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_7_3.removal_right.communicated",
                "text": "Workers are informed of their ability to remove themselves from situations of serious and imminent danger, without reprisal (45001-specific requirement).",
                "verification_hint": "Induction/policy content stating the right to remove oneself from imminent danger (art. 44 D.Lgs 81/08 in Italy).",
                "expected_evidence": ["training_record", "policy", "communication_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_7_3.contractors.included",
                "text": "Awareness extends to contractors and visitors where they are exposed to the organisation's hazards.",
                "verification_hint": "Contractor site inductions, visitor briefings, DUVRI-related communications.",
                "expected_evidence": ["communication_record", "supplier_document"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Implement an OH&S awareness programme including induction for new workers, regular toolbox talks, and contractor site briefings. Record evidence of communication.",
            "who": "HSE Manager / Line Managers",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "LOW",
        },
    },

    # ── Section 8: Operation ─────────────────────────────────────────────────

    "45001_8_1": {
        "id": "45001_8_1",
        "title": "8.1 Operational planning and control",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy"],
        "typical_ncs": [
            "No documented operational controls for significant hazards",
            "Work instructions not available at point of use for high-risk tasks",
            "Permit-to-work system absent for high-risk activities",
        ],
        "evidence_keywords": [
            "operational control", "work instruction", "permit to work",
            "safe system of work", "method statement", "RAMS",
            "operational procedure", "control measures",
        ],
        "remediation_template": {
            "what": "Document operational controls and work instructions for all significant hazards. Implement a permit-to-work system for high-risk activities (work at height, electrical, confined spaces).",
            "who": "Operations Manager / HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "45001_8_1_4": {
        "id": "45001_8_1_4",
        "title": "8.1.4 Procurement — contractors and outsourcing",
        "area": "Operation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if high-risk activities are outsourced with no OH&S controls on contractors; PUNCTUAL if controls exist but documentation gaps for specific contractors",
        "critical_sectors": ["Construction", "Manufacturing", "Energy", "Logistics"],
        "typical_ncs": [
            "No OH&S qualification criteria for contractors performing high-risk activities",
            "High-risk activities (work at height, electrical, confined spaces) outsourced without OH&S controls",
            "No DUVRI (coordination document) for contractor activities with interference risks",
            "Contractors not briefed on site-specific hazards before work commences",
            "No monitoring of contractor OH&S performance",
        ],
        "evidence_keywords": [
            "contractor", "subcontractor", "DUVRI", "contractor qualification",
            "contractor OH&S", "procurement", "outsourcing", "contractor briefing",
            "contractor register", "contractor assessment", "work at height contractor",
        ],
        # Sprint J — atomic_requirements derived from Master KB §5.2.3.
        "atomic_requirements": [
            {
                "id": "45001_8_1_4.qualification.criteria",
                "text": "Documented OH&S qualification criteria for contractors exist (legal compliance, training, equipment, insurance).",
                "verification_hint": "Procurement procedure or contractor register lists OH&S criteria, not just commercial criteria.",
                "expected_evidence": ["procedure", "supplier_document"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_8_1_4.qualification.applied",
                "text": "Contractors actually performing work have been qualified against the criteria (not just declared).",
                "verification_hint": "Qualified-contractor register matches contractors named in actual purchase orders / invoices.",
                "expected_evidence": ["supplier_document", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_8_1_4.coordination.duvri",
                "text": "DUVRI (Documento Unico di Valutazione Rischi da Interferenze) issued for contractor activities with interference risk.",
                "verification_hint": "DUVRI document present for relevant contractors; covers interference hazards and coordination measures.",
                "expected_evidence": ["risk_assessment", "supplier_document"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_8_1_4.briefing.records",
                "text": "Contractors receive a documented site-specific safety briefing before commencing work.",
                "verification_hint": "Briefing records signed by contractor representatives; specific to the site and activity.",
                "expected_evidence": ["training_record", "communication_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_8_1_4.high_risk.controls",
                "text": "Contractor activities classified as high-risk (work at height, electrical, confined spaces) carry specific OH&S controls.",
                "verification_hint": "Permit-to-work, specific JSA, supervisor presence documented for high-risk contractor jobs.",
                "expected_evidence": ["procedure", "record", "risk_assessment"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_8_1_4.monitoring",
                "text": "Contractor OH&S performance is monitored (inspections, audits, incident reporting).",
                "verification_hint": "Contractor audit reports, inspection records, or incident logs referencing contractors.",
                "expected_evidence": ["audit_report", "nonconformity_record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define contractor qualification procedure with OH&S criteria and security requirements. Issue and control DUVRI for all contractors. Implement mandatory safety briefings. Conduct regular audits of critical contractors.",
            "who": "HSE Manager / Procurement Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "45001_8_2": {
        "id": "45001_8_2",
        "title": "8.2 Emergency preparedness and response",
        "area": "Operation",
        "is_spof": False,
        "critical_sectors": ["Manufacturing", "Energy", "Construction"],
        "typical_ncs": [
            "No emergency response plan for OH&S scenarios (fire, injury, chemical release)",
            "Emergency drills not conducted or not documented",
            "First aid arrangements inadequate for risk level",
        ],
        "evidence_keywords": [
            "emergency plan", "fire plan", "evacuation", "first aid",
            "emergency drill", "emergency response", "mustering",
            "AED", "first aider", "emergency procedure",
        ],
        "remediation_template": {
            "what": "Develop or update OH&S emergency plans for all significant scenarios. Conduct and record emergency drills. Ensure adequate first aid provision for the risk level and site size.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    # ── Section 9: Performance Evaluation ───────────────────────────────────

    "45001_9_1": {
        "id": "45001_9_1",
        "title": "9.1 Monitoring, measurement, analysis and evaluation",
        "area": "Performance Evaluation",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if no OH&S KPIs defined and no monitoring programme; PUNCTUAL if KPIs exist but some evidence incomplete or some inspections missed",
        "critical_sectors": ["Construction", "Manufacturing", "Energy"],
        "typical_ncs": [
            "OH&S KPIs not defined or not monitored (accident rate, near miss rate, inspection frequency)",
            "Planned inspections and safety tours not carried out",
            "Monitoring equipment (gas detectors, noise meters) not calibrated",
            "No analysis of OH&S performance data for trends",
        ],
        "evidence_keywords": [
            "OH&S KPI", "accident rate", "near miss rate", "inspection records",
            "safety inspection", "safety tour", "monitoring", "measurement",
            "calibration", "performance indicators", "RIDDOR",
        ],
        # Sprint J — atomic_requirements derived from Master KB §5.2.4.
        "atomic_requirements": [
            {
                "id": "45001_9_1.kpi.defined",
                "text": "OH&S KPIs are formally defined (with name, calculation, target, frequency).",
                "verification_hint": "KPI list / dashboard with measurable indicators (e.g. LTIFR, near-miss rate, inspection completion).",
                "expected_evidence": ["procedure", "objective_plan", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_9_1.kpi.leading_and_lagging",
                "text": "KPI set includes both leading (preventive: inspections, training hours, near miss rate) and lagging (reactive: incidents, lost-time injuries) indicators.",
                "verification_hint": "Mix of preventive and reactive metrics, not only injury counts.",
                "expected_evidence": ["objective_plan", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_9_1.monitoring.schedule",
                "text": "Scheduled safety inspections and tours are planned and recorded.",
                "verification_hint": "Inspection plan with frequency; signed inspection records or checklists.",
                "expected_evidence": ["record", "procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_9_1.equipment.calibration",
                "text": "Monitoring equipment (gas detectors, noise meters, vibration meters, lux meters) is calibrated to documented schedule.",
                "verification_hint": "Calibration certificates / records for OH&S measurement devices; next-due date tracked.",
                "expected_evidence": ["calibration_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_9_1.analysis.trends",
                "text": "OH&S performance data is analysed for trends, not only collected.",
                "verification_hint": "Trend report, period-over-period comparison, charts or commentary on direction.",
                "expected_evidence": ["audit_report", "management_review", "record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_9_1.link.management_review",
                "text": "KPI outputs feed the management review (clause 9.3).",
                "verification_hint": "Management-review minutes reference the same KPIs; corrective actions traced from KPI performance.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Define and implement OH&S KPIs including both leading and lagging indicators. Schedule and record regular safety inspections and tours. Ensure monitoring equipment is calibrated. Link KPI results to management review.",
            "who": "HSE Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },

    "45001_9_1_2": {
        "id": "45001_9_1_2",
        "title": "9.1.2 Evaluation of compliance",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": ["Construction", "Manufacturing", "Energy"],
        "typical_ncs": [
            "No periodic OH&S legal compliance evaluation performed",
            "Compliance evaluation not linked to legal register",
            "No records of compliance status for OH&S legislation",
        ],
        "evidence_keywords": [
            "compliance evaluation", "legal compliance", "OH&S legislation",
            "compliance status", "regulatory compliance", "enforcement visit",
        ],
        "remediation_template": {
            "what": "Implement a formal OH&S compliance evaluation process linked to the legal register. Define evaluation frequency (minimum annually). Record outcomes and corrective actions.",
            "who": "HSE Manager / Legal Advisor",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "MEDIUM",
        },
    },

    "45001_9_2": {
        "id": "45001_9_2",
        "title": "9.2 Internal audit",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No OH&S audit programme in place",
            "Audits not covering high-risk processes and activities",
            "Audit findings not followed up with corrective actions",
        ],
        "evidence_keywords": [
            "internal audit", "OH&S audit", "safety audit", "audit programme",
            "audit report", "audit findings", "corrective action",
        ],
        "remediation_template": {
            "what": "Establish an annual OH&S audit programme prioritising high-risk processes. Train internal auditors. Track findings through to closure.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "Next audit cycle",
            "effort": "MEDIUM",
        },
    },

    "45001_9_3": {
        "id": "45001_9_3",
        "title": "9.3 Management review",
        "area": "Performance Evaluation",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "Management review not conducted or not documented",
            "OH&S performance data not reviewed by top management",
            "No actions defined from management review outputs",
        ],
        "evidence_keywords": [
            "management review", "review minutes", "top management",
            "OH&S performance", "review agenda", "review output",
        ],
        # Sprint R3 — atomic_requirements (ISO 45001:2018 §9.3 input/output
        # list). Promise P3: map MR minutes against required agenda items and
        # name the missing ones. 45001 adds worker-specific inputs/outputs.
        "atomic_requirements": [
            {
                "id": "45001_9_3.held.recorded",
                "text": "Management review is performed at planned intervals and documented (minutes or report with date and attendees including top management).",
                "verification_hint": "MR minutes/report; date, participants, periodicity consistent with OH&S planning.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_9_3.inputs.complete",
                "text": "The review covers the required inputs: status of previous actions; changes in internal/external issues incl. legal requirements and risks/opportunities; OH&S performance (incidents, nonconformities and corrective actions, monitoring results, audit results, worker consultation/participation outcomes, hazards and risks status); objectives achievement; adequacy of resources; relevant communications with interested parties; opportunities for continual improvement.",
                "verification_hint": "Map the minutes against the input list item by item. Name the items NOT discussed — that list is the finding.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_9_3.worker.input",
                "text": "Worker consultation and participation outcomes appear among the discussed inputs (45001-specific requirement).",
                "verification_hint": "Mention of safety committee outcomes, RLS feedback, worker-raised concerns in the minutes.",
                "expected_evidence": ["management_review", "communication_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_9_3.outputs.decisions",
                "text": "Outputs include conclusions on the continuing suitability, adequacy and effectiveness of the OH&S MS, decisions on improvement opportunities, system changes, resources and actions needed, plus implications for the strategic direction.",
                "verification_hint": "Decision/action section with responsibilities and timescales assigned.",
                "expected_evidence": ["management_review"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_9_3.outputs.communicated",
                "text": "Relevant management review outputs are communicated to workers and, where they exist, workers' representatives (45001-specific requirement).",
                "verification_hint": "Communication evidence: distribution of decisions, noticeboard, safety meeting where outcomes were shared.",
                "expected_evidence": ["communication_record", "management_review"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Conduct and document formal management review including all required ISO 45001 §9.3 inputs including incident data, legal compliance, and KPI performance.",
            "who": "Managing Director / HSE Manager",
            "when_major": "30 days",
            "when_minor": "Next review cycle",
            "effort": "LOW",
        },
    },

    # ── Section 10: Improvement ──────────────────────────────────────────────

    "45001_10_2": {
        "id": "45001_10_2",
        "title": "10.2 Incident, nonconformity and corrective action",
        "area": "Improvement",
        "is_spof": True,
        "nc_system_vs_punctual": "SYSTEM if no incident/near miss reporting process or culture of reporting absent; PUNCTUAL if process exists but some incidents not analysed or CAPA incomplete",
        "critical_sectors": ["Construction", "Manufacturing", "Energy", "Healthcare", "Logistics"],
        "typical_ncs": [
            "Near misses not recorded or not analysed — culture of reporting absent",
            "Incident investigations focus only on injuries, not near misses",
            "Root cause analysis not performed for significant incidents",
            "No corrective actions defined or followed up",
            "Repeated incidents in the same area or activity without systemic corrective action",
        ],
        "evidence_keywords": [
            "incident", "near miss", "accident", "injury", "RIDDOR",
            "incident investigation", "root cause analysis", "corrective action",
            "CAPA", "5 whys", "incident register", "near miss register",
            "accident book", "first aid record",
        ],
        # Sprint J — atomic_requirements derived from Master KB §5.2.2.
        "atomic_requirements": [
            {
                "id": "45001_10_2.process.defined",
                "text": "A documented procedure for incident and near-miss reporting exists.",
                "verification_hint": "Procedure document with definitions (incident, near miss), reporting channels, and timelines.",
                "expected_evidence": ["procedure"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_10_2.near_miss.recording",
                "text": "Near misses are actually recorded — not only injury events.",
                "verification_hint": "Register containing near-miss entries; volume consistent with workplace activity (zero near misses is itself a red flag).",
                "expected_evidence": ["nonconformity_record", "record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_10_2.investigation.rca",
                "text": "Significant incidents and near misses receive a root-cause analysis (5 Whys, Ishikawa, or equivalent).",
                "verification_hint": "RCA documents attached to incident records; not just immediate-cause descriptions.",
                "expected_evidence": ["nonconformity_record", "audit_report"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_10_2.capa.actions",
                "text": "Corrective actions are defined for each significant incident, with owner and deadline.",
                "verification_hint": "CAPA log shows action / owner / deadline / status / closure date for each entry.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MAJOR",
            },
            {
                "id": "45001_10_2.capa.effectiveness",
                "text": "Effectiveness of corrective actions is verified after implementation.",
                "verification_hint": "Effectiveness-check entries on CAPA log; signed-off verification date distinct from implementation date.",
                "expected_evidence": ["nonconformity_record"],
                "risk_if_missing": "MINOR",
            },
            {
                "id": "45001_10_2.trend_review",
                "text": "Incidents and near misses are periodically reviewed for trends (cluster by location, activity, root cause).",
                "verification_hint": "Trend report; safety committee minutes referencing aggregated incident analysis.",
                "expected_evidence": ["management_review", "audit_report", "record"],
                "risk_if_missing": "MINOR",
            },
        ],
        "remediation_template": {
            "what": "Establish a near miss and incident reporting procedure with clear definitions. Implement an easy-to-use reporting mechanism. Require root cause analysis and CAPA for all significant near misses and incidents. Conduct periodic review to identify trends.",
            "who": "HSE Manager",
            "when_major": "30 days",
            "when_minor": "60 days",
            "effort": "HIGH",
        },
    },

    "45001_10_3": {
        "id": "45001_10_3",
        "title": "10.3 Continual improvement",
        "area": "Improvement",
        "is_spof": False,
        "critical_sectors": [],
        "typical_ncs": [
            "No evidence of proactive OH&S improvement beyond corrective actions",
            "Improvement not linked to OH&S performance review outcomes",
        ],
        "evidence_keywords": [
            "continual improvement", "safety improvement", "innovation",
            "best practice", "improvement plan", "OH&S performance",
        ],
        "remediation_template": {
            "what": "Establish an OH&S continual improvement programme with documented objectives and outcomes. Review at management review.",
            "who": "HSE Manager",
            "when_major": "45 days",
            "when_minor": "90 days",
            "effort": "MEDIUM",
        },
    },
}
