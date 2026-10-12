"""
sampling.py — campionamento dei documenti lunghi (Piano motore, Fase 1).

Il campionamento storico prende testa (60%) e coda (40%): in una cartella di
lavoro Excel i fogli centrali spariscono (banco Box: il foglio "Interested
Parties" del registro di contesto non arrivava mai alla scheda, e il motore
dichiarava assenti le parti interessate in tutte e tre le norme).

Con READ_SHEET_SAMPLING lo spazio si distribuisce sui fogli: i fogli piccoli
entrano interi, il resto si divide in parti uguali fra i grandi, tagliando a
righe intere e dichiarando quante righe mancano. Per la scheda, una cartella
con più fogli porta in testa l'elenco dei fogli e la richiesta di descriverli
tutti (sta nel testo del documento, quindi entra anche nella chiave della cache
delle schede).
"""
from __future__ import annotations

import re
from typing import List, Optional

from compliance import features

_SHEET_RE = re.compile(r'(?m)^\[SHEET "([^"\n]*)"\][ \t]*$')


def sheet_names(text: str) -> List[str]:
    return [m.group(1) for m in _SHEET_RE.finditer(text or "")]


def head_tail(text: str, cap: int, note: str = "[… omitted middle section …]") -> str:
    text = text or ""
    if len(text) <= cap:
        return text
    head = int(cap * 0.6)
    tail = cap - head
    return text[:head].rstrip() + f"\n\n{note}\n\n" + text[-tail:].lstrip()


def sample_by_sheet(text: str, cap: int) -> Optional[str]:
    """Distribuisce `cap` caratteri sui fogli. None se i fogli sono meno di due."""
    marks = [m.start() for m in _SHEET_RE.finditer(text or "")]
    if len(marks) < 2:
        return None
    pre = text[:marks[0]]
    segs = [text[s:e] for s, e in zip(marks, marks[1:] + [len(text)])]
    budget = max(0, cap - len(pre) - 70 * len(segs))
    alloc = [0] * len(segs)
    order = sorted(range(len(segs)), key=lambda i: len(segs[i]))
    remaining = budget
    for k, i in enumerate(order):                     # riempimento ad acqua
        share = remaining // (len(order) - k)
        alloc[i] = min(len(segs[i]), share)
        remaining -= alloc[i]
    out = [pre]
    for seg, take in zip(segs, alloc):
        if take >= len(seg):
            out.append(seg)
            continue
        cut = seg[:take]
        if "\n" in cut:
            cut = cut[:cut.rfind("\n")]               # solo righe intere
        omitted = seg[len(cut):].strip("\n").count("\n") + 1
        out.append(cut.rstrip("\n") + f"\n[… {omitted} more lines of this sheet omitted …]\n\n")
    return "".join(out)


def for_card(content: str, cap: int) -> str:
    """Testo del documento come lo vede la Phase 2 (scheda)."""
    content = content or ""
    if features.on("READ_SHEET_SAMPLING"):
        names = sheet_names(content)
        if len(names) >= 2:
            note = (f"[WORKBOOK with {len(names)} sheets: {'; '.join(names)}. Describe every sheet in the "
                    "summary and include in iso_clauses_secondary the clauses each sheet supports.]\n")
            body = content if len(content) <= cap else (sample_by_sheet(content, cap - len(note)) or content)
            return note + body
    return head_tail(content, cap)


def for_deep(content: str, cap: int) -> str:
    """Testo del documento come lo vede lo Stage B."""
    content = content or ""
    if len(content) > cap and features.on("READ_SHEET_SAMPLING"):
        s = sample_by_sheet(content, cap)
        if s is not None:
            return s
    return head_tail(content, cap, "[… omitted middle section — head and tail shown …]")
