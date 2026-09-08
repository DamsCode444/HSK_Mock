from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT
from app.db.engine import configure_sqlite, turso_url
from app.db.locking import lock_exam_write


@pytest.fixture
def native_engine(tmp_path):
    engine = create_engine("sqlite+hsk_turso:///" + (tmp_path / "native.sqlite3").as_posix())
    configure_sqlite(engine)
    yield engine
    engine.dispose()


def test_native_libsql_runs_alembic_chain_and_enforces_constraints(native_engine):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with native_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    assert {"users", "questions", "attempts", "options", "answers"} <= set(inspect(native_engine).get_table_names())
    with native_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "e7c3a93f1b24"
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql("INSERT INTO options (question_id,label,position) VALUES (999999,'A',0)")
        connection.rollback()
    with native_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT UNIQUE)")
        connection.exec_driver_sql("INSERT INTO probe VALUES (1,'original')")
    with native_engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql("INSERT INTO probe VALUES (2,'original')")


@pytest.mark.parametrize("url", ["http://database.turso.io", "libsql://u:secret@database.turso.io", "libsql://database.turso.io?token=secret", "libsql://database.turso.io/path", "libsql://database.turso.io:123"])
def test_turso_url_rejects_insecure_or_credential_urls(url):
    with pytest.raises(ValueError):
        turso_url(url)


def test_native_write_lock_serializes_read_modify_write(native_engine):
    with native_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE counter (id INTEGER PRIMARY KEY,value INTEGER NOT NULL)")
        connection.exec_driver_sql("INSERT INTO counter VALUES (1,0)")
    gate = threading.Barrier(2)

    def increment():
        with Session(native_engine) as db:
            # Simulate authentication's earlier read transaction.
            db.execute(text("SELECT value FROM counter WHERE id=1")).scalar_one()
            gate.wait(timeout=10)
            lock_exam_write(db)
            value = db.execute(text("SELECT value FROM counter WHERE id=1")).scalar_one()
            time.sleep(0.05)
            db.execute(text("UPDATE counter SET value=:value WHERE id=1"), {"value": value + 1})
            db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(increment) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    with native_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT value FROM counter WHERE id=1").scalar() == 2
