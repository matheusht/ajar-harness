#!/usr/bin/env python3
"""Run the reducer-owned work queue from outside model sessions."""

from __future__ import annotations

import argparse
import shutil
import signal
from pathlib import Path

from engagement_records import canonical_json_bytes, validate_record
from work_queue_driver import DriverBudget, DriverError, NONCOMPLETION_STATUSES, SignalStop, run_driver


def emit(value: object) -> None:
    import sys

    sys.stdout.buffer.write(canonical_json_bytes(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run one target-local queue under external budgets")
    run.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="canonical absolute target repository root with no symlink components",
    )
    run.add_argument("--engagement", type=Path, required=True, help="absolute target-local engagement root")
    run.add_argument("--runtime", choices=["claude-code"], required=True)
    run.add_argument("--model", required=True, help="ordinary bounded-session model")
    run.add_argument(
        "--reviewer-model",
        action="append",
        required=True,
        help=(
            "ordered fresh-reviewer model pool; repeat for claim/regrade/Pocinator lineage "
            "independence"
        ),
    )
    run.add_argument("--max-sessions", type=int, required=True)
    run.add_argument("--max-wall-seconds", type=float, required=True)
    run.add_argument("--session-timeout-seconds", type=float, required=True)
    run.add_argument("--session-max-budget-usd", type=float)
    run.add_argument("--claude-executable", type=Path)
    run.add_argument(
        "--read-only-input",
        type=Path,
        action="append",
        default=[],
        help=(
            "absolute file or directory the launched session may read; include each distinct "
            "canonical sys.prefix/sys.base_prefix of the active driver Python, then repeat for "
            "any additional operator-declared input"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    executable = args.claude_executable
    if executable is None:
        discovered = shutil.which("claude")
        if discovered is None:
            emit({"schema_version": 1, "ok": False, "error": {"code": "driver_runtime_unavailable"}})
            return 1
        executable = Path(discovered)

    stop = SignalStop()
    prior_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        prior_handlers[signum] = signal.signal(signum, stop.handle)
    try:
        result = run_driver(
            workspace=args.workspace,
            engagement=args.engagement,
            executable=executable,
            model=args.model,
            reviewer_model=args.reviewer_model,
            budget=DriverBudget(
                max_sessions=args.max_sessions,
                max_wall_seconds=args.max_wall_seconds,
                session_timeout_seconds=args.session_timeout_seconds,
                session_max_budget_usd=args.session_max_budget_usd,
            ),
            read_only_inputs=tuple(args.read_only_input),
            stop_requested=stop,
        )
    except DriverError as exc:
        emit({"schema_version": 1, "ok": False, "error": {"code": exc.code}})
        return 1
    except Exception:
        emit({"schema_version": 1, "ok": False, "error": {"code": "driver_internal_error"}})
        return 1
    finally:
        for signum, handler in prior_handlers.items():
            signal.signal(signum, handler)

    if validate_record(result, "work-queue-driver"):
        emit({"schema_version": 1, "ok": False, "error": {"code": "driver_result_invalid"}})
        return 1
    emit(result)
    if result["status"] == "completed":
        return 0
    if result["status"] in NONCOMPLETION_STATUSES:
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
