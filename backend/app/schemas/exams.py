from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SectionSummary(BaseModel):
    section: str
    question_count: int


class TestSummary(BaseModel):
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


class TestDetail(TestSummary):
    exam_url: str | None = None
    full_audio_url: str | None = None
    sections: list[SectionSummary]


class OptionOut(BaseModel):
    id: int
    label: str
    text: str | None
    position: int


class QuestionOut(BaseModel):
    id: int
    section: str
    number: int
    question_text: str
    question_type: str
    audio_url: str | None
    image_url: str | None
    source_page: int | None
    options: list[OptionOut]


class QuestionListResponse(BaseModel):
    test_id: int
    test_code: str
    level: int
    full_audio_url: str | None
    audio_play_limit: int
    questions: list[QuestionOut]


class AttemptAnswerOut(BaseModel):
    question_id: int
    user_answer: str | None
    saved_at: datetime


class AttemptAudioPlayOut(BaseModel):
    question_id: int
    play_count: int


class AttemptOut(BaseModel):
    id: int
    test_id: int
    status: str
    start_time: datetime
    deadline: datetime
    end_time: datetime | None
    remaining_seconds: int
    score: float | None
    max_score: int
    passed: bool | None
    section_scores: dict[str, Any]
    answers: list[AttemptAnswerOut]
    audio_plays: list[AttemptAudioPlayOut]


class AnswerSaveRequest(BaseModel):
    user_answer: str | None = Field(default=None, max_length=10000)

    @field_validator("user_answer")
    @classmethod
    def strip_answer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AnswerSaveResponse(BaseModel):
    attempt_id: int
    question_id: int
    user_answer: str | None
    saved_at: datetime


class AudioPlayRequest(BaseModel):
    question_id: int = Field(gt=0)


class AudioPlayResponse(BaseModel):
    attempt_id: int
    question_id: int
    play_count: int
    play_limit: int
    remaining_plays: int


class SubmissionOut(BaseModel):
    attempt_id: int
    status: str
    score: float
    max_score: int
    passed: bool
    section_scores: dict[str, Any]
    end_time: datetime
    result_url: str


class ResultQuestionOut(BaseModel):
    question_id: int
    number: int
    section: str
    question_text: str
    question_type: str
    image_url: str | None
    options: list[OptionOut]
    user_answer: str | None
    correct_answer: str | None
    is_correct: bool | None
    score: float
    explanation: str | None = None


class ResultOut(BaseModel):
    attempt_id: int
    test_id: int
    test_code: str
    level: int
    title: str
    status: str
    start_time: datetime
    end_time: datetime
    score: float
    max_score: int
    passing_score: int
    passed: bool
    section_scores: dict[str, Any]
    questions: list[ResultQuestionOut]


class DashboardLevelOut(BaseModel):
    level: int
    attempts: int
    average_score: float
    highest_score: float
    pass_rate: float


class DashboardAttemptOut(BaseModel):
    attempt_id: int
    test_id: int
    test_code: str
    title: str
    level: int
    score: float
    max_score: int
    passed: bool
    end_time: datetime


class DashboardOut(BaseModel):
    attempts: int
    completed_attempts: int
    average_score: float
    highest_score: float
    pass_rate: float
    average_percentage: float
    weak_section: str | None
    section_averages: dict[str, float]
    by_level: list[DashboardLevelOut]
    recent_attempts: list[DashboardAttemptOut]
