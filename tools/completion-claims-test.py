#!/usr/bin/env python3
"""Hermetic regression checks for the completion-claim admission boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import completion_claims as claims  # noqa: E402
from engagement_records import RecordError, build_reference_index, canonical_json_bytes, sha256_file
from engagement_state import _append_kernel_event, atomic_write, base_event, compute_review_input_hash, engagement_lock, initialize_engagement, persist_scope_snapshot, read_ledger, reduce_engagement
from engagement_views import render_views, write_views
from memory_disposition import close_engagement, record_memory_disposition


SCOPE = """# Synthetic scope

## Surfaces in scope

Local fixture only.

## Benign safe-objective set

Local checks only.

## Escalation ceiling

No impact demonstration.

## Impact-demo authorization

No.

## Accounts / fixtures

Synthetic fixture.

## Authorization

- Record kernel: `decision-0006-v1`
- Operator: operator-test
- Date: 2026-08-24
- Signed: [x]
"""


class CompletionClaimsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="completion-claims-")
        self.root = Path(self.temporary.name) / "engagement"
        self.root.mkdir()
        (self.root / "scope.md").write_text(SCOPE, encoding="utf-8")
        self.initial_scope = initialize_engagement(self.root, "2026-08-24T00:00:00Z")["scope_hash"]
        self.genesis_hash = read_ledger(self.root, "event")[0]["record_hash"]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _error(self, function) -> str:
        with self.assertRaises(RecordError) as caught:
            function()
        return caught.exception.code

    def _claim_rows(self) -> tuple[tuple[str, str, int], ...]:
        with engagement_lock(self.root) as bound:
            return claims._scan_markdown(bound, self.initial_scope, self.genesis_hash)[1]

    def _claim_rows_for(self, root: Path) -> tuple[tuple[str, str, int], ...]:
        events = read_ledger(root, "event")
        with engagement_lock(root) as bound:
            return claims._scan_markdown(bound, events[0]["payload"]["scope_hash"], events[0]["record_hash"])[1]

    def _pin_manifest(self, rows: tuple[tuple[str, str, int], ...]) -> Path:
        path = Path(self.temporary.name) / "pins.json"
        pins = [{"path_sha256": row[0], "content_sha256": row[1], "claim_count": row[2]} for row in rows]
        path.write_bytes(canonical_json_bytes({"schema_version": 1, "pins": pins}))
        return path

    def _load_manifest(self, path: Path) -> dict[str, tuple[str, int]]:
        with mock.patch.object(claims, "MANIFEST_PATH", path):
            return claims.load_pins()

    @contextmanager
    def _swap_named_entry_after_eof(self, target: Path, *, occurrence: int = 1, replace: bool = True):
        """Replace ``target`` after its open descriptor reaches EOF.

        The replacement has the same size, mode, and mtime as the opened file, so only the
        directory-entry/inode binding can detect the swap.  Callers choose the EOF occurrence to
        place it at an external command's final admission rather than its initial two scans.
        """
        replacement = Path(self.temporary.name) / f"{target.name}.replacement"
        moved = Path(self.temporary.name) / f"{target.name}.opened"
        if not target.exists():
            target.write_bytes(b"safe-content\n")
        self.assertEqual(target.read_bytes(), b"safe-content\n")
        opened = target.stat()
        if replace:
            replacement.write_bytes(b"coverage_dry\n")
            os.chmod(replacement, stat.S_IMODE(opened.st_mode))
            os.utime(replacement, ns=(opened.st_atime_ns, opened.st_mtime_ns))
        target_identity = (opened.st_dev, opened.st_ino)
        real_read = os.read
        state = {"eof_count": 0, "swapped": False}

        def race_read(fd: int, amount: int) -> bytes:
            data = real_read(fd, amount)
            current = os.fstat(fd)
            if not data and (current.st_dev, current.st_ino) == target_identity:
                state["eof_count"] += 1
                if state["eof_count"] == occurrence:
                    os.rename(target, moved)
                    if replace:
                        os.rename(replacement, target)
                    state["swapped"] = True
            return data

        with mock.patch.object(claims.os, "read", side_effect=race_read):
            yield state

    @contextmanager
    def _swap_child_after_last_file_eof(self, child: Path):
        moved = Path(self.temporary.name) / f"{child.name}.opened"
        replacement = Path(self.temporary.name) / f"{child.name}.replacement"
        replacement.mkdir()
        replacement_file = replacement / "last.md"
        replacement_file.write_bytes(b"coverage_dry\n")
        target = child / "last.md"
        self.assertEqual(target.read_bytes(), b"safe-content\n")
        opened = target.stat()
        child_opened = child.stat()
        parent_opened = child.parent.stat()
        os.chmod(replacement_file, stat.S_IMODE(opened.st_mode))
        os.utime(replacement_file, ns=(opened.st_atime_ns, opened.st_mtime_ns))
        os.chmod(replacement, stat.S_IMODE(child_opened.st_mode))
        os.utime(replacement, ns=(child_opened.st_atime_ns, child_opened.st_mtime_ns))
        target_identity = (opened.st_dev, opened.st_ino)
        real_read = os.read
        state = {"swapped": False}

        def race_read(fd: int, amount: int) -> bytes:
            data = real_read(fd, amount)
            current = os.fstat(fd)
            if not data and not state["swapped"] and (current.st_dev, current.st_ino) == target_identity:
                os.rename(child, moved)
                os.rename(replacement, child)
                os.utime(child.parent, ns=(parent_opened.st_atime_ns, parent_opened.st_mtime_ns))
                self.assertEqual(claims._identity(child.parent.stat()), claims._identity(parent_opened))
                state["swapped"] = True
            return data

        with mock.patch.object(claims.os, "read", side_effect=race_read):
            yield state

    @contextmanager
    def _add_root_entry_after_last_file_eof(self, target: Path):
        self.assertEqual(target.read_bytes(), b"safe-content\n")
        opened = target.stat()
        target_identity = (opened.st_dev, opened.st_ino)
        real_read = os.read
        state = {"added": False}

        def race_read(fd: int, amount: int) -> bytes:
            data = real_read(fd, amount)
            current = os.fstat(fd)
            if not data and not state["added"] and (current.st_dev, current.st_ino) == target_identity:
                (self.root / "late-claim.md").write_bytes(b"coverage_dry\n")
                state["added"] = True
            return data

        with mock.patch.object(claims.os, "read", side_effect=race_read):
            yield state

    def _record_no_lesson(self) -> dict[str, object]:
        state = reduce_engagement(self.root)
        disposition = {
            "schema_version": 1, "disposition_id": "memory-token-close", "engagement_id": self.root.name,
            "recorded_at": "2026-08-24T00:01:10Z", "scope_hash": state["scope_hash"],
            "disposition": "no_novel_lesson", "lesson_kind": "none", "lesson_summary": None,
            "rationale": "Synthetic operator review found no reusable lesson.", "candidate_refs": [],
            "source_refs": {key: [] for key in ("event_refs", "candidate_refs", "hypothesis_refs", "attempt_refs", "artifact_refs", "review_refs", "finding_refs", "environment_refs")},
            "sanitization": {"status": "not_applicable", "secret_scan_status": "clean", "target_identifiers_removed": True, "credential_values_removed": True, "harmful_recipe_removed": True, "target_terms_checked": [], "notes": "No lesson body exists to promote."},
            "human_review": {"reviewer": {"role": "operator", "id": "operator-test"}, "reviewed_at": "2026-08-24T00:01:10Z", "decision": "no_novel_lesson", "rationale": "No novel lesson survived review.", "source_material_compared": True, "abstraction_only": True, "plane1_pr_required": True},
            "reopening_condition": None, "provenance": {"actor": {"role": "operator", "id": "operator-test"}},
        }
        proposal_path = Path(self.temporary.name) / "memory-token.json"
        proposal_path.write_bytes(canonical_json_bytes(disposition))
        record_memory_disposition(self.root, proposal_path, "operator-test")
        return state

    def _record_terminal_cleanup(self) -> None:
        state = reduce_engagement(self.root)
        _append_kernel_event(
            self.root,
            base_event(
                event_id="event-cleanup-na",
                engagement_id=self.root.name,
                recorded_at="2026-08-24T00:01:04Z",
                actor_role="operator",
                actor_id="operator-test",
                event_type="cleanup.updated",
                rationale="No live fixture cleanup exists.",
                payload={
                    "entity_id": "cleanup-none",
                    "status": "not_applicable",
                    "scope_hash": state["scope_hash"],
                    "operator_id": "operator-test",
                    "updated_at": "2026-08-24T00:01:04Z",
                    "cleanup_obligations": [{
                        "obligation_id": "cleanup-none",
                        "kind": "no_live_artifacts",
                        "status": "not_applicable",
                        "artifact_refs": [],
                        "rationale": "The synthetic engagement created no live artifacts.",
                        "closed_at": "2026-08-24T00:01:04Z",
                    }],
                },
                state_changes=[{
                    "dimension": "cleanup",
                    "entity_id": "cleanup-none",
                    "previous": None,
                    "current": "not_applicable",
                }],
            ),
        )

    def _real_dry(self) -> None:
        state = reduce_engagement(self.root)
        origin = read_ledger(self.root, "event")[0]["event_id"]
        review = {"schema_version": 1, "review_id": "review-coverage", "engagement_id": self.root.name, "review_type": "coverage", "proposed_finding_id": None, "entity_ref": self.root.name, "finding_revision": None, "recorded_at": "2026-08-24T00:01:00Z", "input_refs": [], "input_hash": "sha256:" + "0" * 64, "evidence_refs": [], "rationale": "Independent fixture review closes the empty bounded search.", "conflicting_evidence": [], "verdict": "coverage_dry", "corrections": [], "required_next_actions": [], "independence": {"reviewer_id": "reviewer-test", "reviewer_run_id": "run-coverage", "reviewer_model": "fixture", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find an omitted branch.", "originating_run_id": origin}, "bounded_space": "Empty local fixture search space.", "hypothesis_dispositions": [], "omitted_branch_challenge": "No hypotheses exist in this fixture.", "residual_uncertainty": []}
        review["input_hash"] = compute_review_input_hash(self.root, review, build_reference_index(self.root))
        path = self.root / "reviews" / "coverage.json"; path.write_bytes(canonical_json_bytes(review))
        _append_kernel_event(self.root, base_event(event_id="event-review-commit", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:01Z", actor_role="operator", actor_id="operator-test", event_type="record.committed", rationale="Commit the immutable fixture coverage review.", payload={"record_path": "reviews/coverage.json", "record_digest": sha256_file(path), "record_type": "review", "record_id": "review-coverage", "record_revision": None}))
        _append_kernel_event(self.root, base_event(event_id="event-coverage-reviewed", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:02Z", actor_role="reviewer", actor_id="reviewer-test", event_type="review.coverage_completed", rationale="Independent fixture review closes coverage.", payload={"review_type": "coverage", "verdict": "coverage_dry"}, review_refs=["review-coverage"]))
        _append_kernel_event(self.root, base_event(event_id="event-coverage-dry", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:03Z", actor_role="operator", actor_id="operator-test", event_type="coverage.status_changed", rationale="Fixture reaches dry coverage.", payload={"entity_id": self.root.name, "status": "coverage_dry", "coverage_review_ref": "event-coverage-reviewed"}, entity_refs=["event-coverage-reviewed"], state_changes=[{"dimension": "coverage", "entity_id": self.root.name, "previous": state["coverage"], "current": "coverage_dry"}]))

    def test_01_exact_boundary_tokens_only(self) -> None:
        text = "coverage_dry COVERED-DRY coverage_dryer uncovered-dry"
        self.assertEqual(len(claims.CLAIM_TOKEN.findall(text)), 2)

    def test_02_active_claim_fails(self) -> None:
        (self.root / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_03_exact_pin_allows_active_legacy_claim(self) -> None:
        (self.root / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows())
        with mock.patch.object(claims, "MANIFEST_PATH", manifest):
            self.assertEqual(claims.assert_completion_claims_clear(self.root)["coverage"], "active")

    def test_04_edit_invalidates_pin(self) -> None:
        note = self.root / "notes.md"; note.write_text("coverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows()); note.write_text("coverage_dry\nchanged\n", encoding="utf-8")
        with mock.patch.object(claims, "MANIFEST_PATH", manifest):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_05_move_invalidates_pin(self) -> None:
        note = self.root / "notes.md"; note.write_text("coverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows()); note.rename(self.root / "moved.md")
        with mock.patch.object(claims, "MANIFEST_PATH", manifest):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_06_copy_requires_its_own_pin(self) -> None:
        note = self.root / "notes.md"; note.write_text("coverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows()); shutil.copyfile(note, self.root / "copy.md")
        with mock.patch.object(claims, "MANIFEST_PATH", manifest):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_07_claim_count_is_pinned(self) -> None:
        note = self.root / "notes.md"; note.write_text("coverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows()); note.write_text("coverage_dry\ncoverage_dry\n", encoding="utf-8")
        with mock.patch.object(claims, "MANIFEST_PATH", manifest):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_08_manifest_must_be_canonical(self) -> None:
        path = Path(self.temporary.name) / "pins.json"; path.write_text('{"schema_version":1,"pins":[]}\n', encoding="utf-8")
        self.assertEqual(self._error(lambda: self._load_manifest(path)), "completion_claims_manifest_invalid")

    def test_09_manifest_closed_shape_and_duplicates_fail(self) -> None:
        path = Path(self.temporary.name) / "pins.json"; path.write_text('{"pins":[],"pins":[],"schema_version":1}\n', encoding="utf-8")
        self.assertEqual(self._error(lambda: self._load_manifest(path)), "completion_claims_manifest_invalid")

    def test_10_manifest_rejects_nonlowercase_and_boolean_count(self) -> None:
        path = Path(self.temporary.name) / "pins.json"
        pin = {"path_sha256": "sha256:" + "A" * 64, "content_sha256": "sha256:" + "b" * 64, "claim_count": True}
        path.write_bytes(canonical_json_bytes({"schema_version": 1, "pins": [pin]}))
        self.assertEqual(self._error(lambda: self._load_manifest(path)), "completion_claims_manifest_invalid")

    def test_11_current_dry_route_passes(self) -> None:
        (self.root / "notes.md").write_text("covered-dry\n", encoding="utf-8")
        with mock.patch.object(claims, "_dry_review_current", return_value=True):
            self.assertEqual(claims.assert_completion_claims_clear(self.root)["engagement_id"], self.root.name)

    def test_12_reopened_or_active_route_fails(self) -> None:
        (self.root / "notes.md").write_text("covered-dry\n", encoding="utf-8")
        with mock.patch.object(claims, "_dry_review_current", return_value=False):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_13_scope_salts_path_digest(self) -> None:
        relative = b"notes.md"
        genesis = b"sha256:" + b"c" * 64
        a = hashlib.sha256(claims.PATH_DOMAIN + b"sha256:" + b"a" * 64 + b"\0" + genesis + b"\0" + relative).hexdigest()
        b = hashlib.sha256(claims.PATH_DOMAIN + b"sha256:" + b"b" * 64 + b"\0" + genesis + b"\0" + relative).hexdigest()
        self.assertNotEqual(a, b)

    def test_14_generated_view_is_not_a_claim_but_is_snapshotted(self) -> None:
        (self.root / "progress.md").write_text("coverage_dry\n", encoding="utf-8")
        with engagement_lock(self.root) as bound:
            tree, found = claims._scan_markdown(bound, self.initial_scope, self.genesis_hash)
        self.assertEqual(found, ())
        self.assertTrue(any(row[0] == "progress.md" for row in tree))

    def test_15_symlink_markdown_fails_closed(self) -> None:
        outside = Path(self.temporary.name) / "outside.md"; outside.write_text("coverage_dry\n", encoding="utf-8")
        os.symlink(outside, self.root / "link.md")
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_tree_unsafe")

    def test_16_invalid_utf8_markdown_fails_closed(self) -> None:
        (self.root / "bad.md").write_bytes(b"\xff")
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_markdown_invalid_utf8")

    def test_17_missing_lock_is_not_created(self) -> None:
        lock = self.root / ".record-kernel.lock"; lock.unlink()
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_source_unavailable")
        self.assertFalse(lock.exists())

    def test_18_quarantine_fails_before_admission(self) -> None:
        with engagement_lock(self.root) as bound, mock.patch.object(claims, "inspect_quarantine", return_value={"quarantined": True}):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear_bound(bound)), "completion_claims_quarantined")

    def test_19_between_snapshots_fails(self) -> None:
        (self.root / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        rows = self._claim_rows(); manifest = self._pin_manifest(rows)
        real_scan = claims._scan_markdown
        calls = 0
        def altered(*args):
            nonlocal calls
            calls += 1
            tree, found = real_scan(*args)
            return ((tree if calls == 1 else tree + (("race.md", "regular", 1, 1, 1, 1, 0o100600, "sha256:" + "0" * 64),)), found)
        with mock.patch.object(claims, "MANIFEST_PATH", manifest), mock.patch.object(claims, "_scan_markdown", side_effect=altered):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_snapshot_changed")

    def test_20_readonly_cli_failure_is_sanitized_and_does_not_mutate(self) -> None:
        (self.root / "claim.md").write_text("coverage_dry\n", encoding="utf-8")
        before = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "completion_claims.py"), "--engagement", str(self.root)], capture_output=True, check=False)
        after = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'"code":"completion_claims_unjustified"', result.stdout)
        self.assertNotIn(str(self.root).encode(), result.stdout)
        self.assertNotIn(b"coverage_dry", result.stdout)
        self.assertEqual(before, after)

    def test_21_render_failure_preserves_view_bytes(self) -> None:
        (self.root / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        before = (self.root / "progress.md").read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "run-engagement.py"), "render", "--engagement", str(self.root)], capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "progress.md").read_bytes(), before)

    def test_22_stale_generated_progress_repairs_after_admission(self) -> None:
        self._real_dry()
        _append_kernel_event(self.root, base_event(event_id="event-coverage-reopen-render", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:04Z", actor_role="orchestrator", actor_id="orchestrator-test", event_type="coverage.reopened", rationale="Fixture reopens coverage before rendering.", payload={"entity_id": self.root.name, "status": "active", "reason": "Fixture reopens coverage before rendering."}, state_changes=[{"dimension": "coverage", "entity_id": self.root.name, "previous": "coverage_dry", "current": "active"}], session_id="session-render", operation_class="notebook"))
        (self.root / "progress.md").write_text("stale\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "run-engagement.py"), "render", "--engagement", str(self.root)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Coverage: `active`", (self.root / "progress.md").read_bytes())

    def test_23_close_failure_leaves_the_entire_tree_unchanged(self) -> None:
        state = reduce_engagement(self.root)
        proposal = {"schema_version": 1, "disposition_id": "memory-final", "engagement_id": self.root.name, "recorded_at": "2026-08-24T00:01:00Z", "scope_hash": state["scope_hash"], "disposition": "no_novel_lesson", "lesson_kind": "none", "lesson_summary": None, "rationale": "Synthetic operator review found no reusable lesson.", "candidate_refs": [], "source_refs": {key: [] for key in ("event_refs", "candidate_refs", "hypothesis_refs", "attempt_refs", "artifact_refs", "review_refs", "finding_refs", "environment_refs")}, "sanitization": {"status": "not_applicable", "secret_scan_status": "clean", "target_identifiers_removed": True, "credential_values_removed": True, "harmful_recipe_removed": True, "target_terms_checked": [], "notes": "No lesson body exists to promote."}, "human_review": {"reviewer": {"role": "operator", "id": "operator-test"}, "reviewed_at": "2026-08-24T00:01:00Z", "decision": "no_novel_lesson", "rationale": "No novel lesson survived review.", "source_material_compared": True, "abstraction_only": True, "plane1_pr_required": True}, "reopening_condition": None, "provenance": {"actor": {"role": "operator", "id": "operator-test"}}}
        proposal_path = Path(self.temporary.name) / "memory.json"; proposal_path.write_bytes(canonical_json_bytes(proposal))
        record_memory_disposition(self.root, proposal_path, "operator-test")
        (self.root / "ordinary.md").write_text("coverage_dry\n", encoding="utf-8")
        before = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(self._error(lambda: close_engagement(self.root, "operator-test", "Synthetic closure.", "2026-08-24T00:02:00Z")), "completion_claims_unjustified")
        after = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_24_success_cli_has_the_exact_public_output(self) -> None:
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "completion_claims.py"), "--engagement", str(self.root)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'{"code":"completion_claims_clear","valid":true}\n')

    def test_25_real_current_coverage_dry_linked_review_passes(self) -> None:
        (self.root / "claim.md").write_text("coverage_dry\n", encoding="utf-8")
        self._real_dry()
        self.assertEqual(claims.assert_completion_claims_clear(self.root)["coverage"], "coverage_dry")

    def test_26_real_reopen_invalidates_dry_claim(self) -> None:
        (self.root / "claim.md").write_text("coverage_dry\n", encoding="utf-8")
        self._real_dry()
        _append_kernel_event(self.root, base_event(event_id="event-coverage-reopen", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:04Z", actor_role="orchestrator", actor_id="orchestrator-test", event_type="coverage.reopened", rationale="Fixture reopens coverage.", payload={"entity_id": self.root.name, "status": "active", "reason": "Fixture reopens coverage."}, state_changes=[{"dimension": "coverage", "entity_id": self.root.name, "previous": "coverage_dry", "current": "active"}], session_id="session-reopen", operation_class="notebook"))
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_27_real_scope_reattestation_invalidates_old_dry(self) -> None:
        (self.root / "claim.md").write_text("coverage_dry\n", encoding="utf-8")
        self._real_dry()
        previous = reduce_engagement(self.root)["scope_hash"]
        (self.root / "scope.md").write_text(SCOPE + "\nReattested fixture scope.\n", encoding="utf-8")
        current = sha256_file(self.root / "scope.md")
        snapshot = persist_scope_snapshot(self.root, current)
        _append_kernel_event(self.root, base_event(event_id="event-scope-reattested", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:04Z", actor_role="operator", actor_id="operator-test", event_type="scope.attested", rationale="Operator reattests the changed fixture scope.", payload={"scope_hash": current, "scope_snapshot_path": snapshot, "operator_id": "operator-test", "signed_date": "2026-08-24", "record_kernel": "decision-0006-v1", "supersedes_scope_hash": previous}, entity_refs=[self.root.name]))
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_28_surrogate_markdown_path_fails_closed(self) -> None:
        with engagement_lock(self.root) as bound, mock.patch.object(claims.os, "listdir", return_value=["\udcff.MD"]):
            self.assertEqual(self._error(lambda: claims._scan_markdown(bound, self.initial_scope, self.genesis_hash)), "completion_claims_tree_path_invalid")

    def test_29_pin_binds_canonical_logical_genesis(self) -> None:
        note = self.root / "notes.md"; note.write_text("coverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows())
        clone = Path(self.temporary.name) / "clone"; shutil.copytree(self.root, clone)
        same = Path(self.temporary.name) / "same-parent" / self.root.name; same.parent.mkdir(); same.mkdir()
        (same / "scope.md").write_text(SCOPE, encoding="utf-8")
        initialize_engagement(same, "2026-08-24T00:00:00Z")
        (same / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        different_time = Path(self.temporary.name) / "different-time-parent" / self.root.name; different_time.parent.mkdir(); different_time.mkdir()
        (different_time / "scope.md").write_text(SCOPE, encoding="utf-8")
        initialize_engagement(different_time, "2026-08-24T00:00:01Z")
        (different_time / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        other = Path(self.temporary.name) / "other"; other.mkdir(); (other / "scope.md").write_text(SCOPE, encoding="utf-8")
        initialize_engagement(other, "2026-08-24T00:00:00Z")
        (other / "notes.md").write_text("coverage_dry\n", encoding="utf-8")
        self.assertEqual(self._claim_rows(), self._claim_rows_for(same))
        self.assertNotEqual(self._claim_rows(), self._claim_rows_for(different_time))
        self.assertNotEqual(self._claim_rows(), self._claim_rows_for(other))
        with mock.patch.object(claims, "MANIFEST_PATH", manifest):
            self.assertEqual(claims.assert_completion_claims_clear(clone)["coverage"], "active")
            self.assertEqual(claims.assert_completion_claims_clear(same)["coverage"], "active")
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(different_time)), "completion_claims_unjustified")
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(other)), "completion_claims_unjustified")

    def test_30_descriptor_swap_after_lstat_fails_closed(self) -> None:
        (self.root / "child").mkdir(); (self.root / "replacement").mkdir()
        real_open = claims.os.open
        swapped = False

        def race_open(name, flags, *args, **kwargs):
            nonlocal swapped
            if name == "child" and not swapped:
                swapped = True
                os.rename(self.root / "child", self.root / "old")
                os.rename(self.root / "replacement", self.root / "child")
            return real_open(name, flags, *args, **kwargs)

        with engagement_lock(self.root) as bound, mock.patch.object(claims.os, "open", side_effect=race_open):
            self.assertEqual(self._error(lambda: claims._scan_markdown(bound, self.initial_scope, self.genesis_hash)), "completion_claims_tree_changed")

    def test_31_deep_tree_cli_is_iterative_and_sanitized(self) -> None:
        root_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        fds = [root_fd]
        try:
            os.mkdir("deep", dir_fd=root_fd)
            child = os.open("deep", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0), dir_fd=root_fd); fds.append(child)
            for _ in range(claims.MAX_TREE_DEPTH + 2):
                os.mkdir("d", dir_fd=fds[-1])
                fds.append(os.open("d", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0), dir_fd=fds[-1]))
            result = subprocess.run([sys.executable, str(ROOT / "tools" / "completion_claims.py"), "--engagement", str(self.root)], capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'"code":"completion_claims_tree_depth_exceeded"', result.stdout)
            self.assertNotIn(b"Traceback", result.stdout + result.stderr)
            self.assertNotIn(str(self.root).encode(), result.stdout + result.stderr)
        finally:
            for index in range(len(fds) - 1, 0, -1):
                os.close(fds[index])
                os.rmdir("d" if index > 1 else "deep", dir_fd=fds[index - 1])
            os.close(fds[0])

    def test_32_post_admission_mutation_blocks_render_before_write(self) -> None:
        before = (self.root / "progress.md").read_bytes()
        with engagement_lock(self.root) as bound:
            admission = claims.assert_completion_claims_clear_bound(bound)
            (self.root / "after-final-scan.txt").write_text("race\n", encoding="utf-8")
            self.assertEqual(
                self._error(lambda: write_views(bound, admission.state, completion_claims_token=admission.token)),
                "completion_claims_admission_stale",
            )
        self.assertEqual((self.root / "progress.md").read_bytes(), before)

    def test_33_cooperating_writer_runs_after_lock_and_next_gate_rejects(self) -> None:
        started = threading.Event(); acquired = threading.Event()

        def writer() -> None:
            started.set()
            with engagement_lock(self.root) as bound:
                acquired.set()
                atomic_write(bound / "later.md", b"coverage_dry\n")

        with engagement_lock(self.root):
            worker = threading.Thread(target=writer)
            worker.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(acquired.wait(0.15))
        self.assertTrue(acquired.wait(2))
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_unjustified")

    def test_34_stale_close_token_writes_no_ledger_or_view_bytes(self) -> None:
        self._real_dry()
        state = self._record_no_lesson()
        with engagement_lock(self.root) as bound:
            admission = claims.assert_completion_claims_clear_bound(bound)
            atomic_write(bound / "after-close-admission.md", b"coverage_dry\n")
            close_event = base_event(
                event_id="event-close-token", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:11Z",
                actor_role="operator", actor_id="operator-test", event_type="engagement.closed",
                rationale="Synthetic closure guarded by the admission token.",
                payload={"entity_id": self.root.name, "status": "closed", "scope_hash": state["scope_hash"], "operator_id": "operator-test", "disposition_ref": "memory-token-close", "disposition_digest": reduce_engagement(bound)["memory_disposition"]["disposition_digest"]},
                entity_refs=["memory-token-close"], state_changes=[{"dimension": "engagement", "entity_id": self.root.name, "previous": "active", "current": "closed"}],
            )
            before = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
            self.assertEqual(self._error(lambda: _append_kernel_event(bound, close_event, lock_held=True, completion_claims_token=admission.token)), "completion_claims_admission_stale")
            after = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_35_repeated_tree_failures_close_every_descriptor(self) -> None:
        outside = Path(self.temporary.name) / "outside.md"; outside.write_text("coverage_dry\n", encoding="utf-8")
        os.symlink(outside, self.root / "leak-check.md")
        before = len(os.listdir("/dev/fd"))
        for _ in range(40):
            self.assertEqual(self._error(lambda: claims.assert_completion_claims_clear(self.root)), "completion_claims_tree_unsafe")
        after = len(os.listdir("/dev/fd"))
        self.assertLessEqual(after, before + 1)

    def test_36_token_bound_close_refuses_unrecorded_pinned_scope_drift(self) -> None:
        # The old scope remains reducer-valid while the drifted bytes are pin-admitted prose.
        (self.root / "scope.md").write_text(SCOPE + "\ncoverage_dry\n", encoding="utf-8")
        manifest = self._pin_manifest(self._claim_rows())
        with mock.patch.object(claims, "MANIFEST_PATH", manifest), engagement_lock(self.root) as bound:
            admission = claims.assert_completion_claims_clear_bound(bound)
            close_event = base_event(
                event_id="event-close-drift-token", engagement_id=self.root.name, recorded_at="2026-08-24T00:01:00Z",
                actor_role="operator", actor_id="operator-test", event_type="engagement.closed",
                rationale="Synthetic token-bound closure with unrecorded scope drift.",
                payload={"entity_id": self.root.name, "status": "closed", "scope_hash": self.initial_scope, "operator_id": "operator-test", "disposition_ref": "memory-none", "disposition_digest": "sha256:" + "0" * 64},
                entity_refs=["memory-none"], state_changes=[{"dimension": "engagement", "entity_id": self.root.name, "previous": "active", "current": "closed"}],
            )
            before = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
            self.assertEqual(self._error(lambda: _append_kernel_event(bound, close_event, lock_held=True, completion_claims_token=admission.token)), "completion_claims_scope_drift_unproposed")
            after = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / "scope-drafts").exists())

    def test_37_reduce_failure_preserves_snapshot_and_every_generated_view(self) -> None:
        generated = ("state.snapshot.json", *render_views(reduce_engagement(self.root)))
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"sentinel-{index}\n".encode("utf-8"))
        (self.root / "ordinary.md").write_text("coverage_dry\n", encoding="utf-8")
        before = {relative: (self.root / relative).read_bytes() for relative in generated}
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "run-engagement.py"), "reduce", "--engagement", str(self.root)],
            capture_output=True,
            check=False,
        )
        after = {relative: (self.root / relative).read_bytes() for relative in generated}
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'"code":"completion_claims_unjustified"', result.stdout)
        self.assertEqual(after, before)

    def test_38_reduce_success_publishes_current_snapshot_and_every_generated_view(self) -> None:
        expected = reduce_engagement(self.root)
        expected_views = render_views(expected)
        generated = ("state.snapshot.json", *expected_views)
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"stale-{index}\n".encode("utf-8"))
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "run-engagement.py"), "reduce", "--engagement", str(self.root)],
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "state.snapshot.json").read_bytes(), canonical_json_bytes(expected))
        self.assertEqual(
            {relative: (self.root / relative).read_bytes() for relative in expected_views},
            expected_views,
        )

    def test_39_idempotent_init_failure_preserves_snapshot_and_every_generated_view(self) -> None:
        generated = ("state.snapshot.json", *render_views(reduce_engagement(self.root)))
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"init-sentinel-{index}\n".encode("utf-8"))
        (self.root / "reports").rmdir()
        (self.root / "ordinary.md").write_text("coverage_dry\n", encoding="utf-8")
        before = {
            path.relative_to(self.root).as_posix():
                ("directory", None) if path.is_dir() else ("file", path.read_bytes())
            for path in self.root.rglob("*")
        }
        self.assertEqual(
            self._error(lambda: initialize_engagement(self.root, "2026-08-24T00:00:01Z")),
            "completion_claims_unjustified",
        )
        after = {
            path.relative_to(self.root).as_posix():
                ("directory", None) if path.is_dir() else ("file", path.read_bytes())
            for path in self.root.rglob("*")
        }
        self.assertEqual(after, before)

    def test_40_idempotent_init_success_publishes_current_snapshot_and_every_generated_view(self) -> None:
        expected = reduce_engagement(self.root)
        expected_views = render_views(expected)
        generated = ("state.snapshot.json", *expected_views)
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"init-stale-{index}\n".encode("utf-8"))
        initialized = initialize_engagement(self.root, "2026-08-24T00:00:01Z")
        self.assertEqual(initialized, expected)
        self.assertEqual((self.root / "state.snapshot.json").read_bytes(), canonical_json_bytes(expected))
        self.assertEqual(
            {relative: (self.root / relative).read_bytes() for relative in expected_views},
            expected_views,
        )

    def test_41_copied_template_inputs_reserve_completion_tokens_for_outputs(self) -> None:
        template = ROOT / "engagements" / "_TEMPLATE"
        occurrences = 0
        for path in template.rglob("*"):
            if not path.is_file() or not path.name.lower().endswith(".md"):
                continue
            relative = path.relative_to(template).as_posix()
            if relative in claims.GENERATED_VIEWS:
                continue
            occurrences += len(claims.CLAIM_TOKEN.findall(path.read_text(encoding="utf-8")))
        self.assertEqual(occurrences, 0)

    def test_42_named_entry_swap_after_open_blocks_render_publication(self) -> None:
        target = self.root / "ordinary.md"
        target.write_bytes(b"safe-content\n")
        generated = tuple(render_views(reduce_engagement(self.root)))
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"render-race-sentinel-{index}\n".encode("utf-8"))
        before = {relative: (self.root / relative).read_bytes() for relative in generated}
        with engagement_lock(self.root) as bound:
            admission = claims.assert_completion_claims_clear_bound(bound)
            with self._swap_named_entry_after_eof(target) as race:
                self.assertEqual(
                    self._error(lambda: write_views(bound, admission.state, completion_claims_token=admission.token)),
                    "completion_claims_tree_changed",
                )
        self.assertTrue(race["swapped"])
        self.assertEqual({relative: (self.root / relative).read_bytes() for relative in generated}, before)

    def test_43_named_entry_swap_after_open_blocks_reduce_publication(self) -> None:
        target = self.root / "ordinary.md"
        generated = ("state.snapshot.json", *render_views(reduce_engagement(self.root)))
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"reduce-race-sentinel-{index}\n".encode("utf-8"))
        before = {relative: (self.root / relative).read_bytes() for relative in generated}
        namespace = runpy.run_path(str(ROOT / "tools" / "run-engagement.py"), run_name="completion_claims_reduce_race_test")
        command = namespace["command_reduce"]
        command.__globals__["emit"] = lambda _value: self.fail("failed reduce must not emit success")
        with self._swap_named_entry_after_eof(target, occurrence=3) as race:
            self.assertEqual(
                self._error(lambda: command(argparse.Namespace(engagement=self.root))),
                "completion_claims_tree_changed",
            )
        self.assertTrue(race["swapped"])
        self.assertEqual({relative: (self.root / relative).read_bytes() for relative in generated}, before)

    def test_44_named_entry_swap_after_open_blocks_close_publication(self) -> None:
        self._real_dry()
        self._record_terminal_cleanup()
        self._record_no_lesson()
        target = self.root / "ordinary.md"
        published = ("events.jsonl", "state.snapshot.json", *render_views(reduce_engagement(self.root)))
        before = {relative: (self.root / relative).read_bytes() for relative in published}
        with self._swap_named_entry_after_eof(target, occurrence=3) as race:
            self.assertEqual(
                self._error(lambda: close_engagement(
                    self.root,
                    "operator-test",
                    "Synthetic close must retain the final completion-claim boundary.",
                    "2026-08-24T00:01:11Z",
                )),
                "completion_claims_tree_changed",
            )
        self.assertTrue(race["swapped"])
        self.assertEqual({relative: (self.root / relative).read_bytes() for relative in published}, before)

    def test_45_named_entry_disappearance_after_open_fails_tree_changed(self) -> None:
        target = self.root / "ordinary.md"
        with self._swap_named_entry_after_eof(target, replace=False) as race, engagement_lock(self.root) as bound:
            self.assertEqual(
                self._error(lambda: claims._scan_markdown(bound, self.initial_scope, self.genesis_hash)),
                "completion_claims_tree_changed",
            )
        self.assertTrue(race["swapped"])

    def test_46_child_rebinding_after_walk_blocks_render_publication(self) -> None:
        child = self.root / "child"
        child.mkdir()
        (child / "last.md").write_bytes(b"safe-content\n")
        generated = tuple(render_views(reduce_engagement(self.root)))
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"child-race-sentinel-{index}\n".encode("utf-8"))
        before = {relative: (self.root / relative).read_bytes() for relative in generated}
        with engagement_lock(self.root) as bound:
            admission = claims.assert_completion_claims_clear_bound(bound)
            with self._swap_child_after_last_file_eof(child) as race:
                self.assertEqual(
                    self._error(lambda: write_views(bound, admission.state, completion_claims_token=admission.token)),
                    "completion_claims_tree_changed",
                )
        self.assertTrue(race["swapped"])
        self.assertEqual({relative: (self.root / relative).read_bytes() for relative in generated}, before)

    def test_47_late_root_addition_blocks_render_publication(self) -> None:
        target = self.root / "zz-last.md"
        target.write_bytes(b"safe-content\n")
        generated = tuple(render_views(reduce_engagement(self.root)))
        for index, relative in enumerate(generated):
            atomic_write(self.root / relative, f"root-race-sentinel-{index}\n".encode("utf-8"))
        before = {relative: (self.root / relative).read_bytes() for relative in generated}
        with engagement_lock(self.root) as bound:
            admission = claims.assert_completion_claims_clear_bound(bound)
            with self._add_root_entry_after_last_file_eof(target) as race:
                self.assertEqual(
                    self._error(lambda: write_views(bound, admission.state, completion_claims_token=admission.token)),
                    "completion_claims_tree_changed",
                )
        self.assertTrue(race["added"])
        self.assertEqual({relative: (self.root / relative).read_bytes() for relative in generated}, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
