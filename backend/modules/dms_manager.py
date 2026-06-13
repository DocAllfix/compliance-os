"""
Amisys QHSE — Document Management System (Fase C, PRD §1.2 / §1.3.2).

La metà *prevention* del prodotto: un repository documentale persistente per
account con cartelle, versioning, soft-delete e retention. È anche il
fondamento di scan-scoping (Fase D), scheduler scadenze (Fase E), task RAG
(Fase F), registro e piramide (Fase G).

Schema (tre tabelle, create idempotenti):
    dms_folders            — albero cartelle per owner (retention opzionale)
    dms_documents          — un documento logico (ultima versione corrente)
    dms_document_versions  — ogni upload è una versione immutabile

Storage binario su filesystem (come il corpus per-analisi, mai blob in SQLite):
    data/dms/{owner}/{doc_id}/v{n}/file{ext}     # bytes originali
    data/dms/{owner}/{doc_id}/v{n}/text.txt      # testo estratto (Phase 1)
Il nome file originale vive SOLO a DB (niente path fragili sul filesystem).

Ownership: stringa username come compliance_analyses.user_id; gli helper
anti-IDOR (api_deps._require_folder_access / _require_document_access) usano
get_folder / get_document definiti qui.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.db_manager import get_connection, DATA_DIR

DMS_DIR = DATA_DIR / "dms"
DMS_DIR.mkdir(parents=True, exist_ok=True)

# Cap dimensione upload (per file). Override via env se serve.
import os as _os
DMS_MAX_UPLOAD_BYTES = int(_os.environ.get("DMS_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))


# ── Schema ────────────────────────────────────────────────────────────────────

def init_dms_tables() -> None:
    """Crea le tabelle DMS (idempotente). Chiamata all'import del modulo."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dms_folders (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                owner          TEXT NOT NULL,
                parent_id      INTEGER,
                name           TEXT NOT NULL,
                retention_days INTEGER,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at     TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dms_documents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                owner           TEXT NOT NULL,
                folder_id       INTEGER,
                filename        TEXT NOT NULL,
                doc_type        TEXT,
                doc_type_source TEXT DEFAULT 'heuristic',  -- heuristic | engine | manual
                expiry_date     TEXT,                       -- YYYY-MM-DD or NULL
                current_version INTEGER DEFAULT 1,
                sha256          TEXT,
                size            INTEGER DEFAULT 0,
                content_chars   INTEGER DEFAULT 0,
                uploaded_by     TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at      TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dms_document_versions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id  INTEGER NOT NULL,
                version      INTEGER NOT NULL,
                sha256       TEXT,
                file_path    TEXT,
                text_path    TEXT,
                size         INTEGER DEFAULT 0,
                content_chars INTEGER DEFAULT 0,
                uploaded_by  TEXT,
                uploaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                note         TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dms_folders_owner ON dms_folders(owner)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dms_docs_owner ON dms_documents(owner)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dms_docs_folder ON dms_documents(folder_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dms_versions_doc ON dms_document_versions(document_id)")
        conn.commit()
    finally:
        conn.close()


# ── Storage helpers ─────────────────────────────────────────────────────────

def _safe_owner(owner: str) -> str:
    """Cartella owner sul filesystem: solo alfanumerici + _ - (no path traversal)."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (owner or "anon"))[:64] or "anon"


def _version_dir(owner: str, doc_id: int, version: int) -> Path:
    return DMS_DIR / _safe_owner(owner) / str(doc_id) / f"v{version}"


def _ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def _store_version_files(
    owner: str, doc_id: int, version: int, filename: str,
    raw: bytes, extracted_text: str,
) -> tuple[str, str]:
    """Scrive bytes + testo estratto. Ritorna (file_path, text_path) relativi a DATA_DIR."""
    vdir = _version_dir(owner, doc_id, version)
    vdir.mkdir(parents=True, exist_ok=True)
    file_path = vdir / f"file{_ext_of(filename)}"
    text_path = vdir / "text.txt"
    file_path.write_bytes(raw)
    text_path.write_text(extracted_text or "", encoding="utf-8")
    # Path relativi a DATA_DIR per portabilità del DB
    return (str(file_path.relative_to(DATA_DIR)), str(text_path.relative_to(DATA_DIR)))


def _abs(path_rel: Optional[str]) -> Optional[Path]:
    if not path_rel:
        return None
    return DATA_DIR / path_rel


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ── Folders ─────────────────────────────────────────────────────────────────

def create_folder(owner: str, name: str, parent_id: Optional[int] = None,
                  retention_days: Optional[int] = None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO dms_folders (owner, parent_id, name, retention_days) VALUES (?, ?, ?, ?)",
            (owner, parent_id, name.strip() or "Untitled", retention_days),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_folder(folder_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM dms_folders WHERE id = ? AND deleted_at IS NULL", (folder_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_folders(owner: str, parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        if parent_id is None:
            rows = conn.execute(
                "SELECT * FROM dms_folders WHERE owner = ? AND parent_id IS NULL "
                "AND deleted_at IS NULL ORDER BY name",
                (owner,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM dms_folders WHERE owner = ? AND parent_id = ? "
                "AND deleted_at IS NULL ORDER BY name",
                (owner, parent_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_all_folders(owner: str) -> List[Dict[str, Any]]:
    """Tutte le cartelle (per costruire l'albero lato frontend)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM dms_folders WHERE owner = ? AND deleted_at IS NULL ORDER BY name",
            (owner,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def rename_folder(folder_id: int, name: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE dms_folders SET name = ? WHERE id = ? AND deleted_at IS NULL",
            (name.strip() or "Untitled", folder_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def move_folder(folder_id: int, new_parent_id: Optional[int]) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE dms_folders SET parent_id = ? WHERE id = ? AND deleted_at IS NULL",
            (new_parent_id, folder_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_folder_retention(folder_id: int, retention_days: Optional[int]) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE dms_folders SET retention_days = ? WHERE id = ? AND deleted_at IS NULL",
            (retention_days, folder_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def soft_delete_folder(folder_id: int) -> bool:
    """Soft-delete cartella + documenti contenuti (ricorsivo sui figli diretti)."""
    conn = get_connection()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("UPDATE dms_folders SET deleted_at = ? WHERE id = ?", (now, folder_id))
        conn.execute(
            "UPDATE dms_documents SET deleted_at = ? WHERE folder_id = ? AND deleted_at IS NULL",
            (now, folder_id),
        )
        # sottocartelle dirette
        children = conn.execute(
            "SELECT id FROM dms_folders WHERE parent_id = ? AND deleted_at IS NULL", (folder_id,)
        ).fetchall()
        conn.commit()
    finally:
        conn.close()
    for ch in children:
        soft_delete_folder(int(ch["id"]))
    return True


# ── Documents ────────────────────────────────────────────────────────────────

def get_document(document_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM dms_documents WHERE id = ? AND deleted_at IS NULL", (document_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_document_by_name(owner: str, folder_id: Optional[int], filename: str) -> Optional[Dict[str, Any]]:
    """Documento attivo con quel nome nella cartella (per upload→nuova versione)."""
    conn = get_connection()
    try:
        if folder_id is None:
            row = conn.execute(
                "SELECT * FROM dms_documents WHERE owner = ? AND folder_id IS NULL "
                "AND filename = ? AND deleted_at IS NULL",
                (owner, filename),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM dms_documents WHERE owner = ? AND folder_id = ? "
                "AND filename = ? AND deleted_at IS NULL",
                (owner, folder_id, filename),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_documents(owner: str, folder_id: Optional[int] = None,
                   include_deleted: bool = False) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        where = ["owner = ?"]
        params: List[Any] = [owner]
        if folder_id is not None:
            where.append("folder_id = ?")
            params.append(folder_id)
        if not include_deleted:
            where.append("deleted_at IS NULL")
        rows = conn.execute(
            f"SELECT * FROM dms_documents WHERE {' AND '.join(where)} ORDER BY filename",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_all_documents(owner: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
    """Tutti i documenti dell'owner (qualsiasi cartella), più recenti prima."""
    conn = get_connection()
    try:
        where = ["owner = ?"]
        params: List[Any] = [owner]
        if not include_deleted:
            where.append("deleted_at IS NULL")
        rows = conn.execute(
            f"SELECT * FROM dms_documents WHERE {' AND '.join(where)} ORDER BY updated_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_document(
    owner: str,
    folder_id: Optional[int],
    filename: str,
    raw: bytes,
    extracted_text: str,
    doc_type: Optional[str] = None,
    doc_type_source: str = "heuristic",
    expiry_date: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    note: str = "",
) -> Dict[str, Any]:
    """Crea un nuovo documento (versione 1) e ne scrive bytes + testo.

    Ritorna {"document_id", "version", "deduped": False}.
    """
    if len(raw) > DMS_MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large: {len(raw)} bytes (max {DMS_MAX_UPLOAD_BYTES})")

    sha = _sha256(raw)
    chars = len(extracted_text or "")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO dms_documents (owner, folder_id, filename, doc_type, doc_type_source, "
            "expiry_date, current_version, sha256, size, content_chars, uploaded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
            (owner, folder_id, filename, doc_type, doc_type_source, expiry_date,
             sha, len(raw), chars, uploaded_by),
        )
        doc_id = int(cur.lastrowid)
        file_path, text_path = _store_version_files(owner, doc_id, 1, filename, raw, extracted_text)
        conn.execute(
            "INSERT INTO dms_document_versions (document_id, version, sha256, file_path, text_path, "
            "size, content_chars, uploaded_by, note) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, sha, file_path, text_path, len(raw), chars, uploaded_by, note),
        )
        conn.commit()
        return {"document_id": doc_id, "version": 1, "deduped": False}
    finally:
        conn.close()


def add_version(
    document_id: int,
    raw: bytes,
    extracted_text: str,
    uploaded_by: Optional[str] = None,
    note: str = "",
    doc_type: Optional[str] = None,
    expiry_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggiunge una versione a un documento esistente (PRD §1.3.2 doc control).

    Dedup sha256: se i bytes sono identici alla versione corrente, no-op
    (ritorna deduped=True). Aggiorna i metadati correnti del documento.
    """
    doc = get_document(document_id)
    if not doc:
        raise ValueError("Document not found")
    if len(raw) > DMS_MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large: {len(raw)} bytes (max {DMS_MAX_UPLOAD_BYTES})")

    sha = _sha256(raw)
    if sha == doc.get("sha256"):
        return {"document_id": document_id, "version": doc["current_version"], "deduped": True}

    new_version = int(doc["current_version"]) + 1
    chars = len(extracted_text or "")
    owner = doc["owner"]
    filename = doc["filename"]
    conn = get_connection()
    try:
        file_path, text_path = _store_version_files(
            owner, document_id, new_version, filename, raw, extracted_text,
        )
        conn.execute(
            "INSERT INTO dms_document_versions (document_id, version, sha256, file_path, text_path, "
            "size, content_chars, uploaded_by, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, new_version, sha, file_path, text_path, len(raw), chars, uploaded_by, note),
        )
        # Aggiorna i metadati correnti; doc_type/expiry solo se forniti e non manuali
        sets = ["current_version = ?", "sha256 = ?", "size = ?", "content_chars = ?",
                "updated_at = ?"]
        params: List[Any] = [new_version, sha, len(raw), chars,
                             datetime.now().isoformat(timespec="seconds")]
        if doc_type and doc.get("doc_type_source") != "manual":
            sets.append("doc_type = ?"); params.append(doc_type)
        if expiry_date and doc.get("doc_type_source") != "manual":
            sets.append("expiry_date = ?"); params.append(expiry_date)
        params.append(document_id)
        conn.execute(f"UPDATE dms_documents SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return {"document_id": document_id, "version": new_version, "deduped": False}
    finally:
        conn.close()


def get_document_versions(document_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, document_id, version, sha256, size, content_chars, uploaded_by, "
            "uploaded_at, note FROM dms_document_versions WHERE document_id = ? "
            "ORDER BY version DESC",
            (document_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def read_version_bytes(document_id: int, version: Optional[int] = None) -> Optional[tuple[bytes, str]]:
    """Ritorna (bytes, filename) della versione richiesta (default: corrente)."""
    doc = get_document(document_id)
    if not doc:
        return None
    v = version or int(doc["current_version"])
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT file_path FROM dms_document_versions WHERE document_id = ? AND version = ?",
            (document_id, v),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    p = _abs(row["file_path"])
    if not p or not p.exists():
        return None
    return (p.read_bytes(), doc["filename"])


def read_document_text(document_id: int, version: Optional[int] = None) -> str:
    """Testo estratto (Phase 1) della versione richiesta (default: corrente)."""
    doc = get_document(document_id)
    if not doc:
        return ""
    v = version or int(doc["current_version"])
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT text_path FROM dms_document_versions WHERE document_id = ? AND version = ?",
            (document_id, v),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return ""
    p = _abs(row["text_path"])
    if not p or not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def update_document_metadata(
    document_id: int,
    doc_type: Optional[str] = None,
    expiry_date: Optional[str] = None,
    folder_id: Optional[int] = None,
    filename: Optional[str] = None,
    manual: bool = True,
) -> bool:
    """PATCH metadati. manual=True marca doc_type_source='manual' (vince sui backfill)."""
    sets: List[str] = []
    params: List[Any] = []
    if doc_type is not None:
        sets.append("doc_type = ?"); params.append(doc_type)
        if manual:
            sets.append("doc_type_source = 'manual'")
    if expiry_date is not None:
        sets.append("expiry_date = ?"); params.append(expiry_date)
    if folder_id is not None:
        sets.append("folder_id = ?"); params.append(folder_id)
    if filename is not None:
        sets.append("filename = ?"); params.append(filename.strip())
    if not sets:
        return False
    sets.append("updated_at = ?"); params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(document_id)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"UPDATE dms_documents SET {', '.join(sets)} WHERE id = ? AND deleted_at IS NULL",
            params,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def backfill_doc_type(document_id: int, doc_type: str, expiry_date: Optional[str] = None) -> bool:
    """Fase D: aggiorna doc_type/expiry dalle evidence card SOLO se non manuale.

    Marca doc_type_source='engine' (autorevole ma sotto il manuale)."""
    doc = get_document(document_id)
    if not doc or doc.get("doc_type_source") == "manual":
        return False
    sets = ["doc_type = ?", "doc_type_source = 'engine'", "updated_at = ?"]
    params: List[Any] = [doc_type, datetime.now().isoformat(timespec="seconds")]
    if expiry_date:
        sets.insert(1, "expiry_date = ?")
        params.insert(1, expiry_date)
    params.append(document_id)
    conn = get_connection()
    try:
        cur = conn.execute(f"UPDATE dms_documents SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def soft_delete_document(document_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE dms_documents SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (datetime.now().isoformat(timespec="seconds"), document_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def restore_document(document_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE dms_documents SET deleted_at = NULL WHERE id = ?", (document_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_documents(owner: str, query: str) -> List[Dict[str, Any]]:
    """Ricerca per nome o doc_type (case-insensitive)."""
    q = f"%{(query or '').strip().lower()}%"
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM dms_documents WHERE owner = ? AND deleted_at IS NULL "
            "AND (LOWER(filename) LIKE ? OR LOWER(COALESCE(doc_type,'')) LIKE ?) "
            "ORDER BY updated_at DESC",
            (owner, q, q),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Scan scoping (Fase D) ────────────────────────────────────────────────────

def documents_for_scope(
    owner: str,
    scope: str = "all",
    folder_id: Optional[int] = None,
    updated_since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Risolve lo scope di scansione in una lista [{filename, content, document_id, version}].

    scope: 'all' | 'folder' | 'updated_since'. Solo documenti dell'owner.
    """
    docs = list_all_documents(owner, include_deleted=False)
    if scope == "folder" and folder_id is not None:
        docs = [d for d in docs if d.get("folder_id") == folder_id]
    elif scope == "updated_since" and updated_since:
        docs = [d for d in docs if str(d.get("updated_at") or "") >= updated_since]

    out: List[Dict[str, Any]] = []
    for d in docs:
        text = read_document_text(int(d["id"]))
        if text and text.strip():
            out.append({
                "filename": d["filename"],
                "content": text,
                "document_id": int(d["id"]),
                "version": int(d["current_version"]),
            })
    return out


# ── Registro documenti + piramide (Fase G, PRD §1.3.5 / §1.3.6) ──────────────

# Mappa doc_type → tier della piramide documentale ISO
# (Policy → Manual → Procedures → Work Instructions → Records).
PYRAMID_TIERS = ["Policy", "Manual", "Procedures", "Work Instructions", "Records"]

_DOC_TYPE_TIER = {
    "policy": "Policy",
    "quality_manual": "Manual",
    "procedure": "Procedures",
    "management_review": "Procedures",
    "audit_report": "Procedures",
    "legal_register": "Procedures",
    "emergency_plan": "Procedures",
    "risk_assessment": "Procedures",
    "objective_plan": "Procedures",
    "contract_specification": "Work Instructions",
    "record": "Records",
    "training_record": "Records",
    "calibration_record": "Records",
    "nonconformity_record": "Records",
    "communication_record": "Records",
    "supplier_document": "Records",
    "certificate": "Records",
}


def tier_for_doc_type(doc_type: Optional[str]) -> str:
    return _DOC_TYPE_TIER.get(str(doc_type or "").lower(), "Unclassified")


def build_register(owner: str) -> List[Dict[str, Any]]:
    """Proiezione tabellare dei documenti (il 'document register' che il
    QHSE manager mantiene a mano). Solo metadati, nessuna estrazione nuova."""
    out: List[Dict[str, Any]] = []
    for d in list_all_documents(owner):
        out.append({
            "id": d["id"],
            "filename": d["filename"],
            "doc_type": d.get("doc_type"),
            "tier": tier_for_doc_type(d.get("doc_type")),
            "version": d.get("current_version"),
            "expiry_date": d.get("expiry_date"),
            "updated_at": d.get("updated_at"),
            "folder_id": d.get("folder_id"),
        })
    return out


def build_pyramid(owner: str) -> Dict[str, Any]:
    """Conteggi e documenti per tier della piramide. Segnala i tier vuoti."""
    docs = build_register(owner)
    tiers: Dict[str, List[Dict[str, Any]]] = {t: [] for t in PYRAMID_TIERS}
    tiers["Unclassified"] = []
    for d in docs:
        tiers.setdefault(d["tier"], []).append(d)
    return {
        "tiers": [
            {"tier": t, "count": len(tiers[t]), "documents": tiers[t]}
            for t in PYRAMID_TIERS + (["Unclassified"] if tiers["Unclassified"] else [])
        ],
        "empty_tiers": [t for t in PYRAMID_TIERS if not tiers[t]],
        "total": len(docs),
    }


def register_to_xlsx(owner: str) -> bytes:
    """Esporta il registro come XLSX (openpyxl già in requirements)."""
    import io
    import openpyxl  # type: ignore

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Document Register"
    headers = ["Document", "Type", "Tier", "Version", "Expiry", "Last updated"]
    ws.append(headers)
    for d in build_register(owner):
        ws.append([
            d["filename"],
            (d["doc_type"] or "").replace("_", " "),
            d["tier"],
            d["version"],
            d["expiry_date"] or "",
            str(d["updated_at"] or "")[:10],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Crea le tabelle all'import (db_manager è già completamente caricato qui).
init_dms_tables()
