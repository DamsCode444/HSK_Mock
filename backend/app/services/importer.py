from __future__ import annotations

import hashlib
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import pymupdf
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.uploads import (
    scan_upload_for_malware,
    validate_uploaded_media,
    validate_zip_signature,
)
from app.models import Answer, HskTest, ImportLog, Option, Question


LEVEL_CONFIG: dict[int, dict[str, Any]] = {
    1: {
        "total": 40,
        "duration": 40,
        "max_score": 200,
        "passing": 120,
        "sections": (("LISTENING", 1, 20), ("READING", 21, 40)),
    },
    2: {
        "total": 60,
        "duration": 55,
        "max_score": 200,
        "passing": 120,
        "sections": (("LISTENING", 1, 35), ("READING", 36, 60)),
    },
    3: {
        "total": 80,
        "duration": 90,
        "max_score": 300,
        "passing": 180,
        "sections": (
            ("LISTENING", 1, 40),
            ("READING", 41, 70),
            ("WRITING", 71, 80),
        ),
    },
    4: {
        "total": 100,
        "duration": 105,
        "max_score": 300,
        "passing": 180,
        "sections": (
            ("LISTENING", 1, 45),
            ("READING", 46, 85),
            ("WRITING", 86, 100),
        ),
    },
    5: {
        "total": 100,
        "duration": 125,
        "max_score": 300,
        "passing": 180,
        "sections": (
            ("LISTENING", 1, 45),
            ("READING", 46, 90),
            ("WRITING", 91, 100),
        ),
    },
    6: {
        "total": 101,
        "duration": 140,
        "max_score": 300,
        "passing": 180,
        "sections": (
            ("LISTENING", 1, 50),
            ("READING", 51, 100),
            ("WRITING", 101, 101),
        ),
    },
}

BUNDLE_PATTERN = re.compile(r"mock-test-HSK(?P<level>[1-6])-(?P<code>H\d+)$", re.I)
ANSWER_MARKER_PATTERN = re.compile(
    r"(?<![\d.])(?P<number>\d{1,3})\s*[．.](?!\d)"
)
QUESTION_MARKER_PATTERN = re.compile(
    r"(?<![\d.])(?P<number>\d{1,3})\s*[．.](?!\d)"
)
GROUPED_QUESTION_PATTERN = re.compile(
    r"(?<!\d)(?P<start>\d{1,3})\s*[-–—－]\s*(?P<end>\d{1,3})\s*[．.](?!\d)"
)
QUESTION_RANGE_PATTERN = re.compile(
    r"第\s*(?P<start>\d{1,3})\s*[-–—－~～]\s*(?P<end>\d{1,3})\s*题"
)
SINGLE_QUESTION_HEADING_PATTERN = re.compile(r"第\s*(?P<number>\d{1,3})\s*题")
OPTION_LABEL_PATTERN = re.compile(r"(?m)^\s*([A-F])(?:\s|$)")
AUDIO_NUMBER_PATTERN = re.compile(r"[-_](?P<number>\d{1,3})$")


@dataclass(frozen=True)
class Bundle:
    root: Path
    level: int
    test_code: str
    exam_pdf: Path
    answer_pdf: Path | None
    writing_pdf: Path | None
    audio_files: tuple[Path, ...]


@dataclass
class PageData:
    document: str
    page_number: int
    text: str
    exact_questions: set[int]
    ranged_questions: set[int]
    option_labels: set[str]
    image_path: str | None = None


def _pdf_text(path: Path, max_pages: int | None = None) -> tuple[str, int]:
    with pymupdf.open(path) as document:
        limit = len(document) if max_pages is None else min(len(document), max_pages)
        text = "\n".join(document[index].get_text("text") for index in range(limit))
        return text, len(document)


def _answer_density(text: str) -> int:
    matches = {
        int(match.group("number"))
        for match in ANSWER_MARKER_PATTERN.finditer(text)
        if 1 <= int(match.group("number")) <= 101
    }
    return len(matches)


def classify_pdfs(bundle_root: Path) -> tuple[Path, Path | None, Path | None]:
    pdfs = sorted(bundle_root.glob("*.pdf"))
    if not pdfs:
        raise ValueError(f"No PDF files found in {bundle_root}")

    writing_candidates = [path for path in pdfs if "writing" in path.stem.lower()]
    writing_pdf = writing_candidates[0] if writing_candidates else None
    candidates = [path for path in pdfs if path != writing_pdf]
    analysis: list[tuple[Path, int, int, str]] = []
    for path in candidates:
        text, pages = _pdf_text(path)
        analysis.append((path, pages, _answer_density(text), text[:2500]))

    likely_answers = sorted(
        analysis,
        key=lambda item: (
            bool(re.search(r"H\d+\s*卷答案", item[3])),
            item[2] / max(item[1], 1),
            -item[1],
            "answer" in item[0].stem.lower(),
        ),
        reverse=True,
    )
    answer_entry = None
    if likely_answers:
        candidate = likely_answers[0]
        has_answer_header = bool(re.search(r"H\d+\s*卷答案", candidate[3]))
        if has_answer_header or (candidate[1] <= 4 and candidate[2] >= 5):
            answer_entry = candidate
    answer_pdf = answer_entry[0] if answer_entry else None

    exam_entries = [item for item in analysis if item[0] != answer_pdf]
    if not exam_entries:
        exam_entries = analysis
    exam_pdf = max(
        exam_entries,
        key=lambda item: (
            item[1],
            "新汉语水平考试" in item[3],
            "exam" in item[0].stem.lower(),
        ),
    )[0]
    return exam_pdf, answer_pdf, writing_pdf


def discover_bundles(source_root: Path | None = None) -> list[Bundle]:
    source = (source_root or settings.source_bundle_root).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Bundle source directory does not exist: {source}")

    bundles: list[Bundle] = []
    for directory in sorted(path for path in source.rglob("mock-test-HSK*-H*") if path.is_dir()):
        match = BUNDLE_PATTERN.fullmatch(directory.name)
        if match is None:
            continue
        exam_pdf, answer_pdf, writing_pdf = classify_pdfs(directory)
        audio_files = tuple(sorted(directory.rglob("*.mp3")))
        bundles.append(
            Bundle(
                root=directory,
                level=int(match.group("level")),
                test_code=match.group("code").upper(),
                exam_pdf=exam_pdf,
                answer_pdf=answer_pdf,
                writing_pdf=writing_pdf,
                audio_files=audio_files,
            )
        )
    return bundles


def parse_answer_pdf(path: Path | None, total_questions: int) -> dict[int, str | None]:
    if path is None:
        return {}
    text, _ = _pdf_text(path)
    answers: dict[int, str | None] = {}
    for line in text.splitlines():
        markers = list(ANSWER_MARKER_PATTERN.finditer(line))
        for index, marker in enumerate(markers):
            number = int(marker.group("number"))
            if not 1 <= number <= total_questions:
                continue
            end = markers[index + 1].start() if index + 1 < len(markers) else len(line)
            value = re.sub(r"\s+", " ", line[marker.end() : end]).strip(" ，,；;\t")
            if not value:
                continue
            answers[number] = None if "略" in value else value.upper()
    return answers


def section_for_question(level: int, number: int) -> str:
    for section, start, end in LEVEL_CONFIG[level]["sections"]:
        if start <= number <= end:
            return section
    raise ValueError(f"Question {number} is outside the HSK {level} structure")


def _fingerprint(bundle: Bundle) -> str:
    digest = hashlib.sha256()
    paths = [bundle.exam_pdf, *(bundle.audio_files or ())]
    if bundle.answer_pdf:
        paths.append(bundle.answer_pdf)
    if bundle.writing_pdf:
        paths.append(bundle.writing_pdf)
    for path in sorted(paths):
        stat = path.stat()
        digest.update(path.name.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _storage_relative(path: Path) -> str:
    return path.resolve().relative_to(settings.storage_root.resolve()).as_posix()


def _copy_file(source: Path, destination_dir: Path) -> str:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if not destination.exists() or destination.stat().st_size != source.stat().st_size:
        shutil.copy2(source, destination)
    return _storage_relative(destination)


def _render_document_pages(
    source: Path,
    page_dir: Path,
    document_name: str,
    total_questions: int,
) -> list[PageData]:
    page_dir.mkdir(parents=True, exist_ok=True)
    pages: list[PageData] = []
    with pymupdf.open(source) as document:
        for index, page in enumerate(document):
            text = page.get_text("text").replace("\x00", "")
            if index == 0 and "新汉语水平考试" in text:
                exact_questions: set[int] = set()
            else:
                exact_questions = {
                    int(match.group("number"))
                    for match in QUESTION_MARKER_PATTERN.finditer(text)
                    if 1 <= int(match.group("number")) <= total_questions
                }
                for match in GROUPED_QUESTION_PATTERN.finditer(text):
                    start, end = int(match.group("start")), int(match.group("end"))
                    if 1 <= start <= end <= total_questions:
                        exact_questions.update(range(start, end + 1))
            ranged_questions: set[int] = set()
            for match in QUESTION_RANGE_PATTERN.finditer(text):
                start, end = int(match.group("start")), int(match.group("end"))
                if 1 <= start <= end <= total_questions:
                    ranged_questions.update(range(start, end + 1))
            for match in SINGLE_QUESTION_HEADING_PATTERN.finditer(text):
                number = int(match.group("number"))
                if 1 <= number <= total_questions:
                    ranged_questions.add(number)

            page_data = PageData(
                document=document_name,
                page_number=index + 1,
                text=text,
                exact_questions=exact_questions,
                ranged_questions=ranged_questions,
                option_labels=set(OPTION_LABEL_PATTERN.findall(text)),
            )
            if exact_questions or ranged_questions or document_name == "writing":
                output = page_dir / f"{document_name}-page-{index + 1:03}.webp"
                if not output.exists():
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False)
                    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                    image.save(output, "WEBP", quality=84, method=5)
                page_data.image_path = _storage_relative(output)
            pages.append(page_data)
    return pages


def _question_text(page: PageData | None, number: int) -> str:
    if page is None:
        return ""
    match = re.search(rf"(?<![\d.]){number}\s*[．.](?!\d)\s*", page.text)
    if match is None:
        return ""
    next_match = QUESTION_MARKER_PATTERN.search(page.text, match.end())
    end = next_match.start() if next_match else len(page.text)
    value = page.text[match.end() : end]
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    compact = " ".join(line for line in lines if line)
    return compact[:2000]


def _map_pages(pages: list[PageData], total_questions: int) -> dict[int, PageData]:
    mapped: dict[int, PageData] = {}
    for page in pages:
        for number in page.ranged_questions:
            mapped.setdefault(number, page)
    for page in pages:
        for number in page.exact_questions:
            mapped[number] = page

    available = sorted(mapped)
    for number in range(1, total_questions + 1):
        if number in mapped or not available:
            continue
        nearest = min(available, key=lambda candidate: abs(candidate - number))
        mapped[number] = mapped[nearest]
    return mapped


def _audio_mapping(bundle: Bundle, audio_paths: dict[Path, str]) -> tuple[dict[int, str], str | None]:
    clips: dict[int, str] = {}
    full_audio: str | None = None
    for source in bundle.audio_files:
        stem = source.stem
        match = AUDIO_NUMBER_PATTERN.search(stem)
        if match:
            number = int(match.group("number"))
            if 1 <= number <= LEVEL_CONFIG[bundle.level]["sections"][0][2]:
                clips[number] = audio_paths[source]
                continue
        if stem.upper() == bundle.test_code or full_audio is None:
            full_audio = audio_paths[source]
    return clips, full_audio


def _structured_option_labels(level: int, number: int) -> list[str] | None:
    ranges: dict[int, tuple[tuple[int, int, str], ...]] = {
        1: (
            (1, 5, "TF"), (6, 10, "ABC"), (11, 15, "ABCDEF"),
            (16, 20, "ABC"), (21, 25, "TF"), (26, 40, "ABCDEF"),
        ),
        2: (
            (1, 10, "TF"), (11, 20, "ABCDEF"), (21, 35, "ABC"),
            (36, 45, "ABCDEF"), (46, 50, "TF"), (51, 60, "ABCDEF"),
        ),
        3: (
            (1, 10, "ABCDEF"), (11, 20, "TF"), (21, 40, "ABC"),
            (41, 60, "ABCDEF"), (61, 70, "ABC"),
        ),
        4: ((1, 10, "TF"), (11, 45, "ABCD"), (46, 55, "ABCDEF"), (66, 85, "ABCD")),
        5: ((1, 90, "ABCD"),),
        6: ((1, 70, "ABCD"), (71, 80, "ABCDE"), (81, 100, "ABCD")),
    }
    for start, end, labels in ranges[level]:
        if start <= number <= end:
            return ["√", "×"] if labels == "TF" else list(labels)
    return None


def _option_labels(
    level: int, number: int, answer: str | None, page: PageData | None, section: str
) -> list[str]:
    if section == "WRITING" and (answer is None or answer not in "ABCDEF"):
        return []
    if answer in {"√", "×"}:
        return ["√", "×"]
    if isinstance(answer, str) and re.fullmatch(r"[A-F]{2,}", answer):
        return sorted(set(answer))
    labels = _structured_option_labels(level, number)
    if labels is not None:
        return labels
    page_labels = sorted(page.option_labels) if page else []
    answer_labels = [answer] if isinstance(answer, str) and answer in "ABCDEF" else []
    maximum = max(page_labels + answer_labels, default="D")
    maximum = max(maximum, "C")
    return [chr(code) for code in range(ord("A"), ord(maximum) + 1)]


def _question_type(section: str, answer: str | None) -> str:
    if answer in {"√", "×"}:
        return "true_false"
    if isinstance(answer, str) and re.fullmatch(r"[A-F]{2,}", answer):
        return "sentence_order"
    if section == "WRITING" and (answer is None or answer not in "ABCDEF"):
        return "writing"
    return "multiple_choice"


def _option_text(label: str) -> str | None:
    if label == "√":
        return "正确 / True"
    if label == "×":
        return "错误 / False"
    return None


def _combine_writing_pages(pages: list[PageData], output: Path) -> str | None:
    paths = [settings.storage_root / page.image_path for page in pages if page.image_path]
    if not paths:
        return None
    images = [Image.open(path).convert("RGB") for path in paths]
    try:
        width = max(image.width for image in images)
        height = sum(image.height for image in images)
        canvas = Image.new("RGB", (width, height), "white")
        y = 0
        for image in images:
            canvas.paste(image, (0, y))
            y += image.height
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, "WEBP", quality=84, method=5)
    finally:
        for image in images:
            image.close()
    return _storage_relative(output)


def import_bundle(db: Session, bundle: Bundle, force: bool = False) -> dict[str, Any]:
    config = LEVEL_CONFIG[bundle.level]
    fingerprint = _fingerprint(bundle)
    existing = db.scalar(
        select(HskTest)
        .options(selectinload(HskTest.questions).selectinload(Question.options))
        .where(HskTest.test_code == bundle.test_code)
    )
    if existing is not None and existing.source_fingerprint == fingerprint and not force:
        return {
            "status": "unchanged",
            "test_id": existing.id,
            "test_code": existing.test_code,
            **(existing.import_summary or {}),
        }

    base_dir = settings.storage_root / f"HSK{bundle.level}" / bundle.test_code
    pdf_dir, audio_dir, page_dir = base_dir / "pdf", base_dir / "audio", base_dir / "pages"
    exam_path = _copy_file(bundle.exam_pdf, pdf_dir)
    answer_path = _copy_file(bundle.answer_pdf, pdf_dir) if bundle.answer_pdf else None
    writing_path = _copy_file(bundle.writing_pdf, pdf_dir) if bundle.writing_pdf else None
    audio_paths = {source: _copy_file(source, audio_dir) for source in bundle.audio_files}

    answers = parse_answer_pdf(bundle.answer_pdf, config["total"])
    pages = _render_document_pages(
        bundle.exam_pdf, page_dir, "exam", config["total"]
    )
    if bundle.writing_pdf:
        pages.extend(
            _render_document_pages(
                bundle.writing_pdf, page_dir, "writing", config["total"]
            )
        )
    page_map = _map_pages(pages, config["total"])
    if bundle.level == 6 and bundle.writing_pdf:
        writing_pages = [page for page in pages if page.document == "writing"]
        if writing_pages:
            combined = _combine_writing_pages(
                writing_pages, page_dir / "writing-question-101.webp"
            )
            writing_pages[0].text = "\n".join(page.text for page in writing_pages)
            writing_pages[0].image_path = combined or writing_pages[0].image_path
            page_map[101] = writing_pages[0]

    clips, full_audio = _audio_mapping(bundle, audio_paths)
    missing_pages = [number for number in range(1, config["total"] + 1) if number not in page_map]
    missing_answers = [
        number
        for number in range(1, config["total"] + 1)
        if number not in answers and section_for_question(bundle.level, number) != "WRITING"
    ]
    warnings: list[str] = []
    if missing_pages:
        warnings.append(f"No source page could be mapped for {len(missing_pages)} questions")
    if missing_answers:
        warnings.append(f"No objective answer was extracted for {len(missing_answers)} questions")
    listening_end = config["sections"][0][2]
    if not full_audio and len(clips) < listening_end:
        warnings.append("Listening audio coverage is incomplete")

    summary: dict[str, Any] = {
        "expected_questions": config["total"],
        "imported_questions": config["total"],
        "answers_extracted": len(answers),
        "audio_files": len(bundle.audio_files),
        "individual_audio_mappings": len(clips),
        "rendered_pages": sum(1 for page in pages if page.image_path),
        "missing_page_questions": missing_pages,
        "missing_objective_answers": missing_answers,
        "warnings": warnings,
        "source_directory": str(bundle.root),
    }

    test = existing or HskTest(test_code=bundle.test_code)
    test.level = bundle.level
    test.title = f"HSK {bundle.level} Mock Test · {bundle.test_code}"
    test.description = "Imported automatically from the supplied official-style PDF and audio bundle."
    test.duration_minutes = config["duration"]
    test.max_score = config["max_score"]
    test.passing_score = config["passing"]
    test.status = "published" if not missing_pages else "draft"
    test.exam_file = exam_path
    test.answer_file = answer_path
    test.writing_file = writing_path
    test.full_audio_file = full_audio
    test.audio_play_limit = test.audio_play_limit or 1
    test.source_fingerprint = fingerprint
    test.import_summary = summary
    if existing is None:
        db.add(test)
        db.flush()

    existing_questions = {question.number: question for question in test.questions}
    for number in range(1, config["total"] + 1):
        section = section_for_question(bundle.level, number)
        page = page_map.get(number)
        question = existing_questions.get(number)
        if question is None:
            question = Question(test_id=test.id, number=number)
            db.add(question)
        question.section = section
        question.question_text = _question_text(page, number)
        question.question_type = _question_type(section, answers.get(number))
        question.audio_file = clips.get(number) or (full_audio if section == "LISTENING" else None)
        question.image_file = page.image_path if page else None
        question.source_page = page.page_number if page else None
        question.correct_answer = answers.get(number)
        question.metadata_json = {
            "source_document": page.document if page else None,
            "uses_full_audio": section == "LISTENING" and number not in clips,
        }
        labels = _option_labels(bundle.level, number, answers.get(number), page, section)
        existing_options = {option.label: option for option in question.options}
        for label, option in existing_options.items():
            if label not in labels:
                db.delete(option)
        for index, label in enumerate(labels):
            option = existing_options.get(label)
            if option is None:
                option = Option(question=question, label=label)
                db.add(option)
            option.text = label if question.question_type == "sentence_order" else _option_text(label)
            option.position = index

    log = ImportLog(
        test=test,
        test_code=bundle.test_code,
        status="success" if test.status == "published" else "warning",
        summary=summary,
        message="; ".join(warnings) if warnings else "Bundle imported successfully",
    )
    db.add(log)
    db.commit()
    db.refresh(test)
    return {"status": "imported", "test_id": test.id, "test_code": test.test_code, **summary}


def import_tests(
    db: Session,
    *,
    test_code: str | None = None,
    import_all: bool = False,
    force: bool = False,
    source_root: Path | None = None,
) -> list[dict[str, Any]]:
    bundles = discover_bundles(source_root)
    if test_code:
        normalized = test_code.upper()
        bundles = [bundle for bundle in bundles if bundle.test_code == normalized]
    elif not import_all:
        bundles = [bundle for bundle in bundles if bundle.test_code == "H11329"]
    if not bundles:
        raise ValueError(f"No matching bundle found for {test_code or 'selection'}")
    return [import_bundle(db, bundle, force=force) for bundle in bundles]


ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".mp3"}


def safely_extract_bundle_zip(zip_path: Path, destination: Path) -> Path:
    """Extract a bundle ZIP while rejecting traversal, links, and unrelated files."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    total_size = 0
    total_compressed = 0
    validate_zip_signature(zip_path)
    scan_upload_for_malware(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        entries = archive.infolist()
        if len(entries) > settings.upload_zip_max_files:
            raise ValueError("ZIP contains too many entries")
        seen_paths: set[str] = set()
        for info in entries:
            normalized = info.filename.replace("\\", "/")
            normalized_path = normalized.rstrip("/")
            posix = PurePosixPath(normalized_path)
            if (
                not normalized_path
                or len(normalized) > 512
                or len(posix.parts) > 12
                or posix.is_absolute()
                or any(part in {"", ".", ".."} for part in normalized_path.split("/"))
                or any(":" in part for part in posix.parts)
                or any(ord(character) < 32 for character in normalized)
            ):
                raise ValueError("ZIP contains an unsafe path")
            collision_key = posix.as_posix().casefold()
            if collision_key in seen_paths:
                raise ValueError("ZIP contains duplicate or colliding paths")
            seen_paths.add(collision_key)
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise ValueError("Encrypted ZIP entries are not supported")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("ZIP archives may not contain symbolic links")
            if Path(posix.name).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
                raise ValueError(f"Unsupported file in bundle: {posix.name}")
            total_size += info.file_size
            total_compressed += info.compress_size
            if total_size > settings.max_upload_mb * 1024 * 1024:
                raise ValueError("Extracted upload exceeds the configured size limit")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > settings.upload_zip_max_ratio:
                raise ValueError("ZIP entry exceeds the configured compression ratio")
            target = (destination / Path(*posix.parts)).resolve()
            if destination not in target.parents:
                raise ValueError("ZIP contains an unsafe path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                copied = 0
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    extracted_so_far = total_size - info.file_size + copied
                    if (
                        copied > info.file_size
                        or extracted_so_far > settings.max_upload_mb * 1024 * 1024
                    ):
                        raise ValueError("Extracted upload exceeds the configured size limit")
                    output.write(chunk)
            if copied != info.file_size:
                raise ValueError("ZIP entry size does not match its directory record")
            validate_uploaded_media(target)
        if (
            total_size
            and total_size / max(total_compressed, 1) > settings.upload_zip_max_ratio
        ):
            raise ValueError("ZIP exceeds the configured compression ratio")
    return destination


def temporary_upload_directory() -> tempfile.TemporaryDirectory[str]:
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="hsk-upload-")
