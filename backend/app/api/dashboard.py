from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.api.attempt_access import get_user_attempt
from app.core.time import utcnow
from app.models import Attempt, HskTest, Question
from app.schemas.exams import (
    DashboardAttemptOut,
    DashboardLevelOut,
    DashboardOut,
)
from app.services.scoring import grade_attempt


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _percentage(attempt: Attempt) -> float:
    if not attempt.max_score:
        return 0.0
    return float(attempt.score or 0) / attempt.max_score * 100


def _section_percentage(section_data: object) -> float | None:
    if not isinstance(section_data, dict):
        return None
    score = section_data.get("score")
    maximum = section_data.get("max_score")
    if not isinstance(score, (int, float)) or not isinstance(maximum, (int, float)):
        return None
    if maximum <= 0:
        return None
    return float(score) / float(maximum) * 100


@router.get("", response_model=DashboardOut)
def get_dashboard(db: DbSession, current_user: CurrentUser) -> DashboardOut:
    # Finalize each expired attempt under the same write lock used by answer
    # saves/submission, then read dashboard history outside the write window.
    now = utcnow()
    user_id = current_user.id
    expired_ids = db.scalars(select(Attempt.id).where(
        Attempt.user_id == user_id, Attempt.status == "in_progress", Attempt.deadline <= now,
    )).all()
    for attempt_id in expired_ids:
        expired = get_user_attempt(db, attempt_id, current_user, for_update=True)
        if expired.status == "in_progress" and now >= expired.deadline:
            grade_attempt(expired, now=now)
            db.commit()
        else:
            db.rollback()
    attempts = db.scalars(
        select(Attempt)
        .options(
            selectinload(Attempt.answers),
            selectinload(Attempt.test)
            .selectinload(HskTest.questions)
            .selectinload(Question.options),
        )
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.start_time.desc())
    ).unique().all()

    completed = [
        attempt
        for attempt in attempts
        if attempt.status == "submitted" and attempt.score is not None
    ]
    percentages = [_percentage(attempt) for attempt in completed]
    passed_count = sum(attempt.passed is True for attempt in completed)

    by_level_attempts: dict[int, list[Attempt]] = defaultdict(list)
    section_values: dict[str, list[float]] = defaultdict(list)
    for attempt in completed:
        by_level_attempts[attempt.test.level].append(attempt)
        for section, section_data in (attempt.section_scores or {}).items():
            percentage = _section_percentage(section_data)
            if percentage is not None:
                section_values[section].append(percentage)

    section_averages = {
        section: round(fmean(values), 2)
        for section, values in sorted(section_values.items())
        if values
    }
    weak_section = (
        min(section_averages, key=section_averages.get) if section_averages else None
    )
    by_level = []
    for level, level_attempts in sorted(by_level_attempts.items()):
        scores = [float(attempt.score or 0) for attempt in level_attempts]
        level_passed = sum(attempt.passed is True for attempt in level_attempts)
        by_level.append(
            DashboardLevelOut(
                level=level,
                attempts=len(level_attempts),
                average_score=round(fmean(scores), 2),
                highest_score=round(max(scores), 2),
                pass_rate=round(level_passed / len(level_attempts) * 100, 2),
            )
        )

    recent = sorted(
        completed,
        key=lambda attempt: attempt.end_time or attempt.start_time,
        reverse=True,
    )[:10]
    return DashboardOut(
        attempts=len(attempts),
        completed_attempts=len(completed),
        average_score=round(
            fmean(float(attempt.score or 0) for attempt in completed), 2
        )
        if completed
        else 0.0,
        highest_score=round(max((float(attempt.score or 0) for attempt in completed), default=0), 2),
        pass_rate=round(passed_count / len(completed) * 100, 2) if completed else 0.0,
        average_percentage=round(fmean(percentages), 2) if percentages else 0.0,
        weak_section=weak_section,
        section_averages=section_averages,
        by_level=by_level,
        recent_attempts=[
            DashboardAttemptOut(
                attempt_id=attempt.id,
                test_id=attempt.test_id,
                test_code=attempt.test.test_code,
                title=attempt.test.title,
                level=attempt.test.level,
                score=float(attempt.score),
                max_score=attempt.max_score,
                passed=bool(attempt.passed),
                end_time=attempt.end_time,
            )
            for attempt in recent
        ],
    )
