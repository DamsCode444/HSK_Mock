from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from collections.abc import Generator
from pathlib import Path

import pytest
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import materials
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.media import PublicExamFiles
from app.db.session import Base, get_db
from app.models import User
from app.services.materials_catalog import (
    ManifestBuilder,
    clear_manifest_cache,
    resolve_material_path,
)
from app.services.materials_access import create_material_access_token


@pytest.fixture()
def materials_api(tmp_path: Path, monkeypatch) -> Generator[tuple[TestClient, dict], None, None]:
    monkeypatch.setattr(settings, "b2_enabled", False)
    source = tmp_path / "source"
    storage = tmp_path / "storage" / "materials"
    source.mkdir()
    storage.mkdir(parents=True)
    document = source / "book.pdf"
    document.write_bytes(b"%PDF-1.4\nmaterial-test-body\n%%EOF")
    cover = storage / "cover.webp"
    cover.write_bytes(b"RIFFfake-WEBP")

    manifest = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "totals": {
            "edition_count": 2,
            "collection_count": 1,
            "book_count": 1,
            "lesson_count": 0,
            "audio_track_count": 0,
            "page_count": 1,
            "audio_duration_seconds": 0,
            "source_file_count": 1,
            "source_size_bytes": document.stat().st_size,
        },
        "collections": [
            {
                "id": "hsk20-l01",
                "slug": "hsk-2-0-level-1",
                "standard": "2.0",
                "level": 1,
                "title": "HSK 1",
                "description": "Test collection",
                "status": "available",
                "available": True,
                "note": "",
                "cover_asset_id": "cover",
                "cover_url": "/api/materials/covers/cover",
                "book_count": 1,
                "lesson_count": 0,
                "audio_track_count": 0,
                "audio_duration_seconds": 0,
                "total_size_bytes": document.stat().st_size,
                "books": [
                    {
                        "id": "book",
                        "title": "HSK 1 Textbook",
                        "pdf_asset_id": "book-pdf",
                        "lessons": [],
                    }
                ],
            }
        ],
        "assets": {
            "book-pdf": {
                "id": "book-pdf",
                "root": "source",
                "path": "book.pdf",
                "kind": "document",
                "media_type": "application/pdf",
                "filename": "HSK-1-Textbook.pdf",
                "size_bytes": document.stat().st_size,
            },
            "cover": {
                "id": "cover",
                "root": "storage",
                "path": "cover.webp",
                "kind": "cover",
                "media_type": "image/webp",
                "filename": "cover.webp",
                "size_bytes": cover.stat().st_size,
            },
        },
        "bundles": {
            "book-complete-bundle": {
                "id": "book-complete-bundle",
                "book_id": "book",
                "kind": "complete",
                "filename": "HSK-1-Book.zip",
                "media_type": "application/zip",
                "size_bytes": document.stat().st_size,
                "prebuilt_asset_id": None,
                "items": [{"asset_id": "book-pdf", "archive_path": "Book/book.pdf"}],
            }
        },
    }
    manifest_path = storage / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(settings, "materials_root", source)
    monkeypatch.setattr(settings, "materials_storage_root", storage)
    monkeypatch.setattr(settings, "materials_manifest_path", manifest_path)
    clear_manifest_cache()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    with testing_session() as db:
        student = User(
            username="reader",
            email="reader@example.com",
            password_hash="not-used",
            role="student",
            is_active=True,
        )
        db.add(student)
        db.commit()
        student_id = student.id

    app = FastAPI()
    app.include_router(materials.router, prefix="/api")

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as db:
            yield db

    def override_user() -> User:
        with testing_session() as db:
            return db.get(User, student_id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, manifest
    clear_manifest_cache()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_public_catalog_and_cover(materials_api) -> None:
    client, _ = materials_api
    catalog = client.get("/api/materials/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["editions"][0]["available_levels"] == [1]
    assert catalog.json()["totals"]["book_count"] == 1
    detail = client.get("/api/materials/collections/hsk-2-0-level-1")
    assert detail.status_code == 200
    assert detail.json()["books"][0]["pdf_asset_id"] == "book-pdf"
    cover = client.get("/api/materials/covers/cover")
    assert cover.status_code == 200
    assert cover.headers["content-type"].startswith("image/webp")


def test_signed_document_supports_inline_range_requests(materials_api) -> None:
    client, _ = materials_api
    grant = client.post(
        "/api/materials/assets/book-pdf/access",
        json={"disposition": "inline"},
    )
    assert grant.status_code == 200
    payload = grant.json()
    assert payload["url"].startswith("/api/materials/content/book-pdf?token=")
    response = client.get(payload["url"], headers={"Range": "bytes=0-3"})
    assert response.status_code == 206
    assert response.content == b"%PDF"
    assert response.headers["content-disposition"].startswith("inline")


@pytest.mark.parametrize("disposition", ["inline", "attachment"])
def test_comparison_png_is_private_but_supports_viewing_and_download(materials_api, monkeypatch, disposition):
    client, manifest = materials_api
    content = b"\x89PNG\r\n\x1a\nreference-fixture"
    (settings.materials_root / "comparison.png").write_bytes(content)
    asset = dict(manifest["assets"]["book-pdf"], id="comparison-image", path="comparison.png",
                 filename="comparison.png", media_type="image/png", size_bytes=len(content))
    monkeypatch.setattr(materials, "material_asset", lambda asset_id: asset if asset_id == asset["id"] else None)
    assert client.get("/api/materials/covers/comparison-image").status_code == 404
    grant = client.post("/api/materials/assets/comparison-image/access", json={"disposition": disposition})
    assert grant.status_code == 200
    assert grant.json()["media_type"] == "image/png"
    response = client.get(grant.json()["url"])
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith(disposition)
    client.app.dependency_overrides.pop(get_current_user)
    assert client.post("/api/materials/assets/comparison-image/access", json={"disposition": disposition}).status_code == 401


def test_signed_bundle_is_a_valid_streamed_zip(materials_api) -> None:
    client, _ = materials_api
    grant = client.post("/api/materials/bundles/book-complete-bundle/access")
    assert grant.status_code == 200
    response = client.get(grant.json()["url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["Book/book.pdf"]
        assert archive.read("Book/book.pdf").startswith(b"%PDF")


def test_material_path_cannot_escape_configured_root(materials_api) -> None:
    _, manifest = materials_api
    unsafe = dict(manifest["assets"]["book-pdf"], path="../outside.pdf")
    with pytest.raises(Exception, match="Unsafe material path"):
        resolve_material_path(unsafe)


def test_private_materials_cannot_use_legacy_static_mount(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "b2_enabled", False)
    public = tmp_path / "storage"
    private = public / "materials"
    private.mkdir(parents=True)
    (private / "manifest.json").write_text("private paths", encoding="utf-8")
    (private / "track.mp3").write_bytes(b"private audio")
    (public / "exam.webp").write_bytes(b"public exam image")
    app = FastAPI()
    app.mount("/media", PublicExamFiles(directory=public, protected_paths=[private]))
    with TestClient(app) as client:
        assert client.get("/media/exam.webp").status_code == 200
        for target in (
            "/media/materials/manifest.json",
            "/media/materials/track.mp3",
            "/media/MATERIALS/track.mp3",
            "/media/%6Daterials/track.mp3",
            "/media/materials%5Ctrack.mp3",
        ):
            assert client.get(target).status_code == 404


def test_media_requires_authentication_and_matching_unexpired_grant(materials_api) -> None:
    client, _ = materials_api
    signed = client.post("/api/materials/assets/book-pdf/access", json={"disposition": "inline"}).json()
    token = signed["url"].split("token=", 1)[1]
    assert client.get("/api/materials/content/cover", params={"token": token}).status_code == 401
    assert client.get("/api/materials/content/book-pdf", params={"token": token + "invalid"}).status_code == 401
    payload = jwt.decode(token, settings.material_signing_secret, algorithms=[settings.jwt_algorithm])
    payload["exp"] = datetime.now(timezone.utc) - timedelta(seconds=30)
    expired = jwt.encode(payload, settings.material_signing_secret, algorithm=settings.jwt_algorithm)
    assert client.get("/api/materials/content/book-pdf", params={"token": expired}).status_code == 401
    client.app.dependency_overrides.pop(get_current_user)
    assert client.post("/api/materials/assets/book-pdf/access", json={"disposition": "inline"}).status_code == 401
    assert client.post("/api/materials/bundles/book-complete-bundle/access").status_code == 401


def test_existing_grant_stops_working_for_disabled_account(materials_api) -> None:
    client, _ = materials_api
    user = client.app.dependency_overrides[get_current_user]()
    token, _ = create_material_access_token(
        user_id=user.id, resource_type="asset", resource_id="book-pdf", disposition="inline"
    )
    for db in client.app.dependency_overrides[get_db]():
        db.get(User, user.id).is_active = False
        db.commit()
    assert client.get("/api/materials/content/book-pdf", params={"token": token}).status_code == 403


def test_single_track_workbook_lesson_is_only_supplemental_after_canonical_end(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    audio = source / "audio"
    output = tmp_path / "output"
    for number in (1, 21):
        lesson = audio / f"lesson-{number:02d}"
        lesson.mkdir(parents=True)
        (lesson / f"hsk3-workbook-{number:02d}.mp3").write_bytes(b"test")
    builder = ManifestBuilder(source_root=source, output_root=output)

    def fake_track(path, *, book_id, lesson_number, track_number, root):
        asset_id = f"{book_id}-u{lesson_number:02d}-t{track_number:02d}"
        return {
            "id": asset_id,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
        }, 1.0

    monkeypatch.setattr(builder, "_track_asset", fake_track)
    lessons = builder._hsk20_lessons(
        audio,
        "workbook",
        supplemental_after=20,
    )
    assert [(lesson["lesson_number"], lesson["kind"]) for lesson in lessons] == [
        (1, "lesson"),
        (21, "supplemental"),
    ]


def test_cloud_materials_work_without_local_media_and_preserve_auth(materials_api, monkeypatch, tmp_path):
    from app.services import object_storage

    client, manifest = materials_api
    raw = b"%PDF-1.4\nmaterial-test-body\n%%EOF"
    calls = []
    bodies = []
    signatures = []

    class FakeB2:
        def get_object(self, **kwargs):
            calls.append(kwargs["Key"])
            content = json.dumps(manifest).encode() if kwargs["Key"].endswith("manifest.json") else raw
            body = io.BytesIO(content)
            bodies.append(body)
            return {"Body": body, "ContentLength": len(content)}

        def generate_presigned_url(self, operation, **kwargs):
            signatures.append((operation, kwargs))
            return "https://private-bucket.example/download?temporary-signature=test"

    monkeypatch.setattr(settings, "b2_enabled", True)
    monkeypatch.setattr(settings, "materials_root", tmp_path / "missing-source")
    monkeypatch.setattr(settings, "materials_storage_root", tmp_path / "missing-output")
    monkeypatch.setattr(settings, "materials_manifest_path", tmp_path / "missing-manifest.json")
    monkeypatch.setattr(object_storage, "b2_client", lambda: FakeB2())
    clear_manifest_cache()
    assert client.get("/api/materials/catalog").json()["totals"]["book_count"] == 1
    assert client.get("/api/materials/collections/hsk-2-0-level-1").status_code == 200
    assert calls == ["storage/materials/manifest.json"]

    grant = client.post("/api/materials/assets/book-pdf/access", json={"disposition": "inline"}).json()
    response = client.get(grant["url"], headers={"Range": "bytes=0-3"}, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["cache-control"] == "private, no-store"
    operation, arguments = signatures[-1]
    assert operation == "get_object"
    assert arguments["Params"]["Key"] == "HSK_Materials/book.pdf"
    assert arguments["Params"]["ResponseContentDisposition"].startswith("inline;")
    assert arguments["Params"]["ResponseContentType"] == "application/pdf"
    assert arguments["HttpMethod"] == "GET"
    assert arguments["ExpiresIn"] == settings.b2_signed_url_ttl_seconds
    assert client.get("/api/materials/content/book-pdf", params={"token": "invalid" * 5}, follow_redirects=False).status_code == 401

    cover = client.get("/api/materials/covers/cover", follow_redirects=False)
    assert cover.status_code == 307
    assert signatures[-1][1]["Params"]["Key"] == "storage/materials/cover.webp"
    assert "no-store" in cover.headers["cache-control"]

    grant = client.post("/api/materials/bundles/book-complete-bundle/access").json()
    response = client.get(grant["url"])
    assert response.status_code == 200
    assert int(response.headers["content-length"]) == len(response.content)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("Book/book.pdf") == raw
    assert calls[-1] == "HSK_Materials/book.pdf"
    assert all(body.closed for body in bodies)


def test_cloud_media_only_signs_public_exam_paths(tmp_path, monkeypatch):
    from app.core import media

    monkeypatch.setattr(settings, "b2_enabled", True)
    calls = []

    def fake_presign(key, **kwargs):
        calls.append((key, kwargs))
        return "https://private-bucket.example/exam?signature=test"

    monkeypatch.setattr(media, "presigned_object_url", fake_presign)
    app = FastAPI()
    app.mount("/media", PublicExamFiles(directory=tmp_path / "not-present", check_dir=False, protected_paths=[]))
    with TestClient(app) as client:
        response = client.get("/media/HSK5/H51328/pages/exam-page-001.webp", follow_redirects=False)
        assert response.status_code == 307
        assert calls[-1][0] == "storage/HSK5/H51328/pages/exam-page-001.webp"
        assert client.head("/media/HSK5/H51328/pdf/exam.pdf", follow_redirects=False).status_code == 307
        assert calls[-1][1]["method"] == "HEAD"
        before = len(calls)
        for path in (
            "materials/manifest.json", "MATERIALS/track.mp3", "%6Daterials/track.mp3",
            "materials%5Ctrack.mp3", "HSK_Materials/book.pdf", "HSK5/.env",
            "HSK5/H51328/secrets.json", "HSK5%5C..%5Cmaterials%5Ctrack.mp3",
        ):
            assert client.get(f"/media/{path}", follow_redirects=False).status_code == 404
        assert len(calls) == before


@pytest.mark.parametrize("path", ["../book.pdf", "/book.pdf", "C:/book.pdf", "folder\\..\\book.pdf", "book.pdf\x00", ""])
def test_cloud_material_keys_reject_unsafe_paths(path):
    from app.services.object_storage import material_object_key

    with pytest.raises(ValueError):
        material_object_key({"root": "source", "path": path})


def test_cloud_catalog_failure_is_safe(materials_api, monkeypatch):
    from app.services import object_storage

    client, _ = materials_api

    class FailingB2:
        def get_object(self, **kwargs):
            raise RuntimeError("private credential or signed URL must not leak")

    monkeypatch.setattr(settings, "b2_enabled", True)
    monkeypatch.setattr(object_storage, "b2_client", lambda: FailingB2())
    clear_manifest_cache()
    response = client.get("/api/materials/catalog")
    assert response.status_code == 503
    assert "private credential" not in response.text


def test_cloud_zip_rejects_changed_object_and_closes_body(monkeypatch):
    from app.services import object_storage

    body = io.BytesIO(b"changed size")

    class FakeB2:
        def get_object(self, **kwargs):
            return {"Body": body, "ContentLength": len(body.getvalue())}

    monkeypatch.setattr(object_storage, "b2_client", lambda: FakeB2())
    source = object_storage.RemoteMaterialFile({"root": "source", "path": "book.pdf", "size_bytes": 1})
    with pytest.raises(object_storage.ObjectStorageError, match="changed"):
        with source.open("rb"):
            pytest.fail("Changed data must not be streamed with the wrong ZIP length")
    assert body.closed
