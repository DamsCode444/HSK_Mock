from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser
from app.models import User
from app.schemas.auth import UserOut


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _password_auth_retired() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Password authentication has moved to Clerk. Use the web sign-in or sign-up flow.",
    )


@router.post("/register", status_code=status.HTTP_410_GONE, deprecated=True)
def register() -> None:
    _password_auth_retired()


@router.post("/login", status_code=status.HTTP_410_GONE, deprecated=True)
def login() -> None:
    _password_auth_retired()


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> User:
    return current_user
