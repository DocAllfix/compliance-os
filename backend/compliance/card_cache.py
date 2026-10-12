"""
card_cache.py — schede di evidenza (Phase 2) salvate e riusate.

Piano motore, Fase 0. La stessa analisi sullo stesso pacco rigenerava ogni
volta le schede con il modello, ed è la prima fonte di variabilità tra due
esecuzioni: le schede guidano la ricerca, la fase 2.6 e la scelta dei documenti
dello Stage B (banco Box 2026-10-12: tra due esecuzioni identiche 9 clausole su
71 cambiano severità e 10 ENC cambiano verdetto).

Con la cache accesa un documento riusa la sua scheda quando la domanda al
modello sarebbe identica: stesso prompt di sistema (contesto aziendale
compreso), stesso deployment, stesso nome file, stesso testo campionato.
Cambia una qualsiasi di queste cose → nuova scheda.

Interruttore: EVIDENCE_CARD_CACHE=1 (spento di default).
Cartella:     EVIDENCE_CARD_CACHE_DIR (default backend/data/card_cache, fuori da git).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger("compliance.card_cache")

# Da incrementare quando cambia il formato delle schede o il modo di costruirle
# in modo non catturato dal prompt (es. post-processing): invalida la cache.
CARD_CACHE_VERSION = "1"

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "card_cache"
_DOC_MARKER_RE = re.compile(r"#\s*──\s*DOC\s*\d+\s*──")
_FILE_NAME_RE = re.compile(r'^\s*file_name:\s*"?(.*?)"?\s*$', re.M)


def enabled() -> bool:
    return os.environ.get("EVIDENCE_CARD_CACHE", "").strip().lower() in ("1", "true", "yes", "on")


def _dir() -> Path:
    return Path(os.environ.get("EVIDENCE_CARD_CACHE_DIR") or _DEFAULT_DIR)


def _basename(name: str) -> str:
    return str(name or "").replace("\\", "/").split("/")[-1].strip().lower()


def key_for(system_prompt: str, deployment: str, filename: str, sampled_text: str) -> str:
    h = hashlib.sha256()
    for part in (CARD_CACHE_VERSION, deployment or "", system_prompt or "",
                 _basename(filename), sampled_text or ""):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _path(key: str) -> Path:
    return _dir() / key[:2] / f"{key}.yaml"


def get(key: str) -> Optional[str]:
    p = _path(key)
    try:
        return p.read_text(encoding="utf-8") if p.exists() else None
    except OSError as e:
        _log.warning("[card_cache] lettura fallita %s: %s", p.name, e)
        return None


def put(key: str, card_yaml: str) -> None:
    p = _path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # tmp univoco: due documenti identici in batch diversi scrivono la stessa chiave
        tmp = p.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(card_yaml, encoding="utf-8")
        os.replace(tmp, p)   # atomico: niente schede troncate con i worker in parallelo
    except OSError as e:
        _log.warning("[card_cache] scrittura fallita %s: %s", p.name, e)


def split_cards(batch_yaml: str) -> List[str]:
    """Divide l'output di un batch in una stringa per scheda (dal marcatore DOC)."""
    marks = [m.start() for m in _DOC_MARKER_RE.finditer(batch_yaml or "")]
    return [batch_yaml[s:e].strip() + "\n"
            for s, e in zip(marks, marks[1:] + [len(batch_yaml)])]


def _is_cacheable(card: str) -> bool:
    """Solo schede vere e leggibili: mai le schede sintetiche di fallback né
    quelle che non passano il parser a valle."""
    if "ev_999_failed" in card or not _FILE_NAME_RE.search(card):
        return False
    try:
        from compliance.gap_analyzer import _parse_evidence_yaml
        cards = _parse_evidence_yaml(card)
    except Exception:
        return False
    return len(cards) == 1 and bool(cards[0].get("evidence_id")) and bool(cards[0].get("file_name"))


def store_batch(batch_docs: List[Dict[str, Any]], batch_yaml: str,
                key_of: Callable[[Dict[str, Any]], str]) -> int:
    """Salva le schede di un batch, abbinandole ai documenti per nome file.

    Un nome file presente due volte nello stesso batch è ambiguo: quelle schede
    non si salvano (meglio rigenerarle che attribuirle al documento sbagliato).
    Ritorna il numero di schede salvate.
    """
    by_bn: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for d in batch_docs:
        by_bn[_basename(d.get("filename", ""))].append(d)
    saved = 0
    for card in split_cards(batch_yaml):
        m = _FILE_NAME_RE.search(card)
        docs = by_bn.get(_basename(m.group(1))) if m else None
        if not docs or len(docs) != 1 or not _is_cacheable(card):
            continue
        put(key_of(docs[0]), card)
        saved += 1
    return saved
