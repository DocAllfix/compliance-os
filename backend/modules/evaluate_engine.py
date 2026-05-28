"""
Sprint I.F — Evaluation tool: human-in-the-loop precision/recall measurement
for the compliance engine.

The premise: we don't have a pre-existing ground-truth of non-conformities for
the analysed document sets. So we build the ground-truth post-hoc by walking
the engine's findings clause-by-clause and recording an expert judgement on
each one. Once enough findings are judged we can compute real precision (how
often the engine is right when it claims a NC) and the part of recall that is
observable from the engine output.

What we can measure precisely from this loop:
  * Precision per severity: of the findings the engine flagged at each
    severity, how many the expert agrees with.
  * Conformance accuracy: of the clauses the engine marked CONFORMANT, how
    many the expert agrees with.

What requires an additional manual sweep of the document set:
  * True recall (NCs the engine missed entirely). The reviewer can record
    these as free-form annotations during the review — they roll up into the
    final report but the tool doesn't pretend to enumerate them automatically.

Usage:
    python -m modules.evaluate_engine list                       # list analyses available
    python -m modules.evaluate_engine review <analysis_id>       # interactive review
    python -m modules.evaluate_engine report <analysis_id>       # show aggregated metrics

Review state is persisted in temp/engine_review/<analysis_id>.json — so you
can interrupt at any time (Ctrl-C) and resume later.
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Force UTF-8 stdout for Italian / accented characters on Windows consoles.
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

DB_PATH = BACKEND / "data" / "audit.db"
REVIEW_DIR = BACKEND / "temp" / "engine_review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)


# ─── Verdict vocabulary ───────────────────────────────────────────────────────
# The reviewer answers one of:
#   T  TRUE_POSITIVE        — engine's verdict matches expert judgement
#   F  FALSE_POSITIVE       — engine flagged a NC that isn't actually a NC
#   U  UNDER_SEVERITY       — there's a real issue, but engine over-rated it (e.g. MAJOR
#                              when the expert would have called it MINOR / OBSERVATION)
#   O  OVER_SEVERITY        — engine under-rated a real issue (rarer; e.g. MINOR
#                              when expert would have called it MAJOR)
#   M  MISSED               — engine declared CONFORMANT or OBSERVATION but expert
#                              sees a real gap the engine didn't surface
#   S  SKIP                 — defer judgement (will revisit later)
VERDICTS = {
    "t": ("TRUE_POSITIVE", "Engine is correct"),
    "f": ("FALSE_POSITIVE", "Engine flagged a NC that isn't one"),
    "u": ("OVER_RATED", "Real issue but engine over-rated severity"),
    "o": ("UNDER_RATED", "Real issue, engine under-rated severity"),
    "m": ("MISSED_BY_ENGINE", "Engine missed something the expert sees"),
    "s": ("SKIP", "Defer judgement"),
}


def _review_path(analysis_id: str) -> Path:
    return REVIEW_DIR / f"{analysis_id}.json"


def _load_review(analysis_id: str) -> Dict[str, Any]:
    p = _review_path(analysis_id)
    if not p.exists():
        return {"analysis_id": analysis_id, "judgements": {}, "missed_ncs": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save_review(state: Dict[str, Any]) -> None:
    p = _review_path(state["analysis_id"])
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
    from modules.db_manager import get_compliance_analysis
    row = get_compliance_analysis(analysis_id)
    if not row or not row.get("result_json"):
        return None
    return json.loads(row["result_json"]) if isinstance(row["result_json"], str) else row["result_json"]


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_list() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT id, company, analysis_date, major_count, minor_count, "
        "observation_count, conformant_count, documents_analyzed, status "
        "FROM compliance_analyses ORDER BY analysis_date DESC"
    )
    rows = cur.fetchall()
    print(f"\n{len(rows)} analyses in DB:\n")
    for r in rows:
        aid, company, date, maj, mnr, obs, conf, docs, status = r
        review = _review_path(aid)
        review_status = "no review" if not review.exists() else "review in progress"
        print(
            f"  {aid}  | {company or '(no company)':30s}  "
            f"M={maj or 0:2d} m={mnr or 0:2d} O={obs or 0:2d} C={conf or 0:2d}  "
            f"docs={docs or 0:3d}  | {status:11s} | {review_status}"
        )
    print()
    conn.close()
    return 0


def cmd_review(analysis_id: str) -> int:
    result = _load_analysis(analysis_id)
    if not result:
        print(f"Analysis '{analysis_id}' not found in DB.")
        return 2

    state = _load_review(analysis_id)
    judgements: Dict[str, Dict[str, Any]] = state["judgements"]

    # Flatten all clauses across norms with stable identifier
    all_clauses: List[Dict[str, Any]] = []
    for norm in result.get("norms", []) or []:
        norm_name = norm.get("norm", "?")
        for clause in norm.get("clauses", []) or []:
            all_clauses.append({"_norm": norm_name, **clause})

    company = result.get("company", "(no company)")
    print(
        f"\n=== Engine review — {analysis_id} ===\n"
        f"Company: {company}\n"
        f"Clauses to review: {len(all_clauses)}\n"
        f"Already judged: {len(judgements)}\n"
    )
    _print_legend()

    for idx, clause in enumerate(all_clauses, start=1):
        cid = clause["clause_id"]
        if cid in judgements and judgements[cid].get("verdict") not in (None, "SKIP"):
            continue  # already judged (non-skip)

        _print_clause(idx, len(all_clauses), clause, company)

        # Prompt
        try:
            choice = input("\n  Verdict [t/f/u/o/m/s, ? help, q quit & save]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\nInterrupted. Saving review state…")
            _save_review(state)
            return 0

        if choice == "q":
            print("Saving review state…")
            _save_review(state)
            return 0
        if choice == "?":
            _print_legend()
            # re-prompt by simply continuing the loop without advancing
            # (cheap: we just refuse to record and let the user see again)
            try:
                choice = input("  Verdict: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                _save_review(state); return 0
        if choice not in VERDICTS:
            print(f"  → unrecognised '{choice}', skipping (use 's' to skip explicitly).")
            continue

        verdict_code, verdict_label = VERDICTS[choice][0], VERDICTS[choice][1]
        note = ""
        if choice != "s":
            try:
                note = input("  Note (optional, press Enter to skip): ").strip()
            except (EOFError, KeyboardInterrupt):
                _save_review(state); return 0

        judgements[cid] = {
            "norm": clause["_norm"],
            "clause_title": clause["clause_title"],
            "engine_severity": clause["severity"],
            "engine_score": clause["score"],
            "verdict": verdict_code,
            "note": note,
        }
        # Persist after every judgement so we never lose work.
        _save_review(state)

    print("\nReview complete for all clauses. Run `report` to see metrics.")
    return 0


def cmd_report(analysis_id: str) -> int:
    state = _load_review(analysis_id)
    judgements = state["judgements"]
    if not judgements:
        print("No judgements recorded yet. Run `review` first.")
        return 1

    # Aggregate by engine severity
    from collections import defaultdict
    by_sev: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid, j in judgements.items():
        sev = j["engine_severity"]
        verdict = j["verdict"]
        by_sev[sev]["_total"] += 1
        by_sev[sev][verdict] += 1

    print(f"\n=== Engine evaluation report — {analysis_id} ===\n")
    print(f"Total clauses judged: {len(judgements)}\n")
    print("By engine severity:")
    print(f"  {'severity':12s} {'total':5s}  {'TP':4s} {'FP':4s} {'OVER':4s} {'UNDER':5s} {'MISS':4s} {'SKIP':4s}  precision")
    overall_tp = 0
    overall_decisions = 0
    for sev in ("MAJOR", "MINOR", "OBSERVATION", "CONFORMANT"):
        bucket = by_sev.get(sev, {})
        total = bucket.get("_total", 0)
        if total == 0:
            continue
        tp = bucket.get("TRUE_POSITIVE", 0)
        fp = bucket.get("FALSE_POSITIVE", 0)
        over = bucket.get("OVER_RATED", 0)
        under = bucket.get("UNDER_RATED", 0)
        miss = bucket.get("MISSED_BY_ENGINE", 0)
        skip = bucket.get("SKIP", 0)
        # Precision in the strict sense: of the verdicts the engine produced
        # at this severity, what fraction the expert fully agrees with.
        decided = total - skip
        precision = (tp / decided * 100) if decided else 0
        overall_tp += tp
        overall_decisions += decided
        print(
            f"  {sev:12s} {total:5d}  {tp:4d} {fp:4d} {over:4d} {under:5d} {miss:4d} {skip:4d}   "
            f"{precision:5.1f}%"
        )

    overall_precision = (overall_tp / overall_decisions * 100) if overall_decisions else 0
    print(f"\nOverall precision (TP / decided judgements): {overall_precision:.1f}%")

    missed = state.get("missed_ncs", [])
    if missed:
        print(f"\nNCs the reviewer flagged the engine missed: {len(missed)}")
        for m in missed[:10]:
            print(f"  - {m}")

    print(
        "\nNote on recall: this report measures observable precision and the "
        "MISSED_BY_ENGINE counts. True recall (NCs entirely absent from the "
        "engine output) requires an independent manual sweep of the document "
        "set — record those in state['missed_ncs'] when found."
    )
    return 0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _print_legend() -> None:
    print(
        "  Verdict legend:\n"
        "    t  TRUE_POSITIVE      — engine is correct\n"
        "    f  FALSE_POSITIVE     — engine flagged a NC that isn't one\n"
        "    u  OVER_RATED         — real issue but engine over-rated severity\n"
        "    o  UNDER_RATED        — real issue, engine under-rated severity\n"
        "    m  MISSED_BY_ENGINE   — engine missed something you see\n"
        "    s  SKIP               — defer judgement\n"
        "    q  QUIT & SAVE\n"
    )


def _print_clause(idx: int, total: int, clause: Dict[str, Any], company: str) -> None:
    print(
        f"\n──────────────────────────────────────────────\n"
        f"[{idx}/{total}] {clause['_norm']}  ·  {clause['clause_id']}  ·  {clause['clause_title']}\n"
        f"  engine verdict: {clause['severity']}  |  score {clause['score']}"
        f"  |  SPoF: {bool(clause.get('is_spof'))}\n"
    )
    print(f"  FINDING:\n    {clause.get('finding', '')[:600]}\n")

    sources = clause.get("sources", []) or []
    if sources:
        print(f"  EVIDENCE CITED ({len(sources)}):")
        for s in sources[:4]:
            fn = s.get("file_name", "?")
            excerpt = (s.get("excerpt") or "").replace("\n", " ")
            print(f"    · {fn}")
            print(f"      \"{excerpt[:160]}{'…' if len(excerpt) > 160 else ''}\"")
    else:
        print("  EVIDENCE CITED: (none)")

    rem = clause.get("remediation", {}) or {}
    if rem.get("what"):
        print(
            f"  REMEDIATION:  {rem.get('what','')[:180]}\n"
            f"    who: {rem.get('who','?')}  |  when: {rem.get('when','?')}  |  effort: {rem.get('effort','?')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sprint I.F — human-in-the-loop evaluation tool for ComplianceOS engine.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List analyses in the DB.")
    p_review = sub.add_parser("review", help="Interactively review an analysis.")
    p_review.add_argument("analysis_id")
    p_report = sub.add_parser("report", help="Show aggregated metrics from review state.")
    p_report.add_argument("analysis_id")
    args = parser.parse_args()

    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "review":
        return cmd_review(args.analysis_id)
    if args.cmd == "report":
        return cmd_report(args.analysis_id)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
