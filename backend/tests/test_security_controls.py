from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.middleware import (
    InMemoryRateLimiter,
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.uploads import validate_uploaded_media, validate_zip_signature


def _settings(**overrides: object) -> Settings:
    """Build settings without reading the developer's local .env file."""
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://app.example.com", ["https://app.example.com"]),
        (
            "https://app.example.com/, https://admin.example.com",
            ["https://app.example.com", "https://admin.example.com"],
        ),
        (
            '["https://APP.example.com/", "https://app.example.com"]',
            ["https://app.example.com"],
        ),
    ],
)
def test_frontend_origins_accept_render_friendly_formats(
    raw: str, expected: list[str]
) -> None:
    settings = _settings(frontend_origins=raw)

    assert settings.frontend_origins == expected


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:password@app.example.com",
        "https://app.example.com/login",
        "https://app.example.com?next=admin",
        "https://app.example.com;script-src https:",
        "https://bad host.example.com",
        "javascript:alert(1)",
    ],
)
def test_frontend_origins_reject_non_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="scheme, hostname, and optional port"):
        _settings(frontend_origins=origin)


def test_production_settings_fail_closed_with_insecure_defaults() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _settings(
            environment="production",
            frontend_origins="http://app.example.com",
        )

    message = str(exc_info.value)
    assert "HSK_DEBUG must be false" in message
    assert "HSK_FRONTEND_ORIGINS must use HTTPS" in message
    assert "HSK_JWT_SECRET" in message
    assert "HSK_MATERIAL_ACCESS_SECRET" in message
    assert "CLERK_SECRET_KEY" in message


def test_production_settings_accept_separate_secrets_and_enable_https() -> None:
    settings = _settings(
        environment="production",
        debug=False,
        frontend_origins="https://app.example.com",
        jwt_secret="jwt-secret-that-is-at-least-thirty-two-characters",
        material_access_secret="material-secret-that-is-at-least-thirty-two-chars",
        clerk_secret_key="sk_live_example",
        database_url="mysql+pymysql://hsk_app:strong-password@app-db:3306/hsk_mock",
    )

    assert settings.is_production is True
    assert settings.force_https is True
    assert settings.material_signing_secret != settings.jwt_secret


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+pymysql://root:strong-password@app-db:3306/hsk_mock",
        "mysql+pymysql://hsk_app:change_me@app-db:3306/hsk_mock",
        "mysql+pymysql://hsk_app@app-db:3306/hsk_mock",
    ],
)
def test_production_mysql_rejects_privileged_or_default_credentials(
    database_url: str,
) -> None:
    with pytest.raises(ValidationError, match="HSK_DATABASE_URL"):
        _settings(
            environment="production",
            debug=False,
            frontend_origins="https://app.example.com",
            jwt_secret="jwt-secret-that-is-at-least-thirty-two-characters",
            material_access_secret="material-secret-that-is-at-least-thirty-two-chars",
            clerk_secret_key="sk_live_example",
            database_url=database_url,
        )


def _app_with_route(path: str = "/api/ping") -> FastAPI:
    app = FastAPI()

    @app.get(path)
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_security_headers_are_added_to_api_responses() -> None:
    app = _app_with_route()
    app.add_middleware(
        SecurityHeadersMiddleware,
        production=True,
        force_https=True,
        frontend_origins=["https://app.example.com"],
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/ping", headers={"authorization": "Bearer test"})

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["strict-transport-security"].startswith("max-age=31536000")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_media_security_headers_allow_only_configured_frontend_to_embed() -> None:
    app = _app_with_route("/api/materials/content/example")
    app.add_middleware(
        SecurityHeadersMiddleware,
        production=True,
        force_https=True,
        frontend_origins=["https://app.example.com"],
    )

    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/materials/content/example")

    assert response.status_code == 200
    assert "x-frame-options" not in response.headers
    assert (
        "frame-ancestors https://app.example.com"
        in response.headers["content-security-policy"]
    )
    assert response.headers["cache-control"] == "no-store"


def test_https_enforcement_honors_forwarded_protocol() -> None:
    app = _app_with_route()
    app.add_middleware(
        SecurityHeadersMiddleware,
        production=True,
        force_https=True,
        frontend_origins=["https://app.example.com"],
    )

    with TestClient(app, base_url="http://testserver") as client:
        rejected = client.get("/api/ping")
        accepted = client.get("/api/ping", headers={"x-forwarded-proto": "https"})

    assert rejected.status_code == 400
    assert rejected.json() == {"detail": "HTTPS is required"}
    assert accepted.status_code == 200


def test_request_body_limit_rejects_declared_oversized_json() -> None:
    app = FastAPI()

    @app.post("/api/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"size": len(body)}

    app.add_middleware(RequestBodyLimitMiddleware, json_limit=16, upload_limit=32)

    with TestClient(app) as client:
        response = client.post("/api/echo", content=b"x" * 17)

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large"}
    assert response.headers["cache-control"] == "no-store"


def test_rate_limit_is_bucketed_and_health_check_is_exempt() -> None:
    now = [100.0]
    clock: Callable[[], float] = lambda: now[0]
    limiter = InMemoryRateLimiter(max_clients=100, window_seconds=60, clock=clock)
    app = _app_with_route()

    @app.get("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        max_clients=100,
        api_limit=2,
        auth_limit=1,
        material_limit=1,
        admin_limit=1,
        limiter=limiter,
    )

    with TestClient(app) as client:
        first = client.get("/api/ping")
        second = client.get("/api/ping")
        rejected = client.get("/api/ping")
        health = [client.get("/api/health") for _ in range(3)]

    assert first.headers["ratelimit-remaining"] == "1"
    assert second.headers["ratelimit-remaining"] == "0"
    assert rejected.status_code == 429
    assert rejected.headers["retry-after"] == "60"
    assert rejected.json() == {"detail": "Too many requests; please retry shortly"}
    assert all(response.status_code == 200 for response in health)
    assert all("ratelimit-limit" not in response.headers for response in health)


def test_request_context_returns_generic_production_error_and_request_id() -> None:
    app = FastAPI()

    @app.get("/api/fail")
    async def fail() -> None:
        raise RuntimeError("database password must never reach the response")

    app.add_middleware(RequestContextMiddleware, production=True)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/fail")

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected server error occurred"}
    assert len(response.headers["x-request-id"]) == 32
    assert "password" not in response.text


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("lesson.pdf", b"comment\n%PDF-1.7\nbody"),
        ("lesson.mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00"),
        ("lesson.mp3", b"\xff\xfb\x90\x64" + b"\x00" * 64),
    ],
)
def test_uploaded_media_accepts_supported_content(
    tmp_path: Path, name: str, content: bytes
) -> None:
    path = tmp_path / name
    path.write_bytes(content)

    validate_uploaded_media(path)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("lesson.pdf", b"this is not a PDF"),
        ("lesson.mp3", b"this is not an MP3"),
        ("lesson.txt", b"%PDF-1.7"),
        ("lesson.mp3", b"junk\xff\xe0more junk"),
    ],
)
def test_uploaded_media_rejects_mismatched_or_malformed_content(
    tmp_path: Path, name: str, content: bytes
) -> None:
    path = tmp_path / name
    path.write_bytes(content)

    with pytest.raises(ValueError, match="does not match its extension"):
        validate_uploaded_media(path)


def test_zip_signature_validation_uses_file_content(tmp_path: Path) -> None:
    valid = tmp_path / "valid.zip"
    invalid = tmp_path / "invalid.zip"
    valid.write_bytes(b"PK\x03\x04archive")
    invalid.write_bytes(b"not a zip")

    validate_zip_signature(valid)
    with pytest.raises(ValueError, match="not a valid ZIP archive"):
        validate_zip_signature(invalid)
