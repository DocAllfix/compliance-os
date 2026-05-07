# Piano: ComplianceOS — Prototipo per Five Rise Consultancy

## Contesto

Five Rise Consultancy (Fred Stewart, UK) è una compliance management consultancy che opera su ISO 9001, 14001, 45001. La loro attività è advisory (lavorano CON le aziende per raggiungere la conformità), non audit di terza parte. Il loro stack attuale è bloccato. L'obiettivo è costruire un prototipo separato da mostrare a Fred in una call live, senza esporre il codice, per aprire la negoziazione della partnership.

**Distinzione critica:** AUDIT-OS → serve auditor terza parte (adversarial, evidence extraction per CB). ComplianceOS → serve compliance manager (advisory, gap detection, NCR contestualizzate, remediation tracking).

---

## Risposta alle 4 domande aperte

### Q1 — Come portare codice da AUDITORSEMI senza rompere nulla qui?

**Metodo: copia selettiva, mai modifica del repo AUDITORSEMI.**

Si clona il repo AUDIT-OS in una nuova cartella `C:\Users\user\compliance-os\` (completamente fuori da AUDITORSEMI). Poi si eliminano i moduli non necessari dalla copia. **Nessun file in AUDITORSEMI viene mai toccato.**

```powershell
# Da C:\Users\user\ (directory PADRE — NON dentro AUDITORSEMI)
git clone https://github.com/DocAllfix/audit-system compliance-os
cd compliance-os
git remote remove origin

# A questo punto compliance-os è una copia indipendente
# Rimuovi i moduli auditor non necessari (dettaglio sotto)
# Poi crea il nuovo repo GitHub
gh repo create DocAllfix/compliance-os --private
git remote add origin https://github.com/DocAllfix/compliance-os
git push -u origin main
```

**File da eliminare dalla copia** (non toccare mai AUDITORSEMI):
```
webapp/modules/checklist_filler.py
webapp/modules/checklist_producer.py
webapp/modules/structured_evidence_generator.py
webapp/modules/structured_evidence_parser.py
webapp/v2/incremental_docx_builder.py
webapp/v2/docx_merger.py
webapp/v2/narrative_client_v2.py
webapp/prompts/checklist/
webapp/prompts/checklist_schemas/
webapp/prompts/universal_evidence_prompt*.md   ← sostituiti da nuovo prompt
webapp/prompts/narrative_*.md
webapp/templates/                              ← template Word per auditor
frontend/src/pages/GeneraReport.jsx
frontend/src/pages/ProduciChecklist.jsx
frontend/src/pages/CompilaChecklist.jsx
frontend/src/components/checklist/
frontend/src/components/layout/WorkflowLayout.jsx
```

**Rinomina per chiarezza:** `webapp/` → `backend/`

---

### Q2 — Serve un CLAUDE.md per la nuova repo?

**Sì, va creato un CLAUDE.md dedicato** in `compliance-os/CLAUDE.md`. Non si porta quello di AUDITORSEMI (è scritto per il sistema auditor). Il nuovo CLAUDE.md documenta:
- Identità del progetto (ComplianceOS, advisory, Five Rise partnership)
- Architettura (pipeline 3 fasi, ChromaDB, Azure-first)
- Regola fondamentale: MAI modificare il repo AUDITORSEMI
- Norme supportate (solo ISO 9001/14001/45001 per MVP)
- Stack tecnologico e come avviarlo
- Struttura directory
- Dove si trova la knowledge base ISO

Il testo del CLAUDE.md è incluso come task della Settimana 1.

---

### Q3 — Come raccogliere la knowledge base delle non conformità?

Il documento `callenglishpartnership/Master ISO 9001 14001 45001 Compliance Knowledge Base & Audit Blueprint.pdf` contiene già la knowledge base completa. È stato analizzato e fornisce:

**Per ISO 9001:2015 — Critical clauses (Major se assenti):**
- 7.5 Document Control — procedure assenti, versioning mancante
- 8.4 Supplier Management — nessun processo qualifica fornitori
- 9.2 Internal Audits — programma assente o audit superficiali
- 9.3 Management Review — verbali assenti, input/output non documentati
- 10.2 CAPA — azioni correttive non definite o senza verifica efficacia

**Per ISO 14001:2015 — Critical clauses:**
- 6.1.2 Aspetti ambientali — matrice assente o non aggiornata
- 6.1.3 Compliance obligations — registro legislativo incompleto
- 8.1 Waste & Traceability — FIR incompleti, codici CER errati
- 8.2 Emergency preparedness — piani mancanti o non testati

**Per ISO 45001:2018 — Critical clauses:**
- 6.1.2 Hazard Identification & Risk Assessment — DVR obsoleto o incompleto
- 5.4/7.3 Worker Involvement — nessun processo di consultazione lavoratori
- 8.1.4 Contractor Management — nessun criterio O&HS per appaltatori
- 9.1 KPI & Monitoring — indicatori non definiti o non monitorati
- 10.2 Incident & CAPA — near miss non registrati, CAPA generiche

**Single Points of Failure (SPoF) codificati:**
- ISO 9001: fornitori critici non qualificati, audit interni inefficaci, riesame direzione assente, CAPA inefficaci
- ISO 14001: aspetti ambientali non identificati, assenza valutazione conformità legale, tracciabilità rifiuti assente
- ISO 45001: HIRA inadeguato, near miss non gestiti, contractor non controllati

Questa knowledge base viene codificata nei file `backend/compliance/iso_clauses/iso9001_clauses.py` (e 14001, 45001) come dizionario strutturato: clausola → descrizione → tipo_requisito → SPoF → NC_tipiche → weight_severity_per_settore.

---

### Q4 — Output YAML (come ora) o altro formato? Come adattare il prompt v3?

**Risposta diretta:** si mantiene YAML come formato intermedio (Fase 1), ma il prompt v3 va riscritto — non riusato così com'è.

**Analisi del prompt v3:**

Cosa c'è di buono e si mantiene:
- Struttura YAML (parser-safe, già validato in produzione)
- Le 18 categorie tematiche (allineate alle aree ISO)
- Regola 1-doc-1-scheda (garantisce tracciabilità)
- Regole YAML parser-safe (R0.1-R0.6) — identiche
- Cluster liberi per tipo documento (DVR, analisi energetica, ecc.)
- Blocco META (azienda + indice)

Cosa va cambiato radicalmente:
- **System identity:** da "sistema per audit di certificazione di terza parte" a "compliance analysis assistant helping managers identify gaps" — linguaggio advisory, non adversariale
- **Lingua:** da italiano a UK English (Five Rise è UK)
- **2 nuovi campi per ogni scheda:**
  - `iso_clause_primary: "ISO 45001 §6.1.2"` — clausola ISO rilevante per quella scheda
  - `gap_signal: true/false` — flag se il documento segnala una lacuna evidente (es. DVR senza sezione cogeneratori, attestati scaduti da oltre 12 mesi)
- **Company context:** il system prompt include `{company_context}` (settore, dimensione, certificazione status, n. siti) per orientare la severity
- **Rimuovere:** riferimenti a "auditor lead", "commessa", "checklist a valle", linguaggio adversariale

**Il nuovo prompt Fase 1** si chiama `backend/prompts/compliance/evidence_extraction_prompt.md`. Non si chiama più "v3" per evitare confusione con AUDIT-OS.

**Il nuovo prompt Fase 2** (gap analysis) è un prompt completamente nuovo, separato, che riceve le evidence cards da Fase 1 + context intake + clausole ISO e produce JSON conformance scoring. Non è derivato da v3.

---

## Decisioni architetturali chiave

### Provider LLM: Azure-first, Gemini come fallback

Azure OpenAI GPT-4.1-mini è primario per tutte le chiamate LLM e OCR (GDPR EU, ~63% più economico di Gemini). Azure Document Intelligence per OCR su PDF scansionati. Gemini rimane come fallback automatico su rate limit 429 (logica già in AUDIT-OS, si riusa identica).

### Architettura NCR detection: Approccio Ibrido

Tre approcci valutati:

| | A: Prompt-only | B: RAG puro | C: Ibrido ✅ |
|---|---|---|---|
| Accuratezza Major NCR | 60-70% ❌ | 92-97% | 85-92% |
| False negatives Major | 20-30% | 2-3% | 5-8% |
| Infrastruttura | Zero | Azure AI Search €100+/mese | ChromaDB locale (zero) |
| Token/audit | 16K | 258K | 110K |
| Settimane implementazione | 1-2 | 4-5 | 2-3 ✅ |

**Approccio C scelto:**
- Fase 1: estrai evidence cards YAML (nuovo prompt) → ogni card include `iso_clause_primary`, `gap_signal`, `{file_name, pages, evidence_id}`
- Fase 2: embedda le evidence cards in ChromaDB locale (non i doc grezzi)
- Fase 3: per ogni clausola ISO → query ChromaDB → LLM vede solo le card rilevanti → score + severity + finding + remediation

**Perché non A:** False negatives del 20-30% su Major NCR sono inaccettabili.
**Perché non B:** 16x più caro in token, Azure AI Search €100+/mese, 4-5 settimane extra. Overkill per MVP.
**Upgrade path:** se accuracy C insufficiente, pivot a B aggiungendo Azure AI Search in 3-4 giorni.

### UX: NotebookLM + in-app document viewer + context intake

Ricerca su Kira, Luminance, Harvey, NotebookLM, Hebbia, Vanta, Drata ha validato questi pattern:
1. Source-grounded findings — ogni NCR linka al passaggio esatto del documento sorgente
2. Two-panel layout — lista NCR a sinistra, PDF viewer con highlight a destra
3. Information funneling — overview score → gap matrix → NCR → documento
4. Event-driven progress — status Open/In-Progress/Closed
5. Guided remediation — Who/What/When per ogni finding

**Context intake (Step 0 del wizard):** 6 domande in 60 secondi prima del caricamento. Tecnicamente necessario: la severity delle NCR varia in base a settore e dimensione (es. assenza procedura qualifica fornitori = Observation per studio di consulenza, Major per impresa edile con 50 subappaltatori). I dati del context intake vengono passati al prompt Fase 1 e Fase 2 come `{company_context}`.

### Deploy: solo locale per ora

Nessun deploy server per il prototipo. Demo via `cloudflare tunnel` o `ngrok` per esporre localhost a Fred senza deploy.

---

## Pipeline tecnica

```
ZIP upload + company_context (da Step 0)
  ↓
FASE 1 — ESTRAZIONE (Azure-first)
  zip_extractor.py → file_triage.py → text_extractor.py
  Azure Document Intelligence per OCR (primario)
  Gemini Vision per OCR (fallback)
  → Nuovo prompt evidence_extraction_prompt.md:
    - UK English, system identity advisory
    - Struttura YAML invariata (18 categorie, 1-doc-1-scheda)
    - Aggiunge: iso_clause_primary, gap_signal
    - Riceve: {company_context} nel system prompt
    Ogni card include: {file_name, pages, timestamp, evidence_id,
                        iso_clause_primary, gap_signal}
  SSE: pct 5→35, "Extracting and reading documents..."

FASE 2 — EMBEDDING
  compliance/embedder.py
  ChromaDB locale embedded (zero infrastruttura)
  ogni evidence card → vettore semantico
  SSE: pct 35→45, "Indexing evidence..."

FASE 3 — GAP ANALYSIS
  compliance/gap_analyzer.py
  Per ogni norma selezionata:
    Per ogni clausola ISO (da iso_clauses/):
      → query ChromaDB top-3 card rilevanti
      → Azure GPT-4.1-mini + gap_analysis_prompt + company_context
      → score 0-100, severity (contestualizzata), finding, traceability_chain, remediation
  SSE: pct 45→80, "Analysing {NORM} conformance [{sector}, {employees}]..."

FASE 4 — OUTPUT
  compliance/report_builder.py → DOCX manager-friendly
  db_manager_ext.py → salva risultato + context + chat setup
  SSE: pct 80→100, "Preparing your compliance report..."
  → {"done": true, "analysis_id": "...", "result": {...}}
```

---

## Schema output NCR (Pydantic)

```python
# backend/compliance/schemas.py

class CompanyContext(BaseModel):
    company_name: str
    sector: str          # Construction / Manufacturing / Services / Logistics / Healthcare / Energy / Other
    employee_range: str  # "1-10" / "11-50" / "51-250" / "250+"
    certified: str       # "yes" / "no" / "in_progress"
    sites_count: str     # "1" / "2-5" / "5+"
    norms: List[str]     # ["ISO 9001", "ISO 14001", "ISO 45001"]

class TraceabilityLink(BaseModel):
    evidence_id: str
    file_name: str
    pages: List[int]
    excerpt: str
    relevance_score: float

class RemediationPlan(BaseModel):
    what: str
    who: str             # es. "Quality Manager", "HSE Officer", "RSPP"
    when: str            # es. "30 days", "3 months"
    effort: str          # LOW / MEDIUM / HIGH

class ClauseGap(BaseModel):
    clause_id: str       # es. "9001_8_4"
    clause_title: str    # es. "8.4 Control of externally provided processes"
    score: int           # 0-100
    severity: str        # MAJOR / MINOR / OBSERVATION / CONFORMANT
    is_spof: bool        # true se è uno dei Single Points of Failure
    finding: str         # max 150 words, plain language UK English
    sources: List[TraceabilityLink]
    remediation: RemediationPlan

class NormGapReport(BaseModel):
    norm: str            # "ISO 9001:2015"
    overall_score: int
    clauses: List[ClauseGap]
    major_count: int
    minor_count: int
    observation_count: int
    conformant_count: int
    spof_count: int      # quanti Major sono SPoF

class ComplianceAnalysisResult(BaseModel):
    analysis_id: str
    company: str
    context: CompanyContext
    analysis_date: str
    norms: List[NormGapReport]
    documents_analyzed: int
    top_gaps: List[ClauseGap]  # top 5 Major/SPoF cross-norma
```

---

## Knowledge base clausole ISO

La knowledge base è estratta dal documento `callenglishpartnership/Master ISO 9001 14001 45001 Compliance Knowledge Base & Audit Blueprint.pdf` e codificata in Python.

Struttura di ogni clausola nel file:
```python
# backend/compliance/iso_clauses/iso9001_clauses.py

ISO9001_CLAUSES = {
    "9001_8_4": {
        "title": "8.4 Control of externally provided processes, products and services",
        "area": "Operations",
        "is_spof": True,
        "critical_sectors": ["Construction", "Manufacturing", "Logistics"],
        "major_threshold": {
            "default": "Process completely absent",
            "high_risk_sectors": "Any gap in supplier qualification for critical suppliers"
        },
        "typical_ncs": [
            "No formal supplier qualification process",
            "Approved supplier list absent or not maintained",
            "No periodic supplier evaluation",
            "No corrective action mechanism for underperforming suppliers"
        ],
        "evidence_keywords": [
            "supplier", "vendor", "subcontractor", "qualification",
            "approved supplier list", "evaluation", "purchase order"
        ],
        "remediation_template": {
            "what": "Establish formal supplier qualification procedure with approved vendor list and periodic evaluation criteria",
            "who": "Quality Manager / Procurement Manager",
            "when_major": "30 days",
            "when_minor": "90 days",
            "effort": "HIGH"
        }
    },
    # ... tutte le altre clausole
}
```

---

## DB: tabelle

```sql
CREATE TABLE compliance_analyses (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    company TEXT,
    norms TEXT,                    -- JSON array
    -- Context Intake
    sector TEXT,
    employee_range TEXT,
    certified TEXT,
    sites_count TEXT,
    company_context_json TEXT,     -- JSON completo CompanyContext
    --
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    overall_score INTEGER,
    major_count INTEGER,
    minor_count INTEGER,
    observation_count INTEGER,
    conformant_count INTEGER,
    spof_count INTEGER,
    documents_analyzed INTEGER,
    result_json TEXT,              -- JSON completo ComplianceAnalysisResult
    docx_filename TEXT,
    status TEXT DEFAULT 'completed'
);

CREATE TABLE ncr_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT REFERENCES compliance_analyses(id),
    clause_id TEXT,
    severity TEXT,
    is_spof INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',    -- open / in_progress / closed
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE compliance_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT REFERENCES compliance_analyses(id),
    role TEXT,                     -- user / assistant
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API endpoints

```
POST /api/compliance/analyze               → SSE pipeline completa (riceve context + ZIP)
GET  /api/compliance/analyses              → storico
GET  /api/compliance/analyses/{id}         → risultato
GET  /api/compliance/analyses/{id}/download → DOCX
PATCH /api/compliance/analyses/{id}/actions/{clause_id} → aggiorna status NCR
GET  /api/compliance/analyses/{id}/compare/{prev_id}    → delta view
POST /api/compliance/analyses/{id}/chat    → chat grounded
GET  /api/health, /api/auth/*              → riusati identici
```

---

## UX: wizard 5 step

```
Step 0 — Company Context
  6 domande rapide (~60 sec), tutto dropdown + testo libero:
  1. Company name (text)
  2. Industry sector (Construction / Manufacturing / Services /
     Logistics / Healthcare / Energy / Other)
  3. Number of employees (1-10 / 11-50 / 51-250 / 250+)
  4. Standards to assess (checkbox: ISO 9001 / 14001 / 45001)
  5. Currently certified? (Yes / No / In progress)
  6. Number of operating sites (1 / 2-5 / 5+)
  → dati salvati in complianceStore + inviati alla pipeline

Step 1 — Upload Documents
  Dropzone ZIP + file count preview per tipo

Step 2 — Review & Confirm
  Riepilogo: company context + norme + file count
  Stima tempo elaborazione
  Bottone "Start Analysis"

Step 3 — Analysis in Progress
  Progress bar UK English, messaggi manager-friendly:
  "Reading documents..." → "Indexing evidence..." →
  "Analysing ISO 9001 conformance [Manufacturing, 51-250 employees]..."
  → "Preparing your compliance report..."
  Il context è visibile brevemente (rassicura che è stato usato)
  Nessun termine tecnico

Step 4 — Results
  ┌─────────────────────────────────────────────────────────┐
  │  OVERALL COMPLIANCE — ACME Ltd — Manufacturing          │
  │  ISO 9001: 67%  ISO 14001: 54%  ISO 45001: 71%          │
  │  ████░░░░  4 Major (2 SPoF)  6 Minor  3 Obs             │
  ├──────────────────────┬──────────────────────────────────┤
  │  GAP MATRIX          │  DOCUMENT VIEWER                 │
  │  ⚠ [Major] §8.4 ..   │  Supplier_Procedure_Rev1.pdf     │
  │  ⚠ [Major] §6.1.2 .  │  [pagina 3 evidenziata in giallo]│
  │  [Minor] §7.2 ..     │                                  │
  │  [Obs]   §9.2.1 ..   │  "Section 4.2 does not specify.."│
  │  ▸ expand finding    │                                  │
  ├──────────────────────┴──────────────────────────────────┤
  │  CHAT                                                   │
  │  "What are the most critical gaps for ISO 45001?"       │
  │  > The two Major SPoF findings are... [source: DVR.pdf] │
  ├─────────────────────────────────────────────────────────┤
  │  [Download DOCX]  [Save & Track]                        │
  └─────────────────────────────────────────────────────────┘
```

---

## Struttura directory compliance-os

```
C:\Users\user\compliance-os\            ← FUORI da AUDITORSEMI, mai toccare AUDITORSEMI
├── CLAUDE.md                           ← NUOVO (vedi sotto)
├── backend/                            ← rinominato da webapp/
│   ├── api_server.py                   ← riscritto per compliance
│   ├── config.py
│   ├── modules/
│   │   ├── auth_manager.py             ← identico
│   │   ├── db_manager.py               ← esteso con tabelle compliance
│   │   ├── genai_factory.py            ← identico
│   │   └── gemini_throttle.py          ← identico (per fallback)
│   ├── v2/                             ← infrastruttura riusata identica
│   │   ├── zip_extractor.py
│   │   ├── file_triage.py
│   │   ├── text_extractor.py
│   │   ├── gemini_client_v2.py         ← solo fallback
│   │   ├── azure_openai_client_v2.py   ← primario
│   │   ├── azure_document_intelligence.py ← OCR primario
│   │   ├── llm_dispatch.py
│   │   ├── sse_emitter.py
│   │   ├── progress_store.py
│   │   ├── token_meter.py
│   │   ├── watchdog.py
│   │   ├── yaml_parser.py
│   │   └── pipeline.py                 ← riscritto (compliance version)
│   ├── compliance/                     ← TUTTO NUOVO
│   │   ├── __init__.py
│   │   ├── schemas.py                  ← Pydantic models
│   │   ├── context_intake.py           ← CompanyContext + build_context_prompt_block()
│   │   ├── embedder.py                 ← ChromaDB integration
│   │   ├── gap_analyzer.py             ← NCR detection engine
│   │   ├── chat_engine.py              ← chat grounded su evidence cards
│   │   ├── report_builder.py           ← DOCX manager-friendly
│   │   ├── delta_engine.py             ← confronto tra analisi
│   │   └── iso_clauses/
│   │       ├── iso9001_clauses.py      ← clausole + NC tipiche + SPoF
│   │       ├── iso14001_clauses.py
│   │       └── iso45001_clauses.py
│   ├── prompts/
│   │   └── compliance/
│   │       ├── evidence_extraction_prompt.md ← NUOVO (non è più v3 di AUDIT-OS)
│   │       ├── gap_analysis_base.md          ← NUOVO
│   │       ├── iso9001_gap.md
│   │       ├── iso14001_gap.md
│   │       ├── iso45001_gap.md
│   │       └── chat_grounded.md
│   └── requirements.txt               ← + chromadb
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Login.jsx              ← identico
│       │   ├── ComplianceDashboard.jsx ← nuovo
│       │   ├── NewAnalysis.jsx        ← wizard 5 step
│       │   ├── AnalysisDetail.jsx     ← nuovo
│       │   └── AdminPanel.jsx         ← adattato
│       ├── components/
│       │   ├── ui/                    ← shadcn identici
│       │   ├── shared/                ← FileDropzone, StatCard identici
│       │   └── compliance/
│       │       ├── ContextIntakeForm.jsx    ← Step 0
│       │       ├── GapMatrix.jsx
│       │       ├── ComplianceScoreCard.jsx
│       │       ├── DocumentViewer.jsx       ← react-pdf + highlight
│       │       ├── ChatPanel.jsx
│       │       ├── RadarChart.jsx
│       │       ├── NCRProgressTracker.jsx
│       │       └── DeltaView.jsx
│       ├── hooks/
│       │   └── useSSEProcess.js       ← identico
│       └── store/
│           └── complianceStore.js     ← nuovo
└── .env.example
```

---

## CLAUDE.md per compliance-os (testo da creare)

Il file `compliance-os/CLAUDE.md` deve contenere:

```markdown
# ComplianceOS — Istruzioni per Claude

## Identità progetto
ComplianceOS è un prodotto separato da AUDIT-OS, pensato per compliance manager
(non auditor di terza parte). Serve Five Rise Consultancy (UK) per aiutare i
loro clienti a raggiungere e mantenere la conformità ISO 9001/14001/45001.

## REGOLA FONDAMENTALE
MAI modificare il repository AUDITORSEMI (c:\Users\user\AUDITORSEMI).
ComplianceOS è una copia indipendente. Qualsiasi modifica va fatta solo qui.

## Lingua
Il frontend e tutti i messaggi utente sono in UK English.
Il backend Python può avere commenti in italiano per continuità con AUDIT-OS.

## Provider LLM
- Azure OpenAI GPT-4.1-mini: provider PRIMARIO per tutto
- Gemini 2.5 Flash: fallback automatico su rate limit 429
- Azure Document Intelligence: OCR primario per PDF scansionati

## Architettura pipeline
3 fasi: (1) Evidence Extraction → YAML, (2) ChromaDB embedding, (3) Gap Analysis
Il prompt di Fase 1 è backend/prompts/compliance/evidence_extraction_prompt.md
NON usare il prompt v3 di AUDIT-OS — è per auditor, non per compliance.

## Norme supportate (MVP)
ISO 9001:2015, ISO 14001:2015, ISO 45001:2018

## Knowledge base clausole
backend/compliance/iso_clauses/ — estratta da:
callenglishpartnership/Master ISO 9001 14001 45001 Compliance Knowledge Base.pdf

## Come avviare
Backend: cd backend && ..\venv-compliance\Scripts\activate && uvicorn api_server:app --reload
Frontend: cd frontend && npm run dev
```

---

## DOCX output (manager-friendly)

1. **Cover** — Company, sector, norme, data, "Prepared by [brand]"
2. **Executive Summary** — Overall score %, Major/Minor/Obs/Conformant count, SPoF count, top 3 rischi
3. **Compliance by Area** — tabella: area ISO → score → severity → trend
4. **Single Points of Failure** — sezione dedicata ai SPoF (massima priorità)
5. **Critical Findings** — per ogni Major: clausola, finding, evidence file+page, azione
6. **Action Plan Template** — Priority | Clause | Action | Responsible | Deadline | Effort
7. **Full Clause Matrix** — tutte clausole: score, severity, key finding
8. **Appendix: Document Index** — file analizzati con categoria e status

Colori: Major=rosso, Minor=arancione, Observation=giallo, Conformant=verde

---

## Fasi implementative (5 settimane)

### Settimana 1 — Scaffold, repo, CLAUDE.md

1. Clone AUDIT-OS in `C:\Users\user\compliance-os\` fuori da AUDITORSEMI
2. Rimuovi file dead code auditor (lista sopra)
3. Rinomina `webapp/` → `backend/`
4. Crea `compliance-os/CLAUDE.md` (testo sopra)
5. Crea repo GitHub privato `DocAllfix/compliance-os`, push initial commit
6. Crea venv `C:\Users\user\venv-compliance\`, installa requirements + chromadb
7. Estendi `backend/modules/db_manager.py` con le 3 nuove tabelle
8. Crea `backend/compliance/schemas.py` (tutti i modelli Pydantic incluso CompanyContext)
9. Crea stub `backend/compliance/gap_analyzer.py` che ritorna mock data
10. Nuovo `backend/api_server.py` con auth + health + stub `/api/compliance/analyze`
11. Riscrivi `frontend/src/App.jsx` con route compliance (UK English)
12. Riscrivi `Sidebar.jsx` con navigazione compliance
13. Crea `complianceStore.js`
14. Crea `NewAnalysis.jsx`: Step 0 `ContextIntakeForm.jsx` + Step 1 upload
15. Crea `ComplianceDashboard.jsx` con mock data

**Milestone:** Login, Step 0 context intake funzionante, Step 1 upload, dashboard mock.

---

### Settimana 2 — Pipeline reale + ISO 9001

1. Scrivi `backend/prompts/compliance/evidence_extraction_prompt.md` (derivato da v3, riscritto UK English, advisory, + iso_clause_primary + gap_signal + company_context)
2. Crea `backend/compliance/context_intake.py` con modello CompanyContext + `build_context_prompt_block()`
3. Codifica `backend/compliance/iso_clauses/iso9001_clauses.py` (dalla knowledge base PDF, tutte le clausole con NC tipiche + SPoF + sector weights)
4. Crea `backend/compliance/embedder.py` (ChromaDB, ~80 righe)
5. Scrivi `backend/prompts/compliance/gap_analysis_base.md` + `iso9001_gap.md`
6. Implementa `backend/compliance/gap_analyzer.py` reale per ISO 9001 (Azure GPT-4.1-mini)
7. Riscrivi `backend/v2/pipeline.py` compliance version (Fase 1-2-3-4)
8. Collega endpoint `/api/compliance/analyze` SSE alla pipeline reale
9. Step 3 wizard collegato all'SSE (riusa `useSSEProcess.js` identico)
10. Step 4 layout GapMatrix + ComplianceScoreCard (struttura finale, mock data)

**Milestone:** Upload ZIP + context → pipeline Azure → scoring ISO 9001 → risultati in UI.

---

### Settimana 3 — ISO 14001/45001 + Document viewer + Chat

1. Codifica `iso14001_clauses.py` e `iso45001_clauses.py`
2. Scrivi `iso14001_gap.md` e `iso45001_gap.md`
3. Aggiorna `gap_analyzer.py` per multi-norma (3 call parallele Azure)
4. Integra `react-pdf`: `DocumentViewer.jsx` con highlight pagine
5. Collega traceability_chain a DocumentViewer (click NCR → PDF alla pagina giusta)
6. Crea `backend/compliance/chat_engine.py` (RAG su ChromaDB + Azure)
7. Crea `ChatPanel.jsx` (two-panel layout)
8. Crea `RadarChart.jsx` + `GapMatrix.jsx` con dati reali

**Milestone:** Multi-norma funzionante, click NCR → documento aperto alla pagina, chat grounded.

---

### Settimana 4 — DOCX + Tracking + Storico

1. Crea `backend/compliance/report_builder.py` (DOCX con sezione SPoF dedicata)
2. Integra DOCX nella pipeline (Fase 4)
3. Endpoint download DOCX
4. `NCRProgressTracker.jsx` (Open/In-Progress/Closed, %)
5. `backend/compliance/delta_engine.py` (confronto analisi)
6. `DeltaView.jsx` (delta score per clausola)
7. `AnalysisHistory.jsx` + `AnalysisDetail.jsx` con dati reali
8. `ComplianceDashboard.jsx` con trend chart reale (Recharts)

**Milestone:** Sistema completo. Download DOCX, tracking NCR, confronto analisi nel tempo.

---

### Settimana 5 — Polish per demo Five Rise

1. Test su documenti reali UK-style (risk assessment, training records, supplier list, quality manual)
2. Tuning prompt: calibrazione severity thresholds, verifica SPoF detection
3. Branding UI: nome prodotto, colori professionali, 100% UK English
4. Empty states, loading states, error boundaries
5. Admin panel adattato da AUDIT-OS
6. Setup `cloudflare tunnel` o `ngrok` per demo remota
7. Preparazione scenario demo con ZIP di test UK realistici

**Milestone: prototipo demo-ready per call con Fred.**

---

## Strategia demo per Fred

**Cosa mostrare:**
1. Step 0: compila context intake live (lui vede che è personalizzato)
2. Upload ZIP con documenti UK ISO-style
3. Elaborazione live con barra progresso
4. Results: score, SPoF evidenziati, click NCR → PDF a pagina giusta
5. Chat: "What should we fix first?" → risposta grounded con fonte
6. Download DOCX executive summary

**Messaggio chiave:** "Il prototipo esiste. Non stiamo vendendo un'idea. La partnership definisce chi possiede cosa."

---

## File di riferimento in AUDITORSEMI (sola lettura, MAI modificare)

- `webapp/v2/pipeline.py` — struttura pipeline da replicare
- `webapp/v2/zip_extractor.py`, `file_triage.py` — copiare identici
- `webapp/prompts/universal_evidence_prompt_v3.md` — riferimento per costruire il nuovo prompt (non riusarlo direttamente)
- `webapp/modules/db_manager.py` — estendere con nuove tabelle
- `frontend/src/hooks/useSSEProcess.js` — copiare identico
- `callenglishpartnership/Master ISO 9001 14001 45001 Compliance Knowledge Base & Audit Blueprint.pdf` — knowledge base per costruire iso_clauses/

---

## Prompt da dare a Claude Code — fase per fase

> Tutto il setup e lo sviluppo viene fatto chiedendo a Claude Code di eseguire.
> Tu apri Claude Code nella cartella giusta e incolli il prompt della fase corrente.
> Claude Code eseguirà i comandi, creerà i file, verificherà che tutto funzioni.

---

### PROMPT 0 — Apertura sessione (ogni volta che riapri compliance-os)

Da incollare all'inizio di ogni sessione di lavoro su compliance-os:

```
Sei in compliance-os, il prototipo separato da AUDIT-OS per Five Rise Consultancy.
Leggi il file CLAUDE.md nella root di questo progetto per le istruzioni specifiche.
REGOLA ASSOLUTA: non toccare mai la cartella C:\Users\user\AUDITORSEMI. Mai.
Lavoriamo solo dentro C:\Users\user\compliance-os.
Stack: FastAPI backend in /backend, React frontend in /frontend.
Provider LLM primario: Azure OpenAI GPT-4.1-mini (GDPR EU). Gemini è solo fallback.
Dimmi quando hai letto CLAUDE.md e sei pronto.
```

---

### PROMPT 1 — Clone, pulizia, repo GitHub

> Aprire Claude Code dalla cartella `C:\Users\user\` (NON da AUDITORSEMI).

```
Devo creare il nuovo progetto ComplianceOS clonando AUDIT-OS in una cartella separata.
Esegui questi step nell'ordine esatto, fermati se qualcosa va storto:

1. Clona https://github.com/DocAllfix/audit-system in C:\Users\user\compliance-os
   (NON dentro AUDITORSEMI — nella cartella padre C:\Users\user\)

2. Entra in compliance-os e rimuovi il remote origin (git remote remove origin)

3. Elimina SOLO da compliance-os questi file e cartelle (MAI toccare AUDITORSEMI):
   - webapp\modules\checklist_filler.py
   - webapp\modules\checklist_producer.py
   - webapp\modules\structured_evidence_generator.py
   - webapp\modules\structured_evidence_parser.py
   - webapp\modules\report_generator.py
   - webapp\v2\incremental_docx_builder.py
   - webapp\v2\docx_merger.py
   - webapp\v2\narrative_client_v2.py
   - webapp\prompts\universal_evidence_prompt_v3.md
   - webapp\prompts\universal_evidence_prompt_spike_llm_v3.md
   - webapp\prompts\universal_evidence_prompt_spike_llm_v31.md
   - cartella webapp\prompts\checklist\
   - cartella webapp\prompts\checklist_schemas\
   - cartella webapp\templates\
   - frontend\src\pages\GeneraReport.jsx
   - frontend\src\pages\ProduciChecklist.jsx
   - frontend\src\pages\CompilaChecklist.jsx
   - frontend\src\pages\StoricoPratiche.jsx
   - cartella frontend\src\components\checklist\
   - frontend\src\components\layout\WorkflowLayout.jsx
   - tutti i file *.zip, *.docx, *.pdf nella root
   - file anonymize_demo.py, MIGRATION_LOCAL_GPT41MINI.md
   - cartelle scripts\, tests\test_v2\, callenglishpartnership\, quotasscreenshot\, testllmnew\

4. Rinomina webapp\ → backend\

5. Verifica che .gitignore copra: venv/, __pycache__/, *.env, *.pyc, node_modules/
   Se mancano voci, aggiungile.

6. Crea il repo GitHub privato DocAllfix/compliance-os usando gh CLI.
   Collega il remote e fai il primo commit con messaggio:
   "Initial ComplianceOS: stripped AUDIT-OS base, removed auditor dead code"

7. Mostrami la struttura finale della cartella compliance-os (ls -la ricorsivo fino a 2 livelli)
   e dimmi che tutto è andato bene.
```

---

### PROMPT 2 — Ambiente Python e dipendenze

> Aprire Claude Code dalla cartella `C:\Users\user\compliance-os\`.

```
Devo creare l'ambiente Python per ComplianceOS.

1. Crea il virtual environment in C:\Users\user\venv-compliance\
   (fuori dalla cartella compliance-os — non deve essere committato)

2. Attiva il venv e installa le dipendenze da backend\requirements.txt

3. Installa le nuove dipendenze necessarie per ComplianceOS:
   - chromadb (per il vector store locale)
   Aggiungi chromadb a backend\requirements.txt dopo l'installazione.

4. Verifica che chromadb sia installato correttamente:
   python -c "import chromadb; print('ChromaDB OK:', chromadb.__version__)"

5. Installa le dipendenze frontend:
   cd frontend && npm install
   Aggiungi anche react-pdf: npm install react-pdf
   Poi torna alla root.

6. Crea il file backend\.env con questo contenuto template
   (usa valori placeholder — io li sostituirò con le chiavi reali):
   AZURE_OPENAI_KEY=YOUR_KEY_HERE
   AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
   AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
   AZURE_OPENAI_API_VERSION=2024-02-01
   AZURE_DI_KEY=YOUR_DI_KEY_HERE
   AZURE_DI_ENDPOINT=https://YOUR-DI-RESOURCE.cognitiveservices.azure.com
   GEMINI_API_KEY=YOUR_GEMINI_KEY_HERE
   V2_PROVIDER=gpt-4.1-mini-azure
   V2_OCR_ENGINE=azure_di
   APP_NAME=ComplianceOS
   APP_VERSION=0.1.0-mvp
   CORS_ORIGINS=http://localhost:5173

7. Crea il file frontend\.env.local:
   VITE_API_BASE_URL=http://localhost:8000
   VITE_APP_NAME=ComplianceOS

8. Dimmi che tutto è pronto e come avviare backend e frontend.
```

---

### PROMPT 3 — CLAUDE.md e scaffold backend base

```
Devo creare il CLAUDE.md di questo progetto e lo scaffold base del backend.

1. Crea il file CLAUDE.md nella root di compliance-os con questo contenuto esatto:

---
# ComplianceOS — Istruzioni per Claude

## Identità progetto
ComplianceOS è un prodotto separato da AUDIT-OS, per compliance manager (non auditor di terza parte).
Serve Five Rise Consultancy (UK) — advisory, non audit adversariale.
Norme supportate MVP: ISO 9001:2015, ISO 14001:2015, ISO 45001:2018.

## REGOLA FONDAMENTALE
MAI modificare il repository AUDITORSEMI (C:\Users\user\AUDITORSEMI). MAI.
Qualsiasi modifica va fatta solo qui dentro compliance-os.

## Lingua
Frontend e messaggi utente: UK English.
Backend Python: commenti in italiano vanno bene.

## Provider LLM
- Azure OpenAI GPT-4.1-mini: PRIMARIO per tutto
- Gemini 2.5 Flash: fallback automatico su rate limit 429
- Azure Document Intelligence: OCR primario per PDF scansionati

## Pipeline (3 fasi)
Fase 1: Evidence Extraction → YAML (prompt in backend/prompts/compliance/evidence_extraction_prompt.md)
Fase 2: ChromaDB embedding delle evidence cards
Fase 3: Gap Analysis per clausola ISO (prompt in backend/prompts/compliance/iso*_gap.md)
NON usare il prompt v3 di AUDIT-OS — è per auditor terza parte, non per compliance.

## Knowledge base clausole ISO
Fonte: callenglishpartnership/Master ISO 9001 14001 45001 Compliance Knowledge Base.pdf
(copiato in backend/compliance/iso_clauses/ come Python dict)

## Come avviare
Backend: cd backend && ..\venv-compliance\Scripts\Activate.ps1 && uvicorn api_server:app --reload
Frontend: cd frontend && npm run dev
---

2. Estendi backend\modules\db_manager.py aggiungendo le 3 nuove tabelle:
   - compliance_analyses (con campi context intake: sector, employee_range, certified, sites_count)
   - ncr_actions (tracking Open/In-Progress/Closed per clausola)
   - compliance_chat (storico chat grounded post-analisi)
   Mantieni tutte le tabelle esistenti invariate.

3. Crea backend\compliance\__init__.py (vuoto)

4. Crea backend\compliance\schemas.py con tutti i modelli Pydantic:
   - CompanyContext
   - TraceabilityLink
   - RemediationPlan
   - ClauseGap (con campo is_spof: bool)
   - NormGapReport (con spof_count)
   - ComplianceAnalysisResult

5. Crea uno stub backend\compliance\gap_analyzer.py che per ora ritorna mock data
   (analyze_compliance() → restituisce ComplianceAnalysisResult con dati fake)

6. Aggiorna backend\api_server.py aggiungendo (senza rimuovere gli endpoint esistenti):
   - POST /api/compliance/analyze (stub SSE, usa lo stub gap_analyzer)
   - GET /api/compliance/analyses
   - GET /api/compliance/analyses/{id}
   - GET /api/compliance/analyses/{id}/download

Dimmi quando hai finito e mostrami i file creati.
```

---

### PROMPT 4 — Frontend base: routing e wizard

```
Devo costruire la struttura base del frontend React per ComplianceOS.

1. Riscrivi frontend\src\App.jsx con le nuove route (UK English):
   / → redirect a /dashboard
   /login → Login (riusato identico)
   /dashboard → ComplianceDashboard
   /new-analysis → NewAnalysis (wizard)
   /analysis/:id → AnalysisDetail
   /history → AnalysisHistory
   /admin → AdminPanel

2. Riscrivi frontend\src\components\layout\Sidebar.jsx con la navigazione compliance:
   - Dashboard
   - New Analysis
   - History
   --- (separatore)
   - Admin (solo per admin)
   Usa UK English per tutte le label.

3. Crea frontend\src\store\complianceStore.js (Zustand):
   - wizard state: currentStep (0-4), companyContext, uploadedFile, analysisResult
   - history state: analyses list
   - actions: setStep, setContext, setFile, setResult, reset

4. Crea frontend\src\pages\ComplianceDashboard.jsx con mock data:
   - 4 KPI cards: Total Analyses, Avg Score, Open Major Gaps, Last Analysis
   - Tabella storico analisi (mock 3 righe)
   - Bottone "New Analysis" che porta a /new-analysis

5. Crea frontend\src\components\compliance\ContextIntakeForm.jsx (Step 0 del wizard):
   6 campi:
   - Company name (text input)
   - Industry sector (Select: Construction / Manufacturing / Services / Logistics / Healthcare / Energy / Other)
   - Number of employees (Select: 1-10 / 11-50 / 51-250 / 250+)
   - Standards to assess (CheckboxGroup: ISO 9001 / ISO 14001 / ISO 45001)
   - Currently certified? (Select: Yes / No / In progress)
   - Number of operating sites (Select: 1 / 2-5 / 5+)
   Bottone Continue abilitato solo quando tutti i required sono compilati.

6. Crea frontend\src\pages\NewAnalysis.jsx con il wizard a 5 step:
   Step 0: ContextIntakeForm
   Step 1: FileDropzone (riusato da AUDIT-OS)
   Step 2: Review & Confirm (riepilogo context + file count + norme + stima tempo + bottone Start)
   Step 3: Progress bar (mockato per ora, uk english messages)
   Step 4: placeholder "Results will appear here"

Usa shadcn/ui per tutti i componenti UI. UK English ovunque.
Mostrami i file uno per uno mentre li crei.
```

---

### PROMPT 5 — Settimana 2: pipeline reale ISO 9001

```
È ora di costruire la pipeline reale. Lavoriamo su ISO 9001 per prima.

1. Crea backend\prompts\compliance\evidence_extraction_prompt.md
   È il nuovo prompt per la Fase 1 (non è il v3 di AUDIT-OS).
   Deve:
   - Avere system identity advisory: "You are a compliance analysis assistant helping managers identify documentation gaps"
   - Essere in UK English
   - Mantenere la struttura YAML del v3 (18 categorie, 1-doc-1-scheda, regole parser-safe)
   - Aggiungere due campi obbligatori per ogni scheda:
     iso_clause_primary: "ISO 9001 §8.4" (la clausola ISO più rilevante per quel documento)
     gap_signal: true/false (true se il documento evidenzia una lacuna o scadenza)
   - Ricevere {company_context} nel system prompt (settore, dimensione, norma) per orientare la classificazione
   - Rimuovere: riferimenti a "auditor", "checklist a valle", "commessa", linguaggio adversariale

2. Crea backend\compliance\context_intake.py:
   - Modello CompanyContext (se non già in schemas.py)
   - Funzione build_context_prompt_block(ctx: CompanyContext) → str
     Produce un blocco testo da iniettare nel system prompt:
     "Company context: [Company Name] operates in [sector] with [employees] employees.
      Currently [certified/not certified]. Operating across [sites] sites.
      Standards under assessment: [norms]."

3. Crea backend\compliance\iso_clauses\iso9001_clauses.py
   Dizionario ISO9001_CLAUSES con tutte le clausole principali (da 4.1 a 10.3).
   Per ogni clausola:
   - id, title, area
   - is_spof: bool
   - critical_sectors: lista settori dove è Major se assente
   - typical_ncs: lista di NC tipiche (dal Knowledge Base PDF che hai disponibile in callenglishpartnership/)
   - evidence_keywords: termini di ricerca per ChromaDB query
   - remediation_template: what, who, when_major, when_minor, effort

4. Crea backend\compliance\embedder.py:
   - Classe EvidenceEmbedder con ChromaDB client embedded (zero server)
   - Metodo index_evidence_cards(cards: list[dict]) → crea collection e indicizza le schede YAML
   - Metodo query_for_clause(clause: dict, n_results=3) → list[dict] con chunks rilevanti + metadata

5. Crea backend\prompts\compliance\gap_analysis_base.md e iso9001_gap.md:
   Il prompt riceve: evidence cards rilevanti + clausola + company_context
   Produce JSON: score 0-100, severity, finding (max 150 words UK English), sources citati, remediation Who/What/When

6. Implementa backend\compliance\gap_analyzer.py reale:
   - analyze_compliance(evidence_yaml, norms, company_context, emitter) → ComplianceAnalysisResult
   - Per ogni norma: per ogni clausola → query ChromaDB → Azure GPT-4.1-mini → ClauseGap validato Pydantic

7. Riscrivi backend\v2\pipeline.py per la compliance pipeline (4 fasi)

Inizia dal punto 1. Mostrami ogni file completo prima di passare al successivo.
```

---

### PROMPT 6 — Settimana 3: ISO 14001/45001 + Document viewer + Chat

```
ISO 9001 funziona. Aggiungiamo le altre norme e il document viewer.

1. Crea backend\compliance\iso_clauses\iso14001_clauses.py
   (stessa struttura di iso9001_clauses.py, clausole ISO 14001:2015)

2. Crea backend\compliance\iso_clauses\iso45001_clauses.py
   (clausole ISO 45001:2018)

3. Crea backend\prompts\compliance\iso14001_gap.md e iso45001_gap.md

4. Aggiorna gap_analyzer.py per supportare multi-norma
   (3 chiamate Azure in parallelo con asyncio.gather)

5. Crea frontend\src\components\compliance\DocumentViewer.jsx:
   - Usa react-pdf per mostrare PDF
   - Riceve props: fileUrl, targetPages (array di numeri pagina da evidenziare)
   - Apre direttamente alla prima pagina target
   - Highlight giallo sulle pagine segnalate
   - Bottone "View full document" per espanderlo

6. Crea frontend\src\components\compliance\GapMatrix.jsx:
   - Tabella NCR con colonne: Severity | Clause | Finding preview | Source file
   - Filtri: All / Major / Minor / Observation / SPoF only
   - Ogni riga espandibile (Radix Accordion): finding completo + evidenza + action plan
   - Click riga → emette evento che aggiorna DocumentViewer (apre file alla pagina giusta)

7. Crea backend\compliance\chat_engine.py:
   - Funzione answer_question(analysis_id, question, db) → str
   - Usa ChromaDB per trovare evidence cards rilevanti alla domanda
   - Chiama Azure GPT-4.1-mini con solo le card rilevanti
   - Ogni risposta include lista di sources citati (file_name:page)

8. Crea frontend\src\components\compliance\ChatPanel.jsx:
   - Input in basso, messaggi sopra
   - Ogni risposta AI mostra chips cliccabili con il file sorgente
   - Click chip → aggiorna DocumentViewer

9. Aggiorna Step 4 di NewAnalysis.jsx con il layout two-panel reale:
   - GapMatrix (sinistra) + DocumentViewer (destra) su desktop
   - ComplianceScoreCard in cima
   - ChatPanel in fondo
   - Download DOCX button

Mostrami un file alla volta.
```

---

### PROMPT 7 — Settimana 4: DOCX + tracking + storico

```
Devo completare il sistema con DOCX professionale, tracking NCR e storico.

1. Crea backend\compliance\report_builder.py:
   DOCX manager-friendly con questa struttura:
   - Cover: Company, sector, norme, data, "Prepared for [company] by ComplianceOS"
   - Executive Summary (1 pag): Overall score %, Major/Minor/Obs/Conformant, SPoF count, top 3 rischi
   - Single Points of Failure: sezione dedicata evidenziata in rosso/arancio
   - Critical Findings: per ogni Major: clausola, finding, evidence file+page, azione
   - Action Plan Template: tabella Priority | Clause | Action | Responsible | Deadline | Effort
   - Full Clause Matrix: tutte le clausole, score, severity, key finding
   Usa python-docx, colori severity: Major=rosso #DC2626, Minor=arancione #F97316,
   Observation=giallo #CA8A04, Conformant=verde #16A34A

2. Integra report_builder nella pipeline (Fase 4)

3. Implementa endpoint GET /api/compliance/analyses/{id}/download

4. Crea frontend\src\components\compliance\NCRProgressTracker.jsx:
   - Per ogni finding, toggle status: Open → In Progress → Closed
   - Barra % completamento azioni per norma
   - Chiama PATCH /api/compliance/analyses/{id}/actions/{clause_id}

5. Crea backend\compliance\delta_engine.py:
   - compare_analyses(analysis_id_new, analysis_id_old) → dict con delta per clausola
   - Ogni clausola: score_old, score_new, delta, severity_changed

6. Crea frontend\src\components\compliance\DeltaView.jsx:
   - Mostra miglioramento/peggioramento per clausola vs analisi precedente
   - Badge verde se migliorato, rosso se peggiorato

7. Crea frontend\src\pages\AnalysisHistory.jsx con lista analisi reali dal DB

8. Crea frontend\src\pages\AnalysisDetail.jsx che ricarica un'analisi salvata

9. Aggiorna ComplianceDashboard.jsx con dati reali dall'API + trend chart Recharts

Mostrami i file critici uno per uno.
```

---

### PROMPT 8 — Settimana 5: polish e demo

```
Siamo alla fase finale. Devo rendere ComplianceOS demo-ready per una call con Fred Stewart di Five Rise Consultancy.

1. Revisione completa UI:
   - Applica la palette colori dal CLAUDE.md: Deep Navy #0C1120, Electric Blue #3A82FF
   - Aggiorna frontend\src\index.css con le variabili CSS severity e colori principali
   - Assicurati che tutto sia in UK English (nessuna parola italiana visibile)
   - Nessun riferimento a "AUDIT-OS" visibile nell'UI

2. Branding:
   - Nome prodotto nell'header: "ComplianceOS"
   - Rimuovi qualsiasi logo o testo di AUDIT-OS

3. Empty states:
   - Dashboard vuota (nessuna analisi ancora): messaggio + CTA "Start your first analysis"
   - GapMatrix vuota durante elaborazione: skeleton loader
   - Chat senza domande: placeholder "Ask a question about this analysis..."

4. Error boundaries:
   - Se pipeline fallisce: messaggio errore chiaro con retry button
   - Se PDF non caricabile: fallback con messaggio "Document preview unavailable"

5. Verifica la demo checklist completa:
   [ ] Step 0 context intake funzionante e salvato
   [ ] Upload ZIP → elaborazione reale con Azure
   [ ] GapMatrix con severity e SPoF evidenziati
   [ ] Click NCR → PDF apre alla pagina giusta
   [ ] Chat grounded risponde con fonti citate
   [ ] Download DOCX con Executive Summary completo
   [ ] NCR progress toggle funzionante
   [ ] Nessuna parola italiana nell'UI
   [ ] Login → Dashboard → New Analysis flusso pulito

6. Setup cloudflare tunnel per demo remota:
   Mostrami il comando esatto per esporre localhost:5173 via HTTPS
   senza deploy su server.

Dimmi cosa manca e cosa ha problemi.
```

---

## Design UI/UX — Riferimenti e specifiche

### Stack di riferimento consigliato

Il frontend usa già shadcn/ui + Tailwind CSS + Recharts + Framer Motion. Si mantiene questo stack senza aggiungere librerie pesanti. Aggiunte specifiche per ComplianceOS:
- `react-pdf` — PDF viewer in-app (già aggiunto al npm install sopra)
- Nessuna altra libreria nuova per MVP

### Palette colori

```css
/* Variabili CSS da aggiungere in frontend/src/index.css */

/* Dark Navy (background principale) */
--bg-primary: #0C1120;
--bg-secondary: #111827;
--bg-card: #1A2236;

/* Electric Blue (accent primario) */
--accent-primary: #3A82FF;
--accent-hover: #2563EB;

/* Testo */
--text-primary: #F8FAFC;
--text-secondary: #8895A7;
--text-muted: #4B5563;

/* Severity — compliance semantics */
--severity-major: #EF4444;       /* rosso */
--severity-major-bg: #1F0A0A;
--severity-minor: #F59E0B;       /* ambra */
--severity-minor-bg: #1C1208;
--severity-observation: #EAB308; /* giallo */
--severity-obs-bg: #1C1A08;
--severity-conformant: #10B981;  /* verde smeraldo */
--severity-conformant-bg: #0A1F17;

/* SPoF — evidenziazione speciale */
--spof-color: #F97316;           /* arancio bruciato, più serio del Minor */
--spof-bg: #1C1008;
```

### Layout principale (Sidebar + Content)

```
┌─────────────────────────────────────────────────────────┐
│  HEADER — Logo "ComplianceOS" + user menu — bg-primary  │
├────────────┬────────────────────────────────────────────┤
│            │                                            │
│  SIDEBAR   │  CONTENT AREA                              │
│  240px     │  padding: 24px                             │
│  bg-card   │  bg-secondary                              │
│            │                                            │
│  ▸ Dashboard         Dashboard: KPI cards 2x2,         │
│  ▸ New Analysis      RadarChart + ClauseBarChart        │
│  ▸ History                                              │
│            │  New Analysis: wizard step 0→4             │
│  ─────────  │                                            │
│  Admin     │  Analysis Detail: split panel              │
│            │  GapMatrix (left) + DocViewer (right)       │
└────────────┴────────────────────────────────────────────┘
```

### Componenti chiave e come implementarli

**1. ComplianceScoreCard** — usa `shadcn/ui Card` con:
- Cerchio progress (SVG stroke-dasharray) con colore da severity
- Numero grande centrale (es. "67%")
- 4 badge sotto: Major N | Minor N | Obs N | Conformant N
- SPoF count in evidenza se > 0 (badge arancio con icona warning)

**2. GapMatrix** — usa `shadcn/ui Table` + `Radix Accordion`:
- Colonna severity (badge colorato), clausola, finding preview, source file
- Espandibile per riga: mostra finding completo + evidenza citata + action
- Filtri in cima: All / Major / Minor / Observation / SPoF only
- Riga click → apre DocumentViewer sulla destra al file+pagina corretto

**3. DocumentViewer** — usa `react-pdf`:
- Panel destro, 50% width su desktop, full-screen su mobile
- Pagina target caricata direttamente (non dalla prima pagina)
- Highlight giallo sulle pagine segnalate nella traceability
- Bottone "Open full PDF" per espandere

**4. RadarChart** — usa `Recharts RadarChart`:
- 6 assi: Context & Leadership | Planning | Support | Operations | Performance | Improvement
- Colori: area fill rgba(58,130,255,0.2), stroke #3A82FF
- Se multi-norma: una shape per norma, colori distinti
- Tooltip on hover per ogni asse

**5. ChatPanel** — input in fondo, messaggi sopra (stile chat):
- User message: allineato destra, bg-accent-primary
- Assistant message: allineato sinistra, bg-card
- Ogni risposta assistant ha lista di source chips cliccabili (file_name:pagina)
- Click source chip → apre DocumentViewer a quella pagina

**6. ContextIntakeForm (Step 0)** — usa `shadcn/ui` Select + Checkbox:
- Layout: 2 colonne su desktop, 1 colonna su mobile
- Validazione inline (campo vuoto = bordo rosso)
- Progress indicator "Step 1 of 5" in alto
- Bottone "Continue" abilitato solo quando tutti i required sono compilati

### Ispirazione visiva di riferimento

| Prodotto | Cosa copiare |
|---|---|
| **Vanta** | Dashboard minimale, color coding red/yellow/green, drill-down |
| **Drata** | Progressive disclosure, Index → Detail → Context panel |
| **NotebookLM** | Two-panel: sources left + content right |
| **Linear** | Sidebar navigation, card design, status badges |
| **Vercel Dashboard** | Clean dark mode, KPI cards, typography |

### Tipografia

- Font: usa il font già in AUDIT-OS (`Inter` o `Geist` — verifica in `index.css`)
- Heading principale: 24px bold
- Subheading: 16px semibold, text-secondary
- Body: 14px regular, text-primary
- Badge/label: 11px semibold uppercase

---

## Verifica finale (demo-ready checklist)

- [ ] Step 0 context intake: 6 domande in 60 secondi, salvate nel DB
- [ ] Upload ZIP → progress bar UK English → elaborazione reale
- [ ] Context usato nella pipeline: severity varia in base a sector + employee_range
- [ ] Analisi ISO 9001 produce scoring per clausola con fonti citate
- [ ] SPoF evidenziati separatamente nel report e nel DOCX
- [ ] Click su NCR → PDF viewer apre documento alla pagina giusta evidenziata
- [ ] Chat grounded: ogni risposta cita il documento sorgente
- [ ] Action plan: Who/What/When per ogni Major finding
- [ ] NCR status toggle: Open → In-Progress → Closed con % completamento
- [ ] Re-upload ZIP → delta view mostra miglioramento clausola per clausola
- [ ] DOCX scaricabile: Executive Summary leggibile da manager UK
- [ ] Nessun riferimento a "AUDIT-OS", "Italia", terminologia auditor italiana
- [ ] Demo via cloudflare tunnel funzionante da browser remoto
