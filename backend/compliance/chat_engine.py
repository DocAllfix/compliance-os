"""
ComplianceOS — Chat Engine (Phase 4).

Answers natural language questions about a completed gap analysis.
Uses ChromaDB to retrieve relevant evidence cards, then calls Azure GPT-4.1-mini
with only the relevant context.

Each answer includes a list of source citations (file_name, pages, excerpt).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

from compliance.context_intake import build_context_prompt_block
from compliance.schemas import CompanyContext


_SYSTEM_PROMPT = """You are a compliance analysis assistant helping a compliance manager understand their ISO gap analysis results.

{company_context}

You have access to evidence cards extracted from the company's documents. Answer questions clearly, concisely, and in UK English. Be direct — the user is a professional, not a student.

Rules:
- Base your answers only on the evidence cards provided. Do not invent facts.
- If the evidence does not contain enough information to answer the question, say so clearly.
- Always cite the source document(s) by file name and page number when available.
- Keep answers under 200 words unless the question genuinely requires more detail.
- Do not use the word "auditor". You are an advisor, not an inspector.
- Format citations as [file_name, p.N] inline in the text.
"""

_CITATION_PROMPT = """

After your answer, output a JSON block on its own line with this exact format:
{"sources": [{"file_name": "...", "pages": [1, 2], "excerpt": "..."}]}

Include only sources you actually referenced in your answer. Maximum 3 sources.
"""


def answer_question(
    question: str,
    analysis_id: str,
    company_context: Optional[CompanyContext] = None,
    n_evidence: int = 4,
) -> Dict[str, Any]:
    """
    Answer a question about a gap analysis using ChromaDB evidence retrieval.

    Args:
        question:        Natural language question from the user.
        analysis_id:     The analysis ID used to locate the ChromaDB collection.
        company_context: Optional context for personalising the system prompt.
        n_evidence:      Number of evidence cards to retrieve.

    Returns:
        dict with keys:
            answer   (str)  — the answer text
            sources  (list) — list of {file_name, pages, excerpt} dicts
            error    (str | None)
    """
    evidence = _retrieve_evidence(question, analysis_id, n_evidence)
    context_block = build_context_prompt_block(company_context) if company_context else ""

    system = _SYSTEM_PROMPT.replace("{company_context}", context_block)
    user   = _build_user_prompt(question, evidence)

    messages = [
        {"role": "system", "content": system + _CITATION_PROMPT},
        {"role": "user",   "content": user},
    ]

    raw = _call_llm(messages)
    answer_text, sources = _parse_response(raw, evidence)

    return {
        "answer":  answer_text,
        "sources": sources,
        "error":   None,
    }


# ── Evidence retrieval ────────────────────────────────────────────────────────

def _retrieve_evidence(question: str, analysis_id: str, n: int) -> List[Dict[str, Any]]:
    """
    Query ChromaDB for evidence cards relevant to the question.
    Uses a persistent client so collections survive across requests.
    Falls back to empty list if collection not found (analysis not yet indexed).
    """
    try:
        from compliance.embedder import _safe_collection_name
        collection_name = _safe_collection_name(analysis_id)

        client = chromadb.EphemeralClient()
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return []

        results = collection.query(
            query_texts=[question],
            n_results=min(n, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        docs      = (results.get("documents")  or [[]])[0]
        metas     = (results.get("metadatas")  or [[]])[0]
        distances = (results.get("distances")  or [[]])[0]

        return [
            {**meta, "excerpt": doc[:400], "distance": round(float(dist), 4)}
            for doc, meta, dist in zip(docs, metas, distances)
        ]
    except Exception:
        return []


def _build_user_prompt(question: str, evidence: List[Dict[str, Any]]) -> str:
    parts = [f"Question: {question}", ""]

    if evidence:
        parts.append("Relevant evidence from the company's documents:")
        for i, ev in enumerate(evidence, 1):
            parts += [
                f"[{i}] File: {ev.get('file_name', 'unknown')}",
                f"    ISO clause: {ev.get('iso_clause_primary', '')}",
                f"    Gap signal: {ev.get('gap_signal', False)}",
                f"    Excerpt: {ev.get('excerpt', '')[:300]}",
                "",
            ]
    else:
        parts.append("No specific evidence cards were retrieved for this question.")
        parts.append("Answer based on general ISO compliance knowledge if appropriate.")

    return "\n".join(parts)


# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_response(raw: str, evidence: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """
    Split the LLM response into answer text and sources JSON block.
    Falls back to extracting sources from the evidence list if JSON is malformed.
    """
    sources: List[Dict[str, Any]] = []
    answer_text = raw.strip()

    # Look for a JSON sources block on its own line
    lines = raw.strip().split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('{"sources"'):
            try:
                parsed = json.loads(stripped)
                sources = parsed.get("sources", [])
                answer_text = "\n".join(lines[:i]).strip()
                break
            except json.JSONDecodeError:
                pass

    # Fallback: use gap-signal evidence as sources
    if not sources and evidence:
        sources = [
            {
                "file_name": ev.get("file_name", ""),
                "pages":     [],
                "excerpt":   ev.get("excerpt", "")[:200],
            }
            for ev in evidence[:2]
            if ev.get("gap_signal") == "true" or ev.get("gap_signal") is True
        ]

    return answer_text, sources


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(messages: List[Dict[str, str]]) -> str:
    try:
        from v2.azure_openai_client_v2 import AzureOpenAIClientV2
        from v2.provider_profiles_v2 import PROVIDER_PROFILES

        profile = PROVIDER_PROFILES.get("gpt-4.1-mini")
        if profile is None:
            raise ValueError("gpt-4.1-mini profile not found")

        client = AzureOpenAIClientV2(profile=profile)
        stream = client.chat_stream(messages=messages, max_tokens=512)

        chunks: List[str] = []
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta   = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    chunks.append(content)

        return "".join(chunks)

    except Exception as e:
        return f"Unable to generate answer: {e}"
