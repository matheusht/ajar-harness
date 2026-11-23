"""Strike-free smoke-test, `@VISITED` / `@UNREACHED` slice-probe, and snapshot CLI handlers (`ajar repro`)."""

from __future__ import annotations

import argparse
import json
import pathlib

from ajar import EXIT_OK, EXIT_USER_ERROR
from ajar.cli.common import _emit
from ajar.db import (
    AjarError,
    list_rows,
    open_run_db,
    resolve_run_id,
    run_dir_for,
)
from ajar.repro_source import run_repro_try
from ajar.slice_probe import run_slice_probe


def cmd_repro(args: argparse.Namespace) -> int:
    rid = resolve_run_id(args.run)
    rdir = run_dir_for(rid)
    conn = open_run_db(rid)
    try:
        if args.repro_cmd == "try":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            tpath = pathlib.Path(run["target_path"])
            oracle_dict = json.loads(args.oracle_json) if getattr(args, "oracle_json", None) else None
            patch_p = pathlib.Path(args.patch) if getattr(args, "patch", None) else None
            res = run_repro_try(
                run_dir=rdir,
                target_dir=tpath,
                cmd=args.cmd,
                patch_path=patch_p,
                build_cmd=args.build_cmd or "",
                oracle=oracle_dict,
                timeout_sec=int(args.timeout),
            )
            _emit(res, True)
            return EXIT_OK

        if args.repro_cmd == "slice-probe":
            run = conn.execute("SELECT * FROM runs LIMIT 1").fetchone()
            if run is not None and str(run["target_mode"]) != "source":
                raise AjarError("`ajar repro slice-probe` requires source mode.", EXIT_USER_ERROR)
            tpath = pathlib.Path(run["target_path"])
            patch_p = pathlib.Path(args.patch) if getattr(args, "patch", None) else None
            task_id = str(getattr(args, "task", None) or "").strip() or None
            res = run_slice_probe(
                conn,
                run_dir=rdir,
                target_dir=tpath,
                focus_locus=str(args.focus_locus),
                cmd=str(args.cmd),
                build_cmd=str(getattr(args, "build_cmd", None) or ""),
                patch_path=patch_p,
                tracer=str(getattr(args, "tracer", "auto") or "auto"),
                sanitizer_flags=bool(getattr(args, "sanitizer_flags", False)),
                record_coverage=bool(getattr(args, "record_coverage", False)),
                task_id=task_id,
                context_lines=int(getattr(args, "context_lines", 8)),
                max_rendered_lines=int(getattr(args, "max_lines", 60)),
                claim_id=str(getattr(args, "claim", None) or ""),
                timeout_sec=int(getattr(args, "timeout", 60)),
                worker_id=str(getattr(args, "worker", "worker") or "worker"),
            )
            if bool(getattr(args, "json", False)):
                _emit(res, True)
            else:
                print(res["annotated_slice"])
            return EXIT_OK

        rows = list_rows(conn, "SELECT * FROM repro_snapshots ORDER BY created_at DESC")
        _emit({"snapshots": rows}, True)
        return EXIT_OK
    finally:
        conn.close()
