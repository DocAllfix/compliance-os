"""
Sprint G.2 (rivisto) — repair script per analisi salvate prima del fix.

Le analisi salvate prima del fix di Sprint G hanno i file_name corrotti
(cp437 misread di bytes UTF-8). Esempio:
    "Idoneita╠Ç BRUNO.pdf"   →   "Idonietà BRUNO.pdf"

Lo script attraversa tutte le righe in `compliance_analyses` e:
  1. Carica result_json
  2. Applica _repair_zip_name a tutti i file_name (sources, expiry_report,
     evidence_used)
  3. Salva il result_json riparato

Uso:
    python -m modules.repair_zip_names              # dry-run (default)
    python -m modules.repair_zip_names --apply      # scrive davvero
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from pathlib import Path

# Forza stdout in UTF-8 per gestire i caratteri italiani
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# Import path setup
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

from compliance.pipeline import _repair_zip_name  # noqa: E402

DB_PATH = BACKEND / "data" / "audit.db"


def _walk_and_repair(obj, counter: dict) -> object:
    """Ricorsivamente cerca chiavi 'file_name' e applica _repair_zip_name."""
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k == "file_name" and isinstance(v, str):
                repaired = _repair_zip_name(v)
                if repaired != v:
                    counter["fixed"] += 1
                    counter["examples"].append((v, repaired))
                new[k] = repaired
            else:
                new[k] = _walk_and_repair(v, counter)
        return new
    if isinstance(obj, list):
        return [_walk_and_repair(x, counter) for x in obj]
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default dry-run)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT id, result_json FROM compliance_analyses")
    rows = cur.fetchall()
    print(f"Found {len(rows)} analyses in DB")

    total_fixed = 0
    for aid, result_json_str in rows:
        if not result_json_str:
            continue
        try:
            data = json.loads(result_json_str)
        except Exception as e:
            print(f"  [{aid}] JSON parse error: {e}")
            continue

        counter = {"fixed": 0, "examples": []}
        repaired = _walk_and_repair(data, counter)
        if counter["fixed"] > 0:
            print(f"\n[{aid}] {counter['fixed']} file_name riparati")
            for orig, fix in counter["examples"][:3]:
                print(f"    {orig!r}")
                print(f" →  {fix!r}")
            total_fixed += counter["fixed"]
            if args.apply:
                cur.execute(
                    "UPDATE compliance_analyses SET result_json=? WHERE id=?",
                    (json.dumps(repaired, ensure_ascii=False), aid),
                )

    if args.apply:
        conn.commit()
        print(f"\n✓ Applied. Total file_name riparati: {total_fixed}")
    else:
        print(f"\n[dry-run] Total file_name riparati: {total_fixed} (re-run con --apply per scrivere)")

    conn.close()


if __name__ == "__main__":
    main()
