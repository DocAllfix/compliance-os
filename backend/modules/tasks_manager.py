"""
Amisys QHSE — Task waterfall with RAG status (Fase F, PRD §1.3.4).

I task NON sono materializzati: il registro NC è già l'overlay persistente, e
materializzare i task creerebbe un sync-di-un-sync. La lista si COMPONE a
lettura da tre sorgenti:

  1. Nonconformità aperte dell'ultima analisi dell'utente
     (due deterministica: MAJOR +30g, MINOR +90g dalla data analisi)
  2. Scadenze dei documenti DMS (due = expiry_date)
  3. Task manuali (tabella `tasks`)

Una tabella sottile `task_state` tiene SOLO le mutazioni utente (done / snooze /
override della due-date), chiave stabile `task_key`:
    nc:{nc_id}   expiry:{doc_id}   manual:{id}

RAG calcolato a lettura (mai persistito): overdue→red, ≤30g→amber, else→green.
Completare un task `nc:*` scrive su nonconformities via update_ncr_status, così
Plan e Tasks non divergono mai.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from modules.db_manager import get_connection

_MAJOR_DAYS = 30
_MINOR_DAYS = 90
_AMBER_WINDOW = 30


def init_tasks_tables() -> None:
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                owner      TEXT NOT NULL,
                title      TEXT NOT NULL,
                due_date   TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_state (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                owner         TEXT NOT NULL,
                task_key      TEXT NOT NULL,
                done          INTEGER DEFAULT 0,
                snoozed_until TEXT,
                due_override  TEXT,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_task_state ON task_state(owner, task_key)")
        conn.commit()
    finally:
        conn.close()


def _rag(due: Optional[str], today: date) -> str:
    if not due:
        return "green"
    try:
        d = datetime.strptime(due, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return "green"
    days = (d - today).days
    if days < 0:
        return "red"
    if days <= _AMBER_WINDOW:
        return "amber"
    return "green"


def _states(owner: str) -> Dict[str, Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM task_state WHERE owner = ?", (owner,)).fetchall()
    finally:
        conn.close()
    return {r["task_key"]: dict(r) for r in rows}


def list_tasks(owner: str, today: date | None = None) -> List[Dict[str, Any]]:
    """Compone la lista task da NC + scadenze DMS + manuali, applica task_state
    e calcola il RAG. Ordinata per due-date (senza due in coda)."""
    from modules.db_manager import get_compliance_analyses, get_nonconformities
    import modules.dms_manager as dms

    today = today or date.today()
    states = _states(owner)
    tasks: List[Dict[str, Any]] = []

    def _apply(task: Dict[str, Any]) -> Dict[str, Any]:
        st = states.get(task["task_key"])
        if st:
            task["done"] = bool(st["done"])
            if st["due_override"]:
                task["due_date"] = st["due_override"]
            task["snoozed_until"] = st["snoozed_until"]
        else:
            task.setdefault("done", False)
            task.setdefault("snoozed_until", None)
        # snoozed nel futuro → green, altrimenti RAG normale
        if task["done"]:
            task["rag"] = "done"
        elif task.get("snoozed_until") and task["snoozed_until"] > today.isoformat():
            task["rag"] = "snoozed"
        else:
            task["rag"] = _rag(task.get("due_date"), today)
        return task

    # 1) Nonconformità dell'ultima analisi
    analyses = get_compliance_analyses(owner, limit=1)
    if analyses:
        a = analyses[0]
        aid = a["id"]
        try:
            adate = datetime.fromisoformat(str(a.get("analysis_date"))).date()
        except (ValueError, TypeError):
            adate = today
        for nc in get_nonconformities(aid):
            if nc.get("dismissed") or str(nc.get("status")) == "closed":
                continue
            sev = str(nc.get("severity") or "").upper()
            if sev not in ("MAJOR", "MINOR"):
                continue
            offset = _MAJOR_DAYS if sev == "MAJOR" else _MINOR_DAYS
            due = (adate + timedelta(days=offset)).isoformat()
            tasks.append(_apply({
                "task_key": f"nc:{nc['id']}",
                "source": "nonconformity",
                "title": nc.get("title") or nc.get("clause_id") or "Nonconformity",
                "severity": sev,
                "due_date": due,
                "link": f"/analyses/{aid}/plan",
                "analysis_id": aid,
                "clause_id": nc.get("clause_id"),
            }))

    # 2) Scadenze documenti DMS
    for d in dms.list_all_documents(owner):
        if not d.get("expiry_date"):
            continue
        tasks.append(_apply({
            "task_key": f"expiry:{d['id']}",
            "source": "expiry",
            "title": f"Renew: {d['filename']}",
            "severity": None,
            "due_date": d["expiry_date"],
            "link": "/documents",
        }))

    # 3) Task manuali
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE owner = ? AND deleted_at IS NULL", (owner,)
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        tasks.append(_apply({
            "task_key": f"manual:{r['id']}",
            "source": "manual",
            "title": r["title"],
            "severity": None,
            "due_date": r["due_date"],
            "link": "/tasks",
        }))

    # ordina per due-date (None in coda), non-done prima
    tasks.sort(key=lambda t: (t["done"], t.get("due_date") or "9999-12-31"))
    return tasks


def _upsert_state(owner: str, task_key: str, **fields) -> None:
    cols = ", ".join(fields.keys())
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM task_state WHERE owner = ? AND task_key = ?", (owner, task_key)
        ).fetchone()
        if existing:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE task_state SET {sets}, updated_at = CURRENT_TIMESTAMP "
                f"WHERE owner = ? AND task_key = ?",
                (*fields.values(), owner, task_key),
            )
        else:
            placeholders = ", ".join("?" for _ in fields)
            conn.execute(
                f"INSERT INTO task_state (owner, task_key, {cols}) VALUES (?, ?, {placeholders})",
                (owner, task_key, *fields.values()),
            )
        conn.commit()
    finally:
        conn.close()


def set_task_done(owner: str, task_key: str, done: bool) -> None:
    """Marca done. Write-through: un task nc:* chiude/riapre la NC collegata
    così Plan e Tasks restano allineati."""
    _upsert_state(owner, task_key, done=1 if done else 0)
    if task_key.startswith("nc:"):
        try:
            nc_id = int(task_key.split(":", 1)[1])
        except ValueError:
            return
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT analysis_id, clause_id FROM nonconformities WHERE id = ?", (nc_id,)
            ).fetchone()
        finally:
            conn.close()
        if row and row["clause_id"]:
            from modules.db_manager import update_ncr_status
            update_ncr_status(row["analysis_id"], row["clause_id"],
                              "closed" if done else "open")


def snooze_task(owner: str, task_key: str, until: str) -> None:
    _upsert_state(owner, task_key, snoozed_until=until)


def add_manual_task(owner: str, title: str, due_date: Optional[str] = None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (owner, title, due_date) VALUES (?, ?, ?)",
            (owner, title.strip() or "Task", due_date),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def delete_manual_task(owner: str, task_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE tasks SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND owner = ?",
            (task_id, owner),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


init_tasks_tables()
