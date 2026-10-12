"""
decompose_norm.py — Piano motore Fase 2, ricostruzione della knowledge base,
passo 1: scomposizione meccanica del testo ufficiale di una norma.

Ogni frase con "deve/devono" e ogni voce a), b), 1), 2)… che la completa
diventa una riga; dal testo esatto si leggono, senza modello:
  - forza: shall (deve) / should (dovrebbe) / may (può) / note (Nota);
  - verbi che cambiano il giudizio: considerare (si può escludere), tenere conto
    (non si può escludere), assicurare, per quanto appropriato, ove applicabile;
  - oggetto: registrazione da conservare / documento da mantenere o rendere
    disponibile / processo / altro.

Il testo della norma è protetto: input e output stanno FUORI dal repository
(C:/Users/user/amisys-bench/kb). Le righe della filigrana di licenza vengono
tolte per struttura (la riga "UNIstore …" e quella che la precede).

Uso:
  python tools/kb/decompose_norm.py <testo.txt> <norma: 9001|14001|45001> <uscita.json>
"""
from __future__ import annotations

import json
import re
import sys
from typing import Dict, List

_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\s+([A-Za-zÀ-ÿ'’].{2,140})$")
_ITEM = re.compile(r"^(?:([a-z])\)|(\d{1,2})\))\s+(.*)$")
_NOTE = re.compile(r"^Nota(?:\s+\d+)?\b\s*(.*)$")


def clean_lines(text: str) -> List[str]:
    lines = text.splitlines()
    drop = set()
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith("UNIstore"):
            drop.add(i)
            if i > 0 and lines[i - 1].strip().isupper() and len(lines[i - 1].strip()) < 60:
                drop.add(i - 1)                       # riga del licenziatario
        if s.startswith("[PAGE") or re.match(r"^UNI EN ISO .*Pagina", s) or s.startswith("© UNI"):
            drop.add(i)
    return [l.rstrip() for i, l in enumerate(lines) if i not in drop]


def normative_body(lines: List[str]) -> List[str]:
    starts = [i for i, l in enumerate(lines) if re.match(r"^4 CONTESTO", l.strip())]
    start = starts[-1] if starts else 0                # la seconda occorrenza: dopo l'indice
    end = next((i for i in range(start, len(lines)) if lines[i].strip().startswith("APPENDICE A")), len(lines))
    return lines[start:end]


def _attributes(text: str) -> Dict:
    t = text.lower()
    if re.search(r"\bdev(e|ono)\b", t):
        strength = "shall"
    elif re.search(r"\bdovrebb(e|ero)\b", t):
        strength = "should"
    elif re.search(r"\b(può|possono)\b", t):
        strength = "may"
    else:
        strength = "inherit"
    verbs = [v for v, rx in (("consider", r"\bconsiderar"), ("take_into_account", r"\btener(e)? conto"),
                             ("ensure", r"\bassicur"), ("as_appropriate", r"per quanto appropriat|ove appropriat"),
                             ("where_applicable", r"ove applicabil|per quanto applicabil"))
             if re.search(rx, t)]
    if re.search(r"conserv\w*\s+(appropriate\s+)?(le\s+)?informazion\w*\s+documentat", t):
        obj = "record"
    elif re.search(r"(mantenut\w*|mantener\w*).{0,40}informazion\w*\s+documentat|disponibil\w*\s+come\s+informazion", t):
        obj = "document"
    elif re.search(r"\bprocess", t):
        obj = "process"
    else:
        obj = "other"
    return {"strength": strength, "verbs": verbs, "object": obj}


def decompose(text: str, norm: str) -> List[Dict]:
    body = normative_body(clean_lines(text))
    rows: List[Dict] = []
    clause, title = "", ""
    para: List[str] = []
    stem = ""

    def flush_para():
        nonlocal para, stem
        if not para:
            return
        txt = re.sub(r"\s+", " ", " ".join(para)).strip()
        para = []
        if not txt:
            return
        m_note = _NOTE.match(txt)
        if m_note:
            rows.append({"kind": "note", "text": txt})
            return
        m_item = _ITEM.match(txt)
        if m_item and stem:
            rows.append({"kind": "item", "label": m_item.group(1) or m_item.group(2), "stem": stem,
                         "text": m_item.group(3)})
            return
        for sent in re.split(r"(?<=[.;])\s+(?=[A-ZÀ-Ý])", txt):
            if sent.rstrip().endswith(":"):
                stem = sent.strip()
                rows.append({"kind": "stem", "text": stem})
            else:
                stem = ""
                rows.append({"kind": "sentence", "text": sent.strip()})

    out: List[Dict] = []
    # Il testo estratto dal PDF alterna righe vuote: non segnano fine paragrafo.
    for raw in [l for l in body if l.strip()] + [""]:
        line = raw.strip()
        h = _HEADING.match(line)
        if h and not re.search(r"\.{4,}", line) and not _ITEM.match(line):
            flush_para()
            for r in rows:
                out.append({"norm": norm, "clause": clause, "clause_title": title, **r})
            rows = []
            clause, title, stem = h.group(1), h.group(2).strip(), ""
            continue
        starts_new = bool(_ITEM.match(line) or _NOTE.match(line) or line.startswith("- "))
        if not line or starts_new:
            flush_para()
        if line:
            para.append(line[2:] if line.startswith("- ") else line)
            if line.endswith((".", ";", ":")) and not starts_new:
                flush_para()
    flush_para()
    for r in rows:
        out.append({"norm": norm, "clause": clause, "clause_title": title, **r})

    # attributi; le voci ereditano la forza dalla frase che le introduce
    reqs = []
    n = 0
    for r in out:
        if r["kind"] == "stem":
            continue
        full = (r.get("stem", "") + " " + r["text"]).strip() if r["kind"] == "item" else r["text"]
        a = _attributes(full)
        if r["kind"] == "note":
            a["strength"] = "note"
        if a["strength"] == "inherit":
            continue                                   # frase descrittiva senza forza normativa
        n += 1
        reqs.append({"row_id": f"{norm}-{r['clause']}-{n:03d}", "norm": norm, "clause": r["clause"],
                     "clause_title": r["clause_title"], "kind": r["kind"], "label": r.get("label"),
                     "text": full, **a})
    return reqs


def main() -> int:
    src, norm, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(src, encoding="utf-8") as f:
        rows = decompose(f.read(), norm)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    from collections import Counter
    print(f"{norm}: {len(rows)} righe", dict(Counter(r["strength"] for r in rows)),
          dict(Counter(r["object"] for r in rows if r["strength"] == "shall")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
