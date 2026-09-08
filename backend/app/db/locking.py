"""Serialize SQLite/Turso read-modify-write exam workflows before their reads."""

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException
import time


def lock_exam_write(db: Session) -> None:
    if db.get_bind().dialect.name != "sqlite":
        # MySQL continues to use the existing row-level SELECT FOR UPDATE locks.
        return
    transaction = db.get_transaction()
    if transaction is not None and db.info.get("exam_write_transaction") is transaction:
        return
    if db.new or db.dirty or db.deleted:
        raise RuntimeError("Acquire the exam write lock before changing database objects")
    # Authentication may already have read the user. Finish that read-only
    # transaction before reserving the writer, so no stale read snapshot is
    # promoted to a write transaction. Never perform Clerk network calls here.
    db.rollback()
    deadline = time.monotonic() + 4.5
    while True:
        try:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            break
        except OperationalError as exc:
            message = str(exc.orig).lower()
            if not any(marker in message for marker in ("database is locked", "database is busy", "sqlite_busy", "sqlite_locked")):
                raise
            db.rollback()
            if time.monotonic() >= deadline:
                raise HTTPException(status_code=503, detail="The exam database is busy. Please retry.", headers={"Retry-After": "1"}) from None
            time.sleep(0.05)
    db.info["exam_write_transaction"] = db.get_transaction()
