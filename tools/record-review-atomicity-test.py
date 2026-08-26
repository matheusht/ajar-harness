#!/usr/bin/env python3
"""Focused transaction tests for signed typed-review admission."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from engagement_records import (
    build_reference_index,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from engagement_state import (
    _append_kernel_event,
    atomic_write,
    base_event,
    compute_review_input_hash,
    initialize_engagement,
    reduce_engagement,
)
from engagement_views import render_views


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run-engagement.py"


SCOPE = """# Scope - record-review atomicity fixture

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic record transaction test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `none`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {reviewer_signers_digest}
## Authorization
- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- Operator: operator-atomicity-test
- Date: 2026-08-25
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


class RecordReviewAtomicityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="record-review-atomicity-")
        self.root = Path(self.temporary.name).resolve()
        self.key = self.root / "reviewer-ed25519"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        public_parts = self.key.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.allowed_signers = self.root / "reviewer-allowed-signers"
        self.allowed_signers.write_text(
            f"reviewer-atomicity {public_parts[0]} {public_parts[1]}\n",
            encoding="utf-8",
        )
        self.engagement = self.root / "target" / "engagements" / "atomicity-fixture"
        self.engagement.mkdir(parents=True)
        self.engagement.joinpath("scope.md").write_text(
            SCOPE.format(reviewer_signers_digest=sha256_file(self.allowed_signers)),
            encoding="utf-8",
        )
        initialize_engagement(self.engagement, "2026-08-25T12:00:00Z")
        _append_kernel_event(
            self.engagement,
            base_event(
                event_id="event-review-origin",
                engagement_id=self.engagement.name,
                recorded_at="2026-08-25T12:00:01Z",
                actor_role="orchestrator",
                actor_id="orchestrator-atomicity",
                event_type="observation.recorded",
                rationale="Establish model-authored material for an independent cold review.",
                payload={
                    "entity_id": "observation-review-origin",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-review-origin",
                operation_class="notebook",
                model="fixture-origin-model",
                provider="fixture-provider",
            ),
        )
        uid, sid = os.getuid(), os.getsid(0)
        self.broker_id = f"local-uid-{uid}:broker"
        self.broker_session = f"session-posix-{uid}-{sid}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _review(
        self,
        review_id: str,
        *,
        review_type: str = "coverage",
        verdict: str = "blocked",
        reviewer_run_id: str | None = None,
        recorded_at: str = "2026-08-25T12:01:00Z",
    ) -> dict[str, object]:
        claim = review_type == "claim_adjudication"
        review: dict[str, object] = {
            "schema_version": 1,
            "review_id": review_id,
            "engagement_id": self.engagement.name,
            "review_type": review_type,
            "proposed_finding_id": "F-atomicity" if claim else None,
            "recorded_at": recorded_at,
            "entity_ref": "F-atomicity" if claim else self.engagement.name,
            "finding_revision": None,
            "input_refs": [],
            "input_hash": "sha256:" + "0" * 64,
            "evidence_refs": [],
            "rationale": "Independent fixture review records only the bounded local evidence.",
            "conflicting_evidence": [],
            "verdict": verdict,
            "corrections": [],
            "required_next_actions": ["Resolve the local blocker."] if verdict == "blocked" else [],
            "independence": {
                "reviewer_id": "reviewer-atomicity",
                "reviewer_run_id": reviewer_run_id or f"run-{review_id}",
                "reviewer_session_id": f"session-{review_id}",
                "reviewer_model": "fixture-independent-reviewer",
                "fresh_context": True,
                "prior_verdict_visible": False,
                "disconfirming_objective": "Find an omitted branch or refute the bounded claim.",
                "originating_run_id": "event-review-origin",
            },
        }
        if review_type == "coverage":
            review.update(
                {
                    "bounded_space": "The empty local fixture search space.",
                    "hypothesis_dispositions": [],
                    "omitted_branch_challenge": "No undeclared branch exists in the fixture.",
                    "residual_uncertainty": ["The declared local blocker remains."],
                }
            )
        review["input_hash"] = compute_review_input_hash(
            self.engagement,
            review,
            build_reference_index(self.engagement),
        )
        return review

    def _event(
        self,
        review: dict[str, object],
        *,
        event_id: str | None = None,
        event_at: str = "2026-08-25T12:01:01Z",
    ) -> dict[str, object]:
        review_id = str(review["review_id"])
        reviewer_id = str(review["independence"]["reviewer_id"])
        if review["review_type"] == "claim_adjudication":
            return base_event(
                event_id=event_id or f"event-{review_id}",
                engagement_id=self.engagement.name,
                recorded_at=event_at,
                actor_role="broker",
                actor_id=self.broker_id,
                event_type="claim.adjudicated",
                rationale="Record the independently adjudicated bounded claim.",
                payload={
                    "entity_id": "F-atomicity",
                    "status": review["verdict"],
                    "review_ref": review_id,
                    "reviewer_id": reviewer_id,
                    "review_digest": sha256_bytes(canonical_json_bytes(review)),
                },
                review_refs=[review_id],
                state_changes=[
                    {
                        "dimension": "claim",
                        "entity_id": "F-atomicity",
                        "previous": None,
                        "current": review["verdict"],
                    }
                ],
                session_id=self.broker_session,
                operation_class="notebook",
            )
        return base_event(
            event_id=event_id or f"event-{review_id}",
            engagement_id=self.engagement.name,
            recorded_at=event_at,
            actor_role="broker",
            actor_id=self.broker_id,
            event_type="review.coverage_completed",
            rationale="Record the independent cold coverage review.",
            payload={
                "review_type": "coverage",
                "verdict": review["verdict"],
                "review_ref": review_id,
                "reviewer_id": reviewer_id,
            },
            review_refs=[review_id],
            session_id=self.broker_session,
            operation_class="notebook",
        )

    def _write_signed_review(self, review: dict[str, object]) -> tuple[Path, Path]:
        review_path = self.root / f"{review['review_id']}.json"
        review_path.write_bytes(canonical_json_bytes(review))
        signature_path = Path(str(review_path) + ".sig")
        signature_path.unlink(missing_ok=True)
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-q",
                "-Y",
                "sign",
                "-f",
                str(self.key),
                "-n",
                "llm-redteam-harness-review-v1",
                str(review_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return review_path, signature_path

    def _run(self, review: dict[str, object], event: dict[str, object]) -> subprocess.CompletedProcess[str]:
        review_path, signature_path = self._write_signed_review(review)
        event_path = self.root / f"{review['review_id']}.event.json"
        event_path.write_bytes(canonical_json_bytes(event))
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "record-review",
                "--engagement",
                str(self.engagement),
                "--file",
                str(review_path),
                "--event",
                str(event_path),
                "--actor-id",
                self.broker_id,
                "--session-id",
                self.broker_session,
                "--signature",
                str(signature_path),
                "--allowed-signers",
                str(self.allowed_signers),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def _durable_projection(self) -> dict[str, bytes]:
        snapshot_bytes = self.engagement.joinpath("state.snapshot.json").read_bytes()
        state = json.loads(snapshot_bytes)
        paths = {
            "events.jsonl",
            "state.snapshot.json",
            *render_views(state).keys(),
        }
        paths.update(
            path.relative_to(self.engagement).as_posix()
            for path in self.engagement.joinpath("reviews").rglob("*")
            if path.is_file()
        )
        return {
            relative: self.engagement.joinpath(relative).read_bytes()
            for relative in sorted(paths)
        }

    def _assert_rejected_without_write(
        self,
        review: dict[str, object],
        event: dict[str, object],
    ) -> subprocess.CompletedProcess[str]:
        before = self._durable_projection()
        result = self._run(review, event)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._durable_projection(), before, result.stdout + result.stderr)
        return result

    def test_wrong_claim_review_digest_is_prewrite_rejection(self) -> None:
        review = self._review(
            "review-claim-wrong-digest",
            review_type="claim_adjudication",
            verdict="supported",
        )
        event = self._event(review)
        event["payload"]["review_digest"] = "sha256:" + "f" * 64
        self._assert_rejected_without_write(review, event)

    def test_wrong_coverage_review_type_is_prewrite_rejection(self) -> None:
        review = self._review("review-coverage-wrong-type")
        event = self._event(review)
        event["payload"]["review_type"] = "claim_adjudication"
        self._assert_rejected_without_write(review, event)

    def test_duplicate_reviewer_run_id_is_prewrite_rejection(self) -> None:
        first = self._review(
            "review-coverage-first",
            reviewer_run_id="run-reviewer-reused",
        )
        first_result = self._run(first, self._event(first))
        self.assertEqual(first_result.returncode, 0, first_result.stdout + first_result.stderr)
        duplicate = self._review(
            "review-coverage-duplicate-run",
            reviewer_run_id="run-reviewer-reused",
            recorded_at="2026-08-25T12:02:00Z",
        )
        self._assert_rejected_without_write(
            duplicate,
            self._event(duplicate, event_at="2026-08-25T12:02:01Z"),
        )

    def test_typed_event_id_collision_is_prewrite_rejection(self) -> None:
        collision_id = "event-review-coverage-event-collision"
        _append_kernel_event(
            self.engagement,
            base_event(
                event_id=collision_id,
                engagement_id=self.engagement.name,
                recorded_at="2026-08-25T12:00:30Z",
                actor_role="orchestrator",
                actor_id="orchestrator-atomicity",
                event_type="observation.recorded",
                rationale="Occupy the prospective typed review event identifier.",
                payload={
                    "entity_id": "observation-event-collision",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-event-collision",
                operation_class="notebook",
                model="fixture-origin-model",
                provider="fixture-provider",
            ),
        )
        review = self._review("review-coverage-event-collision")
        self._assert_rejected_without_write(
            review,
            self._event(review, event_id=collision_id),
        )

    def test_late_review_verdict_mismatch_is_prewrite_rejection(self) -> None:
        review = self._review("review-coverage-verdict-mismatch", verdict="blocked")
        event = self._event(review)
        event["payload"]["verdict"] = "coverage_dry"
        self._assert_rejected_without_write(review, event)

    def test_same_origin_model_is_prewrite_rejection(self) -> None:
        review = self._review("review-coverage-same-origin-model")
        review["independence"]["reviewer_model"] = "fixture-origin-model"
        self._assert_rejected_without_write(review, self._event(review))

    def test_staging_rejects_source_symlink_without_following_it(self) -> None:
        outside = self.root / "outside-symlink-target"
        outside.write_bytes(b"outside bytes must never enter review staging\n")
        self.engagement.joinpath("staging-source-link").symlink_to(outside)
        review = self._review("review-coverage-source-symlink")
        result = self._assert_rejected_without_write(review, self._event(review))
        payload = json.loads(result.stdout)
        self.assertEqual(payload["error"]["code"], "record_review_staging_source_unsafe")
        self.assertEqual(outside.read_bytes(), b"outside bytes must never enter review staging\n")

    def test_staging_rejects_special_source_file(self) -> None:
        os.mkfifo(self.engagement / "staging-source-fifo", 0o600)
        review = self._review("review-coverage-source-fifo")
        result = self._assert_rejected_without_write(review, self._event(review))
        payload = json.loads(result.stdout)
        self.assertEqual(payload["error"]["code"], "record_review_staging_source_unsafe")

    def test_large_sparse_source_is_staged_without_materializing_holes(self) -> None:
        sparse_path = self.engagement / "large-sparse-fixture.bin"
        sparse_size = 4 * 1024 * 1024 * 1024
        sparse_fd = os.open(sparse_path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.ftruncate(sparse_fd, sparse_size)
            os.pwrite(sparse_fd, b"first", 0)
            os.pwrite(sparse_fd, b"last", sparse_size - 4)
            os.fsync(sparse_fd)
            before = os.fstat(sparse_fd)
        finally:
            os.close(sparse_fd)
        review = self._review("review-coverage-large-sparse")
        started = time.monotonic()
        result = self._run(review, self._event(review))
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = sparse_path.stat()
        self.assertEqual((after.st_size, after.st_blocks), (before.st_size, before.st_blocks))
        with sparse_path.open("rb") as stream:
            self.assertEqual(stream.read(5), b"first")
            stream.seek(sparse_size - 4)
            self.assertEqual(stream.read(4), b"last")
        self.assertLess(elapsed, 15.0, f"sparse staging took {elapsed:.2f}s")

    def test_valid_transaction_and_identical_retry_are_idempotent(self) -> None:
        review = self._review("review-coverage-valid")
        event = self._event(review)
        result = self._run(review, event)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        committed = self._durable_projection()
        retry = self._run(review, event)
        self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
        self.assertEqual(self._durable_projection(), committed)

    def test_identical_review_and_commit_resume_before_typed_event(self) -> None:
        review = self._review("review-coverage-partial-resume")
        review_data = canonical_json_bytes(review)
        relative = f"reviews/{review['review_id']}.json"
        atomic_write(self.engagement / relative, review_data)
        _append_kernel_event(
            self.engagement,
            base_event(
                event_id=f"event-{review['review_id']}-commit",
                engagement_id=self.engagement.name,
                recorded_at="2026-08-25T12:01:01Z",
                actor_role="broker",
                actor_id=self.broker_id,
                event_type="record.committed",
                rationale="Commit immutable externally-produced independent review.",
                payload={
                    "record_path": relative,
                    "record_digest": sha256_bytes(review_data),
                    "record_type": "review",
                    "record_id": review["review_id"],
                    "record_revision": None,
                },
                session_id=self.broker_session,
                operation_class="notebook",
            ),
        )
        before_count = reduce_engagement(self.engagement)["event_count"]
        event = self._event(review, event_at="2026-08-25T12:01:02Z")
        result = self._run(review, event)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(reduce_engagement(self.engagement)["event_count"], before_count + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
