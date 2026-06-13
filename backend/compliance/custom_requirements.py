"""
Amisys QHSE — Custom requirement sets (Fase 7, PRD §1.4.4b).

Il PRD chiede la valutazione anche contro "the corresponding requirement
defined within the organization's own operating criteria" — non solo le
clausole ISO. Il registry clausole è data-driven, quindi i criteri operativi
del cliente sono set YAML con LO STESSO SHAPE delle clausole: il motore
(Stage A batch, Stage B deep verification, severity floor, cite-or-fail)
li processa senza alcuna modifica.

I set vivono in `backend/data/requirement_sets/<name>.yaml`:

    label: "Hartwell Operating Criteria"          # identificatore (usato come "norma")
    description: "..."
    requirements:
      - id: hartwell_oc_01
        title: "OC-1 Supplier escalation protocol"
        evidence_keywords: [...]
        atomic_requirements: [...]                 # opzionale, abilita il deep pass
        remediation_template: {what, who, when_major, when_minor, effort}

Il `label` entra in `CompanyContext.norms` accanto agli standard ISO; nel
result il set appare come un NormGapReport con norm = label.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_log = logging.getLogger("compliance.custom_requirements")

REQUIREMENT_SETS_DIR = Path(__file__).resolve().parent.parent / "data" / "requirement_sets"

# Campi obbligatori per ogni requisito (shape del registry clausole)
_REQUIRED_FIELDS = ("id", "title")
_REMEDIATION_FIELDS = ("what", "who", "when_major", "when_minor", "effort")

# Le "norme" ISO ufficiali: un set custom non può usare questi label
_RESERVED_LABELS = {"ISO 9001:2015", "ISO 14001:2015", "ISO 45001:2018"}


def list_requirement_sets() -> List[Dict[str, Any]]:
    """Elenca i set disponibili: [{name, label, description, requirement_count}]."""
    out: List[Dict[str, Any]] = []
    if not REQUIREMENT_SETS_DIR.exists():
        return out
    for path in sorted(REQUIREMENT_SETS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out.append({
                "name": path.stem,
                "label": str(data.get("label", path.stem)),
                "description": str(data.get("description", "") or "")[:300],
                "requirement_count": len(data.get("requirements") or []),
            })
        except Exception as e:
            _log.warning("Requirement set %s illeggibile: %s", path.name, e)
    return out


def load_requirement_set_by_label(label: str) -> Optional[Dict[str, Any]]:
    """Carica e valida il set con il label dato.

    Ritorna un dict con lo shape del registry norme del gap_analyzer:
        {"clauses": {id: clause_dict}, "label": str, "high_freq": set()}
    oppure None se il label non corrisponde a nessun set valido.
    """
    if not REQUIREMENT_SETS_DIR.exists():
        return None
    for path in REQUIREMENT_SETS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            _log.warning("Requirement set %s illeggibile: %s", path.name, e)
            continue
        if str(data.get("label", "")) != label:
            continue
        return _validate_and_shape(data, path.name)
    return None


def _validate_and_shape(data: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    label = str(data.get("label", "") or "").strip()
    if not label:
        _log.warning("%s: 'label' mancante — set ignorato", source)
        return None
    if label in _RESERVED_LABELS:
        _log.warning("%s: il label %r è riservato agli standard ISO — set ignorato",
                     source, label)
        return None

    raw_reqs = data.get("requirements") or []
    if not isinstance(raw_reqs, list) or not raw_reqs:
        _log.warning("%s: nessun requisito — set ignorato", source)
        return None

    clauses: Dict[str, Dict[str, Any]] = {}
    for i, req in enumerate(raw_reqs):
        if not isinstance(req, dict):
            continue
        missing = [f for f in _REQUIRED_FIELDS if not str(req.get(f, "") or "").strip()]
        if missing:
            _log.warning("%s: requisito #%d senza %s — saltato", source, i, missing)
            continue

        cid = _safe_id(str(req["id"]))
        remediation = req.get("remediation_template") or {}
        # Default difendibili: il motore esige il template completo
        shaped_rem = {
            "what": str(remediation.get("what", "") or f"Address the requirement: {req['title']}"),
            "who": str(remediation.get("who", "") or "Process owner"),
            "when_major": str(remediation.get("when_major", "") or "30 days"),
            "when_minor": str(remediation.get("when_minor", "") or "90 days"),
            "effort": str(remediation.get("effort", "") or "MEDIUM").upper(),
        }
        if shaped_rem["effort"] not in ("LOW", "MEDIUM", "HIGH"):
            shaped_rem["effort"] = "MEDIUM"

        atomic = []
        for j, item in enumerate(req.get("atomic_requirements") or []):
            if not isinstance(item, dict) or not str(item.get("text", "") or "").strip():
                continue
            risk = str(item.get("risk_if_missing", "MINOR") or "MINOR").upper()
            atomic.append({
                "id": str(item.get("id") or f"{cid}.item_{j}"),
                "text": str(item["text"]),
                "verification_hint": str(item.get("verification_hint", "") or ""),
                "expected_evidence": list(item.get("expected_evidence") or []),
                "risk_if_missing": risk if risk in ("MAJOR", "MINOR") else "MINOR",
            })

        clauses[cid] = {
            "id": cid,
            "title": str(req["title"]),
            "area": str(req.get("area", "") or "Operating Criteria"),
            "is_spof": bool(req.get("is_spof", False)),
            "critical_sectors": list(req.get("critical_sectors") or []),
            "typical_ncs": list(req.get("typical_ncs") or []),
            "evidence_keywords": list(req.get("evidence_keywords") or []),
            "atomic_requirements": atomic,
            "remediation_template": shaped_rem,
            # Derivazioni esplicite: i criteri custom sono "standard" salvo
            # is_spof/severity_floor dichiarati nel YAML (clause_helpers
            # rispetta gli override espliciti).
            **({"severity_floor": req["severity_floor"]} if "severity_floor" in req else {}),
        }

    if not clauses:
        _log.warning("%s: nessun requisito valido — set ignorato", source)
        return None

    return {"label": label, "clauses": clauses, "high_freq": set()}


def _safe_id(raw: str) -> str:
    """Id sicuro per il motore: niente spazi, lowercase, [a-z0-9_]."""
    return re.sub(r"[^a-z0-9_]", "_", raw.strip().lower())[:64] or "custom_req"
