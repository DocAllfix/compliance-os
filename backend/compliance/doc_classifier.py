"""
Amisys QHSE — Lightweight document classifier (Fase C).

Euristica deterministica eseguita all'UPLOAD nel DMS: niente LLM sul path CRUD
(latenza/costo/coupling Azure, moltiplicato per gli import ZIP massivi). Assegna
un `doc_type` provvisorio (`doc_type_source='heuristic'`) e prova a leggere una
data di scadenza etichettata. Dopo ogni analisi, il backfill dalle evidence
card (Fase D, `doc_type_source='engine'`) sovrascrive l'euristica; il PATCH
manuale (`'manual'`) vince su tutto.

Il vocabolario doc_type rispecchia `pipeline._VALID_DOC_TYPES` così euristica,
motore e UI parlano la stessa lingua.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

# Vocabolario canonico (mirror di pipeline._VALID_DOC_TYPES).
VALID_DOC_TYPES = {
    "quality_manual", "procedure", "policy", "record", "audit_report",
    "training_record", "supplier_document", "risk_assessment",
    "calibration_record", "nonconformity_record", "management_review",
    "objective_plan", "legal_register", "emergency_plan",
    "communication_record", "contract_specification", "certificate", "other",
}

# Ordine = priorità: il primo match vince. Keyword in inglese + italiano
# (i pacchetti reali sono misti UK/IT).
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("quality_manual",       ("quality manual", "manuale qualita", "manuale della qualita", "qhse manual", "integrated manual")),
    ("management_review",    ("management review", "riesame della direzione", "riesame di direzione", "mr minutes", "management review minutes")),
    ("audit_report",         ("audit report", "internal audit", "audit programme", "audit plan", "rapporto di audit", "verifica ispettiva", "programma audit")),
    ("risk_assessment",      ("risk assessment", "risk register", "risks and opportunities", "dvr", "valutazione dei rischi", "valutazione rischi", "environmental aspects", "aspetti ambientali", "hazard")),
    ("nonconformity_record", ("nonconformity", "non-conformity", "non conformity", "corrective action", "ncr", "non conformita", "azione correttiva")),
    ("training_record",      ("training record", "training log", "competence", "attestato", "registro formazione", "formazione", "competenza")),
    ("calibration_record",   ("calibration", "taratura", "calibrazione", "gauge", "strumenti di misura")),
    ("objective_plan",       ("objectives", "kpi", "targets", "obiettivi", "indicatori", "improvement plan", "piano di miglioramento")),
    ("legal_register",       ("legal register", "compliance obligations", "registro legislativo", "obblighi di conformita", "prescrizioni legali", "legal and other requirements")),
    ("emergency_plan",       ("emergency", "evacuation", "piano di emergenza", "emergenza", "first aid", "primo soccorso")),
    ("supplier_document",    ("supplier", "vendor", "subcontractor", "fornitore", "subappalto", "purchasing")),
    ("contract_specification", ("contract", "specification", "tender", "capitolato", "contratto", "specifica tecnica")),
    ("certificate",          ("certificate", "certification", "certificato", "iso 9001", "iso 14001", "iso 45001", "accreditation")),
    ("communication_record", ("communication", "meeting minutes", "comunicazione", "verbale", "newsletter", "toolbox talk")),
    ("policy",               ("policy", "politica")),
    ("procedure",            ("procedure", "sop", "work instruction", "procedura", "istruzione operativa", "istruzione di lavoro")),
    ("record",               ("record", "register", "log", "checklist", "modulo", "registro", "verbale di")),
]

# Etichette che precedono una data di scadenza.
_EXPIRY_LABELS = (
    "expiry", "expires", "expiry date", "valid until", "valid to", "expiration",
    "scadenza", "valido fino", "data scadenza", "valida fino", "scade il",
    "renewal date", "next review", "review date", "da rinnovare entro",
)

# Date in formati comuni: 31/12/2026, 31-12-2026, 2026-12-31, 31.12.2026
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy"),
]


def classify(filename: str, text_head: str = "") -> str:
    """Ritorna un doc_type euristico (default 'other')."""
    hay = f"{filename or ''}\n{(text_head or '')[:2000]}".lower()
    hay = hay.replace("_", " ").replace("-", " ")
    for doc_type, keywords in _KEYWORD_RULES:
        if any(k in hay for k in keywords):
            return doc_type
    return "other"


def detect_expiry(text: str) -> Optional[str]:
    """Cerca una data di scadenza ETICHETTATA nel testo. Ritorna 'YYYY-MM-DD'
    o None. Conservativa: richiede un'etichetta di scadenza vicino alla data,
    così non scambia una data qualsiasi per una scadenza."""
    if not text:
        return None
    low = text.lower()
    best: Optional[str] = None
    for label in _EXPIRY_LABELS:
        idx = low.find(label)
        while idx != -1:
            window = text[idx: idx + 80]
            parsed = _first_date(window)
            if parsed:
                # tieni la scadenza più lontana nel futuro (la più rilevante)
                if best is None or parsed > best:
                    best = parsed
            idx = low.find(label, idx + 1)
    return best


def _first_date(s: str) -> Optional[str]:
    for pattern, order in _DATE_PATTERNS:
        m = pattern.search(s)
        if not m:
            continue
        try:
            if order == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            valid = date(y, mo, d)  # raises if invalid
            return valid.isoformat()
        except (ValueError, TypeError):
            continue
    return None
