"""
Sprint I.B — one-off cleanup for analyses persisted BEFORE the severity-floor
marker fix. Strips the leaked "[severity floor applied — clause is critical] "
prefix from every ClauseGap.finding in result_json, and realigns scores into
the displayed severity band so UI no longer shows "score 70 / MAJOR".

Idempotent: re-running on already-cleaned data is a no-op.

Usage:
    python -m modules.clean_severity_floor_marker             # dry-run (default)
    python -m modules.clean_severity_floor_marker --apply     # write changes
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

# Force UTF-8 stdout for Windows consoles that may otherwise mojibake the
# em-dash and ellipsis characters used in markers and findings.
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

DB_PATH = BACKEND / "data" / "audit.db"

# Match "[severity floor applied — clause is critical] " or "...standard] " etc.
# Both em-dash and ASCII hyphen are tolerated, with optional surrounding spaces.
_MARKER_RE = re.compile(
    r"^\s*\[severity\s+floor\s+applied\s*[—\-]\s*clause\s+is\s+\w+\]\s*",
    re.IGNORECASE,
)

_SEVERITY_SCORE_CEILING = {
    "MAJOR":       29,
    "MINOR":       59,
    "OBSERVATION": 84,
    "CONFORMANT":  100,
}


def _clean_clause(clause: dict, counter: dict) -> None:
    finding = clause.get("finding") or ""
    cleaned = _MARKER_RE.sub("", finding)
    if cleaned != finding:
        clause["finding"] = cleaned
        counter["marker_stripped"] += 1

    # Realign score into severity band (only when score exceeds the ceiling).
    severity = clause.get("severity")
    ceiling = _SEVERITY_SCORE_CEILING.get(severity)
    if ceiling is not None:
        score = clause.get("score")
        if isinstance(score, (int, float)) and score > ceiling:
            clause["_original_llm_score"] = score  # preserved for audit
            clause["score"] = ceiling
            counter["score_realigned"] += 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the cleaned result_json back to the DB (default: dry-run).",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT id, result_json FROM compliance_analyses")
    rows = cur.fetchall()
    print(f"Found {len(rows)} analyses in DB")

    grand = {"marker_stripped": 0, "score_realigned": 0, "analyses_touched": 0}

    for aid, result_json_str in rows:
        if not result_json_str:
            continue
        try:
            data = json.loads(result_json_str)
        except Exception as e:
            print(f"  [{aid}] JSON parse error: {e}")
            continue

        local = {"marker_stripped": 0, "score_realigned": 0}
        for norm in data.get("norms", []) or []:
            for clause in norm.get("clauses", []) or []:
                _clean_clause(clause, local)
        # top_gaps shares the same ClauseGap shape and may carry the marker too
        for clause in data.get("top_gaps", []) or []:
            _clean_clause(clause, local)

        if local["marker_stripped"] or local["score_realigned"]:
            grand["analyses_touched"] += 1
            grand["marker_stripped"] += local["marker_stripped"]
            grand["score_realigned"] += local["score_realigned"]
            print(
                f"\n[{aid}] markers stripped: {local['marker_stripped']}, "
                f"scores realigned: {local['score_realigned']}"
            )
            if args.apply:
                cur.execute(
                    "UPDATE compliance_analyses SET result_json=? WHERE id=?",
                    (json.dumps(data, ensure_ascii=False), aid),
                )

    if args.apply:
        conn.commit()
        print(
            f"\nApplied. Touched {grand['analyses_touched']} analyses "
            f"({grand['marker_stripped']} markers stripped, "
            f"{grand['score_realigned']} scores realigned)."
        )
    else:
        print(
            f"\n[dry-run] Would touch {grand['analyses_touched']} analyses "
            f"({grand['marker_stripped']} markers, "
            f"{grand['score_realigned']} scores). Re-run with --apply to write."
        )

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
