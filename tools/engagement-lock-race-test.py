#!/usr/bin/env python3
"""Regression: a locked transaction never follows an engagement pathname ABA."""

from __future__ import annotations

import fcntl
import io
import os
import shutil
import tempfile
import threading
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import engagement_state
import finding_lifecycle
from engagement_quarantine import MARKER_RELATIVE, canonical_marker
from engagement_records import canonical_json_bytes
from engagement_state import append_ledger_record, base_event, initialize_engagement


def _scope() -> str:
    return """# Scope - synthetic bound-lock race test

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic transaction binding test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
## Accounts / fixtures
- None.
## Authorization
- Operator allowed signers SHA256: sha256:1111111111111111111111111111111111111111111111111111111111111111
- Operator: fixture-operator
- Date: 2026-08-23
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


def _engagement(path: Path) -> Path:
    path.mkdir()
    path.joinpath("scope.md").write_text(_scope(), encoding="utf-8")
    initialize_engagement(path, "2026-08-23T00:00:00Z")
    return path


def _install_marker(engagement: Path) -> None:
    marker = engagement / MARKER_RELATIVE
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(
        canonical_marker(
            {
                "schema_version": 1,
                "status": "quarantined",
                "operator_id": "fixture-operator",
                "reason": "operator-integrity-review",
                "recorded_at": "2026-08-23T00:00:01Z",
                "authority_challenge_digest": "sha256:" + "2" * 64,
                "record_fingerprint": "sha256:" + "3" * 64,
            }
        )
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="engagement-lock-race-") as temporary:
        root = Path(temporary).resolve()
        live = _engagement(root / "synthetic-live")
        quarantined = root / "synthetic-quarantined-copy"
        shutil.copytree(live, quarantined)
        _install_marker(quarantined)
        moved_live = root / "synthetic-live-moved"
        quarantined_before = quarantined.joinpath("events.jsonl").read_bytes()

        original_guard = engagement_state.require_not_quarantined
        swapped = False

        def swap_after_guard(engagement: Path) -> None:
            nonlocal swapped
            original_guard(engagement)
            if swapped:
                return
            swapped = True
            live.rename(moved_live)
            quarantined.rename(live)

        engagement_state.require_not_quarantined = swap_after_guard
        try:
            append_ledger_record(
                live,
                "event",
                base_event(
                    event_id="event-bound-lock-race",
                    engagement_id=live.name,
                    recorded_at="2026-08-23T00:00:02Z",
                    actor_role="orchestrator",
                    actor_id="fixture-orchestrator",
                    event_type="observation.recorded",
                    rationale="Prove the transaction stays on the directory inode it locked.",
                    payload={
                        "entity_id": "fixture-bound-lock-race",
                        "entity_type": "observation",
                        "status": "recorded",
                    },
                    session_id="fixture-session",
                    operation_class="notebook",
                ),
            )
        except Exception as exc:
            failure = f"append failed unexpectedly: {type(exc).__name__}"
        else:
            failure = ""
        finally:
            engagement_state.require_not_quarantined = original_guard
            if swapped:
                live.rename(quarantined)
                moved_live.rename(live)

        quarantined_after = quarantined.joinpath("events.jsonl").read_bytes()
        live_after = live.joinpath("events.jsonl").read_bytes()
        aba_passed = (
            not failure
            and swapped
            and quarantined_after == quarantined_before
            and b"event-bound-lock-race" in live_after
        )

        marked_without_lock = root / "synthetic-marked-without-lock"
        shutil.copytree(live, marked_without_lock)
        marked_without_lock.joinpath(".record-kernel.lock").unlink()
        _install_marker(marked_without_lock)
        entries_before = sorted(
            path.relative_to(marked_without_lock).as_posix()
            for path in marked_without_lock.rglob("*")
        )
        try:
            append_ledger_record(
                marked_without_lock,
                "event",
                base_event(
                    event_id="event-marked-lock-creation",
                    engagement_id=live.name,
                    recorded_at="2026-08-23T00:00:03Z",
                    actor_role="orchestrator",
                    actor_id="fixture-orchestrator",
                    event_type="observation.recorded",
                    rationale="A denied operation must not create its coordination lock.",
                    payload={
                        "entity_id": "fixture-marked-lock-creation",
                        "entity_type": "observation",
                        "status": "recorded",
                    },
                    session_id="fixture-session",
                    operation_class="notebook",
                ),
            )
        except Exception as exc:
            lock_creation_refused = getattr(exc, "code", None) == "engagement_quarantined"
        else:
            lock_creation_refused = False
        entries_after = sorted(
            path.relative_to(marked_without_lock).as_posix()
            for path in marked_without_lock.rglob("*")
        )
        nonmutating_refusal = (
            lock_creation_refused
            and entries_after == entries_before
            and not marked_without_lock.joinpath(".record-kernel.lock").exists()
        )

        # A marker created after the optimistic precheck but while a transaction is waiting for
        # the engagement lock must win. The post-flock check is the linearization boundary.
        marker_race = _engagement(root / "synthetic-post-flock-marker")
        marker_race_before = marker_race.joinpath("events.jsonl").read_bytes()
        lock_fd = os.open(marker_race / ".record-kernel.lock", os.O_RDWR)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        precheck_complete = threading.Event()
        worker_done = threading.Event()
        worker_error: list[str | None] = []
        original_inspect = engagement_state.inspect_quarantine

        def signal_precheck(engagement: Path) -> dict[str, object]:
            result = original_inspect(engagement)
            if threading.current_thread().name == "post-flock-marker-worker" and not result["quarantined"]:
                precheck_complete.set()
            return result

        def blocked_append() -> None:
            try:
                append_ledger_record(
                    marker_race,
                    "event",
                    base_event(
                        event_id="event-post-flock-marker-race",
                        engagement_id=marker_race.name,
                        recorded_at="2026-08-23T00:00:04Z",
                        actor_role="orchestrator",
                        actor_id="fixture-orchestrator",
                        event_type="observation.recorded",
                        rationale="A newly installed marker wins before a waiting append mutates evidence.",
                        payload={
                            "entity_id": "fixture-post-flock-marker-race",
                            "entity_type": "observation",
                            "status": "recorded",
                        },
                        session_id="fixture-session",
                        operation_class="notebook",
                    ),
                )
            except Exception as exc:
                worker_error.append(getattr(exc, "code", None))
            else:
                worker_error.append(None)
            finally:
                worker_done.set()

        engagement_state.inspect_quarantine = signal_precheck
        worker = threading.Thread(target=blocked_append, name="post-flock-marker-worker")
        try:
            worker.start()
            reached_precheck = precheck_complete.wait(timeout=5)
            if reached_precheck:
                _install_marker(marker_race)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        worker.join(timeout=5)
        engagement_state.inspect_quarantine = original_inspect
        marker_wins = (
            reached_precheck
            and worker_done.is_set()
            and worker_error == ["engagement_quarantined"]
            and marker_race.joinpath("events.jsonl").read_bytes() == marker_race_before
        )

        lifecycle_live = _engagement(root / "synthetic-lifecycle-live")
        lifecycle_package = lifecycle_live / "findings" / "F-BOUND"
        lifecycle_package.mkdir()
        lifecycle_package.joinpath("finding.json").write_bytes(b"{}\n")
        lifecycle_quarantined = root / "synthetic-lifecycle-quarantined"
        shutil.copytree(lifecycle_live, lifecycle_quarantined)
        _install_marker(lifecycle_quarantined)
        lifecycle_moved = root / "synthetic-lifecycle-original-moved"
        quarantined_tree_before = {
            path.relative_to(lifecycle_quarantined).as_posix(): path.read_bytes()
            for path in lifecycle_quarantined.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        original_move = finding_lifecycle._bound_move
        lifecycle_swapped = False

        def swap_before_lifecycle_move(*args, **kwargs):
            nonlocal lifecycle_swapped
            lifecycle_live.rename(lifecycle_moved)
            lifecycle_quarantined.rename(lifecycle_live)
            lifecycle_swapped = True
            try:
                return original_move(*args, **kwargs)
            finally:
                lifecycle_live.rename(lifecycle_quarantined)
                lifecycle_moved.rename(lifecycle_live)

        finding_lifecycle._bound_move = swap_before_lifecycle_move
        try:
            with redirect_stdout(io.StringIO()):
                lifecycle_result = finding_lifecycle.cmd_demote(
                    SimpleNamespace(
                        engagement=str(lifecycle_live),
                        finding_id="F-BOUND",
                        actor="fixture-orchestrator",
                        reason="Exercise the bound lifecycle mutation seam.",
                    )
                )
        finally:
            finding_lifecycle._bound_move = original_move
        quarantined_tree_after = {
            path.relative_to(lifecycle_quarantined).as_posix(): path.read_bytes()
            for path in lifecycle_quarantined.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        lifecycle_bound = (
            lifecycle_result == 0
            and lifecycle_swapped
            and quarantined_tree_after == quarantined_tree_before
            and lifecycle_live.joinpath("unproven", "F-BOUND", "finding.json").is_file()
            and not lifecycle_live.joinpath("findings", "F-BOUND").exists()
        )

        passed = aba_passed and nonmutating_refusal and marker_wins and lifecycle_bound
        print(
            f"  {'ok  ' if aba_passed else 'FAIL'} locked append stays on one directory inode "
            "across a pathname ABA"
        )
        print(
            f"  {'ok  ' if nonmutating_refusal else 'FAIL'} quarantined source without a lock "
            "is refused without creating one"
        )
        print(
            f"  {'ok  ' if marker_wins else 'FAIL'} marker installed while append waits "
            "wins at the post-flock boundary"
        )
        print(
            f"  {'ok  ' if lifecycle_bound else 'FAIL'} lifecycle mutation remains bound "
            "across a quarantined pathname ABA"
        )
        if failure:
            print(f"       {failure}")
        if quarantined_after != quarantined_before:
            print("       quarantined ledger bytes changed")
        print("ENGAGEMENT-LOCK-RACE: " + ("PASS" if passed else "FAIL"))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
