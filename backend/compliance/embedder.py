"""
Evidence embedder for ComplianceOS.

Uses ChromaDB in embedded (zero-server) mode. Each analysis session gets its
own ephemeral collection keyed by analysis_id, so sessions never cross-contaminate.
Collections are created fresh per analysis run and discarded after use.

Dependencies: chromadb>=1.5.0 (installed in requirements.txt)
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

import chromadb


class EvidenceEmbedder:
    """
    Wraps ChromaDB embedded client for evidence card indexing and retrieval.

    Usage:
        embedder = EvidenceEmbedder(analysis_id="mock_20260508_1430")
        embedder.index_evidence_cards(cards)
        results = embedder.query_for_clause(clause_dict, n_results=3)
        embedder.close()
    """

    def __init__(self, analysis_id: str):
        self.analysis_id = analysis_id
        self.collection_name = _safe_collection_name(analysis_id)
        self._client = chromadb.EphemeralClient()
        self._collection: Optional[chromadb.Collection] = None

    # ──────────────────────────────────────────────────────────────────────────
    # Indexing
    # ──────────────────────────────────────────────────────────────────────────

    def index_evidence_cards(self, cards: List[Dict[str, Any]]) -> int:
        """
        Index a list of evidence card dicts into a ChromaDB collection.

        Each card is stored as a document combining the summary, excerpts,
        and gap_detail fields — the fields most relevant for semantic search.

        Returns the number of cards successfully indexed.
        """
        if not cards:
            return 0

        # Sprint H.2: ChromaDB's EphemeralClient keeps a process-wide collection
        # registry, so calling create_collection() twice with the same name in
        # the same process raises InternalError("Collection ... already exists").
        # This is exactly what happens on the chat endpoint when the same
        # analysis_id is queried more than once per backend lifetime. Delete
        # any prior collection with this name before creating a fresh one —
        # each indexing call must own a clean slate, never reuse stale content
        # from a previous request.
        try:
            self._client.delete_collection(name=self.collection_name)
        except Exception:
            pass  # No prior collection — first run for this analysis_id.

        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        for i, card in enumerate(cards):
            text = _card_to_document_text(card)
            if not text.strip():
                continue

            doc_id = card.get("evidence_id") or f"ev_{i:03d}"
            ids.append(doc_id)
            documents.append(text)
            metadatas.append({
                "evidence_id":       str(card.get("evidence_id", "")),
                "file_name":         str(card.get("file_name", "")),
                "doc_type":          str(card.get("doc_type", "other")),
                "iso_clause_primary": str(card.get("iso_clause_primary", "")),
                "gap_signal":        str(card.get("gap_signal", False)).lower(),
                "confidence":        float(card.get("confidence", 0.5)),
            })

        if not documents:
            return 0

        self._collection.add(documents=documents, metadatas=metadatas, ids=ids)
        return len(documents)

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
            gap_signal, confidence, excerpt (the indexed text), distance
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
            output.append({
                **meta,
                "excerpt":  doc[:500],
                "distance": round(float(dist), 4),
                "gap_signal": meta.get("gap_signal", "false") == "true",
            })

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
