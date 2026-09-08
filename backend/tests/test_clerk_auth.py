from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api import dependencies
from app.db.session import Base
from app.models import User
from app.services import clerk_auth
from app.services.clerk_auth import ClerkIdentity


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_clerk_identity_links_existing_user_and_preserves_role(monkeypatch) -> None:
    with make_session() as db:
        existing = User(
            username="admin",
            email="owner@example.com",
            password_hash="legacy-hash",
            role="admin",
            is_active=True,
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id

        monkeypatch.setattr(
            clerk_auth,
            "fetch_clerk_identity",
            lambda _: ClerkIdentity(
                user_id="user_clerk_admin",
                email="OWNER@example.com",
                username="different-name",
            ),
        )

        linked = clerk_auth.resolve_local_user(db, "user_clerk_admin")

        assert linked.id == existing_id
        assert linked.clerk_user_id == "user_clerk_admin"
        assert linked.role == "admin"
        assert linked.password_hash == "legacy-hash"


def test_new_clerk_identity_creates_student_with_unique_username(monkeypatch) -> None:
    with make_session() as db:
        db.add(
            User(
                username="learner",
                email="someone-else@example.com",
                password_hash="not-used",
                role="student",
            )
        )
        db.commit()
        monkeypatch.setattr(
            clerk_auth,
            "fetch_clerk_identity",
            lambda _: ClerkIdentity(
                user_id="user_123456789",
                email="learner@example.com",
                username="learner",
            ),
        )

        created = clerk_auth.resolve_local_user(db, "user_123456789")

        assert created.role == "student"
        assert created.email == "learner@example.com"
        assert created.username != "learner"
        assert created.clerk_user_id == "user_123456789"
        assert created.password_hash == clerk_auth.CLERK_PASSWORD_SENTINEL


def test_dependency_accepts_only_verified_clerk_session_tokens(monkeypatch) -> None:
    with make_session() as db:
        local_user = User(
            username="learner",
            email="learner@example.com",
            password_hash="not-used",
            clerk_user_id="user_123",
            role="student",
            is_active=True,
        )
        db.add(local_user)
        db.commit()

        captured = {}

        def fake_authenticate(request, options):
            captured["request"] = request
            captured["options"] = options
            return SimpleNamespace(
                is_signed_in=True,
                payload={"sub": "user_123", "sid": "sess_123"},
            )

        monkeypatch.setattr(dependencies, "authenticate_request", fake_authenticate)
        monkeypatch.setattr(
            dependencies,
            "resolve_local_user",
            lambda session, clerk_user_id: local_user,
        )
        monkeypatch.setattr(
            dependencies.settings,
            "clerk_secret_key",
            SecretStr("test-secret-key"),
        )

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/auth/me",
                "headers": [(b"authorization", b"Bearer session-token")],
            }
        )
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="session-token",
        )

        result = dependencies.get_current_user(request, db, credentials)

        assert result.id == local_user.id
        assert captured["request"] is request
        assert captured["options"].accepts_token == ["session_token"]
        assert captured["options"].authorized_parties == dependencies.settings.frontend_origins


def test_dependency_rejects_non_user_subject(monkeypatch) -> None:
    with make_session() as db:
        monkeypatch.setattr(
            dependencies.settings,
            "clerk_secret_key",
            SecretStr("test-secret-key"),
        )
        monkeypatch.setattr(
            dependencies,
            "authenticate_request",
            lambda *_: SimpleNamespace(
                is_signed_in=True,
                payload={"sub": "machine_123"},
            ),
        )
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/auth/me",
                "headers": [(b"authorization", b"Bearer session-token")],
            }
        )
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="session-token",
        )

        try:
            dependencies.get_current_user(request, db, credentials)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("A non-user Clerk subject must be rejected")
