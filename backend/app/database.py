"""SQLite persistence via SQLAlchemy for SOPs, versions, and deviation events."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, Boolean, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class SOP(Base):
    __tablename__ = "sops"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    domain = Column(String, default="general")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    active_version_id = Column(String, nullable=True)

    versions = relationship("SOPVersion", back_populates="sop", order_by="SOPVersion.version_number")


class SOPVersion(Base):
    __tablename__ = "sop_versions"

    id = Column(String, primary_key=True)
    sop_id = Column(String, ForeignKey("sops.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, default="active")  # active | proposed | deprecated | rejected
    change_reason = Column(Text, default="Initial version")
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    sop = relationship("SOP", back_populates="versions")


class ProcessEvent(Base):
    __tablename__ = "process_events"

    id = Column(String, primary_key=True)
    sop_id = Column(String, ForeignKey("sops.id"), nullable=True)
    process_id = Column(String)
    actor = Column(String)
    step_description = Column(Text)   # what the SOP says should happen (query used for retrieval)
    actual_action = Column(Text)      # what actually happened, from the live event stream
    source_topic = Column(String, default="process-events")
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class DeviationEvent(Base):
    __tablename__ = "deviation_events"

    id = Column(String, primary_key=True)
    process_event_id = Column(String, ForeignKey("process_events.id"))
    sop_id = Column(String, ForeignKey("sops.id"))
    matched_chunk_id = Column(String, nullable=True)
    matched_chunk_text = Column(Text, nullable=True)
    is_deviation = Column(Boolean, default=False)
    severity = Column(String, default="none")  # none | low | medium | high
    explanation = Column(Text)
    similarity_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
