#!/usr/bin/env python3
"""Hermetic regression checks for the completion-claim admission boundary."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import completion_claims as claims  # noqa: E402
from engagement_records import RecordError, build_reference_index, canonical_json_bytes, sha256_file
from engagement_state import _append_kernel_event, base_event, compute_review_input_hash, engagement_lock, initialize_engagement, persist_scope_snapshot, read_ledger, reduce_engagement
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

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _error(self, function) -> str:
        with self.assertRaises(RecordError) as caught:
            function()
        return caught.exception.code

    def _claim_rows(self) -> tuple[tuple[str, str, int], ...]:
        with engagement_lock(self.root) as bound:
            return claims._scan_markdown(bound, self.initial_scope)[1]

    def _pin_manifest(self, rows: tuple[tuple[str, str, int], ...]) -> Path:
        path = Path(self.temporary.name) / "pins.json"
        pins = [{"path_sha256": row[0], "content_sha256": row[1], "claim_count": row[2]} for row in rows]
        path.write_bytes(canonical_json_bytes({"schema_version": 1, "pins": pins}))
        return path

    def _load_manifest(self, path: Path) -> dict[str, tuple[str, int]]:
        with mock.patch.object(claims, "MANIFEST_PATH", path):
            return claims.load_pins()

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
        a = hashlib.sha256(claims.PATH_DOMAIN + b"sha256:" + b"a" * 64 + b"\0" + relative).hexdigest()
        b = hashlib.sha256(claims.PATH_DOMAIN + b"sha256:" + b"b" * 64 + b"\0" + relative).hexdigest()
        self.assertNotEqual(a, b)

    def test_14_generated_view_is_not_a_claim_but_is_snapshotted(self) -> None:
        (self.root / "progress.md").write_text("coverage_dry\n", encoding="utf-8")
        with engagement_lock(self.root) as bound:
            tree, found = claims._scan_markdown(bound, self.initial_scope)
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
            self.assertEqual(self._error(lambda: claims._scan_markdown(bound, self.initial_scope)), "completion_claims_tree_path_invalid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
