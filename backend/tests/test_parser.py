"""
Fast regression for _parse_evidence_yaml.

The parser must:
  - tolerate the multi-DOC marker format produced by Phase 2
  - fall back to regex split when yaml.safe_load on the whole text would
    silently collapse multiple cards into one dict
  - skip individual malformed cards rather than aborting the batch
"""
from __future__ import annotations

from compliance.gap_analyzer import _parse_evidence_yaml


MULTI = """# ── DOC 1 ──
evidence_id: ev_001_alpha
file_name: alpha.pdf
doc_type: policy
iso_clause_primary: "ISO 9001 §5.2"
gap_signal: false
readable: true
summary: First card.

# ── DOC 2 ──
evidence_id: ev_002_beta
file_name: beta.pdf
doc_type: procedure
iso_clause_primary: "ISO 9001 §6.1"
gap_signal: true
readable: true
summary: Second card.

# ── DOC 3 ──
evidence_id: ev_003_gamma
file_name: gamma.pdf
doc_type: record
iso_clause_primary: "ISO 9001 §9.1"
gap_signal: false
readable: true
summary: Third card.
"""

SINGLE = """evidence_id: ev_001_only
file_name: only.pdf
doc_type: policy
iso_clause_primary: "ISO 9001 §5.2"
gap_signal: false
readable: true
summary: Only one card.
"""

PARTIALLY_CORRUPTED = """# ── DOC 1 ──
evidence_id: ev_001_good
file_name: good.pdf
doc_type: record
iso_clause_primary: "ISO 9001 §7.5"
gap_signal: false
readable: true
summary: Good card.

# ── DOC 2 ──
evidence_id: "ev_002_corrupted
file_name: corrupted.pdf
[this card is YAML-broken on purpose

# ── DOC 3 ──
evidence_id: ev_003_alsogood
file_name: alsogood.pdf
doc_type: record
iso_clause_primary: "ISO 9001 §7.5"
gap_signal: false
readable: true
summary: Also good.
"""


def test_parser_multi_card():
    cards = _parse_evidence_yaml(MULTI)
    assert len(cards) == 3
    assert cards[0]["evidence_id"] == "ev_001_alpha"
    assert cards[1]["evidence_id"] == "ev_002_beta"
    assert cards[2]["evidence_id"] == "ev_003_gamma"


def test_parser_single_card():
    cards = _parse_evidence_yaml(SINGLE)
    assert len(cards) == 1
    assert cards[0]["evidence_id"] == "ev_001_only"


def test_parser_empty_input():
    assert _parse_evidence_yaml("") == []
    assert _parse_evidence_yaml("   \n  \n") == []


def test_parser_skips_corrupted_card():
    """The middle card has a syntax error; the parser should keep the two good ones."""
    cards = _parse_evidence_yaml(PARTIALLY_CORRUPTED)
    ids = [c["evidence_id"] for c in cards if "evidence_id" in c]
    assert "ev_001_good" in ids
    assert "ev_003_alsogood" in ids
    # The corrupted middle card may or may not be parsed depending on yaml's
    # tolerance for the quote mismatch — we only require the good ones survive
    assert len(cards) >= 2
