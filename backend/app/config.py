"""
Central, env-driven configuration for ProcessGenome AI.
Every setting has a sane default so the app runs out of the box in "demo mode".
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # LLM
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Event bus
    EVENT_BUS_MODE: str = os.getenv("EVENT_BUS_MODE", "mock").strip().lower()  # mock | kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    TOPIC_PROCESS_EVENTS: str = os.getenv("KAFKA_TOPIC_PROCESS_EVENTS", "process-events")
    TOPIC_DEVIATIONS: str = os.getenv("KAFKA_TOPIC_DEVIATIONS", "sop-deviations")
    TOPIC_SOP_UPDATES: str = os.getenv("KAFKA_TOPIC_SOP_UPDATES", "sop-updates")

    # Embeddings / vector store
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "384"))
    VECTOR_STORE_DIR: str = os.getenv("VECTOR_STORE_DIR", str(BASE_DIR / "data" / "vector_store"))

    # Deviation -> evolution trigger
    DEVIATION_WINDOW_SIZE: int = int(os.getenv("DEVIATION_WINDOW_SIZE", "6"))
    DEVIATION_TRIGGER_COUNT: int = int(os.getenv("DEVIATION_TRIGGER_COUNT", "3"))

    # App / DB
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'processgenome.db'}")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

    SAMPLE_SOP_DIR: str = str(BASE_DIR / "data" / "sample_sops")
    SAMPLE_EVENTS_FILE: str = str(BASE_DIR / "data" / "sample_events.jsonl")


settings = Settings()

# Ensure runtime directories exist
Path(settings.VECTOR_STORE_DIR).mkdir(parents=True, exist_ok=True)
Path(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
