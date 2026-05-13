# ComplianceOS — Screenshot Reference

Visual overview of every user-facing screen in the current product. Updated after each frontend sprint or every time a screen materially changes (new section, palette tweak, layout reflow).

The reference run uses the **CONSORZIO JEOCON 14001.zip** test corpus on `localhost`, light and dark theme, full-page captures. Saved under `docs/screens/`. Naming convention: `YYYYMMDD_<page>_<theme>.png` (e.g. `20260513_results_light.png`).

> ℹ️ The actual `.png` files are not yet committed — Sprint F5 ships the documentation scaffold and the procedure to regenerate them. To produce them, follow §1 below. Once captured, replace each placeholder line with the actual `![alt](screens/<file>.png)` reference.

---

## 1. How to (re)generate the screenshots

Two terminals + a browser. ~15 minutes total.

```powershell
# Terminal 1 — Backend
cd backend
..\venv-compliance\Scripts\Activate.ps1     # adjust if your venv differs
uvicorn api_server:app --reload

# Terminal 2 — Frontend
cd frontend
npm run dev    # opens on http://localhost:5173 with /api proxied to :8000
```

Then in the browser:

1. **`/login`** — submit credentials → captured automatically before redirect (`20260513_login_light.png`, `_dark.png`).
2. **`/dashboard`** — capture the empty state once, then capture again after a single analysis is run (so KPI + sparkline are populated).
3. **`/new-analysis`** — capture each of the 4 wizard steps. Step 4 (Progress) needs an actual ZIP upload to look real; use the CONSORZIO ZIP.
4. **`/analyses/:id`** — long screenshot, full-page scroll. Should show: Company Snapshot, Executive Narrative, summary, tabs, Expiry table (5 expired rows on CONSORZIO), Top 10 Priority Integrations, Findings list.
5. **`/analyses/:id/plan`** — NCR tracker; click one action through `Open → In progress → Closed` to show the pill state machine.
6. **`/analyses/:id/chat`** — kick the three test queries from the manual test note:
   - `"Which documents are expired?"` (sources non-vuoti)
   - `"Which clause is most critical here?"` (clausola citata)
   - `"What is the company VAT number?"` (refusal banner)

Optional — automate with Playwright MCP using a tiny script under `mocks/_screens.py` (not committed yet; left as a future ticket).

---

## 2. The screens

### 2.1 Login

> *Two-column editorial layout. Left half explains what ComplianceOS does. Right half a focused form. Theme toggle in top-right.*

- `screens/YYYYMMDD_login_light.png`
- `screens/YYYYMMDD_login_dark.png`

### 2.2 Dashboard — empty state

> *First-run greeting + CTA. No KPI grid until the first analysis is complete.*

- `screens/YYYYMMDD_dashboard_empty.png`

### 2.3 Dashboard — populated

> *Greeting personalised by hour + first name. KPI grid: overall conformance (weighted avg of latest 5), open major findings, analyses run, latest analysis date. Sparkline from real overall_score series. By-severity bars from the latest analysis. Recent analyses list cliccabile.*

- `screens/YYYYMMDD_dashboard_light.png`
- `screens/YYYYMMDD_dashboard_dark.png`

### 2.4 New Analysis wizard

> *Four steps, left-rail stepper. Step 1 = context, Step 2 = upload (drag + click), Step 3 = review, Step 4 = SSE progress with live phase log.*

- `screens/YYYYMMDD_wizard_step1.png`
- `screens/YYYYMMDD_wizard_step2.png`
- `screens/YYYYMMDD_wizard_step3.png`
- `screens/YYYYMMDD_wizard_step4.png`

### 2.5 Results — full report

> *Compliance review for a real analysis. Sections in order: header (company / sector / date / per-norm scores / Ask the analyst + Download), Company Snapshot, Executive Narrative (serif), summary line, tabs (Findings active, Plan linked, Compare disabled), Expiry table (rosso/ambra/giallo per severity), Top 10 Priority Integrations, Findings list with expand.*

- `screens/YYYYMMDD_results_light.png`
- `screens/YYYYMMDD_results_dark.png`

### 2.6 Plan — NCR tracker

> *Plan overview con closedPct vero. Critical actions (MAJOR + SPoF marker), Improvement actions (MINOR). Status pill avanza open → in-progress → closed con PATCH al backend.*

- `screens/YYYYMMDD_plan_light.png`

### 2.7 Chat — grounded conversation

> *3-column layout. Threads sidebar a sinistra mostra la conversazione corrente in-memory. Conversation al centro con turn user + turn assistant (3-dot thinking durante l'attesa LLM, banner refusal neutro se "no evidence", sources chip cliccabili). Composer in basso con Enter-to-send.*

- `screens/YYYYMMDD_chat_light.png`
- `screens/YYYYMMDD_chat_dark.png`

---

## 3. Severity palette reference

Quick visual key for anyone reviewing the screenshots:

| Severity     | Token                            | OKLCH approx      | Shown in           |
|--------------|----------------------------------|-------------------|--------------------|
| MAJOR        | `--severity-major`               | rosso (≈ #DC2626) | badge, row tint, KPI trend down |
| MINOR        | `--severity-minor`               | ambra (≈ #F59E0B) | badge, row tint    |
| OBSERVATION  | `--severity-observation`         | giallo (≈ #EAB308)| badge, row tint    |
| CONFORMANT   | `--severity-conformant`          | verde sobrio (≈ #16A34A) | breakdown bar |
| SPoF         | `--severity-spof`                | arancio bruciato (≈ #EA580C) | findings badge accanto a MAJOR |
| Accent (gold)| `--accent`                       | oro (≈ #CA8A04)   | CTA, clause tag in Integrations |

Used only where there is semantic severity. Never decoratively.

---

## 4. Known visual gaps (post-Sprint F5)

- **Compare tab** is disabled with tooltip "Available once a second analysis exists". Will become active when the user has ≥2 analyses; UX brief to write.
- **`/chat` route without analysis id** shows an empty state with link to dashboard. We could later let it auto-select the most recent analysis; debated.
- **Sparkline trend** with a single analysis shows a horizontal line. Acceptable for first-run, but a 2nd analysis is needed to make the chart meaningful.
- **Plan export DOCX** is a link to the standard `/api/compliance/analyses/:id/download` (which is the full report). A plan-only DOCX is a future backend ticket.

---

## 5. Maintenance

Add a new screenshot whenever a screen materially changes. Don't churn the file for every CSS tweak — only when sections appear/disappear, or palette shifts, or new pages land. Keep the naming convention strict so diffs are obvious.
