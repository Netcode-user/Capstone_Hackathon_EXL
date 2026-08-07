"""
chunking.py ? Chunking module for ProcessGenome AI

Splits a raw SOP markdown document into overlapping, retrieval-sized chunks
BEFORE they go to embeddings.py -> vector_store.py.

Follows the same "pluggable / dependency-optional" pattern as the rest of
the project:
  - No tokenizer installed?  -> falls back to whitespace-word counting.
  - tiktoken installed?      -> uses real GPT-style token counts for more
                                 accurate chunk sizing.

Public API
----------
    chunk_text(text, strategy="recursive", chunk_size=400, chunk_overlap=60) -> List[Chunk]

Chunk is a small dataclass: {text, index, start_char, end_char, token_count, metadata}

Three strategies are implemented:
  1. "fixed"      - naive fixed-size character windows with overlap.
                    Fast, predictable, good baseline for a demo.
  2. "recursive"  - LangChain-style recursive splitting: tries to split on
                    paragraph breaks first, then sentences, then words,
                    then characters, only falling through to a smaller
                    separator when a piece is still too big. This keeps
                    headings/sections/bullet points intact where possible
                    -- important for SOP docs, which are heavily structured
                    (numbered steps, headings, etc).
  3. "markdown_aware" - SOP-specific: splits on markdown headers (#, ##, ###)
                    first so each chunk stays inside one SOP *step/section*,
                    then recursively sub-splits any section that's still
                    too long. This is the recommended default for SOPs
                    since a "deviation" should map cleanly back to one step.

Every chunk carries the SOP's existing metadata (sop_id, version, source
section heading) so the vector store / RAG citation can point back to the
exact SOP step, matching the project's "cited answer" design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# ---------------------------------------------------------------------------
# Optional tokenizer (mirrors embeddings.py's "use it if installed" pattern)
# ---------------------------------------------------------------------------
try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(s: str) -> int:
        return len(_ENC.encode(s))

except ImportError:  # pragma: no cover - offline/demo-friendly fallback
    def _count_tokens(s: str) -> int:
        # Cheap approximation: ~0.75 tokens per word for English text.
        # Good enough for chunk-size budgeting without any dependency.
        words = s.split()
        return max(1, int(len(words) / 0.75))


@dataclass
class Chunk:
    text: str
    index: int
    start_char: int
    end_char: int
    token_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "index": self.index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Strategy 1: fixed-size window
# ---------------------------------------------------------------------------
def _chunk_fixed(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    step = chunk_size - chunk_overlap
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i:i + chunk_size])
        i += step
    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Strategy 2: recursive character/paragraph/sentence splitter
# ---------------------------------------------------------------------------
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_on(text: str, sep: str) -> List[str]:
    if sep == "":
        return list(text)
    return text.split(sep)


def _recursive_split(text: str, max_tokens: int, separators: List[str]) -> List[str]:
    """Recursively split `text` until every piece is <= max_tokens."""
    if _count_tokens(text) <= max_tokens or not separators:
        return [text]

    sep, rest_seps = separators[0], separators[1:]
    parts = _split_on(text, sep)

    pieces: List[str] = []
    buffer = ""
    for part in parts:
        candidate = (buffer + sep + part) if buffer else part
        if _count_tokens(candidate) <= max_tokens:
            buffer = candidate
        else:
            if buffer:
                pieces.append(buffer)
            # part itself might still be too big -> recurse with smaller separator
            if _count_tokens(part) > max_tokens:
                pieces.extend(_recursive_split(part, max_tokens, rest_seps))
                buffer = ""
            else:
                buffer = part
    if buffer:
        pieces.append(buffer)
    return pieces


def _add_overlap(pieces: List[str], chunk_overlap_tokens: int) -> List[str]:
    """Stitch a small tail of each piece onto the front of the next piece,
    so retrieval doesn't lose context at chunk boundaries."""
    if chunk_overlap_tokens <= 0 or len(pieces) <= 1:
        return pieces
    out = [pieces[0]]
    for i in range(1, len(pieces)):
        prev_words = pieces[i - 1].split()
        overlap_words = prev_words[-chunk_overlap_tokens:] if len(prev_words) > chunk_overlap_tokens else prev_words
        overlap_text = " ".join(overlap_words)
        out.append((overlap_text + " " + pieces[i]).strip())
    return out


def _chunk_recursive(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    # chunk_size/overlap given in *approx tokens* for this strategy
    pieces = _recursive_split(text, max_tokens=chunk_size, separators=_SEPARATORS)
    pieces = [p.strip() for p in pieces if p.strip()]
    pieces = _add_overlap(pieces, chunk_overlap_tokens=chunk_overlap)
    return pieces


# ---------------------------------------------------------------------------
# Strategy 3: markdown-header-aware (recommended default for SOPs)
# ---------------------------------------------------------------------------
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _split_by_headers(text: str):
    """Yield (heading_path, section_text) tuples, splitting on markdown headers."""
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        yield ("", text)
        return

    # content before first header (if any)
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()
        if preamble:
            yield ("", preamble)

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        yield (heading, section_text)


def _chunk_markdown_aware(text: str, chunk_size: int, chunk_overlap: int) -> List[Dict[str, Any]]:
    """Returns list of {text, heading} ? sections stay intact when small,
    and get recursively sub-split when a single section is too long
    (e.g. a very long 'Detailed Steps' section)."""
    out = []
    for heading, section in _split_by_headers(text):
        if _count_tokens(section) <= chunk_size:
            out.append({"text": section, "heading": heading})
        else:
            sub_pieces = _chunk_recursive(section, chunk_size, chunk_overlap)
            for sp in sub_pieces:
                out.append({"text": sp, "heading": heading})
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def chunk_text(
    text: str,
    strategy: str = "markdown_aware",
    chunk_size: int = 400,
    chunk_overlap: int = 60,
    base_metadata: Optional[Dict[str, Any]] = None,
) -> List[Chunk]:
    """
    Split `text` into Chunk objects ready for embeddings.py.

    strategy: "fixed" | "recursive" | "markdown_aware" (default)
    chunk_size: for "fixed" this is CHARACTERS; for "recursive"/"markdown_aware"
                this is approx TOKENS (~words / 0.75).
    chunk_overlap: same unit as chunk_size, for the chosen strategy.
    base_metadata: dict merged into every chunk's metadata (e.g. sop_id, version).
    """
    base_metadata = base_metadata or {}
    text = text.strip()
    if not text:
        return []

    results: List[Chunk] = []

    if strategy == "fixed":
        raw_pieces = _chunk_fixed(text, chunk_size, chunk_overlap)
        cursor = 0
        for idx, piece in enumerate(raw_pieces):
            start = text.find(piece, cursor)
            start = start if start != -1 else cursor
            end = start + len(piece)
            cursor = end
            results.append(Chunk(
                text=piece, index=idx, start_char=start, end_char=end,
                token_count=_count_tokens(piece),
                metadata={**base_metadata, "strategy": "fixed"},
            ))

    elif strategy == "recursive":
        raw_pieces = _chunk_recursive(text, chunk_size, chunk_overlap)
        cursor = 0
        for idx, piece in enumerate(raw_pieces):
            start = text.find(piece[:30], cursor) if piece else cursor
            start = start if start != -1 else cursor
            end = start + len(piece)
            cursor = max(cursor, end)
            results.append(Chunk(
                text=piece, index=idx, start_char=start, end_char=end,
                token_count=_count_tokens(piece),
                metadata={**base_metadata, "strategy": "recursive"},
            ))

    elif strategy == "markdown_aware":
        raw = _chunk_markdown_aware(text, chunk_size, chunk_overlap)
        cursor = 0
        for idx, item in enumerate(raw):
            piece = item["text"]
            start = text.find(piece[:30], cursor) if piece else cursor
            start = start if start != -1 else cursor
            end = start + len(piece)
            cursor = max(cursor, end)
            results.append(Chunk(
                text=piece, index=idx, start_char=start, end_char=end,
                token_count=_count_tokens(piece),
                metadata={**base_metadata, "strategy": "markdown_aware", "section": item["heading"]},
            ))

    else:
        raise ValueError(f"Unknown chunking strategy: {strategy!r}")

    return results


# ---------------------------------------------------------------------------
# Quick manual test: `python backend/app/chunking.py`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_sop = """# Incident Escalation SOP

## Step 1: Detect
Monitor the ticketing queue every 15 minutes. Flag any ticket tagged
'P1' or 'P2' that has been unassigned for more than 10 minutes.

## Step 2: Notify
Page the on-call engineer via PagerDuty. If no ack within 5 minutes,
escalate to the secondary on-call and notify the team lead on Slack.

## Step 3: Resolve
Engineer investigates root cause, applies fix or rollback, and updates
the ticket status. Postmortem required for all P1 incidents within 48h.
"""
    for strat in ("fixed", "recursive", "markdown_aware"):
        print(f"\n=== strategy: {strat} ===")
        chunks = chunk_text(
            sample_sop,
            strategy=strat,
            chunk_size=120 if strat != "fixed" else 300,
            chunk_overlap=20 if strat != "fixed" else 40,
            base_metadata={"sop_id": "sop-001", "version": 1},
        )
        for c in chunks:
            print(f"[{c.index}] ({c.token_count} tok) {c.metadata.get('section','')!r} -> {c.text[:60]!r}...")
