"""
Seed the database + vector store with the sample SOPs.
Usage: python scripts/seed.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.config import settings          # noqa: E402
from backend.app.database import init_db, SOP, get_session  # noqa: E402
from backend.app import sop_manager               # noqa: E402

SOP_FILES = {
    "sop_incident_response.md": ("Production Incident Response", "engineering"),
    "sop_customer_onboarding.md": ("Enterprise Customer Onboarding", "customer-success"),
    "sop_equipment_maintenance.md": ("Warehouse Equipment Preventive Maintenance", "operations"),
}


def main():
    init_db()

    session = get_session()
    existing_titles = {s.title for s in session.query(SOP).all()}
    session.close()

    sop_dir = Path(settings.SAMPLE_SOP_DIR)
    created = []
    for filename, (title, domain) in SOP_FILES.items():
        if title in existing_titles:
            print(f"skip (already seeded): {title}")
            continue
        content = (sop_dir / filename).read_text()
        sop = sop_manager.create_sop(title=title, domain=domain, content=content)
        created.append(sop)
        print(f"seeded: {title}  (id={sop.id})")

    if not created:
        print("\nNothing new to seed -- database already contains these SOPs.")
    else:
        print(f"\nDone. Seeded {len(created)} SOP(s) into the DB and vector store.")


if __name__ == "__main__":
    main()
