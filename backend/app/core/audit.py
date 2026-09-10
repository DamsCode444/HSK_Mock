"""Structured, credential-free security and exam audit events.

Events are intentionally written to the normal application logger so they work
on Render without a database migration.  A production log drain can retain and
index these JSON records later.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any


logger = logging.getLogger("hsk.audit")


def _safe_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    # Audit fields are identifiers/statuses, never answers, tokens, or URLs.
    return str(value).replace("\r", " ").replace("\n", " ")[:256]


def audit_event(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        **{key: _safe_value(value) for key, value in fields.items()},
    }
    logger.info(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
