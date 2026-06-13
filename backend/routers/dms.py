"""
Amisys QHSE — DMS router (Fase C, PRD §1.2 / §1.3.2).

Superficie REST del Document Management System: cartelle, documenti, versioni,
import ZIP. Tutto ownership-checked (anti-IDOR via api_deps) e audit-logged.

Pipeline di upload (riusa Phase 1, niente LLM sul path CRUD):
    bytes → extraction.extract_document → testo
          → doc_classifier.classify + detect_expiry → metadati euristici
          → dms_manager.create_document | add_version (dedup sha256)
"""
from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, Body,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_deps import (
    _get_current_user,
    _require_folder_access,
    _require_document_access,
)
from compliance.doc_classifier import classify, detect_expiry
from compliance.extraction import extract_document, _repair_zip_name
import modules.dms_manager as dms

router = APIRouter(prefix="/api/dms", tags=["dms"])


def _audit(user, action, entity_type=None, entity_id=None, detail=None) -> None:
    try:
        from modules.audit_log import log_audit
        log_audit(user, action, entity_type, entity_id, detail)
    except Exception:
        pass


# ── Models ───────────────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    retention_days: Optional[int] = None


class FolderPatch(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    retention_days: Optional[int] = None
    move: bool = False  # se true, applica parent_id anche se None (root)


class DocumentPatch(BaseModel):
    doc_type: Optional[str] = None
    expiry_date: Optional[str] = None
    folder_id: Optional[int] = None
    filename: Optional[str] = None
    move: bool = False


# ── Folders ──────────────────────────────────────────────────────────────────

@router.get("/folders")
async def list_folders(user: Dict = Depends(_get_current_user)):
    """Tutte le cartelle dell'utente (l'albero si costruisce lato frontend)."""
    return {"folders": dms.list_all_folders(user["username"])}


@router.post("/folders")
async def create_folder(body: FolderCreate, user: Dict = Depends(_get_current_user)):
    if body.parent_id is not None:
        _require_folder_access(body.parent_id, user)  # 404/403 se non tua
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Folder name is required")
    fid = dms.create_folder(user["username"], body.name, body.parent_id, body.retention_days)
    _audit(user, "dms_folder_create", "folder", fid, {"name": body.name.strip()})
    return {"ok": True, "folder_id": fid}


@router.patch("/folders/{folder_id}")
async def patch_folder(folder_id: int, body: FolderPatch, user: Dict = Depends(_get_current_user)):
    _require_folder_access(folder_id, user)
    if body.name is not None:
        dms.rename_folder(folder_id, body.name)
    if body.move:
        if body.parent_id is not None:
            _require_folder_access(body.parent_id, user)
        dms.move_folder(folder_id, body.parent_id)
    if body.retention_days is not None:
        dms.set_folder_retention(folder_id, body.retention_days)
    _audit(user, "dms_folder_update", "folder", folder_id, body.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, user: Dict = Depends(_get_current_user)):
    _require_folder_access(folder_id, user)
    dms.soft_delete_folder(folder_id)
    _audit(user, "dms_folder_delete", "folder", folder_id)
    return {"ok": True}


# ── Documents ────────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    folder_id: Optional[int] = Query(None),
    user: Dict = Depends(_get_current_user),
):
    if folder_id is not None:
        _require_folder_access(folder_id, user)
        docs = dms.list_documents(user["username"], folder_id=folder_id)
    else:
        docs = dms.list_all_documents(user["username"])
    return {"documents": docs}


@router.get("/documents/{document_id}")
async def get_document(document_id: int, user: Dict = Depends(_get_current_user)):
    doc = _require_document_access(document_id, user)
    return {"document": doc, "versions": dms.get_document_versions(document_id)}


def _ingest_one(owner: str, folder_id: Optional[int], filename: str, raw: bytes,
                uploaded_by: str, note: str = "") -> Dict[str, Any]:
    """Estrae, classifica e crea/versiona un singolo file. Ritorna il risultato dms."""
    text = extract_document(filename, raw)
    existing = dms.find_document_by_name(owner, folder_id, filename)
    if existing:
        return dms.add_version(
            existing["id"], raw, text, uploaded_by=uploaded_by, note=note,
            doc_type=classify(filename, text), expiry_date=detect_expiry(text),
        )
    return dms.create_document(
        owner=owner, folder_id=folder_id, filename=filename, raw=raw,
        extracted_text=text, doc_type=classify(filename, text),
        doc_type_source="heuristic", expiry_date=detect_expiry(text),
        uploaded_by=uploaded_by, note=note,
    )


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    folder_id: Optional[int] = Form(None),
    note: str = Form(""),
    user: Dict = Depends(_get_current_user),
):
    """Upload di un singolo documento. Se esiste già un file con lo stesso nome
    nella cartella, diventa una nuova versione (dedup sha256)."""
    if folder_id is not None:
        _require_folder_access(folder_id, user)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="Empty file")
    try:
        res = _ingest_one(user["username"], folder_id, file.filename or "untitled",
                          raw, user["username"], note)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    _audit(user, "dms_document_upload", "document", res["document_id"],
           {"filename": file.filename, "version": res["version"], "deduped": res["deduped"]})
    return {"ok": True, **res}


@router.post("/import-zip")
async def import_zip(
    file: UploadFile = File(...),
    folder_id: Optional[int] = Form(None),
    user: Dict = Depends(_get_current_user),
):
    """Import massivo: ogni file dello ZIP entra nella cartella (create o
    nuova versione). Riusa il name-repair cp437/NFD dei ZIP reali."""
    if folder_id is not None:
        _require_folder_access(folder_id, user)
    raw = await file.read()
    imported, versioned, skipped = 0, 0, 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                display = _repair_zip_name(name)
                try:
                    data = zf.read(name)
                    if not data:
                        skipped += 1
                        continue
                    res = _ingest_one(user["username"], folder_id, display,
                                      data, user["username"], note="zip import")
                    if res["deduped"]:
                        skipped += 1
                    elif res["version"] > 1:
                        versioned += 1
                    else:
                        imported += 1
                except Exception:
                    skipped += 1
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="Not a valid ZIP archive")
    _audit(user, "dms_import_zip", "folder", folder_id,
           {"imported": imported, "versioned": versioned, "skipped": skipped})
    return {"ok": True, "imported": imported, "versioned": versioned, "skipped": skipped}


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    version: Optional[int] = Query(None),
    user: Dict = Depends(_get_current_user),
):
    _require_document_access(document_id, user)
    result = dms.read_version_bytes(document_id, version)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    data, filename = result
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/documents/{document_id}")
async def patch_document(document_id: int, body: DocumentPatch,
                         user: Dict = Depends(_get_current_user)):
    _require_document_access(document_id, user)
    if body.folder_id is not None:
        _require_folder_access(body.folder_id, user)
    ok = dms.update_document_metadata(
        document_id,
        doc_type=body.doc_type,
        expiry_date=body.expiry_date,
        folder_id=body.folder_id if body.move else None,
        filename=body.filename,
        manual=True,
    )
    if not ok:
        raise HTTPException(status_code=422, detail="No changes applied")
    _audit(user, "dms_document_update", "document", document_id,
           body.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, user: Dict = Depends(_get_current_user)):
    _require_document_access(document_id, user)
    dms.soft_delete_document(document_id)
    _audit(user, "dms_document_delete", "document", document_id)
    return {"ok": True}


@router.post("/documents/{document_id}/restore")
async def restore_document(document_id: int, user: Dict = Depends(_get_current_user)):
    # restore deve poter agire su un doc soft-deleted: bypass del filtro deleted
    doc = dms.get_document(document_id)
    if doc is None:
        # potrebbe essere soft-deleted: verifichiamo ownership sulla riga grezza
        from modules.db_manager import get_connection
        conn = get_connection()
        try:
            row = conn.execute("SELECT owner FROM dms_documents WHERE id = ?", (document_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        if str(row["owner"]).lower() != user["username"].lower() and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied")
    dms.restore_document(document_id)
    _audit(user, "dms_document_restore", "document", document_id)
    return {"ok": True}


@router.get("/search")
async def search(q: str = Query(..., min_length=1), user: Dict = Depends(_get_current_user)):
    return {"documents": dms.search_documents(user["username"], q)}


# ── Register + pyramid (Fase G, PRD §1.3.5 / §1.3.6) ─────────────────────────

@router.get("/register")
async def get_register(user: Dict = Depends(_get_current_user)):
    return {"register": dms.build_register(user["username"])}


@router.get("/register/export")
async def export_register(user: Dict = Depends(_get_current_user)):
    data = dms.register_to_xlsx(user["username"])
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="document_register.xlsx"'},
    )


@router.get("/pyramid")
async def get_pyramid(user: Dict = Depends(_get_current_user)):
    return dms.build_pyramid(user["username"])
