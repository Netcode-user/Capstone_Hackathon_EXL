"""
Replays data/sample_events.jsonl onto the process-events topic, one event every couple
of seconds, so you can watch the dashboard's live deviation feed populate and, once
enough deviations pile up for a SOP (see DEVIATION_TRIGGER_COUNT), watch a proposed new
SOP version appear for review.

Usage:
  python scripts/simulate_stream.py                # uses whatever EVENT_BUS_MODE is set (default: mock)
  python scripts/simulate_stream.py --kafka         # force real Kafka producer
  python scripts/simulate_stream.py --delay 0.5     # change the pace
  python scripts/simulate_stream.py --http          # POST to the running API instead of the bus directly
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.config import settings  # noqa: E402


def load_events():
    with open(settings.SAMPLE_EVENTS_FILE) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_via_bus(events, delay: float):
    from backend.app.deviation_detector import start_consumer, handle_process_event
    from backend.app.database import init_db
    from backend.app.event_bus import get_event_bus

    init_db()
    start_consumer()
    bus = get_event_bus()

    for i, event in enumerate(events, 1):
        print(f"[{i}/{len(events)}] publishing process_id={event['process_id']} "
              f"actor={event['actor']} -> {event['step_description'][:60]}...")
        bus.publish(settings.TOPIC_PROCESS_EVENTS, event)
        # Directly invoke too, so this script is useful even before main.py's own
        # subscription races the mock queue (both paths are idempotent-safe to run once).
        result = handle_process_event(event) if bus.name.startswith("mock") else None
        if result:
            dev = result["deviation"]
            tag = "DEVIATION" if dev["is_deviation"] else "compliant"
            print(f"    -> {tag} (severity={dev['severity']}): {dev['explanation'][:100]}")
            if result.get("proposed_version_id"):
                print(f"    !! SOP evolution triggered -> proposed version "
                      f"{result['proposed_version_id']} awaiting approval")
        time.sleep(delay)


def run_via_http(events, delay: float, base_url: str):
    import urllib.request

    for i, event in enumerate(events, 1):
        req = urllib.request.Request(
            f"{base_url}/events/simulate",
            data=json.dumps(event).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        dev = result["deviation"]
        tag = "DEVIATION" if dev["is_deviation"] else "compliant"
        print(f"[{i}/{len(events)}] {event['process_id']} -> {tag} ({dev['severity']}): "
              f"{dev['explanation'][:100]}")
        if result.get("proposed_version_id"):
            print(f"    !! SOP evolution triggered -> proposed version {result['proposed_version_id']}")
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kafka", action="store_true", help="force EVENT_BUS_MODE=kafka for this run")
    parser.add_argument("--http", action="store_true", help="POST events to a running API instead")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    if args.kafka:
        import os
        os.environ["EVENT_BUS_MODE"] = "kafka"

    events = load_events()
    print(f"Loaded {len(events)} sample process events.\n")

    if args.http:
        run_via_http(events, args.delay, args.base_url)
    else:
        run_via_bus(events, args.delay)


if __name__ == "__main__":
    main()
