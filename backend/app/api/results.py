from fastapi import APIRouter, HTTPException

from app.api.attempt_access import get_user_attempt
from app.api.dependencies import CurrentUser, DbSession
from app.api.serializers import result_out
from app.core.time import utcnow
from app.schemas.exams import ResultOut
from app.services.scoring import grade_attempt


router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/{attempt_id}", response_model=ResultOut)
def get_result(
    attempt_id: int, db: DbSession, current_user: CurrentUser
) -> ResultOut:
    attempt = get_user_attempt(db, attempt_id, current_user, for_update=True)
    if attempt.status == "in_progress" and utcnow() >= attempt.deadline:
        grade_attempt(attempt, now=utcnow())
        db.commit()
    if attempt.status != "submitted":
        raise HTTPException(
            status_code=409,
            detail="Results and correct answers are available only after submission",
        )
    return result_out(attempt)
