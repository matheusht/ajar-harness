"""SQLite schema DDL and idempotent versioned migrations for Ajar (`v3.0 -> v3.3`)."""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    target_path TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    target_mode TEXT NOT NULL CHECK(target_mode IN ('source', 'binary', 'live')),
    workspace_mode TEXT NOT NULL CHECK(workspace_mode IN ('envelope', 'in_place')),
    goal TEXT NOT NULL,
    stopping_criterion TEXT NOT NULL DEFAULT 'exhaustive-high'
        CHECK(stopping_criterion IN ('exhaustive-high', 'first-verified-high', 'crown-jewel')),
    campaign_phase TEXT NOT NULL DEFAULT 'hunt'
        CHECK(campaign_phase IN ('hunt', 'remediate', 'full')),
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
        CHECK(kind IN ('map', 'investigate', 'bridge', 'falsify', 'reproduce', 'instrument', 'chain', 'patch', 'escalate')),
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
    door_id TEXT NOT NULL DEFAULT '',
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
    role TEXT NOT NULL DEFAULT 'capability'
        CHECK(role IN ('capability', 'trust_gadget')),
    trusted_invariant TEXT NOT NULL DEFAULT '',
    symbols_json TEXT NOT NULL DEFAULT '[]',
    preconditions TEXT NOT NULL,
    postconditions TEXT NOT NULL,
    guarded_by_locus TEXT NOT NULL DEFAULT '',
    guard_assumption TEXT NOT NULL DEFAULT '',
    provides_tags_json TEXT NOT NULL DEFAULT '[]',
    requires_tags_json TEXT NOT NULL DEFAULT '[]',
    helper_id TEXT NOT NULL DEFAULT '',
    micropatch_diff TEXT NOT NULL DEFAULT '',
    snapshot_id TEXT NOT NULL DEFAULT '',
    evidence_cmd TEXT NOT NULL,
    evidence_output TEXT NOT NULL DEFAULT '',
    chained INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'chained', 'dry')),
    dry_locus TEXT NOT NULL DEFAULT '',
    dry_reason TEXT NOT NULL DEFAULT '',
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
        CHECK(remediation_state IN ('unpatched', 'micropatched', 'verified_local', 'maintainer_patched')),
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
    build_cmd TEXT NOT NULL DEFAULT '',
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
    provides_tags_json TEXT NOT NULL DEFAULT '[]',
    snapshot_id TEXT NOT NULL DEFAULT '',
    realism_tier TEXT NOT NULL DEFAULT 'stepping_stone'
        CHECK(realism_tier IN ('crown_jewel', 'high_impact', 'stepping_stone')),
    realism_json TEXT NOT NULL DEFAULT '{}',
    calibration_notes TEXT NOT NULL DEFAULT '',
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
    realism_tier TEXT NOT NULL DEFAULT 'stepping_stone'
        CHECK(realism_tier IN ('crown_jewel', 'high_impact', 'stepping_stone')),
    realism_json TEXT NOT NULL DEFAULT '{}',
    jewel_id TEXT NOT NULL DEFAULT '',
    door_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crown_jewels (
    jewel_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    subsystem TEXT NOT NULL DEFAULT '',
    locus TEXT NOT NULL,
    impact_class TEXT NOT NULL DEFAULT 'rce'
        CHECK(impact_class IN ('rce', 'sandbox_escape', 'fund_drain', 'auth_bypass', 'state_takeover', 'key_exfil', 'arbitrary_write', 'mem_corrupt')),
    symbols_json TEXT NOT NULL DEFAULT '[]',
    max_interaction_steps INTEGER NOT NULL DEFAULT 1,
    require_default_config INTEGER NOT NULL DEFAULT 1,
    forbid_visible_error INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'locked'
        CHECK(status IN ('locked', 'reached', 'exhausted_unreachable')),
    reached_by_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parked_doors (
    door_id TEXT PRIMARY KEY,
    jewel_id TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'sink_to_source'
        CHECK(direction IN ('sink_to_source', 'source_to_sink', 'bidirectional')),
    anchor_locus TEXT NOT NULL,
    blocker_locus TEXT NOT NULL DEFAULT '',
    subsystem TEXT NOT NULL DEFAULT '',
    held_ids_json TEXT NOT NULL DEFAULT '[]',
    snapshot_id TEXT NOT NULL DEFAULT '',
    missing_link_summary TEXT NOT NULL,
    wanted_tags_json TEXT NOT NULL DEFAULT '[]',
    wanted_symbols_json TEXT NOT NULL DEFAULT '[]',
    wishlist_query TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'parked'
        CHECK(status IN ('parked', 'bridging', 'ready', 'chained', 'exhausted_locked')),
    matched_by_json TEXT NOT NULL DEFAULT '[]',
    bridge_attempts INTEGER NOT NULL DEFAULT 0,
    max_bridge_attempts INTEGER NOT NULL DEFAULT 2,
    resume_task_id TEXT NOT NULL DEFAULT '',
    created_by_worker TEXT NOT NULL DEFAULT 'worker',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS door_fts USING fts5(
    door_id UNINDEXED,
    anchor_locus,
    blocker_locus,
    wanted_symbols,
    missing_link_summary,
    wishlist_query
);

CREATE TABLE IF NOT EXISTS repro_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL DEFAULT '',
    rel_dir TEXT NOT NULL DEFAULT '.',
    archive_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    manifest_json TEXT NOT NULL DEFAULT '{}',
    source_cmd TEXT NOT NULL DEFAULT '',
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
    stage TEXT NOT NULL CHECK(stage IN ('investigate', 'bridge', 'falsify', 'reproduce', 'chain', 'portfolio')),
    wire_profile TEXT NOT NULL CHECK(wire_profile IN ('direct', 'swarm_patch_first', 'regression_tdd')),
    item_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'dispatched'
        CHECK(status IN ('dispatched', 'completed', 'filter_blocked', 'idle_no_return', 'refused')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_salience ON tasks(status, salience_score DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_door_id ON tasks(door_id, status);
CREATE INDEX IF NOT EXISTS idx_doors_status ON parked_doors(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_claims_locus_mech ON claims(locus, mechanism_key);
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_hooks_status_sub ON epistemic_hooks(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_cov_rel_path ON coverage_spans(rel_path, start_line, end_line);
CREATE INDEX IF NOT EXISTS idx_tm_assumptions_status ON threat_assumptions(status, subsystem);
CREATE INDEX IF NOT EXISTS idx_swarm_dispatches_stage ON swarm_dispatches(stage, status, created_at DESC);
"""


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
    conn.execute("PRAGMA legacy_alter_table=ON")
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
                    CHECK(kind IN ('map', 'investigate', 'bridge', 'falsify', 'reproduce', 'instrument', 'chain', 'patch', 'escalate')),
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
                door_id TEXT NOT NULL DEFAULT '',
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
                    CHECK(remediation_state IN ('unpatched', 'micropatched', 'verified_local', 'maintainer_patched')),
                duplicate_of_claim_id TEXT,
                env_blocker TEXT NOT NULL DEFAULT '',
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
    conn.execute("PRAGMA legacy_alter_table=OFF")


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


def _ensure_v33_schema(conn: sqlite3.Connection) -> None:
    """Idempotently migrate v3.2.x SQLite databases to include v3.3 columns, enums, and tables."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not tables:
        return

    conn.execute("PRAGMA legacy_alter_table=ON")

    # 1. Rebuild `runs` if `crown-jewel` or `campaign_phase` is absent from DDL.
    runs_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='runs'").fetchone()
    if runs_ddl and ("'crown-jewel'" not in str(runs_ddl[0] or "") or "campaign_phase" not in str(runs_ddl[0] or "")):
        rcols = [r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()]
        if "campaign_phase" not in rcols:
            conn.execute("ALTER TABLE runs ADD COLUMN campaign_phase TEXT NOT NULL DEFAULT 'hunt'")
            rcols.append("campaign_phase")
        csv_rcols = ", ".join(rcols)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE runs RENAME TO _runs_v32_old;
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                target_path TEXT NOT NULL,
                workspace_path TEXT NOT NULL,
                target_mode TEXT NOT NULL CHECK(target_mode IN ('source', 'binary', 'live')),
                workspace_mode TEXT NOT NULL CHECK(workspace_mode IN ('envelope', 'in_place')),
                goal TEXT NOT NULL,
                stopping_criterion TEXT NOT NULL DEFAULT 'exhaustive-high'
                    CHECK(stopping_criterion IN ('exhaustive-high', 'first-verified-high', 'crown-jewel')),
                campaign_phase TEXT NOT NULL DEFAULT 'hunt'
                    CHECK(campaign_phase IN ('hunt', 'remediate', 'full')),
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
            INSERT INTO runs({csv_rcols}) SELECT {csv_rcols} FROM _runs_v32_old;
            DROP TABLE _runs_v32_old;
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    # 2. Rebuild `tasks` if `'bridge'` or `door_id` is absent.
    tasks_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
    if tasks_ddl and ("'bridge'" not in str(tasks_ddl[0] or "") or "door_id" not in str(tasks_ddl[0] or "")):
        tcols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        if "door_id" not in tcols:
            conn.execute("ALTER TABLE tasks ADD COLUMN door_id TEXT NOT NULL DEFAULT ''")
            tcols.append("door_id")
        csv_tcols = ", ".join(tcols)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE tasks RENAME TO _tasks_v32_old;
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                parent_task_id TEXT,
                parent_claim_id TEXT,
                surface_id TEXT,
                kind TEXT NOT NULL
                    CHECK(kind IN ('map', 'investigate', 'bridge', 'falsify', 'reproduce', 'instrument', 'chain', 'patch', 'escalate')),
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
                door_id TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_epoch REAL
            );
            INSERT INTO tasks({csv_tcols}) SELECT {csv_tcols} FROM _tasks_v32_old;
            DROP TABLE _tasks_v32_old;
            CREATE INDEX IF NOT EXISTS idx_tasks_status_salience ON tasks(status, salience_score DESC);
            CREATE INDEX IF NOT EXISTS idx_tasks_door_id ON tasks(door_id, status);
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    # 3. Rebuild `claims` if `'verified_local'` is absent from `remediation_state`.
    claims_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='claims'").fetchone()
    if claims_ddl and "'verified_local'" not in str(claims_ddl[0] or ""):
        ccols = [r[1] for r in conn.execute("PRAGMA table_info(claims)").fetchall()]
        csv_ccols = ", ".join(ccols)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE claims RENAME TO _claims_v32_old;
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
                    CHECK(remediation_state IN ('unpatched', 'micropatched', 'verified_local', 'maintainer_patched')),
                duplicate_of_claim_id TEXT,
                env_blocker TEXT NOT NULL DEFAULT '',
                blocker_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO claims({csv_ccols}) SELECT {csv_ccols} FROM _claims_v32_old;
            DROP TABLE _claims_v32_old;
            CREATE INDEX IF NOT EXISTS idx_claims_locus_mech ON claims(locus, mechanism_key);
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    # 4. Rebuild `swarm_dispatches` if `'bridge'` or `'portfolio'` is absent.
    sd_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='swarm_dispatches'").fetchone()
    if sd_ddl and "'portfolio'" not in str(sd_ddl[0] or ""):
        scols = [r[1] for r in conn.execute("PRAGMA table_info(swarm_dispatches)").fetchall()]
        csv_scols = ", ".join(scols)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE swarm_dispatches RENAME TO _sd_v32_old;
            CREATE TABLE swarm_dispatches (
                dispatch_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                stage TEXT NOT NULL CHECK(stage IN ('investigate', 'bridge', 'falsify', 'reproduce', 'chain', 'portfolio')),
                wire_profile TEXT NOT NULL CHECK(wire_profile IN ('direct', 'swarm_patch_first', 'regression_tdd')),
                item_ids_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'dispatched'
                    CHECK(status IN ('dispatched', 'completed', 'filter_blocked', 'idle_no_return', 'refused')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO swarm_dispatches({csv_scols}) SELECT {csv_scols} FROM _sd_v32_old;
            DROP TABLE _sd_v32_old;
            CREATE INDEX IF NOT EXISTS idx_swarm_dispatches_stage ON swarm_dispatches(stage, status, created_at DESC);
            COMMIT;
            """
        )
        conn.execute("PRAGMA foreign_keys=ON")

    # 5. Additive columns on `primitives`, `findings`, and `chains`.
    if "primitives" in tables:
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(primitives)").fetchall()}
        for cname, cdef in (
            ("role", "TEXT NOT NULL DEFAULT 'capability'"),
            ("trusted_invariant", "TEXT NOT NULL DEFAULT ''"),
            ("symbols_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("micropatch_diff", "TEXT NOT NULL DEFAULT ''"),
            ("snapshot_id", "TEXT NOT NULL DEFAULT ''"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("dry_locus", "TEXT NOT NULL DEFAULT ''"),
            ("dry_reason", "TEXT NOT NULL DEFAULT ''"),
        ):
            if cname not in pcols:
                conn.execute(f"ALTER TABLE primitives ADD COLUMN {cname} {cdef}")
        conn.execute("UPDATE primitives SET status = 'chained' WHERE chained = 1 AND status = 'active'")

    if "findings" in tables:
        fcols = {r[1] for r in conn.execute("PRAGMA table_info(findings)").fetchall()}
        for cname, cdef in (
            ("build_cmd", "TEXT NOT NULL DEFAULT ''"),
            ("provides_tags_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("snapshot_id", "TEXT NOT NULL DEFAULT ''"),
            ("realism_tier", "TEXT NOT NULL DEFAULT 'stepping_stone'"),
            ("realism_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("calibration_notes", "TEXT NOT NULL DEFAULT ''"),
        ):
            if cname not in fcols:
                conn.execute(f"ALTER TABLE findings ADD COLUMN {cname} {cdef}")

    if "chains" in tables:
        chcols = {r[1] for r in conn.execute("PRAGMA table_info(chains)").fetchall()}
        for cname, cdef in (
            ("realism_tier", "TEXT NOT NULL DEFAULT 'stepping_stone'"),
            ("realism_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("jewel_id", "TEXT NOT NULL DEFAULT ''"),
            ("door_id", "TEXT NOT NULL DEFAULT ''"),
        ):
            if cname not in chcols:
                conn.execute(f"ALTER TABLE chains ADD COLUMN {cname} {cdef}")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS crown_jewels (
            jewel_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            subsystem TEXT NOT NULL DEFAULT '',
            locus TEXT NOT NULL,
            impact_class TEXT NOT NULL DEFAULT 'rce'
                CHECK(impact_class IN ('rce', 'sandbox_escape', 'fund_drain', 'auth_bypass', 'state_takeover', 'key_exfil', 'arbitrary_write', 'mem_corrupt')),
            symbols_json TEXT NOT NULL DEFAULT '[]',
            max_interaction_steps INTEGER NOT NULL DEFAULT 1,
            require_default_config INTEGER NOT NULL DEFAULT 1,
            forbid_visible_error INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'locked'
                CHECK(status IN ('locked', 'reached', 'exhausted_unreachable')),
            reached_by_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS parked_doors (
            door_id TEXT PRIMARY KEY,
            jewel_id TEXT NOT NULL DEFAULT '',
            direction TEXT NOT NULL DEFAULT 'sink_to_source'
                CHECK(direction IN ('sink_to_source', 'source_to_sink', 'bidirectional')),
            anchor_locus TEXT NOT NULL,
            blocker_locus TEXT NOT NULL DEFAULT '',
            subsystem TEXT NOT NULL DEFAULT '',
            held_ids_json TEXT NOT NULL DEFAULT '[]',
            snapshot_id TEXT NOT NULL DEFAULT '',
            missing_link_summary TEXT NOT NULL,
            wanted_tags_json TEXT NOT NULL DEFAULT '[]',
            wanted_symbols_json TEXT NOT NULL DEFAULT '[]',
            wishlist_query TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'parked'
                CHECK(status IN ('parked', 'bridging', 'ready', 'chained', 'exhausted_locked')),
            matched_by_json TEXT NOT NULL DEFAULT '[]',
            bridge_attempts INTEGER NOT NULL DEFAULT 0,
            max_bridge_attempts INTEGER NOT NULL DEFAULT 2,
            resume_task_id TEXT NOT NULL DEFAULT '',
            created_by_worker TEXT NOT NULL DEFAULT 'worker',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS door_fts USING fts5(
            door_id UNINDEXED,
            anchor_locus,
            blocker_locus,
            wanted_symbols,
            missing_link_summary,
            wishlist_query
        );

        CREATE TABLE IF NOT EXISTS repro_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL DEFAULT '',
            rel_dir TEXT NOT NULL DEFAULT '.',
            archive_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            manifest_json TEXT NOT NULL DEFAULT '{}',
            source_cmd TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_door_id ON tasks(door_id, status);
        CREATE INDEX IF NOT EXISTS idx_doors_status ON parked_doors(status, subsystem);
        """
    )
    conn.execute("PRAGMA legacy_alter_table=OFF")
