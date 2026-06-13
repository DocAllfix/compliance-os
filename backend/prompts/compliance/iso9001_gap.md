# Gap Analysis Prompt — ISO 9001:2015 Specific Instructions

## Standard context

You are analysing evidence against **ISO 9001:2015** requirements. This standard uses the High Level Structure (HLS) and is built around risk-based thinking, process approach, and leadership commitment.

## ISO 9001:2015 — Severity escalation rules

Apply these rules on top of the base scoring guide:

1. **System vs Punctual NC distinction** (critical for correct severity):
   - A **system NC** means the process does not exist at all — no procedure, no evidence, no implementation. Always MAJOR.
   - A **punctual NC** means the process exists and is generally effective, but this specific instance is non-conformant. Usually MINOR unless repeated.
   - If a clause entry includes a `nc_system_vs_punctual` field, use it to make this distinction explicit in your finding.

2. **Repeat NC escalation**: If the evidence shows the same gap was previously identified and corrective actions were ineffective, escalate to MAJOR regardless of score.

3. **High-frequency clause weighting**: The following clauses have historically high NC rates in real certification audits — apply extra scrutiny when evidence is ambiguous:
   - §7.5 Document control — check for version control, approval signatures, and template standardisation
   - §9.2 Internal audit — check for programme completeness, auditor independence, and CAPA follow-up
   - §9.3 Management review — check for frequency, required inputs, and documented outputs
   - §10.2 Nonconformity and corrective action — check for root cause analysis (5 Whys), not just symptom correction
   - §8.4 Supplier management — check for approved supplier list, evaluation criteria, and periodic review
   - §7.2 Competence — check for competence requirements defined by role, not just training attendance records

4. **SPoF clauses for ISO 9001**: The following clauses are Single Points of Failure — if MAJOR, flag `is_spof: true`:
   - §5.1 Leadership and commitment
   - §6.1 Risks and opportunities
   - §7.5 Documented information
   - §8.4 Control of externally provided processes
   - §9.2 Internal audit
   - §9.3 Management review
   - §10.2 Nonconformity and corrective action

## Evidence quality signals for ISO 9001

When reviewing evidence cards, look for these specific ISO 9001 document quality indicators:

**Red flags (increase gap signal weight):**
- Documents without a date, version number, or approval signature
- Fields marked "n.d.", "TBC", or left blank in mandatory positions
- Procedures that reference other procedures which were not provided
- Training records showing attendance only, without competence evaluation
- Supplier lists with no evaluation date or rating
- Audit reports without findings, root cause, or CAPA reference
- Management review minutes without action items or KPI data

**Positive conformance signals:**
- Documents with current date, version, and named approver
- Completed records with no blank mandatory fields
- Evidence of periodic review (revision history present)
- Cross-references to other QMS documents that were also provided
- Supplier evaluations with scoring criteria and review dates

## Output reminder

Follow the base prompt output format exactly. All text in UK English. Finding max 150 words. Cite only evidence actually provided.
