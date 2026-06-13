# Gap Analysis Prompt — Organisation's Own Operating Criteria (Fase 7)

## Standard context

You are NOT assessing an ISO standard in this batch: you are assessing the
organisation's OWN OPERATING CRITERIA — requirements the organisation has
defined for itself (internal protocols, client-imposed rules, group policies).
The PRD calls these "the corresponding requirement defined within the
organization's own operating criteria".

## How to assess operating criteria

1. The requirement text in each clause IS the standard: judge the evidence
   against what the requirement itself demands, not against any ISO clause.
2. Apply the SAME severity taxonomy as the base prompt (system vs punctual,
   MAJOR/MINOR/OBSERVATION/CONFORMANT, score bands) — internal requirements
   deserve the same rigour as ISO ones.
3. Where the requirement carries `atomic_requirements`, verify them item by
   item exactly as for ISO clauses.
4. Operating criteria often reference internal document names or codes
   (e.g. "form QF-12"): recognition stays SEMANTIC — a renamed or
   differently-labelled document that fulfils the same function satisfies
   the requirement.
5. In the `finding`, make clear that the requirement is an internal/operating
   criterion (e.g. "The operating criterion requires X; the documentation
   shows…"). Never present it as an ISO obligation.
