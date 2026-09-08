"""Copy a frozen local MySQL database to Turso; never overwrite target records."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings
from app.db.session import Base
from app import models
from sqlalchemy import create_engine, select, text
import httpx

MARKER = "_hsk_cloud_migration"


def identifier(name):
    if not name.replace("_", "").isalnum():
        raise ValueError("Unexpected database identifier")
    return '"' + name + '"'


def encode(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode()}
    return {"type": "text", "value": str(value)}


def decode(value):
    kind = value["type"]
    if kind == "null": return None
    if kind == "integer": return int(value["value"])
    if kind == "float": return float(value["value"])
    if kind == "blob": return base64.b64decode(value["base64"])
    return value["value"]


class Turso:
    def __init__(self):
        parts = urlsplit(settings.turso_database_url or "")
        if parts.scheme not in ("libsql", "https") or not parts.hostname or not parts.hostname.endswith(".turso.io") or parts.username or parts.query:
            raise ValueError("Invalid Turso URL")
        if settings.turso_auth_token is None:
            raise ValueError("Turso token is missing")
        self.url = "https://" + parts.hostname + "/v2/pipeline"
        self.client = httpx.Client(timeout=httpx.Timeout(60, connect=15), trust_env=True, follow_redirects=False,
            headers={"Authorization": "Bearer " + settings.turso_auth_token.get_secret_value()})

    def query(self, sql, params=()):
        response = self.client.post(self.url, json={"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [encode(v) for v in params], "want_rows": True}},
            {"type": "close"}]})
        if response.status_code != 200:
            raise RuntimeError("Turso HTTP request failed with status " + str(response.status_code))
        result = response.json()["results"][0]
        if result["type"] != "ok":
            raise RuntimeError("Turso statement failed: " + str(result.get("error", {}).get("code", "unknown")))
        return [tuple(decode(v) for v in row) for row in result["response"]["result"].get("rows", [])]

    def rows(self, name, columns):
        result = []
        after = None
        selected = ",".join(identifier(column) for column in columns)
        primary = identifier(columns[0])
        while True:
            where = "" if after is None else " WHERE " + primary + " > ?"
            page = self.query("SELECT " + selected + " FROM " + identifier(name) + where + " ORDER BY " + primary + " LIMIT 200", () if after is None else (after,))
            result.extend(page)
            if len(page) < 200:
                return result
            after = page[-1][0]


def make_snapshot(path):
    if path.exists():
        raise ValueError("Snapshot already exists; choose --resume instead of overwriting")
    path.parent.mkdir(exist_ok=True)
    source = create_engine(settings.database_url, pool_pre_ping=True,
                           isolation_level="REPEATABLE READ")
    destination = create_engine("sqlite:///" + path.as_posix())
    Base.metadata.create_all(destination)
    counts = {}
    with source.connect() as incoming, incoming.begin(), destination.begin() as outgoing:
        outgoing.exec_driver_sql("PRAGMA foreign_keys=ON")
        for table in Base.metadata.sorted_tables:
            rows = incoming.execute(select(table).order_by(*table.primary_key.columns)).mappings().all()
            for start in range(0, len(rows), 250):
                outgoing.execute(table.insert(), [dict(row) for row in rows[start:start + 250]])
            counts[table.name] = len(rows)
        version = incoming.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        outgoing.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        outgoing.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (version,))
    source.dispose()
    destination.dispose()
    print(json.dumps({"snapshot_created": str(path.relative_to(ROOT)), "source_counts": counts}), flush=True)


def snapshot_data(path):
    db = sqlite3.connect(path)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Local snapshot integrity validation failed")
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type DESC,name").fetchall()
        tables = []
        digest = hashlib.sha256()
        table_order = [table.name for table in Base.metadata.sorted_tables] + ["alembic_version"]
        for name in table_order:
            columns = [row[1] for row in db.execute("PRAGMA table_info(" + identifier(name) + ")")]
            rows = db.execute("SELECT * FROM " + identifier(name) + " ORDER BY 1").fetchall()
            digest.update(json.dumps([name, columns, rows], ensure_ascii=False, separators=(",", ":")).encode())
            tables.append((name, columns, rows))
        return schema, tables, digest.hexdigest()
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Reuse the preserved snapshot after a partial transfer")
    args = parser.parse_args()
    snapshot = ROOT / ".cloud-transfer" / "mysql-before-turso.sqlite3"
    if not args.resume:
        make_snapshot(snapshot)
    elif not snapshot.is_file():
        raise ValueError("No snapshot exists to resume")
    schema, tables, fingerprint = snapshot_data(snapshot)
    cloud = Turso()
    try:
        remote_tables = {row[0] for row in cloud.query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        expected = {name for name, _, _ in tables}
        if remote_tables:
            if MARKER not in remote_tables or remote_tables - expected - {MARKER}:
                raise ValueError("Destination is not empty or belongs to another migration; no writes performed")
            marker = cloud.query("SELECT fingerprint FROM " + identifier(MARKER))
            if marker != [(fingerprint,)]:
                raise ValueError("Destination migration does not match the local snapshot")
        print(json.dumps({"turso_connected": True, "destination_tables": len(remote_tables),
            "snapshot_fingerprint": fingerprint, "rows": sum(len(rows) for _, _, rows in tables),
            "mode": "apply" if args.apply else "preview"}), flush=True)
        if not args.apply:
            return 0
        if not remote_tables:
            # One atomic statement both creates the ownership marker and records its fingerprint.
            cloud.query("CREATE TABLE " + identifier(MARKER) + " AS SELECT ? AS fingerprint, ? AS created_at", (fingerprint, datetime.now(timezone.utc).isoformat()))
        for kind, name, table, sql in schema:
            if kind != "table":
                continue
            if name not in remote_tables:
                cloud.query(sql)
        report = {}
        for name, columns, source_rows in tables:
            cols = ",".join(identifier(column) for column in columns)
            existing_rows = cloud.rows(name, columns)
            existing = {row[0]: row for row in existing_rows}
            source_by_id = {row[0]: tuple(row) for row in source_rows}
            if any(source_by_id.get(key) != row for key, row in existing.items()):
                raise ValueError("Existing cloud records differ from snapshot; refusing to overwrite")
            missing = [row for row in source_rows if row[0] not in existing]
            # Every INSERT is one atomic SQL statement, avoiding partial multi-statement commits.
            batch_size = max(1, min(100, 900 // len(columns)))
            for start in range(0, len(missing), batch_size):
                batch = missing[start:start + batch_size]
                placeholders = "(" + ",".join("?" for _ in columns) + ")"
                cloud.query("INSERT INTO " + identifier(name) + " (" + cols + ") VALUES " + ",".join(placeholders for _ in batch),
                            [value for row in batch for value in row])
            verified = cloud.rows(name, columns)
            if verified != [tuple(row) for row in source_rows]:
                raise ValueError("Cloud row verification failed")
            report[name] = len(verified)
            print(json.dumps({"table_verified": name, "rows": len(verified)}), flush=True)
        remote_indexes = {row[0] for row in cloud.query("SELECT name FROM sqlite_master WHERE type='index'")}
        for kind, name, table, sql in schema:
            if kind == "index" and name not in remote_indexes:
                cloud.query(sql)
        if cloud.query("PRAGMA foreign_key_check"):
            raise ValueError("Cloud foreign-key integrity check failed")
        if cloud.query("PRAGMA integrity_check") != [("ok",)]:
            raise ValueError("Cloud integrity check failed")
        result = {"migration_complete": True, "tables": report, "snapshot_fingerprint": fingerprint,
                  "verified_at": datetime.now(timezone.utc).isoformat(), "source_mysql_unchanged": True}
        (ROOT / ".cloud-transfer" / "turso-migration-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
        return 0
    finally:
        cloud.client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Do not leak user records, query parameters, credential URLs or tokens.
        print(json.dumps({"error_type": type(exc).__name__, "migration_complete": False,
            "message": "Migration stopped; local MySQL and snapshot are preserved. No existing cloud rows were overwritten."}), flush=True)
        raise SystemExit(1)
