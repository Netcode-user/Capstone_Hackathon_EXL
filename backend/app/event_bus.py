"""
Event bus abstraction so the rest of the app can `publish(topic, payload)` and
`subscribe(topic, handler)` without caring whether the backing transport is a real
Kafka cluster or an in-process mock queue. Selected via EVENT_BUS_MODE (mock|kafka).

This is what makes the "Kafka" part of the stack genuinely swappable: everything
upstream (deviation_detector, sop_manager) talks to this interface only.
"""
from __future__ import annotations

import json
import queue
import threading
from typing import Callable, Dict, List

from .config import settings

Handler = Callable[[dict], None]


class MockEventBus:
    """In-process pub/sub using a background thread per topic. No external services."""

    name = "mock (in-process)"

    def __init__(self):
        self._queues: Dict[str, "queue.Queue[dict]"] = {}
        self._handlers: Dict[str, List[Handler]] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def _get_queue(self, topic: str) -> "queue.Queue[dict]":
        with self._lock:
            if topic not in self._queues:
                self._queues[topic] = queue.Queue()
            return self._queues[topic]

    def publish(self, topic: str, payload: dict) -> None:
        self._get_queue(topic).put(payload)

    def subscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)
            if topic not in self._threads:
                t = threading.Thread(target=self._consume_loop, args=(topic,), daemon=True)
                self._threads[topic] = t
                t.start()

    def _consume_loop(self, topic: str):
        q = self._get_queue(topic)
        while True:
            payload = q.get()
            for handler in list(self._handlers.get(topic, [])):
                try:
                    handler(payload)
                except Exception as exc:  # noqa: BLE001
                    print(f"[event_bus:mock] handler error on topic={topic}: {exc}")


class KafkaEventBus:
    """Real Kafka transport via kafka-python. Requires a running broker."""

    name = "kafka"

    def __init__(self, bootstrap_servers: str):
        from kafka import KafkaProducer  # type: ignore

        self.bootstrap_servers = bootstrap_servers
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        self._consumer_threads: Dict[str, threading.Thread] = {}

    def publish(self, topic: str, payload: dict) -> None:
        self.producer.send(topic, payload)
        self.producer.flush()

    def subscribe(self, topic: str, handler: Handler) -> None:
        if topic in self._consumer_threads:
            return

        def _run():
            from kafka import KafkaConsumer  # type: ignore

            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
                group_id="processgenome-consumers",
            )
            for msg in consumer:
                try:
                    handler(msg.value)
                except Exception as exc:  # noqa: BLE001
                    print(f"[event_bus:kafka] handler error on topic={topic}: {exc}")

        t = threading.Thread(target=_run, daemon=True)
        self._consumer_threads[topic] = t
        t.start()


_bus = None


def get_event_bus():
    global _bus
    if _bus is not None:
        return _bus
    if settings.EVENT_BUS_MODE == "kafka":
        try:
            _bus = KafkaEventBus(settings.KAFKA_BOOTSTRAP_SERVERS)
            print(f"[event_bus] connected to Kafka at {settings.KAFKA_BOOTSTRAP_SERVERS}")
            return _bus
        except Exception as exc:  # noqa: BLE001
            print(f"[event_bus] Kafka unavailable ({exc}); falling back to MockEventBus")
    _bus = MockEventBus()
    print(f"[event_bus] using {_bus.name}")
    return _bus
