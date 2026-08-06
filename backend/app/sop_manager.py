"""
SOP lifecycle management: create/chunk/embed SOPs, version them, and evolve them.

Chunking strategy: split markdown SOPs on `##` headers so each chunk is one coherent
"step" or section -- this keeps retrieval precise (a query about "return shipment"
matches the one section about return shipments, not the whole document).
"""
from __future__ import annotations

import re
import uuid
from typing import List

from .database import DeviationEvent, SOP, SOPVersion, get_session
from .embeddings import embed_texts
from .rag_pipeline import draft_sop_update
from .vector_store import get_vector_store


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def chunk_markdown(content: str) -> List[str]:
    """Split on level-2 markdown headers ('## Step ...'); fall back to paragraphs."""
    parts = re.split(r"\n(?=##\s)", content.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in content.split("\n\n") if p.strip()]
    return parts or [content.strip()]


def _index_version(sop_id: str, sop_title: str, version_id: str, content: str):
    """Embed every chunk of a SOP version and add it to the vector store."""
    chunks = chunk_markdown(content)
    vectors = embed_texts(chunks)
    ids = [f"{version_id}::chunk{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "sop_id": sop_id,
            "sop_title": sop_title,
            "version_id": version_id,
            "chunk_index": i,
            "text": chunk,
        }
        for i, chunk in enumerate(chunks)
    ]
    store = get_vector_store("sops")
    store.add(ids, vectors, metadatas)
    return ids


def create_sop(title: str, domain: str, content: str) -> SOP:
    session = get_session()
    try:
        sop_id = _new_id("sop")
        version_id = _new_id("ver")

        sop = SOP(id=sop_id, title=title, domain=domain, active_version_id=version_id)
        version = SOPVersion(
            id=version_id, sop_id=sop_id, version_number=1, content=content,
            status="active", change_reason="Initial version",
        )
        session.add(sop)
        session.add(version)
        session.commit()

        _index_version(sop_id, title, version_id, content)
        session.refresh(sop)
        return sop
    finally:
        session.close()


def list_sops() -> List[SOP]:
    session = get_session()
    try:
        return session.query(SOP).all()
    finally:
        session.close()


def get_sop(sop_id: str) -> SOP | None:
    session = get_session()
    try:
        return session.query(SOP).filter(SOP.id == sop_id).first()
    finally:
        session.close()


def get_active_version(sop_id: str) -> SOPVersion | None:
    session = get_session()
    try:
        sop = session.query(SOP).filter(SOP.id == sop_id).first()
        if not sop or not sop.active_version_id:
            return None
        return session.query(SOPVersion).filter(SOPVersion.id == sop.active_version_id).first()
    finally:
        session.close()


def propose_update(sop_id: str, deviation_explanations: List[str]) -> SOPVersion | None:
    """
    Called by the deviation detector once enough recurring deviations pile up for a SOP.
    Drafts a revised version of the *currently active* SOP content via RAG + LLM and
    stores it with status='proposed' (a human approves it via /sops/{id}/approve).
    """
    session = get_session()
    try:
        sop = session.query(SOP).filter(SOP.id == sop_id).first()
        if not sop:
            return None
        active = session.query(SOPVersion).filter(SOPVersion.id == sop.active_version_id).first()
        if not active:
            return None

        draft = draft_sop_update(sop.title, active.content, deviation_explanations)
        next_version_number = max(v.version_number for v in sop.versions) + 1

        new_version = SOPVersion(
            id=_new_id("ver"),
            sop_id=sop_id,
            version_number=next_version_number,
            content=draft.get("updated_section", active.content),
            status="proposed",
            change_reason=draft.get("change_reason", "Recurring deviation pattern detected."),
        )
        session.add(new_version)
        session.commit()
        session.refresh(new_version)
        return new_version
    finally:
        session.close()


def approve_version(sop_id: str, version_id: str) -> SOPVersion | None:
    """Promote a proposed version to active: re-embed it and deprecate the old chunks."""
    session = get_session()
    try:
        sop = session.query(SOP).filter(SOP.id == sop_id).first()
        version = session.query(SOPVersion).filter(SOPVersion.id == version_id).first()
        if not sop or not version:
            return None

        old_active_id = sop.active_version_id
        version.status = "active"
        sop.active_version_id = version.id
        if old_active_id and old_active_id != version.id:
            old = session.query(SOPVersion).filter(SOPVersion.id == old_active_id).first()
            if old:
                old.status = "deprecated"
        session.commit()

        _index_version(sop.id, sop.title, version.id, version.content)
        session.refresh(version)
        return version
    finally:
        session.close()


def reject_version(sop_id: str, version_id: str) -> SOPVersion | None:
    session = get_session()
    try:
        version = session.query(SOPVersion).filter(
            SOPVersion.id == version_id, SOPVersion.sop_id == sop_id
        ).first()
        if not version:
            return None
        version.status = "rejected"
        session.commit()
        session.refresh(version)
        return version
    finally:
        session.close()


def recent_deviation_explanations(sop_id: str, limit: int = 10) -> List[str]:
    session = get_session()
    try:
        rows = (
            session.query(DeviationEvent)
            .filter(DeviationEvent.sop_id == sop_id, DeviationEvent.is_deviation.is_(True))
            .order_by(DeviationEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return [r.explanation for r in rows]
    finally:
        session.close()
