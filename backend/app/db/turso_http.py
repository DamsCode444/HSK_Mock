"""Synchronous DB-API transport for Turso's documented SQL-over-HTTP protocol.

HTTPX respects the user's configured HTTPS proxy (including Windows settings).
Tokens and connection batons stay out of URLs, logs, and public exceptions.
Each DB-API connection retains one server-side connection/transaction baton.
"""
from __future__ import annotations

import base64
import sqlite3
from urllib.parse import urlsplit

import httpx


def _argument(value):
    if value is None: return {"type": "null"}
    if isinstance(value, bool): return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int): return {"type": "integer", "value": str(value)}
    if isinstance(value, float): return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode()}
    return {"type": "text", "value": str(value)}


def _value(item):
    kind = item["type"]
    if kind == "null": return None
    if kind == "integer": return int(item["value"])
    if kind == "float": return float(item["value"])
    if kind == "blob": return base64.b64decode(item["base64"])
    return item["value"]


class Connection:
    def __init__(self, database, *, auth_token, isolation_level="", **_kwargs):
        parsed = urlsplit(database)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query:
            raise sqlite3.ProgrammingError("Turso requires a secure database URL")
        self._base = "https://" + parsed.netloc
        self._baton = None
        self._closed = False
        self.in_transaction = False
        self.isolation_level = isolation_level
        self._client = httpx.Client(
            headers={"Authorization": "Bearer " + auth_token},
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
        )

    def cursor(self):
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database")
        return Cursor(self)

    def execute(self, statement, parameters=()):
        return self.cursor().execute(statement, parameters)

    def _send(self, statements, *, close=False):
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database")
        initialize = self._baton is None and not close
        # Turso controls remote lock timeouts and rejects PRAGMA busy_timeout.
        initial = ["PRAGMA foreign_keys=ON"] if initialize else []
        requests = [{"type": "execute", "stmt": {"sql": sql, "args": [], "want_rows": True}} for sql in initial]
        for sql, parameters in statements:
            stmt = {"sql": sql, "want_rows": True}
            if isinstance(parameters, dict):
                stmt["named_args"] = [{"name": key, "value": _argument(value)} for key, value in parameters.items()]
            else:
                stmt["args"] = [_argument(value) for value in parameters]
            requests.append({"type": "execute", "stmt": stmt})
        if close:
            requests.append({"type": "close"})
        payload = {"requests": requests}
        if self._baton:
            payload["baton"] = self._baton
        try:
            response = self._client.post(self._base + "/v2/pipeline", json=payload)
            if response.status_code != 200:
                raise sqlite3.OperationalError("Turso request failed (HTTP " + str(response.status_code) + ")")
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._baton = None
            self.in_transaction = False
            raise sqlite3.OperationalError("Turso network connection failed; retry the request") from None
        self._baton = body.get("baton")
        if body.get("base_url"):
            endpoint = urlsplit(body["base_url"])
            original = urlsplit(self._base).hostname
            if (endpoint.scheme != "https" or endpoint.username or endpoint.query
                or not endpoint.hostname or not (endpoint.hostname == original or endpoint.hostname.endswith(".turso.io"))):
                raise sqlite3.OperationalError("Turso returned an invalid connection endpoint")
            self._base = "https://" + endpoint.netloc
        results = body.get("results", [])
        if len(results) != len(requests):
            raise sqlite3.OperationalError("Turso returned an incomplete response")
        for result in results:
            if result["type"] != "ok":
                code = str(result.get("error", {}).get("code", "UNKNOWN"))
                if "CONSTRAINT" in code:
                    raise sqlite3.IntegrityError("Turso constraint violation (" + code + ")")
                if "BUSY" in code or "LOCKED" in code:
                    raise sqlite3.OperationalError("database is locked (" + code + ")")
                if "EXPIRED" in code or "STREAM" in code:
                    self._baton = None
                    self.in_transaction = False
                    raise sqlite3.OperationalError("Turso session expired; retry the request")
                raise sqlite3.OperationalError("Turso statement failed (" + code + ")")
        return [item["response"]["result"] for item in results[len(initial):len(initial) + len(statements)]]

    def commit(self):
        if self.in_transaction:
            self._send([("COMMIT", ())], close=True)
        elif self._baton:
            self._send([], close=True)
        self.in_transaction = False
        self._baton = None

    def rollback(self):
        try:
            if self.in_transaction:
                self._send([("ROLLBACK", ())], close=True)
            elif self._baton:
                # A long media download can outlive an idle read-only baton.
                # There are no writes to undo; discard expired/closed streams.
                try:
                    self._send([], close=True)
                except sqlite3.OperationalError:
                    pass
        finally:
            self.in_transaction = False
            self._baton = None

    def close(self):
        if self._closed: return
        try:
            self.rollback()
        finally:
            self._closed = True
            self._client.close()


class Cursor:
    arraysize = 1

    def __init__(self, connection):
        self.connection = connection
        self.description = None
        self.rowcount = -1
        self.lastrowid = None
        self._rows = []
        self._index = 0
        self._closed = False

    def execute(self, statement, parameters=()):
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed cursor")
        verb = statement.lstrip().split(None, 1)[0].upper()
        auto_begin = verb in {"INSERT", "UPDATE", "DELETE", "REPLACE"} and not self.connection.in_transaction and self.connection.isolation_level is not None
        if auto_begin:
            self.connection._send([("BEGIN", ())])
            self.connection.in_transaction = True
        result = self.connection._send([(statement, parameters)])[0]
        if verb == "BEGIN": self.connection.in_transaction = True
        elif verb in {"COMMIT", "ROLLBACK", "END"}: self.connection.in_transaction = False
        self._set_result(result)
        return self

    def executemany(self, statement, parameters):
        values = list(parameters)
        if not values:
            self.rowcount = 0
            return self
        if not self.connection.in_transaction and self.connection.isolation_level is not None:
            self.connection._send([("BEGIN", ())])
            self.connection.in_transaction = True
        try:
            results = self.connection._send([(statement, item) for item in values])
        except sqlite3.Error:
            self.connection.rollback()
            raise
        self._set_result(results[-1])
        self.rowcount = sum(int(row.get("affected_row_count", 0)) for row in results)
        return self

    def _set_result(self, result):
        self.description = tuple((column["name"], None, None, None, None, None, None) for column in result.get("cols", [])) or None
        self._rows = [tuple(_value(value) for value in row) for row in result.get("rows", [])]
        self._index = 0
        self.rowcount = int(result.get("affected_row_count", 0))
        self.lastrowid = int(result["last_insert_rowid"]) if result.get("last_insert_rowid") is not None else None

    def fetchone(self):
        if self._index >= len(self._rows): return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchmany(self, size=None):
        count = self.arraysize if size is None else size
        rows = self._rows[self._index:self._index + count]
        self._index += len(rows)
        return rows

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def close(self):
        self._closed = True
        self._rows = []
