"""
Fast regression for nested-ZIP walking (bug CENTRO SERAPIDE: solo 4 doc estratti).

Pins: ricorsione dentro gli ZIP annidati a più livelli, esclusione del junk
macOS (__MACOSX/, ._*, .DS_Store), e che pipeline._extract_documents veda i
file annidati. Niente LLM/OCR: si usano file .txt (estrazione nativa).
"""
from __future__ import annotations

import io
import zipfile

from compliance.extraction import iter_zip_files, _is_zip_junk


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_junk_detection():
    assert _is_zip_junk("__MACOSX/file.pdf")
    assert _is_zip_junk("folder/__MACOSX/._x.pdf")
    assert _is_zip_junk("folder/._shadow.pdf")
    assert _is_zip_junk(".DS_Store")
    assert not _is_zip_junk("folder/real.pdf")
    assert not _is_zip_junk("a/b/inner.zip")


def test_flat_zip_lists_real_files():
    z = _zip({
        "a.txt": b"alpha",
        "sub/b.txt": b"bravo",
        "__MACOSX/._a.txt": b"junk",
        ".DS_Store": b"junk",
        "sub/._b.txt": b"junk",
    })
    names = sorted(n for n, _ in iter_zip_files(z))
    assert names == ["a.txt", "sub/b.txt"]


def test_nested_zip_is_recursed():
    inner = _zip({"deep1.txt": b"d1", "deep2.txt": b"d2"})
    outer = _zip({"loose.txt": b"L", "pack/inner.zip": inner, "__MACOSX/._inner.zip": b"junk"})
    names = sorted(n for n, _ in iter_zip_files(outer))
    # loose + i due dentro il nested, junk escluso
    assert names == ["loose.txt", "pack/inner.zip/deep1.txt", "pack/inner.zip/deep2.txt"]


def test_double_nested_zip():
    lvl2 = _zip({"x.txt": b"x"})
    lvl1 = _zip({"l2.zip": lvl2, "y.txt": b"y"})
    top = _zip({"l1.zip": lvl1})
    names = sorted(n for n, _ in iter_zip_files(top))
    assert names == ["l1.zip/l2.zip/x.txt", "l1.zip/y.txt"]


def test_pipeline_extract_sees_nested(monkeypatch):
    from compliance import pipeline
    inner = _zip({"proc.txt": b"procedure body text"})
    outer = _zip({"policy.txt": b"policy body text", "allegati/inner.zip": inner})
    docs = pipeline._extract_documents(outer, lambda p, m: None)
    names = sorted(d["filename"] for d in docs)
    assert names == ["allegati/inner.zip/proc.txt", "policy.txt"]
    assert all(d["content"].strip() for d in docs)
