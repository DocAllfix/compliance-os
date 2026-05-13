"""
ComplianceOS — Phase 2.5: Expiry Check.

Structured, deterministic extraction of document expiry status from the
evidence cards produced by Phase 2.

Design decision (Sprint 2):
    The original plan called for an LLM call with a Python fallback. After
    review we use **Python only** — arithmetic on dates and a fixed
    doc_type → ISO clause lookup table is strictly more reliable than an
    LLM here, faster (no extra API call), zero token cost, and trivially
    testable. The LLM stays out of the loop in Phase 2.5.

Inputs:
    - The raw evidence YAML string from Phase 2 (already produced)
    - The audit / analysis date

Output (dict matching backend.compliance.schemas.ExpiryReport):
    {
      "audit_date": "YYYY-MM-DD",
      "expired_documents": [...],
      "expiring_soon":     [...],
      "no_expiry_information": <int>,
    }

Severity rules (deterministic):
    days_overdue > 180                          → MAJOR
    30 <= days_overdue <= 180                   → MINOR
    0 <= days_overdue < 30                      → OBSERVATION
    -30 <= days_overdue < 0                     → OBSERVATION (expires <30 days)
    -90 <= days_overdue < -30                   → INFO        (expires <90 days)
    days_overdue < -90 or expiry_date == null   → not reported
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional


# ── Public API ────────────────────────────────────────────────────────────────

def run_expiry_check(
    evidence_yaml: str,
    audit_date: Optional[date] = None,
    emitter: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Phase 2.5 entry point. Returns a dict serialisable to ExpiryReport.

    Args:
        evidence_yaml: raw YAML string from _extract_evidence (Phase 2)
        audit_date:    reference date (defaults to today, UTC date)
        emitter:       optional SSE progress callback

    Returns:
        dict with keys: audit_date, expired_documents, expiring_soon,
        no_expiry_information
    """
    if audit_date is None:
        from datetime import timezone as _tz
        audit_date = datetime.now(_tz.utc).date()

    def emit(pct: float, msg: str) -> None:
        if emitter:
            try:
                emitter(pct, msg)
            except Exception:
                pass

    # Reuse the existing tolerant parser so we don't duplicate YAML handling
    from compliance.gap_analyzer import _parse_evidence_yaml

    cards = _parse_evidence_yaml(evidence_yaml)
    emit(36.0, f"Phase 2.5: scanning {len(cards)} evidence cards for expiries…")

    expired: List[Dict[str, Any]] = []
    expiring_soon: List[Dict[str, Any]] = []
    no_expiry = 0

    for card in cards:
        expiry_raw = card.get("expiry_date")
        if not expiry_raw or expiry_raw in ("null", "None"):
            no_expiry += 1
            continue

        expiry = _parse_iso_date(expiry_raw)
        if expiry is None:
            # Unparseable expiry string — treat as "no information"
            no_expiry += 1
            continue

        days_overdue = (audit_date - expiry).days
        severity = _severity_for_days(days_overdue)
        if severity is None:
            # Outside the reporting window (more than 90 days in the future)
            continue

        record = {
            "file_name":          str(card.get("file_name", "")),
            "doc_type":           str(card.get("doc_type", "other")),
            "evidence_id":        str(card.get("evidence_id", "")),
            "expiry_date":        expiry.strftime("%Y-%m-%d"),
            "days_overdue":       days_overdue,
            "severity":           severity,
            "linked_iso_clauses": _doc_type_to_clauses(str(card.get("doc_type", "other"))),
        }
        if days_overdue >= 0:
            expired.append(record)
        else:
            expiring_soon.append(record)

    # Sort: expired by most overdue first; expiring_soon by closest first
    expired.sort(key=lambda r: -r["days_overdue"])
    expiring_soon.sort(key=lambda r: r["days_overdue"])  # most negative = furthest out

    emit(
        38.0,
        f"Phase 2.5 complete: {len(expired)} expired, {len(expiring_soon)} expiring soon, "
        f"{no_expiry} with no expiry information.",
    )

    return {
        "audit_date":             audit_date.strftime("%Y-%m-%d"),
        "expired_documents":      expired,
        "expiring_soon":          expiring_soon,
        "no_expiry_information":  no_expiry,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_iso_date(value: Any) -> Optional[date]:
    """Accept YYYY-MM-DD or YYYY-MM or YYYY; return None on failure."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip().strip('"').strip("'")
    if not s or s.lower() in ("null", "none"):
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%d/%m/%Y", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _severity_for_days(days_overdue: int) -> Optional[str]:
    """
    Deterministic severity ladder. Returns None for items outside the
    reporting window (more than 90 days in the future).
    """
    if days_overdue > 180:
        return "MAJOR"
    if days_overdue >= 30:
        return "MINOR"
    if days_overdue >= 0:
        return "OBSERVATION"
    if days_overdue >= -30:
        return "OBSERVATION"
    if days_overdue >= -90:
        return "INFO"
    return None


# Doc-type → canonical ISO clause mapping. Static, debuggable, regression-friendly.
# Sources: ISO 9001:2015, ISO 14001:2015, ISO 45001:2018 + Italian D.Lgs 81/08
# practice (DVR, RSPP/RLS appointments, medical surveillance).
_DOC_TYPE_TO_CLAUSES: Dict[str, List[str]] = {
    "training_record": [
        "ISO 9001 §7.2",
        "ISO 45001 §7.2",
    ],
    "calibration_record": [
        "ISO 9001 §7.1.5",
    ],
    "risk_assessment": [
        # DVR (Italian risk assessment) is OH&S primary; also relevant for 9001 6.1
        "ISO 45001 §6.1.2",
        "ISO 9001 §6.1",
        "ISO 14001 §6.1.2",
    ],
    "audit_report": [
        "ISO 9001 §9.2",
        "ISO 14001 §9.2",
        "ISO 45001 §9.2",
    ],
    "management_review": [
        "ISO 9001 §9.3",
        "ISO 14001 §9.3",
        "ISO 45001 §9.3",
    ],
    "nonconformity_record": [
        "ISO 9001 §10.2",
        "ISO 14001 §10.2",
        "ISO 45001 §10.2",
    ],
    "legal_register": [
        "ISO 14001 §6.1.3",
        "ISO 45001 §6.1.3",
    ],
    "emergency_plan": [
        "ISO 14001 §8.2",
        "ISO 45001 §8.2",
    ],
    "certificate": [
        # Fire safety / RSPP / RLS appointments, ISO certificates
        "ISO 45001 §8.2",
        "ISO 9001 §7.2",
    ],
    "supplier_document": [
        "ISO 9001 §8.4",
    ],
    "contract_specification": [
        "ISO 9001 §8.2",
    ],
    "quality_manual": [
        "ISO 9001 §7.5",
    ],
    "procedure": [
        "ISO 9001 §7.5",
    ],
    "policy": [
        "ISO 9001 §5.2",
        "ISO 14001 §5.2",
        "ISO 45001 §5.2",
    ],
    "record": [
        "ISO 9001 §7.5",
    ],
    "objective_plan": [
        "ISO 9001 §6.2",
        "ISO 14001 §6.2",
        "ISO 45001 §6.2",
    ],
    "communication_record": [
        "ISO 9001 §7.4",
        "ISO 14001 §7.4",
        "ISO 45001 §7.4",
    ],
    "other": [],
}


def _doc_type_to_clauses(doc_type: str) -> List[str]:
    """Return the canonical ISO clauses linked to a doc_type. Empty list if unknown."""
    return list(_DOC_TYPE_TO_CLAUSES.get(doc_type.lower().strip(), []))
