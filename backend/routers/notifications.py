"""
Amisys QHSE — Notifications router (Fase E, PRD §1.3.3).

In-app notifications (campanella nell'header): elenco, conteggio non lette,
mark-read. Ownership implicita: ogni utente vede solo le proprie.
"""
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, Query

from api_deps import _get_current_user
import modules.notifications_manager as nm

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    user: Dict = Depends(_get_current_user),
):
    items = nm.list_notifications(user["username"], limit=limit, unread_only=unread_only)
    return {"notifications": items, "unread": nm.unread_count(user["username"])}


@router.get("/unread-count")
async def get_unread_count(user: Dict = Depends(_get_current_user)):
    return {"unread": nm.unread_count(user["username"])}


@router.post("/{notification_id}/read")
async def mark_one_read(notification_id: int, user: Dict = Depends(_get_current_user)):
    nm.mark_read(notification_id, user["username"])
    return {"ok": True, "unread": nm.unread_count(user["username"])}


@router.post("/read-all")
async def mark_all_read(user: Dict = Depends(_get_current_user)):
    n = nm.mark_all_read(user["username"])
    return {"ok": True, "marked": n}
