"""
Fast — parse del sommario esecutivo.

Pin: il modello va a capo tra i paragrafi della narrativa dentro la stringa JSON
(carattere di controllo: JSON non valido in senso stretto). Il sommario non deve
andare perso per questo; restano tollerati i fence e il testo attorno all'oggetto.
"""
from __future__ import annotations

from compliance.pipeline import _parse_summary_json


def test_newlines_inside_strings_are_tolerated():
    raw = '{"company_snapshot": {"key_roles": []}, "executive_narrative": "First paragraph.\n\nSecond paragraph."}'
    data = _parse_summary_json(raw)
    assert data is not None and data["executive_narrative"].endswith("Second paragraph.")


def test_fences_and_surrounding_text():
    assert _parse_summary_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_summary_json('Here it is:\n{"a": 1}\nDone.') == {"a": 1}
    assert _parse_summary_json("not json at all") is None
