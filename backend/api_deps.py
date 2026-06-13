"""
Amisys QHSE — Shared FastAPI dependencies (Fase B).

Estratto da `api_server.py` per permettere ai router modulari
(`routers/dms.py`, `routers/tasks.py`, `routers/notifications.py`) di
riusare auth + ownership senza import circolari su api_server.

Contiene:
    _get_current_user           — dependency Bearer → dict utente
    _require_analysis_access    — anti-IDOR su un'analisi (404/403, admin bypass)
    _require_folder_access      — anti-IDOR su una cartella DMS (Fase C)
    _require_document_access    — anti-IDOR su un documento DMS (Fase C)

I primi due sono importati e ri-esportati da api_server.py: gli endpoint
esistenti non cambiano. I due DMS usano import lazy di `modules.dms_manager`
(creato in Fase C), così importare questo modulo oggi non richiede il DMS.
"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import Header, HTTPException

from modules.auth_manager import validate_session_token, load_users


def _get_current_user(authorization: Optional[str] = Header(None)) -> Dict:
    """Dependency: valida Bearer token → restituisce dict utente."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token non fornito")
    token = authorization.removeprefix("Bearer ").strip()
    # validate_session_token restituisce Optional[str] (username), non un dict
    username = validate_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token non valido o scaduto")
    # Carica il dict completo dell'utente da users.json
    users = load_users()
    user_data = users.get(username.lower(), users.get(username, {}))
    return {
        "username": username,
        "role": user_data.get("role", "member"),
        "email": "",                                  # users.json non ha campo email
        "display_name": user_data.get("name", username),
        "name": user_data.get("name", username),
    }


def _is_admin(user: Dict) -> bool:
    return str(user.get("role") or "").strip().lower() == "admin"


def _same_owner(owner: object, user: Dict) -> bool:
    """Confronto ownership case-insensitive (admin bypass gestito a parte)."""
    return str(owner or "").strip().lower() == str(user.get("username") or "").strip().lower()


def _require_analysis_access(analysis_id: str, user: Dict) -> Dict:
    """Fase 3 (anti-IDOR): carica la riga analisi e verifica l'ownership.

    - 404 se l'analisi non esiste
    - 403 se appartiene a un altro utente (bypass per role=admin)
    - ritorna la riga DB così i chiamanti non rifanno la query
    """
    from modules.db_manager import get_compliance_analysis

    row = get_compliance_analysis(analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if not _is_admin(user) and not _same_owner(row.get("user_id"), user):
        raise HTTPException(
            status_code=403,
            detail="Access denied: this analysis belongs to another user",
        )
    return row


def _require_folder_access(folder_id: int, user: Dict) -> Dict:
    """Fase C (anti-IDOR su DMS): carica la cartella e verifica l'ownership.

    Import lazy di dms_manager così questo modulo è importabile prima che il
    DMS esista (Fase C lo crea).
    """
    from modules.dms_manager import get_folder

    row = get_folder(folder_id)
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")
    if not _is_admin(user) and not _same_owner(row.get("owner"), user):
        raise HTTPException(
            status_code=403,
            detail="Access denied: this folder belongs to another user",
        )
    return row


def _require_document_access(document_id: int, user: Dict) -> Dict:
    """Fase C (anti-IDOR su DMS): carica il documento e verifica l'ownership."""
    from modules.dms_manager import get_document

    row = get_document(document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    if not _is_admin(user) and not _same_owner(row.get("owner"), user):
        raise HTTPException(
            status_code=403,
            detail="Access denied: this document belongs to another user",
        )
    return row
