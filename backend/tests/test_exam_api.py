from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin, attempts, dashboard, results, tests
from app.api.dependencies import get_current_user
from app.core.time import utcnow
from app.db.session import Base, get_db
from app.models import Attempt, HskTest, Option, Question, User


@pytest.fixture()
def api() -> Generator[tuple[TestClient, sessionmaker[Session], dict[str, int]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    with testing_session() as db:
        student = User(
            username="student",
            email="student@example.com",
            password_hash="not-used",
            role="student",
            is_active=True,
        )
        administrator = User(
            username="admin",
            email="admin@example.com",
            password_hash="not-used",
            role="admin",
            is_active=True,
        )
        test = HskTest(
            level=1,
            test_code="H10001",
            title="API Test",
            description=None,
            duration_minutes=40,
            max_score=200,
            passing_score=120,
            status="published",
            exam_file="HSK1/H10001/exam.pdf",
            answer_file="HSK1/H10001/answers.pdf",
            full_audio_file="HSK1/H10001/full.mp3",
            audio_play_limit=1,
            source_fingerprint="test-fingerprint",
            import_summary={},
        )
        test.questions = [
            Question(
                section="LISTENING",
                number=1,
                question_text="Listen",
                question_type="multiple_choice",
                audio_file="HSK1/H10001/001.mp3",
                correct_answer="A",
                metadata_json={},
                options=[Option(label="A", text="One", position=0)],
            ),
            Question(
                section="READING",
                number=2,
                question_text="Read",
                question_type="multiple_choice",
                correct_answer="B",
                metadata_json={},
                options=[Option(label="B", text="Two", position=0)],
            ),
        ]
        db.add_all([student, administrator, test])
        db.commit()
        ids = {
            "student": student.id,
            "admin": administrator.id,
            "test": test.id,
            "listening": test.questions[0].id,
        }

    app = FastAPI()
    for module in (tests, attempts, results, dashboard, admin):
        app.include_router(module.router, prefix="/api")

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as db:
            yield db

    def override_student() -> User:
        with testing_session() as db:
            return db.get(User, ids["student"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_student
    with TestClient(app) as client:
        yield client, testing_session, ids
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_complete_attempt_flow_and_answer_visibility(api) -> None:
    client, _, ids = api
    public_test = client.get(f"/api/tests/{ids['test']}")
    assert public_test.status_code == 200
    assert "answer_file" not in public_test.text
    assert "correct_answer" not in public_test.text

    questions = client.get(f"/api/tests/{ids['test']}/questions")
    assert questions.status_code == 200
    assert "correct_answer" not in questions.text

    first_start = client.post(f"/api/tests/{ids['test']}/start")
    second_start = client.post(f"/api/tests/{ids['test']}/start")
    assert first_start.status_code == 200
    assert second_start.json()["id"] == first_start.json()["id"]
    attempt_id = first_start.json()["id"]

    saved = client.put(
        f"/api/attempts/{attempt_id}/answers/{ids['listening']}",
        json={"user_answer": "\uff21"},
    )
    assert saved.status_code == 200
    assert saved.json()["user_answer"] == "\uff21"

    played = client.post(
        f"/api/attempts/{attempt_id}/audio-plays",
        json={"question_id": ids["listening"]},
    )
    assert played.status_code == 200
    assert played.json()["remaining_plays"] == 0
    assert client.post(
        f"/api/attempts/{attempt_id}/audio-plays",
        json={"question_id": ids["listening"]},
    ).status_code == 409

    submitted = client.post(f"/api/attempts/{attempt_id}/submit")
    repeated = client.post(f"/api/attempts/{attempt_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["score"] == 100.0
    assert repeated.json()["score"] == submitted.json()["score"]

    result = client.get(f"/api/results/{attempt_id}")
    assert result.status_code == 200
    assert result.json()["questions"][0]["correct_answer"] == "A"
    assert result.json()["questions"][0]["is_correct"] is True
    assert client.put(
        f"/api/attempts/{attempt_id}/answers/{ids['listening']}",
        json={"user_answer": "B"},
    ).status_code == 409

    dashboard_response = client.get("/api/dashboard")
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["completed_attempts"] == 1


def test_master_audio_replay_limit_is_shared_across_listening_questions(api) -> None:
    client, testing_session, ids = api
    with testing_session() as db:
        test = db.get(HskTest, ids["test"])
        first = next(question for question in test.questions if question.id == ids["listening"])
        first.audio_file = "HSK1/H10001/full.mp3"
        first.metadata_json = {"uses_full_audio": True}
        second = Question(
            test_id=test.id,
            section="LISTENING",
            number=3,
            question_text="Listen again",
            question_type="multiple_choice",
            audio_file="HSK1/H10001/full.mp3",
            correct_answer="A",
            metadata_json={"uses_full_audio": True},
            options=[Option(label="A", text="One", position=0)],
        )
        db.add(second)
        db.commit()
        second_id = second.id

    attempt_id = client.post(f"/api/tests/{ids['test']}/start").json()["id"]
    first_play = client.post(
        f"/api/attempts/{attempt_id}/audio-plays",
        json={"question_id": ids["listening"]},
    )
    assert first_play.status_code == 200
    assert client.post(
        f"/api/attempts/{attempt_id}/audio-plays",
        json={"question_id": second_id},
    ).status_code == 409

    recovered = client.get(f"/api/attempts/{attempt_id}")
    assert recovered.status_code == 200
    assert recovered.json()["audio_plays"] == [
        {"question_id": ids["listening"], "play_count": 1}
    ]


def test_expired_attempt_is_submitted_by_the_server(api) -> None:
    client, testing_session, ids = api
    attempt_id = client.post(f"/api/tests/{ids['test']}/start").json()["id"]
    with testing_session() as db:
        attempt = db.get(Attempt, attempt_id)
        attempt.deadline = utcnow() - timedelta(seconds=1)
        db.commit()

    recovered = client.get(f"/api/attempts/{attempt_id}")
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "submitted"
    assert recovered.json()["remaining_seconds"] == 0
    assert client.put(
        f"/api/attempts/{attempt_id}/answers/{ids['listening']}",
        json={"user_answer": "A"},
    ).status_code == 409
    assert client.get(f"/api/results/{attempt_id}").status_code == 200


def test_admin_routes_require_admin(api) -> None:
    client, testing_session, ids = api
    assert client.get("/api/admin/overview").status_code == 403

    def override_admin() -> User:
        with testing_session() as db:
            return db.get(User, ids["admin"])

    client.app.dependency_overrides[get_current_user] = override_admin
    assert client.get("/api/admin/overview").status_code == 200
    tests_response = client.get("/api/admin/tests")
    assert tests_response.status_code == 200
    assert tests_response.json()[0]["test_code"] == "H10001"
