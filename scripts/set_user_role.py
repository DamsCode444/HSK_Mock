#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assign a local HSK role to an existing Clerk-linked user.",
    )
    parser.add_argument("--email", required=True, help="Verified Clerk email address")
    parser.add_argument("--role", required=True, choices=("student", "admin"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    email = args.email.strip().lower()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print("No local profile matches that email. Sign in through Clerk once, then retry.")
            return 1
        if user.clerk_user_id is None:
            print("That profile is not linked to Clerk. Sign in through Clerk once, then retry.")
            return 1

        user.role = args.role
        db.commit()
        print(f"Updated {user.username} to role: {args.role}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
