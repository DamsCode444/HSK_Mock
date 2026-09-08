from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from urllib.parse import quote

from app.core.time import utcnow
from app.models import Attempt, HskTest, Question
from app.schemas.exams import (
    AttemptAnswerOut,
    AttemptAudioPlayOut,
    AttemptOut,
    OptionOut,
    QuestionOut,
    ResultOut,
    ResultQuestionOut,
    SectionSummary,
    TestDetail,
    TestSummary,
)


def media_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith(("http://", "https://", "/media/")):
        return path
    normalized = path.replace("\\", "/").lstrip("/")
    return f"/media/{quote(normalized, safe='/')}"


def test_summary(test: HskTest) -> TestSummary:
    return TestSummary(
        id=test.id,
        level=test.level,
        test_code=test.test_code,
        title=test.title,
        description=test.description,
        duration_minutes=test.duration_minutes,
        max_score=test.max_score,
        passing_score=test.passing_score,
        status=test.status,
        audio_play_limit=test.audio_play_limit,
        question_count=len(test.questions),
    )


def test_detail(test: HskTest) -> TestDetail:
    counts = Counter(question.section.upper() for question in test.questions)
    summary = test_summary(test).model_dump()
    return TestDetail(
        **summary,
        exam_url=media_url(test.exam_file),
        full_audio_url=media_url(test.full_audio_file),
        sections=[
            SectionSummary(section=section, question_count=count)
            for section, count in counts.items()
        ],
    )


def option_out(option: object) -> OptionOut:
    return OptionOut(
        id=option.id,
        label=option.label,
        text=option.text,
        position=option.position,
    )


def question_out(question: Question) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        section=question.section,
        number=question.number,
        question_text=question.question_text,
        question_type=question.question_type,
        audio_url=media_url(question.audio_file),
        image_url=media_url(question.image_file),
        source_page=question.source_page,
        options=[option_out(option) for option in question.options],
    )


def attempt_out(attempt: Attempt, *, now: datetime | None = None) -> AttemptOut:
    current_time = now or utcnow()
    remaining = 0
    if attempt.status == "in_progress":
        remaining = max(0, math.ceil((attempt.deadline - current_time).total_seconds()))
    return AttemptOut(
        id=attempt.id,
        test_id=attempt.test_id,
        status=attempt.status,
        start_time=attempt.start_time,
        deadline=attempt.deadline,
        end_time=attempt.end_time,
        remaining_seconds=remaining,
        score=attempt.score,
        max_score=attempt.max_score,
        passed=attempt.passed,
        section_scores=attempt.section_scores or {},
        answers=[
            AttemptAnswerOut(
                question_id=answer.question_id,
                user_answer=answer.user_answer,
                saved_at=answer.saved_at,
            )
            for answer in sorted(attempt.answers, key=lambda item: item.question_id)
        ],
        audio_plays=[
            AttemptAudioPlayOut(
                question_id=audio_play.question_id,
                play_count=audio_play.play_count,
            )
            for audio_play in sorted(
                attempt.audio_plays, key=lambda item: item.question_id
            )
        ],
    )


def result_out(attempt: Attempt) -> ResultOut:
    answers = {answer.question_id: answer for answer in attempt.answers}
    questions: list[ResultQuestionOut] = []
    for question in sorted(attempt.test.questions, key=lambda item: item.number):
        answer = answers.get(question.id)
        metadata = question.metadata_json or {}
        explanation = metadata.get("explanation")
        questions.append(
            ResultQuestionOut(
                question_id=question.id,
                number=question.number,
                section=question.section,
                question_text=question.question_text,
                question_type=question.question_type,
                image_url=media_url(question.image_file),
                options=[option_out(option) for option in question.options],
                user_answer=answer.user_answer if answer else None,
                correct_answer=question.correct_answer,
                is_correct=(
                    answer.is_correct
                    if answer
                    else (False if question.correct_answer is not None else None)
                ),
                score=answer.score if answer else 0.0,
                explanation=explanation if isinstance(explanation, str) else None,
            )
        )
    return ResultOut(
        attempt_id=attempt.id,
        test_id=attempt.test_id,
        test_code=attempt.test.test_code,
        level=attempt.test.level,
        title=attempt.test.title,
        status=attempt.status,
        start_time=attempt.start_time,
        end_time=attempt.end_time,
        score=attempt.score,
        max_score=attempt.max_score,
        passing_score=attempt.test.passing_score,
        passed=attempt.passed,
        section_scores=attempt.section_scores or {},
        questions=questions,
    )
