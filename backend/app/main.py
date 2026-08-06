from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .deviation_detector import start_consumer
from .routers import chat, dashboard, events, sop

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(
    title="ProcessGenome AI",
    description="Dynamic SOP Evolution: RAG + LLM + Vector Store + Kafka",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sop.router)
app.include_router(chat.router)
app.include_router(events.router)
app.include_router(dashboard.router)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
def on_startup():
    init_db()
    start_consumer()
    print("[main] ProcessGenome AI backend ready.")


@app.get("/")
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "ProcessGenome AI backend is running. See /docs for the API."}


@app.get("/health")
def health():
    return {"status": "ok"}
