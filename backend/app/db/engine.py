"""Shared engine configuration for the API, import tools, and Alembic."""

from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import create_engine, event
from sqlalchemy.dialects import registry
from sqlalchemy.engine import Engine, URL, make_url

from app.core.config import Settings, settings


registry.register("sqlite.hsk_turso", "app.db.turso", "TursoDialect")


def turso_url(value: str) -> URL:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"libsql", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("TURSO_DATABASE_URL must be a libsql:// or https:// database hostname without credentials")
    return URL.create("sqlite+hsk_turso", host=parsed.hostname)


def database_url(configuration: Settings = settings) -> URL:
    if configuration.database_backend == "turso":
        if not configuration.turso_database_url:
            raise ValueError("TURSO_DATABASE_URL is required when HSK_DATABASE_BACKEND=turso")
        return turso_url(configuration.turso_database_url)
    return make_url(configuration.database_url)


def configure_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA foreign_keys")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("Database connection did not enable foreign-key enforcement")
            # The native SDK can hold Python's GIL while waiting on a writer.
            # Fail immediately there; lock_exam_write retries outside the SDK
            # so the thread owning the transaction can commit.
            if not (engine.dialect.driver == "hsk_turso" and engine.url.host):
                cursor.execute("PRAGMA busy_timeout=" + ("0" if engine.dialect.driver == "hsk_turso" else "4000"))
        finally:
            cursor.close()


def build_turso_engine(url: str, token: str, **options) -> Engine:
    if not token or not token.strip():
        raise ValueError("TURSO_AUTH_TOKEN is required when HSK_DATABASE_BACKEND=turso")
    connect_args = {"auth_token": token, **options.pop("connect_args", {})}
    engine = create_engine(
        turso_url(url), connect_args=connect_args,
        **{"pool_pre_ping": True, "hide_parameters": True, **options},
    )
    configure_sqlite(engine)
    return engine


def build_engine(configuration: Settings = settings, **options) -> Engine:
    if configuration.database_backend == "turso":
        if not configuration.turso_database_url or configuration.turso_auth_token is None:
            raise ValueError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are required")
        return build_turso_engine(
            configuration.turso_database_url,
            configuration.turso_auth_token.get_secret_value(),
            **options,
        )
    engine_options = {"pool_pre_ping": True, "hide_parameters": True}
    if configuration.database_url.startswith("mysql"):
        engine_options.update({"pool_recycle": 1800, "pool_size": 10, "max_overflow": 20})
    engine_options.update(options)
    # QueuePool sizing is not accepted by Alembic's NullPool.
    if "poolclass" in options:
        engine_options.pop("pool_size", None)
        engine_options.pop("max_overflow", None)
    engine = create_engine(database_url(configuration), **engine_options)
    configure_sqlite(engine)
    return engine
