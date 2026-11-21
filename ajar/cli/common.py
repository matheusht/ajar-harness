"""Shared CLI output and SQLite FTS5 probe helpers."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def _check_sqlite_fts5() -> bool:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x);")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()
