"""Offline B2 publication checks: these tests never construct a real client."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError


_script = Path(__file__).resolve().parents[2] / "scripts" / "upload_cloud_media.py"
_spec = importlib.util.spec_from_file_location("cloud_media_upload", _script)
upload = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(upload)


def local_row(tmp_path, key, content):
    path = tmp_path / key.replace("/", "-")
    path.write_bytes(content)
    return {"path": path, "key": key, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}


class FakeCloud:
    def __init__(self, existing=None):
        self.objects = {}
        self.versions = {}
        self.events = []
        self.after_asset_upload = None
        self.fail_key = None
        for key, content in (existing or {}).items():
            self.set_object(key, content)

    def set_object(self, key, content, metadata=None):
        version = f"version-{len(self.versions) + 1}"
        obj = {"body": content, "ContentLength": len(content),
               "ETag": '"' + hashlib.md5(content).hexdigest() + '"', "VersionId": version,
               "Metadata": metadata or {"sha256": hashlib.sha256(content).hexdigest()}}
        self.objects[key] = obj
        self.versions[version] = obj
        return obj

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, **kwargs):
        yield {"Contents": [{"Key": key, "Size": value["ContentLength"]} for key, value in self.objects.items()]}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        value = self.objects[Key]
        return {key: dict(item) if isinstance(item, dict) else item for key, item in value.items() if key != "body"}

    def get_object(self, *, Bucket, Key, VersionId=None, Range=None):
        obj = self.versions[VersionId] if VersionId else self.objects[Key]
        content = obj["body"][:32] if Range else obj["body"]
        return {**obj, "Body": io.BytesIO(content)}

    def upload_file(self, path, bucket, key, *, ExtraArgs, Config, Callback):
        if key == self.fail_key:
            raise ValueError("Simulated upload failure")
        assert key != upload.MANIFEST_KEY, "The manifest must never enter the parallel transfer queue"
        content = Path(path).read_bytes()
        self.set_object(key, content, ExtraArgs["Metadata"])
        self.events.append(("asset-upload", key))
        Callback(len(content))
        if self.after_asset_upload:
            self.after_asset_upload()

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        assert Key == upload.MANIFEST_KEY, "Only the manifest may use the replacement path"
        self.events.append(("manifest-publish", Key))
        obj = self.set_object(Key, Body, kwargs["Metadata"])
        return {"ETag": obj["ETag"], "VersionId": obj["VersionId"]}


def test_manifest_replacement_requires_explicit_flag(tmp_path):
    cloud = FakeCloud({upload.MANIFEST_KEY: b"old"})
    row = local_row(tmp_path, upload.MANIFEST_KEY, b"new")
    with pytest.raises(ValueError, match="--replace-manifest"):
        upload.run_upload(cloud, "private", [row], apply=True, report_dir=tmp_path / "report")
    assert cloud.events == []


def test_changed_non_manifest_stops_every_write_even_with_flag(tmp_path):
    cloud = FakeCloud({upload.MANIFEST_KEY: b"old", "HSK_Materials/book.pdf": b"original"})
    rows = [local_row(tmp_path, upload.MANIFEST_KEY, b"new"),
            local_row(tmp_path, "HSK_Materials/book.pdf", b"changed")]
    with pytest.raises(ValueError, match="refused to overwrite"):
        upload.run_upload(cloud, "private", rows, apply=True, replace_manifest=True, report_dir=tmp_path / "report")
    assert cloud.events == []


def test_preview_performs_no_writes_or_local_backup(tmp_path):
    cloud = FakeCloud({upload.MANIFEST_KEY: b"old"})
    row = local_row(tmp_path, upload.MANIFEST_KEY, b"new")
    report_dir = tmp_path / "report"
    assert upload.run_upload(cloud, "private", [row], replace_manifest=True, report_dir=report_dir) == 0
    assert not report_dir.exists()
    assert cloud.events == []


def test_assets_verified_first_old_manifest_backed_up_and_new_one_published_last(tmp_path):
    old = b'{"catalog":"old"}'
    cloud = FakeCloud({upload.MANIFEST_KEY: old})
    previous = cloud.head_object(Bucket="private", Key=upload.MANIFEST_KEY)
    rows = [local_row(tmp_path, upload.MANIFEST_KEY, b'{"catalog":"new"}'),
            local_row(tmp_path, "HSK_Materials/new-book.pdf", b"%PDF-new-content")]
    report_dir = tmp_path / "report"
    assert upload.run_upload(cloud, "private", rows, apply=True, replace_manifest=True, report_dir=report_dir) == 0
    assert cloud.events == [("asset-upload", "HSK_Materials/new-book.pdf"), ("manifest-publish", upload.MANIFEST_KEY)]
    report = json.loads((report_dir / "b2-upload-report.json").read_text())
    backup = report_dir / report["previous_manifest_backup"]
    assert backup.read_bytes() == old
    metadata = json.loads(backup.with_suffix(".metadata.json").read_text())
    assert metadata["etag"] == previous["ETag"]
    assert metadata["version_id"] == previous["VersionId"]
    assert metadata["sha256"] == hashlib.sha256(old).hexdigest()
    assert report["manifest_publication"]["sha256"] == rows[0]["sha256"]
    assert report["verified"] == 2


def test_asset_failure_keeps_previous_manifest_current(tmp_path):
    cloud = FakeCloud({upload.MANIFEST_KEY: b"old"})
    cloud.fail_key = "HSK_Materials/new-book.pdf"
    rows = [local_row(tmp_path, upload.MANIFEST_KEY, b"new"), local_row(tmp_path, cloud.fail_key, b"pdf")]
    assert upload.run_upload(cloud, "private", rows, apply=True, replace_manifest=True, report_dir=tmp_path / "report") == 1
    assert cloud.objects[upload.MANIFEST_KEY]["body"] == b"old"
    assert not any(event[0] == "manifest-publish" for event in cloud.events)


@pytest.mark.parametrize("intervening_body", [b"someone else's manifest", b"old"])
def test_changed_remote_etag_or_version_blocks_catalog_publication(tmp_path, intervening_body):
    cloud = FakeCloud({upload.MANIFEST_KEY: b"old"})
    cloud.after_asset_upload = lambda: cloud.set_object(upload.MANIFEST_KEY, intervening_body)
    rows = [local_row(tmp_path, upload.MANIFEST_KEY, b"new"), local_row(tmp_path, "HSK_Materials/new.pdf", b"pdf")]
    assert upload.run_upload(cloud, "private", rows, apply=True, replace_manifest=True, report_dir=tmp_path / "report") == 1
    assert cloud.objects[upload.MANIFEST_KEY]["body"] == intervening_body
    assert not any(event[0] == "manifest-publish" for event in cloud.events)


def test_initial_manifest_is_also_published_last(tmp_path):
    cloud = FakeCloud()
    rows = [local_row(tmp_path, upload.MANIFEST_KEY, b"first"), local_row(tmp_path, "HSK_Materials/new.pdf", b"pdf")]
    assert upload.run_upload(cloud, "private", rows, apply=True, report_dir=tmp_path / "report") == 0
    assert cloud.events[-1] == ("manifest-publish", upload.MANIFEST_KEY)


def test_manifest_appearing_after_preflight_is_not_overwritten(tmp_path):
    cloud = FakeCloud()
    cloud.after_asset_upload = lambda: cloud.set_object(upload.MANIFEST_KEY, b"other publisher")
    rows = [local_row(tmp_path, upload.MANIFEST_KEY, b"first"), local_row(tmp_path, "HSK_Materials/new.pdf", b"pdf")]
    assert upload.run_upload(cloud, "private", rows, apply=True, report_dir=tmp_path / "report") == 1
    assert cloud.objects[upload.MANIFEST_KEY]["body"] == b"other publisher"


def test_local_manifest_changed_after_inventory_is_not_published(tmp_path):
    cloud = FakeCloud({upload.MANIFEST_KEY: b"old"})
    row = local_row(tmp_path, upload.MANIFEST_KEY, b"new")
    original = cloud.head_object(Bucket="private", Key=upload.MANIFEST_KEY)
    row["path"].write_bytes(b"changed while uploading")
    with pytest.raises(ValueError, match="local manifest changed"):
        upload.publish_manifest(cloud, "private", row, original)
    assert cloud.events == []


def test_publication_lock_prevents_local_concurrent_publishers_and_is_released(tmp_path):
    report_dir = tmp_path / "report"
    with upload.publication_lock(report_dir):
        with pytest.raises(ValueError, match="Another upload owns"):
            with upload.publication_lock(report_dir):
                pytest.fail("A second publisher must not acquire the lock")
        assert (report_dir / "b2-upload.lock").is_file()
    assert not (report_dir / "b2-upload.lock").exists()
