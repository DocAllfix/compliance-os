"""
Modulo Database Manager per Amisys QHSE
Gestisce storico pratiche, logging e persistenza dati
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# Path del database
DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "audit.db"

# Assicura che la directory esista
DATA_DIR.mkdir(exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Ottiene una connessione al database.

    Fase B: WAL mode — il DMS e lo scheduler scrivono accanto alle richieste
    web; WAL consente letture concorrenti durante una scrittura ed è più
    robusto contro 'database is locked'. PRAGMA idempotente, persistente sul
    file DB (basta impostarlo una volta, ma è innocuo ripeterlo).
    """
    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except sqlite3.OperationalError:
        pass  # in-memory o filesystem che non supporta WAL — degrada al default
    return conn


def init_database():
    """Inizializza il database con le tabelle necessarie."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabella pratiche
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pratiche (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            tipo TEXT CHECK(tipo IN ('report','checklist_json','checklist_word')) NOT NULL,
            azienda TEXT,
            norma TEXT,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_output_path TEXT,
            file_input_path TEXT,
            file_output_name TEXT,
            file_size INTEGER DEFAULT 0,
            processing_time_seconds REAL DEFAULT 0,
            status TEXT DEFAULT 'completato',
            note TEXT
        )
    """)
    
    # Tabella activity log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabella error_log - Traccia errori per admin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            azienda TEXT,
            error_type TEXT,
            error_message TEXT,
            stack_trace TEXT,
            tab_source TEXT,
            file_involved TEXT,
            pratica_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved INTEGER DEFAULT 0
        )
    """)
    
    # Indici per performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_user ON pratiche(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_date ON pratiche(data_creazione DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_tipo ON pratiche(tipo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pratiche_norma ON pratiche(norma)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_user ON error_log(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_date ON error_log(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_type ON error_log(error_type)")

    # Migrazione R-4: nuove colonne error_log (idempotente — try/except su ogni ALTER)
    migration_cols = [
        ("batch_index",      "INTEGER DEFAULT -1"),
        ("docs_involved",    "TEXT"),
        ("error_subtype",    "TEXT"),
        ("auto_recovered",   "INTEGER DEFAULT 0"),
        ("recovery_details", "TEXT"),
        ("resolved_by",      "TEXT"),
        ("resolved_at",      "TIMESTAMP"),
    ]
    for col_name, col_def in migration_cols:
        try:
            cursor.execute(f"ALTER TABLE error_log ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass  # Colonna già esistente — ignorare

    # Indice su error_subtype per dashboard aggregati
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_subtype ON error_log(error_subtype)")

    conn.commit()
    conn.close()


def init_compliance_tables():
    """Inizializza le tabelle Amisys QHSE (idempotente — CREATE IF NOT EXISTS)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compliance_analyses (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            company TEXT,
            norms TEXT,
            sector TEXT,
            employee_range TEXT,
            certified TEXT,
            sites_count TEXT,
            company_context_json TEXT,
            analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            overall_score INTEGER,
            major_count INTEGER,
            minor_count INTEGER,
            observation_count INTEGER,
            conformant_count INTEGER,
            spof_count INTEGER,
            documents_analyzed INTEGER,
            result_json TEXT,
            docx_filename TEXT,
            status TEXT DEFAULT 'completed'
        )
    """)

    # Fase 4 consolidamento (PRD §1.4.8) — registro NC first-class.
    # Sostituisce ncr_actions (che non aveva UNIQUE: ogni update inseriva una
    # riga duplicata e severity/is_spof restavano sempre vuoti).
    # Il result Pydantic resta uno snapshot immutabile; questo registro è
    # l'overlay persistente (status, dismiss con motivazione, NC manuali)
    # che viene fuso in lettura.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nonconformities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id TEXT NOT NULL REFERENCES compliance_analyses(id),
            clause_id TEXT,                          -- NULL per NC manuali
            source TEXT NOT NULL DEFAULT 'engine',   -- 'engine' | 'manual'
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            severity TEXT DEFAULT '',
            is_spof INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open',              -- open | in_progress | closed
            dismissed INTEGER DEFAULT 0,
            dismiss_reason TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # UNIQUE parziale: una sola riga engine per (analysis_id, clause_id);
    # le NC manuali (clause_id NULL) possono essere multiple.
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_nc_analysis_clause
        ON nonconformities(analysis_id, clause_id)
        WHERE clause_id IS NOT NULL
    """)

    _migrate_ncr_actions(cursor)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compliance_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id TEXT REFERENCES compliance_analyses(id),
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Fase 6 consolidamento — corpus persistito: i testi estratti in Phase 1
    # vengono salvati su filesystem (backend/data/corpus/{analysis_id}/) e
    # indicizzati qui. Abilita il re-analyse (scan ripetibile, fondamento di
    # PRD §1.4.3) e il Compare su base documentale identica.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id TEXT NOT NULL REFERENCES compliance_analyses(id),
            filename TEXT NOT NULL,
            chars INTEGER DEFAULT 0,
            path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ad_analysis ON analysis_documents(analysis_id)")

    # Fase D — provenance DMS: quale documento/versione del DMS ha alimentato
    # questa analisi (abilita "compara v3 vs v5 della procedura"). ALTER idempotente.
    for _col, _def in (("dms_document_id", "INTEGER"), ("dms_version", "INTEGER")):
        try:
            cursor.execute(f"ALTER TABLE analysis_documents ADD COLUMN {_col} {_def}")
        except sqlite3.OperationalError:
            pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ca_user ON compliance_analyses(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ca_date ON compliance_analyses(analysis_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nc_analysis ON nonconformities(analysis_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_analysis ON compliance_chat(analysis_id)")

    # Sprint R1 — persist the full Phase 2 evidence YAML alongside the result.
    # Enables: grounded chat over ALL documents (not only cited ones), delta
    # comparison on evidence, and future re-scan scoping. Idempotent ALTER.
    try:
        cursor.execute("ALTER TABLE compliance_analyses ADD COLUMN evidence_yaml TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Fase B — audit trail append-only. Creata qui (db_manager possiede lo
    # schema) per evitare la dipendenza circolare con audit_log.py.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            username    TEXT NOT NULL,
            action      TEXT NOT NULL,
            entity_type TEXT,
            entity_id   TEXT,
            detail      TEXT,
            ip_address  TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id)")

    conn.commit()
    conn.close()


# ==============================================================================
# FUNZIONI COMPLIANCE ANALYSES
# ==============================================================================

def save_compliance_analysis(analysis_id: str, user_id: str, result_json_str: str,
                              context_json_str: str, docx_filename: str = "",
                              evidence_yaml: str = "") -> None:
    """Salva il risultato di un'analisi compliance nel DB.

    Sprint R1: `evidence_yaml` persiste l'output integrale di Phase 2 così la
    chat grounded e il delta possono vedere TUTTI i documenti, non solo quelli
    citati in almeno un gap.
    """
    import json as _json
    ctx = _json.loads(context_json_str)
    result = _json.loads(result_json_str)

    major = sum(r.get("major_count", 0) for r in result.get("norms", []))
    minor = sum(r.get("minor_count", 0) for r in result.get("norms", []))
    obs   = sum(r.get("observation_count", 0) for r in result.get("norms", []))
    conf  = sum(r.get("conformant_count", 0) for r in result.get("norms", []))
    spof  = sum(r.get("spof_count", 0) for r in result.get("norms", []))
    scores = [r.get("overall_score", 0) for r in result.get("norms", [])]
    overall = int(sum(scores) / len(scores)) if scores else 0

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO compliance_analyses
        (id, user_id, company, norms, sector, employee_range, certified, sites_count,
         company_context_json, overall_score, major_count, minor_count, observation_count,
         conformant_count, spof_count, documents_analyzed, result_json, docx_filename,
         evidence_yaml)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        analysis_id, user_id,
        result.get("company", ""),
        _json.dumps(ctx.get("norms", [])),
        ctx.get("sector", ""), ctx.get("employee_range", ""),
        ctx.get("certified", ""), ctx.get("sites_count", ""),
        context_json_str, overall, major, minor, obs, conf, spof,
        result.get("documents_analyzed", 0), result_json_str, docx_filename,
        evidence_yaml or "",
    ))
    conn.commit()
    conn.close()

    # Fase 4 — popola/aggiorna il registro NC con i finding engine MAJOR/MINOR
    # (non blocca mai il salvataggio dell'analisi).
    try:
        sync_engine_nonconformities(analysis_id, result)
    except Exception as e:
        print(f"[DB] sync registro NC fallito (non bloccante): {e}")


def get_compliance_analyses(user_id: str, limit: int = 50) -> List[Dict]:
    """Recupera lo storico analisi di un utente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, company, norms, sector, employee_range, analysis_date,
               overall_score, major_count, minor_count, observation_count,
               conformant_count, spof_count, documents_analyzed, status, docx_filename
        FROM compliance_analyses
        WHERE user_id = ?
        ORDER BY analysis_date DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_compliance_analysis(analysis_id: str) -> Optional[Dict]:
    """Recupera un'analisi completa per ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM compliance_analyses WHERE id = ?", (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _migrate_ncr_actions(cursor) -> None:
    """Migrazione idempotente Fase 4: ncr_actions → nonconformities.

    La vecchia tabella non aveva UNIQUE, quindi accumulava righe duplicate per
    (analysis_id, clause_id): si tiene la più recente (updated_at massimo).
    Dopo la copia la tabella legacy viene eliminata.
    """
    try:
        exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ncr_actions'"
        ).fetchone()
        if not exists:
            return
        cursor.execute("""
            INSERT OR IGNORE INTO nonconformities
                (analysis_id, clause_id, source, severity, is_spof,
                 status, notes, updated_at)
            SELECT analysis_id, clause_id, 'engine',
                   COALESCE(severity, ''), COALESCE(is_spof, 0),
                   COALESCE(status, 'open'), COALESCE(notes, ''), updated_at
            FROM ncr_actions a
            WHERE a.clause_id IS NOT NULL
              AND a.updated_at = (
                  SELECT MAX(b.updated_at) FROM ncr_actions b
                  WHERE b.analysis_id = a.analysis_id
                    AND b.clause_id = a.clause_id
              )
        """)
        migrated = cursor.execute("SELECT changes()").fetchone()[0]
        cursor.execute("DROP TABLE ncr_actions")
        if migrated:
            print(f"[DB] Migrazione ncr_actions → nonconformities: {migrated} righe (dedup)")
    except sqlite3.OperationalError as e:
        print(f"[DB] Migrazione ncr_actions saltata: {e}")


# ==============================================================================
# CORPUS PERSISTITO (Fase 6 — fondamento di PRD §1.4.3)
# ==============================================================================

CORPUS_DIR = DATA_DIR / "corpus"


def save_analysis_corpus(analysis_id: str, documents: List[Dict]) -> int:
    """Salva i testi estratti (Phase 1) su filesystem + indice su DB.

    Un .txt per documento (page markers inclusi) in
    data/corpus/{analysis_id}/NNN.txt — il nome file originale vive solo nel
    DB, così niente sanitizzazione fragile dei path.
    """
    folder = CORPUS_DIR / analysis_id
    folder.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analysis_documents WHERE analysis_id = ?", (analysis_id,))
    saved = 0
    for i, doc in enumerate(documents):
        fname = str(doc.get("filename", "") or f"document_{i}")
        content = str(doc.get("content", "") or "")
        if not content.strip():
            continue
        path = folder / f"{i:03d}.txt"
        path.write_text(content, encoding="utf-8")
        # Fase D — provenance DMS (presente solo per analyze-dms; None per ZIP)
        cursor.execute(
            "INSERT INTO analysis_documents (analysis_id, filename, chars, path, "
            "dms_document_id, dms_version) VALUES (?, ?, ?, ?, ?, ?)",
            (analysis_id, fname, len(content), str(path),
             doc.get("document_id"), doc.get("version")),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def load_analysis_corpus(analysis_id: str) -> List[Dict]:
    """Ricostruisce la lista Phase-1 {filename, content, [document_id, version]}
    dal corpus salvato. La provenance DMS (se presente) viene riportata così il
    re-analyse la conserva."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT filename, path, dms_document_id, dms_version "
        "FROM analysis_documents WHERE analysis_id = ? ORDER BY id",
        (analysis_id,),
    ).fetchall()
    conn.close()

    docs: List[Dict] = []
    for r in rows:
        try:
            content = Path(r["path"]).read_text(encoding="utf-8")
        except Exception:
            continue
        doc: Dict = {"filename": r["filename"], "content": content}
        if r["dms_document_id"] is not None:
            doc["document_id"] = r["dms_document_id"]
            doc["version"] = r["dms_version"]
        docs.append(doc)
    return docs


# ==============================================================================
# REGISTRO NONCONFORMITÀ (Fase 4 — PRD §1.4.8)
# ==============================================================================

def sync_engine_nonconformities(analysis_id: str, result: Dict) -> int:
    """Upsert delle NC engine dal result appena salvato.

    Una riga per ogni ClauseGap MAJOR/MINOR. In caso di conflitto aggiorna i
    campi derivati dal motore (severity, is_spof, title) ma NON tocca lo stato
    gestito dall'utente (status, dismissed, dismiss_reason, notes).
    """
    conn = get_connection()
    cursor = conn.cursor()
    count = 0
    for norm in (result.get("norms") or []):
        for clause in (norm.get("clauses") or []):
            severity = str(clause.get("severity", ""))
            if severity not in ("MAJOR", "MINOR"):
                continue
            cursor.execute("""
                INSERT INTO nonconformities
                    (analysis_id, clause_id, source, title, description,
                     severity, is_spof, status)
                VALUES (?, ?, 'engine', ?, ?, ?, ?, 'open')
                ON CONFLICT(analysis_id, clause_id) WHERE clause_id IS NOT NULL
                DO UPDATE SET
                    severity = excluded.severity,
                    is_spof = excluded.is_spof,
                    title = excluded.title,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                analysis_id,
                str(clause.get("clause_id", "")),
                str(clause.get("clause_title", ""))[:200],
                str(clause.get("finding", ""))[:500],
                severity,
                1 if clause.get("is_spof") else 0,
            ))
            count += 1
    conn.commit()
    conn.close()
    return count


def get_nonconformities(analysis_id: str) -> List[Dict]:
    """Tutte le NC (engine + manuali) di un'analisi."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM nonconformities WHERE analysis_id = ? ORDER BY id",
        (analysis_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_ncr_status(analysis_id: str, clause_id: str, status: str,
                       notes: str = "") -> bool:
    """Aggiorna lo status di una NC engine (open/in_progress/closed).

    Fase 4: upsert reale sul registro (l'UNIQUE parziale rende l'ON CONFLICT
    effettivo — la vecchia ncr_actions duplicava una riga a ogni click).
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO nonconformities (analysis_id, clause_id, source, status, notes)
        VALUES (?, ?, 'engine', ?, ?)
        ON CONFLICT(analysis_id, clause_id) WHERE clause_id IS NOT NULL
        DO UPDATE SET status = excluded.status,
                      notes = excluded.notes,
                      updated_at = CURRENT_TIMESTAMP
    """, (analysis_id, clause_id, status, notes))
    conn.commit()
    conn.close()
    return True


def add_manual_nonconformity(analysis_id: str, title: str, description: str,
                              severity: str, created_by: str = "") -> int:
    """NC inserita a mano dal manager (PRD §1.4.8: 'manually add-in their own')."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO nonconformities
            (analysis_id, clause_id, source, title, description, severity, created_by)
        VALUES (?, NULL, 'manual', ?, ?, ?, ?)
    """, (analysis_id, title[:200], description[:1000], severity, created_by))
    nc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return int(nc_id)


def set_nonconformity_dismissed(nc_id: int, analysis_id: str, dismissed: bool,
                                 reason: str = "", by: str = "") -> bool:
    """Dismiss/restore di una NC (PRD §1.4.8 'bin/hide findings').

    Mai cancellazione: il record resta con motivazione e autore — trasparenza
    difendibile. Il filtro su analysis_id impedisce dismiss cross-analisi.
    """
    conn = get_connection()
    cur = conn.execute("""
        UPDATE nonconformities
        SET dismissed = ?, dismiss_reason = ?, created_by = COALESCE(NULLIF(?, ''), created_by),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND analysis_id = ?
    """, (1 if dismissed else 0, reason if dismissed else "", by, nc_id, analysis_id))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0


# Inizializza database all'import (audit_log incluso in init_compliance_tables)
init_database()
init_compliance_tables()


# ==============================================================================
# FUNZIONI PRATICHE
# ==============================================================================

def save_pratica(
    user_id: str,
    tipo: str,
    file_output_path: str,
    file_output_name: str,
    azienda: str = "",
    norma: str = "",
    file_input_path: str = "",
    file_size: int = 0,
    processing_time: float = 0,
    note: str = ""
) -> int:
    """
    Salva una nuova pratica nel database.
    
    Returns:
        ID della pratica inserita
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO pratiche 
        (user_id, tipo, azienda, norma, file_output_path, file_input_path, 
         file_output_name, file_size, processing_time_seconds, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, tipo, azienda, norma, file_output_path, file_input_path,
          file_output_name, file_size, processing_time, note))
    
    pratica_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return pratica_id


def get_pratiche_utente(
    user_id: str,
    tipo: str = None,
    limit: int = 50,
    offset: int = 0,
    search_azienda: str = None,
    data_inizio: str = None,
    data_fine: str = None
) -> List[Dict]:
    """
    Recupera le pratiche di un utente con filtri opzionali.
    
    Args:
        user_id: ID utente
        tipo: Filtra per tipo (report, checklist_json, checklist_word)
        limit: Numero massimo risultati
        offset: Offset per paginazione
        search_azienda: Cerca per nome azienda
        data_inizio: Data inizio (YYYY-MM-DD)
        data_fine: Data fine (YYYY-MM-DD)
    
    Returns:
        Lista di pratiche
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM pratiche WHERE user_id = ?"
    params = [user_id]
    
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)
    
    if search_azienda:
        query += " AND azienda LIKE ?"
        params.append(f"%{search_azienda}%")
    
    if data_inizio:
        query += " AND date(data_creazione) >= ?"
        params.append(data_inizio)
    
    if data_fine:
        query += " AND date(data_creazione) <= ?"
        params.append(data_fine)
    
    query += " ORDER BY data_creazione DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_all_pratiche_admin(
    limit: int = 100,
    offset: int = 0,
    search_azienda: str = None,
    user_filter: str = None
) -> List[Dict]:
    """
    Recupera tutte le pratiche (solo admin).
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM pratiche WHERE 1=1"
    params = []
    
    if user_filter:
        query += " AND user_id = ?"
        params.append(user_filter)
    
    if search_azienda:
        query += " AND azienda LIKE ?"
        params.append(f"%{search_azienda}%")
    
    query += " ORDER BY data_creazione DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def count_pratiche_utente(user_id: str, tipo: str = None) -> int:
    """Conta le pratiche di un utente."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if tipo:
        cursor.execute(
            "SELECT COUNT(*) FROM pratiche WHERE user_id = ? AND tipo = ?",
            (user_id, tipo)
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM pratiche WHERE user_id = ?",
            (user_id,)
        )
    
    count = cursor.fetchone()[0]
    conn.close()
    return count


def delete_pratica(pratica_id: int, user_id: str = None) -> bool:
    """
    Elimina una pratica.
    Se user_id è specificato, verifica che appartenga all'utente.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute(
            "DELETE FROM pratiche WHERE id = ? AND user_id = ?",
            (pratica_id, user_id)
        )
    else:
        # Admin può eliminare qualsiasi pratica
        cursor.execute("DELETE FROM pratiche WHERE id = ?", (pratica_id,))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# ==============================================================================
# FUNZIONI STATISTICHE
# ==============================================================================

def get_statistiche_utente(user_id: str) -> Dict:
    """Statistiche per singolo utente."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Totale pratiche
    cursor.execute(
        "SELECT COUNT(*) FROM pratiche WHERE user_id = ?", (user_id,)
    )
    totale = cursor.fetchone()[0]
    
    # Per tipo
    cursor.execute("""
        SELECT tipo, COUNT(*) as count 
        FROM pratiche WHERE user_id = ? 
        GROUP BY tipo
    """, (user_id,))
    per_tipo = {row["tipo"]: row["count"] for row in cursor.fetchall()}
    
    # Oggi
    cursor.execute("""
        SELECT COUNT(*) FROM pratiche 
        WHERE user_id = ? AND date(data_creazione) = date('now')
    """, (user_id,))
    oggi = cursor.fetchone()[0]
    
    # Ultimi 7 giorni
    cursor.execute("""
        SELECT COUNT(*) FROM pratiche 
        WHERE user_id = ? AND data_creazione >= datetime('now', '-7 days')
    """, (user_id,))
    settimana = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "totale": totale,
        "per_tipo": per_tipo,
        "oggi": oggi,
        "settimana": settimana
    }


def get_statistiche_globali() -> Dict:
    """Statistiche globali (solo admin)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Totale pratiche
    cursor.execute("SELECT COUNT(*) FROM pratiche")
    totale = cursor.fetchone()[0]
    
    # Per utente
    cursor.execute("""
        SELECT user_id, COUNT(*) as count 
        FROM pratiche GROUP BY user_id
        ORDER BY count DESC
    """)
    per_utente = {row["user_id"]: row["count"] for row in cursor.fetchall()}
    
    # Per norma
    cursor.execute("""
        SELECT norma, COUNT(*) as count 
        FROM pratiche WHERE norma IS NOT NULL AND norma != ''
        GROUP BY norma ORDER BY count DESC
    """)
    per_norma = {row["norma"]: row["count"] for row in cursor.fetchall()}
    
    # Oggi
    cursor.execute("""
        SELECT COUNT(*) FROM pratiche 
        WHERE date(data_creazione) = date('now')
    """)
    oggi = cursor.fetchone()[0]
    
    # Tempo medio elaborazione
    cursor.execute("""
        SELECT AVG(processing_time_seconds) FROM pratiche 
        WHERE processing_time_seconds > 0
    """)
    tempo_medio = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "totale": totale,
        "per_utente": per_utente,
        "per_norma": per_norma,
        "oggi": oggi,
        "tempo_medio_secondi": round(tempo_medio, 1)
    }


# ==============================================================================
# FUNZIONI ACTIVITY LOG
# ==============================================================================

def log_activity(user_id: str, action: str, details: str = "", ip: str = ""):
    """Registra un'attività nel log."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO activity_log (user_id, action, details, ip_address)
        VALUES (?, ?, ?, ?)
    """, (user_id, action, details, ip))
    
    conn.commit()
    conn.close()


def get_recent_activity(limit: int = 50, user_id: str = None) -> List[Dict]:
    """Recupera attività recenti."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute("""
            SELECT * FROM activity_log 
            WHERE user_id = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (user_id, limit))
    else:
        cursor.execute("""
            SELECT * FROM activity_log 
            ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ==============================================================================
# FUNZIONI ERROR LOG - Tracciamento errori per Admin
# ==============================================================================

def save_error_log(
    user_id: str,
    error_type: str,
    error_message: str,
    tab_source: str,
    azienda: str = "",
    stack_trace: str = "",
    file_involved: str = "",
    pratica_id: int = None
) -> int:
    """
    Salva un errore nel log per revisione admin.
    
    Args:
        user_id: Username dell'utente
        error_type: Tipo errore ('extraction', 'api', 'generation', 'fatal', 'validation')
        error_message: Messaggio di errore principale
        tab_source: Tab in cui è avvenuto l'errore ('tab1', 'tab2', 'tab3')
        azienda: Nome azienda della pratica (se disponibile)
        stack_trace: Stack trace completo (opzionale)
        file_involved: File coinvolto nell'errore (opzionale)
        pratica_id: ID pratica correlata (opzionale)
    
    Returns:
        ID del log inserito
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO error_log 
            (user_id, azienda, error_type, error_message, stack_trace, tab_source, file_involved, pratica_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, azienda, error_type, error_message, stack_trace, tab_source, file_involved, pratica_id))
        
        error_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return error_id
    except Exception as e:
        # Non bloccare il flusso principale se il log fallisce
        print(f"[WARNING] Errore salvataggio error_log: {e}")
        return -1


def get_errors_for_admin(
    limit: int = 50,
    user_id: str = None,
    error_type: str = None,
    include_resolved: bool = False,
    days_back: int = 30
) -> List[Dict]:
    """
    Recupera errori per la pagina admin.
    
    Args:
        limit: Numero massimo di errori da restituire
        user_id: Filtra per utente specifico (opzionale)
        error_type: Filtra per tipo errore (opzionale)
        include_resolved: Se True, include anche errori risolti
        days_back: Ultimi N giorni da considerare
    
    Returns:
        Lista di errori come dizionari
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT * FROM error_log 
        WHERE created_at >= datetime('now', ?)
    """
    params = [f'-{days_back} days']
    
    if not include_resolved:
        query += " AND resolved = 0"
    
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    
    if error_type:
        query += " AND error_type = ?"
        params.append(error_type)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def mark_error_resolved(error_id: int, resolved_by: str = "") -> bool:
    """Segna un errore come risolto, tracciando chi e quando."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE error_log "
            "SET resolved = 1, resolved_by = ?, resolved_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (resolved_by or "", error_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def save_partial_error(
    user_id: str,
    azienda: str,
    error_subtype: str,
    error_message: str,
    batch_index: int = -1,
    docs_involved: list = None,
    auto_recovered: bool = False,
    recovery_details: str = "",
    tab_source: str = "tab1"
) -> int:
    """
    Salva un errore parziale (non bloccante) nel log errori.

    error_subtype valori attesi:
        "json_parse"    — batch perso per parsing JSON fallito
        "ocr_none"      — response.text None su pagina vuota
        "name_conflict" — conflitto nome azienda ZIP vs visura
        "mupdf_warn"    — warning MuPDF (non bloccante)
        "batch_loss"    — batch perso completamente

    Sempre wrapped in try/except — non deve mai bloccare la pipeline.
    """
    try:
        import json as _json
        conn = get_connection()
        cursor = conn.cursor()

        docs_str = _json.dumps(docs_involved) if docs_involved else None

        cursor.execute("""
            INSERT INTO error_log
            (user_id, azienda, error_type, error_message, tab_source,
             error_subtype, batch_index, docs_involved, auto_recovered, recovery_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, azienda, "partial_error", error_message, tab_source,
            error_subtype, batch_index, docs_str,
            1 if auto_recovered else 0, recovery_details
        ))

        error_id = cursor.lastrowid
        conn.commit()
        conn.close()
        print(f"[ERROR_LOG] {error_subtype} salvato (batch={batch_index}, recovered={auto_recovered})")
        return error_id
    except Exception as e:
        print(f"[WARNING] save_partial_error fallito (non bloccante): {e}")
        return -1


def get_error_dashboard(days: int = 30) -> Dict:
    """
    Dashboard errori parziali per admin.
    Restituisce aggregati per subtype e trend giornaliero.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Aggregati per subtype
    cursor.execute("""
        SELECT error_subtype,
               COUNT(*) as count,
               SUM(auto_recovered) as recovered
        FROM error_log
        WHERE error_type = 'partial_error'
          AND created_at >= datetime('now', ?)
          AND error_subtype IS NOT NULL
        GROUP BY error_subtype
        ORDER BY count DESC
    """, (f'-{days} days',))
    by_subtype = [
        {"subtype": row[0], "count": row[1], "recovered": row[2] or 0}
        for row in cursor.fetchall()
    ]

    # Trend giornaliero
    cursor.execute("""
        SELECT date(created_at) as day,
               error_subtype,
               COUNT(*) as count
        FROM error_log
        WHERE error_type = 'partial_error'
          AND created_at >= datetime('now', ?)
          AND error_subtype IS NOT NULL
        GROUP BY date(created_at), error_subtype
        ORDER BY day DESC
    """, (f'-{days} days',))
    daily_trend = [
        {"day": row[0], "subtype": row[1], "count": row[2]}
        for row in cursor.fetchall()
    ]

    # Totali overall
    cursor.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN auto_recovered = 1 THEN 1 ELSE 0 END)
        FROM error_log
        WHERE error_type = 'partial_error'
          AND created_at >= datetime('now', ?)
    """, (f'-{days} days',))
    row = cursor.fetchone()
    total = row[0] or 0
    recovered_total = row[1] or 0

    conn.close()

    return {
        "days": days,
        "total_partial_errors": total,
        "recovered": recovered_total,
        "recovery_rate": round(recovered_total / total * 100, 1) if total > 0 else 0,
        "by_subtype": by_subtype,
        "daily_trend": daily_trend,
    }


def get_error_stats() -> Dict:
    """Statistiche errori per dashboard admin."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Errori ultime 24 ore
    cursor.execute("""
        SELECT COUNT(*) FROM error_log 
        WHERE created_at >= datetime('now', '-1 day')
    """)
    last_24h = cursor.fetchone()[0]
    
    # Errori ultimi 7 giorni
    cursor.execute("""
        SELECT COUNT(*) FROM error_log 
        WHERE created_at >= datetime('now', '-7 days')
    """)
    last_7d = cursor.fetchone()[0]
    
    # Errori non risolti
    cursor.execute("SELECT COUNT(*) FROM error_log WHERE resolved = 0")
    unresolved = cursor.fetchone()[0]
    
    # Errori per tipo (ultimi 7 giorni)
    cursor.execute("""
        SELECT error_type, COUNT(*) as count 
        FROM error_log 
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY error_type
        ORDER BY count DESC
    """)
    by_type = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {
        "last_24h": last_24h,
        "last_7d": last_7d,
        "unresolved": unresolved,
        "by_type": by_type
    }
