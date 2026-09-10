"""Validation and optional malware-scanner integration for admin uploads."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from app.core.config import settings


ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _has_valid_id3_header(sample: bytes, file_size: int) -> bool:
    if len(sample) < 10 or not sample.startswith(b"ID3"):
        return False
    # ID3v2 uses non-0xff version bytes and a four-byte synchsafe size. Reject
    # a forged prefix whose declared tag would extend beyond the upload.
    if sample[3] == 0xFF or sample[4] == 0xFF or any(byte & 0x80 for byte in sample[6:10]):
        return False
    tag_size = (
        (sample[6] << 21)
        | (sample[7] << 14)
        | (sample[8] << 7)
        | sample[9]
    )
    return 10 + tag_size <= file_size


def _has_valid_mpeg_audio_header(sample: bytes) -> bool:
    if len(sample) < 4 or sample[0] != 0xFF or sample[1] & 0xE0 != 0xE0:
        return False
    version = (sample[1] >> 3) & 0b11
    layer = (sample[1] >> 1) & 0b11
    bitrate_index = (sample[2] >> 4) & 0b1111
    sample_rate_index = (sample[2] >> 2) & 0b11
    # Reserved MPEG version/layer, free/invalid bitrate, and reserved sample
    # rate combinations are not valid MP3 frame headers.
    return (
        version != 0b01
        and layer != 0b00
        and bitrate_index not in {0, 0b1111}
        and sample_rate_index != 0b11
    )


def validate_zip_signature(path: Path) -> None:
    with path.open("rb") as source:
        signature = source.read(4)
    if signature not in ZIP_SIGNATURES:
        raise ValueError("Upload content is not a valid ZIP archive")


def validate_uploaded_media(path: Path) -> None:
    """Verify supported media by content, not only by its filename extension."""
    suffix = path.suffix.lower()
    with path.open("rb") as source:
        sample = source.read(256 * 1024)
    if suffix == ".pdf":
        # ISO 32000 readers permit leading bytes before the PDF header, but it
        # must occur within the first 1024 bytes.
        valid = b"%PDF-" in sample[:1024]
    elif suffix == ".mp3":
        valid = _has_valid_id3_header(
            sample, path.stat().st_size
        ) or _has_valid_mpeg_audio_header(sample)
    else:
        valid = False
    if not valid:
        raise ValueError(f"Uploaded {suffix or 'file'} content does not match its extension")


def scan_upload_for_malware(path: Path) -> None:
    """Run an administrator-configured scanner without invoking a shell.

    Example: ``HSK_MALWARE_SCAN_COMMAND=clamdscan --no-summary``.  The upload
    path is appended as the final argument. A missing, timed-out, or rejecting
    scanner fails closed whenever the setting is enabled.
    """
    command = (settings.malware_scan_command or "").strip()
    if not command:
        return
    arguments = shlex.split(command, posix=os.name != "nt")
    if not arguments:
        raise ValueError("Malware scanner command is invalid")
    try:
        completed = subprocess.run(
            [*arguments, str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=settings.malware_scan_timeout_seconds,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Upload malware scan could not be completed") from exc
    if completed.returncode != 0:
        raise ValueError("Upload was rejected by the malware scanner")
