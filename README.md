# ProcessGenome AI: Dynamic SOP Evolution

A hackathon-ready, **fully working** reference implementation of a system that turns
Standard Operating Procedures (SOPs) into a living, self-updating knowledge base.

Live process events stream in (via **Kafka** or an in-process mock bus), get compared
against the *currently documented* SOP steps using **Retrieval-Augmented Generation
(RAG)**, and when the system notices a recurring pattern of deviation it **drafts a new
SOP version with an LLM**, versions it, re-embeds it into the **vector store**, and pushes
it live — a "genome" that mutates as the real process evolves.

## Core concepts implemented

| Concept | Where |
|---|---|
| **Embeddings** | `backend/app/embeddings.py` — pluggable: uses `sentence-transformers` if installed, otherwise a deterministic hashing-vectorizer fallback (pure NumPy, no internet/model download needed) |
| **Vector store** | `backend/app/vector_store.py` — pluggable: uses `faiss` if installed, otherwise a pure NumPy cosine-similarity store, persisted to disk as JSON/NPY |
| **RAG** | `backend/app/rag_pipeline.py` — retrieves relevant SOP chunks, builds a grounded prompt, calls the LLM, returns cited answer |
| **LLM** | `backend/app/llm_client.py` — calls Claude via the `anthropic` SDK (`ANTHROPIC_API_KEY`); if no key is set, falls back to a deterministic extractive summarizer so the whole app still runs end-to-end with zero external dependencies for a demo |
| **Kafka** | `backend/app/event_bus.py`, `backend/app/kafka_producer.py`, `backend/app/kafka_consumer.py` — real Kafka topics (`process-events`, `sop-deviations`, `sop-updates`) via `kafka-python`, wired up in `docker-compose.yml`. A `MockEventBus` (same interface, in-process queue) lets you demo everything without spinning up a broker |

## Architecture

```
                     ┌────────────────────┐
 Process systems ───▶│  Kafka topic:       │
 (ERP/MES/ticketing) │  process-events     │
                     └─────────┬───────────┘
                               │ consumed by
                               ▼
                     ┌────────────────────┐        ┌──────────────┐
                     │ Deviation Detector  │──RAG──▶│ Vector Store │
                     │ (backend consumer)  │◀───────│ (SOP chunks) │
                     └─────────┬───────────┘        └──────────────┘
                               │ produces               ▲
                               ▼                         │ re-embed on
                     ┌────────────────────┐              │ new version
 Kafka topic: ◀──────│ SOP Manager        │──────────────┘
 sop-deviations       │ - versions SOPs    │
                      │ - drafts updates   │──LLM (Claude)──▶ proposed SOP v(n+1)
                      │   via RAG + LLM    │
                      └─────────┬──────────┘
                                │ produces
                                ▼
                     Kafka topic: sop-updates
                                │
                                ▼
                     ┌────────────────────┐
                     │ FastAPI REST API    │◀── Dashboard / Chat (frontend/index.html)
                     └────────────────────┘
```

## Quick start (demo mode — no Kafka, no API key needed)

```bash
cd processgenome-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt         # minimal core installs fine offline-friendly
cp .env.example .env                    # EVENT_BUS_MODE=mock by default

# 1. Seed sample SOPs into the DB + vector store
python scripts/seed.py

# 2. Start the API + background deviation-detector consumer
python backend/run.py
# -> serves REST API + dashboard at http://localhost:8000

# 3. In another terminal, simulate a stream of real-world process events
python scripts/simulate_stream.py
```

Open **http://localhost:8000** for the dashboard: chat with your SOPs (RAG), watch the
live deviation feed, and see proposed SOP version diffs appear as the simulated stream runs.

## Running with real Kafka + real Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export EVENT_BUS_MODE=kafka
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

docker compose up -d          # spins up Zookeeper + Kafka + the backend
python scripts/simulate_stream.py --kafka
```

## Why it still "just works" without any API keys or internet

Every heavy dependency is optional and guarded:

- No `sentence-transformers` → falls back to a 384-dim hashing embedder (deterministic,
  no download).
- No `faiss` → falls back to a NumPy brute-force cosine store (fine at hackathon scale).
- No `ANTHROPIC_API_KEY` → falls back to an extractive/template response generator so
  RAG answers and SOP-update drafts still get produced, just less fluent.
- No Kafka broker → `EVENT_BUS_MODE=mock` uses an in-process pub/sub queue with the
  *exact same interface* as the Kafka implementation, so swapping in real Kafka later is
  a one-line env var change, not a code change.

## Repo layout

```
processgenome-ai/
├── backend/app/
│   ├── main.py              FastAPI app + startup consumer thread
│   ├── config.py            env-driven settings
│   ├── database.py          SQLite via SQLAlchemy
│   ├── models.py            ORM + Pydantic schemas
│   ├── embeddings.py        embedding provider (pluggable)
│   ├── vector_store.py      vector store (pluggable)
│   ├── llm_client.py        Claude client (pluggable)
│   ├── rag_pipeline.py      retrieval + generation
│   ├── sop_manager.py       SOP CRUD, chunking, versioning, evolution
│   ├── deviation_detector.py per-event RAG comparison against SOP
│   ├── event_bus.py         Mock/Kafka bus abstraction
│   ├── kafka_producer.py    real Kafka producer wrapper
│   ├── kafka_consumer.py    real Kafka consumer wrapper
│   └── routers/              sop.py, chat.py, events.py, dashboard.py
├── data/sample_sops/         3 example markdown SOPs
├── data/sample_events.jsonl  simulated stream of process events (incl. deviations)
├── scripts/seed.py           load sample SOPs
├── scripts/simulate_stream.py replay events onto the bus
├── frontend/index.html       single-page dashboard (vanilla JS, no build step)
├── docker-compose.yml        Kafka + Zookeeper + backend
└── requirements.txt
```
