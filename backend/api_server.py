# ==============================================================================
# Amisys QHSE — FastAPI REST Backend
# ==============================================================================
# API REST per il frontend React: auth + compliance engine
# (analyze SSE, analyses, report DOCX, chat grounded, NC actions).
#
# Avvio:
#   cd backend
#   uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
# ==============================================================================

from __future__ import annotations

import os
import sys
import json
import traceback
import logging
from typing import Optional, Dict, List, Any

# ── Percorsi ──────────────────────────────────────────────────────────────────
WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WEBAPP_DIR)

# ── Caricamento .env (rispetta env vars già impostate da systemd) ─────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(WEBAPP_DIR, ".env"), override=False)
except ImportError:
    pass

# ── FastAPI ────────────────────────────────────────────────────────────────────
from fastapi import (
    FastAPI, UploadFile, File, Form, Header,
    HTTPException, Depends, Query, Body
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import concurrent.futures

# ── Moduli applicazione ────────────────────────────────────────────────────────
# Fase 2 consolidamento: rimossi gli import legacy AUDITORSEMI (config checklist,
# pratiche, error log, statistiche). Le funzioni compliance del db_manager sono
# importate lazy nei singoli endpoint.
from modules.auth_manager import (
    authenticate,
    create_persistent_session,
    validate_session_token,
    invalidate_session_token,
    load_users,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Amisys QHSE-api")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Amisys QHSE API",
    version="0.1.0-mvp",
    description="REST backend per Amisys QHSE — Five Rise Consultancy",
)

# Fase 3 consolidamento — CORS esplicito da env, niente più wildcard "*"
# (incompatibile con allow_credentials e inaccettabile per la demo via tunnel:
# aggiungere l'origin del tunnel a CORS_ORIGINS quando serve).
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Autenticazione + ownership ───────────────────────────────────────────────
# Fase B: gli helper vivono in api_deps.py (riusati dai router modulari senza
# import circolari). Ri-esportati qui così gli endpoint esistenti non cambiano.
from api_deps import (  # noqa: E402
    _get_current_user,
    _require_analysis_access,
    _require_folder_access,
    _require_document_access,
)


def _audit(user, action, entity_type=None, entity_id=None, detail=None) -> None:
    """Wrapper sottile sull'audit trail (Fase B). Lazy import + non solleva mai:
    un audit fallito non deve mai rompere la richiesta."""
    try:
        from modules.audit_log import log_audit
        log_audit(user, action, entity_type, entity_id, detail)
    except Exception:
        pass


# ── Router modulari (Fase C+) ────────────────────────────────────────────────
from routers.dms import router as dms_router  # noqa: E402
from routers.notifications import router as notifications_router  # noqa: E402
from routers.tasks import router as tasks_router  # noqa: E402
app.include_router(dms_router)
app.include_router(notifications_router)
app.include_router(tasks_router)

# Fase E — scheduler scadenze/retention (no-op se SCHEDULER_ENABLED non settato)
from scheduler import install_scheduler  # noqa: E402
install_scheduler(app)


# ── Modelli Pydantic ───────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    """Stato del servizio + configurazione provider (mai le chiavi)."""
    return {
        "status": "ok",
        "azure_openai_configured": bool(os.environ.get("AZURE_OPENAI_API_KEY", "").strip()),
        "azure_di_configured": bool(os.environ.get("AZURE_DI_KEY", "").strip()),
        "supported_norms": ["ISO 9001:2015", "ISO 14001:2015", "ISO 45001:2018"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/login")
async def login(body: LoginRequest):
    # authenticate() restituisce (bool, Optional[str]) — NON un dict utente
    success, error_msg = authenticate(body.username, body.password)
    if not success:
        _audit(body.username, "login_failed", "session", None, {"reason": error_msg or "invalid"})
        raise HTTPException(status_code=401, detail=error_msg or "Credenziali non valide")
    token = create_persistent_session(body.username)
    _audit(body.username, "login", "session", None)
    # Carica i dati utente da users.json per costruire la risposta
    users = load_users()
    user_data = users.get(body.username.lower(), users.get(body.username, {}))
    return {
        "token": token,
        "user": {
            "username": body.username,
            "email": "",                                       # non presente in users.json
            "role": user_data.get("role", "auditor"),
            "display_name": user_data.get("name", body.username),
        },
    }


@app.get("/api/auth/me")
async def me(user: Dict = Depends(_get_current_user)):
    return {
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "auditor"),
        "display_name": user.get("display_name", user.get("username", "")),
    }


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            invalidate_session_token(token)
        except Exception:
            pass
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE — REQUIREMENT SETS (Fase 7, PRD §1.4.4b)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/compliance/requirement-sets")
async def list_requirement_sets_endpoint(user: Dict = Depends(_get_current_user)):
    """Set di criteri operativi disponibili (data/requirement_sets/*.yaml).

    I `label` ritornati possono essere inclusi in `norms` del wizard accanto
    agli standard ISO: il motore li valuta con lo stesso Stage A + Stage B.
    """
    from compliance.custom_requirements import list_requirement_sets
    return list_requirement_sets()


# ══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE — ANALYZE  (SSE streaming)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/compliance/analyze")
async def compliance_analyze(
    file: UploadFile = File(...),
    company_name: str = Form(...),
    sector: str = Form(...),
    employee_range: str = Form(...),
    certified: str = Form(...),
    sites_count: str = Form(...),
    norms: str = Form(...),          # JSON array serializzato, es. '["ISO 9001","ISO 14001"]'
    user: Dict = Depends(_get_current_user),
):
    """
    Pipeline compliance completa (SSE).
    Riceve ZIP documenti + CompanyContext come form fields.

    Stream SSE:
      data: {"pct": 10, "msg": "Reading documents..."}
      data: {"pct": 45, "msg": "Indexing evidence..."}
      data: {"pct": 80, "msg": "Analysing ISO 9001 conformance..."}
      data: {"done": true, "analysis_id": "...", "result": {...}}
      data: {"error": "..."}
    """
    from compliance.schemas import CompanyContext
    from compliance.gap_analyzer import analyze_compliance
    from modules.db_manager import save_compliance_analysis

    file_bytes = await file.read()
    username = user["username"]

    try:
        norms_list: List[str] = json.loads(norms)
    except Exception:
        norms_list = [norms]

    context = CompanyContext(
        company_name=company_name,
        sector=sector,
        employee_range=employee_range,
        certified=certified,
        sites_count=sites_count,
        norms=norms_list,
    )

    def _to_dms(result, outcome) -> None:
        """DMS unificato — popola il DMS dai documenti analizzati (cartella =
        azienda), riusando il testo già estratto (no re-OCR). Non-bloccante."""
        from modules.dms_ingest import ingest_analysis, DMS_AUTOSAVE
        if not DMS_AUTOSAVE:
            return
        try:
            stats = ingest_analysis(
                owner=username, company_name=company_name, zip_bytes=file_bytes,
                analysis_id=result.analysis_id, evidence_yaml=outcome.get("evidence_yaml") or "",
            )
            _audit(username, "analysis_to_dms", "analysis", result.analysis_id, stats)
        except Exception as e:
            logger.warning(f"[Compliance] analysis→DMS ingest failed (non-blocking): {e}")

    return _pipeline_sse_response(
        context=context, username=username, zip_bytes=file_bytes, on_success=_to_dms,
    )


class AnalyzeDmsRequest(BaseModel):
    company_name: str
    sector: str
    employee_range: str
    certified: str
    sites_count: str
    norms: List[str]
    scope: str = "all"                 # all | folder | updated_since
    folder_id: Optional[int] = None
    updated_since: Optional[str] = None  # YYYY-MM-DD


@app.post("/api/compliance/analyze-dms")
async def compliance_analyze_dms(
    body: AnalyzeDmsRequest,
    user: Dict = Depends(_get_current_user),
):
    """Fase D (PRD §1.4.3) — analizza i documenti già nel DMS secondo uno scope
    (tutto / cartella / aggiornati da una data). Costruisce il documents_override
    dai testi estratti del DMS (Phase 1 saltata) e rilancia la pipeline.

    A fine run, fa il backfill del doc_type dei documenti DMS dalle evidence
    card (autorevole, marca doc_type_source='engine'); il PATCH manuale vince.
    """
    from compliance.schemas import CompanyContext
    import modules.dms_manager as dms

    username = user["username"]
    if body.scope == "folder":
        if body.folder_id is None:
            raise HTTPException(status_code=422, detail="folder_id is required for scope=folder")
        _require_folder_access(body.folder_id, user)

    docs = dms.documents_for_scope(
        username, scope=body.scope, folder_id=body.folder_id, updated_since=body.updated_since,
    )
    if not docs:
        raise HTTPException(status_code=409, detail="No documents in the selected scope")

    context = CompanyContext(
        company_name=body.company_name, sector=body.sector,
        employee_range=body.employee_range, certified=body.certified,
        sites_count=body.sites_count, norms=body.norms,
    )

    # filename → (document_id, version) per il backfill post-analisi
    by_name = {d["filename"]: (d["document_id"], d["version"]) for d in docs}

    def _backfill(result, outcome) -> None:
        """Aggiorna doc_type/expiry dei documenti DMS dalle evidence card,
        matchando per filename DENTRO il set analizzato (mai globale)."""
        import yaml as _yaml
        raw = outcome.get("evidence_yaml") or ""
        if not raw.strip():
            return
        # le card sono separate dai marker "# ── DOC N ──"; parse tollerante
        from compliance.gap_analyzer import _parse_evidence_yaml
        try:
            cards = _parse_evidence_yaml(raw)
        except Exception:
            cards = []
        for card in cards:
            fname = str(card.get("file_name", "") or "")
            if fname not in by_name:
                continue
            doc_id, _ver = by_name[fname]
            dtype = str(card.get("doc_type", "") or "").strip()
            expiry = card.get("expiry_date")
            if dtype:
                dms.backfill_doc_type(doc_id, dtype, expiry if expiry else None)
        _audit(username, "analyze_dms", "analysis", result.analysis_id,
               {"scope": body.scope, "documents": len(docs)})

    return _pipeline_sse_response(
        context=context, username=username,
        documents_override=docs, on_success=_backfill,
    )


def _pipeline_sse_response(
    context,
    username: str,
    zip_bytes: Optional[bytes] = None,
    documents_override: Optional[List[Dict[str, Any]]] = None,
    on_success=None,
):
    """Fase 6 — streamer SSE condiviso fra analyze (ZIP), re-analyse (corpus)
    e analyze-dms (scope DMS).

    Esegue la pipeline in un worker thread, inoltra i progress event sulla
    queue asyncio, salva il risultato a fine run e chiude con done/error.
    `on_success(result, outcome)` — callback opzionale dopo il salvataggio
    (Fase D: backfill doc_type del DMS dalle evidence card). Non blocca mai.
    """
    from modules.db_manager import save_compliance_analysis

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(pct: int, msg: str):
        asyncio.run_coroutine_threadsafe(queue.put({"pct": pct, "msg": msg}), loop)

    async def event_stream():
        _emit(5, "Reading documents..." if documents_override is None
                 else "Loading stored corpus...")

        def _run():
            from compliance.pipeline import run_compliance_pipeline
            outcome = run_compliance_pipeline(
                zip_bytes=zip_bytes,
                company_context=context,
                emitter=_emit,
                documents_override=documents_override,
            )
            if not outcome.get("success"):
                raise RuntimeError(outcome.get("error", "Pipeline failed"))
            return outcome

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = loop.run_in_executor(pool, _run)

            while not future.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.3)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

            while not queue.empty():
                event = queue.get_nowait()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            try:
                outcome = future.result()
                result = outcome["result"]
                result_dict = result.model_dump()
                context_dict = context.model_dump()

                try:
                    save_compliance_analysis(
                        analysis_id=result.analysis_id,
                        user_id=username,
                        result_json_str=json.dumps(result_dict),
                        context_json_str=json.dumps(context_dict),
                        evidence_yaml=outcome.get("evidence_yaml") or "",
                    )
                except Exception as db_err:
                    logger.warning(f"[Compliance] DB save failed (non-blocking): {db_err}")

                if on_success is not None:
                    try:
                        on_success(result, outcome)
                    except Exception as cb_err:
                        logger.warning(f"[Compliance] on_success callback failed (non-blocking): {cb_err}")

                done_event = {"done": True, "analysis_id": result.analysis_id, "result": result_dict}
                yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"[Compliance] {e}\n{traceback.format_exc()}")
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/compliance/analyses/{analysis_id}/reanalyse")
async def compliance_reanalyse(
    analysis_id: str,
    user: Dict = Depends(_get_current_user),
):
    """Fase 6 — rilancia l'analisi sul corpus salvato (fondamento PRD §1.4.3).

    Stessa base documentale, nuova run del motore → il Compare misura il
    progresso reale del sistema (o l'effetto di un motore aggiornato) senza
    ricaricare lo ZIP. Produce una NUOVA analysis_id; SSE come l'analyze.
    """
    from compliance.schemas import CompanyContext
    from modules.db_manager import load_analysis_corpus

    row = _require_analysis_access(analysis_id, user)

    docs = load_analysis_corpus(analysis_id)
    if not docs:
        raise HTTPException(
            status_code=409,
            detail=(
                "No stored corpus for this analysis (it predates corpus "
                "persistence). Upload the ZIP again to re-assess."
            ),
        )

    try:
        context = CompanyContext(**json.loads(row.get("company_context_json") or "{}"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not restore company context: {e}")

    return _pipeline_sse_response(
        context=context,
        username=user["username"],
        documents_override=docs,
    )


# ══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE — STORICO / DETTAGLIO / DOWNLOAD / ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/compliance/analyses")
async def list_compliance_analyses(
    limit: int = Query(50),
    user: Dict = Depends(_get_current_user),
):
    """Storico analisi compliance dell'utente autenticato."""
    from modules.db_manager import get_compliance_analyses
    analyses = get_compliance_analyses(user["username"], limit=limit)
    return analyses


@app.get("/api/compliance/analyses/{analysis_id}")
async def get_compliance_analysis_detail(
    analysis_id: str,
    user: Dict = Depends(_get_current_user),
):
    """Dettaglio completo di un'analisi (include result_json). Ownership-checked.

    Fase 4 — merge del registro NC nello snapshot: status / dismissed /
    dismiss_reason per clausola + lista delle NC manuali. Il result_json
    persistito resta immutabile; l'overlay vive solo nella risposta.
    """
    import json as _json
    from modules.db_manager import get_nonconformities

    row = _require_analysis_access(analysis_id, user)
    if row.get("result_json"):
        try:
            row["result"] = _json.loads(row["result_json"])
        except Exception:
            row["result"] = None

    try:
        ncs = get_nonconformities(analysis_id)
    except Exception as e:
        logger.warning(f"[NC register] lettura fallita per {analysis_id}: {e}")
        ncs = []

    by_clause = {nc["clause_id"]: nc for nc in ncs if nc.get("clause_id")}
    if row.get("result"):
        for norm in row["result"].get("norms", []):
            for clause in norm.get("clauses", []):
                nc = by_clause.get(clause.get("clause_id"))
                if nc:
                    clause["status"] = nc.get("status", "open")
                    clause["dismissed"] = bool(nc.get("dismissed"))
                    clause["dismiss_reason"] = nc.get("dismiss_reason") or None
                    clause["nc_id"] = nc.get("id")

    row["manual_nonconformities"] = [
        nc for nc in ncs if nc.get("source") == "manual"
    ]
    return row


@app.get("/api/compliance/analyses/{analysis_id}/download")
async def download_compliance_report(
    analysis_id: str,
    user: Dict = Depends(_get_current_user),
):
    """Genera e scarica il report DOCX per un'analisi compliance. Ownership-checked."""
    import json as _json
    from compliance.report_builder import build_docx_report
    from compliance.schemas import ComplianceAnalysisResult
    from modules.db_manager import get_nonconformities

    row = _require_analysis_access(analysis_id, user)

    try:
        result_data = _json.loads(row["result_json"]) if isinstance(row.get("result_json"), str) else row.get("result_json", {})
        result = ComplianceAnalysisResult(**result_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not parse analysis result: {e}")

    # Fase 4: il registro NC guida l'esclusione dei dismissed dalle sezioni
    # operative + l'appendice Set-aside + le NC manuali.
    try:
        register = get_nonconformities(analysis_id)
    except Exception:
        register = []

    try:
        docx_bytes = build_docx_report(result, register=register)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")

    safe_company = result.company.replace(" ", "_").replace("/", "-")[:30]
    filename = f"Amisys QHSE_GAP_Report_{safe_company}_{analysis_id[:8]}.docx"

    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 3.3 — Post-audit chat grounded on the analysis evidences
# ──────────────────────────────────────────────────────────────────────────────

class ChatTurnIn(BaseModel):
    role: str       # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    analysis_id: Optional[str] = None  # Sprint G.4: opzionale → chat "general" senza grounding
    query: str
    conversation_id: Optional[str] = None
    scope: Optional[str] = None         # "all" → analista onnisciente su TUTTE le analisi
    # Fase 6 — multi-turn: gli ultimi turni della conversazione (max 6 usati).
    # La history è CONTESTO conversazionale, mai fonte di evidenza.
    messages: Optional[List[ChatTurnIn]] = None


class ChatSource(BaseModel):
    evidence_id: str
    file_name: str
    excerpt: str
    iso_clause_primary: str
    relevance_score: float


class ChatResponse(BaseModel):
    analysis_id: Optional[str] = None       # echo of req.analysis_id; None per chat general
    response: str
    sources: List[ChatSource]


def _chat_history_block(messages) -> str:
    """Fase 6 — multi-turn: rende gli ultimi 6 turni come blocco di contesto.

    Regola comunicata anche al modello: la history serve a capire i pronomi e
    i riferimenti ("e per la 14001?"), NON è una fonte di evidenza citabile.
    """
    if not messages:
        return ""
    turns = [m for m in messages if m.role in ("user", "assistant") and m.content.strip()][-6:]
    if not turns:
        return ""
    lines = ["## Conversation so far (context only — never cite it as evidence)"]
    for m in turns:
        speaker = "Manager" if m.role == "user" else "Assistant"
        lines.append(f"{speaker}: {m.content.strip()[:500]}")
    return "\n".join(lines) + "\n\n## Current question\n"


def _call_chat_llm(sys_prompt: str, user_prompt: str, max_tokens: int = 800) -> str:
    """Helper chat: Azure-only (fallback Gemini rimosso, decisione utente
    2026-06-12). deep=True: la chat è user-facing e usa il profilo deep
    quando configurato. Gli errori propagano al chiamante → 502."""
    from v2.azure_openai_client_v2 import make_client
    client = make_client(deep=True)
    stream = client.chat_stream(
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=max_tokens,
    )
    chunks: List[str] = []
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if choices:
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta else None
            if content:
                chunks.append(content)
    return "".join(chunks).strip()


async def _chat_account_wide(req: "ChatRequest", user: Dict, history_block: str) -> "ChatResponse":
    """Analista onnisciente (scope='all'): aggrega le evidence card di TUTTE le
    analisi dell'utente + il registro NC con i documenti citati, indicizza e
    risponde citando azienda↔documento↔non-conformità. Ownership: solo le analisi
    dell'utente (admin vede tutto)."""
    from pathlib import Path as _Path
    import json as _json
    from compliance.schemas import ComplianceAnalysisResult
    from compliance.evidence_service import EvidenceService
    from compliance.gap_analyzer import _parse_evidence_yaml
    from modules.db_manager import get_connection

    username = user["username"]
    conn = get_connection()
    try:
        if user.get("role") == "admin":
            rows = conn.execute(
                "SELECT id, company, result_json, evidence_yaml FROM compliance_analyses "
                "ORDER BY analysis_date DESC LIMIT 25"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, company, result_json, evidence_yaml FROM compliance_analyses "
                "WHERE user_id = ? ORDER BY analysis_date DESC LIMIT 25", (username,)
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        return ChatResponse(analysis_id=None, sources=[], response=(
            "There are no analyses in your account yet, so I have no audit data to "
            "reason over. Run an analysis first, then ask me here."))

    MAX_CARDS = 800
    cards: List[Dict[str, Any]] = []
    summary_lines: List[str] = ["## Companies and analyses in scope"]
    nc_items: List[tuple] = []   # (sev_rank, company, clause_id, severity, finding, docs)
    sev_rank = {"MAJOR": 0, "MINOR": 1}

    for row in rows:
        company = str(row["company"] or "?")
        try:
            data = _json.loads(row["result_json"]) if isinstance(row["result_json"], str) else row["result_json"]
            result = ComplianceAnalysisResult(**data)
        except Exception:
            continue
        for n in result.norms:
            summary_lines.append(
                f"- {company} — {n.norm}: {n.major_count} MAJOR / {n.minor_count} MINOR / "
                f"{n.observation_count} OBS / {n.conformant_count} CONF, score {n.overall_score}"
            )
        ey = row["evidence_yaml"] or ""
        if ey.strip() and len(cards) < MAX_CARDS:
            try:
                for c in _parse_evidence_yaml(ey):
                    if not c.get("evidence_id"):
                        continue
                    c = dict(c)
                    c["evidence_id"] = f"{row['id']}::{c['evidence_id']}"
                    c["file_name"] = f"[{company}] {c.get('file_name', '')}"
                    cards.append(c)
                    if len(cards) >= MAX_CARDS:
                        break
            except Exception:
                pass
        for n in result.norms:
            for cl in n.clauses:
                if cl.severity in ("MAJOR", "MINOR"):
                    docs = ", ".join(sorted({s.file_name for s in (cl.sources or []) if s.file_name})) or "(no document cited)"
                    nc_items.append((sev_rank.get(cl.severity, 2), company, cl.clause_id,
                                     cl.severity, (cl.finding or "")[:160], docs))

    nc_items.sort(key=lambda x: x[0])
    nc_lines: List[str] = ["## Nonconformity register (open NCs across all analyses) — NC ↔ documents"]
    for _, comp, cid, sev, finding, docs in nc_items[:60]:
        nc_lines.append(f"- [{comp}] {cid} {sev}: {finding} — documents: {docs}")
    if len(nc_items) > 60:
        nc_lines.append(f"- … and {len(nc_items) - 60} more open NCs")

    retrieved: List[Dict[str, Any]] = []
    if cards:
        service = await asyncio.to_thread(EvidenceService.from_cards, f"account_{username}", cards)
        try:
            retrieved = await asyncio.to_thread(service.get_evidences_similar_to, req.query, 8)
        finally:
            try:
                service.close()
            except Exception:
                pass

    prompt_path = _Path(__file__).parent / "prompts" / "compliance" / "chat_account.md"
    try:
        sys_prompt = prompt_path.read_text(encoding="utf-8")
    except Exception:
        sys_prompt = ("You are the Amisys QHSE analyst with knowledge of ALL the user's "
                      "analyses. Cite documents and nonconformities; UK English; never invent.")

    evidence_lines = ["## Retrieved evidence (across all analyses)"]
    for ev in retrieved:
        evidence_lines.append("---")
        evidence_lines.append(f"file_name: {ev.get('file_name', '')}")
        evidence_lines.append(f"iso_clause_primary: {ev.get('iso_clause_primary', '')}")
        evidence_lines.append(f"excerpt: {str(ev.get('excerpt', ''))[:400]}")

    user_prompt = (
        "\n".join(summary_lines) + "\n\n"
        + "\n".join(nc_lines) + "\n\n"
        + "\n".join(evidence_lines) + "\n\n"
        + (history_block or "## User question\n") + req.query.strip()
    )
    try:
        response_text = await asyncio.to_thread(_call_chat_llm, sys_prompt, user_prompt, 1000)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider failed: {e}")

    sources_out = [ChatSource(
        evidence_id=str(ev.get("evidence_id", "")),
        file_name=str(ev.get("file_name", "")),
        excerpt=str(ev.get("excerpt", ""))[:300],
        iso_clause_primary=str(ev.get("iso_clause_primary", "")),
        relevance_score=float(1.0 - float(ev.get("distance", 0.5))),
    ) for ev in retrieved]
    return ChatResponse(analysis_id=None, response=response_text or "No response generated.",
                        sources=sources_out)


@app.post("/api/compliance/chat", response_model=ChatResponse)
async def compliance_chat(
    req: ChatRequest,
    user: Dict = Depends(_get_current_user),
):
    """
    Grounded post-audit chat (con analysis_id) o general advisory (senza).

    Modalità:
    - analysis_id valorizzato → carica ComplianceAnalysisResult dal DB,
      ricostruisce le evidence cards dalle citations, indexa in ChromaDB
      ephemeral, retrieva top-K per la query, prompt grounded.
    - analysis_id None        → no DB lookup, no ChromaDB, prompt
      "chat_general" advisory su ISO 9001/14001/45001 generic. Sources = [].

    Fase 6: il grounding usa l'evidence_yaml persistito (TUTTO il corpus) con
    fallback alle citations per le analisi pre-R1; il prompt include il
    catalogo corpus (smart searching, PRD §1.3.12) e la history multi-turn.
    """
    from pathlib import Path as _Path

    history_block = _chat_history_block(req.messages)

    # ─── Branch account-wide (analista onnisciente su TUTTE le analisi) ──
    if (req.scope or "").strip().lower() == "all":
        return await _chat_account_wide(req, user, history_block)

    # ─── Branch general (no grounding) ──────────────────────────────────
    if req.analysis_id is None or req.analysis_id.strip() == "":
        chat_prompt_path = _Path(__file__).parent / "prompts" / "compliance" / "chat_general.md"
        try:
            sys_prompt = chat_prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"chat_general.md missing: {e}")
        user_prompt = history_block + req.query.strip()
        try:
            # Sprint R1: off-thread — the LLM call is sync and would block the
            # event loop (freezing concurrent SSE analysis streams).
            response_text = await asyncio.to_thread(
                _call_chat_llm, sys_prompt, user_prompt, 900,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM provider failed: {e}")
        if not response_text:
            response_text = "No response could be generated for this query."
        return ChatResponse(analysis_id=None, response=response_text, sources=[])

    # ─── Branch grounded (analysis_id presente) ─────────────────────────
    import json as _json
    from compliance.schemas import ComplianceAnalysisResult
    from compliance.evidence_service import EvidenceService
    from compliance.context_intake import build_context_prompt_block

    # 1) Load the persisted analysis (Fase 3: ownership-checked)
    row = _require_analysis_access(req.analysis_id, user)
    try:
        result_data = _json.loads(row["result_json"]) if isinstance(row.get("result_json"), str) else row.get("result_json", {})
        result = ComplianceAnalysisResult(**result_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not parse analysis result: {e}")

    # 2) Build evidence cards for grounding.
    # Sprint R1: prefer the persisted full Phase 2 evidence YAML — it covers
    # ALL analysed documents, not only those cited in a gap. Older analyses
    # (pre-R1) have no evidence_yaml; fall back to reconstructing cards from
    # the citations in the result (legacy behaviour, truthful but narrower).
    cards: List[Dict[str, Any]] = []
    evidence_yaml = row.get("evidence_yaml") or ""
    if evidence_yaml.strip():
        try:
            from compliance.gap_analyzer import _parse_evidence_yaml
            cards = [
                c for c in _parse_evidence_yaml(evidence_yaml)
                if c.get("evidence_id")
            ]
        except Exception as e:
            logging.getLogger("compliance.chat").warning(
                "[Compliance chat] evidence_yaml parse failed for %s: %s — "
                "falling back to citation reconstruction", req.analysis_id, e,
            )
            cards = []

    if not cards:
        # Legacy path: reconstruct from citations (TraceabilityLink) only.
        # Sprint H.2: defensively coerce every value to a serialisable
        # primitive so ChromaDB's metadata validation cannot crash the request.
        seen_ids: set = set()
        for norm in result.norms:
            for clause in norm.clauses:
                for src in clause.sources:
                    eid = str(src.evidence_id or "")
                    if not eid or eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    verbatim = str(src.excerpt or "")
                    # Prefer src.summary (Sprint H.1) for the descriptive blob
                    # the embedder uses as searchable text.
                    descriptive = str(getattr(src, "summary", None) or verbatim)
                    cards.append({
                        "evidence_id":        eid,
                        "file_name":          str(src.file_name or ""),
                        "doc_type":           "other",
                        "iso_clause_primary": str(clause.clause_id or ""),
                        "gap_signal":         bool(clause.severity in ("MAJOR", "MINOR")),
                        "confidence":         0.5,
                        "summary":            descriptive,
                        "gap_detail":         "",
                        "excerpts":           [{"text": verbatim, "pages": list(src.pages or [])}],
                    })

    if not cards:
        # No citations available — reply truthfully without calling the LLM
        return ChatResponse(
            analysis_id=req.analysis_id,
            response=(
                "This audit did not surface any evidence citations, so there is no "
                "document content this chat can ground its answers on. Re-run the "
                "analysis with a different document set if you want to chat with the "
                "evidence."
            ),
            sources=[],
        )

    # 3) Index in-process and retrieve top-K for the query.
    # Sprint H.2: wrap with explicit logging — prior to this, a silent crash in
    # from_cards or get_evidences_similar_to surfaced as a generic 500 with no
    # stack trace in the uvicorn log, making the failure mode invisible.
    import traceback as _tb
    _chat_log = logging.getLogger("compliance.chat")
    try:
        # Sprint R1: indexing is CPU/embedding-heavy and sync — run off-thread
        # so concurrent SSE pipelines don't freeze while a chat indexes.
        service = await asyncio.to_thread(
            EvidenceService.from_cards, req.analysis_id, cards,
        )
    except Exception as e:
        _chat_log.error(
            "[Compliance chat] EvidenceService.from_cards failed for analysis %s "
            "(cards=%d): %s\n%s",
            req.analysis_id, len(cards), e, _tb.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Could not index evidence for chat: {str(e)[:200]}",
        )

    try:
        try:
            retrieved = await asyncio.to_thread(
                service.get_evidences_similar_to, req.query, 6,
            )
        except Exception as e:
            _chat_log.error(
                "[Compliance chat] retrieval failed for analysis %s on query %r: %s\n%s",
                req.analysis_id, req.query[:120], e, _tb.format_exc(),
            )
            raise HTTPException(
                status_code=500,
                detail=f"Retrieval failed: {str(e)[:200]}",
            )

        # 4) Build prompt
        chat_prompt_path = _Path(__file__).parent / "prompts" / "compliance" / "chat_grounded.md"
        try:
            sys_prompt = chat_prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Chat prompt missing: {e}")
        context_block = build_context_prompt_block(result.context)
        sys_prompt = sys_prompt.replace("{company_context}", context_block)

        # Compose compact analysis summary for the LLM
        summary_lines: List[str] = [
            f"Analysis ID: {result.analysis_id}",
            f"Company: {result.company}",
            f"Documents analysed: {result.documents_analyzed}",
            "",
            "## Norms and severity counts",
        ]
        for n in result.norms:
            summary_lines.append(
                f"- {n.norm}: {n.major_count} MAJOR / {n.minor_count} MINOR / "
                f"{n.observation_count} OBSERVATION / {n.conformant_count} CONFORMANT, "
                f"SPoF={n.spof_count}, overall score={n.overall_score}"
            )
        summary_lines.append("")
        summary_lines.append("## Top 5 priority gaps")
        for g in (result.top_gaps or [])[:5]:
            summary_lines.append(f"- [{g.clause_id}] {g.severity}: {g.finding[:200]}")

        if result.expiry_report:
            summary_lines.append("")
            summary_lines.append(
                f"## Expiry status (as of {result.expiry_report.audit_date})"
            )
            for d in result.expiry_report.expired_documents[:10]:
                summary_lines.append(
                    f"- EXPIRED {d.days_overdue}d ago [{d.severity}]: {d.file_name}"
                )
            for d in result.expiry_report.expiring_soon[:5]:
                summary_lines.append(
                    f"- Expiring in {abs(d.days_overdue)}d [{d.severity}]: {d.file_name}"
                )

        evidence_lines: List[str] = ["## Retrieved evidence cards"]
        for ev in retrieved:
            evidence_lines.append("---")
            evidence_lines.append(f"evidence_id: {ev.get('evidence_id','')}")
            evidence_lines.append(f"file_name: {ev.get('file_name','')}")
            evidence_lines.append(f"iso_clause_primary: {ev.get('iso_clause_primary','')}")
            evidence_lines.append(f"gap_signal: {ev.get('gap_signal', False)}")
            evidence_lines.append(f"excerpt: {str(ev.get('excerpt',''))[:500]}")

        # Fase 6 — catalogo corpus (smart searching, PRD §1.3.12): UNA riga per
        # OGNI documento analizzato (nome, tipo, sintesi). È ciò che rende
        # rispondibile "find me all the risk assessments" per intero, non solo
        # sui top-6 del retrieval. Cap difensivo a 150 documenti.
        catalogue_lines: List[str] = [
            "## Corpus catalogue (every analysed document — name | type | summary)"
        ]
        for card in cards[:150]:
            fname = str(card.get("file_name", "") or "")
            dtype = str(card.get("doc_type", "other") or "other")
            summ = str(card.get("summary", "") or "").replace("\n", " ")[:140]
            catalogue_lines.append(f"- {fname} | {dtype} | {summ}")

        user_prompt = (
            "## compliance_analysis_summary\n"
            + "\n".join(summary_lines)
            + "\n\n"
            + "\n".join(catalogue_lines)
            + "\n\n"
            + "\n".join(evidence_lines)
            + "\n\n"
            + (history_block or "## User question\n")
            + req.query.strip()
        )

        # 5) Call LLM via shared helper (Azure-only)
        try:
            response_text = await asyncio.to_thread(
                _call_chat_llm, sys_prompt, user_prompt, 800,
            )
        except Exception as e:
            _chat_log.error(
                "[Compliance chat] LLM call failed for analysis %s: %s\n%s",
                req.analysis_id, e, _tb.format_exc(),
            )
            raise HTTPException(status_code=502, detail=f"Both LLM providers failed: {e}")

        if not response_text:
            response_text = "No response could be generated for this query."

        # 6) Hydrate sources from the retrieved set
        sources_out: List[ChatSource] = []
        for ev in retrieved:
            sources_out.append(ChatSource(
                evidence_id=str(ev.get("evidence_id", "")),
                file_name=str(ev.get("file_name", "")),
                excerpt=str(ev.get("excerpt", ""))[:300],
                iso_clause_primary=str(ev.get("iso_clause_primary", "")),
                relevance_score=float(1.0 - float(ev.get("distance", 0.5))),
            ))

        return ChatResponse(
            analysis_id=req.analysis_id,
            response=response_text,
            sources=sources_out,
        )
    finally:
        try:
            service.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Fase H — PQQ / SQ assistant (PRD §1.6.9)
# ──────────────────────────────────────────────────────────────────────────────

class PqqRequest(BaseModel):
    analysis_id: str
    questions: List[str]


class PqqAnswer(BaseModel):
    question: str
    answer: str
    status: str                 # 'answered' | 'needs_input'
    sources: List[ChatSource]


class PqqExportItem(BaseModel):
    question: str
    answer: str
    status: str = "answered"


class PqqExportRequest(BaseModel):
    company: str = ""
    items: List[PqqExportItem]


def _build_grounding_cards(row: Dict, result) -> List[Dict[str, Any]]:
    """Estrae le evidence card per il grounding dall'evidence_yaml persistito.
    (PQQ richiede analisi recenti con evidence_yaml; niente fallback legacy.)"""
    cards: List[Dict[str, Any]] = []
    evidence_yaml = row.get("evidence_yaml") or ""
    if evidence_yaml.strip():
        try:
            from compliance.gap_analyzer import _parse_evidence_yaml
            cards = [c for c in _parse_evidence_yaml(evidence_yaml) if c.get("evidence_id")]
        except Exception:
            cards = []
    return cards


@app.post("/api/compliance/pqq")
async def compliance_pqq(req: PqqRequest, user: Dict = Depends(_get_current_user)):
    """Risponde a una lista di domande PQQ/SQ grounded sull'evidenza
    dell'analisi indicata. Ogni risposta è una BOZZA con citazioni; dove
    l'evidenza non copre, la risposta è 'needs_input' (mai inventare)."""
    import json as _json
    from compliance.schemas import ComplianceAnalysisResult
    from compliance.evidence_service import EvidenceService
    from pathlib import Path as _Path

    if not req.questions:
        raise HTTPException(status_code=422, detail="At least one question is required")

    row = _require_analysis_access(req.analysis_id, user)
    try:
        result_data = _json.loads(row["result_json"]) if isinstance(row.get("result_json"), str) else row.get("result_json", {})
        result = ComplianceAnalysisResult(**result_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not parse analysis result: {e}")

    cards = _build_grounding_cards(row, result)
    if not cards:
        raise HTTPException(
            status_code=409,
            detail="This analysis has no indexed evidence to ground tender answers on.",
        )

    try:
        sys_prompt = (_Path(__file__).parent / "prompts" / "compliance" / "pqq_answer.md").read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pqq_answer.md missing: {e}")
    from compliance.context_intake import build_context_prompt_block
    sys_prompt = sys_prompt.replace("{company_context}", build_context_prompt_block(result.context))

    service = await asyncio.to_thread(EvidenceService.from_cards, req.analysis_id, cards)
    answers: List[PqqAnswer] = []
    try:
        for q in req.questions[:50]:
            q = q.strip()
            if not q:
                continue
            retrieved = await asyncio.to_thread(service.get_evidences_similar_to, q, 6)
            ev_lines = ["## Retrieved evidence"]
            for ev in retrieved:
                ev_lines.append(f"- [{ev.get('file_name','')}] {str(ev.get('excerpt',''))[:400]}")
            user_prompt = "\n".join(ev_lines) + f"\n\n## Tender question\n{q}"
            try:
                ans = await asyncio.to_thread(_call_chat_llm, sys_prompt, user_prompt, 600)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"LLM provider failed: {e}")
            status = "needs_input" if ans.strip().upper().startswith("NEEDS INPUT") else "answered"
            sources_out = [
                ChatSource(
                    evidence_id=str(ev.get("evidence_id", "")),
                    file_name=str(ev.get("file_name", "")),
                    excerpt=str(ev.get("excerpt", ""))[:300],
                    iso_clause_primary=str(ev.get("iso_clause_primary", "")),
                    relevance_score=float(1.0 - float(ev.get("distance", 0.5))),
                )
                for ev in retrieved[:3]
            ]
            answers.append(PqqAnswer(question=q, answer=ans or "No draft could be generated.",
                                     status=status, sources=sources_out))
    finally:
        try:
            service.close()
        except Exception:
            pass

    _audit(user, "pqq_draft", "analysis", req.analysis_id, {"questions": len(answers)})
    return {"analysis_id": req.analysis_id, "answers": [a.model_dump() for a in answers]}


@app.post("/api/compliance/pqq/export")
async def compliance_pqq_export(req: PqqExportRequest, user: Dict = Depends(_get_current_user)):
    """Esporta le risposte PQQ come DOCX con disclaimer 'Draft for review'."""
    from compliance.report_builder import build_pqq_docx
    docx = build_pqq_docx(req.company, [i.model_dump() for i in req.items])
    safe = "".join(c for c in (req.company or "tender") if c.isalnum() or c in " -_")[:40].strip() or "tender"
    return StreamingResponse(
        __import__("io").BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="PQQ_draft_{safe}.docx"'},
    )


@app.patch("/api/compliance/analyses/{analysis_id}/actions/{clause_id}")
async def update_ncr_action(
    analysis_id: str,
    clause_id: str,
    body: Dict = Body(...),
    user: Dict = Depends(_get_current_user),
):
    """Aggiorna status NCR: open / in_progress / closed. Ownership-checked."""
    from modules.db_manager import update_ncr_status
    _require_analysis_access(analysis_id, user)
    status = body.get("status", "open")
    notes = body.get("notes", "")
    if status not in ("open", "in_progress", "closed"):
        raise HTTPException(status_code=422, detail="status must be open / in_progress / closed")
    update_ncr_status(analysis_id, clause_id, status, notes)
    _audit(user, "nc_status_update", "clause", f"{analysis_id}/{clause_id}", {"status": status})
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Fase 5 — Delta / Compare (PRODUCT.md aha moment #3, PRD §2.7 uso ricorrente)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/compliance/analyses/{analysis_id}/delta")
async def get_analysis_delta(
    analysis_id: str,
    against: str = Query(..., description="analysis_id della run precedente"),
    user: Dict = Depends(_get_current_user),
):
    """Confronto fra due analisi (nuova = path param, vecchia = ?against=).

    Ownership-checked su ENTRAMBE le analisi. Ritorna per-clausola:
    improved / regressed / unchanged / new / removed, overall per norma,
    delta del documented-info coverage e contatori di sintesi.
    """
    from compliance.delta_engine import compare_analyses

    _require_analysis_access(analysis_id, user)
    _require_analysis_access(against, user)

    delta = compare_analyses(analysis_id, against)
    if "error" in delta:
        raise HTTPException(status_code=404, detail=delta["error"])
    return delta


# ──────────────────────────────────────────────────────────────────────────────
# Fase 4 — Registro nonconformità (PRD §1.4.8): NC manuali + dismiss/restore
# ──────────────────────────────────────────────────────────────────────────────

class ManualNCRequest(BaseModel):
    title: str
    description: str = ""
    severity: str = "MINOR"   # MAJOR | MINOR | OBSERVATION


class DismissRequest(BaseModel):
    reason: str               # obbligatoria: mai cancellazioni silenziose


@app.post("/api/compliance/analyses/{analysis_id}/nonconformities")
async def add_manual_nc(
    analysis_id: str,
    body: ManualNCRequest,
    user: Dict = Depends(_get_current_user),
):
    """NC inserita a mano dal manager (PRD §1.4.8). Ownership-checked."""
    from modules.db_manager import add_manual_nonconformity
    _require_analysis_access(analysis_id, user)
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title is required")
    if body.severity not in ("MAJOR", "MINOR", "OBSERVATION"):
        raise HTTPException(status_code=422, detail="severity must be MAJOR / MINOR / OBSERVATION")
    nc_id = add_manual_nonconformity(
        analysis_id=analysis_id,
        title=body.title.strip(),
        description=body.description.strip(),
        severity=body.severity,
        created_by=user.get("username", ""),
    )
    _audit(user, "nc_manual_add", "nonconformity", f"{analysis_id}/{nc_id}",
           {"title": body.title.strip(), "severity": body.severity})
    return {"ok": True, "nc_id": nc_id}


@app.post("/api/compliance/analyses/{analysis_id}/nonconformities/{nc_id}/dismiss")
async def dismiss_nc(
    analysis_id: str,
    nc_id: int,
    body: DismissRequest,
    user: Dict = Depends(_get_current_user),
):
    """Mette da parte una NC con motivazione obbligatoria (PRD: 'bin findings').

    Il record non viene mai cancellato: resta nel registro con reason e autore,
    e nel report DOCX finisce nell'appendice 'Set-aside findings'.
    """
    from modules.db_manager import set_nonconformity_dismissed
    _require_analysis_access(analysis_id, user)
    if not body.reason.strip():
        raise HTTPException(status_code=422, detail="a dismiss reason is required")
    ok = set_nonconformity_dismissed(
        nc_id, analysis_id, dismissed=True,
        reason=body.reason.strip(), by=user.get("username", ""),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Nonconformity not found in this analysis")
    _audit(user, "nc_dismiss", "nonconformity", f"{analysis_id}/{nc_id}",
           {"reason": body.reason.strip()})
    return {"ok": True}


@app.post("/api/compliance/analyses/{analysis_id}/nonconformities/{nc_id}/restore")
async def restore_nc(
    analysis_id: str,
    nc_id: int,
    user: Dict = Depends(_get_current_user),
):
    """Ripristina una NC precedentemente messa da parte."""
    from modules.db_manager import set_nonconformity_dismissed
    _require_analysis_access(analysis_id, user)
    ok = set_nonconformity_dismissed(nc_id, analysis_id, dismissed=False)
    if not ok:
        raise HTTPException(status_code=404, detail="Nonconformity not found in this analysis")
    _audit(user, "nc_restore", "nonconformity", f"{analysis_id}/{nc_id}")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Fase B — Audit trail (PRD §4.3.10): sola lettura, admin-only
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/audit-log")
async def read_audit_log(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    target_user: Optional[str] = Query(None, description="filtra per username attore"),
    user: Dict = Depends(_get_current_user),
):
    """Registro append-only delle azioni mutanti. Solo admin (privacy: traccia
    chi ha fatto cosa). Non filtrabile per ownership: è uno strumento di
    governance, non di self-service."""
    if str(user.get("role") or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Audit log is restricted to administrators")
    from modules.audit_log import get_audit_log, count_audit_log
    rows = get_audit_log(limit=limit, offset=offset, username=target_user,
                         entity_type=entity_type, action=action)
    total = count_audit_log(username=target_user, entity_type=entity_type, action=action)
    return {"entries": rows, "total": total, "limit": limit, "offset": offset}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  Amisys QHSE API SERVER")
    print(f"  Azure OpenAI: {'OK' if os.environ.get('AZURE_OPENAI_API_KEY', '').strip() else 'MISSING'}")
    print(f"  Azure DI OCR: {'OK' if os.environ.get('AZURE_DI_KEY', '').strip() else 'MISSING'}")
    print("=" * 60)
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
