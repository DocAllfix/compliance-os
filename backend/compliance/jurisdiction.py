"""
jurisdiction.py — Piano motore Fase 2 (JURISDICTION_FILTER): gli obblighi
nazionali valgono solo per il paese giusto.

La knowledge base internazionale conteneva obblighi italiani: requisiti come
"DUVRI emesso per gli appaltatori" (45001 §8.1.4) o "formulari FIR completi"
(14001 §8.1), NC tipiche "RSPP non nominato", azioni "nomina un RSPP". Su
un'azienda inglese diventavano accuse (banco Box: 2-4 rilievi per esecuzione
con RSPP/DUVRI; pacco sintetico UK: 2-3). Il testo ISO non nomina mai questi
istituti: nella norma UNI EN ISO 45001 compaiono solo nell'appendice nazionale
italiana, informativa.

Per un'organizzazione non italiana (o di paese non dichiarato):
  - i requisiti solo italiani si tolgono (il requisito ISO sottostante resta:
    es. coordinamento con gli appaltatori);
  - i nomi degli istituti italiani diventano l'equivalente neutro;
  - le menzioni che servono a RICONOSCERE un documento italiano ("un DVR è una
    valutazione dei rischi") restano nei prompt: non impongono obblighi.
Per l'Italia la knowledge base resta com'è.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Optional

IT_ONLY_REQUIREMENTS = {
    "45001_8_1_4.coordination.duvri",   # DUVRI: art. 26 D.Lgs 81/08
    "14001_8_1.fir.completeness",       # FIR: formulario di identificazione rifiuti
}

# Ordine: dal più specifico al più generico.
_REWRITES = [
    (r"\s*\((?:in Italy|in Italia)[^)]*\)", ""),
    (r"\s*\(art\.?\s*\d+[^)]*D\.\s?Lgs[^)]*\)", ""),
    (r"\s*\(D\.\s?Lgs\.?\s*81/0?8[^)]*\)", ""),
    (r",?\s*(?:informazione/formazione\s+)?ex D\.\s?Lgs\.?\s*81/0?8", ""),
    (r"\bD\.\s?Lgs\.?\s*81/0?8\b", "national OH&S legislation"),
    (r"\ban RSPP or equivalent OH&S manager\b", "a competent OH&S manager"),
    (r"\bRSPP \(or equivalent OH&S manager\)", "competent OH&S manager"),
    (r"\bRSPP\s*/\s*", ""),
    (r"\bRSPP\b", "OH&S manager"),
    (r"\bRSGA\b", "environmental manager"),
    (r"\bRLS\b", "worker OH&S representative"),
    (r"\bDUVRI \(coordination document\)", "contractor coordination arrangements"),
    (r"\bDUVRI \(Documento Unico[^)]*\)", "contractor coordination document"),
    (r"\bDUVRI-related\b", "contractor coordination"),
    (r"\bDUVRI\b", "contractor coordination document"),
    (r"\bDVR\b", "risk assessment"),
    (r"\briunione periodica\b", "periodic H&S meeting"),
    (r"\bFIR \(formulari\)", "waste transfer notes"),
    (r"\bFIR\b", "waste transfer notes"),
    (r"\bMUD\b", "annual waste return"),
    (r"\bCER (codes?)\b", r"EWC \1"),
    (r"\bCER\b", "EWC"),
]
_REWRITES_RE = [(re.compile(p), r) for p, r in _REWRITES]

_ITALY = {"it", "ita", "italy", "italia"}


def is_italy(country: Optional[str]) -> bool:
    return (country or "").strip().lower() in _ITALY


def neutral_text(text: str) -> str:
    for rx, rep in _REWRITES_RE:
        text = rx.sub(rep, text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _walk(value: Any) -> Any:
    if isinstance(value, str):
        return neutral_text(value)
    if isinstance(value, list):
        out = [_walk(v) for v in value]
        if all(isinstance(v, str) for v in out):          # liste di parole chiave: niente doppioni
            seen, dedup = set(), []
            for v in out:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    dedup.append(v)
            return dedup
        return out
    if isinstance(value, dict):
        return {k: _walk(v) for k, v in value.items()}
    return value


def adapt_clauses(clauses: Dict[str, Dict[str, Any]], country: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Copia della knowledge base adattata al paese (l'originale resta intatto)."""
    if is_italy(country):
        return clauses
    out = {}
    for cid, clause in clauses.items():
        c = copy.deepcopy(clause)
        if c.get("atomic_requirements"):
            c["atomic_requirements"] = [r for r in c["atomic_requirements"]
                                        if str(r.get("id", "")) not in IT_ONLY_REQUIREMENTS
                                        and r.get("jurisdiction") not in ("IT",)]
        out[cid] = _walk(c)
    return out


def adapt_prompt(prompt: str, country: Optional[str]) -> str:
    """Prompt per norma (iso14001_gap.md, iso45001_gap.md): stesse riscritture."""
    return prompt if is_italy(country) else neutral_text(prompt)


def context_line(country: Optional[str]) -> str:
    c = (country or "").strip()
    if not c:
        return ("Country of operation: not stated. Do not require country-specific legal roles or documents "
                "(e.g. Italian RSPP, DUVRI, DVR, FIR) unless the documents show the organisation is subject to them.")
    if is_italy(c):
        return "Country of operation: Italy. Italian legislation (e.g. D.Lgs 81/08) applies."
    return (f"Country of operation: {c}. Apply only the legislation of this country; never require Italian or "
            "other countries' legal roles or documents (e.g. RSPP, DUVRI, DVR, FIR).")
