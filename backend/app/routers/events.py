from fastapi import APIRouter

from ..config import settings
from ..database import DeviationEvent, get_session
from ..deviation_detector import handle_process_event
from ..event_bus import get_event_bus
from ..models import DeviationOut, ProcessEventIn

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/simulate")
def simulate_event(event: ProcessEventIn):
    """
    Publish a process event onto the event bus (Kafka or mock) exactly the way a real
    ERP/MES/ticketing system integration would, then return the immediate handler result
    for convenience in the demo UI (in real Kafka mode this still also flows through the
    async consumer -- this just also runs it inline so the dashboard gets instant feedback).
    """
    bus = get_event_bus()
    bus.publish(settings.TOPIC_PROCESS_EVENTS, event.model_dump())
    result = handle_process_event(event.model_dump())
    return result


@router.get("/deviations", response_model=list[DeviationOut])
def list_deviations(limit: int = 25):
    session = get_session()
    try:
        rows = (
            session.query(DeviationEvent)
            .order_by(DeviationEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return rows
    finally:
        session.close()
