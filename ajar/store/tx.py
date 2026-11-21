"""Atomic `BEGIN IMMEDIATE` transaction manager and run-mutability guards for SQLite WAL."""

from __future__ import annotations

import contextlib
import itertools
import sqlite3
from collections.abc import Iterator

from ajar.domain.enums import RunStatus
from ajar.domain.models import InvalidTransitionError

CURRENT_SCHEMA_VERSION: int = 330

_SAVEPOINT_SEQ = itertools.count(1)


@contextlib.contextmanager
def immediate_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Execute a multi-statement SQLite mutation atomically under `BEGIN IMMEDIATE`.

    Safely nests via SQLite `SAVEPOINT` when the caller already opened a transaction.
    """
    if conn.in_transaction:
        sp = f"ajar_sp_{next(_SAVEPOINT_SEQ)}"
        conn.execute(f"SAVEPOINT {sp};")
        try:
            yield conn
        except BaseException:
            if conn.in_transaction:
                conn.execute(f"ROLLBACK TO SAVEPOINT {sp};")
                conn.execute(f"RELEASE SAVEPOINT {sp};")
            raise
        else:
            if conn.in_transaction:
                conn.execute(f"RELEASE SAVEPOINT {sp};")
        return

    conn.execute("BEGIN IMMEDIATE;")
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    else:
        if conn.in_transaction:
            conn.execute("COMMIT;")


def assert_run_mutable(conn: sqlite3.Connection, *, operation: str = "mutate") -> None:
    """Reject mutations against a sealed (`status = 'finished'`) run until explicitly reopened."""
    row = conn.execute("SELECT run_id, status FROM runs LIMIT 1").fetchone()
    if row is None:
        return
    status = str(row["status"] or RunStatus.ACTIVE.value)
    if status == RunStatus.FINISHED.value:
        raise InvalidTransitionError(
            "run.status",
            status,
            operation,
            entity_id=str(row["run_id"] or ""),
            reason="run is finished; run `ajar reopen <run_id>` before mutating state",
        )
