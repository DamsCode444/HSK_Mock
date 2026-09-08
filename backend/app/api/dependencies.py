from typing import Annotated

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.services.clerk_auth import resolve_local_user


bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate the Clerk session",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _clerk_options() -> AuthenticateRequestOptions:
    if settings.clerk_secret_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk authentication is not configured on the API",
        )

    jwt_key = (
        settings.clerk_jwt_key.get_secret_value()
        if settings.clerk_jwt_key is not None
        else None
    )
    return AuthenticateRequestOptions(
        secret_key=settings.clerk_secret_key.get_secret_value(),
        jwt_key=jwt_key,
        authorized_parties=settings.frontend_origins,
        accepts_token=["session_token"],
    )


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _credentials_error()

    try:
        request_state = authenticate_request(request, _clerk_options())
    except HTTPException:
        raise
    except Exception:
        raise _credentials_error() from None

    payload = request_state.payload or {}
    clerk_user_id = payload.get("sub")
    if (
        not request_state.is_signed_in
        or not isinstance(clerk_user_id, str)
        or not clerk_user_id.startswith("user_")
    ):
        raise _credentials_error()

    user = resolve_local_user(db, clerk_user_id)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
