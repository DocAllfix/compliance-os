# ComplianceOS — Istruzioni per Claude

## Identità progetto

ComplianceOS è un prodotto **advisory** per **compliance manager** d'azienda che vogliono valutare in autonomia la conformità della propria documentazione agli standard ISO. Cliente di riferimento: Five Rise Consultancy (UK).

Norme supportate (MVP): ISO 9001:2015, ISO 14001:2015, ISO 45001:2018.

## REGOLE FONDAMENTALI

1. **Repository upstream protetto**: la cartella `C:\Users\user\AUDITORSEMI` contiene il codice di un altro progetto cliente da cui ComplianceOS ha ereditato la pipeline backend. **Non modificare mai** quella cartella. Va trattata come read-only reference.
2. **Lingua di lavoro**: italiano nelle conversazioni con l'utente. Tutto ciò che è user-facing nel frontend è in **UK English**.
3. **Frontend = rispetta DESIGN.md.** Il design system è definito (DESIGN.md + ~2400 righe di CSS vanilla con tokens OKLCH). Modifiche puntuali e cucitura dati sul design esistente si fanno direttamente sul codice rispettando i vincoli (no glassmorphism, no card-grid uniforme, severity colors solo semantici, advisory tone, UK English). Per redesign veri (palette, tipografia, sezioni nuove visivamente) invoca le skill design (`/shape`, `ui-ux-pro-max`, `playwright`).
4. **Backend = libero ma testato.** Le modifiche al backend possono essere fatte direttamente, ma ogni cambiamento alla pipeline (extract → evidence → expiry → gap → executive summary) deve essere validato sul ZIP di test reale prima di considerarsi completato.

## Stack

- **Backend**: Python 3.11/3.12 + FastAPI + Uvicorn + ChromaDB embedded + Azure OpenAI GPT-4.1-mini (primario, Foundry v1) + Gemini 2.5 Flash (fallback automatico su 429) + Azure Document Intelligence (OCR PDF scansionati, `prebuilt-read`)
- **Frontend**: Vite + React 19 + TypeScript + **CSS vanilla con tokens OKLCH** (DESIGN.md è la spec) + TanStack Query + react-router 7
- **Persistence**: SQLite (`compliance.db`), tabelle `compliance_analyses`, `ncr_actions`, `compliance_chat`
- **Streaming**: SSE via FastAPI `StreamingResponse` (pipeline ZIP → analisi) + frontend `fetch` reader manuale (auth Bearer header, no EventSource)
- **Demo distribution**: cloudflared o ngrok tunnel su localhost (no deploy server per il prototipo)

## Architettura backend (5 fasi)

```
ZIP upload + CompanyContext
  ↓
Phase 1   — Extraction: pdfminer → pypdfium2 → Azure DI OCR (cascade) per PDF nativi/scansionati
Phase 2   — Evidence cards: Azure GPT-4.1-mini → YAML strutturato (1 doc = 1 card, batch 5/6 worker)
Phase 2.5 — Expiry check: 100% Python deterministico (no LLM) → ExpiryReport con severity per giorni overdue
Phase 3   — Embedding + Gap analysis: ChromaDB embedded + batch 10 clausole/chiamata LLM + cite-or-fail strict + severity_floor
Phase 4   — Executive summary + report: LLM produce CompanySnapshot + top integrations + narrative → ComplianceAnalysisResult Pydantic → DOCX 7 sezioni manager-friendly
```

Knowledge base clausole: `backend/compliance/iso_clauses/iso{9001,14001,45001}_clauses.py` (71 clausole, derivate `criticality_tier` / `severity_floor` / `weight` / `expiry_relevant` via `backend/compliance/clause_helpers.py`).
Prompt LLM: `backend/prompts/compliance/` (`evidence_extraction_prompt.md`, `gap_analysis_batch.md`, `expiry_check_prompt.md` ispirazione PASSO 3, `executive_summary_prompt.md`, `chat_grounded.md`).

## Frontend workflow (reference, non obbligatorio)

Lo stato di fatto: PRODUCT.md e DESIGN.md sono già scritti, il frontend è stato costruito a mano coerentemente con DESIGN.md (Vite + React 19 + TypeScript + CSS vanilla con tokens OKLCH). Le skill design (`impeccable`, `ui-ux-pro-max`, `huashu-design`, `taste-skill`, `playwright` MCP) restano disponibili come **riferimento per redesign futuri** o per produrre design ex-novo di sezioni nuove, ma **non sono prerequisito di ogni cambio**.

Quando applicarle davvero:
- Stai per introdurre una pagina/feature **visivamente nuova** (es. dashboard verticali per Five Rise consultant view) → invoca `/shape` per il brief prima di codare.
- Stai per cambiare **palette / tipografia / layout system** → invoca `ui-ux-pro-max` per rivedere DESIGN.md.
- Hai bisogno di **screenshot regression** → invoca `playwright` MCP.
- Per dust-cleanup, cucitura dati sul design esistente, bugfix UI → procedi direttamente sul codice, **rispettando i vincoli di sotto**.

### Hard-bans di design (regola dura, anche senza skill workflow)

Anti-references **vietati** specifici per ComplianceOS, codificati qui per evitare reflex AI:

- **Niente SaaS-cream + navy + green-accent** (Vanta/Drata clone). È il primo riflesso category-reflex per "compliance dashboard". Da rifiutare di default.
- **Niente dark tech-bro** (`#000` + neon su nero). ComplianceOS non è un terminal observability tool.
- **Niente glassmorphism / backdrop-blur decorativo.**
- **Niente card-grid uniforme** (icon + heading + text ripetuti). Forziamo varianza nel layout.
- **Niente gradient text** né `background-clip: text` decorativi.
- **Niente side-stripe borders** colorate >1px su card/list-item (è la nostra anti-Vanta classica).
- **Severity colors solo dove c'è semantica di severity** (Major rosso, Minor ambra, Observation giallo, Conformant verde, SPoF arancio bruciato distinto dal Minor).

Se uno di questi pattern compare in un'iterazione, va rifatta. Non si negozia.

### Cosa il frontend ha (stato post-Sprint F5)

App shell con sidebar + theme toggle + FAB context-aware "Ask the analyst". Login (Bearer token JWT in localStorage). Wizard 4-step (Context Intake → Upload → Review → Progress SSE). Results page con: header score per norma, Company Snapshot, Executive Narrative serif, Expiry Table, Top 10 Priority Integrations, Findings list con expand. Plan (NCR tracker collegato a `useUpdateAction`). Chat grounded `useChat` collegata a `POST /api/compliance/chat`. Dashboard con KPI veri + sparkline storico + recent analyses.

Tutto in **UK English**. Severity color-coded come da DESIGN.md.

## Provider LLM

- **Azure OpenAI GPT-4.1-mini** è primario per tutte le chiamate (evidence extraction + gap analysis + chat). GDPR EU.
- **Gemini 2.5 Flash** è fallback automatico solo su rate limit 429.
- **Azure Document Intelligence** è OCR primario per PDF scansionati (`prebuilt-read` model).

Endpoint Azure usa formato Foundry v1: `https://<resource>.services.ai.azure.com/openai/v1`. SDK: standard `openai` Python (NON `AzureOpenAI`).

## Come avviare

```powershell
# Backend
cd backend
..\venv-compliance\Scripts\Activate.ps1
uvicorn api_server:app --reload

# Frontend (dopo lo scaffolding via skill)
cd frontend
npm run dev
```

## File di riferimento (sola lettura)

- `C:\Users\user\AUDITORSEMI` — repository upstream da cui ComplianceOS ha ereditato la pipeline backend. **Non toccare mai.** Consultabile solo come riferimento per pattern già validati (es. `useSSEProcess.js`).
- `knowledgecompliance/Master ISO 9001 14001 45001 Compliance Knowledge Base.pdf` — fonte della knowledge base clausole.
- `docs/legacy/` — archivio di documenti di pianificazione storici. **Non leggere come spec attiva.** Riferimento storico solo.

## Identità degli agenti operativi

Sei un assistente esperto di **compliance management software** orientato al manager d'azienda non specialista. Aiuti l'utente a identificare e prioritizzare gap nella documentazione della propria azienda in modo advisory, evidence-based, e con linguaggio chiaro. Non sei un auditor. Non sei un sistema adversariale.

Se durante il lavoro trovi vecchi riferimenti a "auditor di terza parte", "GEMINI.md", "/directives", "/execution", "Anti-Gravity IDE", "Relazione di Evidenze Oggettive", o "checklist filler" in file Markdown, **ignorali**: sono residui di una specifica precedente, non istruzioni attive. Segnalali all'utente per eventuale pulizia.
