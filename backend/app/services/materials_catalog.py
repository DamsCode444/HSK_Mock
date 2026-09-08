from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

import pymupdf
from PIL import Image, ImageOps

from app.core.config import settings


MANIFEST_SCHEMA_VERSION = 1
PDF_MIME = "application/pdf"
MP3_MIME = "audio/mpeg"
ZIP_MIME = "application/zip"

_AUDIO_DIR_RE = re.compile(
    r"hsk(?P<level>[1-6])(?P<volume>[ab])?(?P<kind>textbook|workbook)audios$",
    re.IGNORECASE,
)
_BOOK_RE = re.compile(
    r"hsk-(?P<level>[1-6])(?P<volume>[ab])?-(?P<kind>textbook|workbook)$",
    re.IGNORECASE,
)
_LESSON_RE = re.compile(r"lesson[- _]?(?P<number>\d+)$", re.IGNORECASE)
_FOUR_DIGIT_TRACK_RE = re.compile(r"(?P<lesson>\d{2})(?P<track>\d{2})$")
_NEW_TRACK_RE = re.compile(r"(?P<lesson>\d+)[-_](?P<track>\d+)$")
_VOCABULARY_BOOK_RE = re.compile(
    r"New-HSK-Vocabulary-(?:Level-|L)(?P<level>[1-6]|7-9)\.pdf$",
    re.IGNORECASE,
)
_VOCABULARY_REFERENCE_NAME = "hsk new vs old vocabulary comparision.png"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._() -]+")

_manifest_lock = RLock()
_manifest_cache: tuple[tuple[Path, int, int], dict[str, Any]] | None = None


class MaterialsNotIndexedError(RuntimeError):
    pass


class MaterialSourceError(ValueError):
    pass


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_filename(value: str, fallback: str = "material") -> str:
    cleaned = _SAFE_FILENAME_RE.sub("-", Path(value).name).strip(" .-")
    return cleaned or fallback


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches_zip_member(path: Path, info: zipfile.ZipInfo) -> bool:
    if not path.is_file() or path.stat().st_size != info.file_size:
        return False
    checksum = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF == info.CRC


def _synchsafe(value: bytes) -> int:
    if len(value) != 4 or any(byte & 0x80 for byte in value):
        return 0
    return (value[0] << 21) | (value[1] << 14) | (value[2] << 7) | value[3]


def _read_mp3_info(path: Path) -> tuple[float, int, int]:
    """Return duration, bitrate, and sample rate for the supplied CBR MP3s.

    The study archive consists entirely of MPEG Layer III constant-bitrate
    files. Reading the first valid frame keeps indexing dependency-free and
    avoids launching 1,215 external probe processes.
    """
    size = path.stat().st_size
    with path.open("rb") as source:
        header = source.read(10)
        audio_offset = 0
        if header[:3] == b"ID3" and len(header) == 10:
            audio_offset = 10 + _synchsafe(header[6:10])
            if header[5] & 0x10:
                audio_offset += 10
        source.seek(audio_offset)
        sample = source.read(min(256 * 1024, max(0, size - audio_offset)))

    bitrate_v1_l3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
    bitrate_v2_l3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
    sample_rates = (44100, 48000, 32000)
    frame_offset = None
    bitrate = sample_rate = 0
    for index in range(max(0, len(sample) - 4)):
        value = int.from_bytes(sample[index : index + 4], "big")
        if value & 0xFFE00000 != 0xFFE00000:
            continue
        version_bits = (value >> 19) & 0b11
        layer_bits = (value >> 17) & 0b11
        bitrate_index = (value >> 12) & 0b1111
        rate_index = (value >> 10) & 0b11
        if version_bits == 0b01 or layer_bits != 0b01 or bitrate_index in {0, 15} or rate_index == 3:
            continue
        bitrate_kbps = (
            bitrate_v1_l3[bitrate_index]
            if version_bits == 0b11
            else bitrate_v2_l3[bitrate_index]
        )
        rate = sample_rates[rate_index]
        if version_bits == 0b10:
            rate //= 2
        elif version_bits == 0b00:
            rate //= 4
        if not bitrate_kbps or not rate:
            continue
        frame_offset = audio_offset + index
        bitrate = bitrate_kbps * 1000
        sample_rate = rate
        break
    if frame_offset is None:
        raise MaterialSourceError(f"No valid MPEG Layer III frame found in {path.name}")

    audio_bytes = size - frame_offset
    with path.open("rb") as source:
        if size >= 128:
            source.seek(-128, 2)
            if source.read(3) == b"TAG":
                audio_bytes -= 128
    duration = max(0.001, (audio_bytes * 8) / bitrate)
    return round(duration, 3), bitrate, sample_rate


def _is_inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _relative(path: Path, root: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not _is_inside(resolved_path, resolved_root):
        raise MaterialSourceError(f"Material path escapes its configured root: {path}")
    return resolved_path.relative_to(resolved_root).as_posix()


def _natural_key(value: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value))


def _book_id(standard: str, level: int, volume: str | None, kind: str) -> str:
    edition = standard.replace(".", "")
    volume_token = volume.lower() if volume else "full"
    return f"hsk{edition}-l{level:02d}-v{volume_token}-{kind}"


def _collection_slug(standard: str, level: int) -> str:
    return f"hsk-{standard.replace('.', '-')}-level-{level}"


def _book_title(standard: str, level: int, volume: str | None, kind: str) -> str:
    labels = {
        "textbook": "Textbook",
        "workbook": "Workbook",
        "writing": "Writing practice",
        "answers": "Workbook answer key",
    }
    edition_prefix = "New HSK" if standard == "3.0" else "HSK"
    volume_suffix = volume or ""
    return f"{edition_prefix} {level}{volume_suffix} {labels[kind]}"


class ManifestBuilder:
    def __init__(
        self,
        source_root: Path | None = None,
        output_root: Path | None = None,
        manifest_path: Path | None = None,
    ):
        self.source_root = (source_root or settings.materials_root).resolve()
        self.output_root = (output_root or settings.materials_storage_root).resolve()
        if _is_inside(self.output_root, self.source_root) or _is_inside(self.source_root, self.output_root):
            raise MaterialSourceError("Material source and generated storage must be separate directories")
        self.manifest_path = (
            manifest_path
            or (self.output_root / "manifest.json" if output_root is not None else settings.materials_manifest_path)
        ).resolve()
        self._managed_path(self.manifest_path)
        self.assets: dict[str, dict[str, Any]] = {}
        self.bundles: dict[str, dict[str, Any]] = {}
        self.collections: list[dict[str, Any]] = []
        self.references: list[dict[str, Any]] = []
        self._previous_assets = self._load_previous_assets()

    def _load_previous_assets(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.manifest_path
        if not manifest_path.is_file():
            return {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload.get("assets", {}) if isinstance(payload, dict) else {}

    def _managed_path(self, path: Path) -> Path:
        if not _is_inside(path.resolve(), self.output_root):
            raise MaterialSourceError("Generated material path escapes managed storage")
        return path

    def _asset(
        self,
        *,
        asset_id: str,
        path: Path,
        root: str,
        kind: str,
        media_type: str,
        filename: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        configured_root = self.source_root if root == "source" else self.output_root
        if asset_id in self.assets:
            raise MaterialSourceError(f"Multiple source files map to the same material: {asset_id}")
        relative_path = _relative(path, configured_root)
        file_stat = path.stat()
        previous = self._previous_assets.get(asset_id, {})
        unchanged = (
            kind != "audio_archive"
            and previous.get("root") == root
            and previous.get("path") == relative_path
            and previous.get("size_bytes") == file_stat.st_size
            and previous.get("mtime_ns") == file_stat.st_mtime_ns
            and previous.get("sha256")
        )
        record: dict[str, Any] = {
            "id": asset_id,
            "root": root,
            "path": relative_path,
            "kind": kind,
            "media_type": media_type,
            "filename": _safe_filename(filename or path.name),
            "size_bytes": file_stat.st_size,
            "mtime_ns": file_stat.st_mtime_ns,
            "sha256": previous["sha256"] if unchanged else _sha256(path),
        }
        if extra:
            record.update(extra)
        self.assets[asset_id] = record
        return record

    def _normalized_cover(self, source: Path, collection_id: str) -> dict[str, Any]:
        cover_dir = self._managed_path(self.output_root / "covers")
        cover_dir.mkdir(parents=True, exist_ok=True)
        output = self._managed_path(cover_dir / f"{collection_id}.webp")
        regenerate = not output.exists() or output.stat().st_mtime_ns != source.stat().st_mtime_ns
        if regenerate:
            try:
                with Image.open(source) as image:
                    rgb = image.convert("RGB")
                    fitted = ImageOps.fit(
                        rgb,
                        (720, 960),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5),
                    )
                    temporary = self._managed_path(output.with_suffix(".webp.tmp"))
                    fitted.save(temporary, "WEBP", quality=88, method=6)
                    os.utime(temporary, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
                    temporary.replace(output)
            except Exception as exc:
                # The supplied files use an AVIF payload despite a .png suffix.
                # If this Pillow build cannot decode AVIF, serving the original
                # with its sniffed MIME type remains correct and safe.
                with source.open("rb") as image_source:
                    signature = image_source.read(64)
                if b"ftypavif" not in signature and b"ftypavis" not in signature:
                    raise MaterialSourceError(f"Unreadable cover: {source.name}") from exc
                return self._asset(
                    asset_id=f"{collection_id}-cover",
                    path=source,
                    root="source",
                    kind="cover",
                    media_type="image/avif",
                    filename=f"{collection_id}-cover.avif",
                )
        return self._asset(
            asset_id=f"{collection_id}-cover",
            path=output,
            root="storage",
            kind="cover",
            media_type="image/webp",
            filename=f"{collection_id}-cover.webp",
        )

    def _document_asset(
        self,
        path: Path,
        book_id: str,
        *,
        kind: str,
    ) -> tuple[dict[str, Any], int]:
        try:
            with pymupdf.open(path) as document:
                if document.needs_pass:
                    raise MaterialSourceError(f"Encrypted study book is not supported: {path.name}")
                pages = len(document)
        except MaterialSourceError:
            raise
        except Exception as exc:
            raise MaterialSourceError(f"Unreadable study book {path.name}: {exc}") from exc
        asset = self._asset(
            asset_id=f"{book_id}-pdf",
            path=path,
            root="source",
            kind="document",
            media_type=PDF_MIME,
            extra={"page_count": pages, "book_id": book_id, "book_kind": kind},
        )
        return asset, pages

    def _book_cover(self, source_pdf: Path, book_id: str) -> dict[str, Any]:
        cover_dir = self._managed_path(self.output_root / "covers" / "books")
        cover_dir.mkdir(parents=True, exist_ok=True)
        output = self._managed_path(cover_dir / f"{book_id}.webp")
        regenerate = not output.exists() or output.stat().st_mtime_ns != source_pdf.stat().st_mtime_ns
        if regenerate:
            with pymupdf.open(source_pdf) as document:
                page = document[0]
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                fitted = ImageOps.contain(image, (700, 940), method=Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (720, 960), "#f7f4ed")
                canvas.paste(fitted, ((720 - fitted.width) // 2, (960 - fitted.height) // 2))
                temporary = self._managed_path(output.with_suffix(".webp.tmp"))
                canvas.save(temporary, "WEBP", quality=86, method=6)
            os.utime(temporary, ns=(source_pdf.stat().st_atime_ns, source_pdf.stat().st_mtime_ns))
            temporary.replace(output)
        return self._asset(
            asset_id=f"{book_id}-cover",
            path=output,
            root="storage",
            kind="cover",
            media_type="image/webp",
            filename=f"{book_id}-cover.webp",
            extra={"book_id": book_id},
        )

    def _track_asset(
        self,
        path: Path,
        *,
        book_id: str,
        lesson_number: int,
        track_number: int,
        root: str,
    ) -> tuple[dict[str, Any], float]:
        try:
            duration, bitrate, sample_rate = _read_mp3_info(path)
        except Exception as exc:
            raise MaterialSourceError(f"Invalid MP3 file {path}: {exc}") from exc
        asset_id = f"{book_id}-u{lesson_number:02d}-t{track_number:02d}"
        asset = self._asset(
            asset_id=asset_id,
            path=path,
            root=root,
            kind="audio_track",
            media_type=MP3_MIME,
            extra={
                "book_id": book_id,
                "lesson_number": lesson_number,
                "track_number": track_number,
                "duration_seconds": duration,
                "bitrate": bitrate,
                "sample_rate": sample_rate,
            },
        )
        return asset, duration

    def _register_bundles(
        self,
        book: dict[str, Any],
        document_asset: dict[str, Any],
        lessons: list[dict[str, Any]],
        *,
        archive_asset: dict[str, Any] | None = None,
    ) -> None:
        tracks = [track for lesson in lessons for track in lesson["tracks"]]
        if not tracks:
            return
        base_name = _safe_filename(book["title"].replace(" ", "-"))
        audio_id = f"{book['id']}-audio-bundle"
        complete_id = f"{book['id']}-complete-bundle"
        audio_items = []
        for lesson in lessons:
            lesson_folder = (
                "Supplementary"
                if lesson["kind"] == "supplemental"
                else f"Lesson-{lesson['lesson_number']:02d}"
            )
            for track in lesson["tracks"]:
                audio_items.append(
                    {
                        "asset_id": track["asset_id"],
                        "archive_path": f"Audio/{lesson_folder}/Track-{track['order']:02d}.mp3",
                    }
                )
        audio_size = sum(self.assets[item["asset_id"]]["size_bytes"] for item in audio_items)
        self.bundles[audio_id] = {
            "id": audio_id,
            "book_id": book["id"],
            "kind": "audio",
            "filename": f"{base_name}-Audio.zip",
            "media_type": ZIP_MIME,
            "items": audio_items,
            "size_bytes": archive_asset["size_bytes"] if archive_asset else audio_size,
            "prebuilt_asset_id": archive_asset["id"] if archive_asset else None,
        }
        complete_items = [
            {
                "asset_id": document_asset["id"],
                "archive_path": f"Book/{document_asset['filename']}",
            },
            *audio_items,
        ]
        self.bundles[complete_id] = {
            "id": complete_id,
            "book_id": book["id"],
            "kind": "complete",
            "filename": f"{base_name}-Book-and-Audio.zip",
            "media_type": ZIP_MIME,
            "items": complete_items,
            "size_bytes": document_asset["size_bytes"] + audio_size,
            "prebuilt_asset_id": None,
        }
        book["audio_bundle_id"] = audio_id
        book["complete_bundle_id"] = complete_id

    def _hsk20_lessons(
        self,
        audio_dir: Path,
        book_id: str,
        *,
        supplemental_after: int | None = None,
    ) -> list[dict[str, Any]]:
        lessons: list[dict[str, Any]] = []
        for lesson_dir in sorted(
            (path for path in audio_dir.iterdir() if path.is_dir()),
            key=lambda path: _natural_key(path.name),
        ):
            match = _LESSON_RE.fullmatch(lesson_dir.name)
            if match is None:
                continue
            lesson_number = int(match.group("number"))
            files = sorted(lesson_dir.glob("*.mp3"), key=lambda path: _natural_key(path.name))
            if not files:
                continue
            supplemental = supplemental_after is not None and lesson_number > supplemental_after
            tracks: list[dict[str, Any]] = []
            seen_numbers: set[int] = set()
            for fallback_order, path in enumerate(files, start=1):
                parsed = _FOUR_DIGIT_TRACK_RE.search(path.stem)
                if parsed:
                    if int(parsed.group("lesson")) != lesson_number:
                        raise MaterialSourceError(f"Lesson mismatch in audio filename: {path.name}")
                    track_number = int(parsed.group("track"))
                else:
                    track_number = fallback_order
                if track_number in seen_numbers or track_number < 1:
                    raise MaterialSourceError(f"Duplicate or invalid track in lesson: {path.name}")
                seen_numbers.add(track_number)
                asset, duration = self._track_asset(
                    path,
                    book_id=book_id,
                    lesson_number=lesson_number,
                    track_number=track_number,
                    root="source",
                )
                tracks.append(
                    {
                        "id": asset["id"],
                        "asset_id": asset["id"],
                        "title": "Final review" if supplemental else f"Track {track_number:02d}",
                        "filename": asset["filename"],
                        "lesson_number": lesson_number,
                        "order": track_number,
                        "duration_seconds": duration,
                        "size_bytes": asset["size_bytes"],
                    }
                )
            lessons.append(
                {
                    "id": f"{book_id}-u{lesson_number:02d}",
                    "lesson_number": lesson_number,
                    "title": "Final review audio" if supplemental else f"Lesson {lesson_number:02d}",
                    "kind": "supplemental" if supplemental else "lesson",
                    "order": lesson_number,
                    "tracks": tracks,
                }
            )
        return lessons

    @staticmethod
    def _maximum_lesson(audio_dir: Path | None) -> int | None:
        if audio_dir is None:
            return None
        numbers = []
        for path in audio_dir.iterdir():
            match = _LESSON_RE.fullmatch(path.name) if path.is_dir() else None
            if match:
                numbers.append(int(match.group("number")))
        return max(numbers) if numbers else None

    def _build_hsk20(self) -> None:
        edition_root = self.source_root / "HSK2.0"
        if not edition_root.is_dir():
            raise MaterialSourceError(f"Missing HSK 2.0 source directory: {edition_root}")
        for level in range(1, 7):
            level_root = edition_root / f"HSK{level}"
            if not level_root.is_dir():
                continue
            collection_id = f"hsk20-l{level:02d}"
            cover_candidates = sorted(level_root.glob("*cover.*"))
            if not cover_candidates:
                raise MaterialSourceError(f"Missing cover for HSK 2.0 Level {level}")
            cover = self._normalized_cover(cover_candidates[0], collection_id)

            audio_dirs: dict[tuple[str | None, str], Path] = {}
            for directory in level_root.iterdir():
                if not directory.is_dir():
                    continue
                match = _AUDIO_DIR_RE.fullmatch(directory.name)
                if match:
                    if int(match.group("level")) != level:
                        raise MaterialSourceError(f"Audio directory level mismatch: {directory.name}")
                    volume = match.group("volume").upper() if match.group("volume") else None
                    audio_dirs[(volume, match.group("kind").lower())] = directory

            books: list[dict[str, Any]] = []
            pdfs = sorted(level_root.rglob("*.pdf"), key=lambda path: _natural_key(str(path)))
            if not pdfs:
                raise MaterialSourceError(f"No PDF books found for HSK 2.0 Level {level}")
            for pdf in pdfs:
                lowered = pdf.stem.lower()
                if "answer" in lowered:
                    kind, volume = "answers", None
                else:
                    match = _BOOK_RE.fullmatch(lowered)
                    if match is None:
                        raise MaterialSourceError(f"Unrecognized HSK 2.0 book name: {pdf.name}")
                    if int(match.group("level")) != level:
                        raise MaterialSourceError(f"Book level mismatch: {pdf.name}")
                    kind = match.group("kind").lower()
                    volume = match.group("volume").upper() if match.group("volume") else None
                book_id = _book_id("2.0", level, volume, kind)
                document, page_count = self._document_asset(pdf, book_id, kind=kind)
                book_cover = self._book_cover(pdf, book_id)
                canonical_lesson_end = (
                    self._maximum_lesson(audio_dirs.get((volume, "textbook")))
                    if kind == "workbook"
                    else None
                )
                lessons = (
                    self._hsk20_lessons(
                        audio_dirs[(volume, kind)],
                        book_id,
                        supplemental_after=canonical_lesson_end,
                    )
                    if (volume, kind) in audio_dirs
                    else []
                )
                track_count = sum(len(lesson["tracks"]) for lesson in lessons)
                audio_size = sum(
                    track["size_bytes"] for lesson in lessons for track in lesson["tracks"]
                )
                book: dict[str, Any] = {
                    "id": book_id,
                    "slug": book_id,
                    "title": _book_title("2.0", level, volume, kind),
                    "description": "Read the supplied book and study its lesson audio."
                    if lessons
                    else "Reference PDF included with this level.",
                    "kind": kind,
                    "volume": volume,
                    "cover_url": f"/api/materials/covers/{book_cover['id']}",
                    "pdf_asset_id": document["id"],
                    "page_count": page_count,
                    "size_bytes": document["size_bytes"],
                    "audio_size_bytes": audio_size,
                    "viewable": True,
                    "downloadable": True,
                    "has_audio": bool(lessons),
                    "lesson_count": len(lessons),
                    "audio_track_count": track_count,
                    "lessons": lessons,
                    "audio_bundle_id": None,
                    "complete_bundle_id": None,
                }
                self._register_bundles(book, document, lessons)
                books.append(book)

            kind_order = {"textbook": 0, "workbook": 1, "writing": 2, "answers": 3}
            books.sort(key=lambda item: (item["volume"] or "", kind_order[item["kind"]]))
            self.collections.append(
                self._collection(
                    standard="2.0",
                    level=level,
                    level_root=level_root,
                    cover=cover,
                    books=books,
                    note="Levels 4–6 are supplied as A and B volumes." if level >= 4 else "",
                )
            )

    def _safe_zip_members(self, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        members: list[zipfile.ZipInfo] = []
        seen: set[str] = set()
        total_size = 0
        for info in archive.infolist():
            normalized = PurePosixPath(info.filename.replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts or any(":" in part for part in normalized.parts):
                raise MaterialSourceError("Study audio ZIP contains an unsafe path")
            if info.is_dir():
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                raise MaterialSourceError("Study audio ZIP may not contain symbolic links")
            if normalized.suffix.lower() != ".mp3":
                raise MaterialSourceError(f"Unsupported file in study audio ZIP: {normalized.name}")
            folded = normalized.as_posix().casefold()
            if folded in seen:
                raise MaterialSourceError("Study audio ZIP contains colliding paths")
            seen.add(folded)
            total_size += info.file_size
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > settings.material_zip_max_ratio:
                raise MaterialSourceError("Study audio ZIP exceeds the safe compression ratio")
            members.append(info)
        if len(members) > settings.material_zip_max_files:
            raise MaterialSourceError("Study audio ZIP contains too many files")
        if total_size > settings.material_zip_max_uncompressed_mb * 1024 * 1024:
            raise MaterialSourceError("Study audio ZIP is larger than the configured safe limit")
        return members

    def _hsk30_lessons(
        self, archive_path: Path, *, level: int, book_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        archive_asset = self._asset(
            asset_id=f"{book_id}-original-audio-zip",
            path=archive_path,
            root="source",
            kind="audio_archive",
            media_type=ZIP_MIME,
            filename=f"New-HSK-{level}-Textbook-Audio.zip",
            extra={"book_id": book_id},
        )
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        extract_root = self.output_root / "extracted" / f"hsk30-l{level:02d}" / "textbook"
        with zipfile.ZipFile(archive_path) as archive:
            members = self._safe_zip_members(archive)
            parsed_members = []
            seen_tracks = set()
            for info in members:
                member = PurePosixPath(info.filename.replace("\\", "/"))
                lesson_parts = [
                    _LESSON_RE.fullmatch(part)
                    for part in member.parts[:-1]
                    if _LESSON_RE.fullmatch(part)
                ]
                if not lesson_parts:
                    raise MaterialSourceError(f"Cannot identify lesson for ZIP member: {info.filename}")
                lesson_number = int(lesson_parts[-1].group("number"))
                filename_match = _NEW_TRACK_RE.search(member.stem)
                if filename_match is None:
                    raise MaterialSourceError(f"Cannot identify track for ZIP member: {info.filename}")
                if int(filename_match.group("lesson")) != lesson_number:
                    raise MaterialSourceError(f"Lesson mismatch in ZIP member: {info.filename}")
                track_number = int(filename_match.group("track"))
                if lesson_number < 1 or track_number < 1 or (lesson_number, track_number) in seen_tracks:
                    raise MaterialSourceError("ZIP contains an invalid or duplicate lesson/track mapping")
                seen_tracks.add((lesson_number, track_number))
                parsed_members.append((info, lesson_number, track_number))
            for info, lesson_number, track_number in parsed_members:
                destination = self._managed_path(
                    extract_root / f"lesson-{lesson_number:02d}" / f"track-{track_number:02d}.mp3"
                )
                if destination.exists() and not _matches_zip_member(destination, info):
                    # A replaced track gets a new private file; the last published
                    # manifest remains usable if a later part of import fails.
                    destination = self._managed_path(
                        destination.with_name(f"track-{track_number:02d}-{info.CRC:08x}.mp3")
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not _matches_zip_member(destination, info):
                    temporary = self._managed_path(destination.with_suffix(".tmp"))
                    with archive.open(info) as source, temporary.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    temporary.replace(destination)
                asset, duration = self._track_asset(
                    destination,
                    book_id=book_id,
                    lesson_number=lesson_number,
                    track_number=track_number,
                    root="storage",
                )
                grouped[lesson_number].append(
                    {
                        "id": asset["id"],
                        "asset_id": asset["id"],
                        "title": f"Track {track_number:02d}",
                        "filename": asset["filename"],
                        "lesson_number": lesson_number,
                        "order": track_number,
                        "duration_seconds": duration,
                        "size_bytes": asset["size_bytes"],
                    }
                )
        lessons = [
            {
                "id": f"{book_id}-u{lesson_number:02d}",
                "lesson_number": lesson_number,
                "title": f"Lesson {lesson_number:02d}",
                "kind": "lesson",
                "order": lesson_number,
                "tracks": sorted(tracks, key=lambda item: item["order"]),
            }
            for lesson_number, tracks in sorted(grouped.items())
        ]
        return lessons, archive_asset

    def _build_hsk30(self) -> None:
        edition_root = self.source_root / "HSK3.0"
        if not edition_root.is_dir():
            raise MaterialSourceError(f"Missing HSK 3.0 source directory: {edition_root}")
        for level in range(1, 7):
            level_root = edition_root / f"HSK{level}"
            if not level_root.is_dir():
                continue
            collection_id = f"hsk30-l{level:02d}"
            cover_candidates = sorted(level_root.glob("*cover.*"))
            if not cover_candidates:
                raise MaterialSourceError(f"Missing cover for HSK 3.0 Level {level}")
            cover = self._normalized_cover(cover_candidates[0], collection_id)
            audio_archives = sorted(level_root.glob("*.zip"))
            if len(audio_archives) > 1:
                raise MaterialSourceError(f"Multiple textbook audio archives need review for HSK 3.0 Level {level}")

            books: list[dict[str, Any]] = []
            for pdf in sorted(level_root.glob("*.pdf"), key=lambda path: _natural_key(path.name)):
                lowered = pdf.stem.lower()
                if lowered not in {f"hsk-course-{level}", f"hsk-course-{level}-workbook", f"hsk-course-{level}-writing"}:
                    raise MaterialSourceError(f"Unrecognized HSK 3.0 book name: {pdf.name}")
                if lowered.endswith("-workbook"):
                    kind = "workbook"
                elif lowered.endswith("-writing"):
                    kind = "writing"
                else:
                    kind = "textbook"
                book_id = _book_id("3.0", level, None, kind)
                document, page_count = self._document_asset(pdf, book_id, kind=kind)
                book_cover = self._book_cover(pdf, book_id)
                lessons: list[dict[str, Any]] = []
                archive_asset = None
                if kind == "textbook" and audio_archives:
                    lessons, archive_asset = self._hsk30_lessons(
                        audio_archives[0], level=level, book_id=book_id
                    )
                track_count = sum(len(lesson["tracks"]) for lesson in lessons)
                audio_size = sum(
                    track["size_bytes"] for lesson in lessons for track in lesson["tracks"]
                )
                book: dict[str, Any] = {
                    "id": book_id,
                    "slug": book_id,
                    "title": _book_title("3.0", level, None, kind),
                    "description": "Read the supplied course book and study its lesson audio."
                    if lessons
                    else "Supplementary practice PDF included with this level.",
                    "kind": kind,
                    "volume": None,
                    "cover_url": f"/api/materials/covers/{book_cover['id']}",
                    "pdf_asset_id": document["id"],
                    "page_count": page_count,
                    "size_bytes": document["size_bytes"],
                    "audio_size_bytes": audio_size,
                    "viewable": True,
                    "downloadable": True,
                    "has_audio": bool(lessons),
                    "lesson_count": len(lessons),
                    "audio_track_count": track_count,
                    "lessons": lessons,
                    "audio_bundle_id": None,
                    "complete_bundle_id": None,
                }
                self._register_bundles(
                    book, document, lessons, archive_asset=archive_asset
                )
                books.append(book)
            if not books:
                raise MaterialSourceError(f"No PDF books found for HSK 3.0 Level {level}")
            kind_order = {"textbook": 0, "workbook": 1, "writing": 2, "answers": 3}
            books.sort(key=lambda item: kind_order[item["kind"]])
            gaps = []
            if not any(book["kind"] == "workbook" for book in books):
                gaps.append("workbook")
            if not any(book["kind"] == "writing" for book in books):
                gaps.append("writing practice")
            note = (
                f"This supplied level does not include {' or '.join(gaps)}."
                if gaps
                else "Textbook audio is included; workbook audio is not supplied."
            )
            self.collections.append(
                self._collection(
                    standard="3.0",
                    level=level,
                    level_root=level_root,
                    cover=cover,
                    books=books,
                    note=note,
                )
            )

    def _build_vocabulary(self) -> None:
        """Index the optional vocabulary documents without inventing lesson audio."""
        edition_root = self.source_root / "New_HSK_Vocabulary-1-9"
        if not edition_root.exists():
            return
        if not edition_root.is_dir():
            raise MaterialSourceError("The vocabulary source must be a directory")

        # Resolve the complete mapping before generating covers. Alternate L6 /
        # Level-6 spellings are accepted, but two files cannot claim one level.
        documents: dict[str, Path] = {}
        reference_path: Path | None = None
        for path in sorted(edition_root.rglob("*"), key=lambda item: _natural_key(item.name)):
            if not path.is_file():
                continue
            _relative(path, self.source_root)
            if path.parent != edition_root:
                raise MaterialSourceError(f"Unrecognized vocabulary source location: {path.name}")
            match = _VOCABULARY_BOOK_RE.fullmatch(path.name)
            if match:
                level_token = match.group("level")
                if level_token in documents:
                    raise MaterialSourceError(f"Multiple vocabulary PDFs map to Level {level_token}")
                documents[level_token] = path
            elif path.name.lower() == _VOCABULARY_REFERENCE_NAME:
                if reference_path is not None:
                    raise MaterialSourceError("Multiple vocabulary comparison references need review")
                reference_path = path
            else:
                raise MaterialSourceError(f"Unrecognized vocabulary source file: {path.name}")
        if not documents:
            raise MaterialSourceError("No PDF books found in the vocabulary source directory")

        if reference_path is not None:
            try:
                with Image.open(reference_path) as image:
                    if image.format != "PNG":
                        raise MaterialSourceError("The vocabulary comparison reference must contain a PNG image")
                    image.verify()
            except MaterialSourceError:
                raise
            except Exception as exc:
                raise MaterialSourceError("Unreadable vocabulary comparison reference") from exc

        for level_token, pdf in sorted(documents.items(), key=lambda item: _natural_key(item[0])):
            level = 7 if level_token == "7-9" else int(level_token)
            level_label = "7–9" if level == 7 else str(level)
            level_end = 9 if level == 7 else level
            book_id = f"new-hsk-vocabulary-l{level_token}"
            document, page_count = self._document_asset(pdf, book_id, kind="vocabulary")
            if page_count < 1:
                raise MaterialSourceError(f"Vocabulary PDF has no pages: {pdf.name}")
            cover = self._book_cover(pdf, book_id)
            book = {
                "id": book_id,
                "slug": book_id,
                "title": f"New HSK Vocabulary · Level {level_label}",
                "description": "Read and download the supplied vocabulary list. No lesson audio is included.",
                "kind": "vocabulary",
                "volume": None,
                "cover_url": f"/api/materials/covers/{cover['id']}",
                "pdf_asset_id": document["id"],
                "page_count": page_count,
                "size_bytes": document["size_bytes"],
                "audio_size_bytes": 0,
                "viewable": True,
                "downloadable": True,
                "has_audio": False,
                "lesson_count": 0,
                "audio_track_count": 0,
                "lessons": [],
                "audio_bundle_id": None,
                "complete_bundle_id": None,
            }
            self.collections.append({
                "id": f"hsk-vocabulary-l{level_token}",
                "slug": f"hsk-vocabulary-level-{level_token}",
                "standard": "vocabulary",
                "level": level,
                "level_label": level_label,
                "level_end": level_end,
                "title": f"HSK {level_label} Vocabulary",
                "description": f"Supplied New HSK vocabulary PDF for Level {level_label}.",
                "status": "available",
                "available": True,
                "note": "Vocabulary reference PDF; no lesson audio is supplied.",
                "cover_asset_id": cover["id"],
                "cover_url": f"/api/materials/covers/{cover['id']}",
                "book_count": 1,
                "lesson_count": 0,
                "audio_track_count": 0,
                "audio_duration_seconds": 0,
                "total_size_bytes": document["size_bytes"],
                "books": [book],
            })

        if reference_path is not None:
            reference_id = "new-hsk-vocabulary-comparison"
            asset = self._asset(
                asset_id=f"{reference_id}-image",
                path=reference_path,
                root="source",
                kind="document",
                media_type="image/png",
            )
            self.references.append({
                "id": reference_id,
                "standard": "vocabulary",
                "asset_id": asset["id"],
                "title": "New vs old HSK vocabulary comparison",
                "description": "Supplied comparison chart for reference; not verified as current official exam requirements.",
                "size_bytes": asset["size_bytes"],
                "media_type": asset["media_type"],
            })

    def _collection(
        self,
        *,
        standard: str,
        level: int,
        level_root: Path,
        cover: dict[str, Any],
        books: list[dict[str, Any]],
        note: str,
    ) -> dict[str, Any]:
        track_count = sum(book["audio_track_count"] for book in books)
        lesson_count = sum(book["lesson_count"] for book in books)
        audio_seconds = sum(
            track["duration_seconds"]
            for book in books
            for lesson in book["lessons"]
            for track in lesson["tracks"]
        )
        physical_size = sum(path.stat().st_size for path in level_root.rglob("*") if path.is_file())
        display_cover_id = f"{books[0]['id']}-cover" if books else cover["id"]
        return {
            "id": f"hsk{standard.replace('.', '')}-l{level:02d}",
            "slug": _collection_slug(standard, level),
            "standard": standard,
            "level": level,
            "title": f"HSK {level}",
            "description": (
                f"HSK {standard} Level {level} books and lesson-by-lesson audio."
            ),
            "status": "available",
            "available": True,
            "note": note,
            "cover_asset_id": display_cover_id,
            "cover_url": f"/api/materials/covers/{display_cover_id}",
            "book_count": len(books),
            "lesson_count": lesson_count,
            "audio_track_count": track_count,
            "audio_duration_seconds": round(audio_seconds, 3),
            "total_size_bytes": physical_size,
            "books": books,
        }

    def build(self) -> dict[str, Any]:
        if not self.source_root.is_dir():
            raise FileNotFoundError(f"Study-material source directory does not exist: {self.source_root}")
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._build_hsk20()
        self._build_hsk30()
        self._build_vocabulary()
        self.collections.sort(key=lambda item: (item["standard"], item["level"]))

        source_files = [path for path in self.source_root.rglob("*") if path.is_file()]
        indexed_source_paths = {asset["path"] for asset in self.assets.values() if asset["root"] == "source"}
        # Covers are normalized into generated assets, but their sources are
        # also part of the inventory and must be accounted for explicitly.
        indexed_source_paths.update(
            _relative(path, self.source_root)
            for path in source_files
            if "cover" in path.stem.lower() and path.suffix.lower() in {".png", ".avif", ".webp", ".jpg", ".jpeg"}
            and len(path.relative_to(self.source_root).parts) == 3
            and any(path.parent.name == f"HSK{c['level']}" and path.parent.parent.name == f"HSK{c['standard']}" for c in self.collections)
        )
        unindexed = [_relative(path, self.source_root) for path in source_files if _relative(path, self.source_root) not in indexed_source_paths]
        if unindexed:
            raise MaterialSourceError("Unmapped source files need review: " + "; ".join(unindexed[:12]))
        pages = sum(book["page_count"] for collection in self.collections for book in collection["books"])
        track_count = sum(collection["audio_track_count"] for collection in self.collections)
        duration = sum(collection["audio_duration_seconds"] for collection in self.collections)
        books = sum(collection["book_count"] for collection in self.collections)
        digest = hashlib.sha256()
        for asset_id, asset in sorted(self.assets.items()):
            digest.update(asset_id.encode("utf-8"))
            digest.update(asset["sha256"].encode("ascii"))

        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "generated_at": _utc_iso(),
            "fingerprint": digest.hexdigest(),
            "totals": {
                "edition_count": 2 + int(any(item["standard"] == "vocabulary" for item in self.collections)),
                "collection_count": len(self.collections),
                "book_count": books,
                "lesson_count": sum(item["lesson_count"] for item in self.collections),
                "audio_track_count": track_count,
                "page_count": pages,
                "audio_duration_seconds": round(duration, 3),
                "source_file_count": len(source_files),
                "source_size_bytes": sum(path.stat().st_size for path in source_files),
            },
            "collections": self.collections,
            "references": self.references,
            "assets": self.assets,
            "bundles": self.bundles,
        }
        return manifest

    def write(self) -> dict[str, Any]:
        manifest = self.build()
        manifest_path = self._managed_path(self.manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._managed_path(manifest_path.with_suffix(".json.tmp"))
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(manifest_path)
        clear_manifest_cache()
        return manifest


def build_materials_manifest(
    source_root: Path | None = None,
    output_root: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    return ManifestBuilder(source_root=source_root, output_root=output_root, manifest_path=manifest_path).write()


def clear_manifest_cache() -> None:
    global _manifest_cache
    with _manifest_lock:
        _manifest_cache = None
    from app.services.object_storage import clear_cloud_manifest_cache

    clear_cloud_manifest_cache()


def load_materials_manifest() -> dict[str, Any]:
    global _manifest_cache
    if settings.b2_enabled:
        from app.services.object_storage import ObjectStorageError, cloud_materials_manifest

        try:
            manifest = cloud_materials_manifest()
        except ObjectStorageError as exc:
            raise MaterialsNotIndexedError(str(exc)) from exc
        if (
            manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
            or not isinstance(manifest.get("collections"), list)
            or not isinstance(manifest.get("assets"), dict)
            or not isinstance(manifest.get("bundles"), dict)
        ):
            raise MaterialsNotIndexedError("The cloud study-material manifest is invalid; re-index and upload it")
        return manifest
    manifest_path = settings.materials_manifest_path.resolve()
    if not manifest_path.is_file():
        raise MaterialsNotIndexedError(
            "Study materials are not indexed. Run: python scripts/import_hsk_materials.py"
        )
    file_stat = manifest_path.stat()
    cache_key = (manifest_path, file_stat.st_mtime_ns, file_stat.st_size)
    with _manifest_lock:
        if _manifest_cache and _manifest_cache[0] == cache_key:
            return _manifest_cache[1]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MaterialsNotIndexedError("The study-material manifest is invalid; re-index the library") from exc
        if not isinstance(manifest, dict):
            raise MaterialsNotIndexedError("The study-material manifest is invalid; re-index the library")
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise MaterialsNotIndexedError("The study-material manifest version is unsupported; re-index it")
        if not isinstance(manifest.get("collections"), list):
            raise MaterialsNotIndexedError("The study-material manifest has no collections")
        _manifest_cache = (cache_key, manifest)
        return manifest


def _summary(collection: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in collection.items() if key != "books" and key != "cover_asset_id"}


def material_catalog() -> dict[str, Any]:
    manifest = load_materials_manifest()
    editions: list[dict[str, Any]] = []
    for standard, label in (("2.0", "HSK 2.0"), ("3.0", "HSK 3.0")):
        levels = [
            _summary(collection)
            for collection in manifest["collections"]
            if collection["standard"] == standard
        ]
        editions.append(
            {
                "id": standard,
                "label": label,
                "description": (
                    "The established six-level HSK course series."
                    if standard == "2.0"
                    else "The newer three-stage, nine-band framework; supplied materials currently cover Levels 1–3."
                ),
                "available_levels": [item["level"] for item in levels],
                "levels": levels,
            }
        )
    vocabulary_levels = [
        _summary(collection)
        for collection in manifest["collections"]
        if collection["standard"] == "vocabulary"
    ]
    vocabulary_references = [
        reference for reference in manifest.get("references", [])
        if reference.get("standard") == "vocabulary"
    ]
    if vocabulary_levels:
        editions.append({
            "id": "vocabulary",
            "label": "Vocabulary",
            "description": "Supplied New HSK vocabulary lists, with Levels 7–9 grouped in one PDF.",
            "available_levels": [item["level"] for item in vocabulary_levels],
            "levels": vocabulary_levels,
            "references": vocabulary_references,
        })
    return {"editions": editions, "totals": manifest["totals"], "generated_at": manifest["generated_at"]}


def material_collection(slug: str) -> dict[str, Any] | None:
    manifest = load_materials_manifest()
    return next((item for item in manifest["collections"] if item["slug"] == slug), None)


def material_asset(asset_id: str) -> dict[str, Any] | None:
    return load_materials_manifest().get("assets", {}).get(asset_id)


def material_bundle(bundle_id: str) -> dict[str, Any] | None:
    return load_materials_manifest().get("bundles", {}).get(bundle_id)


def resolve_material_path(resource: dict[str, Any]) -> Path:
    root_name = resource.get("root")
    if root_name == "source":
        root = settings.materials_root.resolve()
    elif root_name == "storage":
        root = settings.materials_storage_root.resolve()
    else:
        raise MaterialSourceError("Unknown material storage root")
    relative = PurePosixPath(str(resource.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise MaterialSourceError("Unsafe material path")
    path = (root / Path(*relative.parts)).resolve()
    if not _is_inside(path, root):
        raise MaterialSourceError("Unsafe material path")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path
