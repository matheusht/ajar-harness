"""Argument parser builder and LRU-cached entrypoint parser for the `ajar` CLI."""

from __future__ import annotations

import argparse
import functools

from ajar import (
    EXIT_OK,
    __version__,
)
from ajar.chain_planner import (
    VALID_DOOR_DIRECTIONS,
    VALID_IMPACT_CLASSES,
)
from ajar.cli.claims import (
    cmd_chain,
    cmd_claim,
    cmd_finding,
    cmd_patch,
    cmd_repro,
)
from ajar.cli.hunt import (
    cmd_anomaly,
    cmd_binding,
    cmd_coverage,
    cmd_door,
    cmd_driver,
    cmd_primitive,
    cmd_surface,
    cmd_task,
)
from ajar.cli.ops import (
    cmd_brief,
    cmd_catalog,
    cmd_context,
    cmd_doctor,
    cmd_economics,
    cmd_epistemic_hooks,
    cmd_export_graph,
    cmd_finish,
    cmd_gate_check,
    cmd_hook,
    cmd_init,
    cmd_lead,
    cmd_ledger,
    cmd_loop,
    cmd_map,
    cmd_phase,
    cmd_pulse,
    cmd_quote,
    cmd_ref_query,
    cmd_reopen,
    cmd_report,
    cmd_run,
    cmd_spend,
    cmd_status,
    cmd_steer,
    cmd_swarm,
    cmd_threat_model,
    cmd_touch,
)
from ajar.graph import (
    VALID_GRAPH_SCHEMAS,
    VALID_GRAPH_VISIBILITIES,
)
from ajar.mcp import serve_mcp_stdio
from ajar.swarm import (
    ENV_BLOCKER_KINDS,
    VALID_FALLBACK_REASONS,
    VALID_SWARM_STAGES,
    WIRE_PROFILE_LADDER,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ajar",
        description="Ajar: verification-backed security engine for Code, Fixes, Security reviews, and Supply chain.",
    )
    p.add_argument("--version", action="version", version=f"ajar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # doctor
    p_doc = sub.add_parser("doctor", help="Check local toolchains, sandbox, disk headroom, optional target liveness, and run health.")
    p_doc.add_argument("--target", help="Optional local path, `owner/repo` slug, or git URL to verify freshness and scope readiness.")
    p_doc.add_argument("--subdir", default="", help="Optional in-scope subdirectory inside `--target` monorepo.")
    p_doc.add_argument("--ref", default="", help="Optional remote branch, tag, or commit SHA to verify instead of default_branch.")
    p_doc.add_argument("--peer", action="append", help="Optional sibling reference/contract checkout path to verify.")
    p_doc.add_argument("--max-age-days", type=int, default=90, help="Maximum allowed git HEAD age in days (default: 90).")
    p_doc.add_argument("--no-remote", action="store_true", help="Skip live remote `gh api` / `git ls-remote` upstream checks.")
    p_doc.add_argument("--run", help="Optional run ID to diagnose SQLite integrity, stale leases, and repro slot health.")
    p_doc.add_argument("--prune-slots", action="store_true", help="With `--run`, safely remove unlocked `repro/slot-*` worktree directories.")
    p_doc.add_argument(
        "--failures",
        action="store_true",
        help="With `--run` (or `$AJAR_RUN_ID`), aggregate `repro/failures/*.json` receipts and `swarm_dispatches` fallback telemetry.",
    )
    p_doc.add_argument("--json", action="store_true", default=True)
    p_doc.set_defaults(func=cmd_doctor)

    # quote
    p_qt = sub.add_parser("quote", help="Preview deterministic Code LOC quote and 35%% COGS cap before running.")
    p_qt.add_argument("target", help="Target repository directory or file path.")
    p_qt.add_argument("--diff", help="Optional git diff range (`base..head`) for PR/commit differential quoting.")
    p_qt.add_argument("--json", action="store_true", default=True)
    p_qt.set_defaults(func=cmd_quote)

    stopping_choices = ("exhaustive-high", "first-verified-high", "crown-jewel")
    phase_choices = ("hunt", "remediate", "full")

    # init
    p_init = sub.add_parser("init", help="Initialize a new verification run in --envelope or --in-place mode.")
    p_init.add_argument("target", help="Target directory, binary path, or URL.")
    p_init.add_argument("--mode", choices=("source", "binary", "live"), default="source")
    grp_ws = p_init.add_mutually_exclusive_group()
    grp_ws.add_argument("--envelope", action="store_true", default=True, help="Create isolated workspace with read-only target snapshot (default).")
    grp_ws.add_argument("--in-place", action="store_true", help="Write zero files into target directory.")
    p_init.add_argument("--goal", default="Identify, falsify, and reproduce high-severity software vulnerabilities.")
    p_init.add_argument("--brief-file", help="Optional Markdown campaign brief persisted for the Lead Orchestrator (`brief.md`, omitted from worker contexts).")
    p_init.add_argument("--until", choices=stopping_choices, default="exhaustive-high")
    p_init.add_argument("--stopping", dest="until", choices=stopping_choices, help="Alias for --until (`exhaustive-high`, `first-verified-high`, `crown-jewel`).")
    p_init.add_argument("--phase", choices=phase_choices, default="hunt", help="Campaign phase (`hunt` defers 9-arm `patch verify` until `remediate`).")
    p_init.add_argument("--budget", type=float, default=None, help="Explicit COGS cap override in USD (defaults to 0.35 * Code quote).")
    p_init.add_argument("--cogs-cap", dest="budget", type=float, help="Alias for --budget explicit COGS cap override in USD.")
    p_init.add_argument("--uncapped", action="store_true", help="Disable finite COGS budget caps and 25%%/80%% budget throttles (`uncapped_research`).")
    p_init.add_argument("--diff", help="Optional git diff range (`base..head`) for PR differential Code runs.")
    p_init.add_argument("--parent-run", help="Optional baseline/parent run ID to carry forward kept findings and guards.")
    p_init.add_argument("--allow-host", action="append", help="Allowed live target hostname.")
    p_init.add_argument("--allow-live-requests", action="store_true")
    p_init.add_argument("--allow-live-mutations", action="store_true")
    p_init.add_argument("--allow-historical-target", action="store_true", help="Allow initializing on archived or >90-day-old historical snapshots.")
    p_init.add_argument("--run-id", help="Optional explicit run identifier.")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(func=cmd_init)

    # phase
    p_phs = sub.add_parser("phase", help="Inspect or advance campaign phase (`hunt` -> `remediate` -> `full`).")
    phs_sub = p_phs.add_subparsers(dest="phase_cmd", required=True)
    pph_s = phs_sub.add_parser("show")
    pph_s.add_argument("--run")
    pph_a = phs_sub.add_parser("advance")
    pph_a.add_argument("--to", choices=phase_choices, required=True)
    pph_a.add_argument("--notes", default="")
    pph_a.add_argument("--force", action="store_true", help="Operator override to advance phase while hunt/chain frontier remains active (requires `--notes`).")
    pph_a.add_argument("--run")
    p_phs.set_defaults(func=cmd_phase)

    # brief
    p_brf = sub.add_parser("brief", help="Read or update the Lead Orchestrator campaign brief (`brief.md`) without bloating worker task prefixes.")
    p_brf.add_argument("--set-file", help="Path to Markdown campaign brief file to store in the run directory.")
    p_brf.add_argument("--run", help="Run ID.")
    p_brf.add_argument("--json", action="store_true")
    p_brf.set_defaults(func=cmd_brief)

    # status
    p_stat = sub.add_parser("status", help="Inspect current run progress, gates, and spend.")
    p_stat.add_argument("--run", help="Run ID.")
    p_stat.add_argument("--json", action="store_true", default=True)
    p_stat.set_defaults(func=cmd_status)

    # context
    p_ctx = sub.add_parser("context", help="Render prefix-stable < 4 KB certified context frame for a task.")
    p_ctx.add_argument("--task", required=True)
    p_ctx.add_argument("--run")
    p_ctx.add_argument("--json", action="store_true")
    p_ctx.set_defaults(func=cmd_context)

    # pulse
    p_pls = sub.add_parser("pulse", help="Expire stale leases, check certified bindings, and rescore salience.")
    p_pls.add_argument("--run")
    p_pls.add_argument("--json", action="store_true", default=True)
    p_pls.set_defaults(func=cmd_pulse)

    # map
    p_map = sub.add_parser("map", help="Build Personalized PageRank repository symbol map.")
    p_map.add_argument("--focus-file", action="append")
    p_map.add_argument("--focus-symbol", action="append")
    p_map.add_argument("--budget-tokens", type=int, default=1500)
    p_map.add_argument("--slice-cap", type=int, default=15000, help="Soft target LoC per cohesive subsystem call cone.")
    p_map.add_argument("--unvisited", action="store_true", help="Emit only call slices containing files not yet covered in `coverage_spans` or closed `tasks`.")
    p_map.add_argument("--run")
    p_map.add_argument("--json", action="store_true")
    p_map.set_defaults(func=cmd_map)

    # ref query + precedent search alias
    p_ref = sub.add_parser("ref", help="Query FTS5 index across intent, reachability, and precedent.")
    ref_sub = p_ref.add_subparsers(dest="ref_cmd", required=True)
    p_rq = ref_sub.add_parser("query")
    p_rq.add_argument("--kind", choices=("intent", "reachability", "precedent", "all"), default="all")
    p_rq.add_argument("query")
    p_rq.add_argument("--limit", type=int, default=10)
    p_rq.add_argument("--run")
    p_rq.set_defaults(func=cmd_ref_query)

    p_prec = sub.add_parser("precedent", help="Search curated CVE, chain, and false-positive precedent corpora.")
    prec_sub = p_prec.add_subparsers(dest="prec_cmd", required=True)
    p_ps = prec_sub.add_parser("search")
    p_ps.add_argument("query")
    p_ps.add_argument("--limit", type=int, default=10)
    p_ps.add_argument("--run")
    p_ps.set_defaults(func=cmd_ref_query, kind="precedent")

    # threat-model
    p_tm = sub.add_parser("threat-model", help="Synthesize initial Threat Model and track adaptive trust assumptions.")
    tm_sub = p_tm.add_subparsers(dest="tm_cmd", required=True)
    ptm_set = tm_sub.add_parser("set", help="Set or revise attacker principals, crown-jewel assets, and consumer tiers.")
    ptm_set.add_argument("--principals", required=True, help="Comma-separated untrusted/semi-trusted attacker principals.")
    ptm_set.add_argument("--assets", required=True, help="Comma-separated protected assets or impact classes.")
    ptm_set.add_argument("--consumer-tiers", default="", help="Comma-separated downstream caller tiers (`CLI,Gitaly,guest-VM`).")
    ptm_set.add_argument("--summary", default="", help="Concise architectural threat-model summary.")
    ptm_set.add_argument("--json", action="store_true")
    ptm_set.add_argument("--run")
    ptm_show = tm_sub.add_parser("show", help="Inspect current Threat Model revision and trust assumptions.")
    ptm_show.add_argument("--json", action="store_true")
    ptm_show.add_argument("--run")
    ptm_add = tm_sub.add_parser("assumption-add", help="Register a falsifiable architectural trust assumption.")
    ptm_add.add_argument("--subsystem", default="")
    ptm_add.add_argument("--trust-boundary", default="")
    ptm_add.add_argument("--assumption", required=True)
    ptm_add.add_argument("--check-locus", default="")
    ptm_add.add_argument("--invalidated-by-tags", default="", help="Comma-separated capability tags (`ns:name`) that auto-violate this assumption.")
    ptm_add.add_argument("--dependent-surface", default="", help="Surface ID whose priority escalates if this assumption breaks.")
    ptm_add.add_argument("--escalate-priority", choices=("critical", "high"), default="critical")
    ptm_add.add_argument("--json", action="store_true")
    ptm_add.add_argument("--run")
    ptm_lst = tm_sub.add_parser("assumption-list")
    ptm_lst.add_argument("--json", action="store_true")
    ptm_lst.add_argument("--run")
    ptm_ver = tm_sub.add_parser("verify", help="Mark an assumption verified in code (`verified_holds`).")
    ptm_ver.add_argument("assumption_id")
    ptm_ver.add_argument("--locus", required=True)
    ptm_ver.add_argument("--notes", default="")
    ptm_ver.add_argument("--json", action="store_true")
    ptm_ver.add_argument("--run")
    ptm_inv = tm_sub.add_parser("invalidate", help="Violate a broken assumption and adaptively re-score surfaces/tasks.")
    ptm_inv.add_argument("assumption_id")
    ptm_inv.add_argument("--evidence", required=True, help="Primitive ID, Finding ID, or file:line proving the assumption failed.")
    ptm_inv.add_argument("--notes", default="")
    ptm_inv.add_argument("--json", action="store_true")
    ptm_inv.add_argument("--run")
    p_tm.set_defaults(func=cmd_threat_model)

    # door (`Crown Jewels` + suspended `Open Doors`)
    p_dr = sub.add_parser("door", help="Manage Crown-Jewel terminal sinks and suspended Open-Door chain subgoals.")
    dr_sub = p_dr.add_subparsers(dest="door_cmd", required=True)
    pdr_ja = dr_sub.add_parser("jewel-add", help="Register a target-derived Crown-Jewel terminal sink.")
    pdr_ja.add_argument("--name", required=True)
    pdr_ja.add_argument("--locus", required=True)
    pdr_ja.add_argument("--subsystem", default="")
    pdr_ja.add_argument("--impact-class", choices=VALID_IMPACT_CLASSES, default="rce")
    pdr_ja.add_argument("--symbols", default="", help="Comma-separated sink function/symbol/tag identifiers.")
    pdr_ja.add_argument("--max-steps", type=int, default=1, help="Max victim interaction steps for Crown-Jewel realism.")
    pdr_ja.add_argument("--allow-nondefault-config", action="store_true")
    pdr_ja.add_argument("--allow-visible-error", action="store_true")
    pdr_ja.add_argument("--worker", default="mapper")
    pdr_ja.add_argument("--run")
    pdr_jl = dr_sub.add_parser("jewel-list", help="List Crown-Jewel terminal sinks.")
    pdr_jl.add_argument("--run")
    pdr_pk = dr_sub.add_parser("park", help="Park a blocked deep chain lead as an Open Door and spawn bounded bridge hunters.")
    pdr_pk.add_argument("--anchor-locus", required=True, help="Target sink or partial-chain locus (`file:lines`).")
    pdr_pk.add_argument("--missing", required=True, help="Concise description of the missing upstream/downstream link.")
    pdr_pk.add_argument("--wishlist", default="", help="Optional lexical/symbol FTS5 query describing what unlocks this door.")
    pdr_pk.add_argument("--jewel", default="", help="Optional Crown-Jewel ID (`cjw-...`).")
    pdr_pk.add_argument("--direction", choices=VALID_DOOR_DIRECTIONS, default="sink_to_source")
    pdr_pk.add_argument("--blocker-locus", default="", help="Upstream guard locus (`file:lines`) currently blocking the door.")
    pdr_pk.add_argument("--subsystem", default="")
    pdr_pk.add_argument("--held-ids", default="", help="Comma-separated `fnd-*` / `prim-*` IDs already held on this chain.")
    pdr_pk.add_argument("--snapshot", default="", help="Optional `snp-*` post-state snapshot ID.")
    pdr_pk.add_argument("--wanted-tags", default="", help="Comma-separated capability tags (`ns:name`) that unlock this door.")
    pdr_pk.add_argument("--wanted-symbols", default="", help="Comma-separated code symbols or file paths that unlock this door.")
    pdr_pk.add_argument("--max-bridge-attempts", type=int, default=2)
    pdr_pk.add_argument("--no-spawn-hunters", action="store_true")
    pdr_pk.add_argument("--worker", default="worker")
    pdr_pk.add_argument("--run")
    pdr_ls = dr_sub.add_parser("list", help="List Open Doors (`ready`, `bridging`, `parked`, `chained`, `exhausted_locked`).")
    pdr_ls.add_argument("--status", choices=("parked", "bridging", "ready", "chained", "exhausted_locked"))
    pdr_ls.add_argument("--run")
    p_dr.set_defaults(func=cmd_door)

    # surface
    p_surf = sub.add_parser("surface", help="Manage target entrypoints and trust-boundary surfaces.")
    surf_sub = p_surf.add_subparsers(dest="surface_cmd", required=True)
    ps_add = surf_sub.add_parser("add")
    ps_add.add_argument("--name", required=True)
    ps_add.add_argument("--kind", required=True)
    ps_add.add_argument("--subsystem", default="")
    ps_add.add_argument("--locus", required=True)
    ps_add.add_argument("--priority", choices=("critical", "high", "medium", "low"), default="high")
    ps_add.add_argument("--trust-boundary", default="")
    ps_add.add_argument("--requires-tags", default="", help="Comma-separated capability tags required to reach or trigger this sink.")
    ps_add.add_argument("--run")
    ps_list = surf_sub.add_parser("list")
    ps_list.add_argument("--run")
    p_surf.set_defaults(func=cmd_surface)

    # driver
    p_drv = sub.add_parser("driver", help="Cache reusable surface setup and invocation commands.")
    drv_sub = p_drv.add_subparsers(dest="driver_cmd", required=True)
    pd_add = drv_sub.add_parser("add")
    pd_add.add_argument("--surface", required=True)
    pd_add.add_argument("--setup-cmd", required=True)
    pd_add.add_argument("--invoke-template", required=True)
    pd_add.add_argument("--teardown-cmd", default="")
    pd_add.add_argument("--notes", default="")
    pd_add.add_argument("--run")
    pd_list = drv_sub.add_parser("list")
    pd_list.add_argument("--run")
    p_drv.set_defaults(func=cmd_driver)

    # task
    task_kinds = ("map", "investigate", "bridge", "falsify", "reproduce", "instrument", "chain", "patch", "escalate")
    p_tsk = sub.add_parser("task", help="Coordinate bounded work tasks (`lease`, `checkpoint`, `done`, `dry`, `block`).")
    tsk_sub = p_tsk.add_subparsers(dest="task_cmd", required=True)
    pt_add = tsk_sub.add_parser("add")
    pt_add.add_argument("--kind", choices=task_kinds, required=True)
    pt_add.add_argument(
        "--direction",
        choices=("outside_in", "inside_out", "native_ffi", "peer_symmetry"),
        default="outside_in",
        help="Investigation direction (`outside_in`, `inside_out`, `native_ffi`, `peer_symmetry`).",
    )
    pt_add.add_argument("--title", required=True)
    pt_add.add_argument("--surface")
    pt_add.add_argument("--parent")
    pt_add.add_argument("--subsystem")
    pt_add.add_argument("--locus")
    pt_add.add_argument("--priority", choices=("critical", "high", "medium", "low"), default="high")
    pt_add.add_argument("--run")

    pt_lease = tsk_sub.add_parser("lease")
    pt_lease.add_argument("--worker", required=True)
    pt_lease.add_argument("--kind", choices=task_kinds)
    pt_lease.add_argument("--ttl", type=int, default=900)
    pt_lease.add_argument("--recover", action="store_true")
    pt_lease.add_argument("--run")

    pt_chk = tsk_sub.add_parser("checkpoint")
    pt_chk.add_argument("task_id")
    pt_chk.add_argument("--worker", required=True)
    pt_chk.add_argument("--state-json", required=True, help="Concise JSON object (`<= 2 KB`) persisting progress for session resume.")
    pt_chk.add_argument("--run")

    pt_done = tsk_sub.add_parser("done")
    pt_done.add_argument("task_id")
    pt_done.add_argument("--worker", required=True)
    pt_done.add_argument("--summary", default="")
    pt_done.add_argument("--run")

    pt_dry = tsk_sub.add_parser("dry")
    pt_dry.add_argument("task_id")
    pt_dry.add_argument("--worker", required=True)
    pt_dry.add_argument("--locus", required=True, help="Exact guard file:lines.")
    pt_dry.add_argument("--control", required=True, help="Why the concrete guard prevents the bug.")
    pt_dry.add_argument("--run")

    pt_blk = tsk_sub.add_parser("block")
    pt_blk.add_argument("task_id")
    pt_blk.add_argument("--worker", required=True)
    pt_blk.add_argument("--predicate", required=True)
    pt_blk.add_argument("--check-locus", default="")
    pt_blk.add_argument("--run")

    pt_lst = tsk_sub.add_parser("list")
    pt_lst.add_argument("--run")
    p_tsk.set_defaults(func=cmd_task)

    # coverage
    p_cov = sub.add_parser("coverage", help="Record or inspect audited source line spans (`coverage_spans`).")
    cov_sub = p_cov.add_subparsers(dest="coverage_cmd", required=True)
    pcv_r = cov_sub.add_parser("record")
    pcv_r.add_argument("rel_path", help="Relative file path inside target.")
    pcv_r.add_argument("--start-line", type=int, required=True)
    pcv_r.add_argument("--end-line", type=int, required=True)
    pcv_r.add_argument("--task")
    pcv_r.add_argument("--worker", default="worker")
    pcv_r.add_argument("--run")
    pcv_l = cov_sub.add_parser("list")
    pcv_l.add_argument("--run")
    p_cov.set_defaults(func=cmd_coverage)

    # anomaly
    p_an = sub.add_parser("anomaly", help="Record or explain execution anomalies (decoupled from claim survival).")
    an_sub = p_an.add_subparsers(dest="anomaly_cmd", required=True)
    pa_add = an_sub.add_parser("add")
    pa_add.add_argument("--locus", required=True)
    pa_add.add_argument("--observation", required=True)
    pa_add.add_argument("--repro-cmd", default="")
    pa_add.add_argument("--surface")
    pa_add.add_argument("--claim")
    pa_add.add_argument("--run")
    pa_exp = an_sub.add_parser("explain")
    pa_exp.add_argument("anomaly_id")
    pa_exp.add_argument("--locus", required=True)
    pa_exp.add_argument("--reason", required=True)
    pa_exp.add_argument("--run")
    pa_lst = an_sub.add_parser("list")
    pa_lst.add_argument("--run")
    p_an.set_defaults(func=cmd_anomaly)

    # primitive
    p_pr = sub.add_parser("primitive", help="Register capabilities or trust-laundering gadgets and promote composable helpers.")
    pr_sub = p_pr.add_subparsers(dest="primitive_cmd", required=True)
    pp_add = pr_sub.add_parser("add")
    pp_add.add_argument("--locus", required=True)
    pp_add.add_argument("--kind", required=True)
    pp_add.add_argument("--role", choices=("capability", "trust_gadget"), default="capability", help="`capability` (invariant-breaking quirk) or `trust_gadget` (normal code trusting an upstream invariant).")
    pp_add.add_argument("--trusted-invariant", default="", help="Upstream invariant trusted by a `trust_gadget` step.")
    pp_add.add_argument("--symbols", default="", help="Comma-separated code symbols or file paths touched by this primitive.")
    pp_add.add_argument("--preconditions", required=True)
    pp_add.add_argument("--postconditions", required=True)
    pp_add.add_argument("--evidence-cmd", required=True)
    pp_add.add_argument("--evidence-output", default="")
    pp_add.add_argument("--micropatch", default="", help="Optional counterfactual unified diff file stored for zero-ceremony `ajar chain propose` ablation.")
    pp_add.add_argument("--snapshot", default="", help="Optional associated `snp-*` post-state snapshot ID.")
    pp_add.add_argument("--surface", help="Optional associated surface ID.")
    pp_add.add_argument("--guarded-by", help="Upstream guard locus (`file:lines`) blocking standalone exploitation.")
    pp_add.add_argument("--guard-assumption", default="", help="Invariant assumed by the upstream guard.")
    pp_add.add_argument("--provides-tags", default="", help="Comma-separated capability tags provided by this primitive (`ns:name`).")
    pp_add.add_argument("--requires-tags", default="", help="Comma-separated capability tags required by this primitive (`ns:name`).")
    pp_add.add_argument("--run")

    pp_dry = pr_sub.add_parser("dry", help="Close an unchained guarded primitive as `dry` with a verified guard locus.")
    pp_dry.add_argument("primitive_id")
    pp_dry.add_argument("--worker", default="worker")
    pp_dry.add_argument("--locus", required=True)
    pp_dry.add_argument("--reason", required=True)
    pp_dry.add_argument("--run")

    pp_prm = pr_sub.add_parser("promote-helper", help="Verify and mount a read-only `StageContext` Python helper outside `slot-<k>`.")
    pp_prm.add_argument("primitive_id")
    pp_prm.add_argument("--file", required=True, help="Path to Python helper module.")
    pp_prm.add_argument("--callable", required=True, help="Callable function name accepting `(ctx: StageContext)`.")
    pp_prm.add_argument("--provides-tags", default="", help="Additional comma-separated `provides_tags`.")
    pp_prm.add_argument("--requires-tags", default="", help="Additional comma-separated `requires_tags`.")
    pp_prm.add_argument("--self-test-cmd", default="", help="Optional custom dual-mode verification command.")
    pp_prm.add_argument("--timeout", type=int, default=30)
    pp_prm.add_argument("--worker", default="worker")
    pp_prm.add_argument("--run")

    pp_hlp = pr_sub.add_parser("helpers", help="List promoted `StageContext` helpers.")
    pp_hlp.add_argument("--run")

    pp_lst = pr_sub.add_parser("list")
    pp_lst.add_argument("--run")
    p_pr.set_defaults(func=cmd_primitive)

    # binding
    p_bd = sub.add_parser("binding", help="Certify exact file-hash-bound constants and offsets.")
    bd_sub = p_bd.add_subparsers(dest="binding_cmd", required=True)
    pb_set = bd_sub.add_parser("set")
    pb_set.add_argument("--name", required=True)
    pb_set.add_argument("--value", required=True)
    pb_set.add_argument("--locus", required=True)
    pb_set.add_argument("--task")
    pb_set.add_argument("--run")
    pb_lst = bd_sub.add_parser("list")
    pb_lst.add_argument("--run")
    p_bd.set_defaults(func=cmd_binding)

    # claim
    p_cl = sub.add_parser("claim", help="Manage vulnerability hypotheses (`propose`, `rescope`, `falsify`, `survive`, `duplicate`, `instrument`, `reproduce`).")
    cl_sub = p_cl.add_subparsers(dest="claim_cmd", required=True)
    pc_prop = cl_sub.add_parser("propose")
    pc_prop.add_argument("--worker", required=True)
    pc_prop.add_argument("--title", required=True)
    pc_prop.add_argument("--locus", required=True)
    pc_prop.add_argument("--mechanism", required=True)
    pc_prop.add_argument("--severity", choices=("critical", "high", "medium", "low"), default="high")
    pc_prop.add_argument("--falsification-prediction", required=True)
    pc_prop.add_argument("--falsification-test", required=True)
    pc_prop.add_argument("--surface")
    pc_prop.add_argument("--consume-anomaly")
    pc_prop.add_argument("--same-root-of", default="", help="Optional parent `clm-*` ID when proposing an alternate entry route for the same root cause.")
    pc_prop.add_argument("--seeded-by-human", action="store_true")
    pc_prop.add_argument("--run")

    pc_dup = cl_sub.add_parser("duplicate", help="Close a candidate claim as `duplicate_root_cause` of an existing parent claim.")
    pc_dup.add_argument("claim_id")
    pc_dup.add_argument("--of", required=True, help="Parent `clm-*` ID sharing the same root defect.")
    pc_dup.add_argument("--worker", required=True)
    pc_dup.add_argument("--reason", required=True)
    pc_dup.add_argument("--run")

    pc_rsc = cl_sub.add_parser("rescope")
    pc_rsc.add_argument("claim_id")
    pc_rsc.add_argument("--worker", required=True)
    pc_rsc.add_argument("--reason", required=True)
    pc_rsc.add_argument("--title")
    pc_rsc.add_argument("--locus")
    pc_rsc.add_argument("--mechanism")
    pc_rsc.add_argument("--severity", choices=("critical", "high", "medium", "low"))
    pc_rsc.add_argument("--falsification-prediction")
    pc_rsc.add_argument("--falsification-test")
    pc_rsc.add_argument("--run")

    pc_fal = cl_sub.add_parser("falsify")
    pc_fal.add_argument("claim_id")
    pc_fal.add_argument("--worker", required=True)
    pc_fal.add_argument("--notes", required=True)
    pc_fal.add_argument("--control-locus")
    pc_fal.add_argument("--config-gate", default="", help="Optional runtime config predicate gating reachability (`config_gated` probe).")
    pc_fal.add_argument("--run")

    pc_sur = cl_sub.add_parser("survive")
    pc_sur.add_argument("claim_id")
    pc_sur.add_argument("--worker", required=True)
    pc_sur.add_argument("--notes", required=True)
    pc_sur.add_argument("--run")

    pc_ins = cl_sub.add_parser("instrument", help="Run an isolated diagnostic probe inside the shared `slot-<k>` pool to unblock `needs_instrumentation`.")
    pc_ins.add_argument("claim_id")
    pc_ins.add_argument("--worker", required=True)
    pc_ins.add_argument("--probe-cmd", required=True)
    pc_ins.add_argument("--probe-patch", default="", help="Optional temporary diagnostic diff applied only inside `slot-<k>`.")
    pc_ins.add_argument("--timeout", type=int, default=60)
    pc_ins.add_argument("--run")

    pc_blk = cl_sub.add_parser("block")
    pc_blk.add_argument("claim_id")
    pc_blk.add_argument("--worker", required=True)
    pc_blk.add_argument(
        "--env-blocker",
        choices=ENV_BLOCKER_KINDS,
        default="",
        help="Concrete environmental blocker kind (safety-policy/refusal deferrals are rejected).",
    )
    pc_blk.add_argument("--reason", required=True)
    pc_blk.add_argument("--run")

    pc_rep = cl_sub.add_parser("reproduce")
    pc_rep.add_argument("claim_id")
    pc_rep.add_argument("--worker", required=True)
    pc_rep.add_argument("--mode", choices=("source", "binary", "live"))
    pc_rep.add_argument("--poc-cmd", default="")
    pc_rep.add_argument("--control-cmd", default="")
    pc_rep.add_argument("--build-cmd", default="", help="Optional compile command run on clean and micropatched trees without burning PoC strikes on build errors.")
    pc_rep.add_argument("--micropatch", help="Path to 1-16 line counterfactual unified diff (source mode).")
    pc_rep.add_argument("--max-changed-lines", type=int, default=16, help="Max non-comment changed code lines allowed in `--micropatch` (default: 16).")
    pc_rep.add_argument("--save-post-state", default="", help="Optional relative directory/file inside `slot-<k>` to snapshot into `repro/snapshots/<snp_id>.tar.gz` after Arm 1.")
    pc_rep.add_argument("--provides-tags", default="", help="Optional comma-separated capability tags emitted by this confirmed finding (`ns:name`).")
    pc_rep.add_argument("--declared-steps", type=int, default=None, help="Optional explicit victim interaction step count for realism scoring.")
    pc_rep.add_argument("--shared-guard-locus", default="", help="Optional shared upstream guard locus when micropatch fixes a shared chokepoint.")
    pc_rep.add_argument("--release-cmd", default="", help="Arm 5A release-profile PoC command (`-O2` / `--release` without debug asserts).")
    pc_rep.add_argument("--release-control-cmd", default="", help="Arm 5B release-profile benign control command.")
    pc_rep.add_argument("--oracle-json", help="Optional JSON oracle rules (`expect_regex`, `expect_exit_code`).")
    pc_rep.add_argument("--determinism", choices=("deterministic", "probabilistic_race"), default="deterministic")
    pc_rep.add_argument("--trials", type=int, default=8)
    pc_rep.add_argument("--timeout", type=int, default=60)
    pc_rep.add_argument("--sibling-poc-cmd", help="Optional sibling PoC command for warm cross-kill dedup.")
    pc_rep.add_argument("--binary", help="Executable path override for binary mode.")
    pc_rep.add_argument("--poc-io-json", help="Binary PoC args/stdin JSON.")
    pc_rep.add_argument("--control-io-json", help="Binary control args/stdin JSON.")
    pc_rep.add_argument("--guard-json", help="Binary gdb runtime guard JSON.")
    pc_rep.add_argument("--ablation-json", help="Binary 1-field input ablation JSON.")
    pc_rep.add_argument("--seed-cmd", help="Live mode synthetic state seeder.")
    pc_rep.add_argument("--teardown-cmd", help="Live mode teardown command.")
    pc_rep.add_argument("--target-url", help="Live mode target URL.")
    pc_rep.add_argument("--run")

    pc_lst = cl_sub.add_parser("list")
    pc_lst.add_argument("--run")
    p_cl.set_defaults(func=cmd_claim)

    # repro (Strike-free smoke-test & snapshots)
    p_rpr = sub.add_parser("repro", help="Run strike-free build/PoC smoke tests (`ajar repro try`) and inspect post-state snapshots.")
    rpr_sub = p_rpr.add_subparsers(dest="repro_cmd", required=True)
    prp_t = rpr_sub.add_parser("try", help="Run a strike-free command inside the shared 8-slot pool (`slot-<k>`) without incrementing `failed_repro_count`.")
    prp_t.add_argument("--cmd", required=True)
    prp_t.add_argument("--patch", default="", help="Optional candidate diff applied temporarily inside `slot-<k>`.")
    prp_t.add_argument("--build-cmd", default="", help="Optional compile command run before `--cmd`.")
    prp_t.add_argument("--oracle-json", help="Optional JSON oracle rules.")
    prp_t.add_argument("--timeout", type=int, default=60)
    prp_t.add_argument("--run")
    prp_s = rpr_sub.add_parser("snapshots", help="List captured Arm-1 post-state snapshots (`snp-*`).")
    prp_s.add_argument("--run")
    p_rpr.set_defaults(func=cmd_repro)

    # finding (Operator calibration & listing)
    p_fnd = sub.add_parser("finding", help="Inspect confirmed findings and calibrate severity/titles/realism without raw SQL.")
    fnd_sub = p_fnd.add_subparsers(dest="finding_cmd", required=True)
    pfn_c = fnd_sub.add_parser("calibrate", help="Calibrate severity, title, declared steps, or realism tier on a confirmed finding.")
    pfn_c.add_argument("finding_id")
    pfn_c.add_argument("--severity", choices=("critical", "high", "medium", "low"))
    pfn_c.add_argument("--title")
    pfn_c.add_argument("--declared-steps", type=int, default=None, help="Optional calibrated victim interaction step count.")
    pfn_c.add_argument("--realism-tier", choices=("crown_jewel", "high_impact", "stepping_stone"), help="Optional calibrated realism tier.")
    pfn_c.add_argument("--reason", required=True)
    pfn_c.add_argument("--worker", default="operator")
    pfn_c.add_argument("--run")
    pfn_l = fnd_sub.add_parser("list", help="List confirmed findings.")
    pfn_l.add_argument("--run")
    p_fnd.set_defaults(func=cmd_finding)

    # chain
    p_ch = sub.add_parser("chain", help="Compose verified findings, capabilities, and trust gadgets into ablated multi-step chains.")
    ch_sub = p_ch.add_subparsers(dest="chain_cmd", required=True)
    pch_p = ch_sub.add_parser("propose")
    pch_p.add_argument("--title", required=True)
    pch_p.add_argument("--steps", required=True, help="Comma-separated `fnd-*`, `clm-*`, `prim-*`, or `anom-*` IDs.")
    pch_p.add_argument("--poc-cmd", required=True)
    pch_p.add_argument("--control-cmd", required=True)
    pch_p.add_argument(
        "--build-cmd",
        default="",
        help="Optional compile command run before full/control arms and after step micropatch apply/reset (auto-inherited from step findings if omitted).",
    )
    pch_p.add_argument("--severity", choices=("critical", "high", "medium", "low"), default="critical")
    pch_p.add_argument("--oracle-json", help="Optional JSON oracle rules (`expect_regex`, `expect_exit_code`).")
    pch_p.add_argument("--step-micropatch", action="append", help="Per-step counterfactual patch `<step_id>:<path/to/step.diff>` (auto-inherited for `fnd-*` and `prim-*` with `--micropatch`).")
    pch_p.add_argument("--backup-step", action="append", help="Modular backup step `<primary_step_id>:<backup_step_id>` automatically swapped if primary fails.")
    pch_p.add_argument("--door", default="", help="Optional Open Door ID (`door-*`) resolved by this chain.")
    pch_p.add_argument("--jewel", default="", help="Optional Crown Jewel ID (`cjw-*`) reached by this chain.")
    pch_p.add_argument("--declared-steps", type=int, default=None, help="Optional explicit victim interaction step count.")
    pch_p.add_argument("--no-ablate", action="store_true", help="Skip automated per-step ablation (single-anomaly chains only).")
    pch_p.add_argument("--timeout", type=int, default=60)
    pch_p.add_argument("--worker", default="worker")
    pch_p.add_argument("--run")

    pch_cal = ch_sub.add_parser("calibrate", help="Calibrate realism tier, severity, or declared steps on a recorded chain.")
    pch_cal.add_argument("chain_id")
    pch_cal.add_argument("--realism-tier", choices=("crown_jewel", "high_impact", "stepping_stone"))
    pch_cal.add_argument("--severity", choices=("critical", "high", "medium", "low"))
    pch_cal.add_argument("--declared-steps", type=int, default=None)
    pch_cal.add_argument("--reason", required=True)
    pch_cal.add_argument("--worker", default="operator")
    pch_cal.add_argument("--run")

    pch_pr = ch_sub.add_parser("probe", help="Hydrate a Stage-1 post-state snapshot (`snp-*`) into the shared `slot-<k>` pool and probe Stage 2.")
    pch_pr.add_argument("--from-snapshot", required=True, help="Snapshot ID (`snp-*`) from `ajar claim reproduce --save-post-state`.")
    pch_pr.add_argument("--cmd", required=True, help="Stage-2 probe command executed inside hydrated `slot-<k>`.")
    pch_pr.add_argument("--patch", default="", help="Optional temporary diff applied inside `slot-<k>`.")
    pch_pr.add_argument("--build-cmd", default="", help="Optional compile command run before `--cmd` inside hydrated `slot-<k>`.")
    pch_pr.add_argument("--oracle-json", help="Optional JSON oracle rules.")
    pch_pr.add_argument("--timeout", type=int, default=60)
    pch_pr.add_argument("--worker", default="worker")
    pch_pr.add_argument("--run")

    pch_fr = ch_sub.add_parser("frontier", help="Compile Crown-Jewel, Open-Door, multi-hop Percolation, and Unicorn-Gap frontier.")
    pch_fr.add_argument("--run")

    pch_l = ch_sub.add_parser("list")
    pch_l.add_argument("--run")
    p_ch.set_defaults(func=cmd_chain)

    # hooks (epistemic micro-hooks inspection)
    p_eh = sub.add_parser("hooks", help="Inspect event-driven epistemic micro-hooks (`H1`–`H8`).")
    eh_sub = p_eh.add_subparsers(dest="hooks_cmd", required=True)
    peh_l = eh_sub.add_parser("list")
    peh_l.add_argument("--status", choices=("active", "consumed", "expired"))
    peh_l.add_argument("--run")
    p_eh.set_defaults(func=cmd_epistemic_hooks)

    # patch (9-Arm Production Fixes Gate)
    p_ptc = sub.add_parser("patch", help="Verify production Fixes with the hardened 9-Arm Remediation Gate (`ajar patch verify`).")
    ptc_sub = p_ptc.add_subparsers(dest="patch_cmd", required=True)
    ppt_v = ptc_sub.add_parser("verify")
    ppt_v.add_argument("finding_id")
    ppt_v.add_argument("--patch", required=True, help="Path to unified diff production patch.")
    ppt_v.add_argument("--suite-cmd", required=True, help="Arm 5 full project test suite command.")
    ppt_v.add_argument("--variant-cmd", action="append", required=True, help="Arm 6 bypass variant command (repeat >= 3 times; >= 1 must trigger on clean HEAD).")
    ppt_v.add_argument("--caller-audit", required=True, help="Arm 7 caller NULL/error-return safety audit note (>= 20 chars).")
    ppt_v.add_argument("--sibling-audit", required=True, help="Arm 8 sibling-route / peer-hook symmetry audit note (>= 20 chars).")
    ppt_v.add_argument("--caller-cmd", default="", help="Optional executable Arm 7 caller error-propagation test command.")
    ppt_v.add_argument("--sibling-cmd", default="", help="Optional executable Arm 8 sibling-route symmetry test command.")
    ppt_v.add_argument("--oracle-json", help="Optional JSON oracle rules for PoC/variant checks.")
    ppt_v.add_argument("--shared-guard-locus", default="", help="Optional shared guard locus when patching a common chokepoint.")
    ppt_v.add_argument("--max-changed-lines", type=int, default=120)
    ppt_v.add_argument("--timeout", type=int, default=90)
    ppt_v.add_argument("--suite-timeout", type=int, default=1800, help="Timeout in seconds for Arm 5 full project test suite (default: 1800).")
    ppt_v.add_argument("--build-cmd", default="", help="Optional build command run before clean/patched/reverted verification steps.")
    ppt_v.add_argument("--worker", default="worker")
    ppt_v.add_argument("--run")
    ppt_l = ptc_sub.add_parser("list")
    ppt_l.add_argument("--run")
    p_ptc.set_defaults(func=cmd_patch)

    # steer
    p_st = sub.add_parser("steer", help="Manage attributable workspace Steers (`DEC-0049` / `DEC-0061`).")
    st_sub = p_st.add_subparsers(dest="steer_cmd", required=True)
    pst_a = st_sub.add_parser("add")
    pst_a.add_argument("--rule", required=True, help="Threat-model or scope rule text.")
    pst_a.add_argument("--scope", choices=("global", "subsystem", "path"), default="global")
    pst_a.add_argument("--filter", default="", help="Subsystem name or path prefix when scope != global.")
    pst_a.add_argument("--author", default="operator")
    pst_a.add_argument(
        "--kind",
        choices=("scope_authority", "research_steering"),
        default="scope_authority",
        help="`scope_authority` preserves autonomous attribution; `research_steering` marks human-guided.",
    )
    pst_a.add_argument("--run")
    pst_l = st_sub.add_parser("list")
    pst_l.add_argument("--all", action="store_true", help="Include revoked Steers.")
    pst_l.add_argument("--run")
    pst_r = st_sub.add_parser("revoke")
    pst_r.add_argument("steer_id")
    pst_r.add_argument("--reason", required=True)
    pst_r.add_argument("--actor", default="operator")
    pst_r.add_argument("--run")
    p_st.set_defaults(func=cmd_steer)

    # export-graph (Platform whiteboard feed)
    p_eg = sub.add_parser("export-graph", help="Export deterministic Platform component & attack-flow JSON graph.")
    p_eg.add_argument(
        "--schema",
        choices=VALID_GRAPH_SCHEMAS,
        default="v2",
        help="Graph schema version (`v2` = `ajar-platform-graph/2`, `v1` = legacy `ajar-platform-graph/1`).",
    )
    p_eg.add_argument(
        "--visibility",
        choices=VALID_GRAPH_VISIBILITIES,
        default="internal_full",
        help="Output visibility tier (`internal_full`, `customer_private`, `public_disclosure`).",
    )
    p_eg.add_argument(
        "--include-snippets",
        action="store_true",
        help="Include bounded scrubbed source snippets for finding, chain, and guard loci.",
    )
    p_eg.add_argument(
        "--repo-slug",
        default="",
        help="Repository slug (`owner/repo`) emitted in `run.repo_slug` (auto-inferred when omitted).",
    )
    p_eg.add_argument("--output", help="Optional output file path.")
    p_eg.add_argument("--run")
    p_eg.set_defaults(func=cmd_export_graph)

    # touch
    p_tc = sub.add_parser("touch", help="Record human touches for run attribution (`DEC-0061`/`0071`).")
    tc_sub = p_tc.add_subparsers(dest="touch_cmd", required=True)
    ptc_a = tc_sub.add_parser("add")
    ptc_a.add_argument("--kind", choices=("scope_authority", "env_rescue", "research_steering", "poc_repair", "review_signoff"), required=True)
    ptc_a.add_argument("--notes", required=True)
    ptc_a.add_argument("--actor", default="operator")
    ptc_a.add_argument("--run")
    ptc_l = tc_sub.add_parser("list")
    ptc_l.add_argument("--run")
    p_tc.set_defaults(func=cmd_touch)

    # spend
    p_sp = sub.add_parser("spend", help="Record model token and USD spend (`DEC-0122`).")
    sp_sub = p_sp.add_subparsers(dest="spend_cmd", required=True)
    psp_a = sp_sub.add_parser("add")
    psp_a.add_argument("--worker", required=True)
    psp_a.add_argument("--cost-usd", type=float, required=True)
    psp_a.add_argument("--surface", default="", help="Optional surface ID for dry-surface breaker tracking.")
    psp_a.add_argument("--phase", choices=("explore", "verify"), default="explore")
    psp_a.add_argument("--model", default="")
    psp_a.add_argument("--tokens-in", type=int, default=0)
    psp_a.add_argument("--tokens-out", type=int, default=0)
    psp_a.add_argument("--notes", default="")
    psp_a.add_argument("--run")
    psp_l = sp_sub.add_parser("list")
    psp_l.add_argument("--run")
    p_sp.set_defaults(func=cmd_spend)

    # gate check
    p_gt = sub.add_parser("gate", help="Check SQL closeout gates `G1`–`G5`.")
    gt_sub = p_gt.add_subparsers(dest="gate_cmd", required=True)
    pg_c = gt_sub.add_parser("check")
    pg_c.add_argument("--run")
    pg_c.add_argument("--json", action="store_true", default=True)
    pg_c.set_defaults(func=cmd_gate_check)

    # finish
    p_fin = sub.add_parser("finish", help="Verify all closeout gates pass and finalize run report.")
    p_fin.add_argument("--run")
    p_fin.add_argument("--json", action="store_true", default=True)
    p_fin.set_defaults(func=cmd_finish)

    # report
    p_rep = sub.add_parser("report", help="Render Markdown or JSON security verification report.")
    p_rep.add_argument("--run")
    p_rep.add_argument("--format", choices=("md", "json"), default="md")
    p_rep.add_argument("--output")
    p_rep.add_argument("--include-rejected-appendix", action="store_true")
    p_rep.set_defaults(func=cmd_report)

    # mcp
    def _cmd_mcp(a: argparse.Namespace) -> int:
        serve_mcp_stdio(explicit_run_id=a.run)
        return EXIT_OK

    p_mcp = sub.add_parser("mcp", help="Run STDIO JSON-RPC 2.0 MCP server for Host Mode agents.")
    p_mcp.add_argument("--run")
    p_mcp.set_defaults(func=_cmd_mcp)

    # hook
    p_hk = sub.add_parser("hook", help="Host Mode persistence hooks.")
    hk_sub = p_hk.add_subparsers(dest="hook_cmd", required=True)
    ph_cs = hk_sub.add_parser("claude-stop")
    ph_cs.add_argument("--run")
    ph_cs.add_argument("--if-active", action="store_true")
    ph_cs.set_defaults(func=cmd_hook)

    # loop
    p_lp = sub.add_parser("loop", help="Host Mode continuation loop for Codex, OMP, or custom CLIs.")
    p_lp.add_argument("host", choices=("codex", "omp", "custom"))
    p_lp.add_argument("--cmd", help="Shell command template (`{prompt}` placeholder supported).")
    p_lp.add_argument("--max-rounds", type=int, default=12)
    p_lp.add_argument("--run")
    p_lp.set_defaults(func=cmd_loop)

    # run (Standalone Mode)
    p_run = sub.add_parser("run", help="Run Standalone autonomous verification with 80/20 budget reserve.")
    p_run.add_argument("target")
    p_run.add_argument("--run-id")
    p_run.add_argument("--mode", choices=("source", "binary", "live"), default="source")
    p_run.add_argument("--goal", default="Identify, falsify, and reproduce high-severity software vulnerabilities.")
    p_run.add_argument("--until", choices=stopping_choices, default="exhaustive-high")
    p_run.add_argument("--stopping", dest="until", choices=stopping_choices, help="Alias for --until.")
    p_run.add_argument("--phase", choices=phase_choices, default="hunt", help="Campaign phase (`hunt` defers 9-arm `patch verify` until `remediate`).")
    p_run.add_argument("--budget", type=float, default=None, help="Explicit COGS cap override in USD (defaults to 0.35 * Code quote).")
    p_run.add_argument("--cogs-cap", dest="budget", type=float, help="Alias for --budget explicit COGS cap override in USD.")
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--discover-passes", type=int, default=1, help="Keep-biased Best-of-N discovery passes across directions before funneling.")
    p_run.add_argument("--worker-cmd", help="Worker command executed per leased task.")
    p_run.add_argument("--max-steps", type=int, default=50)
    p_run.add_argument("--json", action="store_true", default=True)
    p_run.set_defaults(func=cmd_run)

    # swarm (Stage-split stripped packet dispatcher + wire-profile fallback ladder)
    p_swm = sub.add_parser(
        "swarm",
        help="Generate stripped Swarm Worker packets and step down `--wire-profile` fallback tiers.",
    )
    swm_sub = p_swm.add_subparsers(dest="swarm_cmd", required=True)
    psw_p = swm_sub.add_parser("packet", help="Emit a stripped Just-Enough-Context worker assignment packet.")
    psw_p.add_argument("--stage", choices=VALID_SWARM_STAGES, required=True)
    psw_p.add_argument(
        "--wire-profile",
        choices=("auto", *WIRE_PROFILE_LADDER),
        default="auto",
        help="Wire framing tier (`auto` defaults to `direct` Swarm Worker and honors prior fallback escalations).",
    )
    psw_p.add_argument("--items", default="", help="Optional comma-separated task/claim/primitive/finding/door IDs.")
    psw_p.add_argument("--limit", type=int, default=4, help="Max items per packet (`regression_tdd` forces 1, `swarm_patch_first` <= 2).")
    psw_p.add_argument("--worker", default="", help="Explicit worker ID override.")
    psw_p.add_argument("--json", action="store_true", help="Emit JSON metadata + packet_markdown instead of raw Markdown.")
    psw_p.add_argument("--run")

    psw_f = swm_sub.add_parser("fallback", help="Record a stalled/filter-blocked worker and emit stepped-down fallback packet(s).")
    psw_f.add_argument("target", help="Dispatch ID (`dsp-...`) or worker ID (`w-...`) that stalled or refused.")
    psw_f.add_argument("--reason", choices=VALID_FALLBACK_REASONS, default="idle_no_return")
    psw_f.add_argument("--notes", default="")
    psw_f.add_argument("--run")

    psw_c = swm_sub.add_parser("complete", help="Mark a swarm dispatch completed.")
    psw_c.add_argument("target", help="Dispatch ID (`dsp-...`) or worker ID (`w-...`).")
    psw_c.add_argument("--notes", default="")
    psw_c.add_argument("--run")

    psw_s = swm_sub.add_parser("status", help="List swarm dispatches and wire-profile escalations.")
    psw_s.add_argument("--run")
    p_swm.set_defaults(func=cmd_swarm)

    # reopen (Hydrate from shared mirror and unblock zero-attempt blocked claims)
    p_reo = sub.add_parser(
        "reopen",
        help="Hydrate a run from shared storage and reopen zero-attempt policy-blocked claims.",
    )
    p_reo.add_argument("run_id", help="Run ID to hydrate and reopen (for example `git-wave1a`).")
    p_reo.add_argument("--keep-blocked", action="store_true", help="Keep zero-attempt blocked claims untouched.")
    p_reo.add_argument("--from-shared", default=None, help="Explicit shared mirror directory override.")
    p_reo.add_argument("--json", action="store_true", default=True)
    p_reo.set_defaults(func=cmd_reopen)

    # economics (DEC-0132 empirical COGS/LoC calibration telemetry export)
    p_eco = sub.add_parser("economics", help="Export advisory DEC-0132 COGS/LoC calibration telemetry.")
    eco_sub = p_eco.add_subparsers(dest="economics_cmd", required=True)
    peco_exp = eco_sub.add_parser("export", help="Export structured per-run COGS and gross-margin telemetry JSON.")
    peco_exp.add_argument("--run")
    peco_exp.add_argument("--output", help="Optional output path for calibration JSON.")
    p_eco.set_defaults(func=cmd_economics)

    # ledger (P0-3 commit-before-submit SHA-256 preimage helper)
    p_ldg = sub.add_parser("ledger", help="Build commit-before-submit SHA-256 ledger preimages.")
    ldg_sub = p_ldg.add_subparsers(dest="ledger_cmd", required=True)
    pldg_cp = ldg_sub.add_parser("commit-preimage", help="Compute SHA-256 commitment and redacted preimage for a finding.")
    pldg_cp.add_argument("finding_id", help="Confirmed finding ID (for example `fnd-1234abcd`).")
    pldg_cp.add_argument("--run")
    pldg_cp.add_argument("--target-slug", default="", help="Optional public target identifier (defaults to target dir name).")
    pldg_cp.add_argument("--commit-sha", default="", help="Optional git commit SHA override.")
    pldg_cp.add_argument("--salt", default=None, help="Optional explicit hex salt for deterministic reproduction.")
    pldg_cp.add_argument("--public-out", help="Optional path to write the public commitment JSON record.")
    pldg_cp.add_argument("--preimage-out", help="Optional path to write the private reveal preimage JSON (mode 0600).")
    p_ldg.set_defaults(func=cmd_ledger)

    # lead (Multi-Agent Expected-Value Lead Voting & Per-Root Plateau Breaker)
    p_lead = sub.add_parser(
        "lead",
        help="Vote on high-EV chain/hunt leads across swarm scouts and inspect root plateau throttles.",
    )
    lead_sub = p_lead.add_subparsers(dest="lead_cmd", required=True)
    lead_target_choices = ("surface", "door", "slice", "chain", "subsystem", "claim", "primitive", "finding")
    pld_v = lead_sub.add_parser("vote", help="Cast or update a structured Expected-Value vote (`1..10` axes) on a lead.")
    pld_v.add_argument("--worker", required=True)
    pld_v.add_argument("--target-kind", choices=lead_target_choices, required=True)
    pld_v.add_argument("--target-id", default="", help="Optional surface, door, slice, chain, claim, primitive, or finding ID.")
    pld_v.add_argument("--locus", default="", help="Optional target locus (`file:lines`).")
    pld_v.add_argument("--subsystem", default="", help="Optional target subsystem.")
    pld_v.add_argument("--impact", type=int, default=7, help="Impact score `1..10` (Crown-Jewel proximity / severity).")
    pld_v.add_argument("--plausibility", type=int, default=7, help="Plausibility score `1..10` (evidence of unguarded path).")
    pld_v.add_argument("--chainability", type=int, default=7, help="Chainability score `1..10` (composable state/capability output).")
    pld_v.add_argument("--effort", type=int, default=5, help="Estimated effort cost `1..10` (lower is cheaper).")
    pld_v.add_argument("--rationale", default="", help="Concise structural rationale for this EV score.")
    pld_v.add_argument("--run")

    pld_r = lead_sub.add_parser("rank", help="Rank multi-agent voted leads by consensus Expected Value.")
    pld_r.add_argument("--target-kind", choices=lead_target_choices, default="")
    pld_r.add_argument("--limit", type=int, default=25)
    pld_r.add_argument("--run")

    pld_t = lead_sub.add_parser("throttles", help="Inspect per-root diminishing-returns plateau throttles.")
    pld_t.add_argument("--run")
    p_lead.set_defaults(func=cmd_lead)

    # catalog (Unified Issue & Gadget Catalog + Backward Sink-to-Source Call-Cone Slicing)
    p_cat = sub.add_parser(
        "catalog",
        help="Search the unified Issue & Gadget Catalog and trace backward sink-to-source call cones.",
    )
    cat_sub = p_cat.add_subparsers(dest="catalog_cmd", required=True)
    pct_s = cat_sub.add_parser("search", help="Query findings, capabilities, trust gadgets, claims, anomalies, and Open Doors.")
    pct_s.add_argument("query", nargs="?", default="", help="Optional lexical/symbol query.")
    pct_s.add_argument("--tags", default="", help="Optional comma-separated capability tags (`ns:name`).")
    pct_s.add_argument("--subsystem", default="", help="Optional subsystem or file filter.")
    pct_s.add_argument(
        "--role",
        choices=("finding", "capability", "trust_gadget", "candidate_claim", "anomaly", "open_door"),
        default="",
    )
    pct_s.add_argument("--verified-only", action="store_true", help="Exclude unverified candidate claims and unexplained anomalies.")
    pct_s.add_argument("--limit", type=int, default=30)
    pct_s.add_argument("--run")

    pct_b = cat_sub.add_parser("backslice", help="Walk `repomap_edges` backward (`callee <- caller`) from a sink/jewel/door/symbol.")
    pct_b.add_argument("sink", help="Crown-Jewel ID (`cjw-*`), Open-Door ID (`door-*`), `file:line` locus, or symbol name.")
    pct_b.add_argument("--max-hops", type=int, default=3, help="Backward call-graph hops `1..6` (default: 3).")
    pct_b.add_argument("--limit", type=int, default=20)
    pct_b.add_argument("--run")
    p_cat.set_defaults(func=cmd_catalog)

    return p


@functools.lru_cache(maxsize=1)
def _get_cached_parser() -> argparse.ArgumentParser:
    return build_parser()
