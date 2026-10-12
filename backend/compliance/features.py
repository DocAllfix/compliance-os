"""
features.py — interruttori del piano motore (2026-10).

Ogni modifica al motore nasce SPENTA: si accende in produzione solo quando il
banco di misura (tools/bench) mostra un miglioramento oltre la variabilità e
nessun calo di precisione. Un interruttore si accende con la sua variabile
d'ambiente oppure con quella del gruppo di fase che lo contiene.

Fase 1 — leggere tutto (ENGINE_PHASE1=1 le accende tutte):
  READ_SHEET_CELLS        Excel: celle vuote conservate, ogni valore con la sua intestazione
  READ_SHEET_SAMPLING     schede e Stage B: spazio distribuito su tutti i fogli, non solo testa+coda
  READ_DOCX_IMAGES        Word: immagini del corpo lette con l'OCR, al loro posto nel testo
  READ_DOCX_HEADERS       Word: testo di intestazioni e piè di pagina (codice, versione, data, modello)
  RETRIEVE_PER_REQUIREMENT  Stage A: ricerca anche per singolo requisito, non solo per clausola

Fase 2 — prove, gravità e azioni (ENGINE_PHASE2=1):
  SEVERITY_RULES          gravità calcolata da Python sulle prove (compliance/severity_rules.py)
  ABSENCE_SEARCH          ogni requisito ABSENT si cerca in tutto il pacco prima di valere come prova
  CONTRADICTION_STATUS    Stage B: stato CONTRADICTED con due citazioni verificate in Python
  ACTIONS_FROM_STATES     verbo dell'azione deciso dagli stati dei requisiti (compliance/action_rules.py)
  JURISDICTION_FILTER     obblighi nazionali solo per il paese giusto (compliance/jurisdiction.py)
  (KB_V2_FILL             solo clausole senza requisiti: fuori dal gruppo, banco 12/10 = ENC 10-11 -> 7)
  (KB_V2                  KB v2 completa: fuori dal gruppo, banco 12/10 = perde i difetti puntuali)
  (KB_STRENGTH            KB attuale, ma le buone pratiche non valgono da obbligo: al massimo osservazione;
                          fuori dal gruppo finché la classificazione non è rivista a mano)

Fase 3 — modello dei fatti (ENGINE_PHASE3=1):
  FACT_MODEL              chi ha emesso ogni documento, dominio, codice, persone, righe dei registri
                          (compliance/facts.py): ruoli chiave solo del cliente, etichette per Stage A/B

Fase 4 — l'organizzazione contro sé stessa (ENGINE_PHASE4=1):
  SELF_CONSISTENCY        dichiarazioni (registri, procedure, verbali) → aspettative → confronti in Python
                          (compliance/self_consistency.py); usa i fatti della Fase 3

Fase 5 — aspettative di settore (ENGINE_PHASE5=1):
  SECTOR_EXPECTATIONS     attività citate → registrazione tipica attesa; se manca: "da verificare", mai NC
                          (compliance/sector_expectations.py)
"""
from __future__ import annotations

import os

_GROUPS = {
    "ENGINE_PHASE1": ("READ_SHEET_CELLS", "READ_SHEET_SAMPLING", "READ_DOCX_IMAGES", "READ_DOCX_HEADERS",
                      "RETRIEVE_PER_REQUIREMENT"),
    "ENGINE_PHASE2": ("SEVERITY_RULES", "ABSENCE_SEARCH", "CONTRADICTION_STATUS", "ACTIONS_FROM_STATES",
                      "JURISDICTION_FILTER"),
    "ENGINE_PHASE3": ("FACT_MODEL",),
    "ENGINE_PHASE4": ("SELF_CONSISTENCY",),
    "ENGINE_PHASE5": ("SECTOR_EXPECTATIONS",),
}


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def on(name: str) -> bool:
    if _truthy(name):
        return True
    return any(name in members and _truthy(group) for group, members in _GROUPS.items())


_STANDALONE = ("KB_V2", "KB_V2_FILL", "KB_STRENGTH")


def active() -> list:
    """Interruttori accesi (per meta delle esecuzioni e log)."""
    names = {n for members in _GROUPS.values() for n in members} | set(_STANDALONE)
    return sorted(n for n in names if on(n))
