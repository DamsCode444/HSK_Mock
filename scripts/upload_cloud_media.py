"""Upload the three approved media roots to private B2 without deleting objects."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError

MAPPINGS = (("HSK_Materials", "HSK_Materials"), ("storage", "storage"),
            ("HSK_mock_test_bundles_exam_answers_audio_file", "exam_bundles"))
ALLOWED = {".pdf", ".mp3", ".webp", ".png", ".jpg", ".jpeg", ".avif", ".zip", ".json", ".txt"}
MANIFEST_KEY = "storage/materials/manifest.json"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024


def client():
    if settings.b2_key_id is None or settings.b2_application_key is None:
        raise ValueError("B2 credentials are not configured")
    return boto3.client("s3", endpoint_url=settings.b2_endpoint_url,
        region_name=settings.b2_region,
        aws_access_key_id=settings.b2_key_id.get_secret_value(),
        aws_secret_access_key=settings.b2_application_key.get_secret_value(),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
            max_pool_connections=40, connect_timeout=20, read_timeout=120,
            retries={"max_attempts": 5, "mode": "standard"},
            request_checksum_calculation="when_required", response_checksum_validation="when_required"))


def inventory():
    rows = []
    for folder, prefix in MAPPINGS:
        root = (ROOT / folder).resolve()
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("A media path escapes its source directory")
            if path.suffix.lower() not in ALLOWED or path.name.startswith(".env"):
                raise ValueError("Unexpected file type in media source; review before upload")
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
                    digest.update(chunk)
            rows.append({"path": path, "key": prefix + "/" + path.relative_to(root).as_posix(),
                         "size": path.stat().st_size, "sha256": digest.hexdigest()})
    return rows


def _same_content(head, row):
    return (head["ContentLength"] == row["size"]
            and head.get("Metadata", {}).get("sha256") == row["sha256"])


def _head_optional(cloud, bucket, key):
    try:
        return cloud.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def _version_identity(head):
    if not head.get("ETag"):
        raise ValueError("Remote manifest has no ETag; publication cannot be checked safely")
    return (head["ETag"], head.get("VersionId"), head["ContentLength"],
            head.get("Metadata", {}).get("sha256"))


def preflight(cloud, bucket, rows, remote, *, replace_manifest=False):
    """Reject every differing overlap except an explicitly approved catalog."""
    pending = []
    manifest = None
    original_manifest = None
    def inspect(row):
        return cloud.head_object(Bucket=bucket, Key=row["key"]) if row["key"] in remote else None
    # Read-only checks may run concurrently, but finish every overlap check
    # before starting any transfer. Preserve inventory order in the results.
    with ThreadPoolExecutor(max_workers=8) as pool:
        heads = list(pool.map(inspect, rows))
    for row, head in zip(rows, heads, strict=True):
        if head is not None and _same_content(head, row):
            continue
        if row["key"] == MANIFEST_KEY:
            if head is not None and not replace_manifest:
                raise ValueError("The B2 catalog differs; use --replace-manifest only for an intended catalog update")
            if head is not None:
                _version_identity(head)
            manifest, original_manifest = row, head
        elif head is not None:
            raise ValueError("An existing B2 object differs; refused to overwrite it")
        else:
            pending.append(row)
    return pending, manifest, original_manifest


@contextmanager
def publication_lock(report_dir):
    """Avoid overlapping publishers from this workspace; never break a stale lock."""
    report_dir.mkdir(parents=True, exist_ok=True)
    lock_path = report_dir / "b2-upload.lock"
    try:
        lock = lock_path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("Another upload owns .cloud-transfer/b2-upload.lock; verify it is stopped before removing a stale lock") from exc
    try:
        with lock:
            json.dump({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, lock)
        yield
    finally:
        lock_path.unlink()


def _read_manifest_object(cloud, bucket, expected_head):
    params = {"Bucket": bucket, "Key": MANIFEST_KEY}
    if expected_head.get("VersionId"):
        params["VersionId"] = expected_head["VersionId"]
    response = cloud.get_object(**params)
    try:
        body = response["Body"].read(MAX_MANIFEST_BYTES + 1)
    finally:
        response["Body"].close()
    if len(body) > MAX_MANIFEST_BYTES or len(body) != expected_head["ContentLength"]:
        raise ValueError("Remote manifest size does not match its checked version")
    if response.get("ETag") != expected_head["ETag"] or response.get("VersionId") != expected_head.get("VersionId"):
        raise ValueError("Remote manifest changed while being read; publication stopped")
    return body


def preserve_manifest(cloud, bucket, original, report_dir):
    """Retain the exact previous version and a credential-free audit record."""
    raw = _read_manifest_object(cloud, bucket, original)
    sha256 = hashlib.sha256(raw).hexdigest()
    declared = original.get("Metadata", {}).get("sha256")
    if declared and declared != sha256:
        raise ValueError("The previous manifest content does not match its SHA-256 metadata")
    backup_dir = report_dir / "manifests"
    backup_dir.mkdir(parents=True, exist_ok=True)
    basename = f"{time.time_ns()}-{sha256[:16]}"
    path = backup_dir / f"{basename}.json"
    with path.open("xb") as destination:
        destination.write(raw)
    evidence = {"bucket": bucket, "key": MANIFEST_KEY, "etag": original["ETag"],
                "version_id": original.get("VersionId"), "size_bytes": len(raw), "sha256": sha256,
                "saved_at": datetime.now(timezone.utc).isoformat(), "backup_file": path.name}
    with (backup_dir / f"{basename}.metadata.json").open("x", encoding="utf-8") as destination:
        json.dump(evidence, destination, indent=2)
    return str(path.relative_to(report_dir))


def publish_manifest(cloud, bucket, row, original):
    """Publish last, with a last-moment version recheck and a full readback.

    B2 does not document atomic If-Match PutObject support. This is deliberately
    a single-publisher workflow, not a cross-machine compare-and-swap guarantee.
    Keep other publishers stopped while running it. No automatic overwrite
    retry is attempted after an intervening version change.
    """
    if row["key"] != MANIFEST_KEY:
        raise ValueError("Only the study catalog may use manifest publication")
    if row["size"] > MAX_MANIFEST_BYTES:
        raise ValueError("Local manifest exceeds its size limit")
    raw = row["path"].read_bytes()
    if len(raw) != row["size"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError("The local manifest changed after inventory; rerun the upload")
    current = _head_optional(cloud, bucket, MANIFEST_KEY)
    if original is None:
        if current is not None:
            raise ValueError("A remote manifest appeared after preflight; refused to overwrite it")
    elif current is None or _version_identity(current) != _version_identity(original):
        raise ValueError("The remote manifest changed after preflight; refused to overwrite it")
    result = cloud.put_object(Bucket=bucket, Key=MANIFEST_KEY, Body=raw,
                              ContentType="application/json", CacheControl="no-cache",
                              Metadata={"sha256": row["sha256"]})
    head = cloud.head_object(Bucket=bucket, Key=MANIFEST_KEY)
    if not _same_content(head, row):
        raise ValueError("Published manifest metadata verification failed")
    if ((result.get("VersionId") and result["VersionId"] != head.get("VersionId"))
            or (result.get("ETag") and result["ETag"] != head.get("ETag"))):
        raise ValueError("Another publication replaced this manifest before verification")
    if hashlib.sha256(_read_manifest_object(cloud, bucket, head)).hexdigest() != row["sha256"]:
        raise ValueError("Published manifest content verification failed")
    return {"etag": head["ETag"], "version_id": head.get("VersionId"), "sha256": row["sha256"]}


def run_upload(cloud, bucket, rows, *, apply=False, replace_manifest=False, workers=8, report_dir=None):
    report_dir = report_dir or ROOT / ".cloud-transfer"
    remote = {}
    for page in cloud.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        remote.update({item["Key"]: item["Size"] for item in page.get("Contents", [])})
    print(json.dumps({"b2_connected": True, "existing_objects": len(remote)}), flush=True)
    print(json.dumps({"local_files": len(rows), "local_bytes": sum(row["size"] for row in rows),
                      "mode": "upload" if apply else "preview"}), flush=True)
    # Preflight all existing overlapping keys before writing any object.
    pending, manifest, original = preflight(cloud, bucket, rows, remote, replace_manifest=replace_manifest)
    upload_count = len(pending) + int(manifest is not None)
    print(json.dumps({"to_upload": upload_count, "already_verified": len(rows) - upload_count,
                      "replace_manifest": original is not None, "manifest_published_last": manifest is not None}), flush=True)
    if not apply:
        return 0
    backup = preserve_manifest(cloud, bucket, original, report_dir) if original is not None else None
    config = TransferConfig(multipart_threshold=16 * 1024 * 1024, multipart_chunksize=16 * 1024 * 1024,
                            max_concurrency=3, use_threads=True)
    progress = {"bytes_sent": 0}
    lock = threading.Lock()
    def uploaded(size):
        with lock:
            progress["bytes_sent"] += size
    def upload(row):
        # A key can appear after listing/preflight. Never intentionally replace
        # any existing differing asset, even in --replace-manifest mode.
        existing = _head_optional(cloud, bucket, row["key"])
        if existing is not None:
            if not _same_content(existing, row):
                raise ValueError("A differing B2 asset appeared after preflight; refused to overwrite it")
            return row
        content_type = mimetypes.guess_type(row["path"].name)[0] or "application/octet-stream"
        if row["path"].suffix.lower() == ".webp":
            content_type = "image/webp"
        cloud.upload_file(str(row["path"]), bucket, row["key"],
            ExtraArgs={"Metadata": {"sha256": row["sha256"]}, "ContentType": content_type},
            Config=config, Callback=uploaded)
        head = cloud.head_object(Bucket=bucket, Key=row["key"])
        if head["ContentLength"] != row["size"] or head.get("Metadata", {}).get("sha256") != row["sha256"]:
            raise ValueError("Uploaded object verification failed")
        # Confirm readable bytes using the same private key, including range support.
        if row["size"]:
            response = cloud.get_object(Bucket=bucket, Key=row["key"], Range="bytes=0-31")
            try:
                prefix = response["Body"].read()
            finally:
                response["Body"].close()
            with row["path"].open("rb") as source:
                if prefix != source.read(32):
                    raise ValueError("Uploaded content range did not match source")
        return row
    completed = len(rows) - upload_count
    failures = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as pool:
        outstanding = {pool.submit(upload, row): row for row in pending}
        while outstanding:
            finished, _ = wait(outstanding, timeout=15, return_when=FIRST_COMPLETED)
            for future in finished:
                row = outstanding.pop(future)
                try:
                    future.result()
                    completed += 1
                except Exception as exc:
                    failures.append({"key": row["key"], "error_type": type(exc).__name__})
            elapsed = time.monotonic() - started
            if not finished or completed % 25 == 0 or not outstanding:
                print(json.dumps({"verified": completed, "total": len(rows), "failures": len(failures),
                    "sent_mib": round(progress["bytes_sent"] / 1048576, 1), "elapsed_seconds": round(elapsed)}), flush=True)
    publication = None
    if manifest is not None and not failures:
        try:
            publication = publish_manifest(cloud, bucket, manifest, original)
            completed += 1
        except Exception as exc:
            failures.append({"key": MANIFEST_KEY, "error_type": type(exc).__name__})
    report_dir.mkdir(exist_ok=True)
    report = {"verified": completed, "total": len(rows), "bytes": sum(r["size"] for r in rows),
              "failures": failures, "previous_manifest_backup": backup, "manifest_publication": publication,
              "objects": [{k: v for k, v in row.items() if k != "path"} for row in rows]}
    (report_dir / "b2-upload-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"upload_complete": not failures, "verified": completed, "total": len(rows)}), flush=True)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Upload new objects after conflict checks")
    parser.add_argument("--replace-manifest", action="store_true", help="Allow only the materials catalog to change; back it up and publish it last. Run only one publisher.")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    cloud = client()
    bucket = settings.b2_bucket_name
    cloud.head_bucket(Bucket=bucket)
    if args.apply:
        report_dir = ROOT / ".cloud-transfer"
        with publication_lock(report_dir):
            return run_upload(cloud, bucket, inventory(), apply=True, replace_manifest=args.replace_manifest,
                              workers=args.workers, report_dir=report_dir)
    return run_upload(cloud, bucket, inventory(), replace_manifest=args.replace_manifest, workers=args.workers)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        print(json.dumps({"error_type": type(exc).__name__, "code": exc.response.get("Error", {}).get("Code")}))
        raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__, "message": "Cloud upload stopped safely; credentials not printed."}))
        raise SystemExit(1)
