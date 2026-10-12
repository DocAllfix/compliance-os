"""
score.py — banco di misura (Fase 0): misura una o più esecuzioni contro la
chiave di un pacco.

Tre metri:
  1. ENC trovate per classe (A-E) — non conformità ingegnerizzate note;
  2. accuse vietate — affermazioni che la chiave sa essere false;
  3. severità — distribuzione, % clausole conformi, NC fondate su un'assenza,
     azioni "istituisci" su clausole conformi, termini legali italiani,
     NC senza nessuna ENC dietro.
Con più esecuzioni misura anche la variabilità (stessa severità per clausola).

L'abbinamento rilievo↔ENC e la ricerca delle accuse vietate li fa un giudice
LLM (profilo deep, temperature 0, cache su disco). Il giudice va TARATO prima
dell'uso: sull'export della demo deve riprodurre le etichette del committente
(colonna fred_scan della chiave) — vedi la sezione "taratura" nell'output.

Uso:
  python tools/bench/score.py --key <key.json> --out <cartella_punteggi> <esecuzione> [<esecuzione> ...]
  (<esecuzione> = cartella di run_pack.py, result.json, oppure export DOCX dei rilievi)

La chiave e i punteggi restano FUORI dal repository: contengono materiale del
committente.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _HERE)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND, ".env"))

from findings import load_run  # noqa: E402

NC = ("MAJOR", "MINOR")
OK = ("OBSERVATION", "CONFORMANT")

_ABSENCE = re.compile(
    r"\b(no (?:\w+ ){0,2}(?:evidence|record|records|documentation|procedure|process|register)|"
    r"not (?:found|evidenced|documented|identified|provided|defined|available)|"
    r"lack(?:s|ing)?|absent|absence|missing|there is no|does not (?:exist|include|cover))\b", re.I)
_ESTABLISH = re.compile(
    r"^\s*(establish|implement|define|develop|introduce|create|set up|document|formali[sz]e|"
    r"assign|appoint|publish|prepare|adopt|issue|draft)\b", re.I)
_ITALIAN = re.compile(r"\b(RSPP|DUVRI|DVR|RLS|D\.\s?Lgs|81/0?8|FIR|MUD|INAIL|preposto|datore di lavoro)\b")


# ── giudice LLM ──────────────────────────────────────────────────────────────

class Judge:
    SYSTEM = ("You grade an automated ISO management-system gap report against a reference "
              "key prepared by an experienced auditor. Be strict and literal. Never give credit "
              "for generic statements. Answer only with the requested JSON.")

    def __init__(self, cache_path: str):
        from v2.azure_openai_client_v2 import make_client
        self.client = make_client(deep=True)
        self.cache_path = cache_path
        self.cache: Dict[str, Any] = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                self.cache = json.load(f)
        self.lock = threading.Lock()

    def ask(self, prompt: str) -> Dict[str, Any]:
        k = hashlib.sha256((self.client.deployment + "\n" + prompt).encode("utf-8")).hexdigest()
        with self.lock:
            if k in self.cache:
                return self.cache[k]
        last: Optional[Exception] = None
        for _ in range(4):
            try:
                r = self.client._sdk.chat.completions.create(
                    model=self.client.deployment, temperature=0.0, seed=42, max_tokens=2500,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": self.SYSTEM},
                              {"role": "user", "content": prompt}])
                out = json.loads(r.choices[0].message.content or "{}")
                with self.lock:
                    self.cache[k] = out
                return out
            except Exception as e:  # retry: 429, timeout, JSON malformato
                last = e
        # Non bloccante: la voce risulta non giudicata (non entra nei conteggi).
        print(f"  [giudice] domanda non giudicata: {str(last)[:160]}", flush=True)
        return {"judge_error": str(last)[:300]}

    def save(self) -> None:
        with self.lock, open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False)


# ── preselezione dei candidati ───────────────────────────────────────────────
# Taratura 2026-10-12: con tutto il report in un solo prompt (~100k caratteri) il
# giudice saltava rilievi presenti (es. "some records lack complete trainer
# details" per ENC004). Ogni domanda vede quindi solo i rilievi pertinenti per
# clausola, documenti citati o identificativi; e deve CITARE: una citazione che
# non si ritrova nel testo del rilievo viene scartata (cite-or-fail anche per
# il giudice). Il verdetto lo aggrega Python dalle citazioni.

_STOP = {"the", "and", "for", "with", "from", "that", "this", "not", "are", "has", "have",
         "was", "were", "been", "any", "all", "but", "despite", "being", "their", "there",
         "which", "into", "only", "other", "also", "such", "they", "does", "will", "shall",
         "record", "records", "document", "documents", "documented", "procedure", "folder"}


def _tokens(text: str) -> set:
    toks = set()
    for t in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}|\d[\w./-]*\d", text or ""):
        t = t.lower().strip("'")
        if t not in _STOP:
            toks.add(t)
    return toks


def _distinctive(text: str) -> set:
    """Identificativi e nomi propri: codici con cifre, parole maiuscole non a inizio frase."""
    ids = {t.lower() for t in re.findall(r"\b[A-Za-z]*\d[\w-]*\b", text or "") if len(t) >= 3}
    names = {t.lower() for t in re.findall(r"(?<=[a-z,;] )[A-Z][a-z]{2,}", text or "")}
    return (ids | names) - _STOP


def _clause_match(clause: str, hint: str) -> bool:
    return clause == hint or clause.startswith(hint + ".") or hint.startswith(clause + ".")


def _ref_in_scope(f: Dict[str, Any], scope: List[str]) -> bool:
    if not scope:
        return True
    for s in scope:
        norm, _, cl = s.partition("§")
        norm = norm.strip()
        if (not norm or norm == f["norm"]) and (f["clause"] == cl or f["clause"].startswith(cl + ".")):
            return True
    return False


def _f_text(f: Dict[str, Any]) -> str:
    return " ".join([f["finding"], f["action"] or "", " ".join(os.path.basename(e) for e in f["evidence"])])


def _enc_candidates(enc: Dict[str, Any], findings: List[Dict[str, Any]], extra_lines: List[str],
                    cap: int = 18) -> tuple:
    ident = _distinctive(enc["description"] + " " + enc["documents"])
    docs = _tokens(enc["documents"])
    scored = []
    for f in findings:
        ft = _f_text(f)
        s = 0
        if any(_clause_match(f["clause"], h) for h in enc.get("clauses", [])):
            s += 2
        s += 3 * len(ident & _distinctive(ft)) + len(docs & _tokens(" ".join(f["evidence"])))
        if s:
            scored.append((s, f))
    scored.sort(key=lambda x: -x[0])
    lines = [l for l in extra_lines if len(ident & _distinctive(l)) or len(docs & _tokens(l)) >= 2]
    return [f for _, f in scored[:cap]], lines[:12]


def _render_candidates(findings: List[Dict[str, Any]], lines: List[str]) -> str:
    rows = [f"[{f['ref']}] {f['severity']} | Finding: {f['finding']} | Action: {(f['action'] or '')[:400]} | "
            f"Evidence: {'; '.join(os.path.basename(e) for e in f['evidence'][:6])}" for f in findings]
    for i, l in enumerate(lines, 1):
        rows.append(f"[section-{i}] {l[:900]}")
    return "\n".join(rows) if rows else "(no candidate passages)"


def _clean_ref(ref: Any) -> str:
    """Il giudice a volte decora il riferimento ("[14001 §4.4] MINOR")."""
    m = re.search(r"(\d{4,5} §[\d.]+|section-\d+)", str(ref or ""))
    return m.group(1) if m else str(ref or "").strip("[] ")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _quote_ok(quote: str, source: str) -> bool:
    q = _norm_ws(quote).strip(" .\"'…")
    if len(q) < 8:
        return False
    src = _norm_ws(source)
    return q in src or q[:60] in src


def _enc_prompt(enc: Dict[str, Any], rendered: str) -> str:
    return (
        f"PLANTED NONCONFORMITY {enc['id']}: {enc['description']}\n"
        f"Related documents: {enc['documents']}\n\n"
        f"CANDIDATE PASSAGES FROM THE REPORT:\n{rendered}\n\n"
        "For each passage that relates to this planted nonconformity, quote verbatim the words that "
        "relate to it and classify the relation, as an auditor reading the report would:\n"
        "- \"same_defect\": the passage reports this defect, even if worded differently, without the exact "
        "record ID, or under a different clause. When the planted nonconformity concerns a specific person, "
        "record, certificate, supplier, document or value, the passage must refer to that same item (by name, "
        "ID or by citing the same file) or state a deficiency that unambiguously covers it. A similar problem "
        "about a different item is NOT the same defect.\n"
        "- \"partly\": the passage refers to the same specific item or document with a related deficiency but "
        "misses the key point, or states the same deficiency in general terms that clearly include this case.\n"
        "Leave out passages about a different item or a different deficiency, and generic remarks on the topic "
        "that would apply to any organisation.\n"
        'Return JSON: {"matches": [{"ref": "<ref>", "quote": "<verbatim words>", '
        '"relation": "same_defect|partly"}], "why": "<one sentence>"}'
    )


def _forbidden_prompt(item: Dict[str, Any], rendered: str) -> str:
    if item["kind"] == "incoherent_action":
        how = ("Report a finding when its Finding text acknowledges that an element exists, is documented, "
               "defined or demonstrated, AND its Action nevertheless asks to establish, define, document, "
               "implement or create that same element (rather than maintain, review or improve it). "
               "Quote both parts.")
        fmt = ('{"hits": [{"ref": "<ref>", "quote": "<verbatim words from the Finding>", '
               '"action_quote": "<verbatim words from the Action>"}], "why": "<one sentence>"}')
    else:
        how = ("Report a finding when it asserts or implies the claim - including hedged wording such as "
               "'not clearly evidenced', 'no dedicated register', 'lacks', 'not explicitly documented', "
               "'no evidence of' - or when its Action presupposes the claim (e.g. asks to create or document "
               "the element). Do not report a finding that only says the element exists but could be improved. "
               "Quote the words that make the claim.")
        fmt = '{"hits": [{"ref": "<ref>", "quote": "<verbatim words>"}], "why": "<one sentence>"}'
    return (
        f"INAPPROPRIATE CLAIM {item['id']} ({item['kind']}): {item['claim']}\n"
        f"Ground truth: {item['truth']}\n\n"
        f"FINDINGS:\n{rendered}\n\n"
        f"Go through the findings one by one. {how}\n"
        f"Return JSON: {fmt}"
    )


# ── metriche ─────────────────────────────────────────────────────────────────

def _severity_metrics(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_norm: Dict[str, Counter] = {}
    for f in findings:
        per_norm.setdefault(f["norm"], Counter())[f["severity"]] += 1
    tot = Counter(f["severity"] for f in findings)
    nc = [f for f in findings if f["severity"] in NC]
    return {
        "clauses": len(findings),
        "by_severity": dict(tot),
        "by_norm": {n: dict(c) for n, c in sorted(per_norm.items())},
        "pct_conformant": round(100 * tot["CONFORMANT"] / max(1, len(findings)), 1),
        "nc": len(nc), "major": tot["MAJOR"],
        "nc_on_absence": sum(1 for f in nc if _ABSENCE.search(f["finding"])),
        "establish_on_ok": [f["ref"] for f in findings
                            if f["severity"] in OK and _ESTABLISH.search(f["action"] or "")],
        "italian_terms": [f["ref"] for f in findings
                          if _ITALIAN.search(f["finding"] + " " + (f["action"] or ""))],
    }


def _judge_enc(enc, findings, extra_lines, judge) -> Dict[str, Any]:
    cands, lines = _enc_candidates(enc, findings, extra_lines)
    by_ref = {f["ref"]: f for f in cands}
    sec = {f"section-{i}": l for i, l in enumerate(lines, 1)}
    if not cands and not lines:
        return {"verdict": "missed", "refs": [], "matches": [], "why": "nessun candidato"}
    o = judge.ask(_enc_prompt(enc, _render_candidates(cands, lines)))
    # Ancoraggio delle parziali: senza, il giudice dava "partly" a passaggi
    # generici sullo stesso tema (taratura: 11 ENC che l'auditor dà per mancate).
    # Una parziale conta solo se il passaggio nomina lo stesso oggetto della ENC.
    anchors = {t for t in _distinctive(enc["description"] + " " + enc["documents"])
               if not re.fullmatch(r"v\d+|\d{1,3}", t)}
    kept = []
    for m in o.get("matches") or []:
        ref = _clean_ref(m.get("ref"))
        src = _f_text(by_ref[ref]) if ref in by_ref else sec.get(ref, "")
        if not (src and _quote_ok(m.get("quote", ""), src) and m.get("relation") in ("same_defect", "partly")):
            continue
        if m.get("relation") == "partly":
            ev = " ".join(by_ref[ref]["evidence"]) if ref in by_ref else ""
            if not (anchors & _distinctive(m.get("quote", "") + " " + ev)):
                continue
        kept.append({"ref": ref, "quote": m.get("quote"), "relation": m.get("relation")})
    rel = {m["relation"] for m in kept}
    verdict = "identified" if "same_defect" in rel else "partial" if "partly" in rel else "missed"
    return {"verdict": verdict, "refs": sorted({m["ref"] for m in kept if m["ref"] in by_ref}),
            "matches": kept, "why": o.get("why", "")}


def _judge_forbidden(item, findings, judge) -> Dict[str, Any]:
    pool = [f for f in findings if _ref_in_scope(f, item.get("scope") or [])]
    hits: Dict[str, Dict[str, Any]] = {}
    whys = []
    for i in range(0, len(pool), 20):           # lotti piccoli: lettura attenta
        chunk = pool[i:i + 20]
        by_ref = {f["ref"]: f for f in chunk}
        o = judge.ask(_forbidden_prompt(item, _render_candidates(chunk, [])))
        whys.append(o.get("why", ""))
        for h in o.get("hits") or []:
            f = by_ref.get(_clean_ref(h.get("ref")))
            if not f:
                continue
            ok = _quote_ok(h.get("quote", ""), _f_text(f))
            if item["kind"] == "incoherent_action":
                ok = ok and _quote_ok(h.get("action_quote", ""), f["action"] or "")
            if ok:
                hits[f["ref"]] = {"ref": f["ref"], "quote": h.get("quote")}
    return {"count": len(hits), "refs": sorted(hits), "hits": list(hits.values()),
            "why": " / ".join(w for w in whys if w)[:600]}


def _own_records_precision(run, key, judge, workers) -> Dict[str, Any]:
    """Fasi 4-5: quante contestazioni "incoerente / registrazione mancante" corrispondono
    a un difetto noto della chiave. Su un pacco sintetico (chiave completa) quelle che non
    corrispondono sono accuse false; su un pacco reale la chiave può non essere esaustiva."""
    checks = [c for c in run.get("self_checks") or [] if c.get("status") in ("INCONSISTENT", "MISSING")]
    if not checks or judge is None or not key.get("encs"):
        return {"total": len(checks), "matched": None, "unmatched": []}
    extra = list(key.get("true_unplanted") or [])       # difetti veri del pacco, non piantati apposta
    encs = "\n".join(f"- {e['id']}: {e['description']}" for e in key["encs"] + extra)

    def one(c):
        o = judge.ask(
            "KNOWN PLANTED NONCONFORMITIES:\n" + encs + "\n\nFINDING OF THE REPORT: " + str(c.get("description"))
            + "\n\nDoes the finding report one of the known nonconformities (same object and same defect, or a "
            "finding that includes it, e.g. a list of missing records that contains it)?\n"
            'Return JSON: {"enc": "<id or null>"}')
        return str(o.get("enc") or "").strip() or None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        matched = list(ex.map(one, checks))
    judge.save()
    ids = {e["id"] for e in key["encs"]}
    true_ids = {e["id"] for e in extra}
    ok = [m for m in matched if m in ids]
    return {"total": len(checks), "matched": len(ok), "enc_ids": sorted(set(ok)),
            "true_unplanted": sum(1 for m in matched if m in true_ids),
            "unmatched": [c["description"][:200] for c, m in zip(checks, matched) if m not in ids | true_ids]}


def score_run(run: Dict[str, Any], key: Dict[str, Any], judge: Judge,
              workers: int = 6) -> Dict[str, Any]:
    findings = run["findings"]
    extra_lines = [l for l in (run.get("extra") or "").split("\n") if len(l.strip()) > 20]

    def _forb(i):
        if i.get("names"):   # F01: controllo deterministico sui ruoli chiave
            roles = run.get("key_roles")
            if roles is None:
                return {"count": None, "refs": [], "hits": [], "why": "ruoli chiave non disponibili in questa sorgente"}
            hit = [r for r in roles if any(n.lower() in r.lower() for n in i["names"])]
            return {"count": len(hit), "refs": hit, "hits": [], "why": "persone dei fornitori tra i ruoli chiave"}
        return _judge_forbidden(i, findings, judge)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        enc_out = list(ex.map(lambda e: _judge_enc(e, findings, extra_lines, judge), key["encs"]))
        forb_out = list(ex.map(_forb, key["forbidden"]))
    if judge is not None:
        judge.save()

    encs = [{"id": e["id"], "class": e["class"], "fred_scan": e.get("fred_scan"), **o}
            for e, o in zip(key["encs"], enc_out)]
    by_class = {}
    for c in "ABCDE":
        cs = [x for x in encs if x["class"] == c]
        if cs:
            by_class[c] = {"n": len(cs),
                           "identified": sum(x["verdict"] == "identified" for x in cs),
                           "partial": sum(x["verdict"] == "partial" for x in cs)}
    forbidden = [{"id": i["id"], "kind": i["kind"], "expected_findings": i.get("expected_findings"), **o}
                 for i, o in zip(key["forbidden"], forb_out)]

    sev = _severity_metrics(findings)
    enc_refs = {r for x in encs if x["verdict"] != "missed" for r in x["refs"]}
    sev["nc_without_enc"] = sorted(f["ref"] for f in findings
                                   if f["severity"] in NC and f["ref"] not in enc_refs)
    # ENC trovate E portate come non conformità: un motore più morbido non deve
    # declassare le non conformità vere (es. una contraddizione provata).
    sev_by_ref = {f["ref"]: f["severity"] for f in findings}
    enc_as_nc = sum(1 for x in encs if x["verdict"] == "identified"
                    and any(sev_by_ref.get(r) in NC for r in x["refs"]))
    return {
        "label": run["label"],
        "enc": {"identified": sum(x["verdict"] == "identified" for x in encs),
                "identified_as_nc": enc_as_nc,
                "partial": sum(x["verdict"] == "partial" for x in encs),
                "n": len(encs), "by_class": by_class, "items": encs},
        "forbidden": {"total": sum(x["count"] or 0 for x in forbidden), "items": forbidden},
        "severity": sev,
        "own_records": _own_records_precision(run, key, judge, workers),
    }


def _calibration(score: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Confronto giudice ↔ etichette del committente (solo se la chiave le ha)."""
    items = [x for x in score["enc"]["items"] if x.get("fred_scan")]
    if not items:
        return None

    def fred(lbl: str) -> str:
        return {"Identified": "identified", "Partial": "partial"}.get(lbl, "missed")
    pairs = Counter((fred(x["fred_scan"]), x["verdict"]) for x in items)
    agree = sum(n for (a, b), n in pairs.items() if a == b)
    # misura principale del banco: "trovata sì/no" (le parziali sono più rumorose)
    binary = sum(1 for x in items if (fred(x["fred_scan"]) == "identified") == (x["verdict"] == "identified"))
    return {"agreement": f"{agree}/{len(items)}", "agreement_identified": f"{binary}/{len(items)}",
            "confusion": {f"fred={a} judge={b}": n for (a, b), n in sorted(pairs.items())},
            "disagreements": [{"id": x["id"], "fred": x["fred_scan"], "judge": x["verdict"], "why": x["why"]}
                              for x in items if fred(x["fred_scan"]) != x["verdict"]]}


def _variance(scores: List[Dict[str, Any]], runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            a = {f["ref"]: f for f in runs[i]["findings"]}
            b = {f["ref"]: f for f in runs[j]["findings"]}
            common = sorted(set(a) & set(b))
            same = sum(a[r]["severity"] == b[r]["severity"] for r in common)
            dscore = [abs((a[r]["score"] or 0) - (b[r]["score"] or 0)) for r in common]
            ea = {x["id"]: x["verdict"] for x in scores[i]["enc"]["items"]}
            eb = {x["id"]: x["verdict"] for x in scores[j]["enc"]["items"]}
            out.append({
                "pair": [runs[i]["label"], runs[j]["label"]],
                "same_severity": f"{same}/{len(common)}",
                "mean_abs_score_diff": round(sum(dscore) / max(1, len(dscore)), 1),
                "severity_flips": [f"{r}: {a[r]['severity']}→{b[r]['severity']}" for r in common
                                   if a[r]["severity"] != b[r]["severity"]],
                "enc_verdict_changes": [f"{k}: {ea[k]}→{eb[k]}" for k in ea if ea[k] != eb.get(k)],
            })
    return {"pairs": out}


def _print_summary(scores: List[Dict[str, Any]]) -> None:
    for s in scores:
        e, sv, fb = s["enc"], s["severity"], s["forbidden"]
        print(f"\n### {s['label']}")
        if e["n"]:
            cls = "  ".join(f"{c}:{v['identified']}+{v['partial']}p/{v['n']}" for c, v in e["by_class"].items())
            print(f"ENC trovate {e['identified']} (come NC {e.get('identified_as_nc', '?')}) + "
                  f"{e['partial']} parziali su {e['n']}   [{cls}]")
        if fb["items"]:
            print(f"Accuse vietate: {fb['total']}   " +
                  "  ".join(f"{x['id']}={x['count'] if x['count'] is not None else 'n/a'}/{x.get('expected_findings')}"
                            for x in fb["items"]))
        bs = sv["by_severity"]
        print(f"Severità: MAJOR {bs.get('MAJOR', 0)}  MINOR {bs.get('MINOR', 0)}  OBS {bs.get('OBSERVATION', 0)}  "
              f"CONF {bs.get('CONFORMANT', 0)}  (conformi {sv['pct_conformant']}%)")
        print(f"NC {sv['nc']}: su assenza {sv['nc_on_absence']}, senza ENC dietro {len(sv['nc_without_enc'])}; "
              f"'istituisci' su clausole OK {len(sv['establish_on_ok'])}; termini legali IT {len(sv['italian_terms'])}")
        o = s.get("own_records") or {}
        if o.get("total"):
            print(f"Confronto con le proprie registrazioni: {o['total']} contestazioni, {o.get('matched')} corrispondono "
                  f"a ENC note ({len(o.get('enc_ids') or [])} ENC distinte), {o.get('true_unplanted', 0)} vere ma non "
                  f"piantate, {len(o.get('unmatched') or [])} senza difetto noto dietro")
        if s.get("calibration"):
            c = s["calibration"]
            print(f"Taratura giudice vs etichette del committente: trovata sì/no {c['agreement_identified']}, tre livelli {c['agreement']}  {c['confusion']}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--key", help="chiave del pacco; senza chiave solo severità e variabilità (niente giudice)")
    ap.add_argument("--out", required=True, help="cartella dei punteggi (fuori dal repo)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--extra-docx", help="report DOCX completo da affiancare a un export DOCX dei rilievi")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    if args.key:
        with open(args.key, encoding="utf-8") as f:
            key = json.load(f)
        judge = Judge(os.path.join(os.path.dirname(os.path.abspath(args.key)), "judge_cache.json"))
    else:
        key, judge = {"encs": [], "forbidden": []}, None

    runs = [load_run(p, args.extra_docx if p.lower().endswith(".docx") else None) for p in args.runs]
    scores = []
    for run in runs:
        s = score_run(run, key, judge, args.workers)
        if run["label"].lower().endswith(".docx"):
            s["calibration"] = _calibration(s)
        scores.append(s)
        with open(os.path.join(args.out, f"score_{re.sub(r'[^A-Za-z0-9_.-]', '_', run['label'])}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
    _print_summary(scores)
    if len(runs) > 1:
        var = _variance(scores, runs)
        with open(os.path.join(args.out, "variance.json"), "w", encoding="utf-8") as f:
            json.dump(var, f, ensure_ascii=False, indent=1)
        for p in var["pairs"]:
            print(f"\nVariabilità {p['pair'][0]} ↔ {p['pair'][1]}: stessa severità {p['same_severity']}, "
                  f"|Δscore| medio {p['mean_abs_score_diff']}, ENC cambiate {len(p['enc_verdict_changes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
