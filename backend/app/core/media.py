from pathlib import Path

from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.services.object_storage import ObjectStorageError, exam_object_key, presigned_object_url


class PublicExamFiles(StaticFiles):
    """Keep private study files outside the legacy exam-media mount."""

    def __init__(self, *, protected_paths: list[Path], **kwargs):
        super().__init__(**kwargs)
        self.protected_paths = tuple(path.resolve() for path in protected_paths)

    def lookup_path(self, path: str):
        full_path, file_stat = super().lookup_path(path)
        if file_stat is None:
            return full_path, file_stat
        resolved = Path(full_path).resolve()
        if any(resolved == root or root in resolved.parents for root in self.protected_paths):
            return "", None
        return full_path, file_stat

    async def check_config(self) -> None:
        if not settings.b2_enabled:
            await super().check_config()

    async def get_response(self, path: str, scope):
        if not settings.b2_enabled:
            return await super().get_response(path, scope)
        if scope["method"] not in {"GET", "HEAD"}:
            raise HTTPException(status_code=405)
        try:
            key = exam_object_key(path)
        except ValueError as exc:
            raise HTTPException(status_code=404) from exc
        try:
            url = presigned_object_url(key, method=scope["method"])
        except ObjectStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return RedirectResponse(
            url,
            status_code=307,
            headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
        )
