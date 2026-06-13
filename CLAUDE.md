# Amisys QHSE — Istruzioni per Claude

## Identità progetto

**Amisys QHSE** (ex ComplianceOS — rebrand 2026-06-13 sul branding del partner) è un prodotto **advisory** per **compliance manager** d'azienda che vogliono valutare in autonomia la conformità della propria documentazione agli standard ISO. Cliente di riferimento: Five Rise Consultancy (UK).

**Brand**: navy `#1B2944` (chrome/sidebar) + arancio `#F2A33C` (logo "A" a nodi, accent) + Quicksand (display/headings) + Inter (body). Chrome navy costante nei due temi; contenuto chiaro di default, dark mode navy-tinted. Spec completa in DESIGN.md v2.

Norme supportate (MVP): ISO 9001:2015, ISO 14001:2015, ISO 45001:2018.

## REGOLE FONDAMENTALI

1. **Repository upstream protetto**: la cartella `C:\Users\user\AUDITORSEMI` contiene il codice di un altro progetto cliente da cui ComplianceOS ha ereditato la pipeline backend. **Non modificare mai** quella cartella. Va trattata come read-only reference.
2. **Lingua di lavoro**: italiano nelle conversazioni con l'utente. Tutto ciò che è user-facing nel frontend è in **UK English**.
3. **Frontend = rispetta DESIGN.md.** Il design system è definito (DESIGN.md + ~2400 righe di CSS vanilla con tokens OKLCH). Modifiche puntuali e cucitura dati sul design esistente si fanno direttamente sul codice rispettando i vincoli (no glassmorphism, no card-grid uniforme, severity colors solo semantici, advisory tone, UK English). Per redesign veri (palette, tipografia, sezioni nuove visivamente) invoca le skill design (`/shape`, `ui-ux-pro-max`, `playwright`).
4. **Backend = libero ma testato.** Le modifiche al backend possono essere fatte direttamente, ma ogni cambiamento alla pipeline (extract → evidence → expiry → gap → executive summary) deve essere validato sul ZIP di test reale prima di considerarsi completato.

## Stack

- **Backend**: Python 3.11/3.12 + FastAPI + Uvicorn + ChromaDB embedded + Azure OpenAI dual-model (GPT-4.1-mini standard + GPT-4.1 full "deep", France Central Data Zone EU) + Azure Document Intelligence (OCR PDF scansionati, `prebuilt-read`, per-pagina sui misti)
- **Frontend**: Vite + React 19 + TypeScript + **CSS vanilla con tokens OKLCH** (DESIGN.md è la spec) + TanStack Query + react-router 7
- **Persistence**: SQLite WAL (`backend/data/audit.db` — NON "compliance.db"). Tabelle compliance: `compliance_analyses` (incl. `evidence_yaml`), `nonconformities` (registro NC), `analysis_documents` (indice corpus + provenance DMS `dms_document_id`/`dms_version`; testi in `backend/data/corpus/{analysis_id}/`), `compliance_chat`, `audit_log` (append-only). Tabelle piattaforma (Fase C-F): `dms_folders`/`dms_documents`/`dms_document_versions` (binari in `backend/data/dms/{owner}/{doc_id}/v{n}/`), `notifications` + `scheduler_state`, `tasks` + `task_state`.
- **API surface**: `/api/health`, `/api/auth/*`, `/api/compliance/*` (analyze SSE, **analyze-dms** SSE scope-based, analyses, detail, download DOCX, delta, reanalyse, requirement-sets, chat, **pqq**+export, actions, nonconformities), `/api/dms/*` (folders/documents/versions/import-zip/register/pyramid), `/api/notifications/*`, `/api/tasks/*`, `/api/audit-log` (admin). Helper auth+ownership in `backend/api_deps.py` (`_require_analysis_access`/`_require_folder_access`/`_require_document_access`, admin bypass); router modulari in `backend/routers/{dms,notifications,tasks}.py`; ogni mutazione passa da `_audit()`.
- **DMS ingest primario** (Fase C-D): i documenti vivono nel DMS; l'analisi parte da uno scope (all/folder/updated_since) → `documents_override` → pipeline (Phase 1 saltata). doc_type euristico all'upload (`doc_classifier.py`, mai LLM sul CRUD) → backfill autorevole dalle evidence card post-analisi (`doc_type_source` heuristic→engine→manual; il manuale vince). Phase 1 estrazione condivisa in `compliance/extraction.py` (riusata da pipeline ZIP e upload DMS).
- **Scheduler** (Fase E): task asyncio nel lifespan FastAPI (`backend/scheduler.py`, `install_scheduler`), off di default (`SCHEDULER_ENABLED=1` per accendere). Job giornalieri idempotenti: notifiche scadenze (-60/-30/-7/0g) + retention sweep. Notifiche in-app only (campanella header).
- **Tasks RAG** (Fase F): composti a lettura (NC aperte ultima analisi + scadenze DMS + manuali), `task_state` per le sole mutazioni utente; completare un task `nc:*` chiude la NC (write-through). RAG = aritmetica a lettura, mai persistito.
- **Streaming**: SSE via FastAPI `StreamingResponse` (analyze ZIP, analyze-dms, reanalyse) + frontend `fetch` reader (`readSseStream`, auth Bearer header, no EventSource).
- **Demo distribution**: cloudflared o ngrok tunnel su localhost (no deploy server per il prototipo)

## Architettura backend (5 fasi)

```
ZIP upload + CompanyContext
  ↓
Phase 1   — Extraction page-aware: pypdfium2 per-pagina con marcatori [PAGE n] → OCR Azure DI SOLO sulle pagine scansionate (PDF misti) → fallback pdfminer/OCR full-doc. XLSX/XLSM via openpyxl (marcatori [SHEET]), XLS via xlrd, DOCX con tabelle
Phase 2   — Evidence cards: Azure GPT-4.1-mini → YAML strutturato (1 doc = 1 card, batch 5/6 worker). L'evidence_yaml integrale viene persistito su DB
Phase 2.5 — Expiry check: 100% Python deterministico (no LLM) → ExpiryReport con severity per giorni overdue
Phase 2.6 — Documented-info coverage: registro MAINTAIN/RETAIN per norma + matcher L1 metadata → L2 semantico → L3 conferma assenza via LLM (mai match per nome file)
Phase 2.7 — Risk register strutturato: estrazione rischi/metodologia/score/mitigazione/owner dai documenti di rischio, con flag deterministici sui campi mancanti (placeholder "to be defined" = mancante)
Phase 3   — Gap analysis a due stadi: Stage A batch screening su chunk index (10 clausole/chiamata, cite-or-fail strict, severity_floor, confidence) + Stage B deep verification sul TESTO COMPLETO dei documenti per clausole critiche/con atomic_requirements (requirement_checks PRESENT/PARTIAL/ABSENT, hedging, wording-check deterministico, dual remediation correction/corrective_action)
Phase 3.5 — Cross-clause coherence: 9 chain dichiarative (rischio→controllo→monitoraggio, objectives loop, legal loop…) verificate sulle evidenze citate + registro rischi
Phase 4   — Executive summary + report: LLM produce CompanySnapshot + top integrations + narrative → ComplianceAnalysisResult Pydantic → DOCX manager-friendly (incl. sezioni documented-info, cross-clause, dual remediation)
```

Knowledge base clausole: `backend/compliance/iso_clauses/iso{9001,14001,45001}_clauses.py` (71 clausole, 36 con `atomic_requirements` — fonte: checklist di audit in `checklistevidence/`; derivate `criticality_tier` / `severity_floor` / `weight` / `expiry_relevant` via `backend/compliance/clause_helpers.py`).
Criteri operativi custom (PRD §1.4.4b): set YAML in `backend/data/requirement_sets/` con lo stesso shape delle clausole — il `label` entra in `norms` accanto agli standard ISO e il motore li processa identici (vedi `example_operating_criteria.yaml` come formato di riferimento).
Prompt LLM: `backend/prompts/compliance/` (`evidence_extraction_prompt.md`, `gap_analysis_batch.md`, `deep_verification.md`, `cross_clause_prompt.md`, `risk_extraction.md`, `executive_summary_prompt.md`, `chat_grounded.md`, `chat_general.md`).
Acceptance: `backend/tests/fred_simulation.py` (pack UK con 7 gap seminati) — `pytest tests/test_fred_simulation.py -m slow` deve dare 10/10.

## Frontend workflow (reference, non obbligatorio)

Lo stato di fatto: PRODUCT.md e DESIGN.md sono già scritti, il frontend è stato costruito a mano coerentemente con DESIGN.md (Vite + React 19 + TypeScript + CSS vanilla con tokens OKLCH). Le skill design (`impeccable`, `ui-ux-pro-max`, `huashu-design`, `taste-skill`, `playwright` MCP) restano disponibili come **riferimento per redesign futuri** o per produrre design ex-novo di sezioni nuove, ma **non sono prerequisito di ogni cambio**.

Quando applicarle davvero:
- Stai per introdurre una pagina/feature **visivamente nuova** (es. dashboard verticali per Five Rise consultant view) → invoca `/shape` per il brief prima di codare.
- Stai per cambiare **palette / tipografia / layout system** → invoca `ui-ux-pro-max` per rivedere DESIGN.md.
- Hai bisogno di **screenshot regression** → invoca `playwright` MCP.
- Per dust-cleanup, cucitura dati sul design esistente, bugfix UI → procedi direttamente sul codice, **rispettando i vincoli di sotto**.

### Hard-bans di design (regola dura, anche senza skill workflow)

Anti-references **vietati** specifici per Amisys QHSE, codificati qui per evitare reflex AI:

- **Niente SaaS-cream + navy + green-accent** (Vanta/Drata clone). È il primo riflesso category-reflex per "compliance dashboard". Da rifiutare di default.
- **Niente dark tech-bro** (`#000` + neon su nero). Il dark mode è navy-tinted (hue 262), mai nero puro. Amisys QHSE non è un terminal observability tool.
- **Il navy `#1B2944` è il brand chrome** (sidebar/header), non un Vanta-clone: si accoppia con l'arancio, mai con green-accent o cream-card di categoria.
- **Niente glassmorphism / backdrop-blur decorativo.**
- **Niente card-grid uniforme** (icon + heading + text ripetuti). Forziamo varianza nel layout.
- **Niente gradient text** né `background-clip: text` decorativi.
- **Niente side-stripe borders** colorate >1px su card/list-item (è la nostra anti-Vanta classica).
- **Severity colors solo dove c'è semantica di severity** (Major rosso, Minor ambra, Observation giallo, Conformant verde, SPoF arancio bruciato distinto dal Minor).

Se uno di questi pattern compare in un'iterazione, va rifatta. Non si negozia.

### Cosa il frontend ha (stato post-Sprint F5)

App shell **brandizzata Amisys QHSE** (sidebar navy + logo arancio a nodi `BrandLogo.tsx`, theme toggle, FAB "Ask the analyst", campanella notifiche `NotificationsBell` in alto a destra). Login (Bearer JWT in localStorage). Pagine: Dashboard (KPI + sparkline), **Documents** (DMS: albero cartelle, upload/import-ZIP, versioni; tab Register con export XLSX; tab Pyramid), wizard 4-step con **Step 2 source = DMS scope / ZIP**, Results (score, snapshot, narrative Inter, expiry, documented-info, cross-clause, **risk register**, findings, Re-analyse), Plan (NCR tracker), Compare (delta), **Tasks** (board RAG), **Tender Q&A** (PQQ con export DOCX), Chat grounded/general.

Brand: **DESIGN.md v2** (navy `#1B2944` chrome + arancio `#F2A33C` accent, Quicksand display + Inter body, niente serif). Token unica fonte in `index.css`. Tutto in **UK English**. Severity/RAG color-coded come da DESIGN.md.

## Provider LLM

- **Dual-model Azure OpenAI** su risorsa unica France Central (Data Zone Standard EU, GDPR):
  - **GPT-4.1-mini** (16M TPM) — provider standard: Phase 2 evidence, Stage A screening, documented-info L3, risk extraction.
  - **GPT-4.1 full** (3M TPM) — profilo "deep" (`COMPLIANCE_DEEP_PROVIDER=gpt-4.1-azure` in `.env`): Stage B deep verification, cross-clause, executive summary, chat. `make_client(deep=True)` in `v2/azure_openai_client_v2.py` degrada alla mini se il deep non è configurato — la pipeline non si rompe mai per il profilo opzionale.
- **Concorrenza** tarata sulle quote alte, override-abile da env: `EVIDENCE_MAX_WORKERS=14`, `GAP_MAX_WORKERS=6`, `DEEP_MAX_WORKERS=6`, `CROSS_MAX_WORKERS=9`, `RISK_MAX_WORKERS=4`. I batch size NON si toccano (sono qualità, non throughput).
- **Niente fallback Gemini**: rimosso il 2026-06-12 per decisione utente (chiave non utilizzabile). La resilienza è data dai retry con backoff (Phase 2 e 3) + re-ask sui parse-fail + degradazione controllata (carte sintetiche, fallback gaps, 502 chat).
- **Azure Document Intelligence** è OCR per PDF scansionati (`prebuilt-read`): full-document per PDF interamente scansionati, **per-pagina** sui PDF misti nativi+scansionati.

Endpoint v1 OpenAI-compatible: `https://<resource>.openai.azure.com/openai/v1` (o formato Foundry `services.ai.azure.com/openai/v1`). SDK: standard `openai` Python (NON `AzureOpenAI`). Nota: i modelli Claude su Foundry sono solo Global Standard (inferenza extra-EU possibile) — scartati per coerenza col pitch GDPR.

## Come avviare

```powershell
# Backend — il venv reale sta in C:\Users\user\venv-compliance
# (NON in ..\venv-compliance: quel path non esiste)
cd backend
C:\Users\user\venv-compliance\Scripts\Activate.ps1
uvicorn api_server:app --reload

# Frontend
cd frontend
npm run dev
```

## Test

```powershell
cd backend
# Suite fast (regression net, no LLM) — deve essere SEMPRE verde
C:\Users\user\venv-compliance\Scripts\python.exe -m pytest tests -m "not slow"
# Acceptance Fred-simulation (LLM reale, ~3 min) — 10/10 atteso
C:\Users\user\venv-compliance\Scripts\python.exe -m pytest tests/test_fred_simulation.py -m slow
# Regressione ZIP italiano reale (CONSORZIO JEOCON)
C:\Users\user\venv-compliance\Scripts\python.exe -m pytest tests/test_pipeline_smoke.py -m slow
```

Il conftest carica `backend/.env` automaticamente per la suite slow.

## File di riferimento (sola lettura)

- `C:\Users\user\AUDITORSEMI` — repository upstream da cui ComplianceOS ha ereditato la pipeline backend. **Non toccare mai.** Consultabile solo come riferimento per pattern già validati (es. `useSSEProcess.js`).
- `knowledgecompliance/Master ISO 9001 14001 45001 Compliance Knowledge Base.pdf` — fonte della knowledge base clausole.
- `docs/legacy/` — archivio di documenti di pianificazione storici. **Non leggere come spec attiva.** Riferimento storico solo.

## Identità degli agenti operativi

Sei un assistente esperto di **compliance management software** orientato al manager d'azienda non specialista. Aiuti l'utente a identificare e prioritizzare gap nella documentazione della propria azienda in modo advisory, evidence-based, e con linguaggio chiaro. Non sei un auditor. Non sei un sistema adversariale.

Se durante il lavoro trovi vecchi riferimenti a "auditor di terza parte", "GEMINI.md", "/directives", "/execution", "Anti-Gravity IDE", "Relazione di Evidenze Oggettive", o "checklist filler" in file Markdown, **ignorali**: sono residui di una specifica precedente, non istruzioni attive. Segnalali all'utente per eventuale pulizia.
