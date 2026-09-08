from __future__ import annotations

import zipfile
from pathlib import Path
from statistics import fmean

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import AdminUser, DbSession
from app.core.config import settings
from app.models import Attempt, HskTest, User
from app.schemas.admin import (
    AdminImportRequest,
    AdminImportResponse,
    AdminOverviewOut,
    AdminRecentAttemptOut,
    AdminTestOut,
    AdminTestPatch,
    AdminUserOut,
    AdminUserPatch,
)


router = APIRouter(prefix="/admin", tags=["Administration"])


def _admin_test_out(
    test: HskTest, question_count: int, attempt_count: int
) -> AdminTestOut:
    return AdminTestOut(
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
        question_count=question_count,
        attempt_count=attempt_count,
        import_summary=test.import_summary or {},
        created_at=test.created_at,
        updated_at=test.updated_at,
    )


@router.get("/overview", response_model=AdminOverviewOut)
def get_overview(db: DbSession, _: AdminUser) -> AdminOverviewOut:
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(
        select(func.count(User.id)).where(User.is_active.is_(True))
    ) or 0
    total_tests = db.scalar(select(func.count(HskTest.id))) or 0
    published_tests = db.scalar(
        select(func.count(HskTest.id)).where(HskTest.status == "published")
    ) or 0
    total_attempts = db.scalar(select(func.count(Attempt.id))) or 0
    completed = db.scalars(
        select(Attempt)
        .options(selectinload(Attempt.user), selectinload(Attempt.test))
        .where(Attempt.status == "submitted")
        .order_by(Attempt.end_time.desc())
    ).all()
    recent = db.scalars(
        select(Attempt)
        .options(selectinload(Attempt.user), selectinload(Attempt.test))
        .order_by(Attempt.start_time.desc())
        .limit(10)
    ).all()

    scores = [float(attempt.score or 0) for attempt in completed]
    percentages = [
        float(attempt.score or 0) / attempt.max_score * 100
        for attempt in completed
        if attempt.max_score > 0
    ]
    passed = sum(attempt.passed is True for attempt in completed)
    attempts_by_level: dict[str, int] = {}
    for level, count in db.execute(
        select(HskTest.level, func.count(Attempt.id))
        .join(Attempt, Attempt.test_id == HskTest.id)
        .group_by(HskTest.level)
        .order_by(HskTest.level)
    ):
        attempts_by_level[str(level)] = count

    return AdminOverviewOut(
        total_users=total_users,
        active_users=active_users,
        total_tests=total_tests,
        published_tests=published_tests,
        total_attempts=total_attempts,
        completed_attempts=len(completed),
        average_score=round(fmean(scores), 2) if scores else 0.0,
        average_percentage=round(fmean(percentages), 2) if percentages else 0.0,
        pass_rate=round(passed / len(completed) * 100, 2) if completed else 0.0,
        attempts_by_level=attempts_by_level,
        recent_attempts=[
            AdminRecentAttemptOut(
                attempt_id=attempt.id,
                username=attempt.user.username,
                test_code=attempt.test.test_code,
                level=attempt.test.level,
                status=attempt.status,
                score=attempt.score,
                max_score=attempt.max_score,
                passed=attempt.passed,
                start_time=attempt.start_time,
                end_time=attempt.end_time,
            )
            for attempt in recent
        ],
    )


@router.get("/tests", response_model=list[AdminTestOut])
def list_admin_tests(db: DbSession, _: AdminUser) -> list[AdminTestOut]:
    tests = db.scalars(select(HskTest).order_by(HskTest.level, HskTest.test_code)).all()
    question_counts = dict(
        db.execute(
            select(HskTest.id, func.count())
            .join(HskTest.questions)
            .group_by(HskTest.id)
        ).all()
    )
    attempt_counts = dict(
        db.execute(
            select(Attempt.test_id, func.count(Attempt.id)).group_by(Attempt.test_id)
        ).all()
    )
    return [
        _admin_test_out(
            test,
            question_counts.get(test.id, 0),
            attempt_counts.get(test.id, 0),
        )
        for test in tests
    ]


@router.get("/users", response_model=list[AdminUserOut])
def list_admin_users(
    db: DbSession,
    _: AdminUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AdminUserOut]:
    users = db.scalars(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    ).all()
    attempt_counts = dict(
        db.execute(
            select(Attempt.user_id, func.count(Attempt.id))
            .where(Attempt.user_id.in_([user.id for user in users]))
            .group_by(Attempt.user_id)
        ).all()
    ) if users else {}
    return [
        AdminUserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            attempt_count=attempt_counts.get(user.id, 0),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        for user in users
    ]


@router.post("/import", response_model=AdminImportResponse)
def import_bundles(
    payload: AdminImportRequest, db: DbSession, _: AdminUser
) -> AdminImportResponse:
    # Imported lazily so ordinary API startup is independent of PDF tooling.
    from app.services.importer import import_tests

    try:
        results = import_tests(
            db,
            test_code=payload.test_code,
            import_all=payload.import_all,
            force=payload.force,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminImportResponse(results=results)


@router.post("/import/upload", response_model=AdminImportResponse)
async def upload_bundle(
    db: DbSession,
    _: AdminUser,
    file: UploadFile = File(...),
) -> AdminImportResponse:
    filename = Path(file.filename or "bundle.zip").name
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=415, detail="Upload must be a ZIP archive")

    from app.services.importer import (
        discover_bundles,
        import_bundle,
        safely_extract_bundle_zip,
        temporary_upload_directory,
    )

    maximum = settings.max_upload_mb * 1024 * 1024
    try:
        with temporary_upload_directory() as temp_name:
            temp_root = Path(temp_name)
            zip_path = temp_root / "bundle.zip"
            total = 0
            with zip_path.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > maximum:
                        raise HTTPException(
                            status_code=413,
                            detail=f"ZIP exceeds the {settings.max_upload_mb} MB upload limit",
                        )
                    destination.write(chunk)

            extracted = safely_extract_bundle_zip(zip_path, temp_root / "extracted")
            bundles = discover_bundles(extracted)
            if not bundles:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No valid mock-test-HSK{level}-{code} bundle directory was found "
                        "inside the ZIP"
                    ),
                )
            results = [import_bundle(db, bundle) for bundle in bundles]
    except HTTPException:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()
    return AdminImportResponse(results=results)


@router.patch("/tests/{test_id}", response_model=AdminTestOut)
def update_test(
    test_id: int,
    payload: AdminTestPatch,
    db: DbSession,
    _: AdminUser,
) -> AdminTestOut:
    test = db.get(HskTest, test_id)
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    values = payload.model_dump(exclude_unset=True)
    for field in (
        "title",
        "duration_minutes",
        "max_score",
        "passing_score",
        "audio_play_limit",
        "status",
    ):
        if field in values and values[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} may not be null")

    effective_max = values.get("max_score", test.max_score)
    effective_passing = values.get("passing_score", test.passing_score)
    if effective_passing > effective_max:
        raise HTTPException(
            status_code=422, detail="passing_score cannot exceed max_score"
        )
    for field, value in values.items():
        setattr(test, field, value)
    db.commit()
    db.refresh(test)
    question_count = db.scalar(
        select(func.count()).select_from(HskTest).join(HskTest.questions).where(HskTest.id == test.id)
    ) or 0
    attempt_count = db.scalar(
        select(func.count(Attempt.id)).where(Attempt.test_id == test.id)
    ) or 0
    return _admin_test_out(test, question_count, attempt_count)


@router.delete("/tests/{test_id}", response_model=AdminTestOut)
def archive_test(test_id: int, db: DbSession, _: AdminUser) -> AdminTestOut:
    test = db.get(HskTest, test_id)
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    test.status = "archived"
    db.commit()
    db.refresh(test)
    question_count = db.scalar(
        select(func.count()).select_from(HskTest).join(HskTest.questions).where(HskTest.id == test.id)
    ) or 0
    attempt_count = db.scalar(
        select(func.count(Attempt.id)).where(Attempt.test_id == test.id)
    ) or 0
    return _admin_test_out(test, question_count, attempt_count)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    payload: AdminUserPatch,
    db: DbSession,
    admin: AdminUser,
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and not payload.is_active:
        raise HTTPException(status_code=409, detail="You cannot disable your own account")
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    attempt_count = db.scalar(
        select(func.count(Attempt.id)).where(Attempt.user_id == user.id)
    ) or 0
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        attempt_count=attempt_count,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
