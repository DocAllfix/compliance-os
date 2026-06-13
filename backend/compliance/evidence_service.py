"""
Amisys QHSE — EvidenceService.

Typed retrieval layer over the ChromaDB evidence index. Wraps
`EvidenceEmbedder` to expose semantically meaningful operations
(get evidence for a clause, semantic search, doc_type filter, coverage gaps)
without leaking the embedder's lower-level query shape into call sites.

Used by:
    - gap_analyzer (Phase 3 retrieval — Sprint 3.2)
    - api_server `/chat` endpoint (Sprint 3.3)

Lifecycle: the service holds a reference to a pre-indexed EvidenceEmbedder.
It does NOT create or own the embedder — that is the caller's responsibility,
so the service composes cleanly with the existing pipeline (Phase 3 already
builds the embedder and we just wrap it).

For the post-audit chat path where the original embedder is no longer in
memory, use `EvidenceService.from_cards(analysis_id, cards)` which builds a
fresh in-process embedder from the persisted ComplianceAnalysisResult plus
the evidence cards retrieved from SQLite. This keeps every query grounded
on the same data that produced the report.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from compliance.embedder import EvidenceEmbedder


class EvidenceService:
    """
    High-level retrieval API over an indexed EvidenceEmbedder.

    All methods return flat list-of-dict shapes ready to be serialised
    as JSON / sent to an LLM / rendered in the UI. Never raw embedder
    internals.
    """

    def __init__(self, analysis_id: str, embedder: Optional[EvidenceEmbedder] = None):
        self.analysis_id = analysis_id
        self._owns_embedder = embedder is None
        self._embedder: EvidenceEmbedder = embedder or EvidenceEmbedder(analysis_id)

    # ── Factory: build a fresh service from persisted cards ───────────────────

    @classmethod
    def from_cards(cls, analysis_id: str, cards: List[Dict[str, Any]]) -> "EvidenceService":
        """
        Construct a service by indexing the provided cards into a fresh
        EvidenceEmbedder. Useful for the post-audit chat path where the
        original embedder used during Phase 3 is no longer alive.

        The caller is responsible for calling `close()` when done.
        """
        emb = EvidenceEmbedder(analysis_id)
        emb.index_evidence_cards(cards)
        return cls(analysis_id=analysis_id, embedder=emb)

    # ── Retrieval API ────────────────────────────────────────────────────────

    def get_evidences_for_clause(self, clause: Dict[str, Any], n: int = 4) -> List[Dict[str, Any]]:
        """
        Top-N evidence cards semantically related to an ISO clause.

        `clause` is the clause dict from the iso_clauses module
        (must contain `title` and `evidence_keywords`).
        """
        return self._embedder.query_for_clause(clause, n_results=n)

    def get_evidences_similar_to(self, query_text: str, n: int = 6) -> List[Dict[str, Any]]:
        """
        Free-text semantic search over the indexed cards.

        Builds a synthetic clause-shaped dict from the query so the
        existing embedder path is reused without modifying its API.
        """
        if not query_text or not query_text.strip():
            return []

        synthetic_clause = {
            "title":             query_text.strip(),
            "evidence_keywords": [],
        }
        return self._embedder.query_for_clause(synthetic_clause, n_results=n)

    def get_evidences_by_doc_type(self, doc_type: str) -> List[Dict[str, Any]]:
        """
        Metadata filter: return all cards of a given doc_type.

        Walks the collection rather than running a vector query — this is
        an exact-match operation, not a semantic one.
        """
        coll = self._embedder._collection  # intentional: no public iterator on EvidenceEmbedder
        if coll is None:
            return []
        try:
            res = coll.get(
                where={"doc_type": doc_type.lower().strip()},
                include=["metadatas", "documents"],
            )
        except Exception:
            return []

        metas = res.get("metadatas") or []
        docs  = res.get("documents") or []
        out: List[Dict[str, Any]] = []
        for meta, doc in zip(metas, docs):
            out.append({
                **meta,
                "excerpt":    str(doc)[:500],
                "gap_signal": str(meta.get("gap_signal", "false")).lower() == "true",
            })
        return out

    def get_clauses_without_evidence(
        self,
        clauses: List[Dict[str, Any]],
        distance_threshold: float = 1.5,
    ) -> List[str]:
        """
        For each clause, run the retrieval and return the clause_ids that
        come back with zero results, OR whose best match is below the
        distance threshold (cosine distance: lower = more similar; a result
        above the threshold indicates no semantically pertinent evidence).
        """
        empty: List[str] = []
        for clause in clauses:
            results = self.get_evidences_for_clause(clause, n=1)
            if not results:
                empty.append(str(clause.get("id", "")))
                continue
            top_distance = float(results[0].get("distance", 0.0))
            if top_distance > distance_threshold:
                empty.append(str(clause.get("id", "")))
        return empty

    def get_all_cards(self) -> List[Dict[str, Any]]:
        """
        Dump every card currently in the collection. Used by the chat
        endpoint to provide full audit context to the LLM when needed.
        """
        coll = self._embedder._collection
        if coll is None:
            return []
        try:
            res = coll.get(include=["metadatas", "documents"])
        except Exception:
            return []
        metas = res.get("metadatas") or []
        docs  = res.get("documents") or []
        out: List[Dict[str, Any]] = []
        for meta, doc in zip(metas, docs):
            out.append({
                **meta,
                "excerpt":    str(doc)[:500],
                "gap_signal": str(meta.get("gap_signal", "false")).lower() == "true",
            })
        return out

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """
        Release the underlying embedder if this service created it.
        If the embedder was supplied by the caller, leave it alone.
        """
        if self._owns_embedder and self._embedder is not None:
            self._embedder.close()
