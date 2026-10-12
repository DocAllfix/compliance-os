"""
facts.py — Piano motore Fase 3 (FACT_MODEL): un modello dei fatti dell'organizzazione.

Prima ogni clausola rileggeva testo grezzo e giudicava da sola, senza sapere di
chi fosse un documento: i firmatari dei certificati dei fornitori diventavano
"ruoli chiave" del cliente (banco Box: 3 nomi esterni su 3 esecuzioni), lo
scope di un fornitore valeva come scope del cliente, un obiettivo di sicurezza
finiva sotto la 9001. Qui si raccolgono una volta sola:
  - documenti: chi li ha emessi (cliente / fornitore / ente / autorità),
    dominio, codice, versione — dichiarati dalla scheda (Phase 2);
  - persone: chi lavora per il cliente e chi per organizzazioni esterne;
  - righe dei registri: i fogli Excel letti senza perdite (READ_SHEET_CELLS)
    diventano righe strutturate {intestazione: valore}, senza modello.
Tutte le fasi leggono da qui (ruoli chiave, evidenze per Stage A/B, Fase 4).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

CARD_FACTS_ADDENDUM = """

## Document facts (additional fields — add to EVERY card, right after `signed_by`)

issuer: "<client | supplier | certification_body | authority | customer | other_external>"
  # Who produced the document. "client" = the organisation's own document (its manual, policy, procedures,
  # registers, matrices, minutes, records, internal forms — even if filled in by hand). Otherwise the external
  # party that issued it: supplier certificates or brochures, questionnaires completed by a supplier,
  # calibration certificates from a laboratory, certification-body certificates, permits from authorities,
  # customer specifications.
issuer_name: "<name of the issuing organisation when issuer is not client, else null>"
domain: "<quality | environment | ohs | integrated | general>"
doc_code: "<the document's own identifier, e.g. IMS3, SOP4, RA1, NC-014, a certificate number — or null>"
version: "<version or revision as stated in the document — or null>"
people:   # named people in the document (max 10); [] if none
  - name: "<full name as written>"
    role: "<role or null>"
    organisation: "<client, or the name of the external organisation>"
"""

# Regola per Stage A e Stage B (aggiunta al prompt con FACT_MODEL).
EVIDENCE_PROVENANCE_RULE = """

## Who issued the evidence (document facts)

Each evidence item or document may carry `issued_by` and `domain`.
- Evidence issued by a supplier, certification body, authority or customer shows THAT party's system or
  data. It is valid evidence for supplier/contractor control, calibration, external certifications and
  permits — but never evidence of the client's own scope, policy, roles, objectives, risks, procedures or
  records. Never treat people named only on external documents as the client's staff.
- Prefer evidence whose domain matches the standard being assessed (quality for ISO 9001, environment for
  ISO 14001, ohs for ISO 45001; integrated or general documents count for all three). Do not use, for
  example, a health and safety objective as evidence of a quality objective.
"""

_ROW_RE = re.compile(r"^Row (\d+): (.*)$")
_SHEET_RE = re.compile(r'^\[SHEET "([^"]*)"\]')
_EXTERNAL = {"supplier", "certification_body", "authority", "customer", "other_external"}


_SYSTEM_DOC_TYPES = {"quality_manual", "policy", "procedure", "management_review", "objective_plan",
                     "emergency_plan", "audit_report"}


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").replace("\\", "/").rsplit("/", 1)[-1]).strip().lower()


def _person_key(name: str) -> str:
    return re.sub(r"[^a-z ]", "", str(name or "").lower()).strip()


def parse_register_rows(file_name: str, text: str) -> List[Dict[str, Any]]:
    """Righe 'Row n: Intestazione: valore | …' (rendering READ_SHEET_CELLS)."""
    rows, sheet = [], ""
    for line in (text or "").splitlines():
        m = _SHEET_RE.match(line.strip())
        if m:
            sheet = m.group(1)
            continue
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        fields = {}
        for part in m.group(2).split(" | "):
            if ": " in part:
                k, v = part.split(": ", 1)
                fields[k.strip()] = "" if v.strip() == "(blank)" else v.strip()
        if fields:
            rows.append({"file_name": file_name, "sheet": sheet, "row": int(m.group(1)), "fields": fields})
    return rows


class Facts:
    def __init__(self) -> None:
        self.documents: Dict[str, Dict[str, Any]] = {}     # nome normalizzato → fatti del documento
        self.client_people: Dict[str, Dict[str, Any]] = {}
        self.external_people: Dict[str, Dict[str, Any]] = {}
        # Persone del cliente nominate nei documenti di sistema (manuale, politica, procedure,
        # riesame): sono le sole candidate a "ruolo chiave". Chi compare soltanto su un foglio
        # presenze o su un attestato (formatori, istruttori, operatori) non lo è.
        self.key_people: Dict[str, Dict[str, Any]] = {}
        self.register_rows: List[Dict[str, Any]] = []

    # ── lettura ──────────────────────────────────────────────────────────────
    def document(self, file_name: str) -> Dict[str, Any]:
        return self.documents.get(_norm_name(file_name), {})

    def is_external(self, file_name: str) -> bool:
        return self.document(file_name).get("issuer") in _EXTERNAL

    def tag(self, file_name: str) -> str:
        """Etichetta breve per i prompt: chi ha emesso il documento e il dominio."""
        d = self.document(file_name)
        if not d:
            return ""
        who = d.get("issuer") or "unknown"
        if who in _EXTERNAL and d.get("issuer_name"):
            who = f"{who} ({d['issuer_name']})"
        return f"issued by: {who}; domain: {d.get('domain') or 'unknown'}"

    def is_external_person(self, name: str) -> bool:
        k = _person_key(name)
        return bool(k) and k in self.external_people and k not in self.client_people

    def is_client_person(self, name: str) -> bool:
        k = _person_key(name)
        if k in self.client_people:
            return True
        parts = k.split()          # "T. Ashworth" / "Tom Ashworth": cognome + iniziale
        return bool(parts) and any(p.split() and p.split()[-1] == parts[-1] and p[0] == parts[0][0]
                                   for p in self.client_people)

    def _in(self, people: Dict[str, Dict[str, Any]], name: str) -> bool:
        k = _person_key(name)
        if k in people:
            return True
        parts = k.split()          # "T. Ashworth" / "Tom Ashworth": cognome + iniziale
        return bool(parts) and any(p.split() and p.split()[-1] == parts[-1] and p[0] == parts[0][0] for p in people)

    def filter_key_roles(self, roles: List[str]) -> List[str]:
        """Ruoli chiave: solo persone del cliente — quelle dei documenti di sistema
        quando ce ne sono, altrimenti tutte quelle note del cliente; senza nessun
        elenco si tolgono almeno quelle che compaiono solo su documenti esterni."""
        out = []
        allowed = self.key_people or self.client_people
        for r in roles or []:
            name = (r.split(":", 1)[1] if ":" in r else r).strip()
            names = [n.strip() for n in re.split(r",|;| and ", name) if n.strip()]
            if allowed:
                if not any(self._in(allowed, n) for n in names):
                    continue
            elif any(self.is_external_person(n) for n in names):
                continue
            out.append(r)
        return out


def build(cards: List[Dict[str, Any]], documents: Optional[List[Dict[str, Any]]] = None) -> Facts:
    f = Facts()
    for c in cards or []:
        fn = str(c.get("file_name") or "")
        if not fn:
            continue
        issuer = str(c.get("issuer") or "").strip().lower() or None
        f.documents[_norm_name(fn)] = {
            "file_name": fn, "issuer": issuer, "issuer_name": c.get("issuer_name"),
            "domain": str(c.get("domain") or "").strip().lower() or None,
            "doc_code": c.get("doc_code"), "version": c.get("version"), "doc_type": c.get("doc_type"),
        }
        # Un certificato lo emette sempre un terzo (ente, laboratorio, formatore):
        # chi lo firma non è personale del cliente (banco Box: il firmatario degli
        # attestati di primo soccorso finiva tra i ruoli chiave).
        is_cert = str(c.get("doc_type") or "") == "certificate"
        for p in c.get("people") or []:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            org = str(p.get("organisation") or "").strip()
            client_like = (issuer == "client" and org.lower() in ("", "client", "none", "null")) or org.lower() == "client"
            target = f.external_people if (is_cert or not client_like) else f.client_people
            entry = {"name": p["name"], "role": p.get("role"), "organisation": org or None, "file_name": fn}
            target.setdefault(_person_key(p["name"]), entry)
            if target is f.client_people and str(c.get("doc_type") or "") in _SYSTEM_DOC_TYPES:
                f.key_people.setdefault(_person_key(p["name"]), entry)
    for d in documents or []:
        text = str(d.get("content") or "")
        if "Row " in text and "[SHEET" in text:
            f.register_rows.extend(parse_register_rows(str(d.get("filename") or ""), text))
    # Le persone elencate nei registri del cliente (matrice formazione, elenchi
    # del personale) sono personale del cliente: fatto deterministico.
    for r in f.register_rows:
        if f.is_external(r["file_name"]):
            continue
        for k, v in r["fields"].items():
            if re.fullmatch(r"(full )?name|employee|person|staff|nome|dipendente|nominativo|lavoratore|nome e cognome|cognome e nome", k.strip().lower()) and v:
                f.client_people.setdefault(_person_key(v), {"name": v, "role": None, "organisation": "client",
                                                            "file_name": r["file_name"]})
    return f
