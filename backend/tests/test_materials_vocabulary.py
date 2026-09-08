from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from app.services import materials_catalog
from app.services.materials_catalog import ManifestBuilder, MaterialSourceError


def _pdf(path: Path, pages: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as document:
        for index in range(pages):
            page = document.new_page(width=300, height=400)
            page.insert_text((25, 40), f"Vocabulary fixture page {index + 1}")
        document.save(path)


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "white").save(path, "PNG")


@pytest.fixture()
def library(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    output = tmp_path / "generated"
    for edition, filename, pages in (
        ("HSK2.0", "hsk-1-textbook.pdf", 1),
        ("HSK3.0", "hsk-course-1.pdf", 2),
    ):
        level = source / edition / "HSK1"
        _pdf(level / filename, pages)
        _png(level / "book-cover.png")
    return source, output


def _vocabulary(source: Path, *, reference: bool = True) -> dict[str, int]:
    folder = source / "New_HSK_Vocabulary-1-9"
    page_counts = {str(level): level for level in range(1, 7)} | {"7-9": 7}
    for level, pages in page_counts.items():
        filename = f"New-HSK-Vocabulary-Level-{level}.pdf"
        if level == "6":
            filename = "New-HSK-Vocabulary-L6.pdf"
        _pdf(folder / filename, pages)
    if reference:
        _png(folder / "hsk new vs old vocabulary comparision.png")
    return page_counts


def test_indexes_vocabulary_pdf_pages_covers_and_private_reference(library, monkeypatch):
    source, output = library
    expected_pages = _vocabulary(source)
    manifest = ManifestBuilder(source, output).write()
    assert manifest["totals"]["edition_count"] == 3
    assert manifest["totals"]["collection_count"] == 9
    assert manifest["totals"]["book_count"] == 9
    assert manifest["totals"]["page_count"] == 3 + sum(expected_pages.values())
    assert manifest["totals"]["source_file_count"] == 12
    assert manifest["totals"]["audio_track_count"] == 0
    assert manifest["totals"]["lesson_count"] == 0
    assert manifest["totals"]["audio_duration_seconds"] == 0
    assert manifest["bundles"] == {}

    collections = [item for item in manifest["collections"] if item["standard"] == "vocabulary"]
    assert [item["level"] for item in collections] == list(range(1, 8))
    assert [item["level_label"] for item in collections] == ["1", "2", "3", "4", "5", "6", "7–9"]
    assert collections[-1]["level_end"] == 9
    for collection, (level, pages) in zip(collections, expected_pages.items(), strict=True):
        assert collection["slug"] == f"hsk-vocabulary-level-{level}"
        assert collection["book_count"] == 1
        book = collection["books"][0]
        assert book["id"] == book["slug"] == f"new-hsk-vocabulary-l{level}"
        assert book["kind"] == "vocabulary"
        assert book["page_count"] == pages
        assert book["has_audio"] is False
        assert book["lessons"] == []
        assert book["audio_track_count"] == book["lesson_count"] == book["audio_size_bytes"] == 0
        assert book["audio_bundle_id"] is None and book["complete_bundle_id"] is None
        document = manifest["assets"][book["pdf_asset_id"]]
        assert document["id"] == f"{book['id']}-pdf"
        assert document["kind"] == "document"
        assert document["root"] == "source"
        assert document["media_type"] == "application/pdf"
        assert document["page_count"] == pages
        assert collection["total_size_bytes"] == book["size_bytes"] == (source / document["path"]).stat().st_size
        cover = manifest["assets"][collection["cover_asset_id"]]
        assert cover["id"] == f"{book['id']}-cover"
        with Image.open(output / cover["path"]) as thumbnail:
            assert thumbnail.format == "WEBP"
            assert thumbnail.size == (720, 960)

    assert len(manifest["references"]) == 1
    reference = manifest["references"][0]
    assert reference["standard"] == "vocabulary"
    assert reference["id"] == "new-hsk-vocabulary-comparison"
    assert "not verified" in reference["description"]
    assert reference["media_type"] == "image/png"
    asset = manifest["assets"][reference["asset_id"]]
    # A document uses the existing authenticated grant endpoint, not public covers.
    assert asset["kind"] == "document"
    assert asset["root"] == "source"
    assert asset["media_type"] == "image/png"
    assert reference["size_bytes"] == (source / asset["path"]).stat().st_size
    monkeypatch.setattr(materials_catalog, "load_materials_manifest", lambda: manifest)
    catalog = materials_catalog.material_catalog()
    vocabulary_edition = catalog["editions"][-1]
    assert vocabulary_edition["id"] == "vocabulary"
    assert vocabulary_edition["label"] == "Vocabulary"
    assert vocabulary_edition["available_levels"] == list(range(1, 8))
    assert vocabulary_edition["references"] == manifest["references"]
    assert "books" not in vocabulary_edition["levels"][0]
    assert not {"path", "root", "sha256"}.intersection(vocabulary_edition["references"][0])


def test_vocabulary_reimport_stable_and_existing_editions_unchanged(library):
    source, output = library
    original = ManifestBuilder(source, output).write()
    _vocabulary(source)
    first = ManifestBuilder(source, output).write()
    second = ManifestBuilder(source, output).write()
    assert first["fingerprint"] == second["fingerprint"]
    assert first["assets"] == second["assets"]
    assert first["collections"] == second["collections"]
    assert first["references"] == second["references"]
    assert [item for item in first["collections"] if item["standard"] != "vocabulary"] == original["collections"]
    for asset_id, asset in original["assets"].items():
        assert first["assets"][asset_id] == asset


def test_missing_vocabulary_folder_preserves_two_edition_catalog(library, monkeypatch):
    source, output = library
    manifest = ManifestBuilder(source, output).write()
    assert manifest["totals"]["edition_count"] == 2
    assert manifest["totals"]["book_count"] == 2
    assert manifest["references"] == []
    # Older manifests did not contain the additive references field.
    manifest.pop("references")
    monkeypatch.setattr(materials_catalog, "load_materials_manifest", lambda: manifest)
    catalog = materials_catalog.material_catalog()
    assert [item["id"] for item in catalog["editions"]] == ["2.0", "3.0"]


def test_optional_comparison_image_is_not_required(library):
    source, output = library
    _vocabulary(source, reference=False)
    manifest = ManifestBuilder(source, output).build()
    assert manifest["totals"]["edition_count"] == 3
    assert manifest["references"] == []


@pytest.mark.parametrize("filename", [
    "New-HSK-Vocabulary-Level-8.pdf", "extra.mp3", "nested/New-HSK-Vocabulary-Level-1.pdf",
])
def test_rejects_unrecognized_vocabulary_files_before_generating_covers(tmp_path: Path, filename: str):
    source = tmp_path / "source"
    output = tmp_path / "generated"
    folder = source / "New_HSK_Vocabulary-1-9"
    _pdf(folder / "New-HSK-Vocabulary-L6.pdf")
    extra = folder / filename
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"unexpected file")
    builder = ManifestBuilder(source, output)
    with pytest.raises(MaterialSourceError, match="Unrecognized vocabulary"):
        builder._build_vocabulary()
    assert builder.assets == {}
    assert not (output / "covers").exists()


def test_rejects_duplicate_vocabulary_level_mapping_before_generating_covers(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "generated"
    folder = source / "New_HSK_Vocabulary-1-9"
    _pdf(folder / "New-HSK-Vocabulary-L6.pdf")
    _pdf(folder / "New-HSK-Vocabulary-Level-6.pdf")
    builder = ManifestBuilder(source, output)
    with pytest.raises(MaterialSourceError, match="Multiple vocabulary PDFs map to Level 6"):
        builder._build_vocabulary()
    assert builder.assets == {}
    assert not (output / "covers").exists()


def test_rejects_invalid_comparison_image_before_generating_covers(tmp_path: Path):
    source = tmp_path / "source"
    output = tmp_path / "generated"
    folder = source / "New_HSK_Vocabulary-1-9"
    _pdf(folder / "New-HSK-Vocabulary-L6.pdf")
    (folder / "hsk new vs old vocabulary comparision.png").write_bytes(b"not a PNG")
    builder = ManifestBuilder(source, output)
    with pytest.raises(MaterialSourceError, match="Unreadable vocabulary comparison"):
        builder._build_vocabulary()
    assert builder.assets == {}
    assert not (output / "covers").exists()


def test_rejects_empty_vocabulary_directory(tmp_path: Path):
    source = tmp_path / "source"
    (source / "New_HSK_Vocabulary-1-9").mkdir(parents=True)
    builder = ManifestBuilder(source, tmp_path / "generated")
    with pytest.raises(MaterialSourceError, match="No PDF books"):
        builder._build_vocabulary()
