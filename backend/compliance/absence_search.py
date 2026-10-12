"""
absence_search.py — Piano motore Fase 2 (ABSENCE_SEARCH): prima di dire
"non c'è", cercare in tutto il pacco.

Lo Stage B legge al massimo 3 documenti per clausola: un requisito che non
trova lì diventava ABSENT, e l'assenza diventava un'accusa senza prova (banco
Box: 11 delle 25 accuse sbagliate dell'auditor sono "mancante" su cose
presenti). Qui ogni requisito ABSENT viene cercato nel testo completo di TUTTI
i documenti:
  1. per parole, con i termini EN/IT del requisito (iso_clauses/search_terms.json):
     l'embedding in uso è solo inglese e non trova un "verbale di riesame";
  2. per significato, sull'indice dei frammenti;
  3. i passaggi migliori vanno al modello, che deve CITARE: la citazione si
     verifica in Python sul testo del passaggio (cite-or-fail).
Esito: trovato → PRESENT/PARTIAL con la fonte; non trovato → ABSENT con
searched=True e la nota della ricerca (solo allora l'assenza è una prova).
Se la ricerca fallisce per un errore tecnico il requisito resta non cercato,
quindi "da verificare": un errore non diventa mai un'accusa.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from compliance.schemas import ClauseGap, TraceabilityLink

_log = logging.getLogger("compliance.absence_search")

_TERMS_PATH = Path(__file__).resolve().parent / "iso_clauses" / "search_terms.json"
_TERMS: Optional[Dict[str, Dict[str, List[str]]]] = None
_PASSAGE_CHARS = 700
_LEXICAL_K = 6
_SEMANTIC_K = 6
_MAX_PASSAGES = 10
_LABEL_RE = re.compile(r'^\[(PAGE \d+|SHEET "[^"]*"|IMAGE "[^"]*")')
_STOP = set("""
the and for with from that this not are has have was were been any all but such their there which into
only other also they does will shall must should can may per its our your are is of to in on by as at or an a
della delle degli dello dei del alla alle agli allo ai al nella nelle negli nello nei nel sulla sulle sui sul
per con che non sono come anche una uno gli le la il lo di da in su tra fra ed e o se
""".split())

_lock = threading.Lock()
_index_cache: Dict[int, "PackIndex"] = {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return s.lower()


def _stems(text: str) -> List[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", _norm(text)):
        if len(t) < 3 or t in _STOP:
            continue
        out.append(t[:6] if len(t) > 6 else t)     # radice grezza: registro/registrazioni, review/reviews
    return out


def _terms_for(req_id: str) -> List[str]:
    global _TERMS
    if _TERMS is None:
        try:
            _TERMS = json.loads(_TERMS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            _log.warning("[absence_search] termini non disponibili (%s): solo ricerca semantica", e)
            _TERMS = {}
    t = _TERMS.get(req_id) or {}
    return list(t.get("en", [])) + list(t.get("it", []))


class PackIndex:
    """Passaggi di ~700 caratteri di tutti i documenti, con l'etichetta di
    pagina/foglio/immagine in cui cadono e le radici per la ricerca a parole."""

    def __init__(self, docs_by_name: Dict[str, str]):
        self.passages: List[Tuple[str, str, str, set]] = []   # (doc, etichetta, testo, radici)
        for doc, text in docs_by_name.items():
            label: str = ""
            buf: List[str] = []
            for line in (text or "").splitlines():
                m = _LABEL_RE.match(line.strip())
                if m:
                    self._flush(doc, label, buf)
                    label, buf = m.group(1), []
                    continue
                buf.append(line)
                if sum(len(x) + 1 for x in buf) >= _PASSAGE_CHARS:
                    self._flush(doc, label, buf)
                    buf = buf[-1:]                      # una riga di sovrapposizione
            self._flush(doc, label, buf)
        df: Counter = Counter()
        for p in self.passages:
            df.update(p[3])
        n = max(1, len(self.passages))
        self.idf = {s: math.log(1 + n / c) for s, c in df.items()}
        self.n_docs = len(docs_by_name)

    def _flush(self, doc: str, label: str, buf: List[str]) -> None:
        text = "\n".join(buf).strip()
        if len(text) >= 20:
            self.passages.append((doc, label, text, set(_stems(text))))

    def lexical(self, terms: List[str], k: int = _LEXICAL_K) -> List[Tuple[str, str, str]]:
        phrases = [set(_stems(t)) for t in terms if _stems(t)]
        if not phrases:
            return []
        scored = []
        for doc, label, text, stems in self.passages:
            s = 0.0
            for ph in phrases:
                hit = ph & stems
                if hit:
                    w = sum(self.idf.get(x, 0.0) for x in hit)
                    s += w * (2.0 if hit == ph else len(hit) / len(ph))
            if s > 0:
                scored.append((s, doc, label, text))
        scored.sort(key=lambda x: -x[0])
        return [(d, l, t) for _, d, l, t in scored[:k]]


def _index_for(docs_by_name: Dict[str, str]) -> PackIndex:
    key = id(docs_by_name)
    with _lock:
        idx = _index_cache.get(key)
        if idx is None or idx.n_docs != len(docs_by_name):
            idx = PackIndex(docs_by_name)
            _index_cache.clear()          # un pacco alla volta: niente crescita di memoria
            _index_cache[key] = idx
        return idx


def _candidates(req: Dict[str, Any], idx: PackIndex, evidence_service) -> List[Tuple[str, str, str]]:
    terms = _terms_for(str(req.get("id", "")))
    cands = idx.lexical(terms)
    if evidence_service is not None:
        q = " ".join(x for x in (req.get("text"), req.get("verification_hint")) if x)
        try:
            for hit in evidence_service.get_evidences_similar_to(q, n=_SEMANTIC_K * 2):
                # Solo testo dei documenti: i riassunti delle schede li ha scritti
                # il modello e non possono fare da prova.
                if str(hit.get("chunk_kind", "content")) != "content":
                    continue
                excerpt = str(hit.get("excerpt") or "")[:_PASSAGE_CHARS]
                if excerpt:
                    pages = hit.get("pages") or []
                    cands.append((str(hit.get("file_name", "")), f"PAGE {pages[0]}" if pages else "", excerpt))
        except Exception as e:
            _log.debug("[absence_search] semantica non disponibile: %s", e)
    seen, out = set(), []
    for doc, label, text in cands:
        key = (doc.lower(), _norm(text)[:120])
        if key not in seen:
            seen.add(key)
            out.append((doc, label, text))
    return out[:_MAX_PASSAGES]


def _prompt(clause: Dict[str, Any], req: Dict[str, Any], cands: List[Tuple[str, str, str]]) -> str:
    rows = [f"[P{i}] {doc}{(' — ' + label) if label else ''}\n{text}" for i, (doc, label, text) in enumerate(cands, 1)]
    return (
        f"REQUIREMENT {req.get('id')} (clause {clause.get('title', '')}): {req.get('text', '')}\n"
        f"How it is usually verified: {req.get('verification_hint', '')}\n\n"
        "The passages below were found by searching the WHOLE document pack (documents may be in English "
        "or Italian). Decide whether any passage provides evidence that the requirement is met.\n"
        "- FOUND: a passage clearly demonstrates the requirement.\n"
        "- PARTIAL: a passage demonstrates part of it.\n"
        "- NOT_FOUND: no passage demonstrates it.\n"
        "Quote verbatim the words that demonstrate it (in the original language).\n\n"
        + "\n\n".join(rows) +
        '\n\nReturn JSON: {"status": "FOUND|PARTIAL|NOT_FOUND", "passage": "P<n>", "quote": "<verbatim>", '
        '"note": "<one sentence, UK English>"}'
    )


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def resolve_absences(gap: ClauseGap, clause: Dict[str, Any], docs_by_name: Dict[str, str],
                     evidence_service, llm_call: Callable, fname_to_eid: Dict[str, str]) -> ClauseGap:
    """Cerca nel pacco ogni requisito ABSENT della knowledge base e aggiorna il check."""
    from compliance.deep_verifier import _parse_json

    reqs = {str(r.get("id", "")): r for r in (clause.get("atomic_requirements") or [])}
    absent = [c for c in gap.requirement_checks if c.status == "ABSENT" and c.requirement_id in reqs]
    if not absent or not docs_by_name:
        return gap
    idx = _index_for(docs_by_name)
    for chk in absent:
        req = reqs[chk.requirement_id]
        cands = _candidates(req, idx, evidence_service)
        if not cands:
            chk.searched = True
            chk.search_note = (f"Searched all {idx.n_docs} documents in the pack: no passage relates to "
                               f"this requirement.")
            continue
        try:
            data = _parse_json(llm_call([{"role": "user", "content": _prompt(clause, req, cands)}], 600))
        except Exception as e:
            _log.warning("[absence_search] %s: ricerca fallita (%s) — resta da verificare",
                         chk.requirement_id, str(e)[:120])
            continue
        if not data:
            continue
        status = str(data.get("status", "")).upper()
        m = re.match(r"P(\d+)", str(data.get("passage", "")).strip().upper())
        quote = str(data.get("quote") or "")
        if status in ("FOUND", "PARTIAL") and m and 1 <= int(m.group(1)) <= len(cands):
            doc, label, text = cands[int(m.group(1)) - 1]
            q = _ws(quote).strip(" .\"'…")
            if len(q) >= 8 and (q in _ws(text) or q[:60] in _ws(text)):
                chk.status = "PRESENT" if status == "FOUND" else "PARTIAL"
                chk.evidence_quote = quote[:300]
                chk.file_name = doc
                chk.pages = [int(label.split()[1])] if label.startswith("PAGE ") else []
                chk.note = (str(data.get("note") or "")[:200] or None)
                chk.searched = True
                chk.search_note = "Found by searching the whole pack."
                key = re.sub(r"\s+", " ", doc.replace("\\", "/").rsplit("/", 1)[-1]).strip().lower()
                if not any(s.file_name == doc for s in gap.sources):
                    gap.sources.append(TraceabilityLink(
                        evidence_id=fname_to_eid.get(key, f"doc::{key}"), file_name=doc,
                        pages=chk.pages, excerpt=quote[:280], relevance_score=0.7, summary=None))
                continue
            _log.warning("[absence_search] %s: citazione non verificabile — resta da verificare",
                         chk.requirement_id)
            continue
        if status == "NOT_FOUND":
            terms = _terms_for(chk.requirement_id)[:6]
            chk.searched = True
            chk.search_note = (f"Searched all {idx.n_docs} documents in the pack ({len(cands)} candidate passages"
                               + (f"; terms: {', '.join(terms)}" if terms else "") + "): not found.")
    return gap



def _short(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").replace("\\", "/").rsplit("/", 1)[-1]).strip().lower()


def search_statement(subject: str, quote: str, exclude: str, docs_by_name: Dict[str, str],
                     evidence_service, llm_call: Callable) -> Optional[bool]:
    """Fase 4: l'organizzazione dichiara di tenere un record ("i verbali sono
    archiviati"): esiste, in un ALTRO documento del pacco? True trovato, False
    cercato e non trovato (prova), None non determinabile (resta da verificare)."""
    from compliance.deep_verifier import _parse_json
    if not docs_by_name:
        return None
    idx = _index_for(docs_by_name)
    ex = _short(exclude)
    terms = [subject] + re.findall(r"[A-Za-z]{4,}", subject)
    cands = [c for c in idx.lexical(terms, k=_LEXICAL_K + 4) if c[0] != ex]
    if evidence_service is not None:
        try:
            for hit in evidence_service.get_evidences_similar_to(subject, n=_SEMANTIC_K * 2):
                if str(hit.get("chunk_kind", "content")) != "content":
                    continue
                doc = _short(hit.get("file_name", ""))
                if doc != ex and hit.get("excerpt"):
                    cands.append((doc, "", str(hit["excerpt"])[:_PASSAGE_CHARS]))
        except Exception:
            pass
    seen, uniq = set(), []
    for doc, label, text in cands:
        key = (doc, _norm(text)[:120])
        if key not in seen:
            seen.add(key)
            uniq.append((doc, label, text))
    uniq = uniq[:_MAX_PASSAGES]
    if not uniq:
        return False
    rows = [f"[P{i}] {doc}" + (f" - {label}" if label else "") + "\n" + text
            for i, (doc, label, text) in enumerate(uniq, 1)]
    prompt = (
        f"The organisation states in its own document \"{_short(exclude)}\": \"{quote}\"\n"
        f"Record or document it refers to: {subject}\n\n"
        "The passages below come from OTHER documents of the same pack, found by searching the whole pack. "
        "Is the record/document itself present (an actual instance of it, not another mention of the rule)?\n"
        "- FOUND: a passage is (part of) that very record or document.\n"
        "- NOT_FOUND: none is. A different record of a similar kind does not count (management review minutes "
        "are not the minutes of a safety committee; a supplier's certificate is not a questionnaire).\n"
        "Quote verbatim the words that show it.\n\n" + "\n\n".join(rows)
        + '\n\nReturn JSON: {"status": "FOUND|NOT_FOUND", "passage": "P<n>", "quote": "<verbatim>"}'
    )
    try:
        data = _parse_json(llm_call([{"role": "user", "content": prompt}], 500)) or {}
    except Exception:
        return None
    status = str(data.get("status", "")).upper()
    if status == "NOT_FOUND":
        return False
    m = re.match(r"P(\d+)", str(data.get("passage", "")).strip().upper())
    if status == "FOUND" and m and 1 <= int(m.group(1)) <= len(uniq):
        text = uniq[int(m.group(1)) - 1][2]
        q = _ws(str(data.get("quote") or "")).strip(" .\"'…")
        if len(q) >= 6 and (q in _ws(text) or q[:50] in _ws(text)):
            return True
    return None
