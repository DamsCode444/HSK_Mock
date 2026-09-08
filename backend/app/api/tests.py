from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.api.serializers import attempt_out, media_url, question_out, test_detail, test_summary
from app.core.time import utcnow
from app.db.locking import lock_exam_write
from app.models import Attempt, HskTest, Question, User
from app.schemas.exams import AttemptOut, QuestionListResponse, TestDetail, TestSummary
from app.services.scoring import grade_attempt


router = APIRouter(prefix="/tests", tags=["Tests"])


def _test_query():
    return select(HskTest).options(
        selectinload(HskTest.questions).selectinload(Question.options)
    )


@router.get("", response_model=list[TestSummary])
def list_tests(db: DbSession) -> list[TestSummary]:
    tests = db.scalars(
        _test_query()
        .where(HskTest.status == "published")
        .order_by(HskTest.level, HskTest.test_code)
    ).unique().all()
    return [test_summary(test) for test in tests]


@router.get("/{test_id}", response_model=TestDetail)
def get_test(test_id: int, db: DbSession) -> TestDetail:
    test = db.scalar(
        _test_query().where(HskTest.id == test_id, HskTest.status == "published")
    )
    if test is None:
        raise HTTPException(status_code=404, detail="Published test not found")
    return test_detail(test)


@router.get("/{test_id}/questions", response_model=QuestionListResponse)
def get_test_questions(
    test_id: int, db: DbSession, current_user: CurrentUser
) -> QuestionListResponse:
    test = db.scalar(_test_query().where(HskTest.id == test_id))
    if test is None or (test.status != "published" and current_user.role != "admin"):
        raise HTTPException(status_code=404, detail="Test not found")
    return QuestionListResponse(
        test_id=test.id,
        test_code=test.test_code,
        level=test.level,
        full_audio_url=media_url(test.full_audio_file),
        audio_play_limit=test.audio_play_limit,
        questions=[question_out(question) for question in test.questions],
    )


@router.post("/{test_id}/start", response_model=AttemptOut)
def start_test(test_id: int, db: DbSession, current_user: CurrentUser) -> AttemptOut:
    lock_exam_write(db)
    test = db.scalar(_test_query().where(HskTest.id == test_id))
    if test is None or (test.status != "published" and current_user.role != "admin"):
        raise HTTPException(status_code=404, detail="Published test not found")

    # Serialize starts per user so two simultaneous requests cannot create two
    # active attempts when neither request can see an existing row yet.
    db.execute(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    now = utcnow()
    existing = db.scalar(
        select(Attempt)
        .options(
            selectinload(Attempt.answers),
            selectinload(Attempt.test)
            .selectinload(HskTest.questions)
            .selectinload(Question.options),
        )
        .where(
            Attempt.user_id == current_user.id,
            Attempt.test_id == test.id,
            Attempt.status == "in_progress",
        )
        .order_by(Attempt.id.desc())
        .with_for_update()
    )
    if existing is not None and now < existing.deadline:
        return attempt_out(existing, now=now)
    if existing is not None:
        grade_attempt(existing, now=now)
        db.flush()

    attempt = Attempt(
        user_id=current_user.id,
        test_id=test.id,
        start_time=now,
        deadline=now + timedelta(minutes=test.duration_minutes),
        status="in_progress",
        max_score=test.max_score,
        section_scores={},
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt_out(attempt, now=now)
