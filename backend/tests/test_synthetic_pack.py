"""
Fast — Piano motore Fase 0: il pacco sintetico del banco di misura.

Pin: il pacco contiene le trappole di lettura dichiarate (Excel multi-foglio con
celle vuote, organigramma come immagine dentro un Word, planimetria come
immagine, PDF con testo nativo) e la chiave è coerente con il pacco: ogni ENC
cita documenti che esistono, tutte le classi A-E sono rappresentate, nessun
contenuto usa concetti legali italiani (l'azienda è inglese).
"""
from __future__ import annotations

import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "bench"))

import synthetic_pack as S  # noqa: E402


def _files():
    return S.build_files()


def test_key_is_consistent_with_pack():
    files = _files()
    key = S.build_key(files)
    assert {e["class"] for e in key["encs"]} == set("ABCDE")
    assert len({e["id"] for e in key["encs"]}) == len(key["encs"])
    assert all(f["expected_findings"] == 0 for f in key["forbidden"])
    assert sum(e["class"] in ("C", "D") for e in key["encs"]) >= len(key["encs"]) // 2


def test_zip_roundtrip():
    files = _files()
    z = zipfile.ZipFile(io.BytesIO(S.build_zip(files)))
    names = z.namelist()
    assert len(names) == len(files)
    assert all(n.startswith(S.ROOT + "/") for n in names)


def test_reading_traps_are_present():
    import docx
    import fitz
    import openpyxl
    files = _files()
    wb = openpyxl.load_workbook(io.BytesIO(files["4 Context/IMS3 Context and Risk Register.xlsx"]))
    assert {"Context", "Interested Parties", "Risks and Opportunities"} <= set(wb.sheetnames)
    owners = [r[5] for r in wb["Risks and Opportunities"].iter_rows(min_row=2, values_only=True)]
    assert None in owners, "serve una cella vuota a metà tabella"
    manual = docx.Document(io.BytesIO(files["5 Leadership/IMS1 Integrated Management System Manual.docx"]))
    assert manual.inline_shapes, "l'organigramma deve essere un'immagine nel Word"
    assert "Organisation Chart" not in "\n".join(p.text for p in manual.paragraphs), \
        "il contenuto dell'organigramma deve stare solo nell'immagine"
    assert files["8 Operations/Emergency/Site plan.png"][:8] == b"\x89PNG\r\n\x1a\n"
    pdf = fitz.open(stream=files["7 Support/Calibration/NWC-2202.pdf"], filetype="pdf")
    assert "FAIL" in pdf[0].get_text()


def test_no_italian_legal_concepts_in_pack():
    import docx
    import openpyxl
    text = []
    for path, data in _files().items():
        if path.endswith(".docx"):
            d = docx.Document(io.BytesIO(data))
            text += [p.text for p in d.paragraphs]
            text += [c.text for t in d.tables for r in t.rows for c in r.cells]
        elif path.endswith(".xlsx"):
            wb = openpyxl.load_workbook(io.BytesIO(data))
            text += [str(v) for ws in wb for row in ws.iter_rows(values_only=True) for v in row if v]
    assert not re.search(r"\b(RSPP|DUVRI|DVR|D\.\s?Lgs|RLS)\b", "\n".join(text))
