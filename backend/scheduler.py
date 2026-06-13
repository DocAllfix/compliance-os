"""
Amisys QHSE — Background scheduler (Fase E, PRD §1.3.3 / §4.3.8).

Task asyncio nel lifespan FastAPI (niente APScheduler/celery — coerente con la
dieta dipendenze). Tick orario; i job giornalieri girano una volta al giorno
(gating via scheduler_state.last_run_date), così qualunque ora di avvio li
innesca al massimo una volta.

Job:
  1. expiry_scan      — notifiche in-app a -60/-30/-7/0 giorni dalle scadenze
                        dei documenti DMS (dedup per soglia → idempotente).
  2. retention_sweep  — soft-delete documenti oltre folder.retention_days e
                        purge dei binari dopo un periodo di grazia (le righe DB
                        restano per l'audit trail).

`SCHEDULER_ENABLED` (default "0") accende il loop: spento nei test, da accendere
via env nel deployment reale. `run_daily_jobs()` è chiamabile direttamente
(usato dai test e da un eventuale trigger manuale).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict

_log = logging.getLogger("scheduler")

# Soglie giorni-alla-scadenza → (etichetta dedup, severità)
_EXPIRY_THRESHOLDS = [
    (0,  "due",  "MAJOR"),    # scaduto o scade oggi
    (7,  "7d",   "MAJOR"),
    (30, "30d",  "MINOR"),
    (60, "60d",  "OBSERVATION"),
]

# Giorni di grazia dopo il soft-delete prima di cancellare i binari.
_PURGE_GRACE_DAYS = int(os.environ.get("DMS_PURGE_GRACE_DAYS", "30"))


def _bucket_for(days_to_expiry: int):
    """Ritorna (label, severity) della soglia più stretta applicabile, o None."""
    for limit, label, sev in _EXPIRY_THRESHOLDS:
        if days_to_expiry <= limit:
            return label, sev
    return None


def expiry_scan(today: date | None = None) -> int:
    """Crea notifiche per i documenti DMS in scadenza. Ritorna # notifiche nuove."""
    from modules.db_manager import get_connection
    from modules.notifications_manager import create_notification

    today = today or date.today()
    created = 0
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, owner, filename, expiry_date FROM dms_documents "
            "WHERE deleted_at IS NULL AND expiry_date IS NOT NULL AND expiry_date != ''"
        ).fetchall()
    finally:
        conn.close()

    for r in rows:
        try:
            exp = datetime.strptime(r["expiry_date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        days = (exp - today).days
        bucket = _bucket_for(days)
        if not bucket:
            continue  # oltre 60 giorni: non ancora rilevante
        label, sev = bucket
        when = "has expired" if days < 0 else ("expires today" if days == 0 else f"expires in {days} days")
        ok = create_notification(
            username=r["owner"],
            kind="expiry",
            severity=sev,
            title=f"{r['filename']} {when}",
            body=f"Document expiry on {r['expiry_date']}. Review or renew to stay compliant.",
            link="/documents",
            entity_ref=f"dms_doc:{r['id']}",
            dedup_key=f"{label}:{r['expiry_date']}",
        )
        if ok:
            created += 1
    return created


def retention_sweep(today: date | None = None) -> Dict[str, int]:
    """Soft-delete documenti oltre la retention della loro cartella; purge dei
    binari dei documenti soft-deleted da oltre il periodo di grazia."""
    from modules.db_manager import get_connection, DATA_DIR

    today = today or date.today()
    soft_deleted, purged = 0, 0
    conn = get_connection()
    try:
        # 1) soft-delete oltre retention (folder.retention_days su updated_at)
        rows = conn.execute("""
            SELECT d.id, d.updated_at FROM dms_documents d
            JOIN dms_folders f ON d.folder_id = f.id
            WHERE d.deleted_at IS NULL AND f.retention_days IS NOT NULL AND f.retention_days > 0
        """).fetchall()
        for r in rows:
            try:
                updated = datetime.fromisoformat(str(r["updated_at"])).date()
            except (ValueError, TypeError):
                continue
            # retention_days letto per riga (join) — rifaccio la query mirata
            fr = conn.execute(
                "SELECT f.retention_days AS rd FROM dms_documents d "
                "JOIN dms_folders f ON d.folder_id=f.id WHERE d.id=?", (r["id"],)
            ).fetchone()
            if not fr or not fr["rd"]:
                continue
            if (today - updated).days > int(fr["rd"]):
                conn.execute(
                    "UPDATE dms_documents SET deleted_at = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), r["id"]),
                )
                soft_deleted += 1
        conn.commit()

        # 2) purge binari dei soft-deleted oltre la grazia
        cutoff = (today - timedelta(days=_PURGE_GRACE_DAYS)).isoformat()
        del_rows = conn.execute(
            "SELECT id, deleted_at FROM dms_documents WHERE deleted_at IS NOT NULL"
        ).fetchall()
        for r in del_rows:
            try:
                deleted_on = datetime.fromisoformat(str(r["deleted_at"])).date().isoformat()
            except (ValueError, TypeError):
                continue
            if deleted_on > cutoff:
                continue  # ancora in grazia
            vrows = conn.execute(
                "SELECT file_path, text_path FROM dms_document_versions WHERE document_id = ?",
                (r["id"],),
            ).fetchall()
            removed_any = False
            for v in vrows:
                for rel in (v["file_path"], v["text_path"]):
                    if not rel:
                        continue
                    p = DATA_DIR / rel
                    if p.exists():
                        try:
                            p.unlink()
                            removed_any = True
                        except OSError:
                            pass
            if removed_any:
                purged += 1
        # le righe DB restano (audit): non cancelliamo dms_documents/versions
    finally:
        conn.close()

    return {"soft_deleted": soft_deleted, "purged": purged}


def run_daily_jobs(today: date | None = None) -> Dict[str, int]:
    """Esegue tutti i job giornalieri. Idempotente sulle notifiche."""
    today = today or date.today()
    notifs = expiry_scan(today)
    ret = retention_sweep(today)
    _log.info("[scheduler] daily jobs: %d expiry notifications, retention %s", notifs, ret)
    return {"expiry_notifications": notifs, **ret}


async def _loop() -> None:
    """Tick orario; esegue i job una volta al giorno (gating su data)."""
    from modules.notifications_manager import get_state, set_state
    while True:
        try:
            today = date.today().isoformat()
            if get_state("last_run_date") != today:
                await asyncio.to_thread(run_daily_jobs)
                set_state("last_run_date", today)
        except Exception as e:  # noqa: BLE001
            _log.warning("[scheduler] tick failed: %s", e)
        await asyncio.sleep(3600)  # 1h


def install_scheduler(app) -> None:
    """Registra il loop sullo startup di FastAPI, se SCHEDULER_ENABLED."""
    if os.environ.get("SCHEDULER_ENABLED", "0").strip() not in ("1", "true", "True"):
        _log.info("[scheduler] disabled (set SCHEDULER_ENABLED=1 to enable)")
        return

    @app.on_event("startup")
    async def _start_scheduler():  # pragma: no cover
        asyncio.create_task(_loop())
        _log.info("[scheduler] started (hourly tick, daily jobs)")
