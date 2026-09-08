#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.services.seed import seed_demo_users  # noqa: E402


with SessionLocal() as session:
    created = seed_demo_users(session)
    print("Created: " + (", ".join(created) if created else "no users; seed is already present"))
