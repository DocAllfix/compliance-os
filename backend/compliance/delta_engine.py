"""
ComplianceOS — Delta Engine.

Compares two compliance analyses and returns per-clause deltas.
Used to show improvement or regression between analysis runs.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from modules.db_manager import get_compliance_analysis


def compare_analyses(
    analysis_id_new: str,
    analysis_id_old: str,
) -> Dict[str, Any]:
    """
    Compare two analyses and return per-clause deltas.

    Returns:
        {
            "analysis_new": str,
            "analysis_old": str,
            "company": str,
            "overall_delta": int,          # new_score - old_score
            "clauses": [
                {
                    "clause_id": str,
                    "clause_title": str,
                    "score_old": int,
                    "score_new": int,
                    "delta": int,           # positive = improved
                    "severity_old": str,
                    "severity_new": str,
                    "severity_changed": bool,
                    "direction": "improved" | "regressed" | "unchanged",
                }
            ]
        }
    """
    row_new = get_compliance_analysis(analysis_id_new)
    row_old = get_compliance_analysis(analysis_id_old)

    if not row_new or not row_old:
        missing = analysis_id_new if not row_new else analysis_id_old
        return {"error": f"Analysis not found: {missing}"}

    result_new = _parse_result(row_new)
    result_old = _parse_result(row_old)

    if not result_new or not result_old:
        return {"error": "Could not parse analysis results"}

    clauses_new = _extract_clauses(result_new)
    clauses_old = _extract_clauses(result_old)

    clause_deltas = []
    all_ids = set(clauses_new.keys()) | set(clauses_old.keys())

    for clause_id in sorted(all_ids):
        c_new = clauses_new.get(clause_id)
        c_old = clauses_old.get(clause_id)

        if c_new and c_old:
            score_new = c_new.get("score", 0)
            score_old = c_old.get("score", 0)
            delta = score_new - score_old
            sev_new = c_new.get("severity", "")
            sev_old = c_old.get("severity", "")
            clause_deltas.append({
                "clause_id":        clause_id,
                "clause_title":     c_new.get("clause_title", clause_id),
                "score_old":        score_old,
                "score_new":        score_new,
                "delta":            delta,
                "severity_old":     sev_old,
                "severity_new":     sev_new,
                "severity_changed": sev_new != sev_old,
                "direction":        "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged",
            })
        elif c_new:
            clause_deltas.append({
                "clause_id":    clause_id,
                "clause_title": c_new.get("clause_title", clause_id),
                "score_old":    None,
                "score_new":    c_new.get("score", 0),
                "delta":        None,
                "severity_old": None,
                "severity_new": c_new.get("severity", ""),
                "severity_changed": False,
                "direction":    "new",
            })

    # Overall score delta (first norm)
    def _overall(result: Dict) -> int:
        norms = result.get("norms") or []
        return norms[0].get("overall_score", 0) if norms else 0

    overall_new = _overall(result_new)
    overall_old = _overall(result_old)

    return {
        "analysis_new":   analysis_id_new,
        "analysis_old":   analysis_id_old,
        "company":        result_new.get("company", ""),
        "overall_new":    overall_new,
        "overall_old":    overall_old,
        "overall_delta":  overall_new - overall_old,
        "clauses":        clause_deltas,
    }


def _parse_result(row: Dict) -> Optional[Dict]:
    try:
        result_json = row.get("result_json")
        if isinstance(result_json, str):
            return json.loads(result_json)
        if isinstance(result_json, dict):
            return result_json
    except Exception:
        pass
    return None


def _extract_clauses(result: Dict) -> Dict[str, Dict]:
    out = {}
    for norm in (result.get("norms") or []):
        for clause in (norm.get("clauses") or []):
            cid = clause.get("clause_id")
            if cid:
                out[cid] = clause
    return out
