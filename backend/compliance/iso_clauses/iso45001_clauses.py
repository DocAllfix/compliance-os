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
