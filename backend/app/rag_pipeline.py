"""
The RAG core: retrieval-augmented generation used for three jobs in this app:

1. `answer_query`        -- chat with your SOPs (dashboard chat box)
2. `analyze_deviation`    -- compare a live process event against the retrieved SOP step
3. `draft_sop_update`     -- given a cluster of deviations, draft a revised SOP section

All three retrieve context from the vector store first, then ground an LLM call in
that context -- classic RAG -- with JSON-mode prompts for the two structured jobs.
"""
from __future__ import annotations

import json
from typing import List, Tuple

from . import llm_client
from .embeddings import embed_text
from .vector_store import get_vector_store


def retrieve(query: str, top_k: int = 4, collection: str = "sops") -> List[Tuple[str, float, dict]]:
    """Embed the query and pull the top_k most similar SOP chunks from the vector store."""
    store = get_vector_store(collection)
    q_vec = embed_text(query)
    return store.search(q_vec, top_k=top_k)


def _format_context(hits: List[Tuple[str, float, dict]]) -> str:
    blocks = []
    for chunk_id, score, meta in hits:
        blocks.append(
            f"[Source: {meta.get('sop_title', 'unknown')} | chunk {chunk_id} | similarity={score:.2f}]\n"
            f"{meta.get('text', '')}"
        )
    return "\n\n".join(blocks)


def answer_query(query: str, top_k: int = 4) -> dict:
    """RAG chat: retrieve relevant SOP chunks, ask Claude to answer grounded only in them."""
    hits = retrieve(query, top_k=top_k)
    context = _format_context(hits)

    system = (
        "You are ProcessGenome AI, an assistant that answers questions about a company's "
        "Standard Operating Procedures (SOPs). Answer ONLY using the provided context. "
        "If the context doesn't contain the answer, say so plainly. Cite which SOP each "
        "piece of your answer comes from. Be concise and operational."
    )
    user = f"Context:\n{context}\n\nQuestion: {query}"
    answer = llm_client.generate(system, user, max_tokens=600)

    sources = [
        {
            "chunk_id": chunk_id,
            "sop_id": meta.get("sop_id", ""),
            "sop_title": meta.get("sop_title", ""),
            "score": score,
            "text": meta.get("text", ""),
        }
        for chunk_id, score, meta in hits
    ]
    return {"answer": answer, "sources": sources}


def analyze_deviation(step_description: str, actual_action: str, sop_hint: str | None = None) -> dict:
    """
    Retrieve the most relevant documented SOP step for `step_description`, then ask the
    LLM whether `actual_action` deviates from it. Returns a dict with is_deviation,
    severity, explanation, plus the matched chunk for traceability.
    """
    hits = retrieve(step_description, top_k=1)
    matched = hits[0] if hits else None
    documented_step = matched[2].get("text", "(no matching SOP step found)") if matched else "(no SOP indexed yet)"

    system = (
        "You are a process-compliance auditor. Compare the DOCUMENTED SOP STEP against the "
        "ACTUAL ACTION taken and decide if this is a deviation. "
        'Respond ONLY with valid JSON: {"is_deviation": bool, "severity": "none|low|medium|high", '
        '"explanation": "one or two sentences"}. is_deviation should include phrase \'is_deviation\' '
        "in your reasoning key."
    )
    user = (
        f"DOCUMENTED SOP STEP:\n{documented_step}\n\n"
        f"ACTUAL ACTION TAKEN:\n{actual_action}\n\n"
        "Does the actual action deviate from the documented step? Respond with the JSON object only."
    )
    raw = llm_client.generate(system, user, max_tokens=300)
    parsed = _safe_json(raw, default={
        "is_deviation": False, "severity": "none", "explanation": "Could not parse LLM output."
    })

    return {
        "is_deviation": bool(parsed.get("is_deviation", False)),
        "severity": parsed.get("severity", "none"),
        "explanation": parsed.get("explanation", ""),
        "matched_chunk_id": matched[0] if matched else None,
        "matched_chunk_text": documented_step,
        "similarity_score": matched[1] if matched else 0.0,
        "sop_id": matched[2].get("sop_id") if matched else None,
    }


def draft_sop_update(sop_title: str, current_section: str, deviation_examples: List[str]) -> dict:
    """
    Given the current SOP section text and a handful of real deviation explanations
    observed in the live event stream, draft a revised section that reflects how the
    process is actually being run -- the "evolution" step.
    """
    examples_block = "\n".join(f"- {d}" for d in deviation_examples)
    system = (
        "You are a process-improvement analyst who rewrites SOP sections so documentation "
        "matches observed reality, without compromising safety or compliance. "
        'Respond ONLY with valid JSON: {"updated_section": "revised SOP text", '
        '"change_reason": "one sentence summary of why"}.'
    )
    user = (
        f"SOP: {sop_title}\n\n"
        f"CURRENT DOCUMENTED SECTION:\n{current_section}\n\n"
        f"RECURRING DEVIATIONS OBSERVED IN LIVE OPERATIONS:\n{examples_block}\n\n"
        "Rewrite the section to reflect the real process while flagging anything that "
        "looks like a genuine compliance risk rather than a legitimate process improvement."
    )
    raw = llm_client.generate(system, user, max_tokens=700)
    parsed = _safe_json(raw, default={
        "updated_section": current_section,
        "change_reason": "Could not parse LLM output; no change applied.",
    })
    return parsed


def _safe_json(raw: str, default: dict) -> dict:
    raw = raw.strip()
    # Strip markdown code fences if the model wrapped its JSON in them.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except Exception:
        # Try to find the first {...} block heuristically.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end + 1])
            except Exception:
                pass
        return default
