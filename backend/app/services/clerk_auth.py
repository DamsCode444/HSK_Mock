from __future__ import annotations

from dataclasses import dataclass
import re

from clerk_backend_api import Clerk
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit_event
from app.core.config import settings
from app.models import User


CLERK_PASSWORD_SENTINEL = "!clerk-managed-account!"


@dataclass(frozen=True)
class ClerkIdentity:
    user_id: str
    email: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


def _secret_key() -> str:
    if settings.clerk_secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk authentication is not configured on the API",
        )
    return settings.clerk_secret_key.get_secret_value()


def _verification_status(email_address: object) -> str | None:
    verification = getattr(email_address, "verification", None)
    verification_status = getattr(verification, "status", None)
    value = getattr(verification_status, "value", verification_status)
    return str(value).lower() if value is not None else None


def fetch_clerk_identity(clerk_user_id: str) -> ClerkIdentity:
    """Load the authoritative Clerk profile when a local account is first linked."""

    try:
        with Clerk(bearer_auth=_secret_key()) as clerk:
            remote_user = clerk.users.get(user_id=clerk_user_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to load the Clerk user profile",
        ) from exc

    if remote_user.id != clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk returned an unexpected user profile",
        )
    if remote_user.banned or remote_user.locked:
        raise HTTPException(status_code=403, detail="This Clerk account is not available")

    primary_email = next(
        (
            address
            for address in remote_user.email_addresses
            if address.id == remote_user.primary_email_address_id
        ),
        None,
    )
    if primary_email is None or _verification_status(primary_email) != "verified":
        raise HTTPException(
            status_code=403,
            detail="A verified primary email address is required",
        )

    email = primary_email.email_address.strip().lower()
    if not email or len(email) > 255:
        raise HTTPException(status_code=403, detail="The Clerk email address is invalid")

    return ClerkIdentity(
        user_id=remote_user.id,
        email=email,
        username=(remote_user.username or "").strip() or None,
        first_name=(remote_user.first_name or "").strip() or None,
        last_name=(remote_user.last_name or "").strip() or None,
    )


def _username_base(identity: ClerkIdentity) -> str:
    name = identity.username
    if not name:
        full_name = "-".join(
            part for part in (identity.first_name, identity.last_name) if part
        )
        name = full_name or identity.email.split("@", 1)[0]

    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("._-").lower()
    if len(normalized) < 3:
        normalized = f"user-{identity.user_id.rsplit('_', 1)[-1][-8:].lower()}"
    return normalized[:50]


def _available_username(db: Session, identity: ClerkIdentity) -> str:
    base = _username_base(identity)
    if db.scalar(select(User.id).where(User.username == base)) is None:
        return base

    identity_suffix = re.sub(r"[^A-Za-z0-9]", "", identity.user_id)[-8:].lower()
    candidate = f"{base[: max(1, 49 - len(identity_suffix))]}-{identity_suffix}"
    if db.scalar(select(User.id).where(User.username == candidate)) is None:
        return candidate

    counter = 2
    while True:
        suffix = f"-{identity_suffix}-{counter}"
        candidate = f"{base[: 50 - len(suffix)]}{suffix}"
        if db.scalar(select(User.id).where(User.username == candidate)) is None:
            return candidate
        counter += 1


def resolve_local_user(db: Session, clerk_user_id: str) -> User:
    """Return or create the local data owner for a verified Clerk identity."""

    linked_user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if linked_user is not None:
        return linked_user

    identity = fetch_clerk_identity(clerk_user_id)
    email_owner = db.scalar(
        select(User).where(func.lower(User.email) == identity.email.lower())
    )
    if email_owner is not None:
        if email_owner.clerk_user_id not in (None, clerk_user_id):
            raise HTTPException(
                status_code=409,
                detail="That verified email is already linked to another Clerk account",
            )
        email_owner.clerk_user_id = clerk_user_id
        user = email_owner
        audit_action = "clerk_account_linked"
    else:
        user = User(
            username=_available_username(db, identity),
            email=identity.email,
            password_hash=CLERK_PASSWORD_SENTINEL,
            clerk_user_id=clerk_user_id,
            role="student",
            is_active=True,
        )
        db.add(user)
        audit_action = "clerk_account_created"

    try:
        db.commit()
        db.refresh(user)
        audit_event(audit_action, user_id=user.id, role=user.role)
        return user
    except IntegrityError as exc:
        db.rollback()
        concurrently_linked = db.scalar(
            select(User).where(User.clerk_user_id == clerk_user_id)
        )
        if concurrently_linked is not None:
            return concurrently_linked
        raise HTTPException(
            status_code=409,
            detail="The Clerk account could not be linked to a local profile",
        ) from exc
