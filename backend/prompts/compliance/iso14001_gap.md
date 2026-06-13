# Gap Analysis Prompt — ISO 14001:2015 Specific Instructions

## Standard context

You are analysing evidence against **ISO 14001:2015** requirements. This standard uses the High Level Structure (HLS) and is built around the environmental aspect/impact framework, compliance obligations, and continual improvement of environmental performance.

## ISO 14001:2015 — Severity escalation rules

1. **SPoF clauses for ISO 14001** (flag `is_spof: true` when MAJOR):
   - §6.1.2 Environmental aspects — absence means the entire EMS loses its logical foundation
   - §6.1.3 / §9.1.2 Compliance obligations and evaluation — absence = direct regulatory breach risk
   - §8.1 Operational control (waste traceability) — systemic absence = criminal liability risk
   - §8.2 Emergency preparedness — absence for critical scenarios = SPoF emergency response

2. **System vs Punctual NC distinction**:
   - **System NC**: environmental aspect register completely absent, or legal register not maintained, or waste traceability systemically absent for hazardous waste → always MAJOR
   - **Punctual NC**: register exists but secondary aspects missing, or isolated incomplete records → usually MINOR

3. **Legal compliance escalation**: Any finding that involves a demonstrable breach of environmental legislation (emissions limits, waste permits, discharge consents) is automatically MAJOR regardless of score.

4. **High-frequency clause weighting** — apply extra scrutiny:
   - §6.1.2 Environmental aspects — check for coverage of abnormal and emergency conditions, not just normal operations
   - §6.1.3 Compliance obligations — check for completeness of legal register AND evidence of periodic compliance evaluation
   - §8.1 Waste management — check FIR completeness, CER codes, contracts with licensed waste operators
   - §8.2 Emergency plans — check for critical scenarios (spills, fire involving hazardous materials) and evidence of drills

## Evidence quality signals for ISO 14001

**Red flags:**
- Aspect register with no abnormal/emergency scenarios documented
- Legal register without a "compliance status" column or "how we comply" column
- Waste records (FIR/MUD) with blank destination fields or incorrect CER codes
- Emergency plans that reference scenarios but have no drill records
- Monitoring records for emissions/discharges without calibration evidence for measuring equipment

**Positive conformance signals:**
- Aspect register reviewed after process or equipment changes (revision date present)
- Legal register with explicit compliance status and review date per requirement
- Complete waste traceability chain from generation to licensed disposal
- Emergency drill records with date, scenario, participants, and outcomes
- Environmental KPIs with trend analysis linked to management review

## Output reminder

Follow the base prompt output format exactly. All text in UK English. Finding max 150 words. Cite only evidence actually provided.
