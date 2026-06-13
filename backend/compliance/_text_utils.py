"""Shared text utilities for Amisys QHSE pipeline.

Sprint H.1: introduces word-boundary aware truncation so that excerpts shown
to the user never end mid-word (e.g. "procurement and maintenance activ").
"""
from __future__ import annotations


def truncate_word_safe(text: str, max_chars: int) -> str:
    """Truncate `text` to at most `max_chars`, snapping back to the previous
    word boundary unless that would discard most of the content.

    Returns the original text untouched when it already fits. When truncation
    happens, an ellipsis (`…`) is appended so the reader knows the quote was
    cut. Trailing punctuation immediately before the ellipsis is stripped to
    avoid awkward sequences like "evidence,…".
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]
    last_space = cut.rfind(" ")
    # Only snap to the previous space if it preserves at least 60% of the
    # budget — otherwise the word itself is genuinely long and snapping would
    # leave too little content.
    if last_space > int(max_chars * 0.6):
        cut = cut[:last_space]
    return cut.rstrip(",;:.- \t\n") + "…"
