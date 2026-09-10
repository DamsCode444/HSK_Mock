"""Small dependency-free ASGI security controls for a single API instance."""

from __future__ import annotations

import json
import logging
import math
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Awaitable, Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.audit import audit_event


logger = logging.getLogger("hsk.api")


def _headers(scope: Scope) -> dict[bytes, bytes]:
    return {key.lower(): value for key, value in scope.get("headers", [])}


async def _json_response(
    send: Send,
    status: int,
    detail: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode("utf-8")
    response_headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]
    if headers:
        response_headers.extend(headers)
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})


class RequestContextMiddleware:
    """Assign request IDs, emit safe error logs, and hide production trace details."""

    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        self.app = app
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = secrets.token_hex(16)
        scope.setdefault("state", {})["request_id"] = request_id
        started = False
        status_code = 500
        started_at = time.monotonic()

        async def send_with_request_id(message: Message) -> None:
            nonlocal started, status_code
            if message["type"] == "http.response.start":
                started = True
                status_code = int(message["status"])
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("ascii"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
            logger.exception(
                "Unhandled API error request_id=%s method=%s path=%s elapsed_ms=%s",
                request_id,
                scope.get("method"),
                scope.get("path"),
                elapsed_ms,
            )
            if not self.production or started:
                raise
            await _json_response(
                send,
                500,
                "An unexpected server error occurred",
                headers=[(b"x-request-id", request_id.encode("ascii"))],
            )
            return

        if status_code >= 500:
            audit_event(
                "api_server_error",
                request_id=request_id,
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
            )


class SecurityHeadersMiddleware:
    """Apply headers that are safe for JSON plus cross-origin PDF/audio viewing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        production: bool,
        force_https: bool,
        frontend_origins: list[str],
    ) -> None:
        self.app = app
        self.production = production
        self.force_https = force_https
        self.frame_ancestors = " ".join(frontend_origins) or "'none'"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_headers = _headers(scope)
        forwarded_proto = request_headers.get(b"x-forwarded-proto", b"").decode(
            "latin-1"
        ).split(",", 1)[0].strip().lower()
        scheme = forwarded_proto if forwarded_proto in {"http", "https"} else scope.get("scheme")
        if self.force_https and scheme != "https":
            await _json_response(send, 400, "HTTPS is required")
            return

        path = str(scope.get("path", ""))
        embeddable = path.startswith("/media/") or path.startswith(
            "/api/materials/content/"
        )
        csp = (
            f"default-src 'none'; base-uri 'none'; form-action 'none'; "
            f"frame-ancestors {self.frame_ancestors}"
            if embeddable
            else "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {key.lower() for key, _ in headers}
                additions = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"x-permitted-cross-domain-policies", b"none"),
                    (b"content-security-policy", csp.encode("latin-1")),
                ]
                if not embeddable:
                    additions.append((b"x-frame-options", b"DENY"))
                if self.production and scheme == "https":
                    additions.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                if (
                    b"authorization" in request_headers
                    or path.startswith("/api/auth/")
                    or "/content/" in path
                ) and b"cache-control" not in existing:
                    additions.append((b"cache-control", b"no-store"))
                headers.extend((key, value) for key, value in additions if key not in existing)
            await send(message)

        await self.app(scope, receive, add_headers)


class RequestBodyLimitExceeded(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Bound JSON and admin-upload request bodies, including chunked requests."""

    def __init__(self, app: ASGIApp, *, json_limit: int, upload_limit: int) -> None:
        self.app = app
        self.json_limit = json_limit
        # Multipart headers and boundaries need a small allowance in addition
        # to the configured ZIP payload limit. The endpoint still enforces the
        # exact archive byte limit while it copies the UploadFile.
        self.upload_limit = upload_limit + 2 * 1024 * 1024

    def _limit_for(self, scope: Scope) -> int | None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            return None
        path = str(scope.get("path", ""))
        if path == "/api/admin/import/upload":
            return self.upload_limit
        if path.startswith("/api/"):
            return self.json_limit
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await _json_response(send, 400, "Invalid Content-Length header")
                return
            if declared < 0:
                await _json_response(send, 400, "Invalid Content-Length header")
                return
            if declared > limit:
                await _json_response(send, 413, "Request body is too large")
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyLimitExceeded
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyLimitExceeded:
            # In normal operation this is caught before a response begins: the
            # request parser consumes the complete body before invoking a route.
            await _json_response(send, 413, "Request body is too large")


@dataclass
class _Window:
    started_at: float
    count: int


class InMemoryRateLimiter:
    """Fixed-window limiter with a strict bound on tracked client buckets."""

    def __init__(
        self,
        *,
        max_clients: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_clients = max_clients
        self.window_seconds = window_seconds
        self.clock = clock
        self._windows: OrderedDict[tuple[str, str], _Window] = OrderedDict()
        # ASGI workers use one event loop per process, so no blocking lock is
        # needed around this synchronous (non-awaiting) critical section.

    def check(self, bucket: str, client: str, limit: int) -> tuple[bool, int, int]:
        now = self.clock()
        key = (bucket, client)
        window = self._windows.get(key)
        if window is None or now - window.started_at >= self.window_seconds:
            window = _Window(started_at=now, count=0)
            self._windows[key] = window
        window.count += 1
        self._windows.move_to_end(key)
        while len(self._windows) > self.max_clients:
            self._windows.popitem(last=False)
        remaining = max(0, limit - window.count)
        reset = max(1, math.ceil(window.started_at + self.window_seconds - now))
        return window.count <= limit, remaining, reset


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        max_clients: int,
        api_limit: int,
        auth_limit: int,
        material_limit: int,
        admin_limit: int,
        limiter: InMemoryRateLimiter | None = None,
    ) -> None:
        self.app = app
        self.enabled = enabled
        self.limits = {
            "api": api_limit,
            "auth": auth_limit,
            "material": material_limit,
            "admin": admin_limit,
        }
        self.limiter = limiter or InMemoryRateLimiter(max_clients=max_clients)

    def _policy(self, scope: Scope) -> tuple[str, int] | None:
        path = str(scope.get("path", ""))
        if not path.startswith("/api/") or path == "/api/health":
            return None
        if path.startswith("/api/auth/"):
            bucket = "auth"
        elif path.startswith("/api/admin/"):
            bucket = "admin"
        elif (
            path.startswith("/api/materials/content/")
            or path.startswith("/api/materials/bundle-content/")
            or path.endswith("/access")
        ):
            bucket = "material"
        else:
            bucket = "api"
        return bucket, self.limits[bucket]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return
        policy = self._policy(scope)
        if policy is None:
            await self.app(scope, receive, send)
            return
        bucket, limit = policy
        client_info = scope.get("client")
        client = str(client_info[0]) if client_info else "unknown"
        allowed, remaining, reset = self.limiter.check(bucket, client, limit)
        rate_headers = [
            (b"ratelimit-limit", str(limit).encode("ascii")),
            (b"ratelimit-remaining", str(remaining).encode("ascii")),
            (b"ratelimit-reset", str(reset).encode("ascii")),
        ]
        if not allowed:
            audit_event("rate_limit_exceeded", bucket=bucket, client=client)
            await _json_response(
                send,
                429,
                "Too many requests; please retry shortly",
                headers=[*rate_headers, (b"retry-after", str(reset).encode("ascii"))],
            )
            return

        async def add_rate_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(rate_headers)
            await send(message)

        await self.app(scope, receive, add_rate_headers)
