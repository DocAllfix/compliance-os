"""
Fast regression — Hardening 2026 problema #3 (gate qualità OCR).

Pin: testo con codifica-font rotta (caratteri di controllo) è riconosciuto come
bassa qualità → instraderà la pagina/doc all'OCR; testo reale (anche italiano
accentato, anche corto) NON viene mai flaggato (no falsi positivi → no OCR inutile).
"""
from __future__ import annotations

from compliance.extraction import _is_low_quality_text


def test_control_char_garbage_is_low_quality():
    garbage = "[PAGE 1]\n" + "".join(chr(c) for c in range(2, 14)) * 400
    assert _is_low_quality_text(garbage) is True


def test_clean_italian_text_is_ok():
    txt = ("La presente procedura definisce le modalità per la gestione della qualità "
           "secondo la norma ISO 9001:2015. Responsabilità, attività e registrazioni "
           "sono descritte nei paragrafi seguenti. Però è necessità della società. ") * 6
    assert _is_low_quality_text(txt) is False


def test_short_text_never_flagged():
    # sotto la soglia minima di caratteri non si forza l'OCR sulla qualità
    assert _is_low_quality_text("abc \x02\x03") is False


def test_short_garbage_page_flagged():
    # raffinamento: pagine-garbage di 40-200 char (control non-whitespace) ora prese
    # (prima sfuggivano con soglia 200) — chiude il buco visto sulla visura
    assert _is_low_quality_text("".join(chr(c) for c in range(2, 9)) * 10) is True


def test_large_clean_doc_with_stray_controls_not_flagged():
    # contro-regressione: un doc grande e pulito con qualche control char sparso
    # NON deve essere flaggato (il trigger assoluto, scartato, lo flaggava)
    big_clean = ("La procedura di gestione qualità ISO 9001. " * 4000) + ("\x07" * 40)
    assert _is_low_quality_text(big_clean) is False


def test_accented_latin_is_readable():
    assert _is_low_quality_text("àèéìòùÀÈÉÌÒÙ çñü " * 40) is False


def test_mostly_garbage_with_some_text():
    mixed = "Documento " + "".join(chr(c) for c in range(2, 14)) * 300
    assert _is_low_quality_text(mixed) is True


def test_page_markers_stripped_before_judging():
    # solo i marcatori [PAGE n] + poco testo → non flaggato (non è garbage)
    assert _is_low_quality_text("[PAGE 1]\n[PAGE 2]\n[PAGE 3]\nbreve testo reale") is False
