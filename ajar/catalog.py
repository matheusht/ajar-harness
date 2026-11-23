"""Unified Issue & Gadget Catalog and backward sink-to-source call-cone slicer.

Implements two complementary synthesis primitives for multi-hop vulnerability chaining:
1. `search_issue_catalog`: Queries verified findings, active capabilities, trust-laundering
   gadgets (`role='trust_gadget'`), candidate/config-gated claims, unexplained anomalies, and
   suspended Open Doors in a single normalized catalog, surfacing direct tag/locus/guard bridges.
2. `trace_backward_sink_slices`: Resolves a Crown-Jewel sink, Open Door, symbol, or `file:line`
   locus and walks `repomap_edges` backward (`callee <- caller`) up to `max_hops`, intersecting
   every hop with catalog primitives/gadgets and highlighting unvisited upstream caller files.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from typing import Any, Sequence

from ajar.redact import scrub_text
from ajar.store import parse_tag_list

_TOKEN_RE = re.compile(r"[a-z0-9_./:-]{2,}")


def _norm_file(locus: str) -> str:
    return (locus or "").split(":", 1)[0].strip().lstrip("./")


def _safe_json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    except (ValueError, TypeError):
        pass
    return []


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def search_issue_catalog(
    conn: sqlite3.Connection,
    *,
    query: str = "",
    tags: str | Sequence[str] | None = None,
    subsystem: str = "",
    role: str = "",
    include_unverified: bool = True,
    limit: int = 30,
) -> dict[str, Any]:
    """Query the unified Issue & Gadget Catalog across findings, primitives, claims, anomalies, and doors."""
    q_tokens = _tokenize(query)
    want_tags = set(parse_tag_list(tags))
    sub_filter = (subsystem or "").strip().lower()
    role_filter = (role or "").strip().lower()

    tables = {
        str(r[0])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    all_items: list[dict[str, Any]] = []
    counts_by_kind: dict[str, int] = {
        "finding": 0,
        "capability": 0,
        "trust_gadget": 0,
        "candidate_claim": 0,
        "anomaly": 0,
        "open_door": 0,
    }

    if "findings" in tables:
        for r in conn.execute("SELECT * FROM findings ORDER BY created_at ASC").fetchall():
            rk = set(r.keys())
            prov = parse_tag_list(r["provides_tags_json"]) if "provides_tags_json" in rk else []
            loc = str(r["locus"] or "")
            f_sub = _norm_file(loc).split("/", 1)[0] if loc else ""
            item = {
                "item_id": str(r["finding_id"]),
                "item_kind": "finding",
                "verified": True,
                "severity": str(r["severity"] or "high"),
                "realism_tier": str(r["realism_tier"] if "realism_tier" in rk else "stepping_stone"),
                "locus": loc,
                "file": _norm_file(loc),
                "subsystem": f_sub,
                "provides_tags": prov,
                "requires_tags": [],
                "guarded_by_locus": "",
                "snapshot_id": str(r["snapshot_id"] if "snapshot_id" in rk else ""),
                "summary": scrub_text(f"{r['title']} — {str(r['root_cause'])[:180]}"),
            }
            counts_by_kind["finding"] += 1
            all_items.append(item)

    if "primitives" in tables:
        for r in conn.execute("SELECT * FROM primitives WHERE status != 'dry' ORDER BY created_at ASC").fetchall():
            rk = set(r.keys())
            prole = str(r["role"] if "role" in rk else "capability") or "capability"
            ikind = "trust_gadget" if prole == "trust_gadget" else "capability"
            prov = parse_tag_list(r["provides_tags_json"]) if "provides_tags_json" in rk else []
            req = parse_tag_list(r["requires_tags_json"]) if "requires_tags_json" in rk else []
            syms = _safe_json_list(r["symbols_json"]) if "symbols_json" in rk else []
            loc = str(r["locus"] or "")
            item = {
                "item_id": str(r["primitive_id"]),
                "item_kind": ikind,
                "verified": True,
                "severity": "medium",
                "realism_tier": "stepping_stone",
                "locus": loc,
                "file": _norm_file(loc),
                "subsystem": str(r["subsystem"] or ""),
                "provides_tags": prov,
                "requires_tags": req,
                "symbols": syms,
                "guarded_by_locus": str(r["guarded_by_locus"] or ""),
                "trusted_invariant": str(r["trusted_invariant"] if "trusted_invariant" in rk else ""),
                "snapshot_id": str(r["snapshot_id"] if "snapshot_id" in rk else ""),
                "summary": scrub_text(
                    f"[{r['kind']}] pre: {str(r['preconditions'])[:100]} -> post: {str(r['postconditions'])[:120]}"
                ),
            }
            counts_by_kind[ikind] += 1
            all_items.append(item)

    if include_unverified and "claims" in tables:
        for r in conn.execute(
            """
            SELECT * FROM claims
            WHERE status IN ('proposed', 'survived_falsify', 'needs_instrumentation', 'config_gated')
            ORDER BY created_at ASC
            """
        ).fetchall():
            loc = str(r["locus"] or "")
            cfg = str(r["config_gate"] or "") if "config_gate" in r.keys() else ""
            item = {
                "item_id": str(r["claim_id"]),
                "item_kind": "candidate_claim",
                "verified": False,
                "status": str(r["status"]),
                "severity": str(r["severity"] or "medium"),
                "realism_tier": "stepping_stone",
                "locus": loc,
                "file": _norm_file(loc),
                "subsystem": str(r["subsystem"] or ""),
                "provides_tags": [],
                "requires_tags": [f"config:{cfg.lower()[:32]}"] if cfg else [],
                "guarded_by_locus": str(r["falsify_control_locus"] or ""),
                "config_gate": cfg,
                "snapshot_id": "",
                "summary": scrub_text(f"[{r['status']}] {r['title']} — {str(r['mechanism'])[:160]}"),
            }
            counts_by_kind["candidate_claim"] += 1
            all_items.append(item)

    if include_unverified and "anomalies" in tables:
        for r in conn.execute(
            "SELECT * FROM anomalies WHERE status = 'unexplained' ORDER BY created_at ASC"
        ).fetchall():
            loc = str(r["locus"] or "")
            item = {
                "item_id": str(r["anomaly_id"]),
                "item_kind": "anomaly",
                "verified": False,
                "severity": "low",
                "realism_tier": "stepping_stone",
                "locus": loc,
                "file": _norm_file(loc),
                "subsystem": str(r["subsystem"] or ""),
                "provides_tags": [],
                "requires_tags": [],
                "guarded_by_locus": "",
                "snapshot_id": "",
                "summary": scrub_text(str(r["observation"])[:220]),
            }
            counts_by_kind["anomaly"] += 1
            all_items.append(item)

    if "parked_doors" in tables:
        for r in conn.execute(
            "SELECT * FROM parked_doors WHERE status IN ('parked', 'bridging', 'ready') ORDER BY created_at ASC"
        ).fetchall():
            loc = str(r["anchor_locus"] or "")
            wtags = parse_tag_list(r["wanted_tags_json"])
            wsyms = _safe_json_list(r["wanted_symbols_json"])
            held = _safe_json_list(r["held_ids_json"])
            item = {
                "item_id": str(r["door_id"]),
                "item_kind": "open_door",
                "verified": str(r["status"]) == "ready",
                "status": str(r["status"]),
                "severity": "critical" if r["jewel_id"] else "high",
                "realism_tier": "stepping_stone",
                "locus": loc,
                "file": _norm_file(loc),
                "subsystem": str(r["subsystem"] or ""),
                "provides_tags": [],
                "requires_tags": wtags,
                "symbols": wsyms,
                "held_ids": held,
                "guarded_by_locus": str(r["blocker_locus"] or ""),
                "snapshot_id": str(r["snapshot_id"] or ""),
                "summary": scrub_text(f"[{r['status']}] missing: {r['missing_link_summary']} (wishlist: {r['wishlist_query']})"),
            }
            counts_by_kind["open_door"] += 1
            all_items.append(item)

    # Synthesize direct 1-hop composable pairs across the catalog (`producer -> consumer`).
    composable_pairs: list[dict[str, Any]] = []
    producers = [it for it in all_items if it["provides_tags"] or it["item_kind"] in ("finding", "capability")]
    consumers = [it for it in all_items if it["requires_tags"] or it["guarded_by_locus"] or it["item_kind"] in ("trust_gadget", "open_door")]
    for prod in producers:
        ptags = set(prod["provides_tags"])
        pfile = prod["file"]
        for cons in consumers:
            if prod["item_id"] == cons["item_id"]:
                continue
            ctags = set(cons["requires_tags"])
            shared_tags = sorted(ptags & ctags)
            guard_file = _norm_file(str(cons.get("guarded_by_locus") or ""))
            guard_match = bool(pfile and guard_file and pfile == guard_file)
            if shared_tags or guard_match:
                composable_pairs.append(
                    {
                        "upstream_id": prod["item_id"],
                        "upstream_kind": prod["item_kind"],
                        "upstream_locus": prod["locus"],
                        "downstream_id": cons["item_id"],
                        "downstream_kind": cons["item_kind"],
                        "downstream_locus": cons["locus"],
                        "matched_tags": shared_tags,
                        "breaks_guard_file": guard_file if guard_match else "",
                    }
                )

    filtered: list[dict[str, Any]] = []
    for it in all_items:
        if role_filter and it["item_kind"] != role_filter:
            continue
        if sub_filter and sub_filter not in str(it["subsystem"]).lower() and sub_filter not in str(it["file"]).lower():
            continue
        item_tags = set(it["provides_tags"]) | set(it["requires_tags"])
        if want_tags and not (want_tags & item_tags):
            continue
        blob = " ".join(
            [
                str(it["item_id"]),
                str(it["item_kind"]),
                str(it["locus"]),
                str(it["subsystem"]),
                " ".join(it["provides_tags"]),
                " ".join(it["requires_tags"]),
                " ".join(it.get("symbols") or []),
                str(it.get("guarded_by_locus") or ""),
                str(it.get("trusted_invariant") or ""),
                str(it["summary"]),
            ]
        ).lower()
        score = 10.0 if it["verified"] else 5.0
        if it["item_kind"] == "open_door" and it.get("status") == "ready":
            score += 15.0
        if q_tokens:
            item_toks = _tokenize(blob)
            hits = q_tokens & item_toks
            substr_hits = sum(1 for qt in q_tokens if qt in blob)
            if not hits and substr_hits == 0:
                continue
            score += (8.0 * len(hits)) + (3.0 * substr_hits)
        if want_tags:
            score += 12.0 * len(want_tags & item_tags)
        scored = dict(it)
        scored["match_score"] = round(score, 2)
        filtered.append(scored)

    filtered.sort(key=lambda x: (-float(x["match_score"]), str(x["item_kind"]), str(x["item_id"])))
    cap_lim = max(1, int(limit))
    return {
        "counts_by_kind": counts_by_kind,
        "total_catalog_items": len(all_items),
        "matched_count": len(filtered),
        "items": filtered[:cap_lim],
        "composable_pairs": composable_pairs[:cap_lim],
    }


def trace_backward_sink_slices(
    conn: sqlite3.Connection,
    *,
    sink: str,
    max_hops: int = 3,
    limit: int = 20,
) -> dict[str, Any]:
    """Walk `repomap_edges` backward (`callee <- caller`) from a sink/jewel/door/symbol and intersect with the Issue Catalog."""
    raw_sink = (sink or "").strip()
    hops_cap = max(1, min(6, int(max_hops)))
    lim = max(1, int(limit))

    tables = {
        str(r[0])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    seed_files: set[str] = set()
    seed_symbols: set[str] = set()
    resolved_label = raw_sink

    if raw_sink.startswith("cjw-") and "crown_jewels" in tables:
        jrow = conn.execute("SELECT * FROM crown_jewels WHERE jewel_id = ?", (raw_sink,)).fetchone()
        if jrow is not None:
            resolved_label = f"{raw_sink}:{jrow['name']}@{jrow['locus']}"
            jf = _norm_file(str(jrow["locus"] or ""))
            if jf:
                seed_files.add(jf)
            seed_symbols.update(_safe_json_list(jrow["symbols_json"]))
    elif raw_sink.startswith("door-") and "parked_doors" in tables:
        drow = conn.execute("SELECT * FROM parked_doors WHERE door_id = ?", (raw_sink,)).fetchone()
        if drow is not None:
            resolved_label = f"{raw_sink}@{drow['anchor_locus']}"
            for loc_col in ("anchor_locus", "blocker_locus"):
                df = _norm_file(str(drow[loc_col] or ""))
                if df:
                    seed_files.add(df)
            seed_symbols.update(_safe_json_list(drow["wanted_symbols_json"]))
    else:
        cand_file = _norm_file(raw_sink)
        if ("/" in cand_file or "." in cand_file) and "repomap_symbols" in tables:
            fhit = conn.execute(
                "SELECT DISTINCT rel_path FROM repomap_symbols WHERE rel_path = ? OR rel_path LIKE ?",
                (cand_file, f"%{cand_file}"),
            ).fetchall()
            for r in fhit:
                seed_files.add(str(r[0]))
        if not seed_files and cand_file and ("/" in cand_file or cand_file.endswith((".c", ".h", ".py", ".rs", ".go", ".ts", ".js", ".sol"))):
            seed_files.add(cand_file)
        if "repomap_symbols" in tables:
            sym_name = raw_sink.split(":", 1)[-1].strip() if ":" in raw_sink and not raw_sink.split(":", 1)[-1].isdigit() else raw_sink
            shits = conn.execute(
                "SELECT rel_path, name FROM repomap_symbols WHERE name = ? OR name LIKE ? ORDER BY pagerank DESC LIMIT 12",
                (sym_name, f"%{sym_name}%"),
            ).fetchall()
            for r in shits:
                seed_files.add(str(r["rel_path"]))
                seed_symbols.add(str(r["name"]))

    # Build reverse call graph (`dst_file -> list[(src_file, symbol, weight)]`).
    rev_edges: dict[str, list[tuple[str, str, float]]] = {}
    if "repomap_edges" in tables:
        for r in conn.execute(
            "SELECT src_file, dst_file, symbol, weight FROM repomap_edges ORDER BY weight DESC"
        ).fetchall():
            dst_f = str(r["dst_file"])
            src_f = str(r["src_file"])
            rev_edges.setdefault(dst_f, []).append((src_f, str(r["symbol"]), float(r["weight"] or 1.0)))
            if seed_symbols and str(r["symbol"]) in seed_symbols and dst_f not in seed_files:
                seed_files.add(dst_f)

    visited_cov: set[str] = set()
    if "coverage_spans" in tables:
        for r in conn.execute("SELECT DISTINCT rel_path FROM coverage_spans").fetchall():
            visited_cov.add(_norm_file(str(r[0] or "")))
    if "tasks" in tables:
        for r in conn.execute("SELECT locus FROM tasks WHERE status IN ('done', 'dry') AND locus != ''").fetchall():
            visited_cov.add(_norm_file(str(r[0] or "")))

    catalog = search_issue_catalog(conn, include_unverified=True, limit=500)
    items_by_file: dict[str, list[dict[str, Any]]] = {}
    for it in catalog["items"]:
        if it["file"]:
            items_by_file.setdefault(it["file"], []).append(it)

    # BFS backward from `seed_files` up to `hops_cap`.
    best_hop: dict[str, int] = {}
    call_chain_for: dict[str, list[str]] = {}
    via_symbols_for: dict[str, list[str]] = {}
    path_weight_for: dict[str, float] = {}
    q: deque[str] = deque()

    for sf in sorted(seed_files):
        best_hop[sf] = 0
        call_chain_for[sf] = [sf]
        via_symbols_for[sf] = sorted(seed_symbols)[:4]
        path_weight_for[sf] = 10.0
        q.append(sf)

    while q:
        cur_f = q.popleft()
        cur_d = best_hop[cur_f]
        if cur_d >= hops_cap:
            continue
        for caller_f, sym, w in rev_edges.get(cur_f, ()):
            nxt_d = cur_d + 1
            if caller_f not in best_hop:
                best_hop[caller_f] = nxt_d
                call_chain_for[caller_f] = [caller_f, *call_chain_for[cur_f]]
                via_symbols_for[caller_f] = [sym, *via_symbols_for[cur_f]][:6]
                path_weight_for[caller_f] = round(path_weight_for[cur_f] + w, 4)
                q.append(caller_f)

    hop_entries: list[dict[str, Any]] = []
    unvisited_callers: list[dict[str, Any]] = []
    candidate_chains: list[dict[str, Any]] = []

    sink_items: list[dict[str, Any]] = []
    for sf in sorted(seed_files):
        sink_items.extend(items_by_file.get(sf, ()))

    for fpath, hop in sorted(best_hop.items(), key=lambda kv: (kv[1], -path_weight_for.get(kv[0], 0.0), kv[0])):
        f_items = items_by_file.get(fpath, [])
        is_visited = fpath in visited_cov
        entry = {
            "file": fpath,
            "hop": hop,
            "visited": is_visited,
            "call_path_to_sink": call_chain_for[fpath],
            "via_symbols": via_symbols_for[fpath],
            "path_weight": path_weight_for[fpath],
            "catalog_item_ids": [it["item_id"] for it in f_items],
            "catalog_kinds": sorted({it["item_kind"] for it in f_items}),
        }
        hop_entries.append(entry)
        if hop >= 1 and not is_visited:
            unvisited_callers.append(
                {
                    "file": fpath,
                    "hop": hop,
                    "call_path_to_sink": call_chain_for[fpath],
                    "via_symbols": via_symbols_for[fpath],
                    "path_weight": path_weight_for[fpath],
                }
            )
        if hop >= 1 and f_items:
            # Check for intermediate `trust_gadget` / `capability` items along `call_chain_for[fpath]`.
            mid_items: list[str] = []
            for mid_f in call_chain_for[fpath][1:-1]:
                mid_items.extend(it["item_id"] for it in items_by_file.get(mid_f, ()))
            for up_it in f_items:
                if up_it["item_kind"] in ("finding", "capability", "candidate_claim", "anomaly"):
                    candidate_chains.append(
                        {
                            "upstream_item_id": up_it["item_id"],
                            "upstream_kind": up_it["item_kind"],
                            "upstream_locus": up_it["locus"],
                            "intermediate_bridge_ids": mid_items[:4],
                            "sink_target": resolved_label,
                            "hop_distance": hop,
                            "call_path_to_sink": call_chain_for[fpath],
                            "via_symbols": via_symbols_for[fpath],
                            "sink_catalog_ids": [si["item_id"] for si in sink_items[:4]],
                        }
                    )

    return {
        "sink_query": raw_sink,
        "sink_resolved": resolved_label,
        "seed_files": sorted(seed_files),
        "seed_symbols": sorted(seed_symbols),
        "max_hops": hops_cap,
        "reachable_files_count": len(hop_entries),
        "hop_slices": hop_entries[:lim],
        "candidate_backward_chains": candidate_chains[:lim],
        "unvisited_caller_files": unvisited_callers[:lim],
    }
