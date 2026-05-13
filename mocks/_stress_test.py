"""
Stress test for the ComplianceOS pipeline.

Builds 3 synthetic ZIPs (50, 100, 200 documents) by duplicating the PDFs
from the CONSORZIO JEOCON 14001.zip with progressively new filenames,
then runs the full pipeline on each, measuring per-phase timings, token
spend, peak RAM, and number of LLM calls.

Output is written to mocks/_stress_results.json so we can compare runs
across sprints.

Run with:
    "C:/Users/user/AppData/Local/Programs/Python/Python312/python.exe" \\
        "c:/Users/user/COMPLIANCE-OS/mocks/_stress_test.py"

Optional env:
    STRESS_SIZES      comma-separated, default "50,100,200"
    CONSORZIO_ZIP_PATH path to the source ZIP (default in code)
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import tracemalloc
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, r"C:\Users\user\COMPLIANCE-OS\backend")
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"C:\Users\user\COMPLIANCE-OS\backend\.env")

from compliance.pipeline import run_compliance_pipeline  # noqa: E402
from compliance.schemas import CompanyContext             # noqa: E402

SRC_ZIP = Path(os.environ.get(
    "CONSORZIO_ZIP_PATH",
    r"C:\Users\user\Desktop\ANTIGRAVITY\ISO14001\CONSORZIO JEOCON 14001.zip",
))
SIZES = [int(s) for s in os.environ.get("STRESS_SIZES", "50,100,200").split(",")]
OUTPUT = Path(r"C:\Users\user\COMPLIANCE-OS\mocks\_stress_results.json")


def _harvest_source_pdfs(zip_path: Path) -> List[tuple]:
    """Return [(filename, bytes), …] for every PDF in the source ZIP."""
    if not zip_path.exists():
        sys.exit(f"Source ZIP not found at {zip_path}")
    out: List[tuple] = []
    with zipfile.ZipFile(zip_path) as zin:
        for info in zin.infolist():
            if info.filename.lower().endswith(".pdf") and not info.filename.startswith("__MACOSX"):
                if info.file_size <= 5_000_000:
                    out.append((info.filename.rsplit("/", 1)[-1], zin.read(info.filename)))
    if not out:
        sys.exit("No PDFs harvested from source ZIP — cannot build stress fixtures.")
    return out


def _build_synthetic_zip(source_pdfs: List[tuple], target_count: int) -> bytes:
    """
    Duplicate the source PDF set with new filenames until target_count is reached.
    Names are stable: stress_001.pdf, stress_002.pdf, ...
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in range(target_count):
            base_name, payload = source_pdfs[i % len(source_pdfs)]
            stem, dot, ext = base_name.rpartition(".")
            ext = ext or "pdf"
            zout.writestr(f"stress_{i + 1:04d}_{stem[:30]}.{ext}" if stem else f"stress_{i + 1:04d}.pdf", payload)
    return buf.getvalue()


def _run_one(size: int, source_pdfs: List[tuple]) -> Dict[str, Any]:
    print(f"\n=== Stress run: {size} documents ===")
    zip_bytes = _build_synthetic_zip(source_pdfs, size)
    print(f"  Built synthetic ZIP: {len(zip_bytes):,} bytes")

    phase_events: List[Dict[str, Any]] = []
    started_at = time.monotonic()

    def emit(pct: float, msg: str) -> None:
        phase_events.append({
            "elapsed_s": round(time.monotonic() - started_at, 2),
            "pct":       pct,
            "msg":       msg,
        })
        if msg.startswith("Phase") or msg.startswith("ISO") or "batch" in msg.lower():
            print(f"    [{pct:5.1f}% @ {phase_events[-1]['elapsed_s']:6.1f}s] {msg}")

    ctx = CompanyContext(
        company_name="Stress Test Corp",
        sector="Manufacturing",
        employee_range="51-250",
        certified="No",
        sites_count="2-5",
        norms=["ISO 14001:2015"],
    )

    tracemalloc.start()
    outcome = run_compliance_pipeline(zip_bytes=zip_bytes, company_context=ctx, emitter=emit)
    current_ram, peak_ram = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    elapsed = round(time.monotonic() - started_at, 2)

    summary: Dict[str, Any] = {
        "target_size":   size,
        "zip_bytes":     len(zip_bytes),
        "success":       outcome.get("success", False),
        "error":         outcome.get("error"),
        "elapsed_s":     elapsed,
        "peak_ram_mb":   round(peak_ram / 1024 / 1024, 1),
        "events_count":  len(phase_events),
    }

    result = outcome.get("result")
    if result is not None:
        summary["documents_analyzed"] = result.documents_analyzed
        summary["expiry_set"]         = result.expiry_report is not None
        summary["executive_set"]      = result.executive_summary is not None
        summary["norms"] = [
            {
                "norm":              n.norm,
                "clauses":           len(n.clauses),
                "major_count":       n.major_count,
                "minor_count":       n.minor_count,
                "observation_count": n.observation_count,
                "conformant_count":  n.conformant_count,
                "spof_count":        n.spof_count,
                "overall_score":     n.overall_score,
            }
            for n in result.norms
        ]

    print(f"  -> {elapsed}s, peak RAM {summary['peak_ram_mb']} MB, success={summary['success']}")
    return summary


def main() -> None:
    source_pdfs = _harvest_source_pdfs(SRC_ZIP)
    print(f"Harvested {len(source_pdfs)} source PDFs from {SRC_ZIP.name}")

    results: List[Dict[str, Any]] = []
    for size in SIZES:
        try:
            results.append(_run_one(size, source_pdfs))
        except Exception as e:
            results.append({
                "target_size": size,
                "success":     False,
                "error":       f"{type(e).__name__}: {e}",
            })
            print(f"  -> FAILED: {e}")

    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "source_zip": str(SRC_ZIP),
        "sizes":   SIZES,
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults written to {OUTPUT}")

    # Summary table
    print("\n=== SUMMARY ===")
    print(f"{'size':>6} {'elapsed':>9} {'peak MB':>9} {'success':>8} {'maj/min/obs/conf':>20}")
    for r in results:
        if r.get("success") and r.get("norms"):
            n = r["norms"][0]
            sev = f"{n['major_count']}/{n['minor_count']}/{n['observation_count']}/{n['conformant_count']}"
        else:
            sev = "-"
        print(f"{r.get('target_size','?'):>6} {r.get('elapsed_s','?'):>9} "
              f"{r.get('peak_ram_mb','?'):>9} {r.get('success','?')!s:>8} {sev:>20}")


if __name__ == "__main__":
    main()
