"""
self_consistency.py — Piano motore Fase 4 (SELF_CONSISTENCY): verificare
l'organizzazione contro sé stessa. È la chiave di volta del piano.

Il motore confrontava i documenti con la norma, mai l'organizzazione con sé
stessa: le contraddizioni tra documenti (classe C) e il "dichiara ma non fa"
(classe D) erano 32 delle 45 non conformità piantate nel pacco Box, e il motore
ne trovava 2. Qui:

  1. si estraggono le DICHIARAZIONI dell'organizzazione:
     - dai registri (fogli letti senza perdite, Fase 1): il modello classifica
       una volta ogni foglio (colonna delle persone, dei corsi, delle scadenze…),
       poi ogni riga è un fatto;
     - dai testi (procedure, manuale, riesame, registro legale): "i verbali sono
       archiviati", "nove estintori", "obiettivo 10%", "audit il 18/04";
  2. ogni dichiarazione genera un'ASPETTATIVA verificabile;
  3. il CONFRONTO lo fa Python: codici cercati in tutto il pacco, date e numeri
     confrontati, nomi abbinati, voci contate. Il modello estrae e allinea
     ("queste due frasi parlano della stessa cosa?"), Python giudica: un
     confronto sbagliato è un difetto riproducibile e correggibile.

Regole di prudenza (banco di misura, pacchi Box e sintetico):
  - una colonna vale come citazione di documenti solo se almeno un suo codice
    si ritrova nel pacco (un registro legale cita leggi, non certificati);
  - "per ogni fornitore": si contesta solo se la registrazione esiste per
    alcuni e manca per altri; se non c'è per nessuno resta da verificare;
  - una registrazione dichiarata è "mancante" solo dopo l'elenco dei file e la
    ricerca nel testo completo; da verbali e obiettivi resta da verificare;
  - valori: solo obiettivo contro obiettivo; date: solo pianificata contro
    effettiva dello stesso evento;
  - persone: si accusa una persona solo se la registrazione dello stesso corso
    e della stessa data esiste ed è leggibile; nel dubbio "da verificare".

Base normativa: la non conformità riguarda anche i requisiti che
l'organizzazione stabilisce per sé stessa (ISO 45001 §3.34, nota 1; stessa
logica in 9001/14001).

Gli esiti diventano controlli (RequirementCheck) sulla clausola competente di
UNA sola norma (un fatto, un giudizio) e passano dalle regole di gravità.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from compliance.facts import Facts

_log = logging.getLogger("compliance.self_consistency")

MAX_WORKERS = 8
MAX_RECORD_CLAIMS = 40        # dichiarazioni "teniamo X" verificate per pacco
MAX_TO_VERIFY_RECORDS = 14    # punti "da verificare" su registrazioni dichiarate
CLAIMS_CHUNK = 14000          # caratteri di documento per ogni estrazione di dichiarazioni
MAX_PAIRS_TO_ALIGN = 40
MAX_FEATURE_DOCS = 12

_STOP = set("the and for with from that this are was were has have all any each every per its our their "
            "of to in on by as at or an a is be been will shall must should can may del della dei delle di "
            "il la le lo gli e o per con che un una dei degli dalle nel nella nei sul sulla sono viene "
            "vengono deve devono ogni tutti tutte".split())
# Parole che non distinguono una registrazione (o un indicatore) da un'altra.
_GENERIC = set("record records document documents documentation copy copies file files evidence information "
               "data relevant other kept held stored maintained digital digitally physical signed formal "
               "completed supplier suppliers vendor vendors contractor contractors customer customers "
               "approved objective objectives target targets rate level number total date reduction "
               "registrazione registrazioni documento documenti documentazione copia copie evidenza evidenze "
               "fornitore fornitori cliente clienti appaltatore appaltatori obiettivo obiettivi traguardo "
               "relativo relativa relativi relative conservato conservati archiviato archiviati".split())


# ── utilità ──────────────────────────────────────────────────────────────────

def _base(name: str) -> str:
    return str(name or "").replace("\\", "/").rsplit("/", 1)[-1]


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if t not in _STOP}


def _stems(s: str) -> Set[str]:
    """Radici delle parole distintive: 'questionnaires' e 'questionnaire', 'certification' e
    'certificate' coincidono."""
    return {t.rstrip("s")[:7] for t in _tokens(s) if t not in _GENERIC and not t.isdigit()}


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"], 1)}
_MONTHS.update({"gen": 1, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "dic": 12})


def parse_date(s: Any) -> Optional[dt.date]:
    """Date nei formati dei documenti: 2026-03-11, 11/03/2026, 8.2.24, 11 November 2026."""
    if isinstance(s, dt.datetime):
        return s.date()
    if isinstance(s, dt.date):
        return s
    t = str(s or "").strip().lower()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b", t)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y = y + 2000 if y < 100 else y
        else:
            m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?\s+(\d{4}|\d{2})\b", t)
            if not m or m.group(2)[:3] not in _MONTHS:
                return None
            d, mo, y = int(m.group(1)), _MONTHS[m.group(2)[:3]], int(m.group(3))
            y = y + 2000 if y < 100 else y
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def _all_dates(text: str) -> Set[dt.date]:
    """Tutte le date scritte in un testo (una registrazione porta la data del corso e quella della firma)."""
    out: Set[dt.date] = set()
    t = str(text or "").lower()
    for rx in (r"\b\d{4}-\d{1,2}-\d{1,2}\b", r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b",
               r"\b\d{1,2}(?:st|nd|rd|th)?\s+[a-z]{3,9}\.?\s+(?:\d{4}|\d{2})\b"):
        for m in re.finditer(rx, t):
            d = parse_date(m.group(0))
            if d:
                out.add(d)
    return out


_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                     "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_WORDS.update({w: i for i, w in enumerate("zero uno due tre quattro cinque sei sette otto nove dieci undici dodici "
                                          "tredici quattordici quindici sedici diciassette diciotto diciannove "
                                          "venti".split()) if w not in ("zero", "sei")})   # "sei" è anche un verbo


def _num(s: Any) -> Optional[float]:
    t = str(s or "")
    m = re.search(r"-?\d+(?:[.,]\d+)?", t)
    if m:
        return float(m.group(0).replace(",", "."))
    for w in re.findall(r"[a-z]+", t.lower()):
        if w in _WORDS:
            return float(_WORDS[w])
    return None


def _quote_in(quote: str, text: str) -> bool:
    q = _ws(quote).strip(" .\"'…")
    return len(q) >= 6 and (q in _ws(text) or q[:50] in _ws(text))


def _names_match(a: str, b: str) -> bool:
    """Stessa persona: cognome uguale (o quasi, OCR) e iniziale del nome compatibile."""
    pa, pb = _ws(a).split(), _ws(b).split()
    if not pa or not pb:
        return False
    if difflib.SequenceMatcher(None, pa[-1], pb[-1]).ratio() < 0.8:
        return False
    return len(pa) == 1 or len(pb) == 1 or pa[0][0] == pb[0][0]


class _Corpus:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = [(str(d.get("filename") or ""), str(d.get("content") or "")) for d in docs]
        self.low = [(_ws(n), _ws(t)) for n, t in self.docs]

    def find_token(self, token: str, exclude: str = "") -> List[int]:
        """Documenti che contengono il codice (nel nome o nel testo), separatori tolleranti."""
        tok = re.escape(_ws(token)).replace(r"\-", r"[-\s_]?").replace(r"\ ", r"[-\s_]?")
        rx = re.compile(r"(?<![a-z0-9])" + tok + r"(?![a-z0-9])")
        return [i for i, (n, t) in enumerate(self.low)
                if self.docs[i][0] != exclude and (rx.search(n) or rx.search(t))]

    def text(self, i: int) -> str:
        return self.docs[i][1]

    def name(self, i: int) -> str:
        return self.docs[i][0]

    def head(self, i: int, chars: int = 600) -> str:
        """Percorso + inizio del testo: dove un documento dice che cosa è."""
        return self.low[i][0] + " " + self.low[i][1][:chars]


# ── estrazione (modello) ─────────────────────────────────────────────────────

SHEET_PROMPT = """You classify one sheet of a company's management-system spreadsheet so that a program can check it
row by row. Sheet "{sheet}" of file "{file}". Columns: {columns}
First rows:
{rows}

Return JSON:
{{"kind": "reference_register | training_matrix | nc_log | supplier_list | objectives | audit_programme | other",
 "reference_column": "<column whose values cite another document or record by its number/ID (certificate number,
                      record ID) or null>",
 "result_column": "<column with a pass/fail or status result for that reference, or null>",
 "next_due_column": "<column with a next-due / expiry date, or null>",
 "status_column": "<open/closed status column, or null>",
 "target_date_column": "<target / due / close-by date column, or null>",
 "person_column": "<column with people's names, or null>",
 "courses": [{{"course": "<course name>", "date_column": "<column with the completion date of this course>",
              "trainer_column": "<column naming who delivered THIS course, or null>"}}],
 "entity_column": "<column naming suppliers/contractors, or null>",
 "item_column": "<column naming the objective / audit / item, or null>",
 "value_column": "<column with a target value, or null>",
 "planned_date_column": "<column with a planned date, or null>",
 "clause": "<the ISO clause this register mainly supports, e.g. ISO 9001 §7.1.5>"}}
Use exact column names from the list."""

CLAIMS_PROMPT = """You read one document of a company's own management system and list the CHECKABLE DECLARATIONS
the organisation makes about itself — statements that ANOTHER document in the pack can confirm or contradict.
Document: "{file}"

Types:
- "record_kept": the organisation commits to keep, store, archive, issue or log a specific RECORD — something
  produced each time an activity happens: minutes, attendance sheets, logs, reports, certificates, completed
  forms, questionnaires, declarations, notes (e.g. "H&S forum minutes are stored digitally", "complaints are
  recorded in the NC log", "a formal NCR report is sent to the supplier", "declarations of conformity are
  collected from suppliers").
  NOT a record: this document itself, IT systems or folders, an action with no record ("obsolete copies are
  destroyed"), general intentions.
  "subject" = the record as the organisation names it. If the record must exist for every item of a list, set
  "per_entity": "supplier" (also vendors and contractors), "customer", "employee" or "document" (e.g. "every
  controlled document carries a revision table at the end" -> "document").
- "quantity": a count of physical things on the site (e.g. "nine fire extinguishers"). "value" = the number.
- "value": the numeric figure of a named objective or indicator (e.g. "downtime objective 10%").
- "date": the date of a named activity (e.g. "internal audit IA-01 on 18/4/26"). Not the issue or revision date
  of the document.
"planned": true when the figure or date is a target, plan or schedule; false when it is a measured result or
something that actually took place.
Only declarations about this organisation, not general requirements of a standard. At most 20; first the
records the organisation says it stores or retains (with where or for how long), then targets and dates.

Return JSON: {{"claims": [{{"type": "...", "subject": "<what it is about, short>", "value": "<number/date/record
name>", "per_entity": "<kind of item or null>", "clause": "<ISO clause, e.g. ISO 45001 §5.4>",
"planned": true, "quote": "<verbatim words from the document, at most 30 words>"}}]}}

DOCUMENT TEXT:
{text}"""

RECORD_PROMPT = """You read a record from a company's pack and extract its key facts as JSON.
File: "{file}"
{text}

Return JSON: {{"kind": "training_record | certificate | other",
 "course": "<course or topic, or null>",
 "date": "<date of the training/calibration/issue EXACTLY as written, or null>",
 "trainer": "<who delivered the training as written, or null if the field is empty or absent>",
 "trainer_field_present": <true if the record has a trainer/instructor field, even if empty>,
 "attendees": ["<names of attendees who signed or are listed>"],
 "attendees_readable": <true if the attendee list is clearly readable>,
 "result": "pass | fail | unknown",
 "next_due": "<next due / expiry date EXACTLY as written in the document (do not reformat), or null>",
 "number": "<certificate or record number, or null>"}}"""

SAME_PROMPT = """Each pair below holds two statements taken from two different documents of the same organisation.
The figures and dates are hidden on purpose ("#"): do not guess them. For each pair decide only whether A and B
are about the SAME thing — the target of the same objective or indicator, the date of the same single event
(same audit, same meeting, same training session), or the number of the same physical items on the same site —
so that two different values would be a contradiction in the organisation's own records.
Answer false when they concern different objects, different indicators, or different periods or occurrences.

{pairs}

Return JSON: {{"pairs": [{{"id": 1, "same": true}}]}}"""

LIST_PROMPT = """Document "{file}" (it may be the OCR text of a plan or drawing):
{text}

Elsewhere the organisation states: "{quote}"
Does THIS document itself show or list the individual {subject}? If it is a plan, drawing, list or register that
shows them, return one entry per item, each exactly as it is written in the text (its label or its line). If the
document only mentions them in passing, return "complete": false.

Return JSON: {{"complete": true, "items": ["<verbatim label or line>"]}}"""

INVENTORY_PROMPT = """The organisation states in "{src}": "{quote}"
Record it refers to: {subject}

Below is the full list of files in the document pack (path and type). Which files, if any, are that record or
clearly contain it — possibly under another name? A blank template is not a record. Choose a file only when its
name or type clearly indicates it; otherwise return an empty list.

{inventory}

Return JSON: {{"files": [<numbers>]}}"""

TARGET_PROMPT = """An objective or indicator of the organisation: "{subject}" (its target is set in another document).
Passages from "{file}":
{passages}

Does this document state the TARGET figure of that same objective or indicator (not a measured result, and not a
different objective)? Quote the words verbatim.

Return JSON: {{"stated": true, "value": "<the target figure as written>", "quote": "<verbatim words>"}}"""

ENTRY_PROMPT = """The organisation states: "{quote}"
So "{file}" should hold: {subject}

Does the file below contain at least one entry that clearly is a case of that (the entry itself shows it, for
example in its source or description)? A column header, an instruction or an entry of another kind (an internal
defect, a supplier problem when customer complaints are meant) does not count; if no entry clearly is one, answer
false. Quote the entry verbatim.
{text}

Return JSON: {{"present": true, "quote": "<verbatim words, or null>"}}"""

FEATURE_PROMPT = """Rule the organisation sets in "{src}": "{quote}"
What every document must carry: {subject}

Does the document below carry it? Quote verbatim the words (table header, block title or line) that show it.
Document "{file}":
{text}

Return JSON: {{"present": true, "quote": "<verbatim words, or null>"}}"""


def _ask(client, prompt: str, max_tokens: int = 1500) -> Dict[str, Any]:
    last: Optional[Exception] = None
    for _ in range(3):
        try:
            r = client._sdk.chat.completions.create(
                model=client.deployment, temperature=0.0, seed=42, max_tokens=max_tokens,
                response_format={"type": "json_object"}, messages=[{"role": "user", "content": prompt}])
            return json.loads(r.choices[0].message.content or "{}")
        except Exception as e:
            last = e
    _log.warning("[self_consistency] chiamata fallita: %s", str(last)[:160])
    return {}


# ── esiti ────────────────────────────────────────────────────────────────────

def _check(kind: str, status: str, description: str, clause: str, cites: List[Tuple[str, str]],
           person: Optional[str] = None) -> Dict[str, Any]:
    """status: INCONSISTENT (contraddizione) | MISSING (assenza verificata) | TO_VERIFY | CONSISTENT."""
    return {"kind": kind, "status": status, "description": description, "clause": clause,
            "cites": [{"file_name": f, "quote": str(q or "")[:300]} for f, q in cites], "person": person}


def _sheets(facts: Facts) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    out: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in facts.register_rows:
        out.setdefault((r["file_name"], r["sheet"]), []).append(r)
    return out


def _row_label(row: Dict[str, Any]) -> str:
    """Come l'organizzazione chiama quella riga: il primo campo compilato (Asset ID: CAL007)."""
    for k, v in row["fields"].items():
        if str(v or "").strip():
            return f"{k} {str(v).strip()[:40]}"
    return f"row {row['row']}"


def _row_quote(row: Dict[str, Any]) -> str:
    return f"Row {row['row']}: " + " | ".join(f"{k}: {v or '(blank)'}" for k, v in row["fields"].items())[:280]


# ── registri che citano altre registrazioni ─────────────────────────────────

_STANDARD_REF = re.compile(r"^(iso|en|bs|uni|iec|ohsas)[-\s]?\d", re.I)
# Codice di una registrazione: lettere e cifre unite (NWC-2203, CAL-03).
# "Regulations 1998" e "Act 1974" non lo sono: lo spazio separa una parola da un anno.
_CODE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,6}-?\d{2,}[A-Za-z0-9]*(?:-[A-Za-z0-9]+)*(?![A-Za-z0-9])")
_CITE_HEADER = re.compile(r"certificate|\bcert\b|cert\.?\s*(?:no|number|ref|id|#)|"
                          r"(?:report|record|doc(?:ument)?)\s*(?:no|number|ref|id|#)|"
                          r"certificato|attestato|(?:n[°.ro]*|numero)\s*(?:del\s+)?(?:rapporto|verbale|certificato)|"
                          r"(?:rapporto|verbale)\s*(?:n[°.ro]*|numero)", re.I)
_CITE_LABEL = re.compile(r"(?:cert(?:ificate|ificato)?|report|record|ref(?:erence)?|doc(?:ument)?|attestato|"
                         r"rapporto|verbale|rif(?:erimento)?|prot(?:ocollo)?)\.?\s*"
                         r"(?:no\.?|number|#|id|n[°.ro]*|numero)?\s*[:.#]?\s*$", re.I)
_OWN_ID_HEADER = re.compile(r"^\s*(?:asset|equipment|item|tag|serial|id|no\.?|#|matricola|codice|strumento|"
                            r"attrezzatura|apparecchiatura|n[°.])\b|\bid\s*$", re.I)
_PASS = re.compile(r"\bpass(?:ed)?\b|\bok\b|\bconform|approved|superat|\bvalid[oa]?\b|\bidone[oa]\b|\bpositiv[oa]\b")
_FAIL = re.compile(r"fail|reject|not ok|non[- ]?conform|out of tol|non idone|negativ|respint|fuori tolleranza|"
                   r"non superat|scadut")


def _record_token(ref: str) -> Optional[str]:
    """Primo codice di registrazione in un testo; un riferimento a una norma non lo è."""
    for m in _CODE.finditer(ref or ""):
        if not _STANDARD_REF.match(m.group(0)):
            return m.group(0)
    return None


def _norm_code(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _has_code(text: str, code: str) -> bool:
    return bool(code) and _norm_code(code) in _norm_code(text)


def _citations(row: Dict[str, Any], ref_col: Optional[str]) -> List[Tuple[str, str]]:
    """(colonna, codice) che la riga cita come registrazione esterna al registro: il codice sta in
    una colonna "Certificate / Report no.", oppure è preceduto da un'etichetta ("Cert: NWC-2201"),
    oppure sta nella colonna indicata dal modello purché non sia l'identificativo della riga
    (Asset ID, Item): quello nomina la cosa, non un documento."""
    out: List[Tuple[str, str]] = []
    for col, val in row["fields"].items():
        v = str(val or "")
        for m in _CODE.finditer(v):
            code = m.group(0)
            if _STANDARD_REF.match(code):
                continue
            labelled = bool(_CITE_HEADER.search(col)) or bool(_CITE_LABEL.search(v[:m.start()].rstrip(" (")))
            hinted = col == ref_col and not _OWN_ID_HEADER.search(col)
            if labelled or hinted:
                out.append((col, code))
    return out


def _ambiguous_dates(a: dt.date, b: dt.date) -> bool:
    """Giorno e mese invertiti (05/01 contro 01/05): formato incerto, non è una prova."""
    return a.year == b.year and a.day == b.month and a.month == b.day


def _record_for(code: str, hits: List[int], corpus: _Corpus, extract) -> Optional[Tuple[int, Dict[str, Any]]]:
    """Il documento che È quella registrazione (non uno che la nomina soltanto)."""
    for i in hits:
        if _has_code(_base(corpus.name(i)), code):
            return i, extract(corpus.name(i), corpus.text(i))
    for i in hits[:4]:
        f = extract(corpus.name(i), corpus.text(i))
        if _norm_code(f.get("number")) == _norm_code(code):
            return i, f
        if f.get("kind") == "certificate" and _has_code(corpus.text(i)[:1500], code):
            return i, f
    return None


def _check_reference_register(rows, spec, corpus: _Corpus, extract) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    file_name, clause = rows[0]["file_name"], spec.get("clause") or ""
    by_col: Dict[str, List[Tuple[Dict[str, Any], str, List[int]]]] = {}
    for row in rows:
        for col, code in _citations(row, spec.get("reference_column")):
            by_col.setdefault(col, []).append((row, code, corpus.find_token(code, exclude=file_name)))
    for col, items in by_col.items():
        if not any(hits for _, _, hits in items):
            continue    # la colonna non cita documenti del pacco (leggi, norme, codici interni)
        for row, code, hits in items:
            rec = _record_for(code, hits, corpus, extract) if hits else None
            if rec is None:
                where = (f" (it is only mentioned in {_base(corpus.name(hits[0]))})" if hits else "")
                out.append(_check("referenced_record", "MISSING",
                                  f"{_base(file_name)} cites {code} ({_row_label(row)}), but no document in the pack is "
                                  f"that record{where}",
                                  clause, [(file_name, _row_quote(row))]))
                continue
            target, facts_t = rec
            tname = _base(corpus.name(target))
            if not _has_code(tname, code):
                near = [c for c in (m.group(0) for m in _CODE.finditer(tname))
                        if difflib.SequenceMatcher(None, _norm_code(c), _norm_code(code)).ratio() >= 0.7]
                if near:
                    out.append(_check("file_name", "INCONSISTENT",
                                      f"The file {tname} holds record {code}: its name ({near[0]}) does not match "
                                      f"the record number", clause, [(corpus.name(target), f"number: {code}")]))
            cells = [str(row["fields"].get(c) or "") for c in (spec.get("result_column"), spec.get("status_column"), col)
                     if c and c in row["fields"]]
            says_pass = next((c for c in cells if _PASS.search(_ws(c)) and not _FAIL.search(_ws(c))), None)
            if says_pass and str(facts_t.get("result") or "unknown") == "fail":
                out.append(_check("register_vs_record", "INCONSISTENT",
                                  f"{_base(file_name)} shows {code} ({_row_label(row)}) as '{says_pass[:60]}', but the "
                                  f"record says it failed",
                                  clause, [(file_name, _row_quote(row)), (corpus.name(target), "result: fail")]))
            due_col = spec.get("next_due_column")
            if due_col not in row["fields"]:
                due_col = next((c for c in row["fields"] if re.search(r"next|due|expir|valid (?:until|to)", c, re.I)), None)
            due_reg = parse_date(row["fields"].get(due_col)) if due_col else None
            due_doc = parse_date(facts_t.get("next_due"))
            if due_reg and due_doc and due_reg != due_doc and not _ambiguous_dates(due_reg, due_doc):
                out.append(_check("register_vs_record", "INCONSISTENT",
                                  f"{_base(file_name)} gives {code} ({_row_label(row)}) a next-due date of "
                                  f"{due_reg.isoformat()}, the record says {due_doc.isoformat()}", clause,
                                  [(file_name, _row_quote(row)), (corpus.name(target), f"next due: {facts_t.get('next_due')}")]))
    return out


def _check_nc_log(rows, spec, audit_date: dt.date) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        status = _ws(str(row["fields"].get(spec.get("status_column") or "", "")))
        target = parse_date(row["fields"].get(spec.get("target_date_column") or "", ""))
        if target and target < audit_date and re.search(r"open|apert[oa]|in progress|ongoing|in corso", status):
            out.append(_check("overdue_action", "INCONSISTENT",
                              f"An item in {_base(row['file_name'])} is still open after its target date "
                              f"({target.isoformat()})", spec.get("clause") or "ISO 9001 §10.2",
                              [(row["file_name"], _row_quote(row))]))
    return out


# ── matrice della formazione ↔ registrazioni dei corsi ──────────────────────

_MAX_MISSING_PEOPLE = 3   # oltre: la registrazione è probabilmente incompleta → da verificare
_NAME_SIM = 0.62          # soglia di somiglianza tra un nome della matrice e uno scritto a mano / letto da OCR
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic", ".webp")
_COURSE_GENERIC = set("training course refresher awareness date completed completion including general "
                      "session level internal record formazione corso aggiornamento addestramento data "
                      "informazione generale specifica".split())


def _courses(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Corsi della matrice: {course, date_column, trainer_column} (formato nuovo) o
    solo colonne-data (formato vecchio: course_date_columns + trainer_column unica)."""
    out = [c for c in spec.get("courses") or [] if isinstance(c, dict) and c.get("date_column")]
    if not out:
        out = [{"course": col, "date_column": col, "trainer_column": spec.get("trainer_column")}
               for col in spec.get("course_date_columns") or []]
    for c in out:
        c["course"] = re.sub(r"\b(training date|date|completed|completion)\b", "", str(c.get("course") or c["date_column"]),
                             flags=re.I).strip() or c["date_column"]
    return out


def _name_parts(s: str) -> List[str]:
    return [p for p in re.findall(r"[a-z]+", _ws(re.sub(r"\(.*?\)", " ", s or ""))) if len(p) > 1]


def _name_sim(person: str, written: str) -> float:
    """Somiglianza tra un nome della matrice e un nome scritto su una registrazione (anche a mano,
    letto da OCR: "Tom Ashwarth", "PRIYA SHAN"). Un solo nome o cognome vale un po' meno."""
    pp, pw = _name_parts(person), _name_parts(written)
    if not pp or not pw:
        return 0.0
    if len(pw) == 1:
        return 0.9 * max(difflib.SequenceMatcher(None, pw[0], x).ratio() for x in (pp[0], pp[-1]))
    return difflib.SequenceMatcher(None, "".join(pp), "".join(pw)).ratio()


def _match_people(people: List[str], written: List[str]) -> Tuple[List[str], List[str]]:
    """Abbina uno a uno i nomi della matrice ai nomi scritti sulla registrazione, i più simili
    prima. Ritorna (persone senza un nome corrispondente, nomi scritti rimasti senza persona)."""
    pairs = sorted(((_name_sim(p, w), i, j) for i, p in enumerate(people) for j, w in enumerate(written)), reverse=True)
    used_p, used_w = set(), set()
    for sim, i, j in pairs:
        if sim < _NAME_SIM:
            break
        if i not in used_p and j not in used_w:
            used_p.add(i)
            used_w.add(j)
    return ([p for i, p in enumerate(people) if i not in used_p],
            [w for j, w in enumerate(written) if j not in used_w])


def _common_folder(names: List[str]) -> str:
    """Cartella comune a tutti i file del pacco ("QHSE Management System/"): non distingue nulla."""
    if not names:
        return ""
    low = [_ws(n).replace("\\", "/") for n in names]
    prefix = low[0]
    for n in low[1:]:
        while not n.startswith(prefix):
            prefix = prefix[:-1]
    return prefix[:prefix.rfind("/") + 1]


def _course_tokens(course: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]{3,}", (course or "").lower()) if t not in _COURSE_GENERIC and t not in _STOP]


def _check_training(rows, spec, corpus: _Corpus, extract, today: Optional[dt.date] = None) -> List[Dict[str, Any]]:
    """Matrice: persona × corso × data → serve la registrazione di quel giorno, con quella persona.

    La sessione si riconosce dalla data scritta sulla registrazione (e dal corso, con tolleranza
    agli errori di lettura); un corso senza foglio presenze può essere provato da un attestato
    individuale. Regola sulle persone: si contesta una persona per nome solo se la registrazione
    è un documento leggibile (non la foto di un modulo scritto a mano), ha la stessa data e ogni
    nome che porta è riconosciuto; altrimenti è un solo punto "da verificare" per sessione."""
    out: List[Dict[str, Any]] = []
    file_name, clause = rows[0]["file_name"], spec.get("clause") or "ISO 9001 §7.2"
    person_col = spec.get("person_column")
    sessions: Dict[Tuple[str, dt.date], List[Tuple[str, Dict[str, Any], Optional[str], str]]] = {}
    all_people: List[str] = []
    for row in rows:
        person = str(row["fields"].get(person_col) or "").strip() if person_col else ""
        if not person:
            continue
        all_people.append(person)
        for c in _courses(spec):
            cell = row["fields"].get(c["date_column"])
            d = parse_date(cell)
            if not d or (today and d > today):          # una data futura è un piano, non un corso svolto
                continue
            note = re.sub(r"[\d/.\-]+", " ", str(cell))  # "25/04/2023 (NEBOSH)" → il titolo che lo prova
            trainer = str(row["fields"].get(c.get("trainer_column") or "") or "").strip() or None
            sessions.setdefault((c["course"], d), []).append((person, row, trainer, note))
    if not sessions:
        return out

    # Registrazioni di formazione del pacco, indicizzate per le date che portano scritte.
    recs: Dict[int, Set[dt.date]] = {}
    for i, (name, text) in enumerate(corpus.docs):
        if name == file_name:
            continue
        if not re.search(r"attendance|training|induction|course|presenze|formazione|signature|firma|"
                         r"addestramento|attestato|\bcorso\b|partecipanti",
                         _ws(name + " " + text[:3000])):
            continue
        dates = _all_dates(text[:700]) or _all_dates(_base(name))
        if not dates:
            d = parse_date((extract(name, text) or {}).get("date"))
            dates = {d} if d else set()
        recs[i] = dates

    def compatible(course: str, i: int) -> bool:
        toks = _course_tokens(course)
        seen = set(re.findall(r"[a-z0-9]{3,}", corpus.head(i, 400)))
        return not toks or any(difflib.get_close_matches(t, seen, n=1, cutoff=0.72) for t in toks)

    found: Dict[Tuple[str, dt.date], Tuple[List[int], bool]] = {}
    session_dates = {d for _, d in sessions}
    for (course, d) in sessions:
        exact = [i for i, ds in recs.items() if d in ds and compatible(course, i)]
        if exact:
            found[(course, d)] = (exact, False)
    for (course, d) in sessions:
        if (course, d) in found:
            continue
        # Stesso giorno e mese, anno diverso (data scritta a mano): solo se quella registrazione
        # non appartiene già a un'altra data della matrice.
        near = [i for i, ds in recs.items() if compatible(course, i) and not (ds & session_dates) and any(
            x.day == d.day and x.month == d.month and 0 < abs(x.year - d.year) <= 2 for x in ds)]
        if near:
            found[(course, d)] = (near, True)
    for (course, d), members in sessions.items():      # più argomenti lo stesso giorno, un solo foglio
        if (course, d) in found:
            continue
        mine = {m[0] for m in members}
        for (c2, d2), (cands, approx) in list(found.items()):
            if d2 == d and not approx and len(mine & {m[0] for m in sessions[(c2, d2)]}) * 2 >= len(mine):
                found[(course, d)] = (cands, False)
                break

    surnames = {_name_parts(p)[-1] for p in all_people if _name_parts(p)}
    root = len(_common_folder([n for n, _ in corpus.docs]))

    def has_certificate(person: str, course: str, note: str) -> bool:
        """Attestato individuale: un documento di quella persona (il suo cognome nel nome del
        file, o in testa al testo senza altri colleghi) che nomina il corso."""
        parts = _name_parts(person)
        toks = _course_tokens(course) + _course_tokens(note)
        if not parts or not toks:
            return False
        sur = parts[-1]
        for i in range(len(corpus.docs)):
            if corpus.name(i) == file_name:
                continue
            where = corpus.low[i][0][root:] + " " + corpus.low[i][1][:600]
            letters = re.sub(r"[^a-z]", "", where)
            own = sur in re.sub(r"[^a-z]", "", _base(corpus.low[i][0])) or (
                sur in letters and sum(1 for o in surnames if o != sur and o in letters) < 2)
            if own and sum(1 for t in toks if t in where) * 2 >= len(toks):
                return True
        return False

    # Giorni già provati da attestati individuali: le altre voci dello stesso giorno per le
    # stesse persone (familiarizzazione, autorizzazione dopo il corso) non chiedono un'altra prova.
    certified: Dict[Tuple[str, dt.date], Set[str]] = {}
    for (course, d), members in sessions.items():
        if (course, d) not in found:
            holders = {m[0] for m in members if has_certificate(m[0], course, m[3])}
            if len(holders) * 2 > len(members):
                certified[(course, d)] = {m[0] for m in members}

    def covered_by_sibling(course: str, d: dt.date, people: List[str]) -> bool:
        mine = set(people)
        return any(d2 == d and c2 != course and len(mine & who) * 2 >= len(mine) for (c2, d2), who in certified.items())

    missing_days: Dict[dt.date, List[str]] = {}
    unmatched: Dict[Tuple[dt.date, Tuple[int, ...], Tuple[str, ...]], Dict[str, Any]] = {}
    done_blank: Set[Tuple[int, ...]] = set()
    for (course, d), members in sessions.items():
        people = [m[0] for m in members]
        if (course, d) not in found:
            if covered_by_sibling(course, d, people):
                continue
            lacking = [m[0] for m in members if not has_certificate(m[0], course, m[3])]
            if len(lacking) * 2 >= len(people):
                missing_days.setdefault(d, []).append(f"{course} ({len(people)} people)")
            elif lacking:
                out.append(_check("training_attendance", "TO_VERIFY",
                                  f"{_base(file_name)} records '{course}' on {d.isoformat()}; no attendance record or "
                                  f"certificate was found in the pack for: {', '.join(lacking[:8])}",
                                  clause, [(file_name, _row_quote(members[0][1]))]))
            continue
        cands, approx = found[(course, d)]
        cands = cands[:4]
        facts_l = [extract(corpus.name(i), corpus.text(i)) or {} for i in cands]
        main = cands[0]
        handwritten = any(corpus.name(i).lower().endswith(_IMAGE_EXT) for i in cands)
        attendees = [str(a) for r in facts_l for a in (r.get("attendees") or []) if a]
        readable = any(r.get("attendees_readable") for r in facts_l) and len(attendees) >= 2

        if tuple(cands) not in done_blank and all(r.get("trainer_field_present") and not r.get("trainer") for r in facts_l):
            done_blank.add(tuple(cands))
            out.append(_check("record_field", "INCONSISTENT",
                              f"The trainer field of the '{course}' record of {d.isoformat()} is blank",
                              clause, [(corpus.name(main), "trainer: (blank)")]))
        rec_trainers = [str(r["trainer"]) for r in facts_l if r.get("trainer")]
        claimed = sorted({m[2] for m in members if m[2] and not re.fullmatch(r"n/?a|-|none", m[2].strip(), re.I)})
        if rec_trainers and claimed and not any(_names_match(c, t) or _name_sim(c, t) >= _NAME_SIM
                                                for c in claimed for t in rec_trainers):
            # Su un modulo scritto a mano il nome letto può essere sbagliato: vale come prova solo
            # se coincide con un'altra persona nota dell'organizzazione.
            other_known = any(_name_sim(p, t) >= _NAME_SIM for p in all_people for t in rec_trainers)
            status = "INCONSISTENT" if not approx and (not handwritten or other_known) else "TO_VERIFY"
            out.append(_check("trainer", status,
                              f"{_base(file_name)} names {', '.join(claimed)} as trainer for '{course}' on "
                              f"{d.isoformat()}; the record names {rec_trainers[0]}", clause,
                              [(file_name, _row_quote(members[0][1])), (corpus.name(main), f"trainer: {rec_trainers[0]}")]))

        absent, extra = _match_people(people, attendees)
        if not absent:
            continue
        unknown = [w for w in extra if not any(_name_sim(p, w) >= _NAME_SIM for p in all_people)]
        legible = readable and not unknown and not approx and not handwritten
        if legible and len(absent) <= _MAX_MISSING_PEOPLE:
            rows_by_person = {m[0]: m[1] for m in members}
            for person in absent:
                out.append(_check("training_attendance", "INCONSISTENT",
                                  f"{_base(file_name)} records {person} as trained in '{course}' on {d.isoformat()}, "
                                  f"but {person} is not on the attendance record of that session",
                                  clause, [(file_name, _row_quote(rows_by_person[person])),
                                           (corpus.name(main), "attendees: " + "; ".join(attendees)[:200])],
                                  person=person))
            continue
        key = (d, tuple(cands), tuple(sorted(absent)))
        entry = unmatched.setdefault(key, {"courses": [], "people": len(people), "main": main, "approx": approx,
                                           "handwritten": handwritten, "row": members[0][1]})
        entry["courses"].append(course)

    for (d, _cands, names), e in unmatched.items():
        why = ("the record carries a different year" if e["approx"]
               else "handwritten record" if e["handwritten"] else "attendee list unclear or incomplete")
        out.append(_check("training_attendance", "TO_VERIFY",
                          f"{_base(file_name)} lists {e['people']} people for {', '.join(e['courses'][:4])} on "
                          f"{d.isoformat()}; {len(names)} could not be matched to a name on the attendance record "
                          f"({why}): {', '.join(names[:8])}", clause,
                          [(file_name, _row_quote(e["row"])), (corpus.name(e["main"]), "attendance record")]))
    if missing_days:
        # Un solo rilievo: i giorni di formazione senza registrazione né attestati.
        days = [f"{d.isoformat()}: {', '.join(c)}" for d, c in sorted(missing_days.items())]
        out.append(_check("training_record", "MISSING",
                          f"{_base(file_name)} records training on {len(days)} date(s) with no attendance record or "
                          f"certificate in the pack: " + "; ".join(days[:10]) + ("…" if len(days) > 10 else ""),
                          clause, [(file_name, "training matrix")]))
    return out


# ── "teniamo / archiviamo X" ─────────────────────────────────────────────────

_CONDITIONAL = re.compile(r"where (?:applicable|required|necessary|relevant|appropriate)|if (?:applicable|required|"
                          r"necessary|any)|as (?:appropriate|applicable|required)|when (?:needed|required)|"
                          r"(?:ove|se|qualora|laddove|quando) (?:applicabile|necessari[oa]|previst[oa]|richiest[oa]|"
                          r"pertinente)|eventual[ei]", re.I)
_ENTITY_STOP = set("ltd limited plc llp inc company group services service systems solutions the and "
                   "srl srls spa snc sas scarl soc coop societa società consorzio ditta impresa".split())
_EVERY_SUPPLIER = re.compile(r"\b(?:each|every|all|any|ogni|ciascun[oa]?|tutti\s+i|tutte\s+le)\b[^.;]{0,80}"
                             r"\b(?:supplier|vendor|contractor|provider|fornitor[ei]|appaltator[ei]|"
                             r"subappaltator[ei])", re.I)
_EVERY_DOCUMENT = re.compile(r"\b(?:each|every|all|ogni|ciascun[oa]?|tutti\s+i|tutte\s+le)\b[^.;]{0,60}"
                             r"\b(?:document|procedur|sop\b|polic)", re.I)


def _entity_kind(per: Any, quote: str = "") -> Optional[str]:
    """A che cosa si riferisce "per ogni …". "document" vale solo se la frase citata parla davvero
    di ogni documento ("at the end of each document"): altrimenti non c'è nulla da confrontare."""
    p = str(per or "").lower()
    if not p or p in ("null", "none"):
        return None
    if re.search(r"suppl|vendor|contractor|provider|fornitor|appaltator", p):
        return "supplier"
    if re.search(r"document|procedur|\bsop\b|polic", p):
        return "document" if _EVERY_DOCUMENT.search(quote or "") or not quote else "other"
    return "other"


def _is_self_reference(subject: str, src: str, doc_type: str = "") -> bool:
    """La "registrazione" dichiarata è il documento stesso ("this policy is maintained")."""
    s = _stems(subject)
    return bool(s) and s <= (_stems(_base(src).rsplit(".", 1)[0]) | _stems(str(doc_type).replace("_", " ")))


def _entity_keys(entities: List[str]) -> Dict[str, List[str]]:
    """Per ogni soggetto, le parole che bastano a riconoscerlo tra gli altri dell'elenco:
    "Greenline Waste Ltd" → greenline; "Yorkshire Steel Stockholders" → yorkshire + steel
    (perché c'è anche "West Yorkshire Gases")."""
    toks = {e: [t for t in re.findall(r"[a-z0-9]{3,}", _ws(re.sub(r"\(.*?\)", " ", e))) if t not in _ENTITY_STOP]
            for e in entities}
    keys: Dict[str, List[str]] = {}
    for e, ts in toks.items():
        key: List[str] = []
        for t in ts:
            key.append(t)
            if not any(o != e and all(k in toks[o] for k in key) for o in toks):
                break
        keys[e] = key
    return keys


def _entity_docs(key: List[str], corpus: _Corpus, exclude: Set[str], by_path: bool) -> List[int]:
    """Documenti del pacco che riguardano quel soggetto: nella sua cartella / con il suo nome nel
    file quando il pacco è ordinato così, altrimenti con il nome in testa al testo."""
    if not key:
        return []
    out = []
    for i in range(len(corpus.docs)):
        if corpus.name(i) in exclude:
            continue
        where = corpus.low[i][0] if by_path else corpus.head(i, 1500)
        if all(re.search(r"(?<![a-z0-9])" + re.escape(t), where) for t in key):
            out.append(i)
    return out


def _check_per_entity(claim, src: str, corpus: _Corpus, entities: List[str],
                      exclude: Set[str]) -> Optional[List[Dict[str, Any]]]:
    """"Per ogni fornitore teniamo X". Si contesta solo se X esiste per alcuni e manca per altri:
    è la prassi dell'organizzazione stessa a dire che quella registrazione si tiene (se la frase
    non dice "ogni fornitore", deve averla almeno la metà). Se non c'è per nessuno può stare
    fuori dal pacco: resta da verificare. None = il confronto per fornitore non si applica
    (resta la verifica semplice "esiste nel pacco?")."""
    subject, quote = str(claim.get("subject") or ""), str(claim.get("quote") or "")
    kind_stems = _stems(subject)
    if not kind_stems or len(entities) < 2:
        return None
    need = max(1, math.ceil(len(kind_stems) / 2))
    keys = _entity_keys(entities[:40])
    skip = exclude | {src}
    by_path = any(_entity_docs(k, corpus, skip, True) for k in keys.values())
    have: List[str] = []
    lacking: List[str] = []
    for ent, key in keys.items():
        ok = any(sum(1 for s in kind_stems if re.search(r"(?<![a-z0-9])" + re.escape(s), corpus.head(i))) >= need
                 for i in _entity_docs(key, corpus, skip, by_path))
        (have if ok else lacking).append(ent)
    if not lacking:
        return []
    every = bool(_EVERY_SUPPLIER.search(quote))
    clause = claim.get("clause") or ""
    if not have:
        if not every:
            return None
        return [_check("declared_record", "TO_VERIFY",
                       f"{_base(src)} says the organisation keeps {subject} for each supplier; none was found in the pack for any "
                       f"supplier (it may be held elsewhere)", clause, [(src, quote)])]
    n = len(have) + len(lacking)
    if not every and len(have) * 2 < n:
        return None         # la tengono in pochi e la frase non dice "ogni": non è una regola per tutti
    # Vale solo se la registrazione è diffusa (un terzo dei fornitori con "ogni", metà senza):
    # trovata per pochissimi vuol dire che la chiamano in un altro modo, non che manca.
    if len(have) * 3 < n:
        return None
    status = "TO_VERIFY" if _CONDITIONAL.search(quote) else "MISSING"
    chk = _check("declared_record", status,
                 f"{_base(src)} says the organisation keeps {subject} for each supplier; found for {len(have)} of "
                 f"{len(have) + len(lacking)}, none found for: {', '.join(lacking[:8])}"
                 + ("…" if len(lacking) > 8 else ""), clause, [(src, quote)])
    chk["lacking"] = sorted(lacking)
    return [chk]


def _check_document_feature(claim, src: str, docs: List[Tuple[str, str]], present_in) -> List[Dict[str, Any]]:
    """"Ogni documento controllato porta X" (tabella delle revisioni, firma di approvazione).
    present_in(nome, testo) → True (citazione verificata) | False | None (non determinabile)."""
    subject, quote = str(claim.get("subject") or ""), str(claim.get("quote") or "")
    found, lacking = [], []
    for name, text in docs[:MAX_FEATURE_DOCS]:
        r = present_in(name, text)
        if r is True:
            found.append(name)
        elif r is False:
            lacking.append(name)
    n = len(found) + len(lacking)
    if n < 3 or not lacking:
        return []
    clause = claim.get("clause") or "ISO 9001 §7.5"
    if not found:
        return [_check("document_feature", "MISSING",
                       f"{_base(src)} requires every controlled document to carry {subject}; none of the {n} "
                       f"documents checked shows one", clause, [(src, quote)])]
    return [_check("document_feature", "TO_VERIFY",
                   f"{_base(src)} requires every controlled document to carry {subject}; not seen in "
                   f"{len(lacking)} of {n}: {', '.join(_base(x) for x in lacking[:6])}", clause, [(src, quote)])]


_KEEPING = re.compile(r"\b(?:record(?:ed|s)?|kept|keeps?|stor(?:ed|es?|age)|maintain(?:ed|s)?|retain(?:ed|s)?|"
                      r"archiv(?:ed|es?)|fil(?:ed|es?)|logg?(?:ed|s)?|held|issued?|sent|collect(?:ed|s)?|"
                      r"documented|evidence|minut(?:ed|es)|sign(?:ed|s)?|complet(?:ed|es?)|return(?:ed|s)?|"
                      r"submit(?:ted|s)?|report(?:ed|s)?|"
                      r"registrat[oaie]|registrazion[ei]|conservat[oaie]|archiviat[oaie]|tenut[oaie]|mantenut[oaie]|"
                      r"custodit[oaie]|verbalizzat[oaie]|verbal[ei]|compilat[oaie]|firmat[oaie]|sottoscritt[oaie]|"
                      r"trasmess[oaie]|inviat[oaie]|rilasciat[oaie]|raccolt[oaie]|documentat[oaie]|evidenz[ae]|"
                      r"annotat[oaie]|riportat[oaie])\b", re.I)
_NOT_A_RECORD = set("obsolete archived superseded previous controlled master active current version versions old "
                    "copy copies obsoleto obsoleti superato superati precedente precedenti versione versioni "
                    "vigente vigenti".split())


def _is_record_claim(claim: Dict[str, Any]) -> bool:
    """La frase citata parla davvero di tenere una registrazione: porta un verbo o un nome di
    registrazione ("recorded", "stored", "minutes", "evidence"). "Preventing pollution" in una
    politica non promette nessuna registrazione; "obsolete copies are archived" non è una prova
    di attività svolta."""
    if _entity_kind(claim.get("per_entity"), str(claim.get("quote") or "")) == "document":
        return True
    if not _KEEPING.search(str(claim.get("quote") or "")):
        return False
    return bool(_stems(str(claim.get("subject") or "")) - {t.rstrip("s")[:7] for t in _NOT_A_RECORD})


def _names_pack_folder(text: str, folders: Set[str]) -> bool:
    """La frase indica una cartella che esiste nel pacco ricevuto ("stored in 8 Operations/Waste",
    "on the QHSE Management System"): allora la registrazione doveva essere lì."""
    low = _ws(text)
    return any(len(f) >= 6 and f in low for f in folders)


def _check_record_kept(claim, src: str, verify, in_inventory=None, rule_doc: bool = True,
                       has_entry=None) -> List[Dict[str, Any]]:
    """"Teniamo / archiviamo X" → X deve esistere nel pacco, fuori dal documento che lo dichiara.
    Non trovata solo se non è tra i file del pacco (elenco completo) e la ricerca nel testo di
    tutto il pacco non la trova. È una mancanza provata (rule_doc) solo quando la dichiara una
    procedura e la colloca dentro il pacco ricevuto; altrimenti il pacco è un campione e resta
    "da verificare".
    Se il file c'è ("i reclami sono registrati nel registro NC") ma non contiene nessuna voce di
    quel tipo, è un punto da verificare: può non essercene stata nessuna."""
    subject, quote = str(claim.get("subject") or ""), str(claim.get("quote") or "")
    files = in_inventory(subject, quote, src) if in_inventory is not None else None
    if files:
        first = files[0] if isinstance(files, list) else None
        if first and has_entry is not None and has_entry(subject, quote, first) is False:
            return [_check("declared_content", "TO_VERIFY",
                           f"{_base(src)} says {_base(first)} holds {subject}; no such entry was found "
                           f"there (confirm that none occurred)", claim.get("clause") or "", [(src, quote)])]
        return []
    if verify(subject, quote, src) is not False:
        return []
    return [_check("declared_record", "MISSING" if rule_doc else "TO_VERIFY",
                   f"{_base(src)} says the organisation keeps {subject}, but no such record is in the pack (whole pack "
                   f"searched)",
                   claim.get("clause") or "", [(src, quote)])]


# ── stesso oggetto, due documenti, due valori ───────────────────────────────

def _value_in_quote(claim: Dict[str, Any]) -> bool:
    """Il valore estratto dal modello sta scritto nella frase citata (cita-o-cade anche per i
    numeri): una data presa da un altro punto del documento non è la data di quell'attività."""
    quote = str(claim.get("quote") or "")
    if claim.get("type") == "date":
        d = parse_date(claim.get("value"))
        return d is not None and d in _all_dates(quote)
    n = _num(claim.get("value"))
    if n is None:
        return False
    found = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", quote)]
    found += [float(_WORDS[w]) for w in re.findall(r"[a-z]+", quote.lower()) if w in _WORDS]
    return any(abs(x) == abs(n) for x in found)


def _mask_values(text: str) -> str:
    """Nasconde date e cifre isolate (non i codici come IA-01): chi allinea due dichiarazioni
    deve dire se parlano della stessa cosa, senza farsi guidare dai valori."""
    t = re.sub(r"\b\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4}\b", "#", text or "")
    return re.sub(r"(?<![A-Za-z0-9-])\d+(?:[.,]\d+)?\s?%?(?![A-Za-z0-9])", "#", t)


def _claim_codes(file_name: str, claim: Dict[str, Any]) -> Set[str]:
    text = " ".join([_base(file_name), str(claim.get("subject") or ""), str(claim.get("quote") or "")])
    return {_norm_code(m.group(0)) for m in _CODE.finditer(text) if not _STANDARD_REF.match(m.group(0))}


def _differs(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """I due valori, se riguardano la stessa cosa, sono una contraddizione?"""
    if a.get("type") == "date":
        # Solo pianificata contro effettiva, entro 45 giorni: oltre sono eventi diversi.
        if bool(a.get("planned")) == bool(b.get("planned")):
            return False
        va, vb = parse_date(a.get("value")), parse_date(b.get("value"))
        return not (va is None or vb is None or va == vb or abs((va - vb).days) > 45 or _ambiguous_dates(va, vb))
    na, nb = _num(a.get("value")), _num(b.get("value"))
    if na is None or nb is None or abs(na) == abs(nb):
        return False
    if a.get("type") == "value":
        # Solo obiettivo contro obiettivo: un risultato misurato non contraddice un obiettivo.
        if not (a.get("planned") and b.get("planned")):
            return False
        if ("%" in str(a.get("value"))) != ("%" in str(b.get("value"))):
            return False
    return True


def _compare_values(claims: List[Tuple[str, Dict[str, Any]]], same_thing=None) -> List[Dict[str, Any]]:
    """Stessa cosa, due documenti, due valori diversi → contraddizione. Stessa cosa: oggetti quasi
    identici; altrimenti (una parola o un codice in comune) lo conferma same_thing(coppie) →
    lista di bool. Un rilievo per gruppo di dichiarazioni, non uno per coppia."""
    sure, ask = [], []
    for i, (fa, a) in enumerate(claims):
        for j in range(i + 1, len(claims)):
            fb, b = claims[j]
            if fa == fb or a.get("type") != b.get("type") or not _differs(a, b):
                continue
            sa, sb = _stems(a.get("subject", "")), _stems(b.get("subject", ""))
            shared = sa & sb
            codes = _claim_codes(fa, a) & _claim_codes(fb, b)
            if a.get("type") == "date":
                # Audit, riunioni e prove si ripetono: due date riguardano lo stesso evento solo
                # se le lega un codice (IA-01), e lo conferma chi allinea.
                if codes:
                    ask.append((i, j))
            elif (a.get("link") and a.get("link") == b.get("link")) or (
                    len(shared) >= 2 and len(shared) / len(sa | sb) >= 0.6):
                sure.append((i, j))
            elif shared or codes:
                ask.append((i, j))
    ask = ask[:MAX_PAIRS_TO_ALIGN]
    if ask and same_thing is not None:
        try:
            answers = same_thing([(claims[i], claims[j]) for i, j in ask])
        except Exception as e:
            _log.warning("[self_consistency] allineamento dichiarazioni fallito: %s", e)
            answers = []
        sure += [p for p, ok in zip(ask, answers) if ok]

    parent = list(range(len(claims)))

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in sure:
        parent[root(i)] = root(j)
    first: Dict[int, Tuple[int, int]] = {}
    members: Dict[int, Set[int]] = {}
    for i, j in sorted(sure):
        r = root(i)
        first.setdefault(r, (i, j))
        members.setdefault(r, set()).update((i, j))
    out = []
    for r, (i, j) in first.items():
        (fa, a), (fb, b) = claims[i], claims[j]
        more = f" ({len(members[r])} documents state it)" if len(members[r]) > 2 else ""
        out.append(_check(f"{a['type']}_mismatch", "INCONSISTENT",
                          f"{a.get('subject')}: {_base(fa)} says {a.get('value')}, {_base(fb)} says {b.get('value')}{more}",
                          a.get("clause") or b.get("clause") or "", [(fa, a.get("quote", "")), (fb, b.get("quote", ""))]))
    return out


def _count_listed(items: List[Any], text: str) -> Tuple[int, bool]:
    """Voci elencate dal modello e ritrovate alla lettera nel testo. exact=False se la stessa
    etichetta si ripete (simboli uguali su una planimetria): il conteggio è indicativo."""
    low = _ws(text)
    seen: Dict[str, int] = {}
    count, exact = 0, True
    for it in items or []:
        k = _ws(str(it)).strip(" .:-")
        if len(k) < 2:
            continue
        occ = len(re.findall(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", low))
        if not occ:
            continue
        seen[k] = seen.get(k, 0) + 1
        if seen[k] <= occ:
            count += 1
        if seen[k] > 1:
            exact = False
    return count, exact


def _check_listed_quantity(claim, src: str, other: str, text: str, listing: Dict[str, Any]) -> List[Dict[str, Any]]:
    """"Nove estintori" contro la planimetria che ne mostra sei: il modello elenca le voci,
    Python le ritrova nel testo e le conta."""
    n = _num(claim.get("value"))
    if n is None or not listing.get("complete"):
        return []
    count, exact = _count_listed(listing.get("items") or [], text)
    if count < 2 or count == int(n):
        return []
    subject = str(claim.get("subject") or "")
    return [_check("quantity_mismatch", "INCONSISTENT" if exact else "TO_VERIFY",
                   f"{_base(src)} states {int(n)} {subject}; {_base(other)} " + ("shows " if exact else "appears to show ")
                   + str(count), claim.get("clause") or "", [(src, claim.get("quote", "")), (other, f"{count} listed")])]


def _check_versions(facts: Facts) -> List[Dict[str, Any]]:
    out = []
    for d in facts.documents.values():
        if d.get("issuer") != "client" or not d.get("version"):
            continue
        m = re.search(r"\bv(?:er(?:sion)?)?\.?\s?(\d+(?:\.\d+)?)\b", _base(d["file_name"]), re.I)
        n_doc = _num(d["version"])
        if m and n_doc is not None and float(m.group(1)) != n_doc:
            out.append(_check("version", "INCONSISTENT",
                              f"{_base(d['file_name'])}: the file name says version {m.group(1)}, the document says "
                              f"{d['version']}", "ISO 9001 §7.5", [(d["file_name"], f"version: {d['version']}")]))
    return out


# ── orchestrazione ───────────────────────────────────────────────────────────

# Documenti di sistema del cliente da cui si estraggono dichiarazioni. Le singole registrazioni
# (attestati, fogli presenze, certificati), le valutazioni dei rischi e i modelli vuoti non
# dichiarano regole: i loro valori riguardano persone ed eventi diversi (banco Box: punteggi di
# rischio e voti d'esame confrontati come "valori in contraddizione").
_SYSTEM_DOC_TYPES = {"quality_manual", "procedure", "policy", "management_review", "objective_plan",
                     "emergency_plan", "legal_register", "audit_report"}
# Una dichiarazione di archiviazione è un impegno verificabile se viene da procedure, manuale,
# politiche e registro legale. Da obiettivi e verbali resta un punto da verificare.
_RULE_DOC_TYPES = {"quality_manual", "procedure", "policy", "legal_register", "emergency_plan"}
_CONTROLLED_DOC_TYPES = {"quality_manual", "procedure", "policy", "emergency_plan"}
_TEMPLATE = re.compile(r"template|\btemp\s?\d|fac[- ]?simile", re.I)
_SPREADSHEET = (".xlsx", ".xls", ".xlsm", ".ods")


def run(docs: List[Dict[str, Any]], facts: Facts, audit_date: dt.date,
        verify_record: Callable[[str, str, str], Optional[bool]],
        trace: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    from v2.azure_openai_client_v2 import make_client
    mini, deep = make_client(), make_client(deep=True)
    corpus = _Corpus(docs)
    cache: Dict[str, Dict[str, Any]] = {}

    def doc_type(name: str) -> str:
        return str(facts.document(name).get("doc_type") or "other")

    def extract(name: str, text: str) -> Dict[str, Any]:
        if name not in cache:
            cache[name] = _ask(deep, RECORD_PROMPT.format(file=_base(name), text=text[:12000]), 1200)
        return cache[name]

    checks: List[Dict[str, Any]] = []
    sheets = _sheets(facts)

    def classify(item):
        (fname, sheet), rows = item
        cols = list(rows[0]["fields"].keys())
        spec = _ask(mini, SHEET_PROMPT.format(sheet=sheet, file=_base(fname), columns=" | ".join(cols),
                                               rows="\n".join(_row_quote(r) for r in rows[:5])), 3000)
        return (fname, sheet), rows, spec

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        classified = list(ex.map(classify, sheets.items()))

    suppliers: List[str] = []
    entity_files: Set[str] = set()
    value_claims: List[Tuple[str, Dict[str, Any]]] = []
    for (fname, sheet), rows, spec in classified:
        kind = spec.get("kind")
        if kind == "supplier_list" and spec.get("entity_column"):
            entity_files.add(fname)
            for r in rows:
                name = str(r["fields"].get(spec["entity_column"]) or "").strip()
                if name and name not in suppliers:
                    suppliers.append(name)
        if kind in ("objectives", "audit_programme") and spec.get("item_column"):
            for r in rows:
                item = str(r["fields"].get(spec["item_column"]) or "")
                if spec.get("value_column") and r["fields"].get(spec["value_column"]):
                    value_claims.append((fname, {"type": "value", "subject": item, "clause": spec.get("clause"),
                                                 "value": r["fields"][spec["value_column"]], "quote": _row_quote(r),
                                                 "planned": True}))
                if spec.get("planned_date_column") and r["fields"].get(spec["planned_date_column"]):
                    value_claims.append((fname, {"type": "date", "subject": item, "clause": spec.get("clause"),
                                                 "value": r["fields"][spec["planned_date_column"]], "quote": _row_quote(r),
                                                 "planned": True}))

    def check_sheet(entry):
        (fname, sheet), rows, spec = entry
        kind = spec.get("kind")
        try:
            if kind in ("reference_register", "supplier_list"):
                return _check_reference_register(rows, spec, corpus, extract)
            if kind == "nc_log":
                return _check_nc_log(rows, spec, audit_date)
            if kind == "training_matrix":
                return _check_training(rows, spec, corpus, extract, audit_date)
        except Exception as e:
            _log.warning("[self_consistency] foglio %s/%s: %s", _base(fname), sheet, e)
        return []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for res in ex.map(check_sheet, classified):
            checks.extend(res)

    # Dichiarazioni nei testi dei documenti di sistema del cliente (fogli: solo il registro legale).
    client_docs = [(n, t) for n, t in corpus.docs
                   if not facts.is_external(n) and len(t) > 200 and doc_type(n) in _SYSTEM_DOC_TYPES
                   and not _TEMPLATE.search(_base(n))
                   and (not n.lower().endswith(_SPREADSHEET) or doc_type(n) == "legal_register")]

    def claims_of(part):
        name, text = part
        out = _ask(deep, CLAIMS_PROMPT.format(file=_base(name), text=text), 3500).get("claims") or []
        return [(name, c) for c in out if isinstance(c, dict) and _quote_in(str(c.get("quote") or ""), text)]

    # Un manuale lungo si legge a blocchi (fino a tre): le dichiarazioni utili stanno anche in fondo.
    parts = [(n, t[i:i + CLAIMS_CHUNK]) for n, t in client_docs
             for i in range(0, min(len(t), 3 * CLAIMS_CHUNK), CLAIMS_CHUNK) if len(t[i:i + CLAIMS_CHUNK]) > 200]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        all_claims = [c for lst in ex.map(claims_of, parts) for c in lst]

    value_claims += [(n, c) for n, c in all_claims if c.get("type") in ("quantity", "value", "date")
                     and _value_in_quote(c)]
    record_claims, seen_records = [], set()
    for n, c in all_claims:
        subject = str(c.get("subject") or "")
        key = (n, frozenset(_stems(subject)))
        if c.get("type") != "record_kept" or key in seen_records or not _is_record_claim(c) \
                or _is_self_reference(subject, n, doc_type(n)):
            continue
        seen_records.add(key)
        record_claims.append((n, c))
    # Prima ciò che l'organizzazione elenca come propria evidenza (registro legale), poi gli
    # impegni di procedure e manuale, poi il resto.
    rank = {"legal_register": 0, "procedure": 1, "emergency_plan": 1, "quality_manual": 2, "policy": 3}
    record_claims.sort(key=lambda x: rank.get(doc_type(x[0]), 4))

    inventory = "\n".join(f"{i}. {n} [{doc_type(n)}]" for i, (n, _) in enumerate(corpus.docs, 1))

    def in_inventory(subject: str, quote: str, src: str) -> List[str]:
        files = _ask(deep, INVENTORY_PROMPT.format(src=_base(src), quote=quote[:300], subject=subject,
                                                    inventory=inventory[:24000]), 200).get("files") or []
        idx = [int(x) for x in files if str(x).isdigit() and 1 <= int(x) <= len(corpus.docs)]
        return [corpus.name(i - 1) for i in idx
                if corpus.name(i - 1) != src and not _TEMPLATE.search(_base(corpus.name(i - 1)))]

    texts = dict(corpus.docs)
    folders = {_ws(part) for n, _ in corpus.docs for part in n.replace("\\", "/").split("/")[:-1] if part.strip()}

    def has_entry(subject: str, quote: str, file_name: str) -> Optional[bool]:
        text = texts.get(file_name, "")
        r = _ask(deep, ENTRY_PROMPT.format(quote=quote[:300], subject=subject, file=_base(file_name),
                                           text=text[:14000]), 300)
        if r.get("present") is False:
            return False
        return True if r.get("present") and _quote_in(str(r.get("quote") or ""), text) else None

    controlled = [(n, t) for n, t in corpus.docs if not facts.is_external(n) and len(t) > 200
                  and doc_type(n) in _CONTROLLED_DOC_TYPES and not _TEMPLATE.search(_base(n))]

    def check_record(item):
        src, claim = item
        try:
            quote = str(claim.get("quote") or "")
            kind = _entity_kind(claim.get("per_entity"), quote)
            if kind == "supplier":
                per = _check_per_entity(claim, src, corpus, suppliers, entity_files)
                if per is not None:
                    return per
            if kind == "document":
                def present_in(name: str, text: str) -> Optional[bool]:
                    body = text if len(text) <= 10000 else text[:5000] + "\n[...]\n" + text[-5000:]
                    r = _ask(deep, FEATURE_PROMPT.format(src=_base(src), quote=str(claim.get("quote") or "")[:300],
                                                         subject=claim.get("subject"), file=_base(name), text=body), 200)
                    if r.get("present") is False:
                        return False
                    return True if r.get("present") and _quote_in(str(r.get("quote") or ""), text) else None
                # il documento che enuncia la regola la cita per forza: non conta come prova
                return _check_document_feature(claim, src, [d for d in controlled if d[0] != src], present_in)
            located = _names_pack_folder(quote + " " + str(claim.get("value") or ""), folders)
            return _check_record_kept(claim, src, verify_record, in_inventory,
                                      rule_doc=located and doc_type(src) in _RULE_DOC_TYPES, has_entry=has_entry)
        except Exception as e:
            _log.warning("[self_consistency] dichiarazione %s: %s", _base(src), e)
            return []

    declared: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for res in ex.map(check_record, record_claims[:MAX_RECORD_CLAIMS]):
            declared.extend(res)
    # "Per ogni fornitore": più frasi dicono la stessa cosa; un rilievo per elenco di fornitori scoperti.
    seen_lacking: Set[Tuple[str, ...]] = set()
    kept: List[Dict[str, Any]] = []
    for c in declared:
        lacking = c.pop("lacking", None)
        if lacking is not None:
            if tuple(lacking) in seen_lacking:
                continue
            seen_lacking.add(tuple(lacking))
        kept.append(c)
    to_verify = [c for c in kept if c["status"] == "TO_VERIFY"]
    checks.extend([c for c in kept if c["status"] != "TO_VERIFY"] + to_verify[:MAX_TO_VERIFY_RECORDS])

    def same_thing(pairs) -> List[bool]:
        rows = []
        for k, ((fa, a), (fb, b)) in enumerate(pairs, 1):
            rows.append(f"[{k}] A ({_base(fa)}): {a.get('subject')} — \"{_mask_values(str(a.get('quote'))[:200])}\"\n"
                        f"    B ({_base(fb)}): {b.get('subject')} — \"{_mask_values(str(b.get('quote'))[:200])}\"")
        got = _ask(deep, SAME_PROMPT.format(pairs="\n".join(rows)), 1200).get("pairs") or []
        same = {int(str(p.get("id"))): bool(p.get("same")) for p in got
                if isinstance(p, dict) and str(p.get("id")).isdigit()}
        return [same.get(k, False) for k in range(1, len(pairs) + 1)]

    # Obiettivi: il valore-obiettivo del piano si ricerca negli altri documenti di sistema (riesame,
    # audit, manuale). È il controllo classico "obiettivi contro riesame", fatto in modo mirato:
    # l'estrazione libera delle dichiarazioni non garantisce di cogliere la stessa cifra due volte.
    objective_files = {f for (f, _), _, spec in classified if spec.get("kind") == "objectives"}
    targets = [(n, c) for n, c in value_claims if c.get("type") == "value" and c.get("planned")
               and (doc_type(n) == "objective_plan" or n in objective_files)][:12]

    def restated(item):
        src, claim = item
        stems = _stems(str(claim.get("subject") or ""))
        claim["link"] = f"{src}|{claim.get('subject')}"
        out = []
        for name, text in client_docs:
            if name == src or not stems:
                continue
            lines = [ln.strip() for ln in re.split(r"(?<=[.!?])\s+|\n", text) if ln.strip()]
            hits = [k for k, ln in enumerate(lines)
                    if any(re.search(r"(?<![a-z0-9])" + re.escape(st), ln.lower()) for st in stems)]
            if not hits or not all(re.search(r"(?<![a-z0-9])" + re.escape(st), text.lower()) for st in stems):
                continue
            passages = list(dict.fromkeys(" ".join(lines[max(0, k - 1):k + 2])[:500] for k in hits))[:5]
            r = _ask(deep, TARGET_PROMPT.format(subject=claim.get("subject"), file=_base(name),
                                                passages="\n".join(f"- {x}" for x in passages)), 300)
            new = {"type": "value", "subject": claim.get("subject"), "value": r.get("value"), "planned": True,
                   "quote": str(r.get("quote") or ""), "clause": claim.get("clause"), "link": claim["link"]}
            if r.get("stated") and _quote_in(new["quote"], text) and _value_in_quote(new):
                out.append((name, new))
        return out

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for res in ex.map(restated, targets):
            value_claims.extend(res)

    checks.extend(_compare_values(value_claims, same_thing))

    # Quantità dichiarata contro le voci di una planimetria / di un elenco.
    def check_quantity(item):
        src, claim = item
        n = _num(claim.get("value"))
        want = _stems(str(claim.get("subject") or ""))
        if n is None or not 2 <= n <= 200 or n != int(n) or not want:
            return []
        out = []
        cands = [i for i in range(len(corpus.docs)) if corpus.name(i) != src and not facts.is_external(corpus.name(i))
                 and all(re.search(r"(?<![a-z0-9])" + re.escape(s), corpus.head(i, 400)) for s in want)]
        for i in cands[:3]:
            listing = _ask(deep, LIST_PROMPT.format(file=_base(corpus.name(i)), text=corpus.text(i)[:6000],
                                                    quote=str(claim.get("quote") or "")[:300],
                                                    subject=claim.get("subject")), 1500)
            out.extend(_check_listed_quantity(claim, src, corpus.name(i), corpus.text(i), listing))
        return out

    quantities = [(n, c) for n, c in all_claims if c.get("type") == "quantity"][:20]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for res in ex.map(check_quantity, quantities):
            checks.extend(res)

    checks.extend(_check_versions(facts))

    seen: Set[str] = set()
    unique = []
    for c in checks:
        if c["description"] not in seen:
            seen.add(c["description"])
            unique.append(c)
    if trace is not None:     # banco di misura: cosa è stato estratto, prima dei confronti
        trace["sheets"] = [{"file": _base(f), "sheet": sh, "rows": len(rows), "spec": spec}
                           for (f, sh), rows, spec in classified]
        trace["claims"] = [{"file": _base(n), **c} for n, c in all_claims]
        trace["value_claims"] = [{"file": _base(n), **c} for n, c in value_claims]
        trace["records"] = {_base(k): v for k, v in cache.items()}
        trace["suppliers"] = suppliers
    _log.info("[self_consistency] %d registri, %d dichiarazioni, %d esiti", len(classified), len(all_claims), len(unique))
    return unique


# ── aggancio alle clausole (un fatto, un giudizio) ──────────────────────────

_NORM_OF = {"9001": "ISO 9001:2015", "14001": "ISO 14001:2015", "45001": "ISO 45001:2018"}
_DEFAULT_CLAUSE = {
    "training_record": "7.2", "training_attendance": "7.2", "trainer": "7.2", "record_field": "7.5",
    "overdue_action": "10.2", "register_vs_record": "9.1", "referenced_record": "7.5", "file_name": "7.5",
    "version": "7.5", "declared_record": "7.5", "document_feature": "7.5", "value_mismatch": "9.3",
    "date_mismatch": "9.2", "quantity_mismatch": "8.2",
}


def _target(check: Dict[str, Any], clauses_by_norm: Dict[str, Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    m = re.search(r"(9001|14001|45001)\D+(\d+(?:\.\d+)*)", str(check.get("clause") or ""))
    wanted = _NORM_OF.get(m.group(1)) if m else None
    number = m.group(2) if m else _DEFAULT_CLAUSE.get(check["kind"], "7.5")
    order = ([wanted] if wanted in clauses_by_norm else []) + [n for n in clauses_by_norm if n != wanted]
    for norm in order:
        prefix = norm.split()[1].split(":")[0] if norm.startswith("ISO ") else norm
        for num in (number, _DEFAULT_CLAUSE.get(check["kind"], "7.5")):
            parts = num.split(".")
            for k in range(len(parts), 0, -1):
                cid = f"{prefix}_" + "_".join(parts[:k])
                if cid in clauses_by_norm[norm]:
                    return norm, cid
    return None


def attach(norm_reports: List[Any], checks: List[Dict[str, Any]],
           clauses_by_norm: Dict[str, Dict[str, Any]]) -> List[Any]:
    """Ogni esito diventa un controllo sulla clausola competente di UNA norma;
    poi gravità e azioni si ricalcolano sulle clausole toccate."""
    from compliance import features
    from compliance.gap_analyzer import _build_norm_report
    from compliance.schemas import RequirementCheck

    by_norm = {r.norm: r for r in norm_reports}
    touched: Dict[Tuple[str, str], Any] = {}
    for n, chk in enumerate(checks, 1):
        if chk["status"] == "CONSISTENT":
            continue
        tgt = _target(chk, {k: v for k, v in clauses_by_norm.items() if k in by_norm})
        if not tgt:
            continue
        norm, cid = tgt
        gap = next((g for g in by_norm[norm].clauses if g.clause_id == cid), None)
        if gap is None:
            continue
        chk["attached_to"] = f"{norm} {cid}"
        if chk["status"] == "TO_VERIFY":
            gap.to_verify.append(chk["description"][:220])
        else:
            first = chk["cites"][0] if chk["cites"] else {"file_name": None, "quote": None}
            second = chk["cites"][1] if len(chk["cites"]) > 1 else {"file_name": None, "quote": None}
            gap.requirement_checks.append(RequirementCheck(
                requirement_id=f"{cid}.self.{n}",
                status="CONTRADICTED" if chk["status"] == "INCONSISTENT" else "ABSENT",
                requirement_text=chk["description"][:300],
                evidence_quote=first["quote"], file_name=first["file_name"],
                counter_quote=second["quote"], counter_file_name=second["file_name"],
                searched=chk["status"] == "MISSING",
                search_note=("Declared by the organisation but not found in the pack (whole pack searched)."
                             if chk["status"] == "MISSING" else None),
                note=chk["description"][:200]))
        touched[(norm, cid)] = gap

    for (norm, cid), gap in touched.items():
        clause = clauses_by_norm[norm].get(cid, {})
        if features.on("SEVERITY_RULES"):
            from compliance import severity_rules
            severity_rules.apply(gap, clause)
        if features.on("ACTIONS_FROM_STATES"):
            from compliance import action_rules
            action_rules.apply(gap, clause)
            own = [c.requirement_text for c in gap.requirement_checks
                   if ".self." in c.requirement_id and c.requirement_text]
            if own and "Own records:" not in gap.finding:
                gap.finding = (gap.finding.rstrip() + " Own records: " + "; ".join(own[:5]) + ".")[:1600]
    return [_build_norm_report(r.norm, r.clauses, clauses_by_norm.get(r.norm)) for r in norm_reports]
