from pathlib import Path
import zipfile

import pytest

from app.services.importer import (
    _option_labels,
    classify_pdfs,
    discover_bundles,
    parse_answer_pdf,
    safely_extract_bundle_zip,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "HSK_mock_test_bundles_exam_answers_audio_file"


def test_discovers_all_supplied_bundles() -> None:
    bundles = discover_bundles(SOURCE_ROOT)
    assert len(bundles) == 26
    assert {bundle.level for bundle in bundles} == {1, 2, 3, 4, 5, 6}


def test_h11329_answer_and_audio_detection() -> None:
    bundle = next(item for item in discover_bundles(SOURCE_ROOT) if item.test_code == "H11329")
    answers = parse_answer_pdf(bundle.answer_pdf, 40)
    assert len(answers) == 40
    assert answers[1] == "√"
    assert answers[6] == "C"
    assert answers[40] == "B"
    assert len(bundle.audio_files) == 21


def test_h31332_swapped_filenames_are_classified_by_content() -> None:
    root = SOURCE_ROOT / "HSK3" / "mock-test-HSK3-H31332"
    exam, answer, _ = classify_pdfs(root)
    assert exam.name.endswith("-answers.pdf")
    assert answer is not None
    assert answer.name.endswith("-exam.pdf")


def test_preserves_structured_and_writing_answers() -> None:
    bundles = {item.test_code: item for item in discover_bundles(SOURCE_ROOT)}
    hsk3 = parse_answer_pdf(bundles["H31327"].answer_pdf, 80)
    hsk4 = parse_answer_pdf(bundles["H41327"].answer_pdf, 100)
    hsk5 = parse_answer_pdf(bundles["H51327"].answer_pdf, 100)
    hsk6 = parse_answer_pdf(bundles["H61328"].answer_pdf, 101)

    assert len(hsk3) == 80
    assert hsk3[71] == "蛋糕被我吃了。"
    assert hsk4[56] == "CBA"
    assert hsk4[100] == "她们一边喝茶一边聊天儿。"
    assert len(hsk5) == 98
    assert 99 not in hsk5 and 100 not in hsk5
    assert len(hsk6) == 101
    assert hsk6[101] is None


def test_sentence_order_answers_become_clickable_tokens() -> None:
    assert _option_labels(4, 56, "CBA", None, "READING") == ["A", "B", "C"]


def test_uploaded_zip_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.pdf", b"not-a-real-pdf")

    with pytest.raises(ValueError, match="unsafe path"):
        safely_extract_bundle_zip(archive_path, tmp_path / "extracted")
    assert not (tmp_path / "outside.pdf").exists()


def test_uploaded_zip_rejects_unexpected_file_types(tmp_path: Path) -> None:
    archive_path = tmp_path / "unexpected.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("mock-test-HSK1-H10001/readme.exe", b"unexpected")

    with pytest.raises(ValueError, match="Unsupported file"):
        safely_extract_bundle_zip(archive_path, tmp_path / "extracted")
