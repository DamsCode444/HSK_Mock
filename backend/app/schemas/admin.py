from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class AdminImportRequest(BaseModel):
    test_code: str | None = Field(default=None, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    import_all: bool = False
    force: bool = False


class AdminImportResponse(BaseModel):
    results: list[dict[str, Any]]


class AdminTestPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    max_score: int | None = Field(default=None, ge=1, le=1000)
    passing_score: int | None = Field(default=None, ge=0, le=1000)
    audio_play_limit: int | None = Field(default=None, ge=0, le=20)
    status: Literal["draft", "published", "archived"] | None = None

    @model_validator(mode="after")
    def reject_empty_patch(self) -> "AdminTestPatch":
        if not self.model_fields_set:
            raise ValueError("At least one setting must be provided")
        return self


class AdminTestOut(BaseModel):
    id: int
    level: int
    test_code: str
    title: str
    description: str | None
    duration_minutes: int
    max_score: int
    passing_score: int
    status: str
    audio_play_limit: int
    question_count: int
    attempt_count: int
    import_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AdminUserPatch(BaseModel):
    is_active: bool


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool
    attempt_count: int
    created_at: datetime
    updated_at: datetime


class AdminRecentAttemptOut(BaseModel):
    attempt_id: int
    username: str
    test_code: str
    level: int
    status: str
    score: float | None
    max_score: int
    passed: bool | None
    start_time: datetime
    end_time: datetime | None


class AdminOverviewOut(BaseModel):
    total_users: int
    active_users: int
    total_tests: int
    published_tests: int
    total_attempts: int
    completed_attempts: int
    average_score: float
    average_percentage: float
    pass_rate: float
    attempts_by_level: dict[str, int]
    recent_attempts: list[AdminRecentAttemptOut]
