#!/usr/bin/env python3
"""Post and read bounded advisory notices through the existing record kernel."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from engagement_records import RecordError, load_json
from engagement_state import _append_kernel_event, base_event, read_ledger
from task_notice import compile_projection, validate_notice


def post_notice(engagement: Path, notice: dict[str, Any], *, recorded_at: str) -> dict[str, Any]:
    events = read_ledger(engagement, "event")
    predecessor = notice.get("predecessor_event_ref")
    uid, sid = os.getuid(), os.getsid(0)
    actor_id, session_id = f"local-uid-{uid}:broker", f"session-posix-{uid}-{sid}"
    event = base_event(
        event_id=f"event-task-notice-{notice.get('notice_id', 'invalid')}", engagement_id=events[0]["engagement_id"],
        recorded_at=recorded_at, actor_role="broker", actor_id=actor_id,
        event_type="observation.recorded", rationale="Retain one bounded advisory task notice.",
        payload={"entity_id": str(notice.get("notice_id", "invalid")), "entity_type": "task_notice", "status": "recorded", "task_notice": notice},
        entity_refs=[notice.get("source_event_ref")] + ([predecessor] if predecessor else []),
        evidence_refs=[], session_id=session_id, operation_class="notebook",
    )
    validate_notice(events, event)
    return _append_kernel_event(engagement, event)


def compile_notices(engagement: Path, *, task_id: str, after_sequence: int = 0) -> dict[str, Any]:
    from engagement_state import reduce_engagement
    reduce_engagement(engagement)
    return compile_projection(read_ledger(engagement, "event"), task_id=task_id, after_sequence=after_sequence)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    post = sub.add_parser("post", help="append one validated advisory notice")
    post.add_argument("--engagement", type=Path, required=True); post.add_argument("--notice", type=Path, required=True)
    post.add_argument("--recorded-at", required=True)
    read = sub.add_parser("read", help="compile a filtered notice projection")
    read.add_argument("--engagement", type=Path, required=True); read.add_argument("--task-id", required=True); read.add_argument("--after-sequence", type=int, default=0)
    args = parser.parse_args()
    result = post_notice(args.engagement.absolute(), load_json(args.notice), recorded_at=args.recorded_at) if args.command == "post" else compile_notices(args.engagement.absolute(), task_id=args.task_id, after_sequence=args.after_sequence)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecordError as exc:
        print(json.dumps({"valid": False, "error": exc.as_dict()}, sort_keys=True, separators=(",", ":")))
        raise SystemExit(1)
