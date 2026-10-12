"""
run_pack.py — banco di misura (Fase 0): esegue la pipeline END-TO-END su un
pacco ZIP una o più volte e salva ogni esecuzione in una cartella FUORI dal
repository. Non scrive sul DB: i pacchi del banco possono essere materiale di
terzi (es. il pacco Box del committente) e non devono finire né nel DB né nel
repo.

Uso:
  python tools/bench/run_pack.py <pacco.zip> --out C:/Users/user/amisys-bench/runs/synthetic \
      --company "Northwind Fabrication Ltd" --sector Manufacturing --employees 11-50 \
      --norms "ISO 9001:2015" "ISO 14001:2015" "ISO 45001:2018" --runs 2

Ogni esecuzione scrive in <out>/<timestamp>_r<n>/:
  result.json     ComplianceAnalysisResult completo
  evidence.yaml   schede (Phase 2)
  corpus.json.gz  testi estratti (Phase 1): il corpus NON va nel DB dell'app
  meta.json       contesto, durata, commit git, modelli e flag attivi
  progress.log    messaggi di avanzamento

  --reuse-corpus <corpus.json.gz> salta la Phase 1 (stesso testo, niente OCR):
  utile per misurare le fasi 2-4 isolando la variabilità dell'estrazione.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import time
from datetime import datetime

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BACKEND, ".env"))

from compliance import features  # noqa: E402
from compliance.pipeline import run_compliance_pipeline  # noqa: E402
from compliance.schemas import CompanyContext  # noqa: E402

# Variabili d'ambiente che descrivono la configurazione del motore. Solo nomi
# di deployment e manopole: mai chiavi o endpoint.
_ENV_TO_RECORD = (
    "COMPLIANCE_DEEP_PROVIDER", "AZURE_OPENAI_DEPLOYMENT",
    "EVIDENCE_MAX_WORKERS", "GAP_MAX_WORKERS", "DEEP_MAX_WORKERS",
    "CROSS_MAX_WORKERS", "RISK_MAX_WORKERS", "EXTRACT_MAX_WORKERS",
    "LLM_SEED", "LLM_REQUEST_TIMEOUT", "EVIDENCE_CARD_CACHE", "EVIDENCE_CARD_CACHE_DIR",
)


def _git_state() -> dict:
    def _run(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", _REPO, *args], capture_output=True,
                                  text=True, timeout=20).stdout.strip()
        except Exception:
            return ""
    return {
        "commit": _run("rev-parse", "HEAD"),
        "dirty_files": [l[3:] for l in _run("status", "--porcelain").splitlines()
                        if l[3:].startswith("backend/")],
    }


def _inside_repo(path: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), _REPO]) == _REPO
    except ValueError:  # dischi diversi su Windows
        return False


def _corpus_to(run_dir: str):
    """Sostituto di db_manager.save_analysis_corpus: il corpus finisce nella
    cartella dell'esecuzione invece che nel DB e in data/corpus/ dell'app."""
    def _save(analysis_id: str, documents: list) -> int:
        docs = [{"filename": d.get("filename"), "content": d.get("content")}
                for d in documents if str(d.get("content", "") or "").strip()]
        with gzip.open(os.path.join(run_dir, "corpus.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False)
        return len(docs)
    return _save


def _run_once(zip_bytes: bytes, ctx: CompanyContext, run_dir: str,
              corpus: list | None = None) -> dict:
    os.makedirs(run_dir, exist_ok=True)
    log = open(os.path.join(run_dir, "progress.log"), "w", encoding="utf-8")

    def emit(pct: float, msg: str) -> None:
        line = f"[{pct:5.1f}%] {msg}"
        print("  " + line, flush=True)
        log.write(line + "\n")
        log.flush()

    import modules.db_manager as _dbm
    _original_save = _dbm.save_analysis_corpus
    _dbm.save_analysis_corpus = _corpus_to(run_dir)
    t0 = time.monotonic()
    try:
        outcome = run_compliance_pipeline(None if corpus is not None else zip_bytes,
                                          ctx, emit, documents_override=corpus)
    finally:
        _dbm.save_analysis_corpus = _original_save
    elapsed = time.monotonic() - t0
    log.close()

    meta = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "success": bool(outcome.get("success")),
        "error": outcome.get("error"),
        "reused_corpus": corpus is not None,
        "features": features.active(),
        "context": ctx.model_dump(),
        "git": _git_state(),
        "env": {k: os.environ.get(k) for k in _ENV_TO_RECORD if os.environ.get(k)},
    }
    if outcome.get("success"):
        result = outcome["result"]
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=1)
        with open(os.path.join(run_dir, "evidence.yaml"), "w", encoding="utf-8") as f:
            f.write(outcome.get("evidence_yaml") or "")
        meta["analysis_id"] = result.analysis_id
        meta["documents_analyzed"] = result.documents_analyzed
    with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return meta


def main() -> int:
    # Console Windows (cp1252) + output rediretto: i messaggi della pipeline
    # contengono caratteri non latin-1.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("--out", required=True, help="cartella delle esecuzioni (fuori dal repo)")
    ap.add_argument("--company", required=True)
    ap.add_argument("--sector", default="n/a")
    ap.add_argument("--employees", default="n/a")
    ap.add_argument("--certified", default="no")
    ap.add_argument("--sites", default="1")
    ap.add_argument("--country", default=None, help="paese (JURISDICTION_FILTER), es. \"United Kingdom\"")
    ap.add_argument("--norms", nargs="+", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--reuse-corpus", help="corpus.json.gz di un'esecuzione precedente: salta la Phase 1")
    ap.add_argument("--card-cache", help="accende la cache delle schede (EVIDENCE_CARD_CACHE) in questa cartella")
    ap.add_argument("--allow-repo", action="store_true",
                    help="consente --out dentro il repository (sconsigliato)")
    args = ap.parse_args()

    if _inside_repo(args.out) and not args.allow_repo:
        print(f"RIFIUTATO: --out {args.out} è dentro il repository. I risultati del "
              "banco possono contenere materiale di terzi: usa una cartella esterna.")
        return 2

    if args.card_cache:
        if _inside_repo(args.card_cache) and not args.allow_repo:
            print(f"RIFIUTATO: --card-cache {args.card_cache} è dentro il repository.")
            return 2
        os.environ["EVIDENCE_CARD_CACHE"] = "1"
        os.environ["EVIDENCE_CARD_CACHE_DIR"] = args.card_cache

    with open(args.zip, "rb") as f:
        zip_bytes = f.read()
    corpus = None
    if args.reuse_corpus:
        with gzip.open(args.reuse_corpus, "rt", encoding="utf-8") as f:
            corpus = json.load(f)
    ctx = CompanyContext(company_name=args.company, sector=args.sector,
                         employee_range=args.employees, certified=args.certified,
                         sites_count=args.sites, norms=list(args.norms),
                         country=args.country)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    failures = 0
    for i in range(1, args.runs + 1):
        run_dir = os.path.join(args.out, f"{stamp}_r{i}")
        print(f"\n=== {args.company}: esecuzione {i}/{args.runs} → {run_dir}", flush=True)
        meta = _run_once(zip_bytes, ctx, run_dir, corpus)
        status = "OK" if meta["success"] else f"FALLITA: {meta['error']}"
        print(f"=== esecuzione {i}: {status} in {meta['elapsed_s']}s", flush=True)
        failures += 0 if meta["success"] else 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
