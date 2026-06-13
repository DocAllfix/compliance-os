---
register: product
---

# ComplianceOS — Product Brief

## What it is

ComplianceOS is a self-service compliance analysis tool that helps managers in mid-sized companies assess their own ISO 9001 / 14001 / 45001 conformance against the documentation they already have. Users upload a ZIP of their company documents (procedures, manuals, registers, policies), the system analyses them clause-by-clause against the relevant ISO standards, and produces a gap report with severity-rated findings, source-cited evidence, and an actionable remediation plan.

It is not an audit tool. It is not adversarial. It is an advisory companion that walks the manager through what their documents say, what the standard requires, and where the distance is.

## Users

### Primary: the company manager doing compliance in autonomy

Not a compliance specialist. Not an external consultant. The person inside a 50-250 employee company who has been told "we need ISO 14001" or "the certification is expiring, prepare it" and has to figure it out, alongside their actual job. Often the QHSE part-timer, the operations manager, or a director who inherited the file.

What they know: the business, the people, the documents, the customer pressure that triggered the certification. What they don't know: which specific clause needs which specific evidence, what counts as a Major non-conformity, how to phrase a remediation action.

What they need from ComplianceOS:
- Clarity on **what's missing**, in plain language, not auditor jargon.
- A **source they can verify** — every finding must point back to the exact document and page that supports (or fails to support) the claim.
- An **action plan they can hand to a team** — Who, What, When, with realistic effort estimates.
- A **trace of progress** between assessments — "three months ago you were at 47%, today you're at 64%; here's what closed, here's what's still open."
- A **way to ask follow-up questions** with confidence the answer is grounded in their own data, not generic boilerplate.

### Secondary: future, but not part of MVP

Five Rise Consultancy advisors, who would use the same tool to triage client documentation before scheduling on-site work. Treat as future market — design decisions favour the manager, not the consultant.

## Use scene

A bright office. A 27" external monitor. A two-hour block carved out of the calendar to "look at the compliance file before next month's audit." Coffee. Browser open. The PDF of the company's quality manual in another tab. The ZIP of procedures on the desktop.

This forces:
- **Light theme by default** (ambient light is high; dark mode is a category-reflex for "tools" that doesn't fit a manager's workflow).
- **Information density is acceptable** (large screen, long session, full attention — we are not on a phone in a queue).
- **The screen can be a working surface** (split panels, multiple panes open at once) rather than a hand-held one.

## Voice & tone

**Patient mentor.** Not a friendly startup, not an austere enterprise tool, not a gamified fitness app. Speaks like a competent colleague who has done this many times before and is happy to explain the why, but does not waste words.

Concrete examples of the right register:

- ✅ "The procedure for supplier qualification is present, but it does not specify periodic re-evaluation criteria. Clause 8.4 requires this to be documented. Below: the page where this should be added, and a draft of what to add."
- ❌ "Awesome work uploading your documents! 🎉 We found some opportunities for you to level up your compliance game!"
- ❌ "DEFICIENCY DETECTED: Clause 8.4 — Supplier qualification subprocess incomplete. Severity: Major. Action required."
- ❌ "I'd be happy to help you understand this finding! Let me walk you through what it means in a friendly way!"

Plain language is non-negotiable. ISO terminology like "non-conformity", "Major", "Minor", "evidence" is fine — it's the lexicon of the field. But "evidence triangulation", "systemic deviation", "audit programme cycle" is not — it's auditor jargon and the manager doesn't speak it.

## Anti-references

What ComplianceOS must **not** look or feel like:

- **Vanta / Drata.** The first reflex when an AI is asked to design a "compliance dashboard". White surfaces, navy + green-accent, identical KPI cards in a grid, a radar chart on the home screen. We are explicitly avoiding this lane. Hard ban.
- **Salesforce / SAP / Dynamics 365.** Enterprise legacy. Giant icon-only sidebar, dense tables full of inline action buttons, modals stacked on modals, IT-administrator language. Not the manager's world.
- **Apple Health / Calm / Headspace.** Pastel surfaces, soft 16px-rounded corners, gentle gradients. Beautiful, but it cannot reflect the gravity of a regulatory file with legal implications.
- **Slack / Discord chat tone.** Emoji, exclamation marks, "you got this!" energy. Compliance is not a celebration.

## North-star visual references

ComplianceOS sits between two visual families: **modern documentation sites** for the layout and reading experience, and **legal-tech reference platforms** for the gravitas and the citation-first feel. Borrow from both, converge on neither.

### Primary lane — modern docs (Stripe Docs, Mintlify, Vercel Docs, Linear changelog)

Sets the layout and the reading rhythm.

- Two-column or three-column structures: navigation/index on the left, rich content centre, contextual detail on the right.
- Strong typographic hierarchy doing the heavy lifting — colour is restrained.
- Light theme by default, comfortable to read for an hour.
- Generous but not wasteful whitespace.
- Code, data, and excerpts treated as first-class typographic objects, not decoration.
- A single accent colour used sparingly for state (active link, selected row, current section).

### Secondary lane — legal-tech reference (Westlaw, Lex Machina, Practical Law)

Sets the seriousness and the citation-first feel. ComplianceOS reasons about regulatory text and produces findings that may end up in a board meeting; it should feel closer to a legal research tool than to a SaaS dashboard.

Borrow specifically:
- **Citation as a first-class element.** Every clause reference, every evidence link, every quoted excerpt looks like a legal citation: monospaced or semibold tabular figures, deliberately bracketed, hover-revealed source. The user feels the chain of provenance is real.
- **Treatment of regulatory text.** Clause numbers, standard names ("ISO 9001 §8.4"), and legal-style hierarchies are typographically distinctive — usually a serif or a tabular sans, never decorative.
- **Tabular density where it earns it.** Findings tables, clause matrices, and audit trails can be dense and information-rich, the way a case-law table is. The manager wants to scan many rows quickly; this is where docs-style spaciousness yields to legal-style tables.
- **Quiet authority.** The interface does not "promote" or "encourage" — it presents what is the case. Same posture as a research platform.

Do **not** borrow:
- The early-2000s skin of Westlaw and similar (gradient blue toolbars, hard-edged dialog frames). We pull the *information posture*, not the visual decade.

### What "tone of the visual" means here

Serious work happening in a calm, well-lit room — but with a desk drawer of legal references nearby. Editorial, not enterprise. Authoritative, not austere. Confident enough to use a single restrained accent and trust typography to do the rest.

## Strategic principles

These four principles co-decide every design choice. Treat all four as primary; trade-offs between them are themselves a design problem.

### 1. Source-grounding

Every claim links to its source. A score is a link to the documents that produced it. A finding is a link to the page where the gap is. A chat answer is a link to the excerpt that supports it. There are no floating numbers, no boilerplate conclusions, no "the system found this" without a click-through to the why.

This is the product's superpower. NotebookLM proved the pattern: when the user can verify, they trust. We inherit and intensify it.

### 2. Progressive disclosure

The manager arrives asking *"how am I doing?"* They leave knowing *"what to do tomorrow."* The path between those two states is overview → area → clause → document → action. Never collapse the levels into one overwhelming screen. Never force the user to assemble the picture themselves.

### 3. Plain language

ISO vocabulary stays (Major, Minor, Observation, evidence, clause). Auditor jargon does not. If a sentence requires the reader to know auditing methodology, rewrite it. If a finding cannot be explained in two sentences a non-specialist would parse, the finding is wrong.

### 4. Action-orientation

A gap without a remediation is half a finding. Every Major and Minor must arrive with: *what* to do, *who* should do it, *when* (realistic), and *how much effort* (LOW / MEDIUM / HIGH). The manager should not have to translate a finding into a task. The tool does that.

## Aha moments (all four are core)

The product earns its keep when the manager experiences each of these:

1. **Source-grounded finding.** They click a Major NCR and the PDF opens at the exact page where the evidence is missing — yellow highlight on the relevant section. *"Oh, that's literally on page 12 — yes, we never wrote that."*
2. **Concrete action plan.** The remediation reads "Quality Manager — draft supplier qualification SOP — within 30 days — HIGH effort". Not philosophy. A line they can put in a sprint board.
3. **Delta vs previous run.** Re-uploading after three months, they see "47% → 64%, two Majors closed, one new Minor on §6.1.3". Visible progress, not theoretical.
4. **Grounded chat.** *"What's the biggest risk on ISO 14001 right now?"* — answer comes back with file-name:page chips they can click straight into the document.

Any single one of these is interesting. All four together is the product.

## Out of scope (for MVP)

- Multi-tenant / org-switching for advisors (Five Rise consultants come later).
- Mobile-first design (the use scene is desktop in an office).
- Real-time collaboration (one user, one analysis at a time).
- Automated remediation (the tool tells you what to fix, it does not write the SOP for you).
- Standards beyond ISO 9001:2015, ISO 14001:2015, ISO 45001:2018 (no SOC 2, no GDPR audit, no industry-specific schemes yet).
- White-label / theming for clients (Five Rise branding ships first; theming is a later concern).
