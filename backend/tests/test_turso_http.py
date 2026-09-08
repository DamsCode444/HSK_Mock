from datetime import datetime
import json
import sqlite3

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.engine import build_turso_engine
from app.db.session import Base
from app.db.turso_http import _argument, _value
from app.models import User


@pytest.fixture
def http_engine(tmp_path, monkeypatch):
    from app.db import turso_http
    real_client = httpx.Client
    connections = {}
    calls = []
    path = str(tmp_path / "http.sqlite3")

    def handle(request):
        assert request.headers["authorization"] == "Bearer test-token"
        assert "test-token" not in str(request.url)
        payload = json.loads(request.content)
        baton = payload.get("baton")
        if baton is None:
            baton = "connection-" + str(len(calls))
            connections[baton] = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        connection = connections[baton]
        results = []
        closed = False
        for entry in payload["requests"]:
            if entry["type"] == "close":
                connection.close()
                del connections[baton]
                closed = True
                results.append({"type": "ok", "response": {"type": "close"}})
                continue
            statement = entry["stmt"]
            sql = statement["sql"]
            calls.append(sql)
            assert "busy_timeout" not in sql
            params = tuple(_value(value) for value in statement.get("args", []))
            if "named_args" in statement:
                params = {item["name"]: _value(item["value"]) for item in statement["named_args"]}
            try:
                cursor = connection.execute(sql, params)
                results.append({"type": "ok", "response": {"type": "execute", "result": {
                    "cols": [{"name": col[0]} for col in cursor.description or []],
                    "rows": [[_argument(value) for value in row] for row in cursor.fetchall()],
                    "affected_row_count": max(0, cursor.rowcount),
                    "last_insert_rowid": str(cursor.lastrowid) if cursor.lastrowid is not None else None,
                }}})
            except sqlite3.Error as exc:
                results.append({"type": "error", "error": {"code": getattr(exc, "sqlite_errorname", "SQLITE_ERROR"), "message": "private values must not leak"}})
        return httpx.Response(200, json={"baton": None if closed else baton, "base_url": None, "results": results})

    def make_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(turso_http.httpx, "Client", make_client)
    engine = build_turso_engine("libsql://test.turso.io", "test-token")
    yield engine, calls
    engine.dispose()
    for connection in connections.values():
        connection.close()


def test_http_transport_orm_commit_rollback_and_connection_reuse(http_engine):
    engine, calls = http_engine
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(username="cloud-test", email="cloud@example.invalid", password_hash="not-a-password", role="student", is_active=True)
        db.add(user)
        db.commit()
        assert user.id == 1
        assert isinstance(user.created_at, datetime)
        user.role = "admin"
        db.flush()
        db.rollback()
    with Session(engine) as db:
        assert db.get(User, 1).role == "student"
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    assert "BEGIN" in calls
    assert "COMMIT" in calls
    assert "ROLLBACK" in calls


def test_http_transport_executemany_constraint_failure_rolls_back(http_engine):
    engine, _ = http_engine
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE sample (id INTEGER PRIMARY KEY,value TEXT UNIQUE)")
    with engine.connect() as connection:
        with pytest.raises(IntegrityError, match="constraint violation") as error:
            connection.exec_driver_sql("INSERT INTO sample VALUES (?,?)", [(1, "duplicate"), (2, "duplicate")])
        assert "private values" not in str(error.value.orig)
        connection.rollback()
        assert connection.exec_driver_sql("SELECT count(*) FROM sample").scalar() == 0
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO sample VALUES (?,?)", [(1, "one"), (2, "two")])
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM sample ORDER BY id")).scalars().all() == ["one", "two"]
