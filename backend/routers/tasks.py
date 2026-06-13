"""
Amisys QHSE — Tasks router (Fase F, PRD §1.3.4).

Task waterfall con stato RAG, composto a lettura da NC + scadenze DMS +
manuali. Mutazioni: complete (write-through sulle NC), snooze, add/delete
manuali. Ownership implicita (sempre owner = utente corrente).
"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_deps import _get_current_user
import modules.tasks_manager as tm

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskDone(BaseModel):
    done: bool = True


class TaskSnooze(BaseModel):
    until: str  # YYYY-MM-DD


class ManualTask(BaseModel):
    title: str
    due_date: Optional[str] = None


def _audit(user, action, entity_id=None, detail=None) -> None:
    try:
        from modules.audit_log import log_audit
        log_audit(user, action, "task", entity_id, detail)
    except Exception:
        pass


@router.get("")
async def list_tasks(user: Dict = Depends(_get_current_user)):
    items = tm.list_tasks(user["username"])
    counts = {"red": 0, "amber": 0, "green": 0, "done": 0, "snoozed": 0}
    for t in items:
        counts[t["rag"]] = counts.get(t["rag"], 0) + 1
    return {"tasks": items, "counts": counts}


@router.post("/{task_key}/done")
async def set_done(task_key: str, body: TaskDone, user: Dict = Depends(_get_current_user)):
    tm.set_task_done(user["username"], task_key, body.done)
    _audit(user, "task_done" if body.done else "task_reopen", task_key)
    return {"ok": True}


@router.post("/{task_key}/snooze")
async def snooze(task_key: str, body: TaskSnooze, user: Dict = Depends(_get_current_user)):
    tm.snooze_task(user["username"], task_key, body.until)
    _audit(user, "task_snooze", task_key, {"until": body.until})
    return {"ok": True}


@router.post("")
async def add_manual(body: ManualTask, user: Dict = Depends(_get_current_user)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    tid = tm.add_manual_task(user["username"], body.title, body.due_date)
    _audit(user, "task_add", f"manual:{tid}", {"title": body.title.strip()})
    return {"ok": True, "task_id": tid}


@router.delete("/manual/{task_id}")
async def delete_manual(task_id: int, user: Dict = Depends(_get_current_user)):
    ok = tm.delete_manual_task(user["username"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    _audit(user, "task_delete", f"manual:{task_id}")
    return {"ok": True}
