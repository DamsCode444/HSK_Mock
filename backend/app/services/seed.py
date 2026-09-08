from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User


DEMO_USERS = (
    {
        "username": "admin",
        "email": "admin@gmail.com",
        "password": "Admin@123",
        "role": "admin",
    },
    {
        "username": "student",
        "email": "student@gmail.com",
        "password": "Student@123",
        "role": "student",
    },
)


def seed_demo_users(db: Session) -> list[str]:
    created: list[str] = []
    for item in DEMO_USERS:
        existing = db.scalar(select(User).where(User.username == item["username"]))
        if existing is not None:
            continue
        db.add(
            User(
                username=item["username"],
                email=item["email"],
                password_hash=hash_password(item["password"]),
                role=item["role"],
            )
        )
        created.append(item["username"])
    db.commit()
    return created
