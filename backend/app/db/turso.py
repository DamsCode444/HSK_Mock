"""A narrow SQLite SQLAlchemy dialect for native and remote libSQL.

The published sqlalchemy-libsql dialect still imports libsql-experimental,
which has no Windows wheel. Local databases use the supported libsql package;
remote databases use the documented HTTP protocol with proxy support. Native
SDK exceptions are normalized to standard DB-API errors.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.engine import URL
from sqlalchemy.pool import QueuePool


def _call(function, *args, **kwargs):
    import libsql

    try:
        return function(*args, **kwargs)
    except (libsql.Error, ValueError) as exc:
        message = str(exc)
        upper = message.upper()
        if any(marker in upper for marker in (
            "SQLITE_CONSTRAINT", "UNIQUE CONSTRAINT", "FOREIGN KEY CONSTRAINT",
            "NOT NULL CONSTRAINT", "CHECK CONSTRAINT", "PRIMARY KEY CONSTRAINT",
        )):
            raise sqlite3.IntegrityError(message) from None
        raise sqlite3.OperationalError(message) from None


class Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def execute(self, statement, parameters=()):
        _call(self._cursor.execute, statement, parameters)
        return self

    def executemany(self, statement, parameters):
        _call(self._cursor.executemany, statement, parameters)
        return self

    def fetchone(self):
        return _call(self._cursor.fetchone)

    def fetchmany(self, size=None):
        return _call(self._cursor.fetchmany) if size is None else _call(self._cursor.fetchmany, size)

    def fetchall(self):
        return _call(self._cursor.fetchall)

    def close(self):
        return _call(self._cursor.close)


class Connection:
    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    @property
    def isolation_level(self):
        return self._connection.isolation_level

    @isolation_level.setter
    def isolation_level(self, value):
        self._connection.isolation_level = value

    def cursor(self):
        return Cursor(_call(self._connection.cursor))

    def execute(self, statement, parameters=()):
        return self.cursor().execute(statement, parameters)

    def commit(self):
        return _call(self._connection.commit)

    def rollback(self):
        return _call(self._connection.rollback)

    def close(self):
        return _call(self._connection.close)


class DBAPI:
    apilevel = "2.0"
    threadsafety = 1
    paramstyle = "qmark"
    # SQLAlchemy's SQLite type/feature detection needs the SDK's version tuple.
    import libsql as _libsql
    sqlite_version_info = _libsql.sqlite_version_info
    Error = sqlite3.Error
    DatabaseError = sqlite3.DatabaseError
    IntegrityError = sqlite3.IntegrityError
    OperationalError = sqlite3.OperationalError
    ProgrammingError = sqlite3.ProgrammingError
    NotSupportedError = sqlite3.NotSupportedError

    @staticmethod
    def connect(database: str, **kwargs: Any) -> Connection:
        if database.startswith("https://"):
            from app.db.turso_http import Connection as HttpConnection
            return HttpConnection(database, **kwargs)
        import libsql

        return Connection(_call(libsql.connect, database, **kwargs))


class TursoDialect(SQLiteDialect_pysqlite):
    driver = "hsk_turso"
    supports_statement_cache = True

    def is_disconnect(self, error, connection, cursor):
        message = str(error).lower()
        return "turso network connection failed" in message or "turso session expired" in message or super().is_disconnect(error, connection, cursor)

    @classmethod
    def import_dbapi(cls):
        return DBAPI

    @classmethod
    def get_pool_class(cls, url):
        # A remote hostname is not an in-memory SQLite database. Connections
        # must never be shared concurrently by request threads.
        return QueuePool

    def on_connect(self):
        # The SDK does not implement sqlite3.create_function. This application
        # does not need the REGEXP/floor UDFs installed by SQLite's base dialect.
        return None

    def create_connect_args(self, url: URL):
        if url.username or url.password or url.query:
            raise ValueError("Turso credentials and connection options must use connect_args")
        if url.host:
            if url.port or url.database:
                raise ValueError("Turso remote URLs must contain only the database hostname")
            database = f"https://{url.host}"
        else:
            database = url.database or ":memory:"
        return [database], {"_check_same_thread": False, "isolation_level": ""}
