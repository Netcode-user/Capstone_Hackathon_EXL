"""
Standalone Kafka consumer helper. The app itself wires up consumption through
event_bus.get_event_bus().subscribe(...) (see main.py's startup hook), which routes to
this same underlying kafka-python KafkaConsumer when EVENT_BUS_MODE=kafka. This module
is kept as a minimal, dependency-isolated example for anyone wiring ProcessGenome AI's
deviation detector into an existing Kafka deployment outside of this FastAPI process
(e.g. as a separate worker / Kafka Streams-style microservice).
"""
from __future__ import annotations

import json

from .config import settings


def make_consumer(topic: str | None = None, group_id: str = "processgenome-consumers"):
    from kafka import KafkaConsumer  # type: ignore

    topic = topic or settings.TOPIC_PROCESS_EVENTS
    return KafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        group_id=group_id,
    )


def run_forever(handler, topic: str | None = None):
    """Blocking loop: pulls messages off `topic` and calls handler(payload) on each."""
    consumer = make_consumer(topic)
    for msg in consumer:
        handler(msg.value)
