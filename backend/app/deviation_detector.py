"""
The consumer-side brain of ProcessGenome AI.

For every process event that arrives on the `process-events` topic (real Kafka or the
mock bus):
  1. Persist the raw event.
  2. RAG-retrieve the SOP chunk that documents this step, and ask the LLM whether the
     actual action deviates from it (rag_pipeline.analyze_deviation).
  3. Persist the deviation verdict, and publish it onto `sop-deviations`.
  4. If a SOP has racked up >= DEVIATION_TRIGGER_COUNT deviations in its last
     DEVIATION_WINDOW_SIZE events, trigger sop_manager.propose_update(...) to draft a
     new SOP version and publish it onto `sop-updates`.
"""
from __future__ import annotations

import uuid

from .config import settings
from .database import DeviationEvent, ProcessEvent, get_session
from .event_bus import get_event_bus
from .rag_pipeline import analyze_deviation
from .sop_manager import propose_update, recent_deviation_explanations


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def handle_process_event(payload: dict) -> dict:
    """Core handler, also callable directly (e.g. from the /events/simulate endpoint)
    so behavior is identical whether an event arrives via Kafka, the mock bus, or the
    REST API."""
    session = get_session()
    try:
        event_id = _new_id("evt")
        event = ProcessEvent(
            id=event_id,
            sop_id=payload.get("sop_id"),
            process_id=payload.get("process_id", "unknown"),
            actor=payload.get("actor", "unknown"),
            step_description=payload.get("step_description", ""),
            actual_action=payload.get("actual_action", ""),
        )
        session.add(event)
        session.commit()

        result = analyze_deviation(
            step_description=event.step_description,
            actual_action=event.actual_action,
        )
        sop_id = result.get("sop_id") or payload.get("sop_id")

        deviation = DeviationEvent(
            id=_new_id("dev"),
            process_event_id=event_id,
            sop_id=sop_id,
            matched_chunk_id=result.get("matched_chunk_id"),
            matched_chunk_text=result.get("matched_chunk_text"),
            is_deviation=result.get("is_deviation", False),
            severity=result.get("severity", "none"),
            explanation=result.get("explanation", ""),
            similarity_score=result.get("similarity_score", 0.0),
        )
        session.add(deviation)
        session.commit()
        session.refresh(deviation)

        bus = get_event_bus()
        bus.publish(settings.TOPIC_DEVIATIONS, {
            "deviation_id": deviation.id,
            "sop_id": sop_id,
            "is_deviation": deviation.is_deviation,
            "severity": deviation.severity,
            "explanation": deviation.explanation,
        })

        proposed_version = None
        if deviation.is_deviation and sop_id:
            proposed_version = _maybe_trigger_evolution(sop_id)

        return {
            "event_id": event_id,
            "deviation": {
                "is_deviation": deviation.is_deviation,
                "severity": deviation.severity,
                "explanation": deviation.explanation,
                "similarity_score": deviation.similarity_score,
            },
            "proposed_version_id": proposed_version.id if proposed_version else None,
        }
    finally:
        session.close()


def _maybe_trigger_evolution(sop_id: str):
    session = get_session()
    try:
        recent = (
            session.query(DeviationEvent)
            .filter(DeviationEvent.sop_id == sop_id)
            .order_by(DeviationEvent.created_at.desc())
            .limit(settings.DEVIATION_WINDOW_SIZE)
            .all()
        )
        deviation_count = sum(1 for r in recent if r.is_deviation)
        if deviation_count < settings.DEVIATION_TRIGGER_COUNT:
            return None
    finally:
        session.close()

    explanations = recent_deviation_explanations(sop_id, limit=settings.DEVIATION_TRIGGER_COUNT)
    if not explanations:
        return None

    new_version = propose_update(sop_id, explanations)
    if new_version:
        bus = get_event_bus()
        bus.publish(settings.TOPIC_SOP_UPDATES, {
            "sop_id": sop_id,
            "proposed_version_id": new_version.id,
            "version_number": new_version.version_number,
            "change_reason": new_version.change_reason,
        })
    return new_version


def start_consumer():
    """Subscribe handle_process_event to the process-events topic on whichever bus is active."""
    bus = get_event_bus()
    bus.subscribe(settings.TOPIC_PROCESS_EVENTS, handle_process_event)
    print(f"[deviation_detector] subscribed to '{settings.TOPIC_PROCESS_EVENTS}' via {bus.name}")
