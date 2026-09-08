"""Private Backblaze B2 objects, without downloading large assets to the API disk."""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import PurePosixPath
from threading import RLock
from types import SimpleNamespace
from typing import Any, Iterator
from urllib.parse import quote

from app.core.config import settings


class ObjectStorageError(RuntimeError):
    """Safe public error that never includes credentials or signed URLs."""


@lru_cache(maxsize=1)
def b2_client():
    import boto3
    from botocore.config import Config

    if not settings.b2_key_id or not settings.b2_application_key:
        raise ObjectStorageError("Cloud file storage credentials are not configured")
    return boto3.client(
        "s3",
        endpoint_url=settings.b2_endpoint_url,
        region_name=settings.b2_region,
        aws_access_key_id=settings.b2_key_id.get_secret_value(),
        aws_secret_access_key=settings.b2_application_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=10,
            read_timeout=60,
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )


def safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {".", "..", ""} for part in normalized.split("/"))
        or ":" in normalized
        or any(ord(char) < 32 for char in normalized)
    ):
        raise ValueError("Unsafe cloud file path")
    return path.as_posix()


def material_object_key(asset: dict[str, Any]) -> str:
    prefixes = {"source": "HSK_Materials", "storage": "storage/materials"}
    prefix = prefixes.get(asset.get("root"))
    if prefix is None:
        raise ValueError("Unknown material storage root")
    return f"{prefix}/{safe_relative_path(str(asset.get('path', '')))}"


def exam_object_key(path: str) -> str:
    relative = safe_relative_path(path)
    parts = PurePosixPath(relative).parts
    allowed_suffixes = {".pdf", ".mp3", ".webp", ".png", ".jpg", ".jpeg", ".wav", ".ogg"}
    if (
        len(parts) < 3
        or not re.fullmatch(r"HSK[1-6]", parts[0])
        or any(part.startswith(".") for part in parts)
        or PurePosixPath(relative).suffix.lower() not in allowed_suffixes
    ):
        raise ValueError("Not a public exam file")
    return f"storage/{relative}"


def content_disposition(disposition: str, filename: str) -> str:
    if disposition not in {"inline", "attachment"}:
        raise ValueError("Invalid content disposition")
    cleaned = "".join(char for char in filename if ord(char) >= 32 and ord(char) != 127)
    cleaned = cleaned.replace("\\", "/").rsplit("/", 1)[-1] or "download"
    fallback = re.sub(r'[^A-Za-z0-9._() -]', "_", cleaned)
    return f'{disposition}; filename="{fallback}"; filename*=UTF-8\'\'{quote(cleaned, safe="")}'


def presigned_object_url(
    key: str,
    *,
    disposition: str = "inline",
    filename: str | None = None,
    media_type: str | None = None,
    method: str = "GET",
) -> str:
    key = safe_relative_path(key)
    params = {"Bucket": settings.b2_bucket_name, "Key": key}
    if method == "GET":
        if filename:
            params["ResponseContentDisposition"] = content_disposition(disposition, filename)
        if media_type:
            params["ResponseContentType"] = media_type
        params["ResponseCacheControl"] = "private, no-store"
    try:
        return b2_client().generate_presigned_url(
            "head_object" if method == "HEAD" else "get_object",
            Params=params,
            ExpiresIn=settings.b2_signed_url_ttl_seconds,
            HttpMethod=method,
        )
    except ObjectStorageError:
        raise
    except Exception as exc:
        raise ObjectStorageError("Cloud file access is temporarily unavailable") from exc


_manifest_lock = RLock()
_manifest_cache: tuple[tuple[str, str], float, dict[str, Any]] | None = None


def clear_cloud_manifest_cache() -> None:
    global _manifest_cache
    with _manifest_lock:
        _manifest_cache = None


def cloud_materials_manifest() -> dict[str, Any]:
    """Cache only the small catalog. Media files stay entirely in the bucket."""
    global _manifest_cache
    identity = (settings.b2_endpoint_url, settings.b2_bucket_name)
    with _manifest_lock:
        now = time.monotonic()
        if _manifest_cache and _manifest_cache[0] == identity and now < _manifest_cache[1]:
            return _manifest_cache[2]
        try:
            response = b2_client().get_object(
                Bucket=settings.b2_bucket_name,
                Key="storage/materials/manifest.json",
            )
            body = response["Body"]
            try:
                # Reject an accidental huge object instead of exhausting service memory.
                raw = body.read(16 * 1024 * 1024 + 1)
            finally:
                body.close()
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("Manifest exceeds its size limit")
            manifest = json.loads(raw)
            if not isinstance(manifest, dict):
                raise ValueError("Invalid manifest")
        except Exception as exc:
            raise ObjectStorageError("The cloud study catalog is unavailable; verify its upload and storage configuration") from exc
        _manifest_cache = (identity, now + 60, manifest)
        return manifest


class RemoteMaterialFile:
    """The read-only subset of Path needed by the bounded-memory ZIP writer."""

    def __init__(self, asset: dict[str, Any]):
        self.key = material_object_key(asset)
        self.size = int(asset["size_bytes"])
        if self.size < 0:
            raise ValueError("Invalid material size")

    def stat(self) -> SimpleNamespace:
        # Object sizes were validated by the importer/upload manifest. The ZIP
        # generator also checks every actual byte count as it streams the file.
        return SimpleNamespace(st_size=self.size, st_mtime=315532800)

    @contextmanager
    def open(self, mode: str) -> Iterator[Any]:
        if mode != "rb":
            raise ValueError("Cloud files are read-only")
        try:
            response = b2_client().get_object(Bucket=settings.b2_bucket_name, Key=self.key)
        except Exception as exc:
            raise ObjectStorageError("A cloud download file is unavailable; please retry") from exc
        body = response["Body"]
        try:
            if int(response["ContentLength"]) != self.size:
                raise ObjectStorageError("A cloud download file changed; re-index the study library")
            yield body
        finally:
            body.close()
