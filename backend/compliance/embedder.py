"""
Evidence embedder for Amisys QHSE.

Uses ChromaDB in embedded (zero-server) mode. Each analysis session gets its
own ephemeral collection keyed by analysis_id, so sessions never cross-contaminate.
Collections are created fresh per analysis run and discarded after use.

Sprint R2 — chunk-level index:
    The collection now holds TWO kinds of entries:
      - `content` chunks: ~1,500-char slices of the ORIGINAL document text
        (page-aware via the `[PAGE n]` / `[SHEET "..."]` markers inserted by
        Phase 1). This is what makes retrieval content-grounded instead of
        summary-grounded, and what gives real page numbers to citations.
      - `summary` chunks: the Phase 2 card blob (summary + gap_detail +
        excerpts). Kept because card summaries are always UK English — for
        non-English corpora they are the bridge that lets an English query
        match Italian documents with the default English embedding model.

    Callers that only have cards (e.g. the chat path rebuilding from the
    persisted evidence YAML) keep using `index_evidence_cards` and get
    summary-only indexing — same behaviour as before R2.

Dependencies: chromadb>=1.5.0 (installed in requirements.txt)
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

import chromadb


# ── Chunking parameters (Sprint R2) ──────────────────────────────────────────

CHUNK_TARGET_CHARS = 1_500
CHUNK_OVERLAP_CHARS = 200

_MARKER_RE = re.compile(r'\[(?:PAGE (\d+)|SHEET "([^"]+)")\]')


def chunk_document_text(text: str) -> List[Dict[str, Any]]:
    """
    Split a Phase 1 document text into ~CHUNK_TARGET_CHARS chunks with
    paragraph-boundary preference and CHUNK_OVERLAP_CHARS of overlap.

    Honours `[PAGE n]` / `[SHEET "name"]` markers: each chunk records the
    page numbers it spans (sheets are numbered by 1-based position).

    Returns a list of {"text": str, "pages": List[int]} dicts. The markers
    themselves are stripped from the chunk text.
    """
    if not text or not text.strip():
        return []

    # Segment the text by positional markers, tracking the active page.
    segments: List[Dict[str, Any]] = []   # {"page": int|None, "text": str}
    sheet_counter = 0
    last_end = 0
    current_page: Optional[int] = None

    for m in _MARKER_RE.finditer(text):
        before = text[last_end:m.start()]
        if before.strip():
            segments.append({"page": current_page, "text": before})
        if m.group(1) is not None:
            current_page = int(m.group(1))
        else:
            sheet_counter += 1
            current_page = sheet_counter
        last_end = m.end()
    tail = text[last_end:]
    if tail.strip():
        segments.append({"page": current_page, "text": tail})

    # Flatten into (paragraph, page) pairs.
    para_pages: List[tuple] = []
    for seg in segments:
        for para in re.split(r"\n{2,}", seg["text"]):
            para = para.strip()
            if para:
                para_pages.append((para, seg["page"]))

    if not para_pages:
        return []

    # Greedy pack paragraphs into chunks of ~CHUNK_TARGET_CHARS.
    chunks: List[Dict[str, Any]] = []
    buf: List[str] = []
    buf_pages: List[int] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_pages, buf_len
        if buf:
            chunks.append({
                "text": "\n\n".join(buf),
                "pages": sorted(set(p for p in buf_pages if p is not None)),
            })
        buf, buf_pages, buf_len = [], [], 0

    for para, page in para_pages:
        # Oversized single paragraph: hard-split on sentence-ish boundaries.
        while len(para) > CHUNK_TARGET_CHARS * 2:
            cut = para.rfind(". ", 0, CHUNK_TARGET_CHARS)
            cut = cut + 1 if cut > CHUNK_TARGET_CHARS // 2 else CHUNK_TARGET_CHARS
            piece, para = para[:cut].strip(), para[cut:].strip()
            if buf_len + len(piece) > CHUNK_TARGET_CHARS:
                flush()
            buf.append(piece); buf_pages.append(page); buf_len += len(piece)
            flush()

        if buf_len + len(para) > CHUNK_TARGET_CHARS and buf:
            # Carry a tail of the previous chunk as overlap for continuity.
            overlap_text = buf[-1][-CHUNK_OVERLAP_CHARS:] if buf else ""
            overlap_page = buf_pages[-1] if buf_pages else None
            flush()
            if overlap_text:
                buf.append(overlap_text); buf_pages.append(overlap_page)
                buf_len = len(overlap_text)
        buf.append(para); buf_pages.append(page); buf_len += len(para)

    flush()
    return chunks


class EvidenceEmbedder:
    """
    Wraps ChromaDB embedded client for evidence indexing and retrieval.

    Usage (full corpus, Phase 3):
        embedder = EvidenceEmbedder(analysis_id)
        embedder.index_corpus(cards, documents)   # content chunks + summaries
        results = embedder.query_for_clause(clause_dict, n_results=4)
        embedder.close()

    Usage (cards only, chat path):
        embedder.index_evidence_cards(cards)      # summary chunks only
    """

    def __init__(self, analysis_id: str):
        self.analysis_id = analysis_id
        self.collection_name = _safe_collection_name(analysis_id)
        self._client = chromadb.EphemeralClient()
        self._collection: Optional[chromadb.Collection] = None

    # ──────────────────────────────────────────────────────────────────────────
    # Indexing
    # ──────────────────────────────────────────────────────────────────────────

    def _fresh_collection(self) -> None:
        # Sprint H.2: ChromaDB's EphemeralClient keeps a process-wide collection
        # registry, so calling create_collection() twice with the same name in
        # the same process raises InternalError. Delete any prior collection
        # before creating a fresh one — each indexing call owns a clean slate.
        try:
            self._client.delete_collection(name=self.collection_name)
        except Exception:
            pass  # No prior collection — first run for this analysis_id.
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def index_corpus(
        self,
        cards: List[Dict[str, Any]],
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        Sprint R2 — index the full corpus: content chunks from the original
        document texts PLUS summary chunks from the Phase 2 cards.

        `documents` is the Phase 1 list of {"filename", "content"} dicts.
        Cards are matched to documents by normalised file name to inherit
        evidence_id / doc_type / gap_signal metadata.

        Returns the number of entries indexed.
        """
        self._fresh_collection()

        ids: List[str] = []
        texts: List[str] = []
        metas: List[Dict[str, Any]] = []

        cards_by_file = {
            _normalise_name(str(c.get("file_name", ""))): c for c in cards
        }

        # 1) Content chunks from original documents
        for doc in (documents or []):
            fname = str(doc.get("filename", ""))
            content = str(doc.get("content", "") or "")
            card = cards_by_file.get(_normalise_name(fname), {})
            evidence_id = str(card.get("evidence_id", "") or f"doc_{_short_hash(fname)}")

            for ci, chunk in enumerate(chunk_document_text(content)):
                ids.append(f"{evidence_id}_c{ci:03d}")
                texts.append(chunk["text"])
                metas.append({
                    "chunk_kind":        "content",
                    "evidence_id":       evidence_id,
                    "file_name":         fname,
                    "doc_type":          str(card.get("doc_type", "other")),
                    "iso_clause_primary": str(card.get("iso_clause_primary", "") or ""),
                    "gap_signal":        str(card.get("gap_signal", False)).lower(),
                    "confidence":        float(card.get("confidence", 0.5) or 0.5),
                    # ChromaDB metadata must be scalar — serialise page list.
                    "pages":             ",".join(str(p) for p in chunk["pages"]),
                })

        # 2) Summary chunks from cards (English bridge + LLM-derived signal)
        for i, card in enumerate(cards):
            text = _card_to_document_text(card)
            if not text.strip():
                continue
            evidence_id = str(card.get("evidence_id", "") or f"ev_{i:03d}")
            ids.append(f"{evidence_id}_summary")
            texts.append(text)
            metas.append({
                "chunk_kind":        "summary",
                "evidence_id":       evidence_id,
                "file_name":         str(card.get("file_name", "")),
                "doc_type":          str(card.get("doc_type", "other")),
                "iso_clause_primary": str(card.get("iso_clause_primary", "") or ""),
                "gap_signal":        str(card.get("gap_signal", False)).lower(),
                "confidence":        float(card.get("confidence", 0.5) or 0.5),
                "pages":             _first_excerpt_pages(card),
            })

        if not ids:
            return 0
        self._collection.add(documents=texts, metadatas=metas, ids=ids)
        return len(ids)

    def index_evidence_cards(self, cards: List[Dict[str, Any]]) -> int:
        """
        Card-only indexing (summary chunks). Used by the chat path where the
        original document texts are no longer available. Pre-R2 behaviour.
        """
        if not cards:
            return 0
        return self.index_corpus(cards, documents=None)

    # ──────────────────────────────────────────────────────────────────────────
    # Query
    # ──────────────────────────────────────────────────────────────────────────

    def query_for_clause(
        self,
        clause: Dict[str, Any],
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Query the collection for evidence relevant to a given ISO clause.

        The query text is built from the clause's evidence_keywords and title,
        giving ChromaDB the best signal for semantic similarity.

        Returns a list of dicts with keys:
            evidence_id, file_name, doc_type, iso_clause_primary,
            gap_signal, confidence, chunk_kind, pages (List[int]),
            excerpt (chunk text), distance
        """
        if self._collection is None:
            return []

        keywords: List[str] = clause.get("evidence_keywords", [])
        title: str = clause.get("title", "")
        query_text = f"{title}. {' '.join(keywords)}"

        try:
            results = self._collection.query(
                query_texts=[query_text],
                n_results=min(n_results, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        output: List[Dict[str, Any]] = []
        docs      = (results.get("documents")  or [[]])[0]
        metas     = (results.get("metadatas")  or [[]])[0]
        distances = (results.get("distances")  or [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            entry = {
                **meta,
                "excerpt":  doc[:1500],
                "distance": round(float(dist), 4),
                "gap_signal": str(meta.get("gap_signal", "false")).lower() == "true",
                "pages": _parse_pages_meta(meta.get("pages", "")),
            }
            output.append(entry)

        return output

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Delete the ephemeral collection to free memory."""
        if self._collection is not None:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = None


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_collection_name(analysis_id: str) -> str:
    """
    ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens,
    start and end with alphanumeric. Hash the id to guarantee compliance.
    """
    slug = re.sub(r"[^a-z0-9]", "-", analysis_id.lower())[:40]
    suffix = hashlib.md5(analysis_id.encode()).hexdigest()[:8]
    name = f"co-{slug}-{suffix}".strip("-")
    return name[:63]


def _normalise_name(name: str) -> str:
    """Filename match key: lowercase, path-stripped, whitespace collapsed."""
    n = name.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\s+", " ", n).strip().lower()


def _short_hash(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()[:8]


def _first_excerpt_pages(card: Dict[str, Any]) -> str:
    excerpts = card.get("excerpts") or []
    if excerpts and isinstance(excerpts[0], dict):
        pages = excerpts[0].get("pages") or []
        return ",".join(str(p) for p in pages)
    return ""


def _parse_pages_meta(raw: Any) -> List[int]:
    if not raw:
        return []
    try:
        return [int(p) for p in str(raw).split(",") if str(p).strip().isdigit()]
    except Exception:
        return []


def _card_to_document_text(card: Dict[str, Any]) -> str:
    """
    Flatten the most semantically rich fields of a card into a single string
    for embedding. Order matters: summary first (most informative), then
    gap_detail, then excerpts.
    """
    parts: List[str] = []

    summary = card.get("summary", "")
    if summary:
        parts.append(str(summary).strip())

    gap_detail = card.get("gap_detail", "")
    if gap_detail and gap_detail.strip().lower() != "no gap identified.":
        parts.append(str(gap_detail).strip())

    excerpts = card.get("excerpts") or []
    for ex in excerpts[:2]:
        text = ex.get("text", "") if isinstance(ex, dict) else str(ex)
        if text:
            parts.append(str(text).strip())

    iso_clause = card.get("iso_clause_primary", "")
    if iso_clause:
        parts.append(f"ISO clause: {iso_clause}")

    return "\n\n".join(p for p in parts if p)
