from __future__ import annotations

import struct
import zlib
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator


LOCAL_FILE_HEADER = 0x04034B50
DATA_DESCRIPTOR = 0x08074B50
CENTRAL_DIRECTORY_HEADER = 0x02014B50
END_OF_CENTRAL_DIRECTORY = 0x06054B50
UTF8_AND_DESCRIPTOR_FLAGS = 0x0808


def _dos_datetime(timestamp: float) -> tuple[int, int]:
    value = datetime.fromtimestamp(timestamp)
    year = min(2107, max(1980, value.year))
    dos_date = ((year - 1980) << 9) | (value.month << 5) | value.day
    dos_time = (value.hour << 11) | (value.minute << 5) | (value.second // 2)
    return dos_time, dos_date


def stored_zip_size(entries: Iterable[tuple[Path, str]]) -> int:
    """Validate the entire bundle before HTTP headers are sent."""
    total = 22  # End-of-central-directory record.
    seen = set()
    for path, archive_name in entries:
        name = archive_name.replace("\\", "/")
        member = PurePosixPath(name)
        if not name or member.is_absolute() or ".." in member.parts or ":" in name or "\x00" in name:
            raise ValueError("Unsafe path in generated ZIP")
        if name.casefold() in seen:
            raise ValueError("Duplicate path in generated ZIP")
        seen.add(name.casefold())
        name_size = len(name.encode("utf-8"))
        file_size = path.stat().st_size
        if name_size > 0xFFFF or file_size >= 0xFFFFFFFF or len(seen) >= 0xFFFF:
            raise ValueError("Generated study bundle exceeds ZIP32 limits")
        total += 30 + name_size + file_size + 16 + 46 + name_size
        if total >= 0xFFFFFFFF:
            raise ValueError("Generated study bundle exceeds ZIP32 limits")
    return total


def iter_stored_zip(
    entries: Iterable[tuple[Path, str]], *, chunk_size: int = 1024 * 1024
) -> Iterator[bytes]:
    """Stream a standards-compliant ZIP without staging or compressing files.

    All supplied study assets are already compressed PDF/MP3 data. ZIP_STORED
    avoids wasted CPU and lets multi-gigabyte downloads begin immediately.
    Individual source files and each generated bundle are constrained to ZIP32.
    """
    entries = tuple(entries)
    stored_zip_size(entries)
    central_records: list[tuple[bytes, int, int, int, int, int]] = []
    offset = 0
    seen: set[str] = set()

    for path, archive_name in entries:
        normalized_name = archive_name.replace("\\", "/").lstrip("/")
        if not normalized_name or ".." in normalized_name.split("/"):
            raise ValueError("Unsafe path in generated ZIP")
        folded = normalized_name.casefold()
        if folded in seen:
            raise ValueError("Duplicate path in generated ZIP")
        seen.add(folded)
        filename = normalized_name.encode("utf-8")
        file_stat = path.stat()
        if file_stat.st_size >= 0xFFFFFFFF or offset >= 0xFFFFFFFF:
            raise ValueError("Generated study bundle exceeds ZIP32 limits")
        dos_time, dos_date = _dos_datetime(file_stat.st_mtime)
        local_offset = offset
        local = struct.pack(
            "<IHHHHHIIIHH",
            LOCAL_FILE_HEADER,
            20,
            UTF8_AND_DESCRIPTOR_FLAGS,
            0,
            dos_time,
            dos_date,
            0,
            0,
            0,
            len(filename),
            0,
        ) + filename
        yield local
        offset += len(local)

        crc = 0
        written = 0
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(chunk_size), b""):
                crc = zlib.crc32(chunk, crc)
                written += len(chunk)
                offset += len(chunk)
                yield chunk
        if written != file_stat.st_size:
            raise ValueError("A study file changed during download; please retry")
        descriptor = struct.pack("<IIII", DATA_DESCRIPTOR, crc & 0xFFFFFFFF, written, written)
        yield descriptor
        offset += len(descriptor)
        central_records.append((filename, crc & 0xFFFFFFFF, written, dos_time, dos_date, local_offset))

    central_offset = offset
    for filename, crc, size, dos_time, dos_date, local_offset in central_records:
        central = struct.pack(
            "<IHHHHHHIIIHHHHHII",
            CENTRAL_DIRECTORY_HEADER,
            20,
            20,
            UTF8_AND_DESCRIPTOR_FLAGS,
            0,
            dos_time,
            dos_date,
            crc,
            size,
            size,
            len(filename),
            0,
            0,
            0,
            0,
            0o100644 << 16,
            local_offset,
        ) + filename
        yield central
        offset += len(central)

    central_size = offset - central_offset
    count = len(central_records)
    if count >= 0xFFFF:
        raise ValueError("Generated study bundle has too many files")
    yield struct.pack(
        "<IHHHHIIH",
        END_OF_CENTRAL_DIRECTORY,
        0,
        0,
        count,
        count,
        central_size,
        central_offset,
        0,
    )
