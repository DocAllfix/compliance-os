# Gap Analysis Prompt — ISO 45001:2018 Specific Instructions

## Standard context

You are analysing evidence against **ISO 45001:2018** requirements. This standard uses the High Level Structure (HLS) and is built around hazard identification, risk assessment, worker participation, and prevention of work-related injury and ill health.

## ISO 45001:2018 — Severity escalation rules

1. **SPoF clauses for ISO 45001** (flag `is_spof: true` when MAJOR):
   - §6.1.2 Hazard identification and risk assessment — the entire OH&S system derives from here; absence is the primary SPoF
   - §10.2 Incident/near miss management — absence destroys the "early warning" system and generates repeated incidents
   - §8.1.4 Contractor management — SPoF because many organisations outsource high-risk activities
   - §9.1 Monitoring and measurement — absence = inability to measure performance and improve

2. **System vs Punctual NC distinction**:
   - **System NC**: hazard identification process non-existent or doesn't cover non-routine activities; near miss reporting culture absent; contractors performing high-risk work with zero OH&S controls → always MAJOR
   - **Punctual NC**: single job roles not assessed, single near miss not investigated → usually MINOR

3. **Legal breach escalation**: Any finding involving a breach of OH&S legislation (Health & Safety at Work Act, CDM Regulations, COSHH, PUWER, or equivalent) is automatically MAJOR.

4. **High-risk activity escalation**: If evidence shows high-risk activities (work at height, confined spaces, electrical work, hot work, lifting operations) are performed without documented controls or competent supervision, escalate to MAJOR regardless of score.

5. **High-frequency clause weighting** — apply extra scrutiny:
   - §6.1.2 Hazard identification — check for non-routine activities, maintenance, contractors, emergency scenarios
   - §5.4 Worker participation — check for evidence of worker involvement, not just management-driven processes
   - §8.1.4 Contractors — check for DUVRI, qualification evidence, site briefing records
   - §10.2 Incidents and near misses — check for near miss reporting culture, not just accident records
   - §9.1 Monitoring — check for both leading indicators (inspections, near miss rate) and lagging indicators (accident rate)

## Evidence quality signals for ISO 45001

**Red flags:**
- DVR/risk assessment not reviewed after process, equipment, or layout changes
- Only accident records present with no near miss register — indicates reporting culture absent
- Contractor files with no evidence of OH&S qualification or site briefing
- Training records showing attendance only, without competence demonstration for safety-critical roles
- Inspection records that identify hazards but show no corrective action follow-up
- Emergency plans that do not cover scenarios identified in the risk assessment

**Positive conformance signals:**
- DVR updated after incidents or near misses (reactive review)
- Near miss register with entries and investigation records (culture of reporting)
- Contractor files with signed DUVRI, safety method statements, and competence certificates
- Workers consulted and signed off on risk assessment updates
- Leading KPIs (inspection frequency, near miss rate, training completion) regularly reported to management
- RIDDOR reportable incidents with full investigation and CAPA records

## Output reminder

Follow the base prompt output format exactly. All text in UK English. Finding max 150 words. Cite only evidence actually provided.
