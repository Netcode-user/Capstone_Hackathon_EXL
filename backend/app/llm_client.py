"""
LLM client abstraction.

Uses Claude (via the `anthropic` SDK) when ANTHROPIC_API_KEY is set. If it isn't
(hackathon demo without a key, offline judging, CI, etc.) falls back to a deterministic
extractive generator so every code path -- RAG chat answers, deviation analysis, SOP
draft generation -- still produces a real, useful (if less fluent) response.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .config import settings


class ClaudeClient:
    name = "anthropic-claude"

    def __init__(self, api_key: str, model: str):
        import anthropic  # type: ignore

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, system: str, user: str, max_tokens: int = 1000) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip()


class TemplateFallbackClient:
    """
    No-API-key fallback. Not a real LLM -- just enough structured text processing to
    keep the RAG / deviation-detection / SOP-drafting pipelines fully functional for a
    demo: it extracts the most relevant sentences from context and applies light
    templating, and returns well-formed JSON when JSON is requested.
    """

    name = "template-fallback (no ANTHROPIC_API_KEY set)"

    def generate(self, system: str, user: str, max_tokens: int = 1000) -> str:
        wants_json = "respond only with valid json" in system.lower() or "respond only with json" in system.lower()
        if wants_json:
            return self._fake_json(system, user)
        return self._extractive_answer(user)

    def _extractive_answer(self, user: str) -> str:
        # Pull the "Context:" block out of the prompt and return its most on-topic
        # sentences, prefixed with a note that this is a non-LLM fallback.
        context_match = re.search(r"Context:\s*(.*?)\n\nQuestion:", user, re.S)
        question_match = re.search(r"Question:\s*(.*)", user, re.S)
        context = context_match.group(1).strip() if context_match else user
        question = question_match.group(1).strip() if question_match else ""

        sentences = re.split(r"(?<=[.!?])\s+", context)
        q_words = set(re.findall(r"[a-zA-Z']+", question.lower()))
        scored = []
        for s in sentences:
            s_words = set(re.findall(r"[a-zA-Z']+", s.lower()))
            overlap = len(q_words & s_words)
            if s.strip():
                scored.append((overlap, s.strip()))
        scored.sort(key=lambda x: -x[0])
        top = [s for _, s in scored[:3]] or sentences[:3]
        return (
            "[offline fallback mode -- set ANTHROPIC_API_KEY for full Claude answers]\n\n"
            + " ".join(top)
        )

    def _fake_json(self, system: str, user: str) -> str:
        # Very small heuristic JSON generator covering the two JSON contracts this app
        # uses: deviation analysis and SOP-update drafting. See rag_pipeline.py.
        if '"is_deviation"' in system or "is_deviation" in user:
            deviation_kw = ["skip", "instead", "without", "did not", "didn't", "unauthorized", "manual override"]
            is_dev = any(kw in user.lower() for kw in deviation_kw)
            return json.dumps({
                "is_deviation": is_dev,
                "severity": "medium" if is_dev else "none",
                "explanation": "[offline fallback] Heuristic keyword match against the documented "
                                "SOP step; set ANTHROPIC_API_KEY for real semantic deviation analysis.",
            })
        # SOP draft update fallback: just append an observed-pattern note.
        return json.dumps({
            "updated_section": "[offline fallback] Based on recurring deviations, add a note to this "
                                "SOP step clarifying the exception path actually being used in practice. "
                                "Set ANTHROPIC_API_KEY for a full Claude-authored rewrite.",
            "change_reason": "Recurring deviation pattern detected in live process events.",
        })


_client: Optional[object] = None


def get_llm_client():
    global _client
    if _client is not None:
        return _client
    if settings.ANTHROPIC_API_KEY:
        try:
            _client = ClaudeClient(settings.ANTHROPIC_API_KEY, settings.CLAUDE_MODEL)
            print(f"[llm] using {ClaudeClient.name} model={settings.CLAUDE_MODEL}")
            return _client
        except Exception as exc:  # noqa: BLE001
            print(f"[llm] anthropic client init failed ({exc}); falling back to template client")
    _client = TemplateFallbackClient()
    print(f"[llm] using {_client.name}")
    return _client


def generate(system: str, user: str, max_tokens: int = 1000) -> str:
    return get_llm_client().generate(system, user, max_tokens=max_tokens)
