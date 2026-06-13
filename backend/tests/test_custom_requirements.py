"""
Fast regression for Fase 7 custom requirement sets (PRD §1.4.4b).

Pins: example-set loading, shape validation/defaults, reserved-label guard,
id sanitisation, registry merge shape compatible with the engine.
"""
from __future__ import annotations

import pytest

from compliance.custom_requirements import (
    REQUIREMENT_SETS_DIR,
    _validate_and_shape,
    list_requirement_sets,
    load_requirement_set_by_label,
)


def test_example_set_is_listed_and_loadable():
    sets = list_requirement_sets()
    labels = [s["label"] for s in sets]
    assert "Hartwell Operating Criteria" in labels
    entry = next(s for s in sets if s["label"] == "Hartwell Operating Criteria")
    assert entry["requirement_count"] == 3

    loaded = load_requirement_set_by_label("Hartwell Operating Criteria")
    assert loaded is not None
    assert len(loaded["clauses"]) == 3
    assert loaded["high_freq"] == set()


def test_loaded_clauses_have_engine_shape():
    """Ogni clausola custom deve avere lo shape che il motore esige."""
    loaded = load_requirement_set_by_label("Hartwell Operating Criteria")
    for cid, clause in loaded["clauses"].items():
        assert clause["id"] == cid
        assert clause["title"]
        assert isinstance(clause["evidence_keywords"], list)
        rem = clause["remediation_template"]
        for f in ("what", "who", "when_major", "when_minor", "effort"):
            assert rem.get(f), f"remediation_template.{f} mancante su {cid}"
        assert rem["effort"] in ("LOW", "MEDIUM", "HIGH")
        for req in clause.get("atomic_requirements", []):
            assert req["id"] and req["text"]
            assert req["risk_if_missing"] in ("MAJOR", "MINOR")

    # clause_helpers deve poter derivare tier/floor/weight senza errori
    from compliance.clause_helpers import get_criticality_tier, get_severity_floor, get_weight
    for clause in loaded["clauses"].values():
        assert get_criticality_tier(clause) in ("critical", "standard", "passing")
        assert get_severity_floor(clause) in ("MAJOR", "MINOR", None)
        assert get_weight(clause) in (1, 3, 5)


def test_unknown_label_returns_none():
    assert load_requirement_set_by_label("Does Not Exist") is None


def test_reserved_iso_label_rejected():
    data = {"label": "ISO 9001:2015", "requirements": [{"id": "x", "title": "X"}]}
    assert _validate_and_shape(data, "test.yaml") is None


def test_defaults_and_id_sanitisation():
    data = {
        "label": "Minimal Set",
        "requirements": [
            {"id": "OC 1 — Strange/ID!", "title": "Minimal requirement"},
            {"id": "", "title": "skipped (no id)"},
            {"title": "skipped (missing id key)"},
        ],
    }
    shaped = _validate_and_shape(data, "test.yaml")
    assert shaped is not None
    assert len(shaped["clauses"]) == 1
    cid = next(iter(shaped["clauses"]))
    assert " " not in cid and "/" not in cid and "!" not in cid
    clause = shaped["clauses"][cid]
    assert clause["remediation_template"]["effort"] == "MEDIUM"  # default
    assert clause["area"] == "Operating Criteria"


def test_engine_registry_merge():
    """analyze_compliance deve risolvere il label custom nel registry effettivo
    e includerlo in norms_to_analyse (verifica del wiring, senza LLM)."""
    from compliance import gap_analyzer as ga
    from compliance.custom_requirements import load_requirement_set_by_label

    custom = load_requirement_set_by_label("Hartwell Operating Criteria")
    effective = dict(ga._NORM_REGISTRY)
    effective["Hartwell Operating Criteria"] = {
        "clauses": custom["clauses"],
        "prompt_path": ga._CUSTOM_GAP_PROMPT,
        "high_freq": set(),
    }
    requested = ["ISO 9001:2015", "Hartwell Operating Criteria", "Unknown Set"]
    norms = [n for n in requested if n in effective]
    assert norms == ["ISO 9001:2015", "Hartwell Operating Criteria"]
    assert ga._CUSTOM_GAP_PROMPT.exists(), "prompt custom_criteria_gap.md mancante"
