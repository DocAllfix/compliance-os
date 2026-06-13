"""
Amisys QHSE — Delta Engine (Fase 5 consolidamento).

Compares two compliance analyses and returns per-clause deltas — the
"47% → 64%, two Majors closed, one new Minor" aha moment of PRODUCT.md and
the recurring-usage requirement of the PRD (§2.7).

Fase 5 upgrades over the original (written during Sprint 3, never exposed):
  - overall delta computed PER NORM (the old version read only norms[0])
  - clauses present only in the OLD analysis are reported as "removed"
  - severity changes are flagged even when the score is unchanged
  - documented-info coverage delta (items resolved / newly missing)
  - summary counters ready for the UI
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from modules.db_manager import get_compliance_analysis

_SEVERITY_RANK = {"CONFORMANT": 0, "OBSERVATION": 1, "MINOR": 2, "MAJOR": 3}


def compare_analyses(
    analysis_id_new: str,
    analysis_id_old: str,
) -> Dict[str, Any]:
    """
    Compare two analyses and return per-clause deltas.

    Returns:
        {
            "analysis_new" / "analysis_old": str,
            "company": str,
            "norms": [ {norm, overall_new, overall_old, overall_delta} ],
            "clauses": [
                {clause_id, clause_title, score_old, score_new, delta,
                 severity_old, severity_new, severity_changed,
                 direction: improved|regressed|unchanged|new|removed}
            ],
            "summary": {improved, regressed, unchanged, new, removed,
                        severity_upgrades, severity_downgrades},
            "documented_info": {resolved: [...], newly_missing: [...]} | None,
        }
        oppure {"error": "..."} se una delle analisi manca o non parsa.
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

    clause_deltas: List[Dict[str, Any]] = []
    severity_upgrades = 0    # peggioramenti (es. MINOR → MAJOR)
    severity_downgrades = 0  # miglioramenti (es. MAJOR → MINOR)

    for clause_id in sorted(set(clauses_new) | set(clauses_old)):
        c_new = clauses_new.get(clause_id)
        c_old = clauses_old.get(clause_id)

        if c_new and c_old:
            score_new = int(c_new.get("score", 0))
            score_old = int(c_old.get("score", 0))
            delta = score_new - score_old
            sev_new = str(c_new.get("severity", ""))
            sev_old = str(c_old.get("severity", ""))
            sev_changed = sev_new != sev_old

            # Fase 5: la severity decide la direzione anche a score invariato
            if sev_changed:
                worse = _SEVERITY_RANK.get(sev_new, 0) > _SEVERITY_RANK.get(sev_old, 0)
                direction = "regressed" if worse else "improved"
                if worse:
                    severity_upgrades += 1
                else:
                    severity_downgrades += 1
            else:
                direction = (
                    "improved" if delta > 0
                    else "regressed" if delta < 0
                    else "unchanged"
                )

            clause_deltas.append({
                "clause_id":        clause_id,
                "clause_title":     c_new.get("clause_title", clause_id),
                "score_old":        score_old,
                "score_new":        score_new,
                "delta":            delta,
                "severity_old":     sev_old,
                "severity_new":     sev_new,
                "severity_changed": sev_changed,
                "direction":        direction,
            })
        elif c_new:
            clause_deltas.append({
                "clause_id":    clause_id,
                "clause_title": c_new.get("clause_title", clause_id),
                "score_old":    None,
                "score_new":    int(c_new.get("score", 0)),
                "delta":        None,
                "severity_old": None,
                "severity_new": str(c_new.get("severity", "")),
                "severity_changed": False,
                "direction":    "new",
            })
        else:  # solo nella vecchia analisi (norma deselezionata, set custom…)
            clause_deltas.append({
                "clause_id":    clause_id,
                "clause_title": c_old.get("clause_title", clause_id),
                "score_old":    int(c_old.get("score", 0)),
                "score_new":    None,
                "delta":        None,
                "severity_old": str(c_old.get("severity", "")),
                "severity_new": None,
                "severity_changed": False,
                "direction":    "removed",
            })

    # Overall per norma (Fase 5: tutte le norme, non solo la prima)
    overall_new_by_norm = {n.get("norm"): n.get("overall_score", 0) for n in (result_new.get("norms") or [])}
    overall_old_by_norm = {n.get("norm"): n.get("overall_score", 0) for n in (result_old.get("norms") or [])}
    norms_delta = []
    for norm in sorted(set(overall_new_by_norm) | set(overall_old_by_norm)):
        o_new = overall_new_by_norm.get(norm)
        o_old = overall_old_by_norm.get(norm)
        norms_delta.append({
            "norm": norm,
            "overall_new": o_new,
            "overall_old": o_old,
            "overall_delta": (o_new - o_old) if (o_new is not None and o_old is not None) else None,
        })

    summary = {
        "improved":   sum(1 for c in clause_deltas if c["direction"] == "improved"),
        "regressed":  sum(1 for c in clause_deltas if c["direction"] == "regressed"),
        "unchanged":  sum(1 for c in clause_deltas if c["direction"] == "unchanged"),
        "new":        sum(1 for c in clause_deltas if c["direction"] == "new"),
        "removed":    sum(1 for c in clause_deltas if c["direction"] == "removed"),
        "severity_upgrades":   severity_upgrades,
        "severity_downgrades": severity_downgrades,
    }

    return {
        "analysis_new":   analysis_id_new,
        "analysis_old":   analysis_id_old,
        "company":        result_new.get("company", ""),
        "date_new":       result_new.get("analysis_date", ""),
        "date_old":       result_old.get("analysis_date", ""),
        "norms":          norms_delta,
        "clauses":        clause_deltas,
        "summary":        summary,
        "documented_info": _documented_info_delta(result_new, result_old),
    }


def _documented_info_delta(result_new: Dict, result_old: Dict) -> Optional[Dict[str, Any]]:
    """Fase 5 — confronta gli item ABSENT del documented-info check (Phase 2.6)."""
    di_new = result_new.get("documented_info_report")
    di_old = result_old.get("documented_info_report")
    if not di_new and not di_old:
        return None

    def absent_set(di) -> set:
        if not di:
            return set()
        return {
            (i.get("norm"), i.get("item"))
            for i in (di.get("items") or [])
            if i.get("status") == "ABSENT"
        }

    a_new, a_old = absent_set(di_new), absent_set(di_old)
    return {
        "resolved":      sorted(f"{n} — {i}" for (n, i) in (a_old - a_new)),
        "newly_missing": sorted(f"{n} — {i}" for (n, i) in (a_new - a_old)),
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
    out: Dict[str, Dict] = {}
    for norm in (result.get("norms") or []):
        for clause in (norm.get("clauses") or []):
            cid = clause.get("clause_id")
            if cid:
                out[cid] = clause
    return out
