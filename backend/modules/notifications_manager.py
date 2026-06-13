"""
Amisys QHSE — Notifications + scheduler state (Fase E, PRD §1.3.3).

Notifiche in-app idempotenti: la chiave UNIQUE(username, kind, entity_ref,
dedup_key) garantisce che lo scheduler, ad ogni passata (anche dopo restart o
reload), non duplichi una notifica già emessa per quella soglia di scadenza.

`scheduler_state` è un k/v minimale: l'ultima data in cui i job giornalieri sono
stati eseguiti, così qualunque ora di avvio innesca la passata al massimo una
volta al giorno.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.db_manager import get_connection


def init_notifications_tables() -> None:
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL,
                kind        TEXT NOT NULL,          -- 'expiry' | ...
                severity    TEXT,                   -- MAJOR | MINOR | OBSERVATION | INFO
                title       TEXT NOT NULL,
                body        TEXT,
                link        TEXT,
                entity_ref  TEXT,                   -- es. 'dms_doc:15'
                dedup_key   TEXT,                   -- es. '30d:2026-12-31'
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at     TIMESTAMP
            )
        """)
        # Idempotenza: una notifica per (utente, tipo, entità, soglia).
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_dedup
            ON notifications(username, kind, entity_ref, dedup_key)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(username, read_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def create_notification(
    username: str,
    kind: str,
    title: str,
    body: str = "",
    link: Optional[str] = None,
    severity: Optional[str] = None,
    entity_ref: Optional[str] = None,
    dedup_key: Optional[str] = None,
) -> bool:
    """Crea una notifica. Ritorna True se inserita, False se già esistente
    (dedup). INSERT OR IGNORE sull'indice unico."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO notifications "
            "(username, kind, severity, title, body, link, entity_ref, dedup_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (username, kind, severity, title, body, link, entity_ref, dedup_key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_notifications(username: str, limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        q = ("SELECT * FROM notifications WHERE username = ?"
             + (" AND read_at IS NULL" if unread_only else "")
             + " ORDER BY id DESC LIMIT ?")
        rows = conn.execute(q, (username, max(1, min(limit, 200)))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def unread_count(username: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE username = ? AND read_at IS NULL",
            (username,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()


def mark_read(notification_id: int, username: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND username = ? AND read_at IS NULL",
            (notification_id, username),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def mark_all_read(username: str) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE username = ? AND read_at IS NULL",
            (username,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ── scheduler_state k/v ──────────────────────────────────────────────────────

def get_state(key: str) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM scheduler_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_state(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO scheduler_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


init_notifications_tables()
