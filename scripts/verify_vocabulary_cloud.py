"""Read-only verification of the published vocabulary catalog and private files.

Uses an existing active user's ID for locally signed test grants. Does not create
or change users/attempts, and never prints tokens or signed URLs.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import User
from app.services.materials_access import create_material_access_token
from app.services.materials_catalog import load_materials_manifest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_cloud(cloud, url, headers=None):
    """Retry only transient, read-only network failures; never retry a denial."""
    for attempt in range(3):
        try:
            response = cloud.get(url, headers=headers)
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                return response
        except httpx.TransportError:
            if attempt == 2:
                raise
        print(json.dumps({"retrying_cloud_read": attempt + 1}), flush=True)
        time.sleep(attempt + 1)


def main():
    require(settings.b2_enabled and settings.database_backend == "turso", "Cloud mode must be enabled")
    manifest = load_materials_manifest()
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.is_active.is_(True)).limit(1))
    require(user_id is not None, "An active user is required for private file checks")
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "files": []}
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=45) as api, \
            httpx.Client(timeout=60, follow_redirects=False) as cloud:
        response = api.get("/api/materials/catalog")
        require(response.status_code == 200, "Public catalog unavailable")
        catalog = response.json()
        vocabulary = next((e for e in catalog["editions"] if e["id"] == "vocabulary"), None)
        require(vocabulary is not None and len(vocabulary["levels"]) == 7, "Expected seven vocabulary groups")
        require(vocabulary["levels"][-1]["level_label"] == "7–9", "Advanced levels must remain grouped")
        report["totals"] = catalog["totals"]
        assets = []
        for summary in vocabulary["levels"]:
            response = api.get(f"/api/materials/collections/{summary['slug']}")
            require(response.status_code == 200, "Vocabulary collection unavailable")
            collection = response.json()
            book = collection["books"][0]
            require(not book["has_audio"] and not book["lessons"], "Vocabulary must not invent audio")
            assets.append(manifest["assets"][book["pdf_asset_id"]])
            cover = api.get(book["cover_url"])
            require(cover.status_code == 307, "Cover must redirect to private B2")
            url = cover.headers["location"]
            require(urlparse(url).hostname == urlparse(settings.b2_endpoint_url).hostname, "Unexpected cover host")
            result = read_cloud(cloud, url, headers={"Range": "bytes=0-31"})
            require(result.status_code == 206 and result.content[:4] == b"RIFF", "Cover range unavailable")
        assets.extend(manifest["assets"][r["asset_id"]] for r in vocabulary["references"])
        require(len(assets) == 8, "Expected seven PDFs and one chart")
        for asset in assets:
            asset_id = asset["id"]
            require(api.post(f"/api/materials/assets/{asset_id}/access", json={"disposition": "inline"}).status_code == 401,
                    "Anonymous access must be denied")
            require(api.get(f"/api/materials/covers/{asset_id}").status_code == 404, "Documents must not be public covers")
            for disposition in ("inline", "attachment"):
                token, _ = create_material_access_token(user_id=user_id, resource_type="asset",
                                                        resource_id=asset_id, disposition=disposition)
                response = api.get(f"/api/materials/content/{asset_id}", params={"token": token})
                require(response.status_code == 307, "Private material redirect failed")
                url = response.headers["location"]
                require(urlparse(url).hostname == urlparse(settings.b2_endpoint_url).hostname, "Unexpected material host")
                headers = {} if disposition == "inline" else {"Range": "bytes=0-31"}
                result = read_cloud(cloud, url, headers=headers)
                require(result.status_code == (200 if disposition == "inline" else 206),
                        f"B2 read failed: {asset_id}, {disposition}, HTTP {result.status_code}")
                require(result.headers.get("content-type", "").split(";")[0] == asset["media_type"], "Wrong material MIME type")
                require(result.headers.get("content-disposition", "").startswith(disposition), "Wrong material disposition")
                if disposition == "inline":
                    require(len(result.content) == asset["size_bytes"], "Material size mismatch")
                    require(hashlib.sha256(result.content).hexdigest() == asset["sha256"], "Material checksum mismatch")
            report["files"].append({"id": asset_id, "size_bytes": asset["size_bytes"],
                                    "sha256_verified": True, "inline_and_download_verified": True})
            print(json.dumps({"verified": asset_id}), flush=True)
        report["cover_count"] = 7
    (ROOT / ".cloud-transfer" / "vocabulary-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"vocabulary_verified": len(report["files"]), "covers_verified": 7}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # HTTP exceptions can embed signed URLs; only show safe error categories.
        print(json.dumps({"verification_failed": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, ValueError) else "Network or service check failed; no credentials printed"}))
        raise SystemExit(1)
