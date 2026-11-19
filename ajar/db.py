"""SQLite WAL state store and long-horizon coordination primitives for Ajar.

Stores all run state outside the target tree (`~/.ajar/runs/<run_id>/run.db`),
enforces `O_NOFOLLOW` symlink checks, scrubs secret patterns before persistence,
and implements:
- Work axis: `surfaces`, `surface_drivers`, `tasks` (with leases & integer salience)
- Truth axis: `claims`, `findings`, `chains`
- Long-horizon memory: `anomalies` (survive claim disproof), `primitives`,
  `certified_bindings` (`< 4 KB` context frames), 2-fail telemetry pivot, and
  `pulse` sweeps every 8 closed tasks
- Economics & attribution: `human_touches`, `spend_ledger`, `scope_rules`
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import sqlite3
import stat
import time
from datetime import datetime, timezone
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.redact import scrub_text

PRIORITY_BASE_SALIENCE: dict[str, int] = {
    "critical": 80,
    "high": 60,
    "medium": 40,
    "low": 20,
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    target_path TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    target_mode TEXT NOT NULL CHECK(target_mode IN ('source', 'binary', 'live')),
    workspace_mode TEXT NOT NULL CHECK(workspace_mode IN ('envelope', 'in_place')),
    goal TEXT NOT NULL,
    stopping_criterion TEXT NOT NULL DEFAULT 'exhaustive-high'
        CHECK(stopping_criterion IN ('exhaustive-high', 'first-verified-high')),
    budget_usd REAL NOT NULL DEFAULT 14.0,
    in_scope_loc INTEGER NOT NULL DEFAULT 0,
    code_quote_usd REAL NOT NULL DEFAULT 10.0,
    cogs_cap_usd REAL NOT NULL DEFAULT 3.5,
    pricing_mode TEXT NOT NULL DEFAULT 'commercial_code'
        CHECK(pricing_mode IN ('commercial_code', 'custom_or_bounty', 'uncapped_research')),
    commitment_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'verify_only', 'finished', 'blocked')),
    stop_reason TEXT DEFAULT '',
    closed_task_counter INTEGER NOT NULL DEFAULT 0,
    zero_skill_leases INTEGER NOT NULL DEFAULT 0,
    domain_skill_leases INTEGER NOT NULL DEFAULT 0,
    consecutive_stall_checks INTEGER NOT NULL DEFAULT 0,
    last_stop_event_id INTEGER NOT NULL DEFAULT 0,
    diff_range TEXT NOT NULL DEFAULT '',
    base_sha TEXT NOT NULL DEFAULT '',
    head_sha TEXT NOT NULL DEFAULT '',
    parent_run_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS scope_rules (
    run_id TEXT PRIMARY KEY,
    allowed_hosts_json TEXT NOT NULL DEFAULT '[]',
    allow_live_requests INTEGER NOT NULL DEFAULT 0,
    allow_live_mutations INTEGER NOT NULL DEFAULT 0,
    signed_by TEXT NOT NULL DEFAULT 'operator',
    raw_scope_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS surfaces (
    surface_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    locus TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'high'
        CHECK(priority IN ('critical', 'high', 'medium', 'low')),
    trust_boundary TEXT NOT NULL DEFAULT '',
    invariants_json TEXT NOT NULL DEFAULT '[]',
    requires_tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS surface_drivers (
    driver_id TEXT PRIMARY KEY,
    surface_id TEXT NOT NULL,
    setup_cmd TEXT NOT NULL,
    invoke_template TEXT NOT NULL,
    teardown_cmd TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(surface_id) REFERENCES surfaces(surface_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    parent_task_id TEXT,
    parent_claim_id TEXT,
    surface_id TEXT,
    kind TEXT NOT NULL
        CHECK(kind IN ('map', 'investigate', 'falsify', 'reproduce', 'instrument', 'chain', 'patch', 'escalate')),
    direction TEXT NOT NULL DEFAULT 'outside_in'
        CHECK(direction IN ('outside_in', 'inside_out', 'native_ffi', 'peer_symmetry')),
    title TEXT NOT NULL,
    subsystem TEXT NOT NULL DEFAULT '',
    locus TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'high'
        CHECK(priority IN ('critical', 'high', 'medium', 'low')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open', 'leased', 'done', 'dry', 'conditional_blocked')),
    worker_id TEXT,
    skill_mode TEXT NOT NULL DEFAULT 'domain'
        CHECK(skill_mode IN ('domain', 'zero_skill')),
    lease_expires_at REAL,
    dry_control_locus TEXT,
    dry_control_reason TEXT,
    blocker_predicate TEXT,
    blocker_check_locus TEXT,
    salience_score INTEGER NOT NULL DEFAULT 60,
    reopened_boost INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    slice_loc INTEGER NOT NULL DEFAULT 0,
    checkpoint_json TEXT NOT NULL DEFAULT '{}',
    diff_state TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_epoch REAL
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id TEXT PRIMARY KEY,
    surface_id TEXT,
    source_claim_id TEXT,
    subsystem TEXT NOT NULL DEFAULT '',
    locus TEXT NOT NULL,
    observation TEXT NOT NULL,
    repro_cmd TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unexplained'
        CHECK(status IN ('unexplained', 'benign_explained', 'consumed_by_claim', 'consumed_by_chain')),
    explanation_locus TEXT,
    explanation_reason TEXT,
    consumed_by_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS primitives (
    primitive_id TEXT PRIMARY KEY,
    surface_id TEXT,
    subsystem TEXT NOT NULL DEFAULT '',
    locus TEXT NOT NULL,
    kind TEXT NOT NULL,
    preconditions TEXT NOT NULL,
    postconditions TEXT NOT NULL,
    guarded_by_locus TEXT NOT NULL DEFAULT '',
    guard_assumption TEXT NOT NULL DEFAULT '',
    provides_tags_json TEXT NOT NULL DEFAULT '[]',
    requires_tags_json TEXT NOT NULL DEFAULT '[]',
    helper_id TEXT NOT NULL DEFAULT '',
    evidence_cmd TEXT NOT NULL,
    evidence_output TEXT NOT NULL DEFAULT '',
    chained INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS primitive_helpers (
    helper_id TEXT PRIMARY KEY,
    primitive_id TEXT NOT NULL,
    module_name TEXT NOT NULL UNIQUE,
    rel_helper_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    callable_name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'python',
    requires_tags_json TEXT NOT NULL DEFAULT '[]',
    provides_tags_json TEXT NOT NULL DEFAULT '[]',
    state_in_keys_json TEXT NOT NULL DEFAULT '[]',
    state_out_keys_json TEXT NOT NULL DEFAULT '[]',
    self_test_cmd TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    verification_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(primitive_id) REFERENCES primitives(primitive_id)
);

CREATE TABLE IF NOT EXISTS epistemic_hooks (
    hook_id TEXT PRIMARY KEY,
    hook_code TEXT NOT NULL,
    trigger_cmd TEXT NOT NULL,
    source_entity_id TEXT NOT NULL DEFAULT '',
    dedup_key TEXT NOT NULL UNIQUE,
    subsystem TEXT NOT NULL DEFAULT '',
    target_locus TEXT NOT NULL DEFAULT '',
    spawned_task_id TEXT,
    directive_text TEXT NOT NULL,
    kill_rule TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 30,
    max_leases INTEGER NOT NULL DEFAULT 2,
    leases_seen INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'consumed', 'expired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coverage_spans (
    span_id TEXT PRIMARY KEY,
    task_id TEXT,
    worker_id TEXT NOT NULL DEFAULT '',
    rel_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    file_sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certified_bindings (
    binding_id TEXT PRIMARY KEY,
    task_id TEXT,
    name TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    locus TEXT NOT NULL,
    file_sha256 TEXT NOT NULL DEFAULT '',
    line_start INTEGER NOT NULL DEFAULT 0,
    line_end INTEGER NOT NULL DEFAULT 0,
    valid INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    surface_id TEXT,
    proposer_worker_id TEXT NOT NULL,
    seeded_by_human INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    subsystem TEXT NOT NULL DEFAULT '',
    locus TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    mechanism_key TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'high'
        CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    falsification_prediction TEXT NOT NULL,
    falsification_test TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK(status IN (
            'proposed',
            'survived_falsify',
            'falsified',
            'needs_instrumentation',
            'reproduced',
            'rejected_repro',
            'duplicate_root_cause',
            'blocked',
            'config_gated'
        )),
    falsifier_worker_id TEXT,
    falsify_notes TEXT NOT NULL DEFAULT '',
    falsify_control_locus TEXT,
    config_gate TEXT NOT NULL DEFAULT '',
    diff_state TEXT NOT NULL DEFAULT '',
    failed_repro_count INTEGER NOT NULL DEFAULT 0,
    last_observation_hash TEXT NOT NULL DEFAULT '',
    instrumented_since_fail INTEGER NOT NULL DEFAULT 0,
    research_state TEXT NOT NULL DEFAULT 'candidate'
        CHECK(research_state IN ('candidate', 'rejected_during_research', 'confirmed')),
    evidence_state TEXT NOT NULL DEFAULT 'unverified'
        CHECK(evidence_state IN ('unverified', 'falsified', 'reproduced')),
    customer_state TEXT NOT NULL DEFAULT 'pending'
        CHECK(customer_state IN ('pending', 'accepted', 'disputed')),
    remediation_state TEXT NOT NULL DEFAULT 'unpatched'
        CHECK(remediation_state IN ('unpatched', 'micropatched', 'maintainer_patched')),
    duplicate_of_claim_id TEXT,
    env_blocker TEXT NOT NULL DEFAULT '',
    blocker_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    locus TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    poc_cmd TEXT NOT NULL,
    control_cmd TEXT NOT NULL,
    micropatch_path TEXT NOT NULL DEFAULT '',
    micropatch_diff TEXT NOT NULL DEFAULT '',
    arm1_clean_poc_json TEXT NOT NULL,
    arm2_clean_ctrl_json TEXT NOT NULL,
    arm3_patch_poc_json TEXT NOT NULL,
    arm4_patch_ctrl_json TEXT NOT NULL,
    oracle_json TEXT NOT NULL DEFAULT '{}',
    arm5a_release_poc_json TEXT NOT NULL DEFAULT '{}',
    arm5b_release_ctrl_json TEXT NOT NULL DEFAULT '{}',
    ub_divergence_class TEXT NOT NULL DEFAULT '',
    diff_state TEXT NOT NULL DEFAULT '',
    attribution TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE IF NOT EXISTS chains (
    chain_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'critical'
        CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    step_ids_json TEXT NOT NULL,
    e2e_poc_cmd TEXT NOT NULL,
    control_cmd TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    slot_index INTEGER NOT NULL DEFAULT -1,
    oracle_json TEXT NOT NULL DEFAULT '{}',
    ablation_matrix_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS human_touches (
    touch_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL
        CHECK(kind IN ('scope_authority', 'env_rescue', 'research_steering', 'poc_repair', 'review_signoff')),
    actor TEXT NOT NULL DEFAULT 'operator',
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spend_ledger (
    entry_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    surface_id TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT 'explore'
        CHECK(phase IN ('explore', 'verify')),
    model TEXT NOT NULL DEFAULT '',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS steers (
    steer_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'global'
        CHECK(scope IN ('global', 'subsystem', 'path')),
    target_filter TEXT NOT NULL DEFAULT '',
    rule_text TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT 'operator',
    touch_kind TEXT NOT NULL DEFAULT 'scope_authority'
        CHECK(touch_kind IN ('scope_authority', 'research_steering')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    revoke_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS patch_verifications (
    verification_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    patch_path TEXT NOT NULL,
    patch_diff TEXT NOT NULL,
    suite_cmd TEXT NOT NULL,
    variant_cmds_json TEXT NOT NULL,
    caller_audit TEXT NOT NULL,
    sibling_audit TEXT NOT NULL,
    arms_json TEXT NOT NULL,
    baseline_suite_json TEXT NOT NULL DEFAULT '{}',
    arm7_caller_cmd TEXT NOT NULL DEFAULT '',
    arm8_sibling_cmd TEXT NOT NULL DEFAULT '',
    arm9_revert_poc_json TEXT NOT NULL DEFAULT '{}',
    passed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES findings(finding_id),
    FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS repomap_symbols (
    symbol_id TEXT PRIMARY KEY,
    rel_path TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    pagerank REAL NOT NULL DEFAULT 0.0,
    signature TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS repomap_edges (
    src_file TEXT NOT NULL,
    dst_file TEXT NOT NULL,
    symbol TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS oracle_docs (
    doc_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('intent', 'reachability', 'precedent')),
    title TEXT NOT NULL,
    locus TEXT NOT NULL,
    body TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT 'untrusted_target'
);

CREATE VIRTUAL TABLE IF NOT EXISTS oracle_fts USING fts5(
    doc_id UNINDEXED,
    kind UNINDEXED,
    title,
    locus,
    body
);

CREATE TABLE IF NOT EXISTS threat_models (
    run_id TEXT PRIMARY KEY,
    principals_json TEXT NOT NULL DEFAULT '[]',
    assets_json TEXT NOT NULL DEFAULT '[]',
    consumer_tiers_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS threat_assumptions (
    assumption_id TEXT PRIMARY KEY,
    subsystem TEXT NOT NULL DEFAULT '',
    trust_boundary TEXT NOT NULL DEFAULT '',
    assumption_text TEXT NOT NULL,
    check_locus TEXT NOT NULL DEFAULT '',
    invalidated_by_tags_json TEXT NOT NULL DEFAULT '[]',
    dependent_surface_id TEXT NOT NULL DEFAULT '',
    escalate_priority TEXT NOT NULL DEFAULT 'critical'
        CHECK(escalate_priority IN ('critical', 'high')),
    status TEXT NOT NULL DEFAULT 'assumed'
        CHECK(status IN ('assumed', 'verified_holds', 'violated')),
    evidence_ref TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS swarm_dispatches (
    dispatch_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    stage TEXT NOT NULL CHECK(stage IN ('investigate', 'falsify', 'reproduce', 'chain')),
    wire_profile TEXT NOT NULL CHECK(wire_profile IN ('direct', 'swarm_patch_first', 'regression_tdd')),
    item_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'dispatched'
        CHECK(status IN ('dispatched', 'completed', 'filter_blocked', 'idle_no_return', 'refused')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_salience ON tasks(status, salience_score DESC);
CREATE INDEX IF NOT EXISTS idx_claims_locus_mech ON claims(locus, mechanism_key);
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_hooks_status_sub ON epistemic_hooks(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_cov_rel_path ON coverage_spans(rel_path, start_line, end_line);
CREATE INDEX IF NOT EXISTS idx_tm_assumptions_status ON threat_assumptions(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_swarm_dispatches_stage ON swarm_dispatches(stage, status, created_at DESC);
"""


class AjarError(Exception):
    """Structured error carrying an explicit CLI exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_USER_ERROR, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.details = details or {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


def get_ajar_home(explicit_home: pathlib.Path | str | None = None) -> pathlib.Path:
    raw = explicit_home or os.environ.get("AJAR_HOME") or (pathlib.Path.home() / ".ajar")
    return pathlib.Path(raw).expanduser()


def run_dir_for(run_id: str, ajar_home: pathlib.Path | str | None = None) -> pathlib.Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}", run_id):
        raise AjarError(f"Invalid run_id {run_id!r}.", EXIT_USER_ERROR)
    return get_ajar_home(ajar_home) / "runs" / run_id


def _assert_no_symlink_components(base_dir: pathlib.Path, target_path: pathlib.Path) -> None:
    """Reject symlink traversal anywhere under `base_dir` (`O_NOFOLLOW` equivalent)."""
    if base_dir.is_symlink():
        raise AjarError(f"Refusing symlinked AJAR_HOME: {base_dir}", EXIT_USER_ERROR)
    cur = base_dir
    try:
        rel_parts = target_path.relative_to(base_dir).parts
    except ValueError:
        if target_path.is_symlink():
            raise AjarError(f"Refusing symlinked database path: {target_path}", EXIT_USER_ERROR)
        return
    for part in rel_parts:
        cur = cur / part
        if cur.exists() or cur.is_symlink():
            st = os.lstat(cur)
            if stat.S_ISLNK(st.st_mode):
                raise AjarError(f"Refusing symlink component in run store: {cur}", EXIT_USER_ERROR)
            if cur == target_path and hasattr(os, "O_NOFOLLOW"):
                fd = os.open(str(cur), os.O_RDONLY | os.O_NOFOLLOW)
                os.close(fd)


def resolve_run_id(
    explicit_run_id: str | None = None,
    *,
    cwd: pathlib.Path | None = None,
    ajar_home: pathlib.Path | str | None = None,
) -> str:
    if explicit_run_id:
        return explicit_run_id.strip()
    env_id = os.environ.get("AJAR_RUN_ID", "").strip()
    if env_id:
        return env_id
    work = cwd or pathlib.Path.cwd()
    for candidate_dir in (work, *work.parents):
        marker = candidate_dir / ".ajar-run-id"
        if marker.is_file() and not marker.is_symlink():
            val = marker.read_text(encoding="utf-8").strip()
            if val:
                return val
    cur_file = get_ajar_home(ajar_home) / "current_run"
    if cur_file.is_file() and not cur_file.is_symlink():
        val = cur_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    raise AjarError(
        "No active run ID found. Pass --run <id>, set AJAR_RUN_ID, or run `ajar init <target>`.",
        EXIT_USER_ERROR,
    )


def _ensure_v31_schema(conn: sqlite3.Connection) -> None:
    """Idempotently migrate v3.0 SQLite databases to include v3.1 columns and tables."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not tables:
        return
    alter_specs = (
        ("runs", "cogs_cap_usd", "REAL NOT NULL DEFAULT 3.5"),
        ("runs", "pricing_mode", "TEXT NOT NULL DEFAULT 'commercial_code'"),
        ("tasks", "direction", "TEXT NOT NULL DEFAULT 'outside_in'"),
        ("primitives", "surface_id", "TEXT"),
        ("primitives", "guarded_by_locus", "TEXT NOT NULL DEFAULT ''"),
        ("primitives", "guard_assumption", "TEXT NOT NULL DEFAULT ''"),
        ("spend_ledger", "surface_id", "TEXT NOT NULL DEFAULT ''"),
    )
    for tbl, col, col_def in alter_specs:
        if tbl in tables:
            existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS steers (
            steer_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL DEFAULT 'global'
                CHECK(scope IN ('global', 'subsystem', 'path')),
            target_filter TEXT NOT NULL DEFAULT '',
            rule_text TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'operator',
            touch_kind TEXT NOT NULL DEFAULT 'scope_authority'
                CHECK(touch_kind IN ('scope_authority', 'research_steering')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            revoke_reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS patch_verifications (
            verification_id TEXT PRIMARY KEY,
            finding_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            patch_path TEXT NOT NULL,
            patch_diff TEXT NOT NULL,
            suite_cmd TEXT NOT NULL,
            variant_cmds_json TEXT NOT NULL,
            caller_audit TEXT NOT NULL,
            sibling_audit TEXT NOT NULL,
            arms_json TEXT NOT NULL,
            passed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(finding_id) REFERENCES findings(finding_id),
            FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
        );
        """
    )


def _ensure_v32_schema(conn: sqlite3.Connection) -> None:
    """Idempotently migrate v3.1 SQLite databases to include v3.2 columns, tables, and CHECK enums."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not tables:
        return
    alter_specs = (
        ("runs", "diff_range", "TEXT NOT NULL DEFAULT ''"),
        ("runs", "base_sha", "TEXT NOT NULL DEFAULT ''"),
        ("runs", "head_sha", "TEXT NOT NULL DEFAULT ''"),
        ("runs", "parent_run_id", "TEXT NOT NULL DEFAULT ''"),
        ("surfaces", "requires_tags_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("tasks", "parent_claim_id", "TEXT"),
        ("tasks", "slice_loc", "INTEGER NOT NULL DEFAULT 0"),
        ("tasks", "checkpoint_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("tasks", "diff_state", "TEXT NOT NULL DEFAULT ''"),
        ("primitives", "provides_tags_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("primitives", "requires_tags_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("primitives", "helper_id", "TEXT NOT NULL DEFAULT ''"),
        ("claims", "config_gate", "TEXT NOT NULL DEFAULT ''"),
        ("claims", "diff_state", "TEXT NOT NULL DEFAULT ''"),
        ("findings", "oracle_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("findings", "arm5a_release_poc_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("findings", "arm5b_release_ctrl_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("findings", "ub_divergence_class", "TEXT NOT NULL DEFAULT ''"),
        ("findings", "diff_state", "TEXT NOT NULL DEFAULT ''"),
        ("chains", "slot_index", "INTEGER NOT NULL DEFAULT -1"),
        ("chains", "oracle_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("chains", "ablation_matrix_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("patch_verifications", "baseline_suite_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("patch_verifications", "arm7_caller_cmd", "TEXT NOT NULL DEFAULT ''"),
        ("patch_verifications", "arm8_sibling_cmd", "TEXT NOT NULL DEFAULT ''"),
        ("patch_verifications", "arm9_revert_poc_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("oracle_docs", "provenance", "TEXT NOT NULL DEFAULT 'untrusted_target'"),
    )
    for tbl, col, col_def in alter_specs:
        if tbl in tables:
            existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS primitive_helpers (
            helper_id TEXT PRIMARY KEY,
            primitive_id TEXT NOT NULL,
            module_name TEXT NOT NULL UNIQUE,
            rel_helper_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            callable_name TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'python',
            requires_tags_json TEXT NOT NULL DEFAULT '[]',
            provides_tags_json TEXT NOT NULL DEFAULT '[]',
            state_in_keys_json TEXT NOT NULL DEFAULT '[]',
            state_out_keys_json TEXT NOT NULL DEFAULT '[]',
            self_test_cmd TEXT NOT NULL DEFAULT '',
            verified INTEGER NOT NULL DEFAULT 0,
            verification_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(primitive_id) REFERENCES primitives(primitive_id)
        );
        CREATE TABLE IF NOT EXISTS epistemic_hooks (
            hook_id TEXT PRIMARY KEY,
            hook_code TEXT NOT NULL,
            trigger_cmd TEXT NOT NULL,
            source_entity_id TEXT NOT NULL DEFAULT '',
            dedup_key TEXT NOT NULL UNIQUE,
            subsystem TEXT NOT NULL DEFAULT '',
            target_locus TEXT NOT NULL DEFAULT '',
            spawned_task_id TEXT,
            directive_text TEXT NOT NULL,
            kill_rule TEXT NOT NULL,
            token_estimate INTEGER NOT NULL DEFAULT 30,
            max_leases INTEGER NOT NULL DEFAULT 2,
            leases_seen INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active', 'consumed', 'expired')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coverage_spans (
            span_id TEXT PRIMARY KEY,
            task_id TEXT,
            worker_id TEXT NOT NULL DEFAULT '',
            rel_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            file_sha256 TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS threat_models (
            run_id TEXT PRIMARY KEY,
            principals_json TEXT NOT NULL DEFAULT '[]',
            assets_json TEXT NOT NULL DEFAULT '[]',
            consumer_tiers_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS threat_assumptions (
            assumption_id TEXT PRIMARY KEY,
            subsystem TEXT NOT NULL DEFAULT '',
            trust_boundary TEXT NOT NULL DEFAULT '',
            assumption_text TEXT NOT NULL,
            check_locus TEXT NOT NULL DEFAULT '',
            invalidated_by_tags_json TEXT NOT NULL DEFAULT '[]',
            dependent_surface_id TEXT NOT NULL DEFAULT '',
            escalate_priority TEXT NOT NULL DEFAULT 'critical'
                CHECK(escalate_priority IN ('critical', 'high')),
            status TEXT NOT NULL DEFAULT 'assumed'
                CHECK(status IN ('assumed', 'verified_holds', 'violated')),
            evidence_ref TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hooks_status_sub ON epistemic_hooks(status, subsystem);
        CREATE INDEX IF NOT EXISTS idx_cov_rel_path ON coverage_spans(rel_path, start_line, end_line);
        CREATE INDEX IF NOT EXISTS idx_tm_assumptions_status ON threat_assumptions(status, subsystem);
        """
    )

    # Upgrade legacy CHECK constraints on `tasks.kind` (`'escalate'`) and `claims.status` (`'config_gated'`) if needed.
    tasks_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
    if tasks_ddl and "'escalate'" not in str(tasks_ddl[0] or ""):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        csv_cols = ", ".join(cols)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE tasks RENAME TO _tasks_v31_old;
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                parent_task_id TEXT,
                parent_claim_id TEXT,
                surface_id TEXT,
                kind TEXT NOT NULL
                    CHECK(kind IN ('map', 'investigate', 'falsify', 'reproduce', 'instrument', 'chain', 'patch', 'escalate')),
                direction TEXT NOT NULL DEFAULT 'outside_in'
                    CHECK(direction IN ('outside_in', 'inside_out', 'native_ffi', 'peer_symmetry')),
                title TEXT NOT NULL,
                subsystem TEXT NOT NULL DEFAULT '',
                locus TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'high'
                    CHECK(priority IN ('critical', 'high', 'medium', 'low')),
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open', 'leased', 'done', 'dry', 'conditional_blocked')),
                worker_id TEXT,
                skill_mode TEXT NOT NULL DEFAULT 'domain'
                    CHECK(skill_mode IN ('domain', 'zero_skill')),
                lease_expires_at REAL,
                dry_control_locus TEXT,
                dry_control_reason TEXT,
                blocker_predicate TEXT,
                blocker_check_locus TEXT,
                salience_score INTEGER NOT NULL DEFAULT 60,
                reopened_boost INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                slice_loc INTEGER NOT NULL DEFAULT 0,
                checkpoint_json TEXT NOT NULL DEFAULT '{{}}',
                diff_state TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_epoch REAL
            );
            INSERT INTO tasks({csv_cols}) SELECT {csv_cols} FROM _tasks_v31_old;
            DROP TABLE _tasks_v31_old;
            CREATE INDEX IF NOT EXISTS idx_tasks_status_salience ON tasks(status, salience_score DESC);
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    claims_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='claims'").fetchone()
    if claims_ddl and "'config_gated'" not in str(claims_ddl[0] or ""):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(claims)").fetchall()]
        csv_cols = ", ".join(cols)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE claims RENAME TO _claims_v31_old;
            CREATE TABLE claims (
                claim_id TEXT PRIMARY KEY,
                surface_id TEXT,
                proposer_worker_id TEXT NOT NULL,
                seeded_by_human INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                subsystem TEXT NOT NULL DEFAULT '',
                locus TEXT NOT NULL,
                mechanism TEXT NOT NULL,
                mechanism_key TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'high'
                    CHECK(severity IN ('critical', 'high', 'medium', 'low')),
                falsification_prediction TEXT NOT NULL,
                falsification_test TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed'
                    CHECK(status IN (
                        'proposed',
                        'survived_falsify',
                        'falsified',
                        'needs_instrumentation',
                        'reproduced',
                        'rejected_repro',
                        'duplicate_root_cause',
                        'blocked',
                        'config_gated'
                    )),
                falsifier_worker_id TEXT,
                falsify_notes TEXT NOT NULL DEFAULT '',
                falsify_control_locus TEXT,
                config_gate TEXT NOT NULL DEFAULT '',
                diff_state TEXT NOT NULL DEFAULT '',
                failed_repro_count INTEGER NOT NULL DEFAULT 0,
                last_observation_hash TEXT NOT NULL DEFAULT '',
                instrumented_since_fail INTEGER NOT NULL DEFAULT 0,
                research_state TEXT NOT NULL DEFAULT 'candidate'
                    CHECK(research_state IN ('candidate', 'rejected_during_research', 'confirmed')),
                evidence_state TEXT NOT NULL DEFAULT 'unverified'
                    CHECK(evidence_state IN ('unverified', 'falsified', 'reproduced')),
                customer_state TEXT NOT NULL DEFAULT 'pending'
                    CHECK(customer_state IN ('pending', 'accepted', 'disputed')),
                remediation_state TEXT NOT NULL DEFAULT 'unpatched'
                    CHECK(remediation_state IN ('unpatched', 'micropatched', 'maintainer_patched')),
                duplicate_of_claim_id TEXT,
                blocker_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO claims({csv_cols}) SELECT {csv_cols} FROM _claims_v31_old;
            DROP TABLE _claims_v31_old;
            CREATE INDEX IF NOT EXISTS idx_claims_locus_mech ON claims(locus, mechanism_key);
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")


def _ensure_v322_schema(conn: sqlite3.Connection) -> None:
    """Idempotently migrate v3.2/v3.2.1 SQLite databases to include v3.2.2 columns and tables."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not tables:
        return
    if "claims" in tables:
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(claims)").fetchall()}
        if "env_blocker" not in existing_cols:
            conn.execute("ALTER TABLE claims ADD COLUMN env_blocker TEXT NOT NULL DEFAULT ''")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS swarm_dispatches (
            dispatch_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            stage TEXT NOT NULL CHECK(stage IN ('investigate', 'falsify', 'reproduce', 'chain')),
            wire_profile TEXT NOT NULL CHECK(wire_profile IN ('direct', 'swarm_patch_first', 'regression_tdd')),
            item_ids_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'dispatched'
                CHECK(status IN ('dispatched', 'completed', 'filter_blocked', 'idle_no_return', 'refused')),
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_swarm_dispatches_stage ON swarm_dispatches(stage, status, created_at DESC);
        """
    )


def open_run_db(
    run_id_or_path: str | pathlib.Path,
    *,
    create: bool = False,
    ajar_home: pathlib.Path | str | None = None,
) -> sqlite3.Connection:
    home = get_ajar_home(ajar_home)
    p = pathlib.Path(run_id_or_path)
    if p.suffix == ".db" or "/" in str(run_id_or_path):
        db_path = p
    else:
        db_path = run_dir_for(str(run_id_or_path), home) / "run.db"

    if create:
        home.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_components(home, db_path.parent)
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_no_symlink_components(home, db_path)

    if not create and not db_path.is_file():
        raise AjarError(f"Run database does not exist: {db_path}", EXIT_USER_ERROR)

    conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    if create:
        conn.executescript(SCHEMA_SQL)
    else:
        _ensure_v31_schema(conn)
        _ensure_v32_schema(conn)
        _ensure_v322_schema(conn)
    return conn


def log_event(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    entity_id: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    clean_payload = scrub_text(json.dumps(payload or {}, sort_keys=True))
    cur = conn.execute(
        "INSERT INTO events(ts, actor, action, entity_id, payload_json) VALUES (?, ?, ?, ?, ?)",
        (utc_now_iso(), scrub_text(actor), action, entity_id, clean_payload),
    )
    return int(cur.lastrowid or 0)


def normalize_mechanism_key(mechanism: str) -> str:
    tokens = re.findall(r"[a-z0-9_]+", mechanism.lower())
    stop = {"the", "a", "an", "in", "on", "to", "of", "at", "by", "with", "via", "when", "is", "are"}
    filtered = [t for t in tokens if t not in stop]
    return " ".join(filtered[:16])


def infer_subsystem(locus: str) -> str:
    path_part = locus.split(":", 1)[0].strip().lstrip("./")
    parts = [p for p in path_part.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts else "root"


def compute_commitment_hash(target_sha256: str, goal: str, stopping_criterion: str, created_at: str) -> str:
    canonical = json.dumps(
        {
            "created_at": created_at,
            "goal": goal,
            "schema": "ajar-research-ledger/1",
            "stopping_criterion": stopping_criterion,
            "target_sha256": target_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def compute_task_salience(conn: sqlite3.Connection, task_row: sqlite3.Row | dict[str, Any]) -> int:
    priority = str(task_row["priority"] or "high")
    subsystem = str(task_row["subsystem"] or "")
    locus = str(task_row["locus"] or "")
    reopened_boost = int(task_row["reopened_boost"] or 0)

    score = PRIORITY_BASE_SALIENCE.get(priority, 60) + reopened_boost

    # Subtract -3 per consecutive recent `dry` sibling in the same subsystem (forces subsystem pivot).
    if subsystem:
        recent_siblings = conn.execute(
            """
            SELECT status FROM tasks
            WHERE subsystem = ? AND status IN ('done', 'dry')
            ORDER BY closed_epoch DESC, updated_at DESC
            LIMIT 10
            """,
            (subsystem,),
        ).fetchall()
        consecutive_dry = 0
        for r in recent_siblings:
            if r["status"] == "dry":
                consecutive_dry += 1
            else:
                break
        score -= 3 * consecutive_dry

        unexplained_anom = conn.execute(
            "SELECT COUNT(*) AS c FROM anomalies WHERE status = 'unexplained' AND (subsystem = ? OR locus = ?)",
            (subsystem, locus),
        ).fetchone()["c"]
        if unexplained_anom > 0:
            score += 10

    if locus:
        unchained_prim = conn.execute(
            "SELECT COUNT(*) AS c FROM primitives WHERE chained = 0 AND (locus = ? OR subsystem = ?)",
            (locus, subsystem),
        ).fetchone()["c"]
        if unchained_prim > 0:
            score += 8

    return max(1, score)


def recompute_all_open_salience(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM tasks WHERE status = 'open'").fetchall()
    for row in rows:
        new_score = compute_task_salience(conn, row)
        conn.execute("UPDATE tasks SET salience_score = ? WHERE task_id = ?", (new_score, row["task_id"]))
    return len(rows)


def check_dead_end_repetition(
    conn: sqlite3.Connection,
    *,
    locus: str,
    mechanism: str,
    consume_anomaly_id: str | None = None,
) -> None:
    """Pre-flight `< 5 ms` guard blocking repetitive dead-end hypotheses."""
    if consume_anomaly_id:
        anom = conn.execute(
            "SELECT status FROM anomalies WHERE anomaly_id = ?",
            (consume_anomaly_id,),
        ).fetchone()
        if anom and anom["status"] == "unexplained":
            return

    mech_key = normalize_mechanism_key(mechanism)
    prior_claim = conn.execute(
        """
        SELECT claim_id, status, falsify_notes FROM claims
        WHERE locus = ? AND mechanism_key = ?
          AND status IN ('falsified', 'rejected_repro', 'duplicate_root_cause')
        LIMIT 1
        """,
        (locus.strip(), mech_key),
    ).fetchone()
    if prior_claim:
        raise AjarError(
            f"Blocked repetitive hypothesis at {locus}: matches prior {prior_claim['status']} "
            f"claim {prior_claim['claim_id']} ({prior_claim['falsify_notes'][:120]}). "
            "Cite a fresh unexplained --consume-anomaly <id> if target behavior changed.",
            EXIT_GATE_BLOCKED,
            {"prior_claim_id": prior_claim["claim_id"], "status": prior_claim["status"]},
        )

    prior_dry = conn.execute(
        """
        SELECT task_id, dry_control_locus, dry_control_reason FROM tasks
        WHERE status = 'dry' AND locus = ?
        LIMIT 1
        """,
        (locus.strip(),),
    ).fetchone()
    if prior_dry and mech_key:
        dry_key = normalize_mechanism_key(prior_dry["dry_control_reason"] or "")
        mech_words = set(mech_key.split())
        dry_words = set(dry_key.split())
        if mech_words and len(mech_words & dry_words) >= max(2, len(mech_words) // 2):
            raise AjarError(
                f"Blocked repetitive hypothesis at {locus}: already closed dry in {prior_dry['task_id']} "
                f"via control {prior_dry['dry_control_locus']}. Cite --consume-anomaly <id> to reopen.",
                EXIT_GATE_BLOCKED,
                {"prior_task_id": prior_dry["task_id"]},
            )


def lease_next_task(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    kind: str | None = None,
    ttl_sec: int = 900,
    recover: bool = False,
) -> dict[str, Any] | None:
    """Atomically lease the highest-salience open task and enforce Zero-Skill quota."""
    now = time.time()
    now_iso = utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Expire stale leases first (`escalate` tasks are single-pass `max_leases=1` and close instead of looping).
        conn.execute(
            """
            UPDATE tasks
            SET status = CASE WHEN kind = 'escalate' THEN 'done' ELSE 'open' END,
                worker_id = CASE WHEN kind = 'escalate' THEN worker_id ELSE NULL END,
                lease_expires_at = NULL,
                attempt_count = attempt_count + 1,
                summary = CASE WHEN kind = 'escalate' AND summary = '' THEN 'Single-pass escalate lease expired' ELSE summary END,
                updated_at = ?
            WHERE status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (now_iso, now),
        )

        if recover:
            existing = conn.execute(
                "SELECT * FROM tasks WHERE status = 'leased' AND worker_id = ? ORDER BY updated_at DESC LIMIT 1",
                (worker_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE tasks SET lease_expires_at = ?, updated_at = ? WHERE task_id = ?",
                    (now + ttl_sec, now_iso, existing["task_id"]),
                )
                conn.commit()
                out = dict(existing)
                out["suppress_domain_skills"] = out["skill_mode"] == "zero_skill"
                return out

        run_row = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        verify_only = bool(run_row and run_row["status"] == "verify_only")

        if kind:
            if verify_only and kind in ("map", "investigate"):
                conn.commit()
                return None
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'open' AND kind = ?
                ORDER BY salience_score DESC, created_at ASC
                LIMIT 1
                """,
                (kind,),
            ).fetchone()
        elif verify_only:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'open' AND kind IN ('falsify', 'reproduce', 'instrument', 'chain', 'patch', 'escalate')
                ORDER BY salience_score DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'open'
                ORDER BY salience_score DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            conn.commit()
            return None

        skill_mode = "domain"
        if row["kind"] == "investigate" and run_row is not None:
            prev_mode = conn.execute(
                """
                SELECT skill_mode FROM tasks
                WHERE worker_id = ? AND kind = 'investigate'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (worker_id,),
            ).fetchone()
            if prev_mode is not None:
                skill_mode = prev_mode["skill_mode"]
            else:
                distinct_prev_workers = conn.execute(
                    "SELECT COUNT(DISTINCT worker_id) AS c FROM tasks WHERE kind = 'investigate' AND worker_id IS NOT NULL AND worker_id != ?",
                    (worker_id,),
                ).fetchone()["c"]
                if distinct_prev_workers >= 1 and int(run_row["zero_skill_leases"]) == 0:
                    skill_mode = "zero_skill"

            if skill_mode == "zero_skill":
                conn.execute("UPDATE runs SET zero_skill_leases = zero_skill_leases + 1")
            else:
                conn.execute("UPDATE runs SET domain_skill_leases = domain_skill_leases + 1")

        conn.execute(
            """
            UPDATE tasks
            SET status = 'leased', worker_id = ?, skill_mode = ?, lease_expires_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (worker_id, skill_mode, now + ttl_sec, now_iso, row["task_id"]),
        )
        log_event(
            conn,
            worker_id,
            "task_leased",
            row["task_id"],
            {"kind": row["kind"], "skill_mode": skill_mode, "salience_score": row["salience_score"]},
        )
        updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
        conn.commit()
        out = dict(updated)
        out["suppress_domain_skills"] = skill_mode == "zero_skill"
        return out
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def maybe_auto_pulse(conn: sqlite3.Connection, target_dir: pathlib.Path | None = None) -> dict[str, Any] | None:
    """Increment closed_task_counter and trigger `run_pulse` every 8 closed tasks."""
    conn.execute("UPDATE runs SET closed_task_counter = closed_task_counter + 1")
    cnt = conn.execute("SELECT closed_task_counter FROM runs LIMIT 1").fetchone()["closed_task_counter"]
    recompute_all_open_salience(conn)
    if int(cnt) % 8 == 0:
        return run_pulse(conn, target_dir=target_dir)
    return None


def file_locus_sha256(target_dir: pathlib.Path, locus: str) -> tuple[str, int, int]:
    """Compute SHA-256 of the referenced line slice (`file:start-end` or `file:line`)."""
    raw_file, _, span = locus.partition(":")
    rel_file = raw_file.strip().lstrip("/")
    fpath = (target_dir / rel_file).resolve()
    try:
        fpath.relative_to(target_dir.resolve())
    except ValueError:
        return ("", 0, 0)
    if not fpath.is_file():
        return ("", 0, 0)

    lines = fpath.read_bytes().splitlines(keepends=True)
    start_line = 1
    end_line = len(lines)
    if span:
        m = re.match(r"^(\d+)(?:-(\d+))?", span.strip())
        if m:
            start_line = max(1, int(m.group(1)))
            end_line = int(m.group(2)) if m.group(2) else start_line
            end_line = min(len(lines), max(start_line, end_line))
    excerpt = b"".join(lines[start_line - 1 : end_line])
    return (hashlib.sha256(excerpt).hexdigest(), start_line, end_line)


def set_certified_binding(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    name: str,
    value: str,
    locus: str,
    task_id: str | None = None,
    actor: str = "worker",
) -> dict[str, Any]:
    sha, s_line, e_line = file_locus_sha256(target_dir, locus)
    now_iso = utc_now_iso()
    clean_val = scrub_text(value)
    existing = conn.execute("SELECT binding_id FROM certified_bindings WHERE name = ?", (name,)).fetchone()
    binding_id = existing["binding_id"] if existing else new_id("bind")
    conn.execute(
        """
        INSERT INTO certified_bindings(
            binding_id, task_id, name, value, locus, file_sha256, line_start, line_end, valid, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            task_id = excluded.task_id,
            value = excluded.value,
            locus = excluded.locus,
            file_sha256 = excluded.file_sha256,
            line_start = excluded.line_start,
            line_end = excluded.line_end,
            valid = 1,
            updated_at = excluded.updated_at
        """,
        (binding_id, task_id, name, clean_val, locus, sha, s_line, e_line, now_iso, now_iso),
    )
    # Recording new target binding also satisfies pending instrumentation on matching locus!
    conn.execute(
        """
        UPDATE claims
        SET instrumented_since_fail = 1,
            status = CASE WHEN status = 'needs_instrumentation' THEN 'survived_falsify' ELSE status END,
            updated_at = ?
        WHERE locus = ? AND status IN ('needs_instrumentation', 'survived_falsify')
        """,
        (now_iso, locus),
    )
    log_event(conn, actor, "binding_certified", binding_id, {"name": name, "locus": locus})
    return {
        "binding_id": binding_id,
        "name": name,
        "value": clean_val,
        "locus": locus,
        "file_sha256": sha,
        "valid": 1,
    }


def add_steer(
    conn: sqlite3.Connection,
    *,
    rule_text: str,
    scope: str = "global",
    target_filter: str = "",
    author: str = "operator",
    touch_kind: str = "scope_authority",
    record_human_touch: bool = True,
) -> dict[str, Any]:
    """Persist an attributable workspace Steer (`DEC-0049` / `DEC-0061`)."""
    if scope not in ("global", "subsystem", "path"):
        raise AjarError(f"Unsupported steer scope: {scope!r}", EXIT_USER_ERROR)
    if touch_kind not in ("scope_authority", "research_steering"):
        raise AjarError(f"Unsupported steer touch_kind: {touch_kind!r}", EXIT_USER_ERROR)
    clean_rule = scrub_text(rule_text.strip())
    if len(clean_rule) < 5:
        raise AjarError("Steer rule_text must be at least 5 characters.", EXIT_USER_ERROR)

    sid = new_id("str")
    now_iso = utc_now_iso()
    clean_filter = scrub_text(target_filter.strip())
    clean_author = scrub_text(author.strip() or "operator")
    conn.execute(
        """
        INSERT INTO steers(steer_id, scope, target_filter, rule_text, author, touch_kind, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (sid, scope, clean_filter, clean_rule, clean_author, touch_kind, now_iso),
    )
    touch_id = None
    if record_human_touch and clean_author != "system":
        touch_id = new_id("tch")
        conn.execute(
            "INSERT INTO human_touches(touch_id, kind, actor, notes, created_at) VALUES (?, ?, ?, ?, ?)",
            (touch_id, touch_kind, clean_author, f"steer {sid} [{scope}:{clean_filter or '*'}]: {clean_rule[:160]}", now_iso),
        )
    log_event(
        conn,
        clean_author,
        "steer_added",
        sid,
        {"scope": scope, "target_filter": clean_filter, "touch_kind": touch_kind, "touch_id": touch_id},
    )
    return {
        "steer_id": sid,
        "scope": scope,
        "target_filter": clean_filter,
        "rule_text": clean_rule,
        "author": clean_author,
        "touch_kind": touch_kind,
        "touch_id": touch_id,
        "active": 1,
    }


def list_steers(
    conn: sqlite3.Connection,
    *,
    active_only: bool = False,
    subsystem: str = "",
    locus: str = "",
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM steers"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY steer_id ASC"
    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    if not subsystem and not locus:
        return rows
    matched: list[dict[str, Any]] = []
    loc_file = locus.split(":", 1)[0].strip().lstrip("./")
    for r in rows:
        sc = r["scope"]
        flt = (r["target_filter"] or "").strip().lstrip("./")
        if sc == "global" or not flt:
            matched.append(r)
        elif sc == "subsystem" and subsystem and (subsystem == flt or subsystem.startswith(flt + "/")):
            matched.append(r)
        elif sc == "path" and loc_file and (loc_file.startswith(flt) or flt in loc_file):
            matched.append(r)
    return matched


def revoke_steer(
    conn: sqlite3.Connection,
    *,
    steer_id: str,
    reason: str,
    actor: str = "operator",
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM steers WHERE steer_id = ?", (steer_id,)).fetchone()
    if row is None:
        raise AjarError(f"Unknown steer_id: {steer_id}", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    clean_reason = scrub_text(reason.strip() or "revoked")
    conn.execute(
        "UPDATE steers SET active = 0, revoked_at = ?, revoke_reason = ? WHERE steer_id = ?",
        (now_iso, clean_reason, steer_id),
    )
    log_event(conn, actor, "steer_revoked", steer_id, {"reason": clean_reason})
    return {"steer_id": steer_id, "active": 0, "revoked_at": now_iso, "revoke_reason": clean_reason}


def rescope_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    worker_id: str,
    reason: str,
    title: str | None = None,
    locus: str | None = None,
    mechanism: str | None = None,
    severity: str | None = None,
    falsification_prediction: str | None = None,
    falsification_test: str | None = None,
) -> dict[str, Any]:
    """Re-scope a candidate claim when locus, preconditions, or severity shift (`claim_mismatch` recovery)."""
    clm = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if clm is None:
        raise AjarError(f"Unknown claim_id: {claim_id}", EXIT_USER_ERROR)
    if clm["status"] == "reproduced":
        raise AjarError(
            f"Truth-axis monotonicity gate: verified reproduced claim {claim_id} cannot be rescoped in place.",
            EXIT_GATE_BLOCKED,
        )
    if len(reason.strip()) < 8:
        raise AjarError("Claim rescope --reason must be at least 8 characters.", EXIT_USER_ERROR)

    new_title = scrub_text(title.strip()) if title else str(clm["title"])
    new_locus = locus.strip() if locus else str(clm["locus"])
    new_mech = scrub_text(mechanism.strip()) if mechanism else str(clm["mechanism"])
    new_sev = severity.strip() if severity else str(clm["severity"])
    new_pred = scrub_text(falsification_prediction.strip()) if falsification_prediction else str(clm["falsification_prediction"])
    new_test = scrub_text(falsification_test.strip()) if falsification_test else str(clm["falsification_test"])
    new_sub = infer_subsystem(new_locus)
    new_mech_key = normalize_mechanism_key(new_mech)

    # Re-run independent falsification whenever root-cause locus or mechanism changed.
    root_changed = (new_locus != clm["locus"]) or (new_mech_key != clm["mechanism_key"])
    new_status = "proposed" if root_changed or clm["status"] in ("falsified", "rejected_repro") else str(clm["status"])
    new_falsifier = None if new_status == "proposed" else clm["falsifier_worker_id"]
    now_iso = utc_now_iso()

    conn.execute(
        """
        UPDATE claims
        SET title = ?, subsystem = ?, locus = ?, mechanism = ?, mechanism_key = ?,
            severity = ?, falsification_prediction = ?, falsification_test = ?,
            status = ?, falsifier_worker_id = ?, research_state = 'candidate',
            evidence_state = CASE WHEN ? = 'proposed' THEN 'unverified' ELSE evidence_state END,
            failed_repro_count = CASE WHEN ? THEN 0 ELSE failed_repro_count END,
            updated_at = ?
        WHERE claim_id = ?
        """,
        (
            new_title,
            new_sub,
            new_locus,
            new_mech,
            new_mech_key,
            new_sev,
            new_pred,
            new_test,
            new_status,
            new_falsifier,
            new_status,
            1 if root_changed else 0,
            now_iso,
            claim_id,
        ),
    )
    log_event(
        conn,
        worker_id,
        "claim_rescoped",
        claim_id,
        {
            "old_locus": clm["locus"],
            "new_locus": new_locus,
            "old_severity": clm["severity"],
            "new_severity": new_sev,
            "new_status": new_status,
            "reason": scrub_text(reason[:200]),
        },
    )
    return {
        "claim_id": claim_id,
        "status": new_status,
        "locus": new_locus,
        "severity": new_sev,
        "root_changed": root_changed,
    }


def checkpoint_task(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    state_dict: dict[str, Any],
) -> dict[str, Any]:
    """Persist structured trajectory checkpoint JSON onto `tasks.checkpoint_json` for clean session resume."""
    row = conn.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    clean_json = scrub_text(json.dumps(state_dict, sort_keys=True))
    if len(clean_json.encode("utf-8")) > 2048:
        raise AjarError("Task checkpoint exceeds 2 KB limit; store concise loci and verified facts only.", EXIT_USER_ERROR)
    now_iso = utc_now_iso()
    conn.execute(
        "UPDATE tasks SET checkpoint_json = ?, updated_at = ? WHERE task_id = ?",
        (clean_json, now_iso, task_id),
    )
    log_event(conn, worker_id, "task_checkpointed", task_id, {"keys": sorted(state_dict.keys())})
    return {"task_id": task_id, "checkpoint": json.loads(clean_json), "updated_at": now_iso}


def record_coverage_span(
    conn: sqlite3.Connection,
    *,
    target_dir: pathlib.Path,
    task_id: str | None,
    worker_id: str,
    rel_path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    """Record an audited source line range (`coverage_spans`) bound to file SHA-256."""
    clean_rel = rel_path.strip().lstrip("./")
    if start_line < 1 or end_line < start_line:
        raise AjarError(f"Invalid line span {start_line}..{end_line} for {clean_rel}.", EXIT_USER_ERROR)
    sha, s_ln, e_ln = file_locus_sha256(target_dir, f"{clean_rel}:{start_line}-{end_line}")
    if not sha:
        raise AjarError(f"Target file not found for coverage span: {clean_rel}", EXIT_USER_ERROR)
    sid = new_id("cov")
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO coverage_spans(span_id, task_id, worker_id, rel_path, start_line, end_line, file_sha256, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, task_id, scrub_text(worker_id), clean_rel, s_ln, e_ln, sha, now_iso),
    )
    return {
        "span_id": sid,
        "task_id": task_id,
        "rel_path": clean_rel,
        "start_line": s_ln,
        "end_line": e_ln,
        "file_sha256": sha,
    }


def render_task_context(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    record_exposure: bool = False,
) -> dict[str, Any]:
    """Build a prefix-stable `< 4 KB` (`<= 50` lines) certified context projection.

    Places run-invariant sections (`Goal`, `Active Workspace Steers`, sorted `Certified Bindings`)
    at the top of the prompt so multi-worker LLM calls hit provider KV prompt caches, followed
    by the task-specific delta (`Capability Bridges`, `Active Epistemic Hooks`, `Dead Ends`) at the tail.
    """
    from ajar.epistemic_hooks import (
        detect_capability_bridges,
        record_hook_lease_exposure,
        select_active_hooks_for_task,
    )

    task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if task is None:
        raise AjarError(f"Unknown task_id: {task_id}", EXIT_USER_ERROR)
    run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()

    lineage: list[str] = []
    cur = task
    depth = 0
    while cur is not None and depth < 6:
        lineage.append(f"{cur['task_id']}[{cur['kind']}] {cur['title']}")
        parent_id = cur["parent_task_id"]
        cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (parent_id,)).fetchone() if parent_id else None
        depth += 1
    lineage.reverse()

    # Deterministic name-sorted bindings keep the top prompt prefix byte-identical across tasks.
    bindings = conn.execute(
        "SELECT name, value, locus FROM certified_bindings WHERE valid = 1 ORDER BY name ASC LIMIT 8"
    ).fetchall()
    sub = task["subsystem"] or infer_subsystem(task["locus"] or "")
    direction = str(task["direction"] if "direction" in task.keys() and task["direction"] else "outside_in")
    # Global steers only in the invariant prefix so cross-subsystem tasks share identical top bytes;
    # path/subsystem steers appear in Task Delta if present.
    all_active_steers = list_steers(conn, active_only=True, subsystem=sub, locus=str(task["locus"] or ""))[:5]
    global_steers = [s for s in all_active_steers if s["scope"] == "global"]
    scoped_steers = [s for s in all_active_steers if s["scope"] != "global"]

    anomalies = conn.execute(
        """
        SELECT anomaly_id, locus, observation FROM anomalies
        WHERE status = 'unexplained' AND (subsystem = ? OR subsystem = '')
        ORDER BY created_at DESC LIMIT 3
        """,
        (sub,),
    ).fetchall()
    guarded_prims = conn.execute(
        """
        SELECT primitive_id, locus, kind, guarded_by_locus FROM primitives
        WHERE chained = 0 AND guarded_by_locus != '' AND (subsystem = ? OR locus = ? OR guarded_by_locus = ?)
        ORDER BY created_at DESC LIMIT 3
        """,
        (sub, task["locus"], task["locus"]),
    ).fetchall()
    dead_claims = conn.execute(
        """
        SELECT claim_id, locus, mechanism, status, diff_state FROM claims
        WHERE (subsystem = ? OR locus = ?)
          AND status IN ('falsified', 'rejected_repro', 'duplicate_root_cause', 'config_gated')
        ORDER BY updated_at DESC LIMIT 3
        """,
        (sub, task["locus"]),
    ).fetchall()
    dry_controls = conn.execute(
        """
        SELECT task_id, dry_control_locus, dry_control_reason FROM tasks
        WHERE status = 'dry' AND subsystem = ?
        ORDER BY updated_at DESC LIMIT 3
        """,
        (sub,),
    ).fetchall()

    bridges = detect_capability_bridges(conn, subsystem=sub, locus=str(task["locus"] or ""), limit=2)
    active_hooks = select_active_hooks_for_task(conn, task, limit=2)
    if active_hooks and record_exposure:
        record_hook_lease_exposure(conn, [str(h["hook_id"]) for h in active_hooks])

    # 1. Run-Invariant Cacheable Prefix (100% byte-identical across all tasks in the run!)
    prefix_lines: list[str] = [
        f"# Certified Run Prefix: {(run['run_id'] if run else 'run')}",
        f"Goal: {(run['goal'] if run else '')[:160]}",
    ]
    if global_steers:
        prefix_lines.append("## Active Workspace Steers (operator threat-model boundaries)")
        for st in global_steers:
            prefix_lines.append(f"- [{st['scope']}:{st['target_filter'] or '*'}] {st['rule_text'][:110]}")
    if bindings:
        prefix_lines.append("## Certified Bindings (valid=1)")
        for b in bindings:
            prefix_lines.append(f"- {b['name']} = {b['value'][:90]} @ {b['locus']}")

    # 2. Task-Specific Delta
    delta_lines: list[str] = [
        f"## Task Delta: {task['task_id']}",
        f"Mode: skill_mode={task['skill_mode']} | kind={task['kind']} | direction={direction} | salience={task['salience_score']}",
    ]
    if task["skill_mode"] == "zero_skill":
        delta_lines.append("Rule: ZERO-SKILL FIRST-PRINCIPLES LEASE. Do NOT read skills/domains/*; derive invariants strictly from target code.")
    delta_lines.append(f"Target Locus: {task['locus'] or '(unassigned)'} (subsystem: {sub or 'root'})")
    delta_lines.append("Lineage: " + " -> ".join(lineage))
    if scoped_steers:
        for st in scoped_steers[:2]:
            delta_lines.append(f"Subsystem Steer [{st['scope']}:{st['target_filter']}]: {st['rule_text'][:100]}")

    raw_ckpt = str(task["checkpoint_json"] if "checkpoint_json" in task.keys() else "{}") or "{}"
    if raw_ckpt != "{}":
        delta_lines.append(f"## Trajectory Checkpoint: {raw_ckpt[:180]}")

    if bridges:
        delta_lines.append("## Cross-Subsystem Capability Bridges")
        for br in bridges:
            if br["bridge_type"] == "guarded_sink_upstream_audit":
                delta_lines.append(
                    f"- [guard_ref] {br['sink_id']}@{br['sink_locus']} ({br['sink_subsystem']}) blocked by {br['guard_locus']}"
                )
            elif br["providers"]:
                pv = br["providers"][0]
                hlp = f" helper={pv['helper']}" if pv.get("helper") else ""
                mtags = ",".join(br["matched_tags"][:2])
                delta_lines.append(
                    f"- [{br['bridge_type']}] {pv['primitive_id']}@{pv['locus']} ({pv['subsystem']}) -> "
                    f"{br['sink_id']}@{br['sink_locus']} tags=[{mtags}]{hlp}"
                )
            else:
                delta_lines.append(
                    f"- [missing_provider] {br['sink_id']}@{br['sink_locus']} needs tags=[{','.join(br['missing_tags'][:2])}]"
                )

    violated_assumptions = conn.execute(
        """
        SELECT assumption_id, assumption_text, evidence_ref FROM threat_assumptions
        WHERE status = 'violated'
          AND (subsystem = ? OR subsystem = '' OR dependent_surface_id = ?)
        ORDER BY updated_at DESC LIMIT 2
        """,
        (sub, str(task["surface_id"] or "")),
    ).fetchall()
    if violated_assumptions:
        delta_lines.append("## Adaptive Threat-Model Shift (assumption violated)")
        for va in violated_assumptions:
            ev = f" by {va['evidence_ref']}" if va["evidence_ref"] else ""
            delta_lines.append(f"- {va['assumption_id']} [violated{ev}]: {va['assumption_text'][:85]}")

    if active_hooks:
        delta_lines.append("## Active Epistemic Hooks (obey Kill Rule to close dry fast)")
        for hk in active_hooks:
            delta_lines.append(f"- [{hk['hook_code']}] {hk['directive_text']} | Kill Rule: {hk['kill_rule']}")

    if guarded_prims:
        delta_lines.append("## Guarded Primitives (anti-premature-dry: test guard break before closing dry)")
        for gp in guarded_prims:
            delta_lines.append(f"- {gp['primitive_id']} [{gp['kind']}] @ {gp['locus']} guarded_by={gp['guarded_by_locus']}")
    if anomalies:
        delta_lines.append("## Unexplained Anomalies (must explain or consume)")
        for a in anomalies:
            delta_lines.append(f"- {a['anomaly_id']} @ {a['locus']}: {a['observation'][:100]}")
    if dead_claims or dry_controls:
        delta_lines.append("## Subsystem Dead Ends (do NOT repeat)")
        for dc in dead_claims:
            dtag = f"{dc['status']}:{dc['diff_state']}" if dc["diff_state"] else str(dc["status"])
            delta_lines.append(f"- {dc['claim_id']} [{dtag}] @ {dc['locus']}: {dc['mechanism'][:80]}")
        for dr in dry_controls:
            delta_lines.append(f"- {dr['task_id']} [dry] guard @ {dr['dry_control_locus']}: {(dr['dry_control_reason'] or '')[:80]}")

    # Enforce strict <= 50 lines and < 4096 bytes.
    max_delta = max(4, 48 - len(prefix_lines))
    delta_lines = delta_lines[:max_delta]
    certified_prefix = "\n".join(prefix_lines)
    task_delta = "\n".join(delta_lines)
    markdown = certified_prefix + "\n" + task_delta
    if len(markdown.encode("utf-8")) > 3900:
        markdown = markdown.encode("utf-8")[:3900].decode("utf-8", errors="ignore")

    return {
        "task_id": task["task_id"],
        "skill_mode": task["skill_mode"],
        "direction": direction,
        "suppress_domain_skills": task["skill_mode"] == "zero_skill",
        "salience_score": task["salience_score"],
        "steers_count": len(all_active_steers),
        "bindings_count": len(bindings),
        "bridges_count": len(bridges),
        "active_hooks_count": len(active_hooks),
        "active_hooks": [str(h["hook_code"]) for h in active_hooks],
        "unexplained_anomalies_count": len(anomalies),
        "dead_ends_count": len(dead_claims) + len(dry_controls),
        "certified_prefix": certified_prefix,
        "task_delta": task_delta,
        "rendered": markdown,
    }


def run_pulse(conn: sqlite3.Connection, *, target_dir: pathlib.Path | None = None) -> dict[str, Any]:
    """Deterministic maintenance sweep: expire leases/hooks, verify bindings, bridge tags, reopen unblocked tasks."""
    from ajar.epistemic_hooks import expire_stale_hooks, parse_tag_list

    now = time.time()
    now_iso = utc_now_iso()

    cur_exp = conn.execute(
        """
        UPDATE tasks
        SET status = CASE WHEN kind = 'escalate' THEN 'done' ELSE 'open' END,
            worker_id = CASE WHEN kind = 'escalate' THEN worker_id ELSE NULL END,
            lease_expires_at = NULL,
            attempt_count = attempt_count + 1,
            updated_at = ?
        WHERE status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
        """,
        (now_iso, now),
    )
    expired_leases = int(cur_exp.rowcount or 0)
    expired_hooks = expire_stale_hooks(conn)

    invalidated_bindings = 0
    if target_dir is not None and target_dir.is_dir():
        for b in conn.execute("SELECT binding_id, locus, file_sha256 FROM certified_bindings WHERE valid = 1").fetchall():
            if b["file_sha256"]:
                cur_sha, _, _ = file_locus_sha256(target_dir, b["locus"])
                if cur_sha and cur_sha != b["file_sha256"]:
                    conn.execute(
                        "UPDATE certified_bindings SET valid = 0, updated_at = ? WHERE binding_id = ?",
                        (now_iso, b["binding_id"]),
                    )
                    invalidated_bindings += 1

    # Check `conditional_blocked` tasks against newly discovered capability tags, primitives, anomalies, and findings.
    reopened_tasks: list[str] = []
    blocked_rows = conn.execute("SELECT * FROM tasks WHERE status = 'conditional_blocked'").fetchall()
    if blocked_rows:
        signal_blobs: list[str] = []
        provided_tag_set: set[str] = set()
        for p in conn.execute(
            "SELECT locus, kind, postconditions, guarded_by_locus, provides_tags_json FROM primitives"
        ).fetchall():
            ptags = parse_tag_list(p["provides_tags_json"])
            provided_tag_set.update(ptags)
            signal_blobs.append(
                f"{p['locus']} {p['kind']} {p['postconditions']} {p['guarded_by_locus']} {' '.join(ptags)}".lower()
            )
        for a in conn.execute("SELECT locus, observation FROM anomalies WHERE status = 'unexplained'").fetchall():
            signal_blobs.append(f"{a['locus']} {a['observation']}".lower())
        for f in conn.execute("SELECT locus, title, root_cause FROM findings").fetchall():
            signal_blobs.append(f"{f['locus']} {f['title']} {f['root_cause']}".lower())
        combined_signals = "\n".join(signal_blobs)

        for brow in blocked_rows:
            check_loc = (brow["blocker_check_locus"] or "").strip().lower()
            pred = (brow["blocker_predicate"] or "").strip().lower()
            matched = False
            pred_tags = [t for t in parse_tag_list(pred) if ":" in t]
            if pred_tags and any(pt in provided_tag_set for pt in pred_tags):
                matched = True
            elif check_loc and check_loc in combined_signals:
                matched = True
            elif pred:
                pred_tokens = [t for t in re.findall(r"[a-z0-9_]{4,}", pred) if t not in {"need", "when", "until", "with", "from"}]
                if pred_tokens and all(tok in combined_signals for tok in pred_tokens[:2]):
                    matched = True
            if matched:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'open', reopened_boost = reopened_boost + 12, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (now_iso, brow["task_id"]),
                )
                reopened_tasks.append(brow["task_id"])

    rescored = recompute_all_open_salience(conn)
    result = {
        "expired_leases": expired_leases,
        "expired_hooks": expired_hooks,
        "invalidated_bindings": invalidated_bindings,
        "reopened_tasks": reopened_tasks,
        "rescored_open_tasks": rescored,
    }
    log_event(conn, "system", "pulse", "", result)
    return result


def record_repro_failure(
    conn: sqlite3.Connection,
    *,
    claim: sqlite3.Row | dict[str, Any],
    worker_id: str,
    observation_hash: str,
    reason: str,
) -> dict[str, Any]:
    """Apply the 2-fail telemetry pivot (`KVMEscape` rule) when blind PoC retries stall."""
    now_iso = utc_now_iso()
    claim_id = str(claim["claim_id"])
    prev_fails = int(claim["failed_repro_count"] or 0) + 1
    same_obs = bool(claim["last_observation_hash"] and claim["last_observation_hash"] == observation_hash)

    pivoted = prev_fails >= 2 or same_obs
    new_status = "needs_instrumentation" if pivoted else "survived_falsify"
    instrument_task_id = None

    conn.execute(
        """
        UPDATE claims
        SET failed_repro_count = ?,
            last_observation_hash = ?,
            instrumented_since_fail = CASE WHEN ? THEN 0 ELSE instrumented_since_fail END,
            status = ?,
            updated_at = ?
        WHERE claim_id = ?
        """,
        (prev_fails, observation_hash, 1 if pivoted else 0, new_status, now_iso, claim_id),
    )

    if pivoted:
        instrument_task_id = new_id("task")
        sub = str(claim["subsystem"] or infer_subsystem(str(claim["locus"])))
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, parent_claim_id, surface_id, kind, title, subsystem, locus, priority,
                status, salience_score, summary, created_at, updated_at
            ) VALUES (?, ?, ?, 'instrument', ?, ?, ?, 'critical', 'open', 85, ?, ?, ?)
            """,
            (
                instrument_task_id,
                claim_id,
                claim["surface_id"],
                f"Instrument target state for stalled reproduction of {claim_id}",
                sub,
                claim["locus"],
                scrub_text(f"2 failed PoC attempts ({reason[:120]}). Capture target trace/binding before retrying."),
                now_iso,
                now_iso,
            ),
        )
    log_event(
        conn,
        worker_id,
        "claim_repro_failed",
        claim_id,
        {
            "failed_repro_count": prev_fails,
            "pivoted_to_instrumentation": pivoted,
            "instrument_task_id": instrument_task_id,
            "reason": reason[:200],
        },
    )
    return {
        "claim_id": claim_id,
        "status": new_status,
        "failed_repro_count": prev_fails,
        "pivoted_to_instrumentation": pivoted,
        "instrument_task_id": instrument_task_id,
    }


def list_rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def upsert_threat_model(
    conn: sqlite3.Connection,
    *,
    principals: Sequence[str],
    assets: Sequence[str],
    consumer_tiers: Sequence[str] = (),
    summary: str = "",
) -> dict[str, Any]:
    """Create or update the structured Threat Model for the active run (incrementing `revision`)."""
    run = conn.execute("SELECT run_id FROM runs LIMIT 1").fetchone()
    rid = str(run["run_id"]) if run else "run"
    existing = conn.execute("SELECT * FROM threat_models WHERE run_id = ?", (rid,)).fetchone()
    now_iso = utc_now_iso()
    clean_p = [scrub_text(p.strip()) for p in principals if p and p.strip()]
    clean_a = [scrub_text(a.strip()) for a in assets if a and a.strip()]
    clean_c = [scrub_text(c.strip()) for c in consumer_tiers if c and c.strip()]
    clean_sum = scrub_text(summary.strip())
    rev = (int(existing["revision"]) + 1) if existing else 1
    conn.execute(
        """
        INSERT INTO threat_models(
            run_id, principals_json, assets_json, consumer_tiers_json, summary, revision, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            principals_json = excluded.principals_json,
            assets_json = excluded.assets_json,
            consumer_tiers_json = excluded.consumer_tiers_json,
            summary = excluded.summary,
            revision = excluded.revision,
            updated_at = excluded.updated_at
        """,
        (rid, json.dumps(clean_p), json.dumps(clean_a), json.dumps(clean_c), clean_sum, rev, now_iso),
    )
    log_event(conn, "mapper", "threat_model_upserted", rid, {"revision": rev, "principals": len(clean_p), "assets": len(clean_a)})
    return {
        "run_id": rid,
        "principals": clean_p,
        "assets": clean_a,
        "consumer_tiers": clean_c,
        "summary": clean_sum,
        "revision": rev,
        "updated_at": now_iso,
    }


def add_threat_assumption(
    conn: sqlite3.Connection,
    *,
    subsystem: str,
    assumption_text: str,
    trust_boundary: str = "",
    check_locus: str = "",
    invalidated_by_tags: Sequence[str] = (),
    dependent_surface_id: str = "",
    escalate_priority: str = "critical",
) -> dict[str, Any]:
    """Register a falsifiable architectural trust assumption linked to downstream surfaces/tasks."""
    from ajar.epistemic_hooks import parse_tag_list

    if escalate_priority not in ("critical", "high"):
        raise AjarError(f"Unsupported --escalate-priority {escalate_priority!r}", EXIT_USER_ERROR)
    aid = new_id("tma")
    now_iso = utc_now_iso()
    norm_tags = parse_tag_list(list(invalidated_by_tags))
    clean_sub = scrub_text(subsystem.strip()) or infer_subsystem(check_locus)
    clean_txt = scrub_text(assumption_text.strip())
    clean_tb = scrub_text(trust_boundary.strip())
    clean_loc = check_locus.strip()
    dep_sid = dependent_surface_id.strip()
    conn.execute(
        """
        INSERT INTO threat_assumptions(
            assumption_id, subsystem, trust_boundary, assumption_text, check_locus,
            invalidated_by_tags_json, dependent_surface_id, escalate_priority,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'assumed', ?, ?)
        """,
        (
            aid,
            clean_sub,
            clean_tb,
            clean_txt,
            clean_loc,
            json.dumps(norm_tags),
            dep_sid,
            escalate_priority,
            now_iso,
            now_iso,
        ),
    )
    log_event(conn, "mapper", "threat_assumption_added", aid, {"subsystem": clean_sub, "dependent_surface_id": dep_sid, "tags": norm_tags})
    return {
        "assumption_id": aid,
        "subsystem": clean_sub,
        "trust_boundary": clean_tb,
        "assumption_text": clean_txt,
        "check_locus": clean_loc,
        "invalidated_by_tags": norm_tags,
        "dependent_surface_id": dep_sid,
        "escalate_priority": escalate_priority,
        "status": "assumed",
    }


def transition_threat_assumption(
    conn: sqlite3.Connection,
    assumption_id: str,
    *,
    new_status: str,
    evidence_ref: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Verify (`verified_holds`) or violate (`violated`) a threat assumption.

    When an assumption transitions to `violated`, Ajar adaptively bumps `threat_models.revision`,
    upgrades `dependent_surface_id` priority, unblocks parked tasks (`+30` salience), and spawns
    an escalation task if the newly exposed surface has no open work.
    """
    if new_status not in ("verified_holds", "violated", "assumed"):
        raise AjarError(f"Invalid assumption status {new_status!r}", EXIT_USER_ERROR)
    row = conn.execute("SELECT * FROM threat_assumptions WHERE assumption_id = ?", (assumption_id,)).fetchone()
    if row is None:
        raise AjarError(f"Unknown assumption_id: {assumption_id}", EXIT_USER_ERROR)

    prev_status = str(row["status"])
    now_iso = utc_now_iso()
    clean_ev = scrub_text(evidence_ref.strip())
    clean_notes = scrub_text(notes.strip())
    conn.execute(
        """
        UPDATE threat_assumptions
        SET status = ?, evidence_ref = ?, notes = ?, updated_at = ?
        WHERE assumption_id = ?
        """,
        (new_status, clean_ev, clean_notes, now_iso, assumption_id),
    )

    unblocked_tasks = 0
    upgraded_surface = ""
    spawned_task_id = ""
    new_revision = 1

    if new_status == "violated" and prev_status != "violated":
        run = conn.execute("SELECT run_id FROM runs LIMIT 1").fetchone()
        rid = str(run["run_id"]) if run else "run"
        tm = conn.execute("SELECT revision FROM threat_models WHERE run_id = ?", (rid,)).fetchone()
        if tm is not None:
            new_revision = int(tm["revision"]) + 1
            conn.execute("UPDATE threat_models SET revision = ?, updated_at = ? WHERE run_id = ?", (new_revision, now_iso, rid))
        else:
            new_revision = 2
            conn.execute(
                "INSERT INTO threat_models(run_id, summary, revision, updated_at) VALUES (?, ?, ?, ?)",
                (rid, f"Auto-initialized on violation of {assumption_id}", new_revision, now_iso),
            )

        dep_sid = str(row["dependent_surface_id"] or "").strip()
        esc_prio = str(row["escalate_priority"] or "critical")
        prio_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        if dep_sid:
            srow = conn.execute("SELECT surface_id, priority, locus, subsystem, name FROM surfaces WHERE surface_id = ?", (dep_sid,)).fetchone()
            if srow is not None:
                if prio_rank.get(str(srow["priority"]), 1) < prio_rank.get(esc_prio, 4):
                    conn.execute("UPDATE surfaces SET priority = ? WHERE surface_id = ?", (esc_prio, dep_sid))
                    upgraded_surface = dep_sid

        chk_loc = str(row["check_locus"] or "").strip()
        cur = conn.execute(
            """
            UPDATE tasks
            SET status = 'open',
                reopened_boost = reopened_boost + 30,
                salience_score = MIN(100, salience_score + 30),
                updated_at = ?
            WHERE status = 'conditional_blocked'
              AND (
                  (? != '' AND blocker_check_locus = ?)
                  OR (? != '' AND surface_id = ?)
                  OR blocker_predicate LIKE ?
              )
            """,
            (now_iso, chk_loc, chk_loc, dep_sid, dep_sid, f"%{assumption_id}%"),
        )
        unblocked_tasks = int(cur.rowcount or 0)

        if dep_sid:
            open_on_surf = conn.execute(
                "SELECT task_id FROM tasks WHERE surface_id = ? AND status IN ('open', 'leased') LIMIT 1",
                (dep_sid,),
            ).fetchone()
            if open_on_surf is None:
                srow = conn.execute("SELECT locus, subsystem, name FROM surfaces WHERE surface_id = ?", (dep_sid,)).fetchone()
                if srow is not None:
                    spawned_task_id = new_id("task")
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            task_id, surface_id, kind, direction, title, subsystem, locus,
                            priority, status, salience_score, reopened_boost, summary, created_at, updated_at
                        ) VALUES (?, ?, 'investigate', 'outside_in', ?, ?, ?, ?, 'open', 92, 30, ?, ?, ?)
                        """,
                        (
                            spawned_task_id,
                            dep_sid,
                            f"Adaptive threat-model escalation on {srow['name']} ({assumption_id} violated)",
                            str(srow["subsystem"] or row["subsystem"] or ""),
                            str(srow["locus"] or ""),
                            esc_prio,
                            f"Trust assumption {assumption_id} ({str(row['assumption_text'])[:90]}) was violated by {clean_ev or 'new evidence'}.",
                            now_iso,
                            now_iso,
                        ),
                    )

        log_event(
            conn,
            "engine",
            "threat_assumption_violated",
            assumption_id,
            {
                "evidence_ref": clean_ev,
                "upgraded_surface": upgraded_surface,
                "unblocked_tasks": unblocked_tasks,
                "spawned_task_id": spawned_task_id,
                "threat_model_revision": new_revision,
            },
        )
    else:
        log_event(conn, "worker", "threat_assumption_updated", assumption_id, {"status": new_status, "evidence_ref": clean_ev})

    return {
        "assumption_id": assumption_id,
        "status": new_status,
        "evidence_ref": clean_ev,
        "upgraded_surface": upgraded_surface,
        "unblocked_tasks": unblocked_tasks,
        "spawned_task_id": spawned_task_id,
        "threat_model_revision": new_revision,
    }


def evaluate_adaptive_threat_assumptions(
    conn: sqlite3.Connection,
    *,
    evidence_ref: str,
    confirmed_locus: str = "",
    provided_tags: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Automatically violate matching `assumed` threat assumptions when new capabilities or findings land."""
    from ajar.epistemic_hooks import parse_tag_list

    tag_set = set(parse_tag_list(list(provided_tags)))
    loc_norm = confirmed_locus.strip()
    loc_file = loc_norm.split(":", 1)[0].strip().lstrip("./") if loc_norm else ""

    rows = conn.execute("SELECT * FROM threat_assumptions WHERE status = 'assumed'").fetchall()
    triggered: list[dict[str, Any]] = []
    for r in rows:
        inv_tags = set(parse_tag_list(r["invalidated_by_tags_json"]))
        matched_tags = sorted(tag_set & inv_tags)
        chk = str(r["check_locus"] or "").strip()
        chk_file = chk.split(":", 1)[0].strip().lstrip("./") if chk else ""
        locus_hit = bool(loc_norm and chk and (loc_norm == chk or (loc_file and loc_file == chk_file and ":" not in chk)))
        if matched_tags or locus_hit:
            why = (
                f"Auto-violated by capability tags {matched_tags}"
                if matched_tags
                else f"Auto-violated by confirmed finding at {loc_norm}"
            )
            res = transition_threat_assumption(
                conn,
                str(r["assumption_id"]),
                new_status="violated",
                evidence_ref=evidence_ref,
                notes=why,
            )
            triggered.append(res)
    return triggered
