"""Transactional SQLite storage primitives for Ajar (`domain -> store -> services`)."""

from __future__ import annotations

from ajar.store.migrations import (
    SCHEMA_SQL,
    _ensure_v31_schema,
    _ensure_v32_schema,
    _ensure_v33_schema,
    _ensure_v322_schema,
)
from ajar.store.tx import CURRENT_SCHEMA_VERSION, assert_run_mutable, immediate_tx
from ajar.store.util import (
    PRIORITY_BASE_SALIENCE,
    _assert_no_symlink_components,
    compute_commitment_hash,
    compute_task_salience,
    get_ajar_home,
    infer_subsystem,
    list_rows,
    log_event,
    new_id,
    normalize_mechanism_key,
    open_run_db,
    parse_tag_list,
    recompute_all_open_salience,
    resolve_run_id,
    run_dir_for,
    utc_now_iso,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "PRIORITY_BASE_SALIENCE",
    "SCHEMA_SQL",
    "_assert_no_symlink_components",
    "_ensure_v31_schema",
    "_ensure_v32_schema",
    "_ensure_v322_schema",
    "_ensure_v33_schema",
    "assert_run_mutable",
    "compute_commitment_hash",
    "compute_task_salience",
    "get_ajar_home",
    "immediate_tx",
    "infer_subsystem",
    "list_rows",
    "log_event",
    "new_id",
    "normalize_mechanism_key",
    "open_run_db",
    "parse_tag_list",
    "recompute_all_open_salience",
    "resolve_run_id",
    "run_dir_for",
    "utc_now_iso",
]
