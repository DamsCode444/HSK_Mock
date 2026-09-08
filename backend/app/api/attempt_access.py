from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Attempt, HskTest, Question, User
from app.db.locking import lock_exam_write


def attempt_query():
    return select(Attempt).options(
        selectinload(Attempt.answers),
        selectinload(Attempt.audio_plays),
        selectinload(Attempt.test)
        .selectinload(HskTest.questions)
        .selectinload(Question.options),
    )


def get_user_attempt(
    db: Session, attempt_id: int, user: User, *, for_update: bool = False
) -> Attempt:
    query = attempt_query().where(Attempt.id == attempt_id)
    if for_update:
        lock_exam_write(db)
        query = query.with_for_update()
    attempt = db.scalar(query)
    if attempt is None or (attempt.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt
