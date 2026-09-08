import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.materials_catalog import ManifestBuilder, MaterialSourceError
from app.services.streaming_zip import iter_stored_zip, stored_zip_size


@pytest.mark.parametrize("member", ["../outside.mp3", "/outside.mp3", "C:/outside.mp3", "lesson-01/run.exe"])
def test_rejects_unsafe_zip_members_before_extraction(tmp_path: Path, member: str):
    archive_path = tmp_path / "audio.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member, b"test")
    builder = ManifestBuilder(source_root=tmp_path / "source", output_root=tmp_path / "generated")
    with zipfile.ZipFile(archive_path) as archive, pytest.raises(MaterialSourceError):
        builder._safe_zip_members(archive)


def test_rejects_zip_links_and_semantic_track_collisions(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    archive_path = source / "audio.zip"
    link = zipfile.ZipInfo("lesson-01/1-1.mp3")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, b"../../outside")
    builder = ManifestBuilder(source_root=source, output_root=tmp_path / "generated")
    with zipfile.ZipFile(archive_path) as archive, pytest.raises(MaterialSourceError, match="symbolic"):
        builder._safe_zip_members(archive)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Audio/lesson-01/1-1.mp3", b"test")
        archive.writestr("Other/lesson-01/01-01.mp3", b"test")
    with pytest.raises(MaterialSourceError, match="duplicate lesson/track"):
        builder._hsk30_lessons(archive_path, level=1, book_id="textbook")
    assert not (tmp_path / "generated" / "extracted").exists()


def test_same_size_zip_replacement_updates_audio_and_preserves_previous_file(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "generated"
    source.mkdir()
    output.mkdir()
    archive_path = source / "audio.zip"
    old_audio = b"\xff\xfb\x90\x00" + b"A" * 1000
    new_audio = b"\xff\xfb\x90\x00" + b"B" * 1000
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Audio/lesson-01/1-1.mp3", old_audio)
    archive_stat = archive_path.stat()
    first = ManifestBuilder(source_root=source, output_root=output)
    lessons, original_archive = first._hsk30_lessons(archive_path, level=1, book_id="textbook")
    track_id = lessons[0]["tracks"][0]["id"]
    old_path = output / first.assets[track_id]["path"]
    (output / "manifest.json").write_text(json.dumps({"assets": first.assets}), encoding="utf-8")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Audio/lesson-01/1-1.mp3", new_audio)
    os.utime(archive_path, ns=(archive_stat.st_atime_ns, archive_stat.st_mtime_ns))
    assert archive_path.stat().st_size == archive_stat.st_size
    second = ManifestBuilder(source_root=source, output_root=output)
    _, updated_archive = second._hsk30_lessons(archive_path, level=1, book_id="textbook")
    assert updated_archive["sha256"] != original_archive["sha256"]
    assert (output / second.assets[track_id]["path"]).read_bytes() == new_audio
    assert old_path.read_bytes() == old_audio


def test_generated_storage_must_be_separate_from_source(tmp_path: Path):
    with pytest.raises(MaterialSourceError, match="separate directories"):
        ManifestBuilder(source_root=tmp_path, output_root=tmp_path / "generated")


def test_material_storage_defaults_follow_configured_storage(tmp_path: Path):
    configured = Settings(_env_file=None, storage_root=tmp_path)
    assert configured.materials_storage_root == tmp_path / "materials"
    assert configured.materials_manifest_path == tmp_path / "materials" / "manifest.json"


def test_streaming_zip_preflight_matches_actual_size_and_rejects_collisions(tmp_path: Path):
    source = tmp_path / "audio.mp3"
    source.write_bytes(b"test audio")
    entries = [(source, "Audio/Lesson-01/Track-01.mp3"), (source, "Audio/Lesson-02/Track-01.mp3")]
    assert stored_zip_size(entries) == len(b"".join(iter_stored_zip(entries)))
    with pytest.raises(ValueError, match="Duplicate"):
        stored_zip_size([(source, "track.mp3"), (source, "TRACK.mp3")])
