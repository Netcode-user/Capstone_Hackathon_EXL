"""Pydantic schemas used by the API layer (kept separate from the SQLAlchemy ORM models
in database.py so request/response shapes can evolve independently of storage)."""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from pydantic import BaseModel, Field


class SOPCreateRequest(BaseModel):
    title: str
    domain: str = "general"
    content: str


class SOPVersionOut(BaseModel):
    id: str
    version_number: int
    status: str
    change_reason: str
    created_at: dt.datetime
    content: str

    class Config:
        from_attributes = True


class SOPOut(BaseModel):
    id: str
    title: str
    domain: str
    active_version_id: Optional[str]
    created_at: dt.datetime
    versions: List[SOPVersionOut] = []

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    query: str
    top_k: int = 4


class RetrievedChunk(BaseModel):
    chunk_id: str
    sop_id: str
    sop_title: str
    score: float
    text: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[RetrievedChunk]


class ProcessEventIn(BaseModel):
    process_id: str
    sop_id: Optional[str] = None
    actor: str = "unknown"
    step_description: str = Field(..., description="What the SOP says should happen / the step being executed")
    actual_action: str = Field(..., description="What actually happened in the real process")


class DeviationOut(BaseModel):
    id: str
    process_event_id: str
    sop_id: Optional[str]
    is_deviation: bool
    severity: str
    explanation: str
    similarity_score: float
    matched_chunk_text: Optional[str]
    created_at: dt.datetime

    class Config:
        from_attributes = True


class ApproveVersionRequest(BaseModel):
    version_id: str
