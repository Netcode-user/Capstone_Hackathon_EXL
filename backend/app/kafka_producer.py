"""
Standalone Kafka producer helper -- used by scripts/simulate_stream.py when run with
`--kafka`, and useful as a copy-paste starting point for wiring in a real ERP/MES/
ticketing system that should publish process events onto the `process-events` topic.

For the mock-mode demo path, use event_bus.get_event_bus().publish(...) instead --
this module is specifically for the real-Kafka path.
"""
from __future__ import annotations

import json

from .config import settings


def make_producer():
    from kafka import KafkaProducer  # type: ignore

    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def publish_process_event(producer, event: dict, topic: str | None = None) -> None:
    topic = topic or settings.TOPIC_PROCESS_EVENTS
    producer.send(topic, event)
    producer.flush()
