from contextlib import asynccontextmanager
import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, attempts, auth, dashboard, materials, results, tests
from app.core.config import settings
from app.core.media import PublicExamFiles


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
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/api/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
