"""
Helper accessors for ISO clause metadata.

Returns the four derived fields (criticality_tier, severity_floor, weight,
expiry_relevant) for any clause across all three norms (9001 / 14001 / 45001).

Resolution order, per field:
  1. Explicit value in the clause dict (override path for future tuning).
  2. Deterministic derivation from existing signals (is_spof, HIGH_FREQUENCY
     lists, area patterns).

This lets us tune per-clause overrides later without forcing a bulk edit
of every clause dict today.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Areas (case-insensitive substring match on clause["area"] or clause["title"])
# whose documents typically carry an expiry date in the field. Used by Phase 2.5.
_EXPIRY_RELEVANT_KEYWORDS = (
    "competence", "training", "awareness",          # 7.2, 7.3
    "documented information",                        # 7.5
    "monitoring", "internal audit",                 # 9.1, 9.2
    "nonconformity", "corrective action",           # 10.2
    "hazard identification", "risk assessment",     # 45001 6.1.2 (DVR)
    "emergency",                                     # 14001 8.2, 45001 8.2
    "calibration",                                   # 9001 7.1.5
    "legal", "compliance obligations",              # 14001 6.1.3, 9.1.2
    "contractor",                                    # 45001 8.1.4
    "worker participation", "consultation",         # 45001 5.4
    "incident",                                      # 45001 10.2
    "operational control", "waste",                 # 14001 8.1
)


def _is_high_frequency(clause_id: str) -> bool:
    """True if the clause is in any norm's HIGH_FREQUENCY list."""
    from compliance.iso_clauses.iso9001_clauses import ISO9001_HIGH_FREQUENCY_CLAUSES
    from compliance.iso_clauses.iso14001_clauses import ISO14001_HIGH_FREQUENCY_CLAUSES
    from compliance.iso_clauses.iso45001_clauses import ISO45001_HIGH_FREQUENCY_CLAUSES

    return (
        clause_id in ISO9001_HIGH_FREQUENCY_CLAUSES
        or clause_id in ISO14001_HIGH_FREQUENCY_CLAUSES
        or clause_id in ISO45001_HIGH_FREQUENCY_CLAUSES
    )


def _is_context_passing(clause: Dict[str, Any]) -> bool:
    """
    True for purely contextual / informational clauses (typically §4.x of every
    norm: understanding the organisation, interested parties, scope, EMS scope).
    These are advisory anchors, not operational requirements; severity floor None.
    """
    area = str(clause.get("area", "")).lower()
    title = str(clause.get("title", "")).lower()
    if "context" in area:
        return True
    # Section 4 of any norm is contextual unless the area says otherwise
    cid = str(clause.get("id", ""))
    parts = cid.split("_")
    if len(parts) >= 2 and parts[1] == "4":
        return True
    if "understanding the organisation" in title:
        return True
    if "interested parties" in title and "context" in area:
        return True
    return False


def get_criticality_tier(clause: Dict[str, Any]) -> str:
    """
    Returns "critical" | "standard" | "passing".

    Rules:
      - critical: is_spof=True OR in any HIGH_FREQUENCY list
      - passing: context/informational clauses (typically §4.x)
      - standard: everything else
    """
    explicit = clause.get("criticality_tier")
    if explicit in ("critical", "standard", "passing"):
        return explicit

    if clause.get("is_spof") is True:
        return "critical"
    if _is_high_frequency(str(clause.get("id", ""))):
        return "critical"
    if _is_context_passing(clause):
        return "passing"
    return "standard"


def get_severity_floor(clause: Dict[str, Any]) -> Optional[str]:
    """
    Returns "MAJOR" | "MINOR" | "OBSERVATION" | None.

    The floor is the minimum severity to apply if zero pertinent evidence is
    found by retrieval (or if the LLM hallucinates citations and they are all
    discarded). None means no floor.
    """
    if "severity_floor" in clause:
        return clause["severity_floor"]  # may be None explicitly

    tier = get_criticality_tier(clause)
    if tier == "critical":
        return "MAJOR"
    if tier == "standard":
        return "MINOR"
    return None  # passing


def get_weight(clause: Dict[str, Any]) -> int:
    """
    Returns the scoring weight 1-5 for aggregating overall norm scores.

      critical → 5
      standard → 3
      passing  → 1
    """
    explicit = clause.get("weight")
    if isinstance(explicit, int) and 1 <= explicit <= 5:
        return explicit

    tier = get_criticality_tier(clause)
    return {"critical": 5, "standard": 3, "passing": 1}[tier]


def is_expiry_relevant(clause: Dict[str, Any]) -> bool:
    """
    True if documents typically linked to this clause carry an expiry date
    (training certificates, calibration records, DVR revision, etc.).

    Used by Phase 2.5 (expiry check) to know which clauses to flag when an
    expired document is found.
    """
    explicit = clause.get("expiry_relevant")
    if isinstance(explicit, bool):
        return explicit

    haystack = (
        str(clause.get("area", "")) + " " +
        str(clause.get("title", ""))
    ).lower()
    return any(kw in haystack for kw in _EXPIRY_RELEVANT_KEYWORDS)


def summarise_tiering(clauses: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Diagnostic helper: count how many clauses fall in each tier."""
    counts = {"critical": 0, "standard": 0, "passing": 0}
    for clause in clauses.values():
        counts[get_criticality_tier(clause)] += 1
    return counts
