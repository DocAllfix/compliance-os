"""
cross_norm.py — banco di misura: coerenza tra le norme sulle clausole comuni.

Le tre norme condividono la struttura (4.1, 4.2, 4.3, 5.3, 7.2, 7.5, 9.2, 9.3,
10.2 …). In un sistema integrato lo stesso fatto (un manuale, un organigramma,
un programma di audit) non può essere "conforme" in una norma e "non conforme"
in un'altra. Lo strumento elenca le clausole con lo stesso numero giudicate in
modo opposto (CONFORMANT contro MINOR/MAJOR) in un'esecuzione salvata.

Uso:  python tools/bench/cross_norm.py <cartella_esecuzione> [...]
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

_NC = ("MINOR", "MAJOR")


def conflicts(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_number: Dict[str, List[Dict[str, Any]]] = {}
    for n in result.get("norms", []):
        for c in n.get("clauses", []):
            number = ".".join(str(c.get("clause_id", "")).split("_")[1:])
            by_number.setdefault(number, []).append({"norm": n.get("norm"), **c})
    out = []
    for number, items in sorted(by_number.items()):
        ok = [c for c in items if c.get("severity") == "CONFORMANT"]
        nc = [c for c in items if c.get("severity") in _NC]
        if ok and nc:
            out.append({"clause": number,
                        "conformant": [c["norm"] for c in ok],
                        "nonconforming": [{"norm": c["norm"], "severity": c["severity"],
                                           "finding": str(c.get("finding"))[:260]} for c in nc]})
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for path in sys.argv[1:]:
        with open(os.path.join(path, "result.json") if os.path.isdir(path) else path, encoding="utf-8") as f:
            found = conflicts(json.load(f))
        print(f"\n### {os.path.basename(path.rstrip('/'))}: {len(found)} clausole comuni con giudizi opposti")
        for c in found:
            print(f"  §{c['clause']}: conforme in {', '.join(c['conformant'])}")
            for x in c["nonconforming"]:
                print(f"      {x['severity']} in {x['norm']}: {x['finding']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
