from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import User
from app.services.clerk_auth import CLERK_PASSWORD_SENTINEL


DEMO_USERS = (
    {
        "username": "admin",
        "email": "admin@example.invalid",
        "role": "admin",
    },
    {
        "username": "student",
        "email": "student@example.invalid",
        "role": "student",
    },
)


def seed_demo_users(db: Session) -> list[str]:
    if settings.is_production:
        raise RuntimeError("Demo users cannot be seeded in production")
    created: list[str] = []
    for item in DEMO_USERS:
        existing = db.scalar(select(User).where(User.username == item["username"]))
        if existing is not None:
            continue
        db.add(
            User(
                username=item["username"],
                email=item["email"],
                password_hash=CLERK_PASSWORD_SENTINEL,
                role=item["role"],
            )
        )
        created.append(item["username"])
    db.commit()
    return created
