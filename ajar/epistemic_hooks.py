"""Event-driven epistemic micro-hooks and cross-subsystem capability bridges (`Ajar v3.2`).

Implements "Hooks, Not Prisons":
- Zero prompt overhead (`0` tokens) on plain code when no signal fires.
- Evaluates deterministic SQLite state transitions and lightweight AST/source signals
  (`H1`..`H8`), capping injected guidance at `<= 2` active hooks per task.
- Pairs every triggered hook with a mandatory 1-line `DRY` Kill Rule so workers close
  clean near-misses fast without speculative chain bias.
- Matches typed `provides_tags` and `requires_tags` across subsystems to surface
  upstream providers and spawn Stage-5 `chain` tasks deterministically.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import sqlite3
from typing import Any, Sequence

from ajar.domain.enums import HookCode
from ajar.redact import scrub_text

HOOK_CODES: tuple[str, ...] = tuple(h.value for h in HookCode)

COMPILED_UB_EXTENSIONS: frozenset[str] = frozenset(
    {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".rs", ".zig"}
)

UB_MECHANISM_RE = re.compile(
    r"\b(?:overflow|underflow|wrap(?:around|ped|s)?|truncat(?:e|ion)|shift|signed|"
    r"int(?:8|16|32|64)_t|uint(?:8|16|32|64)_t|usize|isize|unsafe|assert|debug_assert|"
    r"ubsan|ftrapv)\b",
    re.IGNORECASE,
)

UNWIND_SIGNAL_RE = re.compile(
    r"\b(?:recover\s*\(|longjmp|siglongjmp|zend_bailout|catch\s*\(\s*(?:Throwable|Error|Exception)|"
    r"deferred_batches|pending_credit|partial_rollback|worker_loop)\b",
    re.IGNORECASE,
)

FFI_OR_CLIENT_SINK_RE = re.compile(
    r"(?:@IntrinsicCandidate|\bextern\s+\"C\"|\bunsafe\s*\{|\bcgo\b|\bctypes\b|"
    r"\b(?:urllib\.request|httpx|requests|fetch|http\.Client)\b.*\b(?:json\.loads|pickle|yaml\.load|unmarshal|deserialize)\b)",
    re.IGNORECASE,
)

PREAUTH_OR_FSM_RE = re.compile(
    r"\b(?:x-forwarded-(?:for|host|user)|x-internal-scope|x-original-url|"
    r"unverified_header|get_unverified_header|jwt\.decode\([^)]*verify\s*=\s*False|"
    r"SSH_MSG_|pre_auth|skip_auth)\b",
    re.IGNORECASE,
)

CACHE_KEY_SIGNAL_RE = re.compile(
    r"\b(?:cache_key|_memo|_verified_entries|attestation_cache|is_ref_attested)\b",
    re.IGNORECASE,
)

CANONICALIZER_SIGNAL_RE = re.compile(
    r"(?:unquote|decodeURIComponent|pct_decode|split\s*\(\s*['\"][;@]['\"]|"
    r"lstrip\s*\(|removeprefix\s*\(|startswith\s*\()",
)


def parse_tag_list(raw: str | Sequence[str] | None) -> list[str]:
    """Normalize comma-separated or sequence tag inputs into sorted unique `ns:name` strings."""
    if raw is None:
        return []
    items: list[str] = []
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    items = [str(x) for x in parsed]
                else:
                    items = [s]
            except json.JSONDecodeError:
                items = s.split(",")
        else:
            items = s.split(",")
    else:
        for entry in raw:
            items.extend(str(entry).split(","))

    cleaned: set[str] = set()
    for item in items:
        tok = re.sub(r"[^A-Za-z0-9_:./-]+", "", item.strip().lower())
        if tok:
            cleaned.add(tok[:64])
    return sorted(cleaned)


def _dedup_hash(hook_code: str, key_material: str) -> str:
    digest = hashlib.sha256(f"{hook_code}:{key_material}".encode("utf-8")).hexdigest()
    return digest[:16]


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def register_epistemic_hook(
    conn: sqlite3.Connection,
    *,
    hook_code: str,
    trigger_cmd: str,
    source_entity_id: str,
    dedup_material: str,
    subsystem: str,
    target_locus: str,
    directive_text: str,
    kill_rule: str,
    spawned_task_id: str | None = None,
    max_leases: int = 2,
) -> dict[str, Any]:
    """Idempotently register or refresh an epistemic micro-hook in `run.db`."""
    from ajar.db import new_id, utc_now_iso

    if hook_code not in HOOK_CODES:
        raise ValueError(f"Unsupported hook_code: {hook_code!r}")

    dedup_key = _dedup_hash(hook_code, dedup_material)
    existing = conn.execute(
        "SELECT * FROM epistemic_hooks WHERE dedup_key = ?",
        (dedup_key,),
    ).fetchone()
    if existing is not None:
        return {**dict(existing), "created": False}

    hid = new_id("hok")
    now_iso = utc_now_iso()
    clean_dir = scrub_text(directive_text.strip())[:180]
    clean_kill = scrub_text(kill_rule.strip())[:180]
    tok_est = min(45, _estimate_tokens(clean_dir))

    conn.execute(
        """
        INSERT INTO epistemic_hooks(
            hook_id, hook_code, trigger_cmd, source_entity_id, dedup_key,
            subsystem, target_locus, spawned_task_id, directive_text, kill_rule,
            token_estimate, max_leases, leases_seen, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?)
        """,
        (
            hid,
            hook_code,
            trigger_cmd,
            source_entity_id,
            dedup_key,
            subsystem,
            target_locus,
            spawned_task_id,
            clean_dir,
            clean_kill,
            tok_est,
            max(1, int(max_leases)),
            now_iso,
            now_iso,
        ),
    )
    return {
        "hook_id": hid,
        "hook_code": hook_code,
        "dedup_key": dedup_key,
        "subsystem": subsystem,
        "target_locus": target_locus,
        "spawned_task_id": spawned_task_id,
        "directive_text": clean_dir,
        "kill_rule": clean_kill,
        "token_estimate": tok_est,
        "status": "active",
        "created": True,
    }


def consume_hooks_for_locus(
    conn: sqlite3.Connection,
    *,
    locus: str = "",
    source_entity_id: str = "",
    hook_code: str = "",
) -> int:
    """Mark matching active hooks `consumed` once their target guard/claim resolves."""
    from ajar.db import utc_now_iso

    now_iso = utc_now_iso()
    clauses: list[str] = ["status = 'active'"]
    params: list[Any] = [now_iso]
    if hook_code:
        clauses.append("hook_code = ?")
        params.append(hook_code)
    if locus and source_entity_id:
        clauses.append("(target_locus = ? OR source_entity_id = ?)")
        params.extend([locus, source_entity_id])
    elif locus:
        clauses.append("target_locus = ?")
        params.append(locus)
    elif source_entity_id:
        clauses.append("source_entity_id = ?")
        params.append(source_entity_id)
    else:
        return 0

    sql = f"UPDATE epistemic_hooks SET status = 'consumed', updated_at = ? WHERE {' AND '.join(clauses)}"
    cur = conn.execute(sql, tuple(params))
    return int(cur.rowcount or 0)


def expire_stale_hooks(conn: sqlite3.Connection) -> int:
    """Auto-expire hooks that have been leased `>= max_leases` times once no leased task holds them."""
    from ajar.db import utc_now_iso

    cur = conn.execute(
        """
        UPDATE epistemic_hooks
        SET status = 'expired', updated_at = ?
        WHERE status = 'active'
          AND leases_seen >= max_leases
          AND (
              spawned_task_id IS NULL OR spawned_task_id = ''
              OR NOT EXISTS (
                  SELECT 1 FROM tasks t
                  WHERE t.task_id = epistemic_hooks.spawned_task_id AND t.status = 'leased'
              )
          )
        """,
        (utc_now_iso(),),
    )
    return int(cur.rowcount or 0)


def record_hook_lease_exposure(conn: sqlite3.Connection, hook_ids: Sequence[str]) -> None:
    """Increment `leases_seen` once per task lease when a worker leases context carrying active hooks."""
    from ajar.db import utc_now_iso

    if not hook_ids:
        return
    now_iso = utc_now_iso()
    for hid in hook_ids:
        conn.execute(
            """
            UPDATE epistemic_hooks
            SET leases_seen = leases_seen + 1,
                updated_at = ?
            WHERE hook_id = ? AND status = 'active'
            """,
            (now_iso, hid),
        )


def select_active_hooks_for_task(
    conn: sqlite3.Connection,
    task: sqlite3.Row | dict[str, Any],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Select at most `limit` active hooks matching `task` (0 rows on plain clean code)."""
    from ajar.db import infer_subsystem

    tid = str(task["task_id"])
    loc = str(task["locus"] or "")
    sub = str(task["subsystem"] or infer_subsystem(loc))
    parent_clm = str(task["parent_claim_id"] or "") if "parent_claim_id" in task.keys() else ""

    rows = conn.execute(
        """
        SELECT * FROM epistemic_hooks
        WHERE status = 'active'
          AND (leases_seen < max_leases OR spawned_task_id = ?)
          AND (
              spawned_task_id = ?
              OR (? != '' AND target_locus = ?)
              OR (? != '' AND source_entity_id = ?)
              OR (? != '' AND subsystem = ?)
          )
        ORDER BY
            CASE
                WHEN spawned_task_id = ? THEN 0
                WHEN (? != '' AND target_locus = ?) THEN 1
                WHEN (? != '' AND source_entity_id = ?) THEN 2
                ELSE 3
            END ASC,
            created_at DESC
        LIMIT ?
        """,
        (tid, tid, loc, loc, parent_clm, parent_clm, sub, sub, tid, loc, loc, parent_clm, parent_clm, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def detect_capability_bridges(
    conn: sqlite3.Connection,
    *,
    subsystem: str = "",
    locus: str = "",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Meet-in-the-Middle cross-subsystem capability bridge (`provides_tags <-> requires_tags`).

    Resolves cross-subsystem blindness (`WHERE subsystem = ?`) by joining upstream
    primitives/helpers across ALL subsystems whose `provides_tags_json` intersect
    `requires_tags_json` on sinks/surfaces in `subsystem`, or whose `guarded_by_locus`
    targets `locus`/`subsystem`.
    """
    from ajar.db import infer_subsystem

    all_prims = conn.execute(
        """
        SELECT p.*, ph.module_name AS helper_module, ph.callable_name AS helper_callable
        FROM primitives p
        LEFT JOIN primitive_helpers ph ON p.helper_id = ph.helper_id
        WHERE p.status != 'dry'
        ORDER BY p.created_at ASC
        """
    ).fetchall()
    all_findings = conn.execute("SELECT * FROM findings ORDER BY created_at ASC").fetchall()
    surfaces = conn.execute("SELECT * FROM surfaces ORDER BY created_at ASC").fetchall()

    providers_by_tag: dict[str, list[dict[str, Any]]] = {}
    for p in all_prims:
        p_dict = dict(p)
        for tag in parse_tag_list(p_dict.get("provides_tags_json", "[]")):
            providers_by_tag.setdefault(tag, []).append(p_dict)
    for f in all_findings:
        f_dict = dict(f)
        ftags = parse_tag_list(f_dict.get("provides_tags_json", "[]"))
        if ftags:
            prov_entry = {
                "primitive_id": str(f_dict["finding_id"]),
                "locus": str(f_dict["locus"]),
                "subsystem": infer_subsystem(str(f_dict["locus"])),
                "kind": "finding",
                "helper_module": "",
                "helper_callable": "",
            }
            for tag in ftags:
                providers_by_tag.setdefault(tag, []).append(prov_entry)

    bridges: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    # 1. Match sinks (`primitives` or `surfaces`) requiring tags against cross-subsystem providers.
    sink_candidates: list[dict[str, Any]] = []
    for p in all_prims:
        req = parse_tag_list(p["requires_tags_json"] if "requires_tags_json" in p.keys() else "[]")
        if req:
            sink_candidates.append(
                {
                    "sink_id": str(p["primitive_id"]),
                    "sink_kind": "primitive",
                    "subsystem": str(p["subsystem"] or ""),
                    "locus": str(p["locus"] or ""),
                    "requires_tags": req,
                }
            )
    for s in surfaces:
        req = parse_tag_list(s["requires_tags_json"] if "requires_tags_json" in s.keys() else "[]")
        if req:
            sink_candidates.append(
                {
                    "sink_id": str(s["surface_id"]),
                    "sink_kind": "surface",
                    "subsystem": str(s["subsystem"] or ""),
                    "locus": str(s["locus"] or ""),
                    "requires_tags": req,
                }
            )

    for sink in sink_candidates:
        if subsystem and sink["subsystem"] != subsystem and (not locus or sink["locus"] != locus):
            continue
        matched_tags: list[str] = []
        missing_tags: list[str] = []
        matched_providers: list[dict[str, Any]] = []
        for rtag in sink["requires_tags"]:
            provs = providers_by_tag.get(rtag, [])
            if provs:
                matched_tags.append(rtag)
                for pv in provs:
                    if pv["primitive_id"] != sink["sink_id"] and pv not in matched_providers:
                        matched_providers.append(pv)
            else:
                missing_tags.append(rtag)

        if matched_providers or missing_tags:
            bkey = f"{sink['sink_id']}:{','.join(matched_tags)}:{','.join(missing_tags)}"
            if bkey not in seen_keys:
                seen_keys.add(bkey)
                bridges.append(
                    {
                        "bridge_type": "complete_bridge" if not missing_tags else "partial_bridge_gap",
                        "sink_id": sink["sink_id"],
                        "sink_locus": sink["locus"],
                        "sink_subsystem": sink["subsystem"],
                        "matched_tags": matched_tags,
                        "missing_tags": missing_tags,
                        "providers": [
                            {
                                "primitive_id": pv["primitive_id"],
                                "locus": pv["locus"],
                                "subsystem": pv["subsystem"],
                                "kind": pv["kind"],
                                "helper": (
                                    f"ajar_helpers.{pv['helper_module']}.{pv['helper_callable']}"
                                    if pv.get("helper_module")
                                    else ""
                                ),
                            }
                            for pv in matched_providers[:3]
                        ],
                    }
                )

    # 2. Match cross-subsystem guarded primitives whose `guarded_by_locus` points INTO `subsystem`/`locus`.
    loc_file = locus.split(":", 1)[0].strip().lstrip("./") if locus else ""
    for p in all_prims:
        gloc = str(p["guarded_by_locus"] or "").strip()
        if not gloc or int(p["chained"] or 0) == 1:
            continue
        g_file = gloc.split(":", 1)[0].strip().lstrip("./")
        in_scope = False
        if locus and (gloc == locus or (loc_file and g_file == loc_file)):
            in_scope = True
        elif subsystem and (g_file == subsystem or g_file.startswith(subsystem + "/")):
            in_scope = True
        if in_scope and str(p["subsystem"] or "") != subsystem:
            bkey = f"guard_ref:{p['primitive_id']}:{gloc}"
            if bkey not in seen_keys:
                seen_keys.add(bkey)
                bridges.append(
                    {
                        "bridge_type": "guarded_sink_upstream_audit",
                        "sink_id": str(p["primitive_id"]),
                        "sink_locus": str(p["locus"]),
                        "sink_subsystem": str(p["subsystem"]),
                        "guard_locus": gloc,
                        "matched_tags": parse_tag_list(p["provides_tags_json"] if "provides_tags_json" in p.keys() else "[]"),
                        "missing_tags": [],
                        "providers": [],
                    }
                )

    return bridges[: max(1, int(limit))]


def _detect_python_dirty_unwind(text: str) -> bool:
    """AST detector: state attribute/subscript mutation before `raise`, or selective `except` without rollback."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    saw_mut_before_raise = False
    saw_selective_except = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            saw_attr_mut = False
            for stmt in ast.walk(node):
                if isinstance(stmt, (ast.AugAssign, ast.Assign)):
                    targets = [stmt.target] if isinstance(stmt, ast.AugAssign) else list(stmt.targets)
                    if any(isinstance(t, (ast.Attribute, ast.Subscript)) for t in targets):
                        saw_attr_mut = True
                elif isinstance(stmt, ast.Raise) and saw_attr_mut:
                    saw_mut_before_raise = True
        elif isinstance(node, ast.ExceptHandler):
            if node.type is not None:
                saw_selective_except = True
    return saw_mut_before_raise and saw_selective_except


def scan_source_for_epistemic_signals(rel_path: str, text: str) -> list[tuple[str, str, str]]:
    """Scan a single target source file for deterministic hook signals (`0` hits on plain CRUD code).

    Returns list of `(hook_code, directive_text, kill_rule)`.
    """
    hits: list[tuple[str, str, str]] = []
    if not text.strip():
        return hits

    if UNWIND_SIGNAL_RE.search(text) or (rel_path.endswith(".py") and _detect_python_dirty_unwind(text)):
        hits.append(
            (
                "H2_DIRTY_UNWIND",
                f"Test request N+1 on same worker/store after fault N in {rel_path}; check unrolled credits, nonces, or pooled buffers.",
                "STOP and mark dry if mutated state is a request-local draft discarded on exception or recomputed from immutable storage.",
            )
        )

    if FFI_OR_CLIENT_SINK_RE.search(text):
        hits.append(
            (
                "H3_INTRINSIC_AND_PEER_SINK",
                f"Diff intrinsic/FFI fast-path bounds against fallback in {rel_path} and treat outbound HTTP/RPC responses as untrusted.",
                "STOP and mark dry if exact length/schema validation executes inline prior to buffer write or deserialization.",
            )
        )

    if PREAUTH_OR_FSM_RE.search(text) or len(CANONICALIZER_SIGNAL_RE.findall(text)) >= 3:
        hits.append(
            (
                "H7_TRUST_METADATA_AND_FSM_ORDER",
                f"Check pre-auth header/metadata routing and `%`/`;`/`@` normalization order vs prefix/auth checks in {rel_path}.",
                "STOP and mark dry if terminal handler enforces a flat allowlist and binds identity from an immutable verified session.",
            )
        )

    if CACHE_KEY_SIGNAL_RE.search(text):
        hits.append(
            (
                "H8_PROJECTION_UNDER_CONSTRAINT",
                f"Verify cache/attestation key tuple in {rel_path} includes tenant, mode/overlay, and resolved digest.",
                "STOP and mark dry if the cache serves non-binding UI previews only and commit re-verifies authoritative storage.",
            )
        )

    return hits


def on_primitive_added(
    conn: sqlite3.Connection,
    *,
    primitive_id: str,
    subsystem: str,
    locus: str,
    kind: str,
    guarded_by_locus: str = "",
    provides_tags: Sequence[str] = (),
    requires_tags: Sequence[str] = (),
    role: str = "capability",
    trusted_invariant: str = "",
    symbols: Sequence[str] = (),
    snapshot_id: str = "",
    postconditions: str = "",
    spawn_guard_task: bool = True,
) -> list[dict[str, Any]]:
    """Evaluate `H1`, `H4`, Open-Door wakeup, and Adaptive Threat-Model assumptions when a primitive is recorded."""
    from ajar.chain_planner import wake_matching_doors_for_artifact
    from ajar.db import (
        compute_task_salience,
        evaluate_adaptive_threat_assumptions,
        infer_subsystem,
        new_id,
        utc_now_iso,
    )

    fired: list[dict[str, Any]] = []
    now_iso = utc_now_iso()
    if provides_tags:
        evaluate_adaptive_threat_assumptions(
            conn,
            evidence_ref=primitive_id,
            provided_tags=provides_tags,
        )

    # H1: Guarded inner primitive -> register guard-symmetry hook and optional inside-out guard task.
    gloc = guarded_by_locus.strip()
    if gloc:
        spawned_tid: str | None = None
        if spawn_guard_task:
            existing_guard_task = conn.execute(
                """
                SELECT task_id FROM tasks
                WHERE locus = ? AND kind IN ('investigate', 'chain')
                  AND status IN ('open', 'leased', 'done', 'dry')
                LIMIT 1
                """,
                (gloc,),
            ).fetchone()
            if existing_guard_task is None:
                gsub = infer_subsystem(gloc)
                draft = {"priority": "high", "subsystem": gsub, "locus": gloc, "reopened_boost": 8}
                sal = max(82, compute_task_salience(conn, draft))
                spawned_tid = new_id("task")
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, direction, title, subsystem, locus,
                        priority, status, salience_score, summary, created_at, updated_at
                    ) VALUES (?, 'investigate', 'inside_out', ?, ?, ?, 'high', 'open', ?, ?, ?, ?)
                    """,
                    (
                        spawn_guard_task and spawned_tid or "",
                        f"Audit upstream guard {gloc} blocking {primitive_id} ({kind})",
                        gsub,
                        gloc,
                        sal,
                        f"Auto-enqueued by H1_GUARD_SYMMETRY for {primitive_id} @ {locus}.",
                        now_iso,
                        now_iso,
                    ),
                )
        gsub = infer_subsystem(gloc)
        h1 = register_epistemic_hook(
            conn,
            hook_code="H1_GUARD_SYMMETRY",
            trigger_cmd="primitive.add",
            source_entity_id=primitive_id,
            dedup_material=f"{gloc}:{locus}",
            subsystem=gsub,
            target_locus=gloc,
            spawned_task_id=spawned_tid,
            directive_text=(
                f"Audit guard {gloc} in isolation: check shared bit-width, mask/modulus, "
                f"normalization, or fail-open branch with {primitive_id}@{locus}."
            ),
            kill_rule=(
                f"STOP and mark dry if {gloc} enforces widening/checked bounds on immutable "
                "server state with zero shared truncation."
            ),
        )
        fired.append(h1)

    # H4: Typed state bridge across subsystems (`provides_tags <-> requires_tags`).
    if provides_tags or requires_tags:
        bridges = detect_capability_bridges(conn, limit=8)
        for br in bridges:
            if br["bridge_type"] != "complete_bridge" or not br["providers"]:
                continue
            prov0 = br["providers"][0]
            if prov0["primitive_id"] != primitive_id and br["sink_id"] != primitive_id:
                continue
            tags_s = ",".join(br["matched_tags"][:3])
            existing_chain = conn.execute(
                """
                SELECT task_id FROM tasks
                WHERE kind = 'chain' AND status IN ('open', 'leased')
                  AND summary LIKE ?
                LIMIT 1
                """,
                (f"%{br['sink_id']}%",),
            ).fetchone()
            chain_tid: str | None = None
            if existing_chain is None:
                chain_tid = new_id("task")
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, direction, title, subsystem, locus,
                        priority, status, salience_score, summary, created_at, updated_at
                    ) VALUES (?, 'chain', 'outside_in', ?, ?, ?, 'high', 'open', 86, ?, ?, ?)
                    """,
                    (
                        chain_tid,
                        f"Bridge {prov0['primitive_id']} -> {br['sink_id']} via [{tags_s}]",
                        br["sink_subsystem"],
                        br["sink_locus"],
                        f"Cross-subsystem bridge: {prov0['primitive_id']}@{prov0['locus']} provides [{tags_s}] required by {br['sink_id']}@{br['sink_locus']}.",
                        now_iso,
                        now_iso,
                    ),
                )
            h4 = register_epistemic_hook(
                conn,
                hook_code="H4_TYPED_STATE_BRIDGE",
                trigger_cmd="primitive.add",
                source_entity_id=primitive_id,
                dedup_material=f"{prov0['primitive_id']}->{br['sink_id']}:{tags_s}",
                subsystem=br["sink_subsystem"],
                target_locus=br["sink_locus"],
                spawned_task_id=chain_tid,
                directive_text=(
                    f"Bridge {prov0['primitive_id']}@{prov0['locus']} provides [{tags_s}] "
                    f"required by {br['sink_id']}@{br['sink_locus']}; prove end-to-end via ajar chain propose."
                ),
                kill_rule=(
                    f"STOP and mark dry if {br['sink_locus']} re-verifies principal and digest "
                    f"inline from authoritative state independent of [{tags_s}]."
                ),
            )
            fired.append(h4)

    wake_matching_doors_for_artifact(
        conn,
        artifact_id=primitive_id,
        artifact_kind=role or "capability",
        locus=locus,
        subsystem=subsystem,
        text_blob=f"{kind} {postconditions} {trusted_invariant}",
        provides_tags=provides_tags,
        symbols=symbols,
        snapshot_id=snapshot_id,
        trigger_cmd="primitive.add",
    )
    return fired


def on_anomaly_or_claim_recorded(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    trigger_cmd: str,
    subsystem: str,
    locus: str,
    text_blob: str,
    target_dir: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate `H2`, `H7`, `H8`, and Open-Door wakeup on new anomalies/claims or their target source file."""
    from ajar.chain_planner import wake_matching_doors_for_artifact

    fired: list[dict[str, Any]] = []
    combined = text_blob
    rel_file = locus.split(":", 1)[0].strip().lstrip("./")
    if target_dir is not None and rel_file:
        candidate = (target_dir / rel_file).resolve()
        try:
            candidate.relative_to(target_dir.resolve())
            if candidate.is_file():
                src_text = candidate.read_text(encoding="utf-8", errors="ignore")
                for hcode, directive, kill_r in scan_source_for_epistemic_signals(rel_file, src_text):
                    fired.append(
                        register_epistemic_hook(
                            conn,
                            hook_code=hcode,
                            trigger_cmd=trigger_cmd,
                            source_entity_id=entity_id,
                            dedup_material=f"{rel_file}:{hcode}",
                            subsystem=subsystem,
                            target_locus=locus,
                            directive_text=directive,
                            kill_rule=kill_r,
                        )
                    )
        except ValueError:
            pass

    if UNWIND_SIGNAL_RE.search(combined):
        fired.append(
            register_epistemic_hook(
                conn,
                hook_code="H2_DIRTY_UNWIND",
                trigger_cmd=trigger_cmd,
                source_entity_id=entity_id,
                dedup_material=locus,
                subsystem=subsystem,
                target_locus=locus,
                directive_text=(
                    f"Send benign request N+1 on same worker/store after fault N at {locus}; "
                    "check unreset globals, pending credits, or locks."
                ),
                kill_rule="STOP and mark dry if fault N aborts isolated process state or rolls back atomically.",
            )
        )

    if entity_id.startswith("anom-"):
        wake_matching_doors_for_artifact(
            conn,
            artifact_id=entity_id,
            artifact_kind="anomaly",
            locus=locus,
            subsystem=subsystem,
            text_blob=text_blob,
            trigger_cmd=trigger_cmd,
        )
    return fired


def claim_requires_release_ub_diff(locus: str, mechanism: str) -> bool:
    """Return True if `H6_RELEASE_UB_DIFF` applies (`C/C++/Rust/Zig` + UB/overflow/assert mechanism)."""
    rel_file = locus.split(":", 1)[0].strip()
    ext = pathlib.PurePosixPath(rel_file).suffix.lower()
    if ext in COMPILED_UB_EXTENSIONS and UB_MECHANISM_RE.search(mechanism):
        return True
    return False


def on_claim_survived(
    conn: sqlite3.Connection,
    *,
    claim_row: sqlite3.Row | dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate `H6_RELEASE_UB_DIFF` when a claim passes independent `survive`."""
    fired: list[dict[str, Any]] = []
    cid = str(claim_row["claim_id"])
    loc = str(claim_row["locus"] or "")
    sub = str(claim_row["subsystem"] or "")
    mech = f"{claim_row['title']} {claim_row['mechanism']}"
    if claim_requires_release_ub_diff(loc, mech):
        fired.append(
            register_epistemic_hook(
                conn,
                hook_code="H6_RELEASE_UB_DIFF",
                trigger_cmd="claim.survive",
                source_entity_id=cid,
                dedup_material=cid,
                subsystem=sub,
                target_locus=loc,
                max_leases=2,
                directive_text=(
                    f"Supply --release-cmd (-O2 / --release without debug asserts or trapv) "
                    f"when reproducing {cid} at {loc} to classify production UB."
                ),
                kill_rule=(
                    "STOP and rescope severity if --release-cmd exits 0 with intact post-state "
                    "invariants (debug_assert_only)."
                ),
            )
        )
    return fired


def on_claim_config_gated(
    conn: sqlite3.Connection,
    *,
    claim_row: sqlite3.Row | dict[str, Any],
    config_predicate: str,
) -> dict[str, Any]:
    """Park a default-off sink as `config_gated` (`NGINX2Root` pattern) and spawn 1 override probe."""
    from ajar.db import new_id, utc_now_iso

    cid = str(claim_row["claim_id"])
    loc = str(claim_row["locus"] or "")
    sub = str(claim_row["subsystem"] or "")
    now_iso = utc_now_iso()
    pred = scrub_text(config_predicate.strip())[:160]

    probe_tid = new_id("task")
    conn.execute(
        """
        INSERT INTO tasks(
            task_id, surface_id, parent_claim_id, kind, direction, title, subsystem, locus,
            priority, status, salience_score, summary, created_at, updated_at
        ) VALUES (?, ?, ?, 'investigate', 'inside_out', ?, ?, ?, 'medium', 'open', 68, ?, ?, ?)
        """,
        (
            probe_tid,
            claim_row["surface_id"],
            cid,
            f"Probe runtime config/header enablement for {cid} ({pred[:60]})",
            sub,
            loc,
            f"Single-pass probe (`max_leases=1`) checking whether {pred} is reachable via tenant config, ingress templates, or sibling routes.",
            now_iso,
            now_iso,
        ),
    )
    hook = register_epistemic_hook(
        conn,
        hook_code="H3_INTRINSIC_AND_PEER_SINK",
        trigger_cmd="claim.falsify.config_gate",
        source_entity_id=cid,
        dedup_material=f"{loc}:{pred}",
        subsystem=sub,
        target_locus=loc,
        spawned_task_id=probe_tid,
        max_leases=1,
        directive_text=f"Check if runtime config, tenant prefs, or container defaults enable `{pred}` for {cid}@{loc}.",
        kill_rule=f"STOP and mark dry if `{pred}` is compile-time disabled or restricted to trusted root operators.",
    )
    return {"probe_task_id": probe_tid, "hook": hook}


def on_finding_confirmed(
    conn: sqlite3.Connection,
    *,
    finding_id: str,
    claim_row: sqlite3.Row | dict[str, Any],
    provides_tags: Sequence[str] = (),
    snapshot_id: str = "",
    realism_tier: str = "stepping_stone",
) -> dict[str, Any] | None:
    """Evaluate Open-Door wakeup, Adaptive Threat-Model assumptions, and `H5_POST_CONFIRM_ESCALATION`."""
    from ajar.chain_planner import wake_matching_doors_for_artifact
    from ajar.db import evaluate_adaptive_threat_assumptions, new_id, utc_now_iso

    sev = str(claim_row["severity"] or "").lower()
    cid = str(claim_row["claim_id"])
    loc = str(claim_row["locus"] or "")
    sub = str(claim_row["subsystem"] or "")
    consume_hooks_for_locus(conn, locus=loc, source_entity_id=cid, hook_code="H6_RELEASE_UB_DIFF")
    evaluate_adaptive_threat_assumptions(
        conn,
        evidence_ref=finding_id,
        confirmed_locus=loc,
        provided_tags=provides_tags,
    )
    woken = wake_matching_doors_for_artifact(
        conn,
        artifact_id=finding_id,
        artifact_kind="finding",
        locus=loc,
        subsystem=sub,
        text_blob=f"{claim_row['title']} {claim_row['mechanism']}",
        provides_tags=provides_tags,
        snapshot_id=snapshot_id,
        trigger_cmd="claim.reproduce",
    )

    should_escalate = sev in ("low", "medium") or (sev == "high" and realism_tier == "stepping_stone")
    if not should_escalate:
        return {"woken_doors": woken} if woken else None

    rel_file = loc.split(":", 1)[0].strip().lstrip("./")
    callers: list[str] = []
    for r in conn.execute(
        "SELECT src_file FROM repomap_edges WHERE dst_file = ? ORDER BY weight DESC LIMIT 8",
        (rel_file,),
    ).fetchall():
        sf = str(r["src_file"])
        if sf and sf not in callers:
            callers.append(sf)
        if len(callers) >= 4:
            break
    caller_hint = ", ".join(callers) if callers else "1-hop callers"

    esc_tid = new_id("task")
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO tasks(
            task_id, surface_id, parent_claim_id, kind, direction, title, subsystem, locus,
            priority, status, salience_score, summary, created_at, updated_at
        ) VALUES (?, ?, ?, 'escalate', 'outside_in', ?, ?, ?, 'high', 'open', 80, ?, ?, ?)
        """,
        (
            esc_tid,
            claim_row["surface_id"],
            cid,
            f"Evaluate post-confirm escalation consumers of {finding_id} ({sev}/{realism_tier})",
            sub,
            loc,
            f"Single-pass ceiling-breaker (`max_leases=1`): check whether {caller_hint} trust output from {finding_id}@{loc} or park as an Open Door.",
            now_iso,
            now_iso,
        ),
    )
    hook = register_epistemic_hook(
        conn,
        hook_code="H5_POST_CONFIRM_ESCALATION",
        trigger_cmd="claim.reproduce",
        source_entity_id=finding_id,
        dedup_material=finding_id,
        subsystem=sub,
        target_locus=loc,
        spawned_task_id=esc_tid,
        max_leases=1,
        directive_text=(
            f"Finding {finding_id} ({sev}/{realism_tier}) is proven at {loc}; check consumers ({caller_hint}) "
            "or park an Open Door (`ajar door park`) if a downstream sink needs one missing link."
        ),
        kill_rule="STOP and mark done unless every escalation hop uses verified code paths in target modules.",
    )
    return {"escalate_task_id": esc_tid, "hook": hook, "woken_doors": woken}
