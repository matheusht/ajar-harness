"""20-seed 3-way quantitative A/B benchmark for Wave-C (`v3.3-sim` vs `v3.4-base` vs `v3.4-wave-c`).

Measures deterministic lift across `N = 20` PRNG seeds (`random.Random(1000 + trial)`) on a
synthetic 12-island, 60-file C-scale systems repository (`uncapped_research`, `cogs_cap_usd = 0.0`,
`stopping_criterion = 'crown-jewel'`):
  1. Subsystem Illumination @ 16 Explore Leases (`>= 0.80` vs `<= 0.55` / `<= 0.35`)
  2. Max Single-Island Explore Lease Share (`<= 0.35` vs `>= 0.45` / `>= 0.55`)
  3. False-Positive Conjunctive Chain Tasks Spawned (`== 0.0` vs `>= 1.0`)
  4. True Middle-Unicorn Recall@8 (`== 1.00`) & MRR (`>= 0.75` vs `0.00`)
  5. Mean Explore Leases to Crown-Jewel Percolation (`<= 9.5` vs `>= 16.5` / `> 22.0`)
  6. False Progress Resets Across 25 Bureaucratic Churn Events (`0 / 25` vs `25 / 25`)
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import shutil
import sqlite3
import tempfile
import time
import unittest
from collections import deque
from typing import Any, Sequence

import ajar.chain_planner as chain_planner_mod
from ajar import EXIT_OK
from ajar.chain_planner import list_crown_jewels
from ajar.db import (
    compute_epistemic_delta,
    compute_island_illumination,
    compute_root_plateau_throttles,
    infer_subsystem,
    lease_next_task,
    log_event,
    new_id,
    open_run_db,
    parse_tag_list,
    utc_now_iso,
)
from ajar.hooks import evaluate_claude_stop_hook
from ajar.store import KIND_SALIENCE_FLOORS, PRIORITY_BASE_SALIENCE, immediate_tx

ISLAND_FILES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("isl:unpack", ("unpack.c", "unpack-check.c", "unpack-tar.c", "unpack-patch.c", "unpack-links.c")),
    ("isl:reconcile", ("reconcile.c", "reconcile-tree.c", "reconcile-threeway.c", "reconcile-blobs.c", "reconcile-index.c")),
    ("isl:diffcore", ("diffcore.c", "diffcore-api.c", "diffcore-reconcile.c", "diffcore-fast.c", "diffcore-hist.c")),
    ("isl:storage", ("storage.c", "storage-objects.c", "storage-bitmap.c", "storage-check.c", "storage-write.c")),
    (
        "isl:channel",
        ("channel.c", "channel-helper.c", "channel-internal.c", "channel-http.c", "channel-fd.c"),
    ),
    ("isl:indexdb", ("indexdb.c", "indexdb-files.c", "indexdb-packed.c", "indexdb-iter.c", "indexdb-cache.c")),
    ("isl:attr", ("attr.c", "attr-check.c", "attr-stack.c", "attr-macro.c", "attr-tree.c")),
    ("isl:sandbox", ("sandbox.c", "sandbox-add.c", "sandbox-list.c", "sandbox-lock.c", "sandbox-prune.c")),
    (
        "isl:manifest",
        ("manifest.c", "manifest-config.c", "manifest-cache.c", "manifest-init.c", "manifest-sync.c"),
    ),
    (
        "isl:credential",
        (
            "credential.c",
            "credential-cache.c",
            "credential-store.c",
            "credential-helper.c",
            "credential-url.c",
        ),
    ),
    ("isl:ingest", ("ingest.c", "ingest-stream.c", "ingest-archive.c", "ingest-filter.c", "ingest-v2.c")),
    (
        "isl:procexec",
        (
            "procexec/proc-exec.c",
            "procexec/child-proc.c",
            "procexec/plugin-exec.c",
            "procexec/async-pipe.c",
            "procexec/spawn-env.c",
        ),
    ),
)

_JEWEL_WEIGHTS: dict[str, float] = {
    "rce": 1.00,
    "sandbox_escape": 1.00,
    "fund_drain": 1.00,
    "auth_bypass": 0.92,
    "state_takeover": 0.92,
    "key_exfil": 0.90,
    "arbitrary_write": 0.86,
    "mem_corrupt": 0.85,
}


def _ref_ah_puct_score(
    *,
    reaches_crown_jewel: bool,
    impact_class: str = "rce",
    unmet_requires_count: int = 1,
    has_unmet_guard: bool = False,
    call_hop_distance: int | None = None,
    max_edge_weight: float = 0.0,
    has_snapshot: bool = False,
    backward_proved_steps: int = 0,
    bridge_visits: int = 0,
    total_bridge_visits: int = 0,
    gamma: float = 0.82,
    c_puct: float = 0.35,
) -> float:
    if hasattr(chain_planner_mod, "ah_puct_score"):
        fn: Any = chain_planner_mod.ah_puct_score  # type: ignore[attr-defined,unused-ignore]
        return float(
            fn(
                reaches_crown_jewel=reaches_crown_jewel,
                impact_class=impact_class,
                unmet_requires_count=unmet_requires_count,
                has_unmet_guard=has_unmet_guard,
                call_hop_distance=call_hop_distance,
                max_edge_weight=max_edge_weight,
                has_snapshot=has_snapshot,
                backward_proved_steps=backward_proved_steps,
                bridge_visits=bridge_visits,
                total_bridge_visits=total_bridge_visits,
                gamma=gamma,
                c_puct=c_puct,
            )
        )
    w_impact = _JEWEL_WEIGHTS.get(impact_class.lower(), 0.90) if reaches_crown_jewel else 0.55
    hop_penalty = (
        0.0
        if call_hop_distance == 0
        else 0.15
        if call_hop_distance == 1
        else 0.35
        if call_hop_distance == 2
        else 0.65
    )
    guard_extra = 0.50 if (unmet_requires_count == 0 and has_unmet_guard) else 0.0
    d_hat = max(1.0, float(max(0, unmet_requires_count)) + guard_extra + hop_penalty)
    q_val = (w_impact * (gamma**d_hat)) + (0.02 * float(min(4, max(0, backward_proved_steps))))

    norm_w = min(1.0, max(0.0, float(max_edge_weight)) / 5.0)
    if call_hop_distance == 0:
        s_call = 1.0
    elif call_hop_distance == 1:
        s_call = 0.80 + (0.20 * norm_w)
    elif call_hop_distance == 2:
        s_call = 0.45 + (0.20 * norm_w)
    else:
        s_call = 0.10
    s_snap = 1.0 if has_snapshot else 0.0
    prior = min(1.0, 0.15 + (0.55 * s_call) + (0.30 * s_snap))
    u_val = c_puct * prior * (math.sqrt(1.0 + max(0, total_bridge_visits)) / (1.0 + max(0, bridge_visits)))
    return round(q_val + u_val, 6)


def _evaluate_percolation_for_arm(
    conn: sqlite3.Connection,
    *,
    arm: str,
    enqueue_tasks: bool = True,
    max_hops: int = 10,
) -> dict[str, Any]:
    """Evaluate chain percolation under Arm A (`v3.3-sim`), Arm B (`v3.4-base`), or Arm C (`v3.4-wave-c`).

    When Track C1 (`ah_puct_score`) is merged into `ajar.chain_planner`, Arm C delegates directly
    to `ajar.chain_planner.detect_percolated_multi_hop_paths`.
    """
    if arm == "v3.4-wave-c" and hasattr(chain_planner_mod, "ah_puct_score"):
        return chain_planner_mod.detect_percolated_multi_hop_paths(
            conn, max_hops=max_hops, enqueue_tasks=enqueue_tasks
        )
    if arm == "v3.4-base" and not hasattr(chain_planner_mod, "ah_puct_score"):
        return chain_planner_mod.detect_percolated_multi_hop_paths(
            conn, max_hops=max_hops, enqueue_tasks=enqueue_tasks
        )

    is_wave_c = arm == "v3.4-wave-c"
    nodes: dict[str, dict[str, Any]] = {}
    for p in conn.execute("SELECT * FROM primitives WHERE status != 'dry' ORDER BY rowid ASC").fetchall():
        pid = str(p["primitive_id"])
        prov = set(parse_tag_list(p["provides_tags_json"]))
        req = set(parse_tag_list(p["requires_tags_json"]))
        raw_syms = json.loads(str(p["symbols_json"] or "[]"))
        syms = {str(s).strip().lower() for s in raw_syms if str(s).strip()}
        g_loc = str(p["guarded_by_locus"] or "").strip()
        role = str(p["role"] or "capability")
        nodes[pid] = {
            "id": pid,
            "kind": role,
            "locus": str(p["locus"]),
            "subsystem": str(p["subsystem"]),
            "provides": prov,
            "requires": req,
            "guarded_by": g_loc,
            "symbols": syms,
            "is_source_root": (len(req) == 0 and not g_loc and role == "capability"),
            "is_sink": False,
            "jewel_id": "",
            "impact_class": "",
        }

    for f in conn.execute("SELECT * FROM findings ORDER BY rowid ASC").fetchall():
        fid = str(f["finding_id"])
        prov = set(parse_tag_list(f["provides_tags_json"]))
        nodes[fid] = {
            "id": fid,
            "kind": "finding",
            "locus": str(f["locus"]),
            "subsystem": infer_subsystem(str(f["locus"])),
            "provides": prov,
            "requires": set(),
            "guarded_by": "",
            "symbols": set(),
            "is_source_root": True,
            "is_sink": False,
            "jewel_id": "",
            "impact_class": "",
        }

    jewels = list_crown_jewels(conn)
    jewel_loci = {str(cj["locus"]) for cj in jewels}
    for cj in jewels:
        jid = str(cj["jewel_id"])
        raw_syms = json.loads(str(cj.get("symbols_json") or "[]"))
        cj_syms = {str(s).strip().lower() for s in raw_syms if str(s).strip()}
        cj_tags = {s for s in cj_syms if ":" in s}
        nodes[jid] = {
            "id": jid,
            "kind": "crown_jewel",
            "locus": str(cj["locus"]),
            "subsystem": str(cj["subsystem"]),
            "provides": set(),
            "requires": cj_tags,
            "guarded_by": "",
            "symbols": cj_syms,
            "is_source_root": False,
            "is_sink": True,
            "jewel_id": jid,
            "impact_class": str(cj.get("impact_class") or "rce"),
        }

    for s in conn.execute("SELECT * FROM surfaces ORDER BY rowid ASC").fetchall():
        rtags = set(parse_tag_list(s["requires_tags_json"]))
        if rtags and str(s["locus"]) not in jewel_loci:
            sid = str(s["surface_id"])
            nodes[sid] = {
                "id": sid,
                "kind": "surface_sink",
                "locus": str(s["locus"]),
                "subsystem": str(s["subsystem"]),
                "provides": set(),
                "requires": rtags,
                "guarded_by": "",
                "symbols": set(),
                "is_source_root": False,
                "is_sink": True,
                "jewel_id": "",
                "impact_class": "",
            }

    out_adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    in_adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    edge_modes: dict[tuple[str, str], set[str]] = {}

    for u in nodes.values():
        uid = u["id"]
        if u["is_sink"]:
            continue
        u_file = str(u["locus"]).split(":", 1)[0].strip()
        for v in nodes.values():
            vid = v["id"]
            if uid == vid:
                continue
            modes: set[str] = set()
            if u["provides"] and v["requires"] and (u["provides"] & v["requires"]):
                modes.add("tag")
            if v["guarded_by"]:
                g_file = str(v["guarded_by"]).split(":", 1)[0].strip()
                if u_file and u_file == g_file:
                    modes.add("guard")
            if v["kind"] == "crown_jewel":
                v_file = str(v["locus"]).split(":", 1)[0].strip()
                if ((u_file and u_file == v_file) or (u["symbols"] & v["symbols"])) and (
                    not is_wave_c or not v["requires"] or v["requires"].issubset(u["provides"])
                ):
                    modes.add("jewel_locus_or_sym")
            if modes:
                edge_modes[(uid, vid)] = modes
                out_adj[uid].append(vid)
                in_adj[vid].append(uid)

    fwd_paths: dict[str, list[str]] = {}
    fwd_acc_tags: dict[str, frozenset[str]] = {}
    grounded_tag_paths: dict[str, tuple[list[str], frozenset[str]]] = {}
    sink_multi_paths: dict[str, list[str]] = {}
    q_fwd: deque[tuple[str, list[str], frozenset[str]]] = deque()

    for nid, nd in nodes.items():
        if nd["is_source_root"]:
            init_acc = frozenset(nd["provides"])
            fwd_paths[nid] = [nid]
            fwd_acc_tags[nid] = init_acc
            for t in init_acc:
                if t not in grounded_tag_paths:
                    grounded_tag_paths[t] = ([nid], init_acc)
            q_fwd.append((nid, [nid], init_acc))

    while q_fwd:
        cur, cur_path, cur_acc = q_fwd.popleft()
        if len(cur_path) >= max_hops + 1:
            continue
        for nxt in out_adj.get(cur, ()):
            if nxt in cur_path:
                continue
            req: set[str] = set(nodes[nxt]["requires"])
            modes = edge_modes.get((cur, nxt), set())
            eff_prefix = list(cur_path)
            eff_acc = cur_acc | frozenset(nodes[nxt]["provides"])

            if is_wave_c and len(req) >= 1 and "guard" not in modes and "ready_door" not in modes:
                if req.issubset(cur_acc):
                    pass
                elif (cur_acc & req) and all(m in grounded_tag_paths for m in (req - cur_acc)):
                    merged_prefix = list(cur_path)
                    merged_acc = set(cur_acc)
                    for m_tag in sorted(req - cur_acc):
                        m_path, m_acc = grounded_tag_paths[m_tag]
                        for step_id in m_path:
                            if step_id not in merged_prefix and step_id != nxt:
                                merged_prefix.append(step_id)
                        merged_acc.update(m_acc)
                    if not req.issubset(merged_acc) or len(merged_prefix) > max_hops:
                        continue
                    eff_prefix = merged_prefix
                    eff_acc = frozenset(merged_acc | set(nodes[nxt]["provides"]))
                else:
                    continue

            new_path = [*eff_prefix, nxt]
            if nodes[nxt]["is_sink"]:
                if nxt not in fwd_paths:
                    fwd_paths[nxt] = new_path
                if len(eff_prefix) >= 2 and nxt not in sink_multi_paths:
                    sink_multi_paths[nxt] = new_path
                    fwd_paths[nxt] = new_path
                continue
            if len(eff_prefix) >= max_hops:
                continue
            prev_path = fwd_paths.get(nxt)
            if prev_path is None or (len(prev_path) == 1 and len(new_path) >= 2):
                fwd_paths[nxt] = new_path
                fwd_acc_tags[nxt] = eff_acc
                for t in eff_acc:
                    if t not in grounded_tag_paths or len(new_path) < len(grounded_tag_paths[t][0]):
                        grounded_tag_paths[t] = (new_path, eff_acc)
                q_fwd.append((nxt, new_path, eff_acc))

    bwd_paths: dict[str, list[str]] = {}
    q_bwd: deque[str] = deque()
    sink_order = sorted(
        (nid for nid, nd in nodes.items() if nd["is_sink"]),
        key=lambda nid: (0 if nodes[nid]["kind"] == "crown_jewel" else 1, nid),
    )
    for nid in sink_order:
        bwd_paths[nid] = [nid]
        q_bwd.append(nid)
    while q_bwd:
        cur = q_bwd.popleft()
        cur_suffix = bwd_paths[cur]
        if len(cur_suffix) >= max_hops:
            continue
        for prev in in_adj.get(cur, ()):
            if prev in bwd_paths or prev in cur_suffix:
                continue
            if is_wave_c and len(nodes[cur]["requires"]) >= 2:
                p_modes = edge_modes.get((prev, cur), set())
                if "guard" not in p_modes and not set(nodes[cur]["requires"]).issubset(nodes[prev]["provides"]):
                    continue
            bwd_paths[prev] = [prev, *cur_suffix]
            q_bwd.append(prev)

    percolated: list[dict[str, Any]] = []
    seen_tuples: set[tuple[str, ...]] = set()
    for sink_id in sink_order:
        full_chain = sink_multi_paths.get(sink_id) or fwd_paths.get(sink_id)
        if not full_chain:
            continue
        step_ids = [x for x in full_chain if not nodes[x]["is_sink"]]
        min_steps = 2 if is_wave_c else 1
        if len(step_ids) >= min_steps and tuple(step_ids) not in seen_tuples:
            seen_tuples.add(tuple(step_ids))
            percolated.append(
                {
                    "sink_id": sink_id,
                    "sink_locus": nodes[sink_id]["locus"],
                    "jewel_id": nodes[sink_id]["jewel_id"],
                    "hop_count": len(step_ids),
                    "step_ids": step_ids,
                }
            )

    fwd_tips = [
        nid
        for nid, path in fwd_paths.items()
        if not nodes[nid]["is_sink"]
        and nid not in bwd_paths
        and not any(nxt in fwd_paths and len(fwd_paths[nxt]) > len(path) for nxt in out_adj.get(nid, ()))
    ]
    bwd_entries = [
        nid
        for nid in bwd_paths
        if nid not in fwd_paths and (nodes[nid]["requires"] or nodes[nid]["guarded_by"])
    ]

    adj_weights: dict[str, dict[str, float]] = {}
    for erow in conn.execute(
        "SELECT src_file, dst_file, MAX(weight) AS w FROM repomap_edges GROUP BY src_file, dst_file"
    ).fetchall():
        sf = str(erow["src_file"])
        df = str(erow["dst_file"])
        w = float(erow["w"] or 1.0)
        adj_weights.setdefault(sf, {})[df] = max(w, adj_weights.get(sf, {}).get(df, 0.0))
        adj_weights.setdefault(df, {})[sf] = max(w, adj_weights.get(df, {}).get(sf, 0.0))

    snap_bearing: set[str] = {
        str(r["primitive_id"])
        for r in conn.execute("SELECT primitive_id FROM primitives WHERE snapshot_id != ''").fetchall()
    }

    def _call_prox(loc_a: str, loc_b: str) -> tuple[int | None, float]:
        fa = loc_a.split(":", 1)[0].strip()
        fb = loc_b.split(":", 1)[0].strip()
        if fa and fb and fa == fb:
            return (0, 5.0)
        if fb in adj_weights.get(fa, {}):
            return (1, adj_weights[fa][fb])
        best_2 = 0.0
        found_2 = False
        for mid, w1 in adj_weights.get(fa, {}).items():
            if fb in adj_weights.get(mid, {}):
                found_2 = True
                best_2 = max(best_2, min(w1, adj_weights[mid][fb]))
        if found_2:
            return (2, best_2)
        return (None, 0.0)

    tip_iter = fwd_tips if is_wave_c else fwd_tips[:8]
    entry_iter = bwd_entries if is_wave_c else bwd_entries[:8]

    unicorn_gaps: list[dict[str, Any]] = []
    for tip_id in tip_iter:
        for entry_id in entry_iter:
            if tip_id == entry_id:
                continue
            prefix = fwd_paths[tip_id]
            suffix = bwd_paths[entry_id]
            if len(prefix) + len(suffix) > max_hops + 1:
                continue
            tip_prov = fwd_acc_tags.get(tip_id, frozenset(nodes[tip_id]["provides"])) if is_wave_c else nodes[tip_id]["provides"]
            unmet = sorted(set(nodes[entry_id]["requires"]) - set(tip_prov))
            tail_sink = suffix[-1] if suffix else ""
            reaches_jewel = bool(tail_sink in nodes and nodes[tail_sink]["kind"] == "crown_jewel")
            hop_dist, max_ew = _call_prox(nodes[tip_id]["locus"], nodes[entry_id]["locus"])
            has_snap = any(sid in snap_bearing for sid in prefix)
            puct = _ref_ah_puct_score(
                reaches_crown_jewel=reaches_jewel,
                impact_class=str(nodes[tail_sink]["impact_class"] or "rce") if tail_sink in nodes else "rce",
                unmet_requires_count=len(unmet),
                has_unmet_guard=bool(nodes[entry_id]["guarded_by"]),
                call_hop_distance=hop_dist,
                max_edge_weight=max_ew,
                has_snapshot=has_snap,
                backward_proved_steps=len([x for x in suffix if not nodes[x]["is_sink"]]),
            )
            unicorn_gaps.append(
                {
                    "forward_prefix": prefix,
                    "forward_tip_id": tip_id,
                    "forward_tip_locus": nodes[tip_id]["locus"],
                    "forward_provides": sorted(tip_prov),
                    "backward_entry_id": entry_id,
                    "backward_entry_locus": nodes[entry_id]["locus"],
                    "backward_guard": nodes[entry_id]["guarded_by"],
                    "unmet_requires": unmet,
                    "backward_suffix": suffix,
                    "reaches_crown_jewel": reaches_jewel,
                    "total_chain_hops_if_bridged": len(prefix) + 1 + len([x for x in suffix if not nodes[x]["is_sink"]]),
                    "ah_puct_score": puct,
                    "call_hop_distance": hop_dist,
                    "has_snapshot": has_snap,
                }
            )

    if is_wave_c:
        unicorn_gaps.sort(
            key=lambda g: (
                0 if bool(g.get("reaches_crown_jewel")) else 1,
                -float(g["ah_puct_score"]),
                len(g["unmet_requires"]),
                -len(g["backward_suffix"]),
                -int(g["total_chain_hops_if_bridged"]),
                str(g["backward_entry_id"]),
            )
        )
    else:
        unicorn_gaps.sort(
            key=lambda g: (
                0 if bool(g.get("reaches_crown_jewel")) else 1,
                len(g["unmet_requires"]),
                -len(g["backward_suffix"]),
                -int(g["total_chain_hops_if_bridged"]),
                str(g["backward_entry_id"]),
            )
        )

    spawned_tasks: list[str] = []
    if enqueue_tasks and percolated:
        now_iso = utc_now_iso()
        for pc in percolated:
            step_csv = ",".join(pc["step_ids"])
            exists = conn.execute(
                "SELECT 1 FROM tasks WHERE kind = 'chain' AND summary LIKE '%' || ? || '%' LIMIT 1",
                (step_csv,),
            ).fetchone()
            if not exists:
                tid = new_id("task")
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, direction, title, subsystem, locus, priority, status,
                        salience_score, summary, created_at, updated_at
                    ) VALUES (?, 'chain', 'outside_in', ?, ?, ?, 'critical', 'open', 98, ?, ?, ?)
                    """,
                    (
                        tid,
                        f"Verify percolated {pc['hop_count']}-step chain ({step_csv}) -> {pc['sink_id']}",
                        infer_subsystem(pc["sink_locus"]),
                        pc["sink_locus"],
                        f"Percolated multi-hop path [{step_csv}] -> {pc['sink_id']}@{pc['sink_locus']}",
                        now_iso,
                        now_iso,
                    ),
                )
                spawned_tasks.append(tid)

    return {
        "percolated_paths": percolated,
        "unicorn_gaps": unicorn_gaps[:8],
        "spawned_chain_tasks": spawned_tasks,
    }


def _build_base_template_db(base_dir: pathlib.Path, target_dir: pathlib.Path) -> pathlib.Path:
    """Create the shared 12-island, 60-file synthetic `run.db` template (`cogs_cap_usd = 0.0`)."""
    tpl_path = base_dir / "template.db"
    conn = open_run_db(tpl_path, create=True, ajar_home=base_dir)
    now = "2026-11-23T00:00:00Z"
    try:
        with immediate_tx(conn):
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, target_path, workspace_path, target_mode, workspace_mode,
                    goal, stopping_criterion, campaign_phase, budget_usd, code_quote_usd,
                    cogs_cap_usd, pricing_mode, commitment_hash, status, created_at
                ) VALUES (
                    'run-bench', ?, ?, 'source', 'in_place',
                    'Wave-C 20-seed benchmark', 'crown-jewel', 'hunt', 0.0, 0.0,
                    0.0, 'uncapped_research', 'bench-commit-sha', 'active', ?
                )
                """,
                (str(target_dir), str(target_dir), now),
            )

            sym_idx = 0
            for _isl, files in ISLAND_FILES:
                for rel in files:
                    sym_idx += 1
                    conn.execute(
                        "INSERT INTO repomap_symbols(symbol_id, rel_path, name, kind, line_no, pagerank) VALUES (?, ?, ?, 'fn', 1, 0.05)",
                        (f"sym-{sym_idx:03d}", rel, f"fn_{sym_idx}"),
                    )

            # 2-hop structural call path: `manifest.c -> channel.c -> procexec/proc-exec.c`
            conn.execute(
                """
                INSERT INTO repomap_edges(src_file, dst_file, symbol, weight)
                VALUES ('manifest.c', 'channel.c', 'channel_push_frame', 4.8),
                       ('channel.c', 'procexec/proc-exec.c', 'run_command', 4.8)
                """
            )

            # Crown Jewel in `isl:procexec` + 3-tag conjunctive surface sink in `isl:storage`
            conn.execute(
                """
                INSERT INTO crown_jewels(
                    jewel_id, name, subsystem, locus, impact_class, symbols_json,
                    max_interaction_steps, require_default_config, forbid_visible_error,
                    status, created_at, updated_at
                ) VALUES (
                    'cjw-rce', 'Child Command Execution', 'procexec', 'procexec/proc-exec.c:42',
                    'rce', '["run_command", "cap:ExecHook"]', 1, 1, 1, 'locked', ?, ?
                )
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO surfaces(
                    surface_id, name, kind, subsystem, locus, priority, requires_tags_json, created_at
                ) VALUES (
                    'surf-conj', 'Conjunctive Storage Sink', 'cli', 'storage', 'storage-objects.c:80',
                    'critical', '["cap:hook_mode", "cap:path_norm", "cap:symlink_stage"]', ?
                ), (
                    'surf-unpack', 'Unpack Entry', 'cli', 'unpack', 'unpack.c:10', 'high', '[]', ?
                )
                """,
                (now, now),
            )

            # Forward Tip #0: 1-of-3 partial tag match decoy toward `surf-conj` (+ auxiliary capability so 2-step chain forms in disjunctive arms)
            conn.execute(
                """
                INSERT INTO primitives(
                    primitive_id, subsystem, locus, kind, role, symbols_json, preconditions, postconditions,
                    provides_tags_json, requires_tags_json, evidence_cmd, status, created_at
                ) VALUES (
                    'prim-decoy-0', 'unpack', 'unpack.c:4', 'input_frame', 'capability', '[]',
                    'patch header', 'emits raw path', '["cap:raw_hdr"]', '[]', 'true', 'active', '2026-11-23T00:00:01Z'
                ), (
                    'prim-decoy-1', 'unpack', 'unpack.c:12', 'path_fold', 'capability', '[]',
                    'cap:raw_hdr', 'partial path norm', '["cap:path_norm"]', '["cap:raw_hdr"]', 'true', 'active', '2026-11-23T00:00:02Z'
                )
                """
            )

            # Forward Tips #1..#10: 10 unrelated source_root noise capabilities inside `isl:unpack` / `isl:manifest`
            # (pushing `prim-stage1` to index #11 > 8 while keeping greenfield islands unvisited at t=0!)
            noise_loci = (
                "unpack.c:18",
                "unpack-check.c:6",
                "unpack-tar.c:6",
                "unpack-patch.c:6",
                "unpack-links.c:6",
                "unpack.c:26",
                "unpack-check.c:12",
                "unpack-tar.c:12",
                "manifest-config.c:8",
                "manifest-cache.c:8",
            )
            for idx, nloc in enumerate(noise_loci, start=1):
                conn.execute(
                    """
                    INSERT INTO primitives(
                        primitive_id, subsystem, locus, kind, role, symbols_json, preconditions, postconditions,
                        provides_tags_json, requires_tags_json, evidence_cmd, status, created_at
                    ) VALUES (?, ?, ?, 'quirk', 'capability', '[]', 'in', 'out', ?, '[]', 'true', 'active', ?)
                    """,
                    (
                        f"prim-noise-{idx:02d}",
                        infer_subsystem(nloc),
                        nloc,
                        json.dumps([f"cap:noise_f{idx:02d}"]),
                        f"2026-11-23T00:01:{idx:02d}Z",
                    ),
                )

            # Forward Tip #11 (past old `[:8]` slice!): `prim-stage1` in `isl:manifest` with materialized `snp-stage1`
            conn.execute(
                """
                INSERT INTO repro_snapshots(
                    snapshot_id, claim_id, rel_dir, archive_path, sha256, size_bytes, manifest_json, source_cmd, created_at
                ) VALUES ('snp-stage1', 'clm-s1', '.', 'repro/snapshots/snp-stage1.tar.gz', 'deadbeef', 512, '{}', 'true', ?)
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO primitives(
                    primitive_id, subsystem, locus, kind, role, symbols_json, preconditions, postconditions,
                    provides_tags_json, requires_tags_json, snapshot_id, evidence_cmd, status, created_at
                ) VALUES (
                    'prim-stage1', 'manifest', 'manifest.c:18', 'config_inject', 'capability', '[]',
                    'manifest descriptor', 'injects alias state', '["cap:ConfigAlias"]', '[]',
                    'snp-stage1', 'true', 'active', '2026-11-23T00:02:00Z'
                )
                """
            )

            # Backward Entries #1..#8 (inside `isl:procexec` ahead of `prim-stage3`, pushing `prim-stage3` to index >= 9 > 8!)
            for bidx in range(1, 9):
                conn.execute(
                    """
                    INSERT INTO primitives(
                        primitive_id, subsystem, locus, kind, role, symbols_json, preconditions, postconditions,
                        provides_tags_json, requires_tags_json, evidence_cmd, status, created_at
                    ) VALUES (?, 'procexec', 'procexec/spawn-env.c:20', 'sink_gadget', 'trust_gadget', '["run_command"]',
                              'multi-precond', 'calls run_command', '["cap:ExecHook"]', ?, 'true', 'active', ?)
                    """,
                    (
                        f"prim-bwd-{bidx:02d}",
                        json.dumps([f"cap:bwd_a{bidx}", f"cap:bwd_b{bidx}", f"cap:bwd_c{bidx}", f"cap:bwd_d{bidx}"]),
                        f"2026-11-23T00:03:{bidx:02d}Z",
                    ),
                )

            # Backward Entry #9 (past old `[:8]` slice!): true Stage-3 gadget in `isl:procexec` requiring 1 tag `cap:ChannelHandoff`
            conn.execute(
                """
                INSERT INTO primitives(
                    primitive_id, subsystem, locus, kind, role, symbols_json, preconditions, postconditions,
                    provides_tags_json, requires_tags_json, evidence_cmd, status, created_at
                ) VALUES (
                    'prim-stage3', 'procexec', 'procexec/proc-exec.c:25', 'hook_handoff', 'trust_gadget', '["run_command"]',
                    'cap:ChannelHandoff', 'executes run_command', '["cap:ExecHook"]', '["cap:ChannelHandoff"]',
                    'true', 'active', '2026-11-23T00:04:00Z'
                )
                """
            )
    finally:
        conn.close()
    return tpl_path


def _rescore_legacy_arm(conn: sqlite3.Connection, *, arm: str) -> None:
    """Rescore open explore tasks using historical `v3.3-sim` or `v3.4-base` salience rules."""
    throttles = compute_root_plateau_throttles(conn) if arm == "v3.4-base" else {}
    rows = conn.execute("SELECT * FROM tasks WHERE status = 'open'").fetchall()
    with immediate_tx(conn):
        for r in rows:
            kind = str(r["kind"])
            prio = str(r["priority"] or "high")
            loc = str(r["locus"] or "")
            if arm == "v3.3-sim":
                # v3.3 had no root plateau throttle and no QD-Islands (`high` + unchained prim in unpack = 68 > 60).
                score = PRIORITY_BASE_SALIENCE.get(prio, 60)
                if loc.startswith("unpack"):
                    score += 8
            else:
                # v3.4-base (`2944993`) has KIND_SALIENCE_FLOORS (`escalate` = 82) + file-only `compute_root_plateau_throttles`.
                base_floor = KIND_SALIENCE_FLOORS.get(kind, 0)
                score = max(PRIORITY_BASE_SALIENCE.get(prio, 60), base_floor)
                if loc.startswith("unpack"):
                    score += 8
                rfile = loc.split(":", 1)[0].strip()
                if rfile in throttles and throttles[rfile]["throttled"] and kind in ("investigate", "escalate"):
                    score -= int(throttles[rfile]["salience_penalty"])
            conn.execute("UPDATE tasks SET salience_score = ? WHERE task_id = ?", (max(1, score), r["task_id"]))


def _seed_trial_tasks(conn: sqlite3.Connection, rng: random.Random) -> None:
    """Seed Lease-1 `unpack.c` root task plus 1 `high` greenfield `investigate` task per each of the 11 other islands."""
    now = "2026-11-23T00:05:00Z"
    other_tasks: list[tuple[str, str, str]] = []
    for isl, files in ISLAND_FILES:
        if isl == "isl:unpack":
            continue
        other_tasks.append((isl, files[0], f"{files[0]}:10"))
    rng.shuffle(other_tasks)

    with immediate_tx(conn):
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, surface_id, kind, direction, title, subsystem, locus,
                priority, status, salience_score, created_at, updated_at
            ) VALUES (
                'tsk-unpack-00', 'surf-unpack', 'investigate', 'outside_in',
                'Audit unpack.c root', 'unpack', 'unpack.c:10', 'critical', 'open', 80, ?, ?
            )
            """,
            (now, now),
        )
        for idx, (_isl, fname, loc) in enumerate(other_tasks, start=1):
            ts = f"2026-11-23T00:06:{idx:02d}Z"
            conn.execute(
                """
                INSERT INTO tasks(
                    task_id, kind, direction, title, subsystem, locus,
                    priority, status, salience_score, created_at, updated_at
                ) VALUES (?, 'investigate', 'outside_in', ?, ?, ?, 'high', 'open', 60, ?, ?)
                """,
                (f"tsk-gf-{idx:02d}", f"Explore {fname}", infer_subsystem(loc), loc, ts, ts),
            )


def _run_single_arm_trial(
    *,
    arm: str,
    seed: int,
    template_db: pathlib.Path,
    work_dir: pathlib.Path,
    target_dir: pathlib.Path,
) -> dict[str, float]:
    rng = random.Random(seed)
    db_path = work_dir / f"{arm}-{seed}.db"
    shutil.copy2(template_db, db_path)
    conn = open_run_db(db_path, create=False, ajar_home=work_dir)
    try:
        _seed_trial_tasks(conn, rng)

        # 1. Evaluate initial percolation & Middle-Unicorn gap ranking (`prim-stage1 -> prim-stage3`).
        perc0 = _evaluate_percolation_for_arm(conn, arm=arm, enqueue_tasks=True)
        fp_conj_chains = sum(
            1 for p in perc0["percolated_paths"] if str(p.get("sink_id")) == "surf-conj"
        )
        gaps = list(perc0["unicorn_gaps"])
        unicorn_rank: int | None = None
        for idx, g in enumerate(gaps, start=1):
            if g["forward_tip_id"] == "prim-stage1" and g["backward_entry_id"] == "prim-stage3":
                unicorn_rank = idx
                break
        recall_at_8 = 1.0 if unicorn_rank is not None else 0.0
        mrr = (1.0 / float(unicorn_rank)) if unicorn_rank is not None else 0.0

        # Delete any chain task spawned during initial static check so explore-lease simulation measures explore scheduling cleanly.
        with immediate_tx(conn):
            conn.execute("DELETE FROM tasks WHERE kind = 'chain'")

        # 2. Simulate 24 explore leases (`cogs_cap_usd == 0.0`, `uncapped_research`).
        max_leases = 24
        illum_at_16 = 0.0
        max_island_share_at_16 = 0.0
        leases_to_percolation: float = 25.0
        percolated_jewel = False

        # Track pure explore-lease illumination (islands visited by explore leases) identically across all 3 arms!
        leased_islands_seen: dict[str, int] = {}

        for step in range(1, max_leases + 1):
            step_ts = f"2026-11-23T01:{step // 60:02d}:{step % 60:02d}Z"
            if arm in ("v3.3-sim", "v3.4-base"):
                _rescore_legacy_arm(conn, arm=arm)
                next_row = conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = 'open' AND kind IN ('investigate', 'bridge', 'escalate')
                    ORDER BY salience_score DESC, created_at ASC, task_id ASC
                    LIMIT 1
                    """
                ).fetchone()
                if next_row is None:
                    break
                leased_tid = str(next_row["task_id"])
                leased_loc = str(next_row["locus"] or "")
                with immediate_tx(conn):
                    conn.execute(
                        "UPDATE tasks SET status = 'leased', worker_id = 'w-sim', updated_at = ? WHERE task_id = ?",
                        (step_ts, leased_tid),
                    )
            else:
                leased_dict = lease_next_task(conn, worker_id="w-sim")
                while leased_dict is not None and str(leased_dict["kind"]) == "chain":
                    with immediate_tx(conn):
                        conn.execute(
                            "UPDATE tasks SET status = 'done', updated_at = ? WHERE task_id = ?",
                            (step_ts, leased_dict["task_id"]),
                        )
                    leased_dict = lease_next_task(conn, worker_id="w-sim")
                if leased_dict is None:
                    break
                leased_tid = str(leased_dict["task_id"])
                leased_loc = str(leased_dict["locus"] or "")

            from ajar.store import canonical_island_key

            isl_now = canonical_island_key(leased_loc)
            leased_islands_seen[isl_now] = leased_islands_seen.get(isl_now, 0) + 1

            # Execute leased task transitions:
            with immediate_tx(conn):
                conn.execute(
                    "UPDATE tasks SET status = 'done', closed_epoch = ?, updated_at = ? WHERE task_id = ?",
                    (time.time() + step, step_ts, leased_tid),
                )
                if leased_tid == "tsk-unpack-00":
                    # Adversarial Mode-Collapse Trap (`78.8h C systems campaign`): Lease 1 yields a `medium` `stepping_stone` finding
                    # on `unpack.c` and enqueues 12 derivative `escalate` tasks (4 on `unpack.c` + 8 across sibling `unpack-*.c`).
                    conn.execute(
                        """
                        INSERT INTO claims(
                            claim_id, proposer_worker_id, falsifier_worker_id, title, subsystem, locus,
                            mechanism, mechanism_key, severity, falsification_prediction, falsification_test,
                            status, research_state, evidence_state, created_at, updated_at
                        ) VALUES (
                            'clm-unpack-step', 'w1', 'w2', 'Unpack stepping stone', 'unpack', 'unpack.c:10',
                            'm', 'm', 'medium', 'pred', 'true', 'reproduced', 'confirmed', 'reproduced',
                            '2026-11-23T01:00:01Z', '2026-11-23T01:00:01Z'
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO findings(
                            finding_id, claim_id, title, severity, locus, root_cause, poc_cmd, control_cmd,
                            arm1_clean_poc_json, arm2_clean_ctrl_json, arm3_patch_poc_json, arm4_patch_ctrl_json,
                            realism_tier, attribution, created_at
                        ) VALUES (
                            'fnd-unpack-step', 'clm-unpack-step', 'Unpack stepping stone', 'medium', 'unpack.c:10',
                            'm', 'true', 'true', '{}', '{}', '{}', '{}',
                            'stepping_stone', 'found_autonomously_by_ajar', '2026-11-23T01:00:01Z'
                        )
                        """
                    )
                    deriv_loci = (
                        "unpack.c:20",
                        "unpack.c:30",
                        "unpack.c:40",
                        "unpack.c:50",
                        "unpack.c:60",
                        "unpack.c:70",
                        "unpack.c:80",
                        "unpack.c:90",
                        "unpack-check.c:15",
                        "unpack-check.c:35",
                        "unpack-tar.c:15",
                        "unpack-tar.c:35",
                        "unpack-patch.c:15",
                        "unpack-patch.c:35",
                        "unpack-links.c:15",
                        "unpack-links.c:35",
                    )
                    for didx, dloc in enumerate(deriv_loci, start=1):
                        conn.execute(
                            """
                            INSERT INTO tasks(
                                task_id, kind, direction, title, subsystem, locus,
                                priority, status, salience_score, created_at, updated_at
                            ) VALUES (?, 'escalate', 'outside_in', ?, 'unpack', ?, 'high', 'open', 82, ?, ?)
                            """,
                            (f"tsk-unpack-esc-{didx:02d}", f"Corroborate {dloc}", dloc, step_ts, step_ts),
                        )

                # When `channel.c:10` is explored, the middle link `prim-stage2` (`cap:ConfigAlias -> cap:ChannelHandoff`) lands!
                if leased_loc == "channel.c:10" and not percolated_jewel:
                    conn.execute(
                        """
                        INSERT INTO primitives(
                            primitive_id, subsystem, locus, kind, role, symbols_json, preconditions, postconditions,
                            provides_tags_json, requires_tags_json, evidence_cmd, status, created_at
                        ) VALUES (
                            'prim-stage2', 'channel', 'channel.c:10', 'protocol_handoff', 'capability', '[]',
                            'cap:ConfigAlias', 'emits cap:ChannelHandoff', '["cap:ChannelHandoff"]', '["cap:ConfigAlias"]',
                            'true', 'active', ?
                        )
                        """,
                        (step_ts,),
                    )
                    perc_now = _evaluate_percolation_for_arm(conn, arm=arm, enqueue_tasks=False)
                    if any(str(p.get("jewel_id")) == "cjw-rce" for p in perc_now["percolated_paths"]):
                        percolated_jewel = True
                        leases_to_percolation = float(step)

            if step == 16:
                if arm == "v3.4-wave-c":
                    # Also cross-check `compute_island_illumination` directly on `run.db`.
                    qd = compute_island_illumination(conn)
                    assert qd["island_count"] == 12
                illum_at_16 = float(len(leased_islands_seen)) / 12.0
                max_island_share_at_16 = float(max(leased_islands_seen.values())) / 16.0

        # 3. 25-Event Bureaucratic Churn Burst: compare `max_ev > prev_ev` vs Grounded Lyapunov `Phi(t)`.
        churn_actions: Sequence[tuple[str, str, dict[str, Any]]] = (
            ("finding_calibrated", "fnd-unpack-step", {"new_severity": "low"}),
            ("lead_vote_cast", "vot-b", {"ev_score": 77.0}),
            ("task_leased", "tsk-unpack-00", {"kind": "investigate"}),
            ("task_checkpointed", "tsk-unpack-00", {"progress": "reading"}),
            ("claim_repro_failed", "clm-unpack-step", {"failed_repro_count": 1}),
            ("chain_proposed", "chn-bad", {"verified": False, "steps": ["prim-decoy-0"]}),
        )
        false_resets = 0
        if arm in ("v3.3-sim", "v3.4-base"):
            prev_ev = int(conn.execute("SELECT COALESCE(MAX(event_id), 0) AS m FROM events").fetchone()["m"])
            for c_idx in range(25):
                act, eid, pld = churn_actions[c_idx % len(churn_actions)]
                ev_id = log_event(conn, "w-churn", act, eid, pld)
                if ev_id > prev_ev:
                    false_resets += 1
                    prev_ev = ev_id
        else:
            # Establish baseline stop-hook check #1 (`stalls == 0`)
            conn.execute("UPDATE runs SET consecutive_stall_checks = 0, stop_reason = ''")
            rc_base, p_base = evaluate_claude_stop_hook(conn, target_dir=target_dir)
            assert rc_base != EXIT_OK and p_base["stalls"] == 0
            for c_idx in range(25):
                act, eid, pld = churn_actions[c_idx % len(churn_actions)]
                log_event(conn, "w-churn", act, eid, pld)
                ep_d = compute_epistemic_delta(conn, reference_actions=("stop_hook_check",))
                if float(ep_d["delta_phi"]) > 0.0:
                    false_resets += 1
            # Checks #2, #3, #4 deterministically release on check #4!
            _, p_c2 = evaluate_claude_stop_hook(conn, target_dir=target_dir)
            _, p_c3 = evaluate_claude_stop_hook(conn, target_dir=target_dir)
            rc_c4, p_c4 = evaluate_claude_stop_hook(conn, target_dir=target_dir)
            assert p_c2["stalls"] == 1 and p_c3["stalls"] == 2
            assert rc_c4 == EXIT_OK and bool(p_c4.get("stalled_release"))

        return {
            "illum_at_16": illum_at_16,
            "max_share_at_16": max_island_share_at_16,
            "fp_conj_chains": float(fp_conj_chains),
            "recall_at_8": recall_at_8,
            "mrr": mrr,
            "leases_to_percolation": leases_to_percolation,
            "false_resets": float(false_resets),
        }
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)


def run_wave_c_benchmark(trials: int = 20) -> dict[str, dict[str, float]]:
    """Run the 20-seed 3-way Wave-C A/B benchmark and return per-arm mean metrics."""
    arms = ("v3.3-sim", "v3.4-base", "v3.4-wave-c")
    agg: dict[str, dict[str, float]] = {
        arm: {
            "illum_at_16": 0.0,
            "max_share_at_16": 0.0,
            "fp_conj_chains": 0.0,
            "recall_at_8": 0.0,
            "mrr": 0.0,
            "leases_to_percolation": 0.0,
            "false_resets": 0.0,
        }
        for arm in arms
    }

    with tempfile.TemporaryDirectory(prefix="ajar-wave-c-bench-") as td:
        base = pathlib.Path(td)
        target_dir = base / "sys-sim"
        target_dir.mkdir(parents=True, exist_ok=True)
        for _isl, files in ISLAND_FILES:
            for rel in files:
                fp = target_dir / rel
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text("int stub(void) { return 0; }\n", encoding="utf-8")

        tpl = _build_base_template_db(base, target_dir)
        for trial in range(trials):
            seed = 1000 + trial
            for arm in arms:
                res = _run_single_arm_trial(
                    arm=arm,
                    seed=seed,
                    template_db=tpl,
                    work_dir=base,
                    target_dir=target_dir,
                )
                for k, v in res.items():
                    agg[arm][k] += v

    return {
        arm: {k: round(v / float(trials), 4) for k, v in metrics.items()}
        for arm, metrics in agg.items()
    }


class TestWaveCBenchmark(unittest.TestCase):
    def test_wave_c_qd_islands_puct_and_lyapunov_benchmark(self) -> None:
        means = run_wave_c_benchmark(trials=20)
        v33 = means["v3.3-sim"]
        v34_base = means["v3.4-base"]
        wave_c = means["v3.4-wave-c"]

        # 1. Subsystem Illumination @ 16 Explore Leases (`cogs_cap_usd = 0.0`)
        self.assertLessEqual(v33["illum_at_16"], 0.35, means)
        self.assertLessEqual(v34_base["illum_at_16"], 0.55, means)
        self.assertGreaterEqual(wave_c["illum_at_16"], 0.80, means)
        self.assertGreaterEqual(wave_c["illum_at_16"] - v34_base["illum_at_16"], 0.25, means)

        # 2. Max Single-Island Explore Lease Share (`max_i L_i / 16` without Crown-Jewel win)
        self.assertGreaterEqual(v33["max_share_at_16"], 0.55, means)
        self.assertGreaterEqual(v34_base["max_share_at_16"], 0.45, means)
        self.assertLessEqual(wave_c["max_share_at_16"], 0.35, means)

        # 3. False-Positive Conjunctive Chain Tasks Spawned (on 1-of-3 partial tag match)
        self.assertGreaterEqual(v33["fp_conj_chains"], 1.0, means)
        self.assertGreaterEqual(v34_base["fp_conj_chains"], 1.0, means)
        self.assertEqual(wave_c["fp_conj_chains"], 0.0, means)

        # 4. True Middle-Unicorn Recall@8 & Mean Reciprocal Rank (`MRR`) (tip #11 <-> entry #9)
        self.assertEqual(v33["recall_at_8"], 0.0, means)
        self.assertEqual(v34_base["recall_at_8"], 0.0, means)
        self.assertEqual(wave_c["recall_at_8"], 1.0, means)
        self.assertGreaterEqual(wave_c["mrr"], 0.75, means)

        # 5. Mean Explore Leases to Crown-Jewel Percolation (`>= 40%` reduction over `v3.4-base`)
        self.assertGreater(v33["leases_to_percolation"], 22.0, means)
        self.assertGreaterEqual(v34_base["leases_to_percolation"], 16.5, means)
        self.assertLessEqual(wave_c["leases_to_percolation"], 9.5, means)
        self.assertLessEqual(wave_c["leases_to_percolation"], 0.60 * v34_base["leases_to_percolation"], means)

        # 6. False Progress Resets Across 25 Churn Events (`Delta Phi == 0.0` exact)
        self.assertEqual(v33["false_resets"], 25.0, means)
        self.assertEqual(v34_base["false_resets"], 25.0, means)
        self.assertEqual(wave_c["false_resets"], 0.0, means)


if __name__ == "__main__":
    unittest.main()
