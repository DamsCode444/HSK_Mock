from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from app.core.time import utcnow
from app.models import Attempt, Question


SECTION_ORDER = {"LISTENING": 0, "READING": 1, "WRITING": 2}


@dataclass(frozen=True)
class QuestionGrade:
    question_id: int
    section: str
    is_correct: bool | None
    score: float


@dataclass(frozen=True)
class ScoringResult:
    score: float
    section_scores: dict[str, dict[str, int | float]]
    question_grades: tuple[QuestionGrade, ...]


def normalize_answer(value: str | None) -> str | None:
    """Canonicalize objective answers without changing Chinese word order."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold() or None


def _accepted_answers(question: Question) -> tuple[str, ...]:
    accepted: list[str] = []
    if question.correct_answer is not None:
        accepted.append(question.correct_answer)
    metadata = question.metadata_json or {}
    variants = metadata.get("accepted_answers")
    if isinstance(variants, list):
        accepted.extend(item for item in variants if isinstance(item, str))
    return tuple(accepted)


def calculate_scores(
    questions: Iterable[Question],
    submitted_answers: Mapping[int, str | None],
    max_score: int,
) -> ScoringResult:
    """Score each section equally, independent of its number of questions.

    Standard HSK tests therefore award 100 points to listening/reading for
    levels 1-2 and 100 points to listening/reading/writing for levels 3-6.
    Questions with no imported answer key remain ungradable and receive zero.
    """
    ordered_questions = sorted(
        questions,
        key=lambda question: (
            SECTION_ORDER.get(question.section.upper(), 99),
            question.number,
            question.id,
        ),
    )
    grouped: dict[str, list[Question]] = defaultdict(list)
    for question in ordered_questions:
        grouped[question.section.upper()].append(question)

    if not grouped or max_score <= 0:
        return ScoringResult(score=0.0, section_scores={}, question_grades=())

    section_max = max_score / len(grouped)
    section_scores: dict[str, dict[str, int | float]] = {}
    grades: list[QuestionGrade] = []
    raw_total = 0.0

    for section, section_questions in grouped.items():
        question_value = section_max / len(section_questions)
        correct_count = 0
        answered_count = 0
        gradable_count = 0
        raw_section_score = 0.0

        for question in section_questions:
            user_answer = normalize_answer(submitted_answers.get(question.id))
            if user_answer is not None:
                answered_count += 1
            accepted = {
                normalized
                for value in _accepted_answers(question)
                if (normalized := normalize_answer(value)) is not None
            }
            if not accepted:
                is_correct: bool | None = None
            else:
                gradable_count += 1
                is_correct = user_answer is not None and user_answer in accepted

            answer_score = question_value if is_correct else 0.0
            if is_correct:
                correct_count += 1
                raw_section_score += answer_score
            grades.append(
                QuestionGrade(
                    question_id=question.id,
                    section=section,
                    is_correct=is_correct,
                    score=round(answer_score, 6),
                )
            )

        raw_total += raw_section_score
        section_scores[section] = {
            "score": round(raw_section_score, 2),
            "max_score": round(section_max, 2),
            "correct": correct_count,
            "total": len(section_questions),
            "answered": answered_count,
            "gradable": gradable_count,
            "accuracy": round(correct_count / gradable_count * 100, 2)
            if gradable_count
            else 0.0,
        }

    return ScoringResult(
        score=round(min(raw_total, float(max_score)), 2),
        section_scores=section_scores,
        question_grades=tuple(grades),
    )


def grade_attempt(attempt: Attempt, *, now: datetime | None = None) -> ScoringResult:
    """Finalize an active attempt using its currently saved answers."""
    submitted_answers = {
        answer.question_id: answer.user_answer for answer in attempt.answers
    }
    result = calculate_scores(attempt.test.questions, submitted_answers, attempt.max_score)
    grades = {grade.question_id: grade for grade in result.question_grades}
    for answer in attempt.answers:
        grade = grades[answer.question_id]
        answer.is_correct = grade.is_correct
        answer.score = grade.score

    finished_at = now or utcnow()
    attempt.end_time = min(finished_at, attempt.deadline)
    attempt.status = "submitted"
    attempt.score = result.score
    attempt.section_scores = result.section_scores
    attempt.passed = result.score >= attempt.test.passing_score
    return result
