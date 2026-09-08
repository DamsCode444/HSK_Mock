#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.materials_catalog import build_materials_manifest  # noqa: E402


def _summary(manifest: dict, manifest_path: Path) -> dict:
    return {
        "manifest": str(manifest_path),
        "generated_at": manifest["generated_at"],
        "fingerprint": manifest["fingerprint"],
        "totals": manifest["totals"],
        "collections": [
            {
                "slug": collection["slug"],
                "standard": collection["standard"],
                "level": collection["level"],
                "books": collection["book_count"],
                "lessons": collection["lesson_count"],
                "tracks": collection["audio_track_count"],
                "pages": sum(book["page_count"] for book in collection["books"]),
                "note": collection["note"],
            }
            for collection in manifest["collections"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Index HSK 2.0/3.0 books and lesson audio without copying the source library. "
            "Only normalized covers, the manifest, and ZIP-contained HSK 3.0 tracks are written."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=settings.materials_root,
        help="Study-material source root (defaults to HSK_MATERIALS_ROOT)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Managed index/extraction root (defaults to storage/materials)",
    )
    parser.add_argument("--manifest", type=Path, help="Manifest destination inside the managed output directory")
    args = parser.parse_args()
    output_root = (args.output or settings.materials_storage_root).resolve()
    manifest_path = (
        args.manifest
        or (output_root / "manifest.json" if args.output else settings.materials_manifest_path)
    ).resolve()
    manifest = build_materials_manifest(
        source_root=args.source.resolve(),
        output_root=output_root,
        manifest_path=manifest_path,
    )
    print(json.dumps(_summary(manifest, manifest_path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
