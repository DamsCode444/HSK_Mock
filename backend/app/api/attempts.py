from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.attempt_access import get_user_attempt
from app.api.dependencies import CurrentUser, DbSession
from app.api.serializers import attempt_out
from app.core.audit import audit_event
from app.core.time import utcnow
from app.models import Answer, AttemptAudioPlay
from app.schemas.exams import (
    AnswerSaveRequest,
    AnswerSaveResponse,
    AttemptOut,
    AudioPlayRequest,
    AudioPlayResponse,
    SubmissionOut,
)
from app.services.scoring import grade_attempt


router = APIRouter(prefix="/attempts", tags=["Attempts"])


def _reject_unavailable_attempt(attempt, db: DbSession) -> None:
    if attempt.status != "in_progress":
        raise HTTPException(status_code=409, detail="Attempt has already been submitted")
    now = utcnow()
    if now >= attempt.deadline:
        grade_attempt(attempt, now=now)
        db.commit()
        audit_event(
            "attempt_expired",
            user_id=attempt.user_id,
            attempt_id=attempt.id,
            test_id=attempt.test_id,
        )
        raise HTTPException(
            status_code=409,
            detail="Attempt deadline has passed; the attempt was submitted automatically",
        )


def _submission_out(attempt) -> SubmissionOut:
    return SubmissionOut(
        attempt_id=attempt.id,
        status=attempt.status,
        score=attempt.score,
        max_score=attempt.max_score,
        passed=attempt.passed,
        section_scores=attempt.section_scores or {},
        end_time=attempt.end_time,
        result_url=f"/api/results/{attempt.id}",
    )


@router.get("/{attempt_id}", response_model=AttemptOut)
def get_attempt(
    attempt_id: int, db: DbSession, current_user: CurrentUser
) -> AttemptOut:
    attempt = get_user_attempt(db, attempt_id, current_user, for_update=True)
    now = utcnow()
    if attempt.status == "in_progress" and now >= attempt.deadline:
        grade_attempt(attempt, now=now)
        db.commit()
    return attempt_out(attempt, now=now)


@router.put("/{attempt_id}/answers/{question_id}", response_model=AnswerSaveResponse)
def save_answer(
    attempt_id: int,
    question_id: int,
    payload: AnswerSaveRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> AnswerSaveResponse:
    attempt = get_user_attempt(db, attempt_id, current_user, for_update=True)
    _reject_unavailable_attempt(attempt, db)
    if not any(
        question.id == question_id and question.test_id == attempt.test_id
        for question in attempt.test.questions
    ):
        raise HTTPException(status_code=404, detail="Question is not part of this attempt")

    answer = db.scalar(
        select(Answer)
        .where(
            Answer.attempt_id == attempt.id,
            Answer.question_id == question_id,
        )
        .with_for_update()
    )
    saved_at = utcnow()
    if answer is None:
        answer = Answer(
            attempt_id=attempt.id,
            question_id=question_id,
            user_answer=payload.user_answer,
            saved_at=saved_at,
        )
        db.add(answer)
    else:
        answer.user_answer = payload.user_answer
        answer.saved_at = saved_at
        answer.is_correct = None
        answer.score = 0
    db.commit()
    db.refresh(answer)
    return AnswerSaveResponse(
        attempt_id=attempt.id,
        question_id=answer.question_id,
        user_answer=answer.user_answer,
        saved_at=answer.saved_at,
    )


@router.post("/{attempt_id}/audio-plays", response_model=AudioPlayResponse)
def record_audio_play(
    attempt_id: int,
    payload: AudioPlayRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> AudioPlayResponse:
    attempt = get_user_attempt(db, attempt_id, current_user, for_update=True)
    _reject_unavailable_attempt(attempt, db)
    question = next(
        (
            item
            for item in attempt.test.questions
            if item.id == payload.question_id and item.test_id == attempt.test_id
        ),
        None,
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question is not part of this attempt")
    if not question.audio_file:
        raise HTTPException(status_code=409, detail="Question has no listening audio")

    play_limit = attempt.test.audio_play_limit
    if play_limit <= 0:
        raise HTTPException(status_code=403, detail="Audio playback is disabled for this test")
    # A master listening stream is attached to many questions by the importer.
    # Count those uses against one canonical record so navigation cannot reset
    # the replay limit. Individually split clips retain per-question limits.
    tracking_question_id = question.id
    if (question.metadata_json or {}).get("uses_full_audio"):
        matching_ids = [
            item.id
            for item in attempt.test.questions
            if item.audio_file == question.audio_file
            and (item.metadata_json or {}).get("uses_full_audio")
        ]
        if matching_ids:
            tracking_question_id = min(matching_ids)

    audio_play = db.scalar(
        select(AttemptAudioPlay)
        .where(
            AttemptAudioPlay.attempt_id == attempt.id,
            AttemptAudioPlay.question_id == tracking_question_id,
        )
        .with_for_update()
    )
    if audio_play is None:
        audio_play = AttemptAudioPlay(
            attempt_id=attempt.id,
            question_id=tracking_question_id,
            play_count=0,
            started_at=utcnow(),
        )
        db.add(audio_play)
    if audio_play.play_count >= play_limit:
        audit_event(
            "exam_audio_limit_rejected",
            user_id=current_user.id,
            attempt_id=attempt.id,
            question_id=tracking_question_id,
        )
        raise HTTPException(status_code=409, detail="Audio play limit reached")

    audio_play.play_count += 1
    db.commit()
    return AudioPlayResponse(
        attempt_id=attempt.id,
        question_id=question.id,
        play_count=audio_play.play_count,
        play_limit=play_limit,
        remaining_plays=max(0, play_limit - audio_play.play_count),
    )


@router.post("/{attempt_id}/submit", response_model=SubmissionOut)
def submit_attempt(
    attempt_id: int, db: DbSession, current_user: CurrentUser
) -> SubmissionOut:
    attempt = get_user_attempt(db, attempt_id, current_user, for_update=True)
    if attempt.status == "in_progress":
        grade_attempt(attempt, now=utcnow())
        db.commit()
        audit_event(
            "attempt_submitted",
            user_id=current_user.id,
            attempt_id=attempt.id,
            test_id=attempt.test_id,
            score=attempt.score,
        )
    elif attempt.status != "submitted":
        raise HTTPException(status_code=409, detail="Attempt cannot be submitted")
    return _submission_out(attempt)
