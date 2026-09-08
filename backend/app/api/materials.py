from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

from app.api.dependencies import CurrentUser, DbSession
from app.core.config import settings
from app.models import User
from app.schemas.materials import MaterialAccessGrant, MaterialAccessRequest
from app.services.materials_access import (
    create_material_access_token,
    decode_material_access_token,
    expires_at_iso,
)
from app.services.materials_catalog import (
    MaterialSourceError,
    MaterialsNotIndexedError,
    ZIP_MIME,
    material_asset,
    material_bundle,
    material_catalog,
    material_collection,
    resolve_material_path,
)
from app.services.streaming_zip import iter_stored_zip, stored_zip_size
from app.services.object_storage import (
    ObjectStorageError,
    RemoteMaterialFile,
    content_disposition,
    material_object_key,
    presigned_object_url,
)


router = APIRouter(prefix="/materials", tags=["Study materials"])


def _catalog_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


def _load_asset(asset_id: str) -> dict:
    try:
        asset = material_asset(asset_id)
    except MaterialsNotIndexedError as exc:
        raise _catalog_error(exc) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="Study material not found")
    return asset


def _load_bundle(bundle_id: str) -> dict:
    try:
        bundle = material_bundle(bundle_id)
    except MaterialsNotIndexedError as exc:
        raise _catalog_error(exc) from exc
    if bundle is None:
        raise HTTPException(status_code=404, detail="Study-material download not found")
    return bundle


def _validate_grant_user(db: DbSession, payload: dict) -> User:
    try:
        user_id = int(str(payload["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid material access link") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Material access user no longer exists")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")
    return user


def _decode_grant(token: str, resource_type: str, resource_id: str, db: DbSession) -> dict:
    try:
        payload = decode_material_access_token(
            token,
            resource_type=resource_type,  # type: ignore[arg-type]
            resource_id=resource_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _validate_grant_user(db, payload)
    return payload


def _file_response(
    asset: dict,
    *,
    disposition: str,
    filename: str | None = None,
) -> Response:
    if settings.b2_enabled:
        try:
            url = presigned_object_url(
                material_object_key(asset),
                disposition=disposition,
                filename=filename or asset["filename"],
                media_type=asset["media_type"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Study-material storage is invalid") from exc
        except ObjectStorageError as exc:
            raise _catalog_error(exc) from exc
        return RedirectResponse(
            url,
            status_code=307,
            headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
        )
    try:
        path = resolve_material_path(asset)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Study-material file is missing") from exc
    except MaterialSourceError as exc:
        raise HTTPException(status_code=500, detail="Study-material storage is invalid") from exc
    return FileResponse(
        path,
        media_type=asset["media_type"],
        filename=filename or asset["filename"],
        content_disposition_type=disposition,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/catalog")
def get_material_catalog() -> dict:
    try:
        return material_catalog()
    except MaterialsNotIndexedError as exc:
        raise _catalog_error(exc) from exc


@router.get("/collections/{slug}")
def get_material_collection(slug: str) -> dict:
    try:
        collection = material_collection(slug)
    except MaterialsNotIndexedError as exc:
        raise _catalog_error(exc) from exc
    if collection is None:
        raise HTTPException(status_code=404, detail="Study-material collection not found")
    return collection


@router.get("/covers/{asset_id}")
def get_material_cover(asset_id: str) -> Response:
    asset = _load_asset(asset_id)
    if asset.get("kind") != "cover":
        raise HTTPException(status_code=404, detail="Study-material cover not found")
    response = _file_response(asset, disposition="inline")
    if not settings.b2_enabled:
        response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
    return response


@router.post("/assets/{asset_id}/access", response_model=MaterialAccessGrant)
def grant_asset_access(
    asset_id: str,
    request: MaterialAccessRequest,
    current_user: CurrentUser,
) -> MaterialAccessGrant:
    asset = _load_asset(asset_id)
    if asset.get("kind") not in {"document", "audio_track"}:
        raise HTTPException(status_code=404, detail="Study material not available through this endpoint")
    token, expires_at = create_material_access_token(
        user_id=current_user.id,
        resource_type="asset",
        resource_id=asset_id,
        disposition=request.disposition,
    )
    return MaterialAccessGrant(
        url=f"/api/materials/content/{quote(asset_id, safe='')}?token={quote(token, safe='')}",
        expires_at=expires_at_iso(expires_at),
        filename=asset["filename"],
        media_type=asset["media_type"],
        size_bytes=asset["size_bytes"],
    )


@router.get("/content/{asset_id}")
def serve_material_asset(
    asset_id: str,
    db: DbSession,
    token: str = Query(..., min_length=20),
) -> Response:
    asset = _load_asset(asset_id)
    payload = _decode_grant(token, "asset", asset_id, db)
    return _file_response(asset, disposition=payload["disposition"])


@router.post("/bundles/{bundle_id}/access", response_model=MaterialAccessGrant)
def grant_bundle_access(bundle_id: str, current_user: CurrentUser) -> MaterialAccessGrant:
    bundle = _load_bundle(bundle_id)
    token, expires_at = create_material_access_token(
        user_id=current_user.id,
        resource_type="bundle",
        resource_id=bundle_id,
        disposition="attachment",
    )
    return MaterialAccessGrant(
        url=f"/api/materials/bundle-content/{quote(bundle_id, safe='')}?token={quote(token, safe='')}",
        expires_at=expires_at_iso(expires_at),
        filename=bundle["filename"],
        media_type=bundle["media_type"],
        size_bytes=bundle["size_bytes"],
    )


@router.get("/bundle-content/{bundle_id}")
def serve_material_bundle(
    bundle_id: str,
    db: DbSession,
    token: str = Query(..., min_length=20),
):
    bundle = _load_bundle(bundle_id)
    _decode_grant(token, "bundle", bundle_id, db)

    prebuilt_id = bundle.get("prebuilt_asset_id")
    if prebuilt_id:
        prebuilt = _load_asset(prebuilt_id)
        return _file_response(
            prebuilt,
            disposition="attachment",
            filename=bundle["filename"],
        )

    entries = []
    try:
        for item in bundle["items"]:
            asset = _load_asset(item["asset_id"])
            source = RemoteMaterialFile(asset) if settings.b2_enabled else resolve_material_path(asset)
            entries.append((source, item["archive_path"]))
        content_length = stored_zip_size(entries)
    except (FileNotFoundError, MaterialSourceError) as exc:
        raise HTTPException(status_code=404, detail="A file in this download is missing") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="This download needs re-indexing before it can be prepared") from exc

    filename = bundle["filename"]
    headers = {
        "Content-Disposition": content_disposition("attachment", filename),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Length": str(content_length),
    }
    return StreamingResponse(iter_stored_zip(entries), media_type=ZIP_MIME, headers=headers)
