from contextlib import asynccontextmanager
import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, attempts, auth, dashboard, materials, results, tests
from app.core.config import settings
from app.core.media import PublicExamFiles
from app.core.middleware import (
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)


# Windows' MIME registry does not always include WebP.  Register it explicitly
# before StaticFiles creates responses for the rendered exam pages.
mimetypes.add_type("image/webp", ".webp")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.materials_storage_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Local MVP API for importing and taking official-style HSK mock tests.",
    lifespan=lifespan,
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    json_limit=settings.max_json_body_kb * 1024,
    upload_limit=settings.max_upload_mb * 1024 * 1024,
)
app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.rate_limit_enabled,
    max_clients=settings.rate_limit_max_clients,
    api_limit=settings.rate_limit_api_per_minute,
    auth_limit=settings.rate_limit_auth_per_minute,
    material_limit=settings.rate_limit_material_per_minute,
    admin_limit=settings.rate_limit_admin_per_minute,
)
# CORS wraps the request/body controls so browser clients can read bounded
# 413/429 responses instead of receiving an opaque cross-origin failure.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    # Authentication is an explicit Clerk bearer token, not a cross-site
    # cookie, so credentialed CORS is neither needed nor desirable.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "Range"],
    expose_headers=[
        "Accept-Ranges",
        "Content-Disposition",
        "Content-Length",
        "Content-Range",
        "RateLimit-Limit",
        "RateLimit-Remaining",
        "RateLimit-Reset",
        "Retry-After",
        "X-Request-ID",
    ],
    max_age=600,
)
app.add_middleware(
    SecurityHeadersMiddleware,
    production=settings.is_production,
    force_https=bool(settings.force_https),
    frontend_origins=settings.frontend_origins,
)
app.add_middleware(RequestContextMiddleware, production=settings.is_production)

app.include_router(auth.router, prefix="/api")
app.include_router(tests.router, prefix="/api")
app.include_router(attempts.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(materials.router, prefix="/api")
app.mount(
    "/media",
    PublicExamFiles(
        directory=settings.storage_root,
        check_dir=False,
        protected_paths=[
            settings.storage_root / "materials",
            settings.materials_root,
            settings.materials_storage_root,
            settings.materials_manifest_path,
        ],
    ),
    name="media",
)


@app.get("/", include_in_schema=False)
def service_root() -> dict[str, str]:
    """Provide a useful response when the Render service URL is opened directly."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "health": "/api/health",
        "docs": "/docs",
    }


@app.get("/api/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
