"""Hunt-phase CLI handlers (`surface`, `driver`, `task`, `coverage`, `anomaly`, `primitive`, `binding`, `door`)."""

from __future__ import annotations

import argparse
import json
import pathlib

from ajar import (
    EXIT_OK,
    EXIT_USER_ERROR,
)
from ajar.chain_planner import (
    _parse_symbol_list,
    add_crown_jewel,
    list_crown_jewels,
    park_open_door,
)
from ajar.cli.common import _emit
from ajar.db import (
    AjarError,
    checkpoint_task,
    lease_next_task,
    list_rows,
    mark_primitive_dry,
    open_run_db,
    record_coverage_span,
    render_task_context,
    resolve_run_id,
    run_dir_for,
    set_certified_binding,
)
from ajar.repro_compose import promote_primitive_helper
from ajar.services import (
    add_anomaly,
    add_primitive,
    add_surface,
    add_surface_driver,
    add_task,
    block_task,
    close_task_done,
    close_task_dry,
    explain_anomaly,
)


def cmd_surface(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.surface_cmd == "add":
            res = add_surface(
                conn,
                name=args.name,
                kind=args.kind,
                locus=args.locus,
                subsystem=args.subsystem,
                priority=args.priority,
                trust_boundary=args.trust_boundary or "",
                requires_tags=getattr(args, "requires_tags", None),
                actor="worker",
            )
            _emit(res, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM surfaces ORDER BY created_at ASC")
        _emit({"surfaces": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_driver(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.driver_cmd == "add":
            res = add_surface_driver(
                conn,
                surface_id=args.surface,
                setup_cmd=args.setup_cmd,
                invoke_template=args.invoke_template,
                teardown_cmd=args.teardown_cmd or "",
                notes=args.notes or "",
            )
            _emit(res, True)
            return EXIT_OK
        rows = list_rows(conn, "SELECT * FROM surface_drivers ORDER BY created_at ASC")
        _emit({"drivers": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_task(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
        tpath = pathlib.Path(run["target_path"]) if run else None

        if args.task_cmd == "add":
            res = add_task(
                conn,
                kind=args.kind,
                title=args.title,
                locus=args.locus or "",
                subsystem=args.subsystem,
                priority=args.priority,
                direction=getattr(args, "direction", "outside_in") or "outside_in",
                parent_task_id=args.parent,
                surface_id=args.surface,
            )
            _emit(res, True)
            return EXIT_OK

        if args.task_cmd == "lease":
            leased = lease_next_task(
                conn,
                worker_id=args.worker,
                kind=args.kind,
                ttl_sec=args.ttl,
                recover=bool(args.recover),
            )
            if leased is not None:
                leased["context"] = render_task_context(
                    conn, leased["task_id"], record_exposure=not bool(args.recover)
                )["rendered"]
            _emit({"leased": leased}, True)
            return EXIT_OK

        if args.task_cmd == "checkpoint":
            try:
                parsed_state = json.loads(args.state_json)
            except json.JSONDecodeError as exc:
                raise AjarError(f"Invalid --state-json JSON object: {exc}", EXIT_USER_ERROR) from exc
            if not isinstance(parsed_state, dict):
                raise AjarError("--state-json must decode to a JSON object (`{...}`).", EXIT_USER_ERROR)
            res = checkpoint_task(
                conn,
                task_id=args.task_id,
                worker_id=args.worker,
                state_dict=parsed_state,
            )
            _emit(res, True)
            return EXIT_OK

        if args.task_cmd == "done":
            res = close_task_done(
                conn,
                task_id=args.task_id,
                worker_id=args.worker,
                summary=args.summary or "",
                target_dir=tpath,
            )
            _emit(res, True)
            return EXIT_OK

        if args.task_cmd == "dry":
            res = close_task_dry(
                conn,
                task_id=args.task_id,
                worker_id=args.worker,
                locus=args.locus,
                control_reason=args.control,
                target_dir=tpath,
                target_mode=str(run["target_mode"] if run else "source"),
            )
            _emit(res, True)
            return EXIT_OK

        if args.task_cmd == "block":
            res = block_task(
                conn,
                task_id=args.task_id,
                worker_id=args.worker,
                predicate=args.predicate,
                check_locus=args.check_locus or "",
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM tasks ORDER BY salience_score DESC, created_at ASC")
        _emit({"tasks": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_coverage(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.coverage_cmd == "record":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            res = record_coverage_span(
                conn,
                target_dir=tpath,
                task_id=args.task,
                worker_id=args.worker,
                rel_path=args.rel_path,
                start_line=int(args.start_line),
                end_line=int(args.end_line),
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM coverage_spans ORDER BY rel_path ASC, start_line ASC")
        _emit({"coverage_spans": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_anomaly(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.anomaly_cmd == "add":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"]) if run else None
            res = add_anomaly(
                conn,
                locus=args.locus,
                observation=args.observation,
                surface_id=args.surface,
                source_claim_id=args.claim,
                repro_cmd=args.repro_cmd or "",
                target_dir=tpath,
                actor="worker",
            )
            _emit(res, True)
            return EXIT_OK

        if args.anomaly_cmd == "explain":
            res = explain_anomaly(
                conn,
                anomaly_id=args.anomaly_id,
                locus=args.locus,
                reason=args.reason,
                actor="worker",
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM anomalies ORDER BY created_at ASC")
        _emit({"anomalies": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_primitive(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        if args.primitive_cmd == "add":
            res = add_primitive(
                conn,
                locus=args.locus,
                kind=args.kind,
                preconditions=args.preconditions,
                postconditions=args.postconditions,
                evidence_cmd=args.evidence_cmd,
                evidence_output=args.evidence_output or "",
                surface_id=getattr(args, "surface", None),
                role=getattr(args, "role", None) or "capability",
                trusted_invariant=getattr(args, "trusted_invariant", None) or "",
                symbols=_parse_symbol_list(getattr(args, "symbols", None)),
                guarded_by_locus=getattr(args, "guarded_by", None) or "",
                guard_assumption=getattr(args, "guard_assumption", None) or "",
                provides_tags=getattr(args, "provides_tags", None),
                requires_tags=getattr(args, "requires_tags", None),
                micropatch_path=getattr(args, "micropatch", None),
                snapshot_id=getattr(args, "snapshot", None) or "",
            )
            _emit(res, True)
            return EXIT_OK

        if args.primitive_cmd == "dry":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"]) if run else pathlib.Path(".")
            tmode = str(run["target_mode"]) if run else "source"
            res = mark_primitive_dry(
                conn,
                target_dir=tpath,
                target_mode=tmode,
                primitive_id=args.primitive_id,
                worker_id=args.worker,
                locus=args.locus,
                reason=args.reason,
            )
            _emit(res, True)
            return EXIT_OK

        if args.primitive_cmd == "promote-helper":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            res = promote_primitive_helper(
                conn,
                run_dir=rdir,
                target_dir=tpath,
                primitive_id=args.primitive_id,
                helper_file=pathlib.Path(args.file),
                callable_name=args.callable,
                provides_tags=args.provides_tags,
                requires_tags=args.requires_tags,
                self_test_cmd=args.self_test_cmd or "",
                timeout_sec=args.timeout,
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if args.primitive_cmd == "helpers":
            rows = list_rows(conn, "SELECT * FROM primitive_helpers ORDER BY created_at ASC")
            _emit({"primitive_helpers": rows}, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM primitives ORDER BY created_at ASC")
        _emit({"primitives": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_binding(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.binding_cmd == "set":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            res = set_certified_binding(
                conn,
                target_dir=tpath,
                name=args.name,
                value=args.value,
                locus=args.locus,
                task_id=args.task,
            )
            _emit(res, True)
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM certified_bindings ORDER BY updated_at DESC")
        _emit({"bindings": rows}, True)
        return EXIT_OK
    finally:
        conn.close()


def cmd_door(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    conn = open_run_db(rid)
    try:
        if args.door_cmd == "jewel-add":
            res = add_crown_jewel(
                conn,
                name=args.name,
                locus=args.locus,
                subsystem=args.subsystem or "",
                impact_class=args.impact_class,
                symbols=args.symbols,
                max_interaction_steps=int(args.max_steps),
                require_default_config=not bool(args.allow_nondefault_config),
                forbid_visible_error=not bool(args.allow_visible_error),
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if args.door_cmd == "jewel-list":
            _emit({"crown_jewels": list_crown_jewels(conn)}, True)
            return EXIT_OK

        if args.door_cmd == "park":
            res = park_open_door(
                conn,
                anchor_locus=args.anchor_locus,
                missing_link_summary=args.missing,
                wishlist_query=args.wishlist or "",
                jewel_id=args.jewel or "",
                direction=args.direction,
                blocker_locus=args.blocker_locus or "",
                subsystem=args.subsystem or "",
                held_ids=args.held_ids,
                snapshot_id=args.snapshot or "",
                wanted_tags=args.wanted_tags,
                wanted_symbols=args.wanted_symbols,
                max_bridge_attempts=int(args.max_bridge_attempts),
                spawn_hunters=not bool(args.no_spawn_hunters),
                worker_id=args.worker,
            )
            _emit(res, True)
            return EXIT_OK

        if getattr(args, "status", None):
            rows = list_rows(
                conn,
                "SELECT * FROM parked_doors WHERE status = ? ORDER BY updated_at DESC",
                (args.status,),
            )
        else:
            rows = list_rows(conn, "SELECT * FROM parked_doors ORDER BY updated_at DESC")
        _emit({"open_doors": rows}, True)
        return EXIT_OK
    finally:
        conn.close()
