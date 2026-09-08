#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services.importer import discover_bundles, import_tests  # noqa: E402
from app.services.seed import seed_demo_users  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover and import the supplied HSK PDF/audio bundles into MySQL."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--test-code", help="Import one code, for example H11329")
    selection.add_argument("--all", action="store_true", help="Import all discovered bundles")
    parser.add_argument("--force", action="store_true", help="Re-parse even if files are unchanged")
    parser.add_argument("--list", action="store_true", help="List detected bundles without importing")
    parser.add_argument("--seed-users", action="store_true", help="Create demo admin/student accounts")
    args = parser.parse_args()

    if args.list:
        rows = [
            {
                "level": bundle.level,
                "test_code": bundle.test_code,
                "exam_pdf": bundle.exam_pdf.name,
                "answer_pdf": bundle.answer_pdf.name if bundle.answer_pdf else None,
                "writing_pdf": bundle.writing_pdf.name if bundle.writing_pdf else None,
                "audio_files": len(bundle.audio_files),
            }
            for bundle in discover_bundles()
        ]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    with SessionLocal() as db:
        if args.seed_users:
            created = seed_demo_users(db)
            print(json.dumps({"seeded_users": created}, indent=2))
        results = import_tests(
            db,
            test_code=args.test_code,
            import_all=args.all,
            force=args.force,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
