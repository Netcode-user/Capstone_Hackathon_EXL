# Adding Chunking to ProcessGenome AI ? Integration Guide

This adds a **standalone, pluggable Chunking module** to the existing
Embeddings ? Vector Store ? RAG ? LLM ? Kafka pipeline in
`Netcode-user/Capstone_Hackathon_EXL` (ProcessGenome AI).

## 1. Where Chunking fits in the pipeline

```
Raw SOP (markdown)
      ?
      ?
???????????????????   NEW: backend/app/chunking.py
?   CHUNKING       ?   splits SOP into step-sized, overlapping chunks
????????????????????   (markdown-header-aware by default)
         ?
???????????????????
?   EMBEDDINGS     ?   backend/app/embeddings.py ? embeds each chunk
????????????????????
         ?
???????????????????
?  VECTOR STORE    ?   backend/app/vector_store.py ? stores chunk vectors
????????????????????
         ?
???????????????????
?      RAG         ?   backend/app/rag_pipeline.py ? retrieves top-k chunks,
????????????????????   builds grounded prompt
         ?
???????????????????
?      LLM         ?   backend/app/llm_client.py ? Claude / fallback
???????????????????
```

Kafka (`event_bus.py`) is unaffected ? it streams *process events*, not
SOP text, so chunking only sits on the SOP ingestion side (`sop_manager.py`
and `scripts/seed.py`), not the event stream side.

## 2. Files to add

Copy these two files into the cloned repo, preserving the paths:

```
backend/app/chunking.py         <- new pluggable chunker
scripts/test_chunking.py        <- standalone test against data/sample_sops/*.md
```

## 3. Wire it into `sop_manager.py`

The README states `sop_manager.py` already does "SOP CRUD, chunking,
versioning, evolution" ? meaning chunking today is done **inline** inside
that file. Replace the inline logic with a call into the new module.

Find wherever `sop_manager.py` currently splits SOP text before calling
`embeddings.py` (likely a small function like `_split_into_chunks` or
similar, called from `create_sop()` / `update_sop()`), and replace it with:

```python
# top of backend/app/sop_manager.py
from .chunking import chunk_text
from .config import settings  # already imported in this style elsewhere

...

def _prepare_chunks(sop_id: str, version: int, sop_markdown: str):
    """Chunk an SOP document before embedding + vector store insertion."""
    chunks = chunk_text(
        sop_markdown,
        strategy=settings.CHUNK_STRATEGY,      # "markdown_aware" default
        chunk_size=settings.CHUNK_SIZE,        # ~400 tokens default
        chunk_overlap=settings.CHUNK_OVERLAP,  # ~60 tokens default
        base_metadata={"sop_id": sop_id, "version": version},
    )
    return chunks  # list[Chunk] -> feed .text into embeddings.embed(), .metadata into vector_store
```

Then wherever the old code called `embeddings.embed(raw_text)` on the
*whole document*, call it per-chunk instead:

```python
chunks = _prepare_chunks(sop.id, sop.version, sop.content)
for c in chunks:
    vector = embeddings.embed(c.text)
    vector_store.add(
        vector=vector,
        text=c.text,
        metadata=c.metadata,   # carries sop_id, version, section heading
    )
```

This means RAG citations (`rag_pipeline.py`) now resolve to a specific
**SOP step/section**, not just "the SOP" ? a direct quality improvement
for the "cited answer" feature already promised in the README, and it
also gives the Deviation Detector (`deviation_detector.py`) a tighter,
step-level comparison target instead of comparing against a whole
uncut SOP document.

## 4. Add chunking settings to `config.py`

Add these next to the existing `EVENT_BUS_MODE`, `KAFKA_BOOTSTRAP_SERVERS`, etc:

```python
# backend/app/config.py
CHUNK_STRATEGY: str = "markdown_aware"   # "fixed" | "recursive" | "markdown_aware"
CHUNK_SIZE: int = 400                    # tokens (or chars if strategy="fixed")
CHUNK_OVERLAP: int = 60
```

And in `.env.example` / `sample.env`:

```
CHUNK_STRATEGY=markdown_aware
CHUNK_SIZE=400
CHUNK_OVERLAP=60
```

## 5. Re-seed after adding chunking

Since `scripts/seed.py` calls `sop_manager` to load the 3 sample SOPs,
once you've wired step 3 in, just re-run seeding ? no other script changes
needed; the new chunking happens transparently underneath.

---

# Full Step-by-Step: Setup & Run (with Chunking included)

## Step 1 ? Clone and enter the repo
```bash
git clone https://github.com/Netcode-user/Capstone_Hackathon_EXL.git processgenome-ai
cd processgenome-ai
```

## Step 2 ? Add the chunking files
Copy `chunking.py` into `backend/app/` and `test_chunking.py` into `scripts/`,
then make the edits from sections 3?4 above to `sop_manager.py` and `config.py`.

## Step 3 ? Create virtual environment & install deps
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional (better chunk-size accuracy, matches OpenAI/Claude-style tokenization):
```bash
pip install tiktoken
```

## Step 4 ? Configure environment
```bash
cp sample.env .env
# Edit .env:
#   EVENT_BUS_MODE=mock          (demo mode; no Kafka needed)
#   CHUNK_STRATEGY=markdown_aware
#   CHUNK_SIZE=400
#   CHUNK_OVERLAP=60
#   ANTHROPIC_API_KEY=           (optional ? leave blank to use fallback LLM)
```

## Step 5 ? Sanity-check chunking alone (fast, no server needed)
```bash
python scripts/test_chunking.py --strategy markdown_aware --chunk-size 400 --overlap 60
```
You should see each sample SOP broken into per-step chunks with token counts.

## Step 6 ? Seed the sample SOPs (now chunked) into the DB + vector store
```bash
python scripts/seed.py
```

## Step 7 ? Start the API + background deviation-detector consumer
```bash
python backend/run.py
```
Serves the REST API + dashboard at **http://localhost:8000**

## Step 8 ? Simulate a live event stream (separate terminal)
```bash
source .venv/bin/activate
python scripts/simulate_stream.py
```

## Step 9 ? Open the dashboard
Go to **http://localhost:8000** ? chat with the SOPs (RAG over your new
chunks), watch the live deviation feed, and see proposed SOP version diffs
as the simulated stream runs.

---

## Optional: Run with real Kafka + real Claude LLM
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export EVENT_BUS_MODE=kafka
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

docker compose up -d              # spins up Zookeeper + Kafka + backend
python scripts/simulate_stream.py --kafka
```

---

## Why "markdown_aware" is the right default strategy for this project
SOPs in `data/sample_sops/*.md` are structured documents (headings, numbered
steps). Splitting on markdown headers first means:
- Each chunk = one SOP step ? RAG retrieval and citations map to a single
  actionable step, not an arbitrary slice of text.
- The **Deviation Detector** compares a live process event against one
  clean step at a time, improving match precision.
- Falls back to recursive token-based splitting automatically for any
  section that's unusually long (e.g. a giant "Detailed Steps" block),
  so nothing ever exceeds your embedding model's context limit.

Switch to `"recursive"` or `"fixed"` via `CHUNK_STRATEGY` in `.env` if your
own SOPs aren't well-structured markdown.
