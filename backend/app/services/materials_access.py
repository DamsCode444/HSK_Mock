from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from jwt import InvalidTokenError

from app.core.config import settings


ResourceType = Literal["asset", "bundle"]
Disposition = Literal["inline", "attachment"]


def create_material_access_token(
    *,
    user_id: int,
    resource_type: ResourceType,
    resource_id: str,
    disposition: Disposition,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.material_access_ttl_seconds)
    payload = {
        "sub": str(user_id),
        "type": "material_access",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "disposition": disposition,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        settings.material_signing_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_material_access_token(
    token: str,
    *,
    resource_type: ResourceType,
    resource_id: str,
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.material_signing_secret,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": [
                    "sub",
                    "type",
                    "resource_type",
                    "resource_id",
                    "disposition",
                    "exp",
                ]
            },
        )
    except InvalidTokenError as exc:
        raise ValueError("Invalid or expired material access link") from exc
    if payload.get("type") != "material_access":
        raise ValueError("Invalid material access link type")
    if payload.get("resource_type") != resource_type or payload.get("resource_id") != resource_id:
        raise ValueError("Material access link does not match this resource")
    if payload.get("disposition") not in {"inline", "attachment"}:
        raise ValueError("Invalid material access disposition")
    try:
        int(str(payload["sub"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid material access subject") from exc
    return payload


def expires_at_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
