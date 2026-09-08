"""Exercise cloud exam persistence using a temporary, precisely scoped QA user."""
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.engine import build_turso_engine
from app.models import Attempt, HskTest, Question, User
from app.api.tests import start_test
from app.api.attempts import record_audio_play, save_answer, submit_attempt
from app.schemas.exams import AnswerSaveRequest, AudioPlayRequest
from fastapi import HTTPException


def main():
    engine = build_turso_engine(settings.turso_database_url, settings.turso_auth_token.get_secret_value())
    name = "cloud-qa-" + uuid.uuid4().hex[:20]
    user_id = None
    try:
        with Session(engine, expire_on_commit=False) as db:
            user = User(username=name, email=name + "@example.invalid", password_hash="!temporary-verification!", role="student", is_active=True)
            db.add(user)
            db.commit()
            user_id = user.id
            test_id = db.scalar(select(HskTest.id).where(HskTest.level == 5, HskTest.status == "published").limit(1))
            question_id = db.scalar(select(Question.id).where(Question.test_id == test_id, Question.section == "LISTENING").order_by(Question.number).limit(1))
        print(json.dumps({"temporary_probe_created": True}), flush=True)
        def action(label, function):
            started = time.monotonic()
            with Session(engine, expire_on_commit=False) as db:
                result = function(db, db.get(User, user_id))
            print(json.dumps({"check": label, "seconds": round(time.monotonic() - started, 2), "passed": True}), flush=True)
            return result
        attempt = action("start", lambda db, user: start_test(test_id, db, user))
        repeated = action("resume_same_attempt", lambda db, user: start_test(test_id, db, user))
        assert attempt.id == repeated.id
        action("save_answer", lambda db, user: save_answer(attempt.id, question_id, AnswerSaveRequest(user_answer="A"), db, user))
        action("audio_play", lambda db, user: record_audio_play(attempt.id, AudioPlayRequest(question_id=question_id), db, user))
        try:
            action("second_audio_play", lambda db, user: record_audio_play(attempt.id, AudioPlayRequest(question_id=question_id), db, user))
            raise AssertionError("Replay limit was not enforced")
        except HTTPException as exc:
            assert exc.status_code == 409
            print(json.dumps({"check": "audio_limit", "passed": True}), flush=True)
        result = action("submit", lambda db, user: submit_attempt(attempt.id, db, user))
        assert result.status == "submitted"
        print(json.dumps({"cloud_runtime_verified": True}), flush=True)
    finally:
        # Only this uniquely named QA account and its own attempts are removed.
        with Session(engine) as db:
            target = db.scalar(select(User).where(User.username == name, User.email == name + "@example.invalid"))
            if target is not None:
                db.execute(delete(Attempt).where(Attempt.user_id == target.id))
                db.execute(delete(User).where(User.id == target.id, User.username == name))
                db.commit()
                print(json.dumps({"temporary_probe_removed": True}), flush=True)
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"cloud_runtime_verified": False, "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
