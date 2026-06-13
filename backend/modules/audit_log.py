"""
Amisys QHSE — Audit trail (Fase B, PRD §4.3.10 / §4.4.5).

Tabella **append-only**: ogni azione mutante (login, action PATCH, dismiss/
restore NC, NC manuale, e in futuro ogni CRUD del DMS) scrive una riga
immutabile (data/ora, utente, azione, entità, dettaglio JSON). Niente UPDATE,
niente DELETE: è la prova di conformità che ICO/ISO richiedono.

API:
    init_audit_table()                                  — idempotente
    log_audit(user, action, entity_type, entity_id, detail=None, ip=None)
    get_audit_log(limit, offset, user=None, entity_type=None, action=None)
    count_audit_log(...)

Il logging non deve MAI rompere il flusso applicativo: log_audit cattura ogni
eccezione internamente (un audit fallito non deve impedire l'operazione, ma
viene segnalato a log).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from modules.db_manager import get_connection

_log = logging.getLogger("audit_log")


def init_audit_table() -> None:
    """Crea la tabella append-only (idempotente)."""
    conn = get_connection()
    try:
        conn.execute("""
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id)")
        conn.commit()
    finally:
        conn.close()


def log_audit(
    user: Any,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[Any] = None,
    detail: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> None:
    """Append-only. `user` può essere il dict utente o una stringa username.

    Non solleva mai: un audit fallito viene loggato ma non blocca l'azione.
    """
    try:
        if isinstance(user, dict):
            username = str(user.get("username") or user.get("name") or "unknown")
        else:
            username = str(user or "unknown")
        detail_json = json.dumps(detail, ensure_ascii=False) if detail else None
        eid = None if entity_id is None else str(entity_id)
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO audit_log (username, action, entity_type, entity_id, detail, ip_address) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, action, entity_type, eid, detail_json, ip),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — audit must never break the request
        _log.warning("audit_log write failed (%s on %s/%s): %s",
                     action, entity_type, entity_id, e)


def get_audit_log(
    limit: int = 100,
    offset: int = 0,
    username: Optional[str] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lettura paginata, più recenti prima. Filtri opzionali."""
    clauses: List[str] = []
    params: List[Any] = []
    if username:
        clauses.append("username = ?")
        params.append(username)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if action:
        clauses.append("action = ?")
        params.append(action)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([max(1, min(limit, 1000)), max(0, offset)])

    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT id, ts, username, action, entity_type, entity_id, detail, ip_address "
            f"FROM audit_log{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    finally:
        conn.close()

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if d.get("detail"):
            try:
                d["detail"] = json.loads(d["detail"])
            except (ValueError, TypeError):
                pass
        out.append(d)
    return out


def count_audit_log(
    username: Optional[str] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
) -> int:
    clauses: List[str] = []
    params: List[Any] = []
    if username:
        clauses.append("username = ?")
        params.append(username)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if action:
        clauses.append("action = ?")
        params.append(action)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_connection()
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM audit_log{where}", params).fetchone()
    finally:
        conn.close()
    return int(row["n"]) if row else 0
