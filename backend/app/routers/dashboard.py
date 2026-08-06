from fastapi import APIRouter

from ..database import DeviationEvent, ProcessEvent, SOP, SOPVersion, get_session
from ..embeddings import get_embedder
from ..event_bus import get_event_bus
from ..llm_client import get_llm_client
from ..vector_store import get_vector_store

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats():
    session = get_session()
    try:
        num_sops = session.query(SOP).count()
        num_versions = session.query(SOPVersion).count()
        num_proposed = session.query(SOPVersion).filter(SOPVersion.status == "proposed").count()
        num_events = session.query(ProcessEvent).count()
        num_deviations = session.query(DeviationEvent).filter(DeviationEvent.is_deviation.is_(True)).count()
    finally:
        session.close()

    store = get_vector_store("sops")
    return {
        "sops": num_sops,
        "sop_versions": num_versions,
        "proposed_versions_awaiting_review": num_proposed,
        "process_events_ingested": num_events,
        "deviations_detected": num_deviations,
        "vector_store_chunks": store.count(),
        "vector_store_backend": getattr(store, "backend_name", "unknown"),
        "embedding_provider": get_embedder().name,
        "llm_provider": get_llm_client().name,
        "event_bus": get_event_bus().name,
    }
