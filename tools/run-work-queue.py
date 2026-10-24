#!/usr/bin/env python3
"""Run the explicit legacy work queue from outside model sessions.

New local source research uses tools/native_research.py.
"""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

from docker_session_runtime import DockerRuntimeLimits
from engagement_records import canonical_json_bytes, validate_record
from work_queue_driver import (
    DockerQueueBackend,
    DriverBudget,
    DriverError,
    NONCOMPLETION_STATUSES,
    SignalStop,
    run_driver,
)


def emit(value: object) -> None:
    import sys

    sys.stdout.buffer.write(canonical_json_bytes(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run one legacy target-local queue under external budgets")
    run.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="canonical absolute target repository root with no symlink components",
    )
    run.add_argument("--engagement", type=Path, required=True, help="absolute target-local engagement root")
    run.add_argument("--runtime", choices=["claude-code"], required=True)
    run.add_argument(
        "--session-backend",
        choices=["docker"],
        required=True,
        help="required strong isolation backend; no implicit host-process fallback",
    )
    run.add_argument("--model", required=True, help="ordinary bounded-session model")
    run.add_argument(
        "--reviewer-model",
        action="append",
        required=True,
        help=(
            "legacy queue fresh-reviewer model pool; repeat for claim/regrade/Pocinator lineage "
            "independence"
        ),
    )
    run.add_argument("--max-sessions", type=int, required=True)
    run.add_argument("--max-wall-seconds", type=float, required=True)
    run.add_argument("--session-timeout-seconds", type=float, required=True)
    run.add_argument("--session-max-budget-usd", type=float)
    run.add_argument(
        "--corpus-enumeration-ref",
        help="registered frozen corpus manifest artifact used if a budget boundary is declared",
    )
    run.add_argument(
        "--claude-executable",
        type=Path,
        required=True,
        help="absolute Claude executable path inside the pinned container image",
    )
    run.add_argument("--docker-image", required=True, help="immutable repository@sha256 image")
    run.add_argument(
        "--docker-python-executable",
        required=True,
        help="absolute Python executable path inside the pinned image",
    )
    run.add_argument("--docker-executable", type=Path, required=True)
    run.add_argument("--docker-memory-bytes", type=int, required=True)
    run.add_argument("--docker-cpus", type=float, required=True)
    run.add_argument("--docker-pids", type=int, required=True)
    run.add_argument("--docker-nofile", type=int, required=True)
    run.add_argument("--docker-scratch-bytes", type=int, required=True)
    run.add_argument("--docker-scratch-inodes", type=int, required=True)
    run.add_argument("--docker-shm-bytes", type=int, required=True)
    run.add_argument("--docker-shm-inodes", type=int, required=True)
    run.add_argument(
        "--read-only-input",
        type=Path,
        action="append",
        default=[],
        help=(
            "canonical absolute regular file the container session may read; repeat in the "
            "desired deterministic /inputs/000, /inputs/001, ... mount order"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    docker_backend = DockerQueueBackend(
        image=args.docker_image,
        python_executable=args.docker_python_executable,
        docker_executable=args.docker_executable,
        limits=DockerRuntimeLimits(
            memory_bytes=args.docker_memory_bytes,
            cpu_count=args.docker_cpus,
            pids=args.docker_pids,
            nofile=args.docker_nofile,
            scratch_bytes=args.docker_scratch_bytes,
            scratch_inodes=args.docker_scratch_inodes,
            shm_bytes=args.docker_shm_bytes,
            shm_inodes=args.docker_shm_inodes,
        ),
    )

    stop = SignalStop()
    prior_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        prior_handlers[signum] = signal.signal(signum, stop.handle)
    try:
        result = run_driver(
            workspace=args.workspace,
            engagement=args.engagement,
            executable=args.claude_executable,
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
            docker_backend=docker_backend,
            corpus_enumeration_ref=args.corpus_enumeration_ref,
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
