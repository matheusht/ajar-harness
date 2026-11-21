"""Deterministic Reactive Weird-Machine Planner (`Crown Jewels`, `Open Doors`, & Realism Scorer).

Zero-LLM relational engine coordinating:
1. Target-derived Crown-Jewel terminal sinks (`crown_jewels`);
2. Suspended chain subgoals ("Open Doors" in `parked_doors` + `door_fts`) with hybrid
   tri-modal wakeup across (a) capability tags, (b) code symbols / guard loci / 1-hop
   call edges, and (c) SQLite FTS5 BM25 lexical matching;
3. Bounded parallel `bridge` hunt spawning (`<= 2` attempts per parked door);
4. Mechanical precondition realism scoring (`crown_jewel` vs `stepping_stone`) and
   anti-self-override command enforcement.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Sequence

from ajar import EXIT_GATE_BLOCKED, EXIT_USER_ERROR
from ajar.db import AjarError, infer_subsystem, log_event, new_id, utc_now_iso
from ajar.epistemic_hooks import parse_tag_list, register_epistemic_hook
from ajar.redact import scrub_text

VALID_IMPACT_CLASSES: tuple[str, ...] = (
    "rce",
    "sandbox_escape",
    "fund_drain",
    "auth_bypass",
    "state_takeover",
    "key_exfil",
    "arbitrary_write",
    "mem_corrupt",
)

VALID_DOOR_DIRECTIONS: tuple[str, ...] = (
    "sink_to_source",
    "source_to_sink",
    "bidirectional",
)

DELUSIONAL_EXEC_OVERRIDE_RE = re.compile(
    r"(?:"
    r"(?:^|\s)-c\s+['\"]?core\.(?:sshcommand|fsmonitor|pager|editor|askpass|hookspath)\s*="
    r"|(?:^|\s)-c\s+['\"]?protocol\.ext\.allow\s*="
    r"|(?:^|\s)-c\s+['\"]?filter\.[^=\s]+\.(?:clean|smudge|process)\s*="
    r"|(?:^|\s)--(?:upload-pack|receive-pack|exec)\s*="
    r"|\b(?:GIT_SSH_COMMAND|LD_PRELOAD|DYLD_INSERT_LIBRARIES|BASH_ENV|PYTHONINSPECT)\s*="
    r")",
    re.IGNORECASE,
)

VISIBLE_ERROR_NOISE_RE = re.compile(
    r"(?:^|\n)\s*(?:fatal:|Traceback \(most recent call last\):|thread '[^']+' panicked at|Segmentation fault)",
    re.IGNORECASE,
)

STOPWORDS_SET: frozenset[str] = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "into",
        "when",
        "where",
        "which",
        "while",
        "after",
        "before",
        "under",
        "over",
        "through",
        "allow",
        "allows",
        "allowing",
        "block",
        "blocks",
        "blocked",
        "check",
        "checks",
        "checked",
        "reach",
        "reaches",
        "reaching",
        "state",
        "input",
        "output",
        "value",
        "path",
        "file",
        "files",
        "code",
        "call",
        "calls",
        "need",
        "needs",
        "missing",
        "link",
        "chain",
        "stage",
        "step",
        "mode",
        "test",
        "target",
        "user",
        "data",
    }
)

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]{2,}")
IDENT_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def _parse_symbol_list(raw: str | Sequence[str] | None) -> list[str]:
    if raw is None:
        return []
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
                items = re.split(r"[,;\s]+", s)
        else:
            items = re.split(r"[,;\s]+", s)
    else:
        items = [str(x) for x in raw]
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        clean = it.strip().lstrip("./")
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _locus_file_and_line(locus: str) -> tuple[str, int]:
    raw = (locus or "").strip().lstrip("./")
    if not raw:
        return ("", 0)
    if ":" not in raw:
        return (raw, 0)
    fpart, lpart = raw.split(":", 1)
    m = re.match(r"(\d+)", lpart.strip())
    return (fpart.strip(), int(m.group(1)) if m else 0)


def _extract_domain_tokens(text: str) -> set[str]:
    toks: set[str] = set()
    for m in IDENT_TOKEN_RE.findall((text or "").lower()):
        if len(m) >= 4 and m not in STOPWORDS_SET:
            toks.add(m)
    for m in re.findall(r"[a-z0-9_]+(?:/[a-z0-9_.-]+)+", (text or "").lower()):
        toks.add(m)
        base = m.rsplit("/", 1)[-1].split(".", 1)[0]
        if len(base) >= 4 and base not in STOPWORDS_SET:
            toks.add(base)
    return toks


def _safe_fts_or_query(tokens: Sequence[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        alnum = re.sub(r"[^a-zA-Z0-9_]", "", tok).lower()
        if len(alnum) >= 4 and alnum not in STOPWORDS_SET and alnum not in seen:
            seen.add(alnum)
            cleaned.append(f'"{alnum}"')
        if len(cleaned) >= 16:
            break
    return " OR ".join(cleaned)


def _extract_artifact_code_symbols(
    conn: sqlite3.Connection,
    *,
    locus: str,
    text_blob: str,
    explicit_symbols: Sequence[str] = (),
) -> set[str]:
    syms: set[str] = {s.lower() for s in _parse_symbol_list(explicit_symbols)}
    rel_file, line_no = _locus_file_and_line(locus)
    if rel_file:
        syms.add(rel_file.lower())
        base = rel_file.rsplit("/", 1)[-1]
        if base:
            syms.add(base.lower())

    has_repomap = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repomap_symbols'").fetchone()
        is not None
    )
    if not has_repomap:
        for tok in IDENT_TOKEN_RE.findall(text_blob or ""):
            if "_" in tok or any(c.isupper() for c in tok[1:]):
                syms.add(tok.lower())
        return syms

    if rel_file and line_no > 0:
        near = conn.execute(
            """
            SELECT name FROM repomap_symbols
            WHERE rel_path = ? AND ABS(line_no - ?) <= 45
            ORDER BY ABS(line_no - ?) ASC LIMIT 4
            """,
            (rel_file, line_no, line_no),
        ).fetchall()
        for r in near:
            syms.add(str(r["name"]).lower())

    cand_idents = set(IDENT_TOKEN_RE.findall(text_blob or ""))
    for ident in list(cand_idents)[:32]:
        if ident.lower() in STOPWORDS_SET:
            continue
        cnt_row = conn.execute(
            "SELECT COUNT(DISTINCT rel_path) AS c FROM repomap_symbols WHERE name = ?",
            (ident,),
        ).fetchone()
        cnt = int(cnt_row["c"] or 0) if cnt_row else 0
        if 1 <= cnt <= 20:
            syms.add(ident.lower())
        elif "_" in ident and len(ident) >= 5:
            syms.add(ident.lower())

    return syms


def add_crown_jewel(
    conn: sqlite3.Connection,
    *,
    name: str,
    locus: str,
    subsystem: str = "",
    impact_class: str = "rce",
    symbols: str | Sequence[str] | None = None,
    max_interaction_steps: int = 1,
    require_default_config: bool = True,
    forbid_visible_error: bool = True,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Register a target-derived Crown-Jewel terminal sink."""
    imp = (impact_class or "rce").strip().lower()
    if imp not in VALID_IMPACT_CLASSES:
        raise AjarError(
            f"Unsupported --impact-class {imp!r}; choose from {', '.join(VALID_IMPACT_CLASSES)}.",
            EXIT_USER_ERROR,
        )
    if not name.strip() or not locus.strip():
        raise AjarError("Crown-jewel sink requires non-empty --name and --locus.", EXIT_USER_ERROR)

    jid = new_id("cjw")
    now_iso = utc_now_iso()
    sub = subsystem.strip() or infer_subsystem(locus)
    sym_list = _parse_symbol_list(symbols)
    conn.execute(
        """
        INSERT INTO crown_jewels(
            jewel_id, name, subsystem, locus, impact_class, symbols_json,
            max_interaction_steps, require_default_config, forbid_visible_error,
            status, reached_by_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'locked', '', ?, ?)
        """,
        (
            jid,
            scrub_text(name.strip()),
            sub,
            locus.strip(),
            imp,
            json.dumps(sym_list),
            max(1, int(max_interaction_steps)),
            1 if require_default_config else 0,
            1 if forbid_visible_error else 0,
            now_iso,
            now_iso,
        ),
    )
    log_event(
        conn,
        worker_id,
        "crown_jewel_added",
        jid,
        {"name": name.strip(), "locus": locus.strip(), "impact_class": imp, "symbols": sym_list},
    )
    return {
        "jewel_id": jid,
        "name": name.strip(),
        "subsystem": sub,
        "locus": locus.strip(),
        "impact_class": imp,
        "symbols": sym_list,
        "status": "locked",
    }


def list_crown_jewels(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM crown_jewels ORDER BY created_at ASC").fetchall()
    return [dict(r) for r in rows]


def _score_door_match(
    conn: sqlite3.Connection,
    door: sqlite3.Row | dict[str, Any],
    *,
    artifact_id: str,
    locus: str,
    text_blob: str,
    provides_tags: Sequence[str],
    code_symbols: set[str],
    fts_hit_ids: set[str],
) -> tuple[float, list[str]]:
    held_ids = set(_parse_symbol_list(door["held_ids_json"]))
    if artifact_id in held_ids:
        return (0.0, [])
    try:
        prev_matches = json.loads(str(door["matched_by_json"] or "[]"))
    except json.JSONDecodeError:
        prev_matches = []
    if any(isinstance(m, dict) and m.get("id") == artifact_id for m in prev_matches):
        return (0.0, [])

    modes: list[str] = []
    best_score = 0.0

    # Mode 1: Capability / State-Carrier Tag Intersection
    wanted_tags = set(parse_tag_list(str(door["wanted_tags_json"] or "[]")))
    prov_set = set(parse_tag_list(list(provides_tags)))
    if wanted_tags and (wanted_tags & prov_set):
        modes.append("tag")
        best_score = max(best_score, 0.78)

    # Mode 2: Concrete Symbol, Guard-Locus Proximity, or 1-Hop Repomap Call Edge
    art_file, art_line = _locus_file_and_line(locus)
    blk_file, blk_line = _locus_file_and_line(str(door["blocker_locus"] or ""))
    anc_file, _ = _locus_file_and_line(str(door["anchor_locus"] or ""))

    if art_file and blk_file and art_file == blk_file:
        if blk_line == 0 or art_line == 0 or abs(art_line - blk_line) <= 80:
            modes.append("blocker_locus")
            best_score = max(best_score, 0.85)

    wanted_syms = {s.lower() for s in _parse_symbol_list(str(door["wanted_symbols_json"] or "[]"))}
    # Also include explicit file/symbol tokens mentioned in wishlist_query or missing_link_summary
    raw_wish = f"{door['wishlist_query']} {door['missing_link_summary']}"
    for p_tok in re.findall(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", raw_wish):
        wanted_syms.add(p_tok.lower().lstrip("./"))
        wanted_syms.add(p_tok.rsplit("/", 1)[-1].lower())

    overlap_syms = wanted_syms & code_symbols
    if not overlap_syms and wanted_syms and text_blob:
        low_blob = text_blob.lower()
        overlap_syms = {ws for ws in wanted_syms if len(ws) >= 4 and ws in low_blob}

    if overlap_syms:
        modes.append("symbol")
        best_score = max(best_score, 0.78)

    has_edges = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repomap_edges'").fetchone()
        is not None
    )
    if has_edges and art_file and "symbol" not in modes and "blocker_locus" not in modes:
        peer_files = [f for f in (blk_file, anc_file) if f and f != art_file]
        for pf in peer_files:
            edge = conn.execute(
                """
                SELECT symbol, weight FROM repomap_edges
                WHERE (src_file = ? AND dst_file = ?) OR (src_file = ? AND dst_file = ?)
                ORDER BY weight DESC LIMIT 1
                """,
                (art_file, pf, pf, art_file),
            ).fetchone()
            if edge is not None and float(edge["weight"] or 0.0) >= 0.35:
                # Require at least 1 shared domain token too so unrelated helpers in the same file don't over-fire.
                door_toks = _extract_domain_tokens(raw_wish)
                art_toks = _extract_domain_tokens(f"{locus} {text_blob}")
                if str(edge["symbol"]).lower() in (door_toks | wanted_syms) or len(door_toks & art_toks) >= 1:
                    modes.append("call_edge")
                    best_score = max(best_score, 0.68)
                    break

    # Mode 3: SQLite FTS5 BM25 + >= 2 Distinct Domain/Code Token Overlap
    did = str(door["door_id"])
    if did in fts_hit_ids:
        door_toks = _extract_domain_tokens(
            f"{door['wishlist_query']} {door['missing_link_summary']} {door['wanted_symbols_json']} {door['blocker_locus']}"
        )
        art_toks = _extract_domain_tokens(f"{locus} {text_blob}") | code_symbols
        if len(door_toks & art_toks) >= 2:
            modes.append("fts5")
            best_score = max(best_score, 0.68)

    return (round(best_score, 3), modes)


def _activate_door_ready(
    conn: sqlite3.Connection,
    door: sqlite3.Row | dict[str, Any],
    *,
    matched_entry: dict[str, Any],
    snapshot_id: str = "",
    trigger_cmd: str = "artifact.added",
) -> dict[str, Any]:
    did = str(door["door_id"])
    now_iso = utc_now_iso()
    try:
        prev_matches = json.loads(str(door["matched_by_json"] or "[]"))
        if not isinstance(prev_matches, list):
            prev_matches = []
    except json.JSONDecodeError:
        prev_matches = []
    prev_matches.append(matched_entry)

    eff_snap = str(door["snapshot_id"] or "") or snapshot_id
    resume_tid = str(door["resume_task_id"] or "")
    existing_task = (
        conn.execute("SELECT * FROM tasks WHERE task_id = ?", (resume_tid,)).fetchone()
        if resume_tid
        else None
    )

    held = _parse_symbol_list(str(door["held_ids_json"] or "[]"))
    step_preview = ",".join([*held, str(matched_entry["id"])]) or str(matched_entry["id"])
    snap_note = f" snapshot={eff_snap}" if eff_snap else ""
    jewel_note = f" -> jewel={door['jewel_id']}" if door["jewel_id"] else ""

    if existing_task is not None and str(existing_task["status"]) in ("open", "leased", "conditional_blocked"):
        conn.execute(
            """
            UPDATE tasks
            SET status = CASE WHEN status = 'conditional_blocked' THEN 'open' ELSE status END,
                priority = 'critical',
                salience_score = MAX(salience_score, 96),
                summary = ?,
                updated_at = ?
            WHERE task_id = ?
            """,
            (
                f"Open Door {did} WOKEN by {matched_entry['id']} ({','.join(matched_entry['modes'])}): "
                f"compose [{step_preview}] @ {door['anchor_locus']}{snap_note}{jewel_note}.",
                now_iso,
                resume_tid,
            ),
        )
        chain_tid = resume_tid
    else:
        chain_tid = new_id("task")
        sub = str(door["subsystem"] or infer_subsystem(str(door["anchor_locus"])))
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, kind, direction, title, subsystem, locus, priority, status,
                salience_score, door_id, summary, created_at, updated_at
            ) VALUES (?, 'chain', 'outside_in', ?, ?, ?, 'critical', 'open', 96, ?, ?, ?, ?)
            """,
            (
                chain_tid,
                f"Integrate woken Open Door {did} ({step_preview}) -> {door['anchor_locus']}",
                sub,
                str(door["anchor_locus"]),
                did,
                f"Open Door {did} woken via {','.join(matched_entry['modes'])}: "
                f"combine [{step_preview}]{snap_note}{jewel_note} and verify causal ablation (`ajar chain propose`).",
                now_iso,
                now_iso,
            ),
        )

    # Close any unleased `bridge` tasks for this door now that a concrete match arrived.
    conn.execute(
        """
        UPDATE tasks
        SET status = 'done', summary = 'Superseded: parked door woken by matching capability', updated_at = ?
        WHERE door_id = ? AND kind = 'bridge' AND status = 'open'
        """,
        (now_iso, did),
    )

    conn.execute(
        """
        UPDATE parked_doors
        SET status = 'ready',
            matched_by_json = ?,
            snapshot_id = ?,
            resume_task_id = ?,
            updated_at = ?
        WHERE door_id = ?
        """,
        (json.dumps(prev_matches), eff_snap, chain_tid, now_iso, did),
    )

    register_epistemic_hook(
        conn,
        hook_code="H4_TYPED_STATE_BRIDGE",
        trigger_cmd=trigger_cmd,
        source_entity_id=did,
        dedup_material=f"door_wake:{did}:{matched_entry['id']}",
        subsystem=str(door["subsystem"] or infer_subsystem(str(door["anchor_locus"]))),
        target_locus=str(door["anchor_locus"]),
        spawned_task_id=chain_tid,
        max_leases=2,
        directive_text=(
            f"Open Door {did} unlocked by {matched_entry['id']}@{matched_entry['locus']}; "
            f"probe{snap_note} and verify [{step_preview}] -> {door['anchor_locus']}."
        ),
        kill_rule=(
            f"STOP, mark dry, and keep door parked if state from {matched_entry['id']} "
            f"is sanitized prior to {door['anchor_locus']}."
        ),
    )
    log_event(
        conn,
        "planner",
        "door_woken",
        did,
        {
            "matched_id": matched_entry["id"],
            "modes": matched_entry["modes"],
            "score": matched_entry["score"],
            "chain_task_id": chain_tid,
            "snapshot_id": eff_snap,
        },
    )
    return {"door_id": did, "chain_task_id": chain_tid, "matched": matched_entry, "snapshot_id": eff_snap}


def wake_matching_doors_for_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    artifact_kind: str,
    locus: str,
    subsystem: str = "",
    text_blob: str = "",
    provides_tags: Sequence[str] = (),
    symbols: Sequence[str] = (),
    snapshot_id: str = "",
    trigger_cmd: str = "artifact.added",
) -> list[dict[str, Any]]:
    """Tri-modally check all non-chained Open Doors against a newly discovered artifact."""
    cand_doors = conn.execute(
        "SELECT * FROM parked_doors WHERE status IN ('parked', 'bridging', 'exhausted_locked') ORDER BY created_at ASC"
    ).fetchall()
    if not cand_doors:
        detect_percolated_multi_hop_paths(conn, enqueue_tasks=True)
        return []

    code_syms = _extract_artifact_code_symbols(
        conn,
        locus=locus,
        text_blob=text_blob,
        explicit_symbols=symbols,
    )
    domain_toks = list(_extract_domain_tokens(f"{locus} {text_blob}") | code_syms)
    fts_q = _safe_fts_or_query(domain_toks)
    fts_hit_ids: set[str] = set()
    if fts_q:
        try:
            frows = conn.execute(
                "SELECT door_id, bm25(door_fts) AS rank FROM door_fts WHERE door_fts MATCH ? LIMIT 16",
                (fts_q,),
            ).fetchall()
            for fr in frows:
                # In SQLite FTS5, bm25() returns negative values where more negative = stronger match.
                if abs(float(fr["rank"] or 0.0)) >= 0.01:
                    fts_hit_ids.add(str(fr["door_id"]))
        except sqlite3.OperationalError:
            fts_hit_ids = set()

    woken: list[dict[str, Any]] = []
    for d in cand_doors:
        score, modes = _score_door_match(
            conn,
            d,
            artifact_id=artifact_id,
            locus=locus,
            text_blob=text_blob,
            provides_tags=provides_tags,
            code_symbols=code_syms,
            fts_hit_ids=fts_hit_ids,
        )
        if score >= 0.65 and modes:
            woken.append(
                _activate_door_ready(
                    conn,
                    d,
                    matched_entry={
                        "id": artifact_id,
                        "kind": artifact_kind,
                        "locus": locus,
                        "subsystem": subsystem or infer_subsystem(locus),
                        "modes": modes,
                        "score": score,
                    },
                    snapshot_id=snapshot_id,
                    trigger_cmd=trigger_cmd,
                )
            )
    detect_percolated_multi_hop_paths(conn, enqueue_tasks=True)
    return woken


def _spawn_door_bridge_hunters(conn: sqlite3.Connection, door: sqlite3.Row | dict[str, Any]) -> list[str]:
    """Spawn at most `<= 2` bounded parallel `bridge` hunt tasks for an unmatched parked door."""
    max_att = max(0, min(2, int(door["max_bridge_attempts"] or 0)))
    cur_att = int(door["bridge_attempts"] or 0)
    budget = max_att - cur_att
    if budget <= 0:
        return []

    did = str(door["door_id"])
    anc_file, _ = _locus_file_and_line(str(door["anchor_locus"] or ""))
    blk_locus = str(door["blocker_locus"] or "").strip()
    blk_file, _ = _locus_file_and_line(blk_locus)

    candidates: list[tuple[str, str, str]] = []  # (locus, direction, note)
    if blk_locus and blk_file != anc_file:
        candidates.append((blk_locus, "inside_out", f"Audit upstream guard {blk_locus} blocking door {did}"))
    elif blk_locus:
        candidates.append((blk_locus, "inside_out", f"Search alternate callers bypassing guard {blk_locus}"))

    has_edges = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repomap_edges'").fetchone()
        is not None
    )
    if has_edges and anc_file and len(candidates) < budget:
        edge_rows = conn.execute(
            """
            SELECT src_file, dst_file, symbol, weight FROM repomap_edges
            WHERE src_file = ? OR dst_file = ?
            ORDER BY weight DESC LIMIT 6
            """,
            (anc_file, anc_file),
        ).fetchall()
        for er in edge_rows:
            peer = str(er["src_file"]) if str(er["dst_file"]) == anc_file else str(er["dst_file"])
            if peer and peer not in {anc_file, blk_file} and all(c[0].split(":", 1)[0] != peer for c in candidates):
                candidates.append(
                    (f"{peer}:1", "peer_symmetry", f"Search {peer} ({er['symbol']}) for missing link on {did}")
                )
                if len(candidates) >= budget:
                    break

    has_oracle = (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='oracle_fts'").fetchone()
        is not None
    )
    if has_oracle and len(candidates) < budget:
        fts_q = _safe_fts_or_query(
            list(_extract_domain_tokens(f"{door['wishlist_query']} {door['wanted_symbols_json']}"))
        )
        if fts_q:
            try:
                orows = conn.execute(
                    """
                    SELECT locus FROM oracle_fts
                    WHERE kind = 'reachability' AND oracle_fts MATCH ?
                    LIMIT 6
                    """,
                    (fts_q,),
                ).fetchall()
                for orow in orows:
                    oloc = str(orow["locus"] or "").strip()
                    ofile, _ = _locus_file_and_line(oloc)
                    if ofile and ofile not in {anc_file, blk_file} and all(c[0].split(":", 1)[0] != ofile for c in candidates):
                        candidates.append((oloc, "outside_in", f"Probe reachability candidate {oloc} for door {did}"))
                        if len(candidates) >= budget:
                            break
            except sqlite3.OperationalError:
                pass

    if not candidates and door["anchor_locus"]:
        candidates.append(
            (
                str(door["anchor_locus"]),
                "peer_symmetry",
                f"Search sibling callers/consumers for missing link on {did}",
            )
        )

    spawned: list[str] = []
    now_iso = utc_now_iso()
    for loc, direction, note in candidates[:budget]:
        tid = new_id("task")
        sub = infer_subsystem(loc)
        conn.execute(
            """
            INSERT INTO tasks(
                task_id, kind, direction, title, subsystem, locus, priority, status,
                salience_score, door_id, summary, created_at, updated_at
            ) VALUES (?, 'bridge', ?, ?, ?, ?, 'high', 'open', 78, ?, ?, ?, ?)
            """,
            (
                tid,
                direction,
                f"Bridge hunt for {did}: {str(door['missing_link_summary'])[:72]}",
                sub,
                loc,
                did,
                f"{note} | Missing: {str(door['missing_link_summary'])[:140]}",
                now_iso,
                now_iso,
            ),
        )
        register_epistemic_hook(
            conn,
            hook_code="H4_TYPED_STATE_BRIDGE",
            trigger_cmd="door.park",
            source_entity_id=did,
            dedup_material=f"bridge_hunt:{did}:{loc}",
            subsystem=sub,
            target_locus=loc,
            spawned_task_id=tid,
            max_leases=1,
            directive_text=(
                f"Missing-link hunt ({did}): check if {loc} emits ({str(door['missing_link_summary'])[:65]}) "
                f"to unlock {door['anchor_locus']}."
            ),
            kill_rule=(
                f"STOP and mark dry after auditing cone if no path breaks {blk_locus or 'guard'} "
                f"or satisfies {did}."
            ),
        )
        spawned.append(tid)

    if spawned:
        conn.execute(
            """
            UPDATE parked_doors
            SET status = 'bridging', bridge_attempts = bridge_attempts + ?, updated_at = ?
            WHERE door_id = ?
            """,
            (len(spawned), now_iso, did),
        )
    return spawned


def park_open_door(
    conn: sqlite3.Connection,
    *,
    anchor_locus: str,
    missing_link_summary: str,
    wishlist_query: str = "",
    jewel_id: str = "",
    direction: str = "sink_to_source",
    blocker_locus: str = "",
    subsystem: str = "",
    held_ids: str | Sequence[str] | None = None,
    snapshot_id: str = "",
    wanted_tags: str | Sequence[str] | None = None,
    wanted_symbols: str | Sequence[str] | None = None,
    max_bridge_attempts: int = 2,
    spawn_hunters: bool = True,
    worker_id: str = "worker",
) -> dict[str, Any]:
    """Suspend a deep chain subgoal ('Open Door'), retroactively check existing signals, or spawn <= 2 bridge hunters."""
    dir_clean = (direction or "sink_to_source").strip()
    if dir_clean not in VALID_DOOR_DIRECTIONS:
        raise AjarError(
            f"Unsupported door --direction {dir_clean!r}; choose from {', '.join(VALID_DOOR_DIRECTIONS)}.",
            EXIT_USER_ERROR,
        )
    if not anchor_locus.strip() or not missing_link_summary.strip():
        raise AjarError("`ajar door park` requires non-empty --anchor-locus and --missing.", EXIT_USER_ERROR)

    held_list = _parse_symbol_list(held_ids)
    w_tags = parse_tag_list(wanted_tags)
    w_syms = _parse_symbol_list(wanted_symbols)
    eff_snap = (snapshot_id or "").strip()

    # Auto-inherit snapshot_id from held finding/primitive if not explicitly passed.
    if not eff_snap and held_list:
        for hid in held_list:
            if hid.startswith("fnd-"):
                frow = conn.execute("SELECT snapshot_id FROM findings WHERE finding_id = ?", (hid,)).fetchone()
                if frow and frow["snapshot_id"]:
                    eff_snap = str(frow["snapshot_id"])
                    break
            elif hid.startswith("prim-"):
                prow = conn.execute("SELECT snapshot_id FROM primitives WHERE primitive_id = ?", (hid,)).fetchone()
                if prow and prow["snapshot_id"]:
                    eff_snap = str(prow["snapshot_id"])
                    break

    did = new_id("door")
    now_iso = utc_now_iso()
    sub = subsystem.strip() or infer_subsystem(anchor_locus)
    wish = scrub_text((wishlist_query or missing_link_summary).strip())
    miss = scrub_text(missing_link_summary.strip())

    conn.execute(
        """
        INSERT INTO parked_doors(
            door_id, jewel_id, direction, anchor_locus, blocker_locus, subsystem,
            held_ids_json, snapshot_id, missing_link_summary, wanted_tags_json,
            wanted_symbols_json, wishlist_query, status, matched_by_json,
            bridge_attempts, max_bridge_attempts, resume_task_id, created_by_worker,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'parked', '[]', 0, ?, '', ?, ?, ?)
        """,
        (
            did,
            (jewel_id or "").strip(),
            dir_clean,
            anchor_locus.strip(),
            blocker_locus.strip(),
            sub,
            json.dumps(held_list),
            eff_snap,
            miss,
            json.dumps(w_tags),
            json.dumps(w_syms),
            wish,
            max(0, min(4, int(max_bridge_attempts))),
            worker_id,
            now_iso,
            now_iso,
        ),
    )
    conn.execute(
        """
        INSERT INTO door_fts(door_id, anchor_locus, blocker_locus, wanted_symbols, missing_link_summary, wishlist_query)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (did, anchor_locus.strip(), blocker_locus.strip(), " ".join(w_syms), miss, wish),
    )

    door_row = conn.execute("SELECT * FROM parked_doors WHERE door_id = ?", (did,)).fetchone()

    # Retroactively check already-discovered active primitives, findings, and anomalies in `run.db`!
    existing_artifacts: list[dict[str, Any]] = []
    for p in conn.execute(
        "SELECT * FROM primitives WHERE status != 'dry' ORDER BY created_at ASC"
    ).fetchall():
        existing_artifacts.append(
            {
                "id": str(p["primitive_id"]),
                "kind": str(p["role"] if "role" in p.keys() else "capability"),
                "locus": str(p["locus"]),
                "subsystem": str(p["subsystem"]),
                "text": f"{p['kind']} {p['preconditions']} {p['postconditions']} {p['trusted_invariant'] if 'trusted_invariant' in p.keys() else ''}",
                "tags": parse_tag_list(p["provides_tags_json"]),
                "symbols": _parse_symbol_list(p["symbols_json"] if "symbols_json" in p.keys() else "[]"),
                "snapshot_id": str(p["snapshot_id"] if "snapshot_id" in p.keys() else ""),
            }
        )
    for f in conn.execute("SELECT * FROM findings ORDER BY created_at ASC").fetchall():
        existing_artifacts.append(
            {
                "id": str(f["finding_id"]),
                "kind": "finding",
                "locus": str(f["locus"]),
                "subsystem": infer_subsystem(str(f["locus"])),
                "text": f"{f['title']} {f['root_cause']}",
                "tags": parse_tag_list(f["provides_tags_json"] if "provides_tags_json" in f.keys() else "[]"),
                "symbols": [],
                "snapshot_id": str(f["snapshot_id"] if "snapshot_id" in f.keys() else ""),
            }
        )
    for a in conn.execute("SELECT * FROM anomalies WHERE status = 'unexplained' ORDER BY created_at ASC").fetchall():
        existing_artifacts.append(
            {
                "id": str(a["anomaly_id"]),
                "kind": "anomaly",
                "locus": str(a["locus"]),
                "subsystem": str(a["subsystem"]),
                "text": str(a["observation"]),
                "tags": [],
                "symbols": [],
                "snapshot_id": "",
            }
        )

    retro_wake: dict[str, Any] | None = None
    for art in existing_artifacts:
        if art["id"] in held_list:
            continue
        code_syms = _extract_artifact_code_symbols(
            conn,
            locus=art["locus"],
            text_blob=art["text"],
            explicit_symbols=art["symbols"],
        )
        fts_q = _safe_fts_or_query(list(_extract_domain_tokens(f"{art['locus']} {art['text']}") | code_syms))
        fts_hits: set[str] = set()
        if fts_q:
            try:
                fr = conn.execute(
                    "SELECT door_id FROM door_fts WHERE door_id = ? AND door_fts MATCH ?",
                    (did, fts_q),
                ).fetchone()
                if fr is not None:
                    fts_hits.add(did)
            except sqlite3.OperationalError:
                pass
        score, modes = _score_door_match(
            conn,
            door_row,
            artifact_id=art["id"],
            locus=art["locus"],
            text_blob=art["text"],
            provides_tags=art["tags"],
            code_symbols=code_syms,
            fts_hit_ids=fts_hits,
        )
        if score >= 0.65 and modes:
            retro_wake = _activate_door_ready(
                conn,
                door_row,
                matched_entry={
                    "id": art["id"],
                    "kind": art["kind"],
                    "locus": art["locus"],
                    "subsystem": art["subsystem"],
                    "modes": modes,
                    "score": score,
                },
                snapshot_id=art["snapshot_id"],
                trigger_cmd="door.park",
            )
            break

    spawned_hunters: list[str] = []
    if retro_wake is None and spawn_hunters:
        spawned_hunters = _spawn_door_bridge_hunters(conn, door_row)

    final_row = conn.execute("SELECT * FROM parked_doors WHERE door_id = ?", (did,)).fetchone()
    log_event(
        conn,
        worker_id,
        "door_parked",
        did,
        {
            "anchor_locus": anchor_locus.strip(),
            "blocker_locus": blocker_locus.strip(),
            "status": str(final_row["status"]),
            "spawned_bridge_tasks": spawned_hunters,
            "snapshot_id": str(final_row["snapshot_id"]),
        },
    )
    return {
        "door_id": did,
        "status": str(final_row["status"]),
        "snapshot_id": str(final_row["snapshot_id"]),
        "spawned_bridge_tasks": spawned_hunters,
        "retroactive_wakeup": retro_wake,
    }


def reconcile_door_bridge_tasks(conn: sqlite3.Connection) -> list[str]:
    """Transition `bridging` (or `ready`-closed-`dry`) doors to `exhausted_locked` once active tasks finish."""
    bridging = conn.execute("SELECT door_id, bridge_attempts, max_bridge_attempts FROM parked_doors WHERE status = 'bridging'").fetchall()
    exhausted: list[str] = []
    now_iso = utc_now_iso()
    for d in bridging:
        did = str(d["door_id"])
        active_b = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE door_id = ? AND kind = 'bridge' AND status IN ('open', 'leased', 'conditional_blocked')",
            (did,),
        ).fetchone()["c"]
        if int(active_b) == 0:
            conn.execute(
                "UPDATE parked_doors SET status = 'exhausted_locked', updated_at = ? WHERE door_id = ?",
                (now_iso, did),
            )
            exhausted.append(did)

    ready_rows = conn.execute(
        "SELECT door_id, resume_task_id FROM parked_doors WHERE status = 'ready' AND resume_task_id != ''"
    ).fetchall()
    for rd in ready_rows:
        trow = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (str(rd["resume_task_id"]),)).fetchone()
        if trow is not None and str(trow["status"]) == "dry":
            did = str(rd["door_id"])
            conn.execute(
                "UPDATE parked_doors SET status = 'exhausted_locked', updated_at = ? WHERE door_id = ?",
                (now_iso, did),
            )
            exhausted.append(did)
    return exhausted


def evaluate_precondition_realism(
    conn: sqlite3.Connection,
    *,
    poc_cmd: str,
    control_cmd: str,
    stdout: str = "",
    stderr: str = "",
    severity: str = "high",
    config_gate: str = "",
    step_ids: Sequence[str] = (),
    declared_steps: int | None = None,
    target_locus: str = "",
    explicit_jewel_id: str = "",
) -> dict[str, Any]:
    """Block self-override flags on victim invocations and classify `crown_jewel` vs `stepping_stone`."""
    poc_override = DELUSIONAL_EXEC_OVERRIDE_RE.search(poc_cmd or "")
    ctrl_override = DELUSIONAL_EXEC_OVERRIDE_RE.search(control_cmd or "")
    if poc_override and not ctrl_override:
        raise AjarError(
            f"precondition_realism_gate: `--poc-cmd` injects an execution/config override flag "
            f"({poc_override.group(0).strip()!r}) absent from `--control-cmd`. "
            "Trigger target sinks through repository, file, or wire state rather than caller-supplied execution flags.",
            EXIT_GATE_BLOCKED,
        )

    # Estimate interaction steps when not explicitly provided (count `;` / `&&` non-build invocations as upper bound hint).
    if declared_steps is not None:
        eff_steps = max(1, int(declared_steps))
    else:
        segments = [
            seg.strip()
            for seg in re.split(r"(?:&&|;|\|\|)", poc_cmd or "")
            if seg.strip() and not re.match(r"^(?:cd|mkdir|rm|cp|mv|cat|printf|echo|export|make|cargo\s+build|cc|gcc|clang|true)\b", seg.strip())
        ]
        eff_steps = max(1, len(segments)) if segments else 1

    nondefault_cfg = bool((config_gate or "").strip())
    visible_err = bool(VISIBLE_ERROR_NOISE_RE.search(stderr or ""))

    # Resolve candidate Crown Jewel (explicit -> door -> locus/symbol match).
    jewel_row: sqlite3.Row | None = None
    if explicit_jewel_id:
        jewel_row = conn.execute("SELECT * FROM crown_jewels WHERE jewel_id = ?", (explicit_jewel_id,)).fetchone()

    if jewel_row is None and step_ids:
        for sid in step_ids:
            drow = conn.execute(
                """
                SELECT jewel_id FROM parked_doors
                WHERE jewel_id != '' AND (held_ids_json LIKE '%' || ? || '%' OR matched_by_json LIKE '%' || ? || '%')
                ORDER BY updated_at DESC LIMIT 1
                """,
                (sid, sid),
            ).fetchone()
            if drow and drow["jewel_id"]:
                jewel_row = conn.execute(
                    "SELECT * FROM crown_jewels WHERE jewel_id = ?", (str(drow["jewel_id"]),)
                ).fetchone()
                if jewel_row is not None:
                    break

    if jewel_row is None:
        all_jewels = conn.execute("SELECT * FROM crown_jewels ORDER BY created_at ASC").fetchall()
        t_file, _ = _locus_file_and_line(target_locus)
        combined_low = f"{poc_cmd} {stdout} {stderr} {target_locus}".lower()
        for cj in all_jewels:
            cj_file, _ = _locus_file_and_line(str(cj["locus"]))
            cj_syms = [s.lower() for s in _parse_symbol_list(str(cj["symbols_json"] or "[]"))]
            if (t_file and cj_file and t_file == cj_file) or any(s in combined_low for s in cj_syms if len(s) >= 4):
                jewel_row = cj
                break

    sev_low = (severity or "high").lower()
    resolved_jewel_id = str(jewel_row["jewel_id"]) if jewel_row is not None else ""

    if jewel_row is not None:
        max_steps_ok = eff_steps <= int(jewel_row["max_interaction_steps"] or 1)
        cfg_ok = (not nondefault_cfg) or (not bool(jewel_row["require_default_config"]))
        err_ok = (not visible_err) or (not bool(jewel_row["forbid_visible_error"]))
        if max_steps_ok and cfg_ok and err_ok and sev_low in ("critical", "high"):
            tier = "crown_jewel"
        elif sev_low in ("critical", "high") and cfg_ok:
            tier = "stepping_stone"
        else:
            tier = "stepping_stone"
    else:
        # Without explicit crown_jewels rows, an un-gated 1-step critical chain with clean stderr qualifies as high_impact;
        # crown_jewel requires either matching a crown_jewels sink or an un-gated critical multi-step chain.
        if sev_low == "critical" and len(step_ids) >= 2 and not nondefault_cfg and not visible_err:
            tier = "crown_jewel"
        elif sev_low in ("critical", "high") and not nondefault_cfg:
            tier = "high_impact" if eff_steps == 1 and not visible_err else "stepping_stone"
        else:
            tier = "stepping_stone"

    return {
        "realism_tier": tier,
        "jewel_id": resolved_jewel_id,
        "interaction_steps": eff_steps,
        "requires_nondefault_config": nondefault_cfg,
        "visible_error_before_impact": visible_err,
    }


def mark_chain_doors_and_jewels_resolved(
    conn: sqlite3.Connection,
    *,
    chain_id: str,
    step_ids: Sequence[str],
    door_id: str = "",
    jewel_id: str = "",
    realism_tier: str = "stepping_stone",
) -> list[str]:
    """Mark woken/matching Open Doors `chained` and Crown Jewels `reached` when a verified chain lands."""
    now_iso = utc_now_iso()
    resolved_doors: list[str] = []
    step_set = set(step_ids)

    candidates = conn.execute(
        "SELECT * FROM parked_doors WHERE status IN ('ready', 'parked', 'bridging')"
    ).fetchall()
    for d in candidates:
        did = str(d["door_id"])
        is_match = bool(door_id and did == door_id)
        if not is_match and step_set:
            held = set(_parse_symbol_list(str(d["held_ids_json"] or "[]")))
            try:
                m_entries = json.loads(str(d["matched_by_json"] or "[]"))
            except json.JSONDecodeError:
                m_entries = []
            matched_ids = {str(m.get("id")) for m in m_entries if isinstance(m, dict) and m.get("id")}
            if held and matched_ids and (held & step_set) and (matched_ids & step_set):
                is_match = True
            elif held and not matched_ids and held.issubset(step_set) and len(step_set) >= 2:
                is_match = True
        if is_match:
            conn.execute(
                "UPDATE parked_doors SET status = 'chained', updated_at = ? WHERE door_id = ?",
                (now_iso, did),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = 'done', summary = ?, updated_at = ?
                WHERE door_id = ? AND kind IN ('chain', 'bridge') AND status IN ('open', 'leased')
                """,
                (f"Resolved by verified chain {chain_id}", now_iso, did),
            )
            resolved_doors.append(did)
            if not jewel_id and d["jewel_id"]:
                jewel_id = str(d["jewel_id"])

    if realism_tier == "crown_jewel" and jewel_id:
        conn.execute(
            """
            UPDATE crown_jewels
            SET status = 'reached', reached_by_id = ?, updated_at = ?
            WHERE jewel_id = ?
            """,
            (chain_id, now_iso, jewel_id),
        )
    return resolved_doors


def detect_percolated_multi_hop_paths(
    conn: sqlite3.Connection,
    *,
    max_hops: int = 10,
    enqueue_tasks: bool = False,
) -> dict[str, Any]:
    """Transitive $N$-hop graph percolation ('7 CVSS-5 annoyances + 8th middle unicorn = 10.0 chain').

    Builds the directed Weird-Machine transition graph over all active `primitives`
    (`capability` + `trust_gadget`), confirmed `findings`, and `crown_jewels`:
    - `source_roots`: unguarded findings/primitives with zero unmet `requires_tags`
      (reachable from untrusted input even when standalone severity is low);
    - `edges (u -> v)`: tag satisfaction (`provides_tags(u) & requires_tags(v)`),
      guard-locus unlock (`u.locus` hits `v.guarded_by_locus`), or explicit symbol
      handoff (`u.symbols & v.requires_symbols`);
    - `percolated_paths`: complete `2..max_hops` chains from a `source_root` into a
      `crown_jewel` (or high-impact guarded sink) that snap together as soon as a
      middle link lands;
    - `unicorn_gaps`: `(forward_tip, backward_entry)` pairs separated by a single
      missing intermediate transition so hunters see which middle link completes a
      deep multi-step chain.
    """
    from collections import deque

    nodes: dict[str, dict[str, Any]] = {}
    for p in conn.execute("SELECT * FROM primitives WHERE status != 'dry' ORDER BY created_at ASC").fetchall():
        pid = str(p["primitive_id"])
        prov = set(parse_tag_list(p["provides_tags_json"]))
        req = set(parse_tag_list(p["requires_tags_json"]))
        syms = {s.lower() for s in _parse_symbol_list(p["symbols_json"] if "symbols_json" in p.keys() else "[]")}
        g_loc = str(p["guarded_by_locus"] or "").strip()
        nodes[pid] = {
            "id": pid,
            "kind": str(p["role"] if "role" in p.keys() else "capability"),
            "locus": str(p["locus"]),
            "subsystem": str(p["subsystem"]),
            "provides": prov,
            "requires": req,
            "guarded_by": g_loc,
            "symbols": syms,
            "is_source_root": (len(req) == 0 and not g_loc and str(p["role"] if "role" in p.keys() else "capability") == "capability"),
            "is_sink": False,
            "jewel_id": "",
        }

    for f in conn.execute("SELECT * FROM findings ORDER BY created_at ASC").fetchall():
        fid = str(f["finding_id"])
        prov = set(parse_tag_list(f["provides_tags_json"] if "provides_tags_json" in f.keys() else "[]"))
        nodes[fid] = {
            "id": fid,
            "kind": "finding",
            "locus": str(f["locus"]),
            "subsystem": infer_subsystem(str(f["locus"])),
            "provides": prov,
            "requires": set(),
            "guarded_by": "",
            "symbols": _extract_artifact_code_symbols(conn, locus=str(f["locus"]), text_blob=f"{f['title']} {f['root_cause']}"),
            "is_source_root": True,
            "is_sink": False,
            "jewel_id": "",
        }

    jewels = list_crown_jewels(conn)
    for cj in jewels:
        jid = str(cj["jewel_id"])
        cj_syms = {s.lower() for s in _parse_symbol_list(cj.get("symbols_json") or "[]")}
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
        }

    # Also treat guarded primitives / requires-tag surfaces as terminal sinks when no crown_jewels exist yet.
    if not jewels:
        for s in conn.execute("SELECT * FROM surfaces ORDER BY created_at ASC").fetchall():
            rtags = set(parse_tag_list(s["requires_tags_json"] if "requires_tags_json" in s.keys() else "[]"))
            if rtags:
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
                }

    out_adj: dict[str, list[str]] = {nid: [] for nid in nodes}
    in_adj: dict[str, list[str]] = {nid: [] for nid in nodes}

    node_list = list(nodes.values())
    for u in node_list:
        uid = u["id"]
        if u["is_sink"]:
            continue
        u_file, u_line = _locus_file_and_line(u["locus"])
        for v in node_list:
            vid = v["id"]
            if uid == vid or v["kind"] == "finding":
                continue
            connected = False
            if u["provides"] and v["requires"] and (u["provides"] & v["requires"]):
                connected = True
            elif v["guarded_by"]:
                g_file, g_line = _locus_file_and_line(v["guarded_by"])
                if u_file and g_file and u_file == g_file and (g_line == 0 or u_line == 0 or abs(u_line - g_line) <= 80):
                    connected = True
            elif v["kind"] == "crown_jewel":
                v_file, _ = _locus_file_and_line(v["locus"])
                if (u_file and v_file and u_file == v_file) or (u["symbols"] and v["symbols"] and (u["symbols"] & v["symbols"])):
                    connected = True
            if connected and vid not in out_adj[uid]:
                out_adj[uid].append(vid)
                in_adj[vid].append(uid)

    # Also wire woken `ready` doors as explicit directed bridges (`held -> matched -> jewel/anchor`).
    for rd in conn.execute("SELECT * FROM parked_doors WHERE status = 'ready'").fetchall():
        held = [h for h in _parse_symbol_list(str(rd["held_ids_json"] or "[]")) if h in nodes]
        try:
            matches = json.loads(str(rd["matched_by_json"] or "[]"))
        except json.JSONDecodeError:
            matches = []
        mids = [str(m.get("id")) for m in matches if isinstance(m, dict) and str(m.get("id")) in nodes]
        jid = str(rd["jewel_id"] or "")
        for h in held:
            for m in mids:
                if h != m and m not in out_adj[h]:
                    out_adj[h].append(m)
                    in_adj[m].append(h)
        if jid in nodes:
            for tail in (mids or held):
                if tail != jid and jid not in out_adj[tail]:
                    out_adj[tail].append(jid)
                    in_adj[jid].append(tail)

    # Forward BFS from all `source_roots` (`<= max_hops`).
    fwd_paths: dict[str, list[str]] = {}
    q_fwd: deque[str] = deque()
    for nid, nd in nodes.items():
        if nd["is_source_root"]:
            fwd_paths[nid] = [nid]
            q_fwd.append(nid)
    while q_fwd:
        cur = q_fwd.popleft()
        cur_path = fwd_paths[cur]
        if len(cur_path) >= max_hops:
            continue
        for nxt in out_adj.get(cur, ()):
            if nxt not in fwd_paths and nxt not in cur_path:
                fwd_paths[nxt] = [*cur_path, nxt]
                if not nodes[nxt]["is_sink"]:
                    q_fwd.append(nxt)

    # Backward BFS from all `is_sink` nodes (`<= max_hops`).
    bwd_paths: dict[str, list[str]] = {}
    q_bwd: deque[str] = deque()
    for nid, nd in nodes.items():
        if nd["is_sink"]:
            bwd_paths[nid] = [nid]
            q_bwd.append(nid)
    while q_bwd:
        cur = q_bwd.popleft()
        cur_suffix = bwd_paths[cur]
        if len(cur_suffix) >= max_hops:
            continue
        for prev in in_adj.get(cur, ()):
            if prev not in bwd_paths and prev not in cur_suffix:
                bwd_paths[prev] = [prev, *cur_suffix]
                q_bwd.append(prev)

    percolated: list[dict[str, Any]] = []
    seen_step_tuples: set[tuple[str, ...]] = set()
    for sink_id, nd in nodes.items():
        if not nd["is_sink"] or sink_id not in fwd_paths:
            continue
        full_chain = fwd_paths[sink_id]
        step_ids = [x for x in full_chain if not nodes[x]["is_sink"]]
        # Require at least 2 capability/finding/gadget steps with >= 1 invariant-breaking source/capability.
        if len(step_ids) >= 2 and tuple(step_ids) not in seen_step_tuples:
            seen_step_tuples.add(tuple(step_ids))
            percolated.append(
                {
                    "sink_id": sink_id,
                    "sink_locus": nd["locus"],
                    "jewel_id": nd["jewel_id"],
                    "hop_count": len(step_ids),
                    "step_ids": step_ids,
                }
            )

    # Identify 1-link "Unicorn Gaps": deepest forward tips `u` not yet reaching a sink vs
    # deepest backward suffix entries `v` whose unmet `requires` or `guarded_by` is 1 link away!
    unicorn_gaps: list[dict[str, Any]] = []
    fwd_tips = [
        nid
        for nid, path in fwd_paths.items()
        if not nodes[nid]["is_sink"]
        and nid not in bwd_paths
        and not any(
            nxt in fwd_paths and len(fwd_paths[nxt]) > len(path)
            for nxt in out_adj.get(nid, ())
        )
    ]
    bwd_entries = [
        nid
        for nid, suffix in bwd_paths.items()
        if nid not in fwd_paths and (nodes[nid]["requires"] or nodes[nid]["guarded_by"])
    ]
    for tip_id in fwd_tips[:6]:
        for entry_id in bwd_entries[:6]:
            if tip_id == entry_id:
                continue
            prefix = fwd_paths[tip_id]
            suffix = bwd_paths[entry_id]
            if len(prefix) + len(suffix) > max_hops + 1:
                continue
            unmet = sorted(nodes[entry_id]["requires"] - nodes[tip_id]["provides"])
            unicorn_gaps.append(
                {
                    "forward_prefix": prefix,
                    "forward_tip_id": tip_id,
                    "forward_tip_locus": nodes[tip_id]["locus"],
                    "forward_provides": sorted(nodes[tip_id]["provides"]),
                    "backward_entry_id": entry_id,
                    "backward_entry_locus": nodes[entry_id]["locus"],
                    "backward_guard": nodes[entry_id]["guarded_by"],
                    "unmet_requires": unmet,
                    "backward_suffix": suffix,
                    "total_chain_hops_if_bridged": len(prefix) + 1 + len([x for x in suffix if not nodes[x]["is_sink"]]),
                }
            )
    unicorn_gaps.sort(
        key=lambda g: (
            -int(g["total_chain_hops_if_bridged"]),
            -len(g["backward_suffix"]),
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
            already_verified = conn.execute(
                "SELECT 1 FROM chains WHERE verified = 1 AND step_ids_json = ? LIMIT 1",
                (json.dumps(pc["step_ids"]),),
            ).fetchone()
            if not exists and not already_verified:
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
                        f"Percolated multi-hop path [{step_csv}] -> {pc['sink_id']}@{pc['sink_locus']}; prove end-to-end with `ajar chain propose`.",
                        now_iso,
                        now_iso,
                    ),
                )
                spawned_tasks.append(tid)

    return {
        "percolated_paths": percolated,
        "unicorn_gaps": unicorn_gaps[:8],
        "forward_reachable_count": len(fwd_paths),
        "backward_cone_count": len(bwd_paths),
        "spawned_chain_tasks": spawned_tasks,
    }


def compute_chain_frontier(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compile the complete Crown-Jewel, Open-Door, Percolation, Snapshot, and Capability-Bridge frontier."""
    from ajar.epistemic_hooks import detect_capability_bridges

    reconcile_door_bridge_tasks(conn)
    jewels = list_crown_jewels(conn)
    doors = [dict(r) for r in conn.execute("SELECT * FROM parked_doors ORDER BY updated_at DESC").fetchall()]
    snaps = [dict(r) for r in conn.execute("SELECT * FROM repro_snapshots ORDER BY created_at DESC").fetchall()]
    bridges = detect_capability_bridges(conn, limit=12)
    percolation = detect_percolated_multi_hop_paths(conn, enqueue_tasks=False)

    by_status: dict[str, list[dict[str, Any]]] = {
        "ready": [],
        "bridging": [],
        "parked": [],
        "chained": [],
        "exhausted_locked": [],
    }
    for d in doors:
        by_status.setdefault(str(d["status"]), []).append(d)

    ready_candidates: list[dict[str, Any]] = []
    for rd in by_status.get("ready", []):
        held = _parse_symbol_list(str(rd.get("held_ids_json") or "[]"))
        try:
            matches = json.loads(str(rd.get("matched_by_json") or "[]"))
        except json.JSONDecodeError:
            matches = []
        matched_ids = [str(m.get("id")) for m in matches if isinstance(m, dict) and m.get("id")]
        ready_candidates.append(
            {
                "door_id": rd["door_id"],
                "jewel_id": rd["jewel_id"],
                "anchor_locus": rd["anchor_locus"],
                "snapshot_id": rd["snapshot_id"],
                "step_candidates": [*held, *[m for m in matched_ids if m not in held]],
                "resume_task_id": rd["resume_task_id"],
                "missing_link_summary": rd["missing_link_summary"],
            }
        )

    return {
        "crown_jewels": jewels,
        "ready_candidates": ready_candidates,
        "percolated_paths": percolation["percolated_paths"],
        "unicorn_gaps": percolation["unicorn_gaps"],
        "counts": {
            "crown_jewels_total": len(jewels),
            "crown_jewels_reached": sum(1 for j in jewels if j["status"] == "reached"),
            "ready_doors": len(by_status.get("ready", [])),
            "bridging_doors": len(by_status.get("bridging", [])),
            "parked_doors": len(by_status.get("parked", [])),
            "chained_doors": len(by_status.get("chained", [])),
            "exhausted_doors": len(by_status.get("exhausted_locked", [])),
            "percolated_paths": len(percolation["percolated_paths"]),
            "unicorn_gaps": len(percolation["unicorn_gaps"]),
            "snapshots": len(snaps),
            "capability_bridges": len(bridges),
        },
        "doors_by_status": by_status,
        "capability_bridges": bridges,
        "snapshots": snaps,
    }
