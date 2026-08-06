"""Launch the ProcessGenome AI FastAPI app: `python backend/run.py`"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow `backend.app...` imports

import uvicorn  # noqa: E402

from backend.app.config import settings  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=False)
