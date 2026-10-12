"""
Fast — Piano motore Fase 2 (JURISDICTION_FILTER): obblighi nazionali solo per il paese giusto.

Pin: per un'organizzazione UK (o di paese non dichiarato) nella knowledge base
adattata non resta nessun istituto italiano (RSPP, DUVRI, DVR, FIR, MUD, CER,
RLS, D.Lgs 81/08) e i requisiti solo italiani spariscono, mentre il requisito
ISO sottostante resta; per l'Italia la knowledge base è identica; l'originale
non viene mai modificato; il blocco di contesto dichiara il paese solo con
l'interruttore acceso.
"""
from __future__ import annotations

import json
import re

from compliance import jurisdiction as J
from compliance.iso_clauses.iso14001_clauses import ISO14001_CLAUSES
from compliance.iso_clauses.iso45001_clauses import ISO45001_CLAUSES
from compliance.schemas import CompanyContext

_IT = re.compile(r"\b(RSPP|DUVRI|DVR|FIR|MUD|CER|RLS|RSGA|D\.\s?Lgs|81/0?8|riunione periodica)\b")


def test_uk_knowledge_base_has_no_italian_obligations():
    for kb in (ISO45001_CLAUSES, ISO14001_CLAUSES):
        before = json.dumps(kb, ensure_ascii=False)
        adapted = J.adapt_clauses(kb, "United Kingdom")
        assert not _IT.search(json.dumps(adapted, ensure_ascii=False))
        assert json.dumps(kb, ensure_ascii=False) == before, "l'originale non si tocca"
    ids = {r["id"] for c in J.adapt_clauses(ISO45001_CLAUSES, None).values() for r in c.get("atomic_requirements") or []}
    assert "45001_8_1_4.coordination.duvri" not in ids
    assert any(i.startswith("45001_8_1_4.") for i in ids), "il requisito ISO sui contraenti resta"


def test_italy_keeps_the_national_layer():
    assert J.adapt_clauses(ISO45001_CLAUSES, "Italy") is ISO45001_CLAUSES
    assert J.adapt_prompt("check for DUVRI", "Italia") == "check for DUVRI"
    assert J.adapt_prompt("check for DUVRI", "United Kingdom") == "check for contractor coordination document"


def test_context_block_states_country_only_with_flag(monkeypatch):
    from compliance.context_intake import build_context_prompt_block
    ctx = CompanyContext(company_name="N", sector="Manufacturing", employee_range="11-50", certified="no",
                         sites_count="1", norms=["ISO 45001:2018"], country="United Kingdom")
    for v in ("JURISDICTION_FILTER", "ENGINE_PHASE2"):
        monkeypatch.delenv(v, raising=False)
    assert "Country" not in build_context_prompt_block(ctx)
    monkeypatch.setenv("JURISDICTION_FILTER", "1")
    assert "Country of operation: United Kingdom" in build_context_prompt_block(ctx)
