"""
sector_expectations.py — Piano motore Fase 5 (SECTOR_EXPECTATIONS): aspettative di settore.

Alcune evidenze non le chiede la norma ma le chiede l'attività: chi usa colle e
inchiostri ha le schede di sicurezza, chi produce rifiuti pericolosi ha i
documenti di trasporto, chi ha una gru ha le verifiche periodiche (banco Box:
3 delle 45 non conformità piantate erano di questo tipo). Qui, senza modello:
  1. se i documenti del cliente mostrano l'attività (termini EN/IT),
  2. si cerca nel pacco la registrazione tipica di quell'attività;
  3. se manca, è un punto DA VERIFICARE — mai una non conformità: la norma non
     la nomina, può stare in un altro sistema, e i nomi cambiano da paese a paese.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Tuple

PROFILES: List[Dict[str, Any]] = [
    {"id": "hazardous_substances", "clause": ("45001", "8.1"),
     "triggers": ["coshh", "hazardous substance", "chemical", "solvent", "glue", "adhesive", "ink", "paint",
                  "primer", "cutting fluid", "sostanze pericolose", "sostanza pericolosa", "colla", "vernice",
                  "solvente", "inchiostr", "chimic"],
     "expect": "Safety data sheets for the hazardous substances in use",
     "evidence": ["safety data sheet", "sds", "msds", "scheda di sicurezza", "schede di sicurezza",
                  "schede dati di sicurezza", "hazard statements", "indicazioni di pericolo"]},
    {"id": "waste", "clause": ("14001", "8.1"),
     "triggers": ["hazardous waste", "waste carrier", "waste oil", "rifiuti pericolosi", "rifiuti speciali",
                  "smaltimento rifiuti", "waste disposal", "skip hire"],
     "expect": "Waste transfer or consignment notes for waste removed from site",
     "evidence": ["waste transfer note", "consignment note", "duty of care", "formulario", "registro di carico",
                  "fir ", "ewc code", "codice cer"]},
    {"id": "lifting", "clause": ("45001", "8.1"),
     "triggers": ["overhead crane", "crane", "hoist", "forklift", "fork lift", "flt", "carrello elevatore",
                  "carrelli elevatori", "gru ", "paranco"],
     "expect": "Periodic thorough examination records for lifting equipment (cranes, hoists, forklift trucks)",
     "evidence": ["thorough examination", "loler", "report of thorough", "lifting equipment inspection",
                  "verifica periodica", "verifiche periodiche", "libretto"]},
    {"id": "pressure", "clause": ("45001", "8.1"),
     "triggers": ["air receiver", "pressure vessel", "compressor", "compressore", "recipiente a pressione",
                  "recipienti a pressione"],
     "expect": "Written scheme and periodic examination records for pressure systems",
     "evidence": ["written scheme", "pressure system examination", "pssr", "verifica periodica",
                  "recipienti a pressione"]},
    {"id": "lev", "clause": ("45001", "8.1"),
     "triggers": ["local exhaust ventilation", "lev ", "fume extraction", "dust extraction", "aspirazione fumi",
                  "impianto di aspirazione"],
     "expect": "Thorough examination and test records for local exhaust ventilation",
     "evidence": ["lev examination", "thorough examination and test", "lev test", "verifica impianto di aspirazione",
                  "manutenzione aspirazione"]},
    {"id": "noise", "clause": ("45001", "6.1.2"),
     "triggers": ["noise", "ear defender", "hearing protection", "rumore", "otoprotettor"],
     "expect": "Noise exposure assessment (measurements in dB(A))",
     "evidence": ["noise assessment", "noise survey", "noise exposure", "db(a)", "dba", "valutazione del rumore",
                  "valutazione rumore", "fonometr"]},
    {"id": "fire_equipment", "clause": ("45001", "8.2"),
     "triggers": ["fire extinguisher", "extinguishers", "estintor"],
     "expect": "Inspection and maintenance records for fire extinguishers",
     "evidence": ["extinguisher service", "extinguisher inspection", "fire extinguisher maintenance",
                  "manutenzione estintori", "controllo estintori", "registro antincendio", "service record"]},
]

_NORMS = {"9001": "ISO 9001:2015", "14001": "ISO 14001:2015", "45001": "ISO 45001:2018"}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.lower())


_RX: Dict[str, Any] = {}


def _rx(term: str):
    """Confine di parola a sinistra; i termini brevi ('ink', 'flt', 'fir') anche a
    destra (con plurale), così 'ink' non scatta in 'thinking'. I termini lunghi
    sono radici ('inchiostr', 'estintor') e accettano qualsiasi desinenza."""
    t = term.strip()
    if t not in _RX:
        right = r"s?(?![a-z0-9])" if len(t) <= 5 else ""
        _RX[t] = re.compile(r"(?<![a-z0-9])" + re.escape(t) + right)
    return _RX[t]


def _hits(text: str, terms: List[str]) -> List[str]:
    return [t.strip() for t in terms if _rx(t).search(text)]


def evaluate(docs: List[Dict[str, Any]], is_external) -> List[Dict[str, Any]]:
    """Aspettative attivate dai documenti del cliente, con l'esito della ricerca."""
    client = " ".join(_fold(str(d.get("content") or "")[:60000]) for d in docs
                      if not is_external(str(d.get("filename") or "")))
    allpack = [(str(d.get("filename") or ""), _fold(str(d.get("filename") or "") + " " +
                                                    str(d.get("content") or "")[:60000])) for d in docs]
    out = []
    for p in PROFILES:
        trig = _hits(client, p["triggers"])
        if not trig:
            continue
        found = [name for name, text in allpack if _hits(text, p["evidence"])]
        out.append({"profile": p["id"], "clause": p["clause"], "expect": p["expect"], "triggers": trig[:5],
                    "found_in": found[:5], "status": "CONSISTENT" if found else "TO_VERIFY"})
    return out


def attach(norm_reports: List[Any], results: List[Dict[str, Any]],
           clauses_by_norm: Dict[str, Dict[str, Any]]) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """I punti mancanti diventano "da verificare" sulla clausola indicata (o la
    stessa clausola di un'altra norma analizzata). Mai una non conformità."""
    from compliance import features
    by_norm = {r.norm: r for r in norm_reports}
    checks = []
    for r in results:
        if r["status"] != "TO_VERIFY":
            continue
        pref, num = r["clause"]
        order = [_NORMS[pref]] + [n for n in by_norm if n != _NORMS[pref]]
        for norm in order:
            if norm not in by_norm:
                continue
            prefix = norm.split()[1].split(":")[0]
            parts = num.split(".")
            cid = next((f"{prefix}_" + "_".join(parts[:k]) for k in range(len(parts), 0, -1)
                        if f"{prefix}_" + "_".join(parts[:k]) in clauses_by_norm.get(norm, {})), None)
            gap = next((g for g in by_norm[norm].clauses if g.clause_id == cid), None) if cid else None
            if gap is None:
                continue
            item = (f"{r['expect']} (the documents mention {', '.join(t.strip() for t in r['triggers'][:3])}; "
                    f"no such record was found in the pack)")
            gap.to_verify.append(item[:220])
            if features.on("ACTIONS_FROM_STATES"):
                from compliance import action_rules
                action_rules.apply(gap, clauses_by_norm[norm].get(cid, {}))
            checks.append({"kind": "sector_expectation", "status": "TO_VERIFY", "description": item,
                           "clause": f"{norm} {cid}", "attached_to": f"{norm} {cid}", "cites": [], "person": None})
            break
    return norm_reports, checks
