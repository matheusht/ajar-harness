#!/usr/bin/env python3
"""Focused adversarial tests for reducer-owned work-queue mutation predicates."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from driver_action_admission import _evaluate_predicate
from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from engagement_state import _project_pocinator_proof
from work_queue_admission import build_action_admission


class WorkQueueAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="work-queue-admission-test-")
        self.root = Path(self.temporary.name)
        self.engagement = self.root / "target" / "engagements" / "fixture"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _evaluate(
        self,
        predicate: dict,
        proposal: dict,
        event: dict | None = None,
    ) -> None:
        proposal_path = self.root / "proposal.json"
        proposal_path.write_bytes(canonical_json_bytes(proposal))
        arguments = ["--file", str(proposal_path)]
        if event is not None:
            event_path = self.root / "event.json"
            event_path.write_bytes(canonical_json_bytes(event))
            arguments.extend(["--event", str(event_path)])
        _evaluate_predicate(predicate, arguments)

    @staticmethod
    def _review_item(item_id: str, finding_id: str) -> dict:
        return {
            "class": "review_obligation_open",
            "entity": {"type": "review_obligation", "id": item_id, "detail": finding_id},
        }

    @staticmethod
    def _finding_item(item_class: str, finding_id: str) -> dict:
        return {
            "class": item_class,
            "entity": {"type": "finding", "id": finding_id, "detail": None},
        }

    @staticmethod
    def _review_documents(
        review_type: str,
        finding_id: str,
        revision: int | None,
        verdict: str,
        prior_runs: list[str],
        *,
        reviewer_id: str = "reviewer-new",
        reviewer_fingerprint: str = "sha256:" + "3" * 64,
        originating_run_id: str | None = None,
        resolves: list[str] | None = None,
    ) -> tuple[dict, dict]:
        proposal = {
            "review_type": review_type,
            "entity_ref": finding_id,
            "proposed_finding_id": finding_id if review_type != "coverage" else None,
            "finding_revision": revision,
            "verdict": verdict,
            "prior_review_run_ids": prior_runs,
            "independence": {
                "reviewer_id": reviewer_id,
                "reviewer_signer_fingerprint": reviewer_fingerprint,
                "originating_run_id": originating_run_id or f"event-{finding_id}-revision",
            },
        }
        event_type = {
            "claim_adjudication": "claim.adjudicated",
            "coverage": "review.coverage_completed",
            "regrade": "review.regrade_completed",
            "pocinator": "review.pocinator_completed",
        }[review_type]
        payload = {"verdict": verdict}
        if review_type == "claim_adjudication":
            payload = {"entity_id": finding_id, "status": verdict}
        elif review_type in {"regrade", "pocinator"}:
            proposal["claim_tuple_hash"] = "sha256:" + "2" * 64
            payload.update(
                {
                    "finding_id": finding_id,
                    "finding_revision": revision,
                    "claim_tuple_hash": proposal["claim_tuple_hash"],
                }
            )
            if review_type == "pocinator":
                proposal["high_value"] = True
                payload["high_value"] = True
        if resolves is not None:
            payload["resolves_review_refs"] = resolves
        event = {"event_type": event_type, "payload": payload, "review_refs": ["review-new"]}
        return proposal, event

    def _assert_predicate_rejects(self, predicate: dict, proposal: dict, event: dict) -> None:
        with self.assertRaises(RecordError) as raised:
            self._evaluate(predicate, proposal, event)
        self.assertEqual(raised.exception.code, "driver_action_predicate_mismatch")

    def test_current_regrade_binds_exact_claim_adjudication_run(self) -> None:
        state = {
            "findings": {"F-1": {"revision": 3, "claim_tuple_hash": "sha256:" + "2" * 64, "revision_event_ref": "event-F-1-revision"}},
            "claim_adjudications": {"F-1": {"reviewer_run_id": "run-claim-current"}},
        }
        predicate = build_action_admission(
            self._finding_item("finding_unproved", "F-1"),
            {"action_id": "record_current_revision_regrade"},
            state,
            self.engagement,
        )
        proposal, event = self._review_documents(
            "regrade", "F-1", 3, "confirmed", ["run-claim-current"]
        )
        self._evaluate(predicate, proposal, event)
        for runs in ([], ["run-other"], ["run-claim-current", "run-other"]):
            changed = copy.deepcopy(proposal)
            changed["prior_review_run_ids"] = runs
            self._assert_predicate_rejects(predicate, changed, event)
        for path in ("subject", "tuple", "origin", "event_tuple"):
            changed_proposal, changed_event = copy.deepcopy(proposal), copy.deepcopy(event)
            if path == "subject":
                changed_proposal["proposed_finding_id"] = "F-other"
            elif path == "tuple":
                changed_proposal["claim_tuple_hash"] = "sha256:" + "9" * 64
                changed_event["payload"]["claim_tuple_hash"] = changed_proposal["claim_tuple_hash"]
            elif path == "origin":
                changed_proposal["independence"]["originating_run_id"] = "event-unrelated"
            else:
                changed_event["payload"]["claim_tuple_hash"] = "sha256:" + "9" * 64
            self._assert_predicate_rejects(predicate, changed_proposal, changed_event)

    def test_current_pocinator_binds_exact_regrade_run(self) -> None:
        state = {
            "findings": {"F-1": {"revision": 3, "claim_tuple_hash": "sha256:" + "2" * 64, "revision_event_ref": "event-F-1-revision"}},
            "regrade_reviews": {"F-1:r3": {"reviewer_run_id": "run-regrade-current"}},
        }
        predicate = build_action_admission(
            self._finding_item("finding_unproved", "F-1"),
            {"action_id": "record_current_revision_pocinator"},
            state,
            self.engagement,
        )
        proposal, event = self._review_documents(
            "pocinator", "F-1", 3, "verified", ["run-regrade-current"]
        )
        self._evaluate(predicate, proposal, event)
        proposal["prior_review_run_ids"].append("run-unrelated")
        self._assert_predicate_rejects(predicate, proposal, event)
        wrong_value = copy.deepcopy(event)
        wrong_value["payload"]["high_value"] = False
        proposal["prior_review_run_ids"] = ["run-regrade-current"]
        self._assert_predicate_rejects(predicate, proposal, wrong_value)

    def test_distinct_second_pocinator_binds_all_prior_runs_and_new_reviewer(self) -> None:
        row = {
            "review_type": "pocinator",
            "entity_ref": "F-1",
            "review_ref": "event-poc-first",
        }
        state = {
            "findings": {"F-1": {"revision": 3, "claim_tuple_hash": "sha256:" + "2" * 64, "revision_event_ref": "event-F-1-revision"}},
            "outstanding_reviews": [row],
            "proof_reviews": {
                "F-1:r3": {
                    "reviewer_run_ids": ["run-poc-a", "run-poc-b"],
                    "reviewer_ids": ["reviewer-a", "reviewer-b"],
                    "reviewer_signer_fingerprints": [
                        "sha256:" + "4" * 64,
                        "sha256:" + "5" * 64,
                    ],
                }
            },
        }
        predicate = build_action_admission(
            self._review_item("event-poc-first", "F-1"),
            {"action_id": "record_distinct_pocinator_second_review"},
            state,
            self.engagement,
        )
        proposal, event = self._review_documents(
            "pocinator", "F-1", 3, "reward_hacked", ["run-poc-a", "run-poc-b"]
        )
        self._evaluate(predicate, proposal, event)
        same_reviewer = copy.deepcopy(proposal)
        same_reviewer["independence"]["reviewer_id"] = "reviewer-a"
        self._assert_predicate_rejects(predicate, same_reviewer, event)
        same_signer = copy.deepcopy(proposal)
        same_signer["independence"]["reviewer_signer_fingerprint"] = "sha256:" + "4" * 64
        self._assert_predicate_rejects(predicate, same_signer, event)
        missing_signer = copy.deepcopy(proposal)
        del missing_signer["independence"]["reviewer_signer_fingerprint"]
        self._assert_predicate_rejects(predicate, missing_signer, event)
        extra_run = copy.deepcopy(proposal)
        extra_run["prior_review_run_ids"].append("run-poc-extra")
        self._assert_predicate_rejects(predicate, extra_run, event)

    def test_blocked_supersession_binds_only_opening_run_and_exact_row(self) -> None:
        row = {
            "review_type": "regrade",
            "entity_ref": "F-1",
            "review_ref": "event-regrade-blocked",
            "opening_reviewer_run_id": "run-regrade-blocked",
        }
        state = {
            "findings": {"F-1": {"revision": 3, "claim_tuple_hash": "sha256:" + "2" * 64, "revision_event_ref": "event-F-1-revision"}},
            "outstanding_reviews": [row],
        }
        predicate = build_action_admission(
            self._review_item("event-regrade-blocked", "F-1"),
            {"action_id": "supersede_blocked_review_obligation"},
            state,
            self.engagement,
        )
        proposal, event = self._review_documents(
            "regrade",
            "F-1",
            3,
            "blocked",
            ["run-regrade-blocked"],
            resolves=["event-regrade-blocked"],
        )
        self._evaluate(predicate, proposal, event)
        wrong = copy.deepcopy(proposal)
        wrong["prior_review_run_ids"] = ["run-unrelated"]
        self._assert_predicate_rejects(predicate, wrong, event)

    def test_coverage_review_binds_exact_sorted_dispositions_and_one_review_ref(self) -> None:
        state = {
            "engagement_id": "eng-1",
            "coverage_relevant_event_ref": "event-coverage-relevant",
            "hypotheses": {"hyp-b": {"status": "held"}, "hyp-a": {"status": "closed"}},
        }
        predicate = build_action_admission(
            {"class": "coverage_review_missing", "entity": {"id": "eng-1"}},
            {"action_id": "record_cold_coverage_review"},
            state,
            self.engagement,
        )
        proposal, event = self._review_documents(
            "coverage",
            "eng-1",
            None,
            "continue",
            [],
            originating_run_id="event-coverage-relevant",
        )
        proposal["hypothesis_dispositions"] = [
            {"hypothesis_ref": "hyp-a", "status": "closed"},
            {"hypothesis_ref": "hyp-b", "status": "held"},
        ]
        self._evaluate(predicate, proposal, event)
        omitted = copy.deepcopy(proposal)
        omitted["hypothesis_dispositions"].pop()
        self._assert_predicate_rejects(predicate, omitted, event)
        extra_ref = copy.deepcopy(event)
        extra_ref["review_refs"].append("review-unrelated")
        self._assert_predicate_rejects(predicate, proposal, extra_ref)
        older_origin = copy.deepcopy(proposal)
        older_origin["independence"]["originating_run_id"] = "event-coverage-older"
        self._assert_predicate_rejects(predicate, older_origin, event)
        missing_origin_state = copy.deepcopy(state)
        missing_origin_state["coverage_relevant_event_ref"] = None
        with self.assertRaises(RecordError) as missing_origin:
            build_action_admission(
                {"class": "coverage_review_missing", "entity": {"id": "eng-1"}},
                {"action_id": "record_cold_coverage_review"},
                missing_origin_state,
                self.engagement,
            )
        self.assertEqual(
            missing_origin.exception.code,
            "work_queue_admission_coverage_origin_missing",
        )

    def test_claim_filing_review_binds_inputs_freshness_and_required_disposition(self) -> None:
        row = {
            "review_type": "regrade",
            "entity_ref": "F-1",
            "review_ref": "event-regrade-refuted",
            "status": "correction_required",
            "opened_at": "2026-08-25T12:00:00Z",
            "resolution_input_refs": ["artifact-fresh"],
            "required_claim_status": "refuted",
        }
        state = {
            "findings": {"F-1": {"revision": 3, "revision_event_ref": "event-F-1-revision"}},
            "claim_adjudications": {"F-1": {"event_ref": "event-claim-current"}},
            "outstanding_reviews": [row],
        }
        predicate = build_action_admission(
            self._review_item("event-regrade-refuted", "F-1"),
            {"action_id": "record_claim_adjudication"},
            state,
            self.engagement,
        )
        proposal, event = self._review_documents(
            "claim_adjudication",
            "F-1",
            3,
            "refuted",
            [],
            originating_run_id="event-claim-current",
        )
        proposal.update(
            {
                "recorded_at": "2026-08-25T12:00:01Z",
                "input_refs": ["event-regrade-refuted", "artifact-fresh"],
            }
        )
        self._evaluate(predicate, proposal, event)
        for mutate in ("missing", "stale", "wrong_verdict"):
            changed_proposal, changed_event = copy.deepcopy(proposal), copy.deepcopy(event)
            if mutate == "missing":
                changed_proposal["input_refs"].remove("artifact-fresh")
            elif mutate == "stale":
                changed_proposal["recorded_at"] = row["opened_at"]
            else:
                changed_proposal["verdict"] = "confirmed"
                changed_event["payload"]["status"] = "confirmed"
            self._assert_predicate_rejects(predicate, changed_proposal, changed_event)
        stale_origin = copy.deepcopy(proposal)
        stale_origin["independence"]["originating_run_id"] = "event-F-1-revision"
        self._assert_predicate_rejects(predicate, stale_origin, event)

        fallback_state = copy.deepcopy(state)
        fallback_state["claim_adjudications"]["F-1"] = {}
        fallback_predicate = build_action_admission(
            self._review_item("event-regrade-refuted", "F-1"),
            {"action_id": "record_claim_adjudication"},
            fallback_state,
            self.engagement,
        )
        fallback = copy.deepcopy(proposal)
        fallback["independence"]["originating_run_id"] = "event-F-1-revision"
        self._evaluate(fallback_predicate, fallback, event)
        no_origin_state = copy.deepcopy(fallback_state)
        del no_origin_state["findings"]["F-1"]["revision_event_ref"]
        with self.assertRaises(RecordError) as no_origin:
            build_action_admission(
                self._review_item("event-regrade-refuted", "F-1"),
                {"action_id": "record_claim_adjudication"},
                no_origin_state,
                self.engagement,
            )
        self.assertEqual(
            no_origin.exception.code,
            "work_queue_admission_claim_origin_missing",
        )

    def test_pocinator_projection_requires_distinct_verified_signer_keys(self) -> None:
        first_payload = {
            "finding_id": "F-1",
            "finding_revision": 3,
            "claim_tuple_hash": "sha256:" + "2" * 64,
            "review_ref": "review-poc-a",
            "verdict": "reward_hacked",
            "high_value": True,
        }
        first_review = {
            "independence": {
                "reviewer_id": "alias-a",
                "reviewer_run_id": "run-poc-a",
                "reviewer_signer_fingerprint": "sha256:" + "4" * 64,
            }
        }
        first = _project_pocinator_proof(None, first_payload, first_review)
        self.assertEqual(first["terminal_status"], "pending_second_review")

        second_payload = {**first_payload, "review_ref": "review-poc-b"}
        same_key_alias = {
            "independence": {
                "reviewer_id": "alias-b",
                "reviewer_run_id": "run-poc-b",
                "reviewer_signer_fingerprint": "sha256:" + "4" * 64,
            }
        }
        with self.assertRaises(RecordError) as same_key:
            _project_pocinator_proof(first, second_payload, same_key_alias)
        self.assertEqual(same_key.exception.code, "pocinator_reviewer_signer_not_distinct")

        missing_key_alias = copy.deepcopy(same_key_alias)
        del missing_key_alias["independence"]["reviewer_signer_fingerprint"]
        with self.assertRaises(RecordError) as missing_key:
            _project_pocinator_proof(first, second_payload, missing_key_alias)
        self.assertEqual(missing_key.exception.code, "pocinator_reviewer_signer_not_distinct")

        distinct_key_alias = copy.deepcopy(same_key_alias)
        distinct_key_alias["independence"]["reviewer_signer_fingerprint"] = "sha256:" + "5" * 64
        missing_prior_key = copy.deepcopy(first)
        missing_prior_key["reviewer_signer_fingerprints"] = [None]
        with self.assertRaises(RecordError) as incomplete_lineage:
            _project_pocinator_proof(missing_prior_key, second_payload, distinct_key_alias)
        self.assertEqual(
            incomplete_lineage.exception.code,
            "pocinator_reviewer_signer_not_distinct",
        )

        second = _project_pocinator_proof(first, second_payload, distinct_key_alias)
        self.assertEqual(second["terminal_status"], "second_review_confirmed")
        self.assertEqual(
            second["reviewer_signer_fingerprints"],
            ["sha256:" + "4" * 64, "sha256:" + "5" * 64],
        )

    def test_review_evidence_requires_fresh_committed_artifact_and_non_model_source(self) -> None:
        row = {
            "entity_ref": "F-1",
            "review_ref": "event-review-open",
            "hypothesis_ref": "hyp-review",
            "opened_at": "2026-08-25T12:00:00Z",
        }
        state = {
            "scope_hash": "sha256:" + "1" * 64,
            "active_environment_ref": "environment-1",
            "outstanding_reviews": [row],
            "work_queue_context": {
                "pending_attempts": {},
                "artifacts": {
                    "artifact-stale": {
                        "created_at": "2026-08-25T11:59:59Z",
                        "environment_ref": "environment-1",
                    },
                    "artifact-wrong-environment": {
                        "created_at": "2026-08-25T12:00:01Z",
                        "environment_ref": "environment-old",
                    },
                    "artifact-fresh": {
                        "created_at": "2026-08-25T12:00:01Z",
                        "environment_ref": "environment-1",
                    },
                },
            },
        }
        predicate = build_action_admission(
            self._review_item("event-review-open", "F-1"),
            {"action_id": "collect_review_evidence"},
            state,
            self.engagement,
        )
        proposal = {
            "kind": "primary",
            "hypothesis_ref": "hyp-review",
            "experiment_ref": "event-review-open",
            "recorded_at": "2026-08-25T12:00:02Z",
            "scope_hash": state["scope_hash"],
            "environment_ref": "environment-1",
            "evidence_refs": ["artifact-fresh"],
            "observation": {"source": "source_inspection"},
        }
        self._evaluate(predicate, proposal)
        for evidence, source in (
            ([], "source_inspection"),
            (["artifact-stale"], "source_inspection"),
            (["artifact-wrong-environment"], "source_inspection"),
            (["artifact-fresh"], "model_report"),
        ):
            changed = copy.deepcopy(proposal)
            changed["evidence_refs"] = evidence
            changed["observation"]["source"] = source
            with self.assertRaises(RecordError):
                self._evaluate(predicate, changed)

    def test_settlement_uses_rendered_current_request_not_historical_approved_request(self) -> None:
        proposal = {"finding_id": "F-1", "revision": 3}
        digest = sha256_bytes(canonical_json_bytes(proposal))
        state = {
            "authority_requests": {
                "request-old": {
                    "action_kind": "revise-finding",
                    "status": "approved",
                    "target": {"id": "F-1", "file_digest": "sha256:" + "0" * 64},
                },
                "request-current": {
                    "action_kind": "revise-finding",
                    "status": "approved",
                    "target": {"id": "F-1", "file_digest": digest},
                },
            }
        }
        action = {
            "action_id": "settle_approved_finding_revision",
            "arguments": ["--authority-request-id", "request-current"],
        }
        predicate = build_action_admission(
            self._finding_item("finding_revision_pending", "F-1"),
            action,
            state,
            self.engagement,
        )
        self._evaluate(predicate, proposal)
        with self.assertRaises(RecordError):
            self._evaluate(predicate, {"finding_id": "F-1", "revision": 2})

    def test_alternate_queue_contexts_all_build_closed_predicates(self) -> None:
        base = {
            "engagement_id": "eng-1",
            "scope_hash": "sha256:" + "1" * 64,
            "active_environment_ref": "environment-1",
            "findings": {
                "F-1": {
                    "revision": 3,
                    "claim_tuple_hash": "sha256:" + "2" * 64,
                    "revision_event_ref": "event-F-1-revision",
                }
            },
            "claim_adjudications": {
                "F-1": {
                    "status": "confirmed",
                    "event_ref": "event-claim-current",
                    "review_ref": "review-claim-current",
                    "reviewer_run_id": "run-claim-current",
                    "expected_filing_revision": 4,
                }
            },
            "outstanding_reviews": [],
            "proof_reviews": {},
            "regrade_reviews": {},
            "hypotheses": {},
            "control_candidates": [],
            "work_queue_context": {
                "pending_attempts": {},
                "artifacts": {
                    "artifact-fresh": {
                        "created_at": "2026-08-25T12:00:01Z",
                        "environment_ref": "environment-1",
                    }
                },
            },
            "authority_requests": {},
        }
        built: set[str] = set()

        def build(action_id: str, item: dict, state: dict | None = None, action: dict | None = None) -> None:
            predicate = build_action_admission(
                item,
                action or {"action_id": action_id},
                state or base,
                self.engagement,
            )
            self.assertEqual(predicate["schema_version"], 1)
            self.assertTrue(predicate["documents"])
            self.assertTrue(predicate["constraints"])
            built.add(action_id)

        review_item = self._review_item("event-review-open", "F-1")
        review_row = {
            "review_type": "regrade",
            "entity_ref": "F-1",
            "review_ref": "event-review-open",
            "status": "routed",
            "hypothesis_ref": "hyp-review",
            "opened_at": "2026-08-25T12:00:00Z",
        }
        for action_id, status in (
            ("select_review_hypothesis", "queued"),
            ("run_review_hypothesis", "selected"),
            ("requeue_review_hypothesis", "held"),
        ):
            state = copy.deepcopy(base)
            state["outstanding_reviews"] = [review_row]
            state["hypotheses"] = {
                "hyp-review": {
                    "status": status,
                    "next_experiment": "bounded route",
                    "next_route": None,
                    "experiment_refs": [],
                    "control_refs": [],
                    "supporting_evidence_refs": [],
                    "conflicting_evidence_refs": [],
                    "unresolved_questions": [],
                }
            }
            build(action_id, review_item, state)
        build("route_review_obligation", review_item)

        control_item = {
            "class": "control_candidate_unverified",
            "entity": {"type": "control_candidate", "id": "event-routing-negative", "detail": None},
        }
        for action_id, status, primary in (
            ("select_control_hypothesis", "queued", None),
            ("run_control_hypothesis", "selected", None),
            ("requeue_control_hypothesis", "held", None),
            ("record_control_primary", "running", None),
            ("record_control_attempt", "running", "attempt-control-primary"),
        ):
            state = copy.deepcopy(base)
            state["control_candidates"] = [
                {
                    "routing_event_id": "event-routing-negative",
                    "hypothesis_ref": "hyp-control",
                    "primary_attempt_ref": primary,
                }
            ]
            state["hypotheses"] = {
                "hyp-control": {
                    "status": status,
                    "next_experiment": "control route",
                    "next_route": None,
                    "experiment_refs": [],
                    "control_refs": [],
                    "supporting_evidence_refs": [],
                    "conflicting_evidence_refs": [],
                    "unresolved_questions": [],
                }
            }
            build(action_id, control_item, state)
        state = copy.deepcopy(base)
        state["control_candidates"] = [{"routing_event_id": "event-routing-negative"}]
        build("create_control_hypothesis", control_item, state)

        coverage_item = {
            "class": "coverage_review_missing",
            "entity": {"type": "engagement", "id": "eng-1", "detail": None},
        }
        for action_id, verdict in (
            ("record_coverage_dry", "coverage_dry"),
            ("record_coverage_blocked", "blocked"),
            ("create_coverage_followup_hypothesis", "continue"),
        ):
            state = copy.deepcopy(base)
            state["latest_coverage_review"] = {
                "event_ref": "event-coverage-current",
                "review_refs": ["review-coverage-current"],
                "verdict": verdict,
            }
            build(action_id, coverage_item, state)

        build(
            "request_finding_revision_authority",
            self._finding_item("finding_revision_pending", "F-1"),
        )
        build(
            "create_candidate_hypothesis",
            {"class": "candidate_undisposed", "entity": {"id": "candidate-1"}},
        )
        build(
            "record_candidate_skipped",
            {"class": "deferred_candidate_unreviewed", "entity": {"id": "candidate-1"}},
        )
        self.assertEqual(
            built,
            {
                "select_review_hypothesis",
                "run_review_hypothesis",
                "requeue_review_hypothesis",
                "route_review_obligation",
                "select_control_hypothesis",
                "run_control_hypothesis",
                "requeue_control_hypothesis",
                "record_control_primary",
                "record_control_attempt",
                "create_control_hypothesis",
                "record_coverage_dry",
                "record_coverage_blocked",
                "create_coverage_followup_hypothesis",
                "request_finding_revision_authority",
                "create_candidate_hypothesis",
                "record_candidate_skipped",
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
