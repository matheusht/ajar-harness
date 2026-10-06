#!/usr/bin/env python3
"""Signed synthetic target E2E for the issue-125 scoped cleanup boundary."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engagement_records import RecordError, build_reference_index, canonical_json_bytes, sha256_bytes, sha256_file
from engagement_state import (append_event, attempt_ledger_context, base_event, blocking_work_identities,
                              compute_review_input_hash, project_current_terminal_work_state, read_ledger, reduce_engagement)
from memory_disposition import close_engagement, record_memory_disposition
from operator_signature import ending_override_action, operator_challenge_bytes


CLI = Path(__file__).with_name("run-engagement.py")
EFFECT = b"synthetic-scoped-effect-v1\n"


def main() -> None:
    results: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="scoped-cleanup-e2e-") as temporary:
        root = Path(temporary).resolve()
        effect_root = root / "effects"
        effect_root.mkdir()
        engagement = root / "synthetic"
        engagement.mkdir()
        key = root / "operator-ed25519"
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        public = key.with_suffix(".pub").read_text().split()
        allowed = root / "allowed-signers"
        allowed.write_text(f"operator-synthetic {public[0]} {public[1]}\nreviewer-cold {public[0]} {public[1]}\n")
        now = datetime.now(timezone.utc) - timedelta(seconds=30)

        def at(seconds: int) -> str:
            return (now + timedelta(seconds=seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")

        def at_micro(seconds: int, microseconds: int) -> str:
            return (now + timedelta(seconds=seconds, microseconds=microseconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")

        scope = f"""# Signed synthetic scope
## Surfaces in scope
- One inert local file.
## Benign safe-objective set
- Verify exact local file cleanup.
## Escalation ceiling
- Local synthetic file only.
## Impact-demo authorization
- impact_demo_authorized: `no`
## Accounts / fixtures
- No accounts or live target.
## Scoped cleanup and closure
- scoped_cleanup_closure: `yes`
- scoped_cleanup_root: `{effect_root}`
## Independent reviewer identity
- Reviewer allowed signers SHA256: {sha256_file(allowed)}
## Authorization
- Operator allowed signers SHA256: {sha256_file(allowed)}
- Operator: operator-synthetic
- Date: 2026-10-06
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""
        (engagement / "scope.md").write_text(scope)
        init_time = at(0)
        challenge = {
            "schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
            "engagement_id": engagement.name, "scope_hash": sha256_file(engagement / "scope.md"),
            "ledger_hash": None, "operation": f"initialize-engagement:{init_time}",
            "operator_id": "operator-synthetic",
        }
        challenge_path = root / "init-challenge.json"
        challenge_path.write_bytes(canonical_json_bytes(challenge))
        subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n", "llm-redteam-harness-operator-v1", str(challenge_path)], check=True, stdout=subprocess.DEVNULL)
        signed_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed)}

        def cli(*args: str, env: dict[str, str] | None = None) -> dict:
            completed = subprocess.run([sys.executable, str(CLI), *args], env=env, text=True, capture_output=True)
            try:
                result = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"command produced non-JSON: {args}: {completed.stdout} {completed.stderr}") from exc
            result["returncode"] = completed.returncode
            return result

        init = cli("init", "--engagement", str(engagement), "--recorded-at", init_time, env=signed_env)
        assert init["returncode"] == 0, init
        results["signed_scope"] = reduce_engagement(engagement)["scope_hash"]
        broker = f"local-uid-{os.getuid()}:broker"
        session = f"session-posix-{os.getuid()}-{os.getsid(0)}"
        effect_name = "marker.txt"
        effect_path = effect_root / effect_name
        obligation_id = "cleanup-marker"
        digest = sha256_bytes(EFFECT)

        def proposal(status: str, seconds: int) -> Path:
            value = {
                "entity_id": obligation_id, "status": status,
                "cleanup_obligations": [{
                    "obligation_id": obligation_id, "kind": "scoped_local_file", "status": status,
                    "artifact_refs": [], "rationale": f"Exact inert marker {status}.",
                    "closed_at": None if status == "open" else at(seconds),
                    "effect_name": effect_name, "effect_sha256": digest,
                }],
            }
            path = root / f"cleanup-{status}.json"
            path.write_bytes(canonical_json_bytes(value))
            return path

        def cleanup(status: str, seconds: int) -> dict:
            return cli("record-cleanup", "--scoped", "--engagement", str(engagement),
                       "--file", str(proposal(status, seconds)), "--reason", f"Synthetic {status}.",
                       "--recorded-at", at(seconds), "--executor-id", broker, "--session-id", session)

        def create(name: str, seconds: int) -> dict:
            return cli("create-scoped-effect", "--engagement", str(engagement),
                       "--obligation-id", obligation_id, "--effect-name", name,
                       "--recorded-at", at(seconds), "--executor-id", broker, "--session-id", session)

        missing = create(effect_name, 1)
        assert missing["returncode"] != 0 and not effect_path.exists(), missing
        results["obligation_before_effect"] = missing["error"]["code"]
        opened = cleanup("open", 2)
        assert opened["returncode"] == 0 and not effect_path.exists(), opened
        opened_count = len(read_ledger(engagement, "event"))
        opened_retry = cleanup("open", 2)
        assert opened_retry["returncode"] == 0 and opened_retry.get("replayed") is True and len(read_ledger(engagement, "event")) == opened_count, opened_retry
        results["open_retry"] = "same committed event"
        opened_event = read_ledger(engagement, "event")[-1]
        forged_effect = base_event(event_id="event-forged-effect", engagement_id=engagement.name, recorded_at=at(3),
                                   actor_role="broker", actor_id=broker, event_type="observation.recorded",
                                   rationale="Attempt to claim a file without the canonical creator.",
                                   payload={"entity_id": f"effect-{obligation_id}", "entity_type": "scoped_local_effect",
                                            "status": "created", "scoped_effect": {"effect_name": effect_name,
                                            "effect_sha256": digest, "root_dev": opened_event["payload"]["scoped_cleanup"]["root_dev"],
                                            "root_ino": opened_event["payload"]["scoped_cleanup"]["root_ino"],
                                            "cleanup_obligation_ref": opened["event_id"]}},
                                   entity_refs=[opened["event_id"]], session_id=session, operation_class="notebook")
        forged_path = root / "forged-effect.json"
        forged_path.write_bytes(canonical_json_bytes(forged_effect))
        forged = cli("append-event", "--engagement", str(engagement), "--file", str(forged_path))
        assert forged["returncode"] != 0 and forged["error"]["code"] == "canonical_notebook_command_required", forged
        assert len(read_ledger(engagement, "event")) == opened_count and not effect_path.exists()
        results["forged_creation_rejected"] = forged["error"]["code"]
        canceled_work = root / "canceled-work"
        shutil.copytree(engagement, canceled_work)
        canceled = cli("record-cleanup", "--scoped", "--engagement", str(canceled_work),
                       "--file", str(proposal("not_applicable", 3)), "--reason", "Cancel before any effect exists.",
                       "--recorded-at", at(3), "--executor-id", broker, "--session-id", session)
        assert canceled["returncode"] == 0 and reduce_engagement(canceled_work)["cleanup"]["open_count"] == 0 and not effect_path.exists(), canceled
        results["aborted_creation_cancel"] = canceled["event_id"]
        preexisting_work = root / "preexisting-work"
        shutil.copytree(engagement, preexisting_work)
        effect_path.write_bytes(EFFECT)
        preexisting_count = len(read_ledger(preexisting_work, "event"))
        preexisting = cli("create-scoped-effect", "--engagement", str(preexisting_work),
                          "--obligation-id", obligation_id, "--effect-name", effect_name,
                          "--recorded-at", at(3), "--executor-id", broker, "--session-id", session)
        assert preexisting["returncode"] != 0 and preexisting["error"]["code"] == "scoped_effect_preexisting", preexisting
        assert effect_path.read_bytes() == EFFECT and len(read_ledger(preexisting_work, "event")) == preexisting_count
        results["preexisting_same_bytes"] = preexisting["error"]["code"]
        effect_path.unlink()
        before_regression = len(read_ledger(engagement, "event"))
        regressed = create(effect_name, 1)
        assert regressed["returncode"] != 0 and not effect_path.exists() and len(read_ledger(engagement, "event")) == before_regression, regressed
        results["append_failure_rollback"] = regressed["error"]["code"]
        created = create(effect_name, 3)
        assert created["returncode"] == 0 and effect_path.read_bytes() == EFFECT, created
        count_after_create = len(read_ledger(engagement, "event"))
        retried = create(effect_name, 3)
        assert retried["returncode"] == 0 and len(read_ledger(engagement, "event")) == count_after_create, retried
        out_of_scope = create("../outside.txt", 4)
        assert out_of_scope["returncode"] != 0 and not (root / "outside.txt").exists(), out_of_scope
        results["out_of_authority"] = out_of_scope["error"]["code"]

        effect_path.write_bytes(b"changed")
        changed = cleanup("completed", 5)
        assert changed["returncode"] != 0 and effect_path.read_bytes() == b"changed", changed
        results["changed_effect"] = changed["error"]["code"]
        effect_path.unlink()
        outside = root / "outside-target.txt"
        outside.write_bytes(b"keep")
        effect_path.symlink_to(outside)
        symlink = cleanup("completed", 5)
        assert symlink["returncode"] != 0 and effect_path.is_symlink() and outside.read_bytes() == b"keep", symlink
        results["symlink_refusal"] = symlink["error"]["code"]
        effect_path.unlink()
        effect_path.write_bytes(EFFECT)
        recovery = root / "recovery"
        shutil.copytree(engagement, recovery)
        effect_path.unlink()  # simulate a crash after unlink but before the ledger append
        recovered = cli("record-cleanup", "--scoped", "--engagement", str(recovery),
                        "--file", str(proposal("completed", 5)), "--reason", "Recover missing marker.",
                        "--recorded-at", at(5), "--executor-id", broker, "--session-id", session)
        assert recovered["returncode"] == 0 and recovered["checked_absent"] is True, recovered
        recovered_event = read_ledger(recovery, "event")[-1]
        assert recovered_event["payload"]["scoped_cleanup"]["observed_sha256"] is None, recovered_event
        results["interrupted_unlink_recovery"] = recovered["event_id"]
        effect_path.write_bytes(EFFECT)
        completed = cleanup("completed", 5)
        assert completed["returncode"] == 0, completed
        completed_count = len(read_ledger(engagement, "event"))
        completed_retry = cleanup("completed", 5)
        assert completed_retry["returncode"] == 0 and completed_retry.get("replayed") is True and len(read_ledger(engagement, "event")) == completed_count, completed_retry
        results["completed_retry"] = "same committed event"
        independently_absent = subprocess.run([sys.executable, "-c", "import os,sys; sys.exit(1 if os.path.lexists(sys.argv[1]) else 0)", str(effect_path)]).returncode == 0
        assert independently_absent
        after = reduce_engagement(engagement)
        assert after["cleanup"]["open_count"] == 0
        results["independent_postcheck"] = independently_absent
        results["cleanup_event"] = completed["event_id"]
        restarted = cli("reduce", "--engagement", str(engagement))
        assert restarted["returncode"] == 0 and reduce_engagement(engagement)["cleanup"] == after["cleanup"], restarted
        results["restart_reduction"] = "same cleanup projection"

        # Prepare existing operator-owned memory disposition. This ticket does not change that gate.
        state = reduce_engagement(engagement)
        memory = {
            "schema_version": 1, "disposition_id": "memory-none", "engagement_id": engagement.name,
            "recorded_at": at(6), "scope_hash": state["scope_hash"],
            "disposition": "no_novel_lesson", "lesson_kind": "none", "lesson_summary": None,
            "rationale": "The synthetic effect yields no transferable lesson.", "candidate_refs": [],
            "source_refs": {key: [] for key in ("event_refs", "candidate_refs", "hypothesis_refs", "attempt_refs", "artifact_refs", "review_refs", "finding_refs", "environment_refs")},
            "sanitization": {"status": "not_applicable", "secret_scan_status": "clean", "target_identifiers_removed": True, "credential_values_removed": True, "harmful_recipe_removed": True, "target_terms_checked": [], "notes": "No lesson body."},
            "human_review": {"reviewer": {"role": "operator", "id": "operator-synthetic"}, "reviewed_at": at(6), "decision": "no_novel_lesson", "rationale": "No lesson.", "source_material_compared": True, "abstraction_only": True, "plane1_pr_required": True},
            "reopening_condition": None, "provenance": {"actor": {"role": "operator", "id": "operator-synthetic"}},
        }
        memory_path = root / "memory.json"
        memory_path.write_bytes(canonical_json_bytes(memory))
        record_memory_disposition(engagement, memory_path, "operator-synthetic")

        # Give the existing cold coverage gate a distinct source principal and signed reviewer.
        origin = base_event(event_id="event-origin", engagement_id=engagement.name, recorded_at=at(7),
                            actor_role="orchestrator", actor_id="orchestrator-origin", event_type="observation.recorded",
                            rationale="Bound the synthetic source observation.",
                            payload={"entity_id": "synthetic-source", "entity_type": "observation", "status": "recorded"},
                            session_id="session-origin", operation_class="notebook", model="origin-model")
        append_event(engagement, origin)
        review = {
            "schema_version": 1, "review_id": "review-cold", "engagement_id": engagement.name,
            "review_type": "coverage", "proposed_finding_id": None, "entity_ref": engagement.name,
            "finding_revision": None, "recorded_at": at(8), "input_refs": ["event-origin"],
            "input_hash": "sha256:" + "0" * 64, "evidence_refs": [], "conflicting_evidence": [],
            "rationale": "No open hypothesis exists in the bounded synthetic file exercise.",
            "verdict": "coverage_dry", "corrections": [], "required_next_actions": [],
            "independence": {"reviewer_id": "reviewer-cold", "reviewer_run_id": "run-review-cold", "reviewer_session_id": "session-reviewer", "reviewer_model": "cold-model", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find omitted work in the synthetic file exercise.", "originating_run_id": "event-origin"},
            "bounded_space": "One inert local file and its cleanup obligation.",
            "hypothesis_dispositions": [], "omitted_branch_challenge": "No additional branch exists in this synthetic exercise.",
            "residual_uncertainty": ["No live target was assessed."],
        }
        review["input_hash"] = compute_review_input_hash(engagement, review, build_reference_index(engagement))
        review_path = root / "review.json"
        review_path.write_bytes(canonical_json_bytes(review))
        subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n", "llm-redteam-harness-review-v1", str(review_path)], check=True, stdout=subprocess.DEVNULL)
        review_event = base_event(event_id="event-coverage-review", engagement_id=engagement.name, recorded_at=at(9),
                                  actor_role="broker", actor_id=broker, event_type="review.coverage_completed",
                                  rationale="Independent synthetic cold review.",
                                  payload={"review_ref": "review-cold", "review_type": "coverage", "verdict": "coverage_dry", "reviewer_id": "reviewer-cold"},
                                  review_refs=["review-cold"], session_id=session, operation_class="notebook")
        review_event_path = root / "review-event.json"
        review_event_path.write_bytes(canonical_json_bytes(review_event))
        recorded_review = cli("record-review", "--engagement", str(engagement), "--file", str(review_path),
                              "--event", str(review_event_path), "--actor-id", broker, "--session-id", session,
                              "--signature", str(review_path) + ".sig", "--allowed-signers", str(allowed))
        assert recorded_review["returncode"] == 0, recorded_review
        open_work = root / "open-work"
        shutil.copytree(engagement, open_work)
        coverage = base_event(event_id="event-coverage-dry", engagement_id=engagement.name, recorded_at=at(10),
                              actor_role="orchestrator", actor_id="orchestrator-origin", event_type="coverage.status_changed",
                              rationale="Bounded synthetic exercise is dry.",
                              payload={"entity_id": engagement.name, "status": "coverage_dry", "coverage_review_ref": "event-coverage-review"},
                              entity_refs=["event-coverage-review"], state_changes=[{"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "coverage_dry"}],
                              session_id="session-origin", operation_class="notebook")
        append_event(engagement, coverage)

        # The saved ledger must replay without the physical root, while each
        # new operation must reject a renamed or replaced containment inode.
        moved_root = root / "effects-moved"
        effect_root.rename(moved_root)
        missing_replay = cli("reduce", "--engagement", str(engagement))
        assert missing_replay["returncode"] == 0, missing_replay
        missing_close = cli("close", "--scoped", "--engagement", str(engagement),
                            "--reason", "Root is absent.", "--recorded-at", at(11),
                            "--executor-id", broker, "--session-id", session)
        assert missing_close["returncode"] != 0 and missing_close["error"]["code"] == "scoped_cleanup_root_unavailable", missing_close
        effect_root.mkdir()
        (moved_root / effect_name).write_bytes(EFFECT)
        replaced_replay = cli("reduce", "--engagement", str(engagement))
        replaced_cleanup = cleanup("completed", 5)
        replaced_close = cli("close", "--scoped", "--engagement", str(engagement),
                             "--reason", "Root was replaced.", "--recorded-at", at(11),
                             "--executor-id", broker, "--session-id", session)
        assert replaced_replay["returncode"] == 0, replaced_replay
        assert replaced_cleanup["returncode"] != 0 and replaced_cleanup["error"]["code"] == "scoped_cleanup_root_changed", replaced_cleanup
        assert replaced_close["returncode"] != 0 and replaced_close["error"]["code"] == "scoped_cleanup_root_changed", replaced_close
        assert (moved_root / effect_name).read_bytes() == EFFECT and not effect_path.exists()
        effect_root.rmdir()
        moved_root.rename(effect_root)
        effect_path.unlink()
        results["physical_root_replacement"] = {"replay": "succeeded", "cleanup": replaced_cleanup["error"]["code"],
                                                 "closure": replaced_close["error"]["code"], "missing_root": missing_close["error"]["code"]}

        blocked_work = root / "blocked-work"
        shutil.copytree(engagement, blocked_work)
        blocked_id = "cleanup-unfinished"
        blocked_name = "unfinished.txt"
        def blocked_proposal(status: str) -> Path:
            value = {"entity_id": blocked_id, "status": status, "cleanup_obligations": [{
                "obligation_id": blocked_id, "kind": "scoped_local_file", "status": status,
                "artifact_refs": [], "rationale": "Keep the synthetic effect unfinished.",
                "closed_at": None if status == "open" else at(12),
                "effect_name": blocked_name, "effect_sha256": digest,
            }]}
            path = root / f"blocked-{status}.json"
            path.write_bytes(canonical_json_bytes(value))
            return path
        for status, second in (("open", 11), ("blocked", 12)):
            if status == "blocked":
                created_blocked = cli("create-scoped-effect", "--engagement", str(blocked_work),
                                      "--obligation-id", blocked_id, "--effect-name", blocked_name,
                                      "--recorded-at", at(11), "--executor-id", broker, "--session-id", session)
                assert created_blocked["returncode"] == 0, created_blocked
            result = cli("record-cleanup", "--scoped", "--engagement", str(blocked_work),
                         "--file", str(blocked_proposal(status)), "--reason", f"Synthetic {status}.",
                         "--recorded-at", at(second), "--executor-id", broker, "--session-id", session)
            assert result["returncode"] == 0, result
        blocked_cleanup_close = cli("close", "--scoped", "--engagement", str(blocked_work),
                                    "--reason", "Cannot close unfinished cleanup.", "--recorded-at", at(13),
                                    "--executor-id", broker, "--session-id", session)
        assert blocked_cleanup_close["returncode"] != 0 and blocked_cleanup_close["error"]["code"] == "engagement_closure_cleanup_remaining", blocked_cleanup_close
        results["blocked_cleanup_exit"] = blocked_cleanup_close["error"]["code"]
        (effect_root / blocked_name).unlink()

        def close(target: Path, seconds: int = 11) -> dict:
            return cli("close", "--scoped", "--engagement", str(target), "--reason", "Close verified synthetic work.",
                       "--recorded-at", at(seconds), "--executor-id", broker, "--session-id", session)

        before_reappearance = len(read_ledger(engagement, "event"))
        effect_path.write_bytes(EFFECT)
        reappeared = close(engagement, 11)
        assert reappeared["returncode"] != 0 and reappeared["error"]["code"] == "scoped_effect_remaining", reappeared
        try:
            close_engagement(engagement, "operator-synthetic", "Operator closure must also recheck effects.", at(11))
        except RecordError as exc:
            operator_reappearance = exc.code
        else:
            operator_reappearance = None
        assert operator_reappearance == "scoped_effect_remaining" and len(read_ledger(engagement, "event")) == before_reappearance and effect_path.read_bytes() == EFFECT
        results["reappeared_effect_blocks_both_closures"] = reappeared["error"]["code"]
        effect_path.unlink()

        # Preserve an actual unfinished terminal event with a live queue identity.
        source = base_event(event_id="event-unfinished-source", engagement_id=engagement.name,
                            recorded_at=at_micro(9, 1), actor_role="orchestrator", actor_id="orchestrator-origin",
                            event_type="observation.recorded", rationale="One unresolved synthetic route remains.",
                            payload={"entity_id": "unfinished-source", "entity_type": "observation", "status": "recorded"},
                            session_id="session-origin", operation_class="notebook")
        append_event(open_work, source)
        route = base_event(event_id="event-unfinished-route", engagement_id=engagement.name,
                           recorded_at=at_micro(9, 2), actor_role="orchestrator", actor_id="orchestrator-origin",
                           event_type="routing.assessed", rationale="Route the unresolved synthetic source.",
                           payload={"entity_id": "unfinished-route", "source_observation_ref": source["event_id"],
                                    "activation_strength": "strong", "card_ids": ["card-synthetic"], "status": "assessed"},
                           entity_refs=[source["event_id"]], session_id="session-origin", operation_class="notebook")
        append_event(open_work, route)
        zero_cost = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0,
                     "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None,
                     "human_review_seconds": 0}
        candidate = base_event(event_id="event-unfinished-candidate", engagement_id=engagement.name,
                               recorded_at=at_micro(9, 3), actor_role="orchestrator", actor_id="orchestrator-origin",
                               event_type="candidate.proposed", rationale="Retain a bounded candidate as unfinished work.",
                               payload={"candidate_id": "candidate-unfinished", "source_observation_ref": source["event_id"],
                                        "routing_review_ref": route["event_id"], "activation_strength": "strong",
                                        "card_ids": ["card-synthetic"], "status": "queued", "expected_information_gain": 1,
                                        "safety_class": "clear_local", "cost_estimate": zero_cost},
                               entity_refs=[source["event_id"], route["event_id"]],
                               state_changes=[{"dimension": "search", "entity_id": "candidate-unfinished", "previous": None, "current": "queued"}],
                               session_id="session-origin", operation_class="notebook")
        candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}
        append_event(open_work, candidate)
        unfinished_state = reduce_engagement(open_work)
        unfinished_attempts = read_ledger(open_work, "attempt")
        blockers = blocking_work_identities(project_current_terminal_work_state(unfinished_state, unfinished_attempts, coverage="blocked"))
        assert any(item["class"] == "candidate_undisposed" and item["entity"]["id"] == "candidate-unfinished" for item in blockers), blockers
        unfinished_reason = "Record exact unfinished synthetic work instead of claiming clean closure."
        unfinished_payload = {"entity_id": engagement.name, "terminal_kind": "engagement", "status": "blocked",
                              "reason": unfinished_reason, "operator_id": "operator-synthetic",
                              "scope_hash": unfinished_state["scope_hash"], "blocking_items": blockers,
                              "blocking_queue_digest": sha256_bytes(canonical_json_bytes(blockers)),
                              **attempt_ledger_context(unfinished_attempts)}
        unfinished_changes = [
            {"dimension": "engagement", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
            {"dimension": "coverage", "entity_id": engagement.name, "previous": "active", "current": "blocked"},
        ]
        unfinished_action = ending_override_action(engagement_id=engagement.name, recorded_at=at(10),
                                                   actor={"role": "operator", "id": "operator-synthetic"},
                                                   payload=unfinished_payload, entity_refs=[], evidence_refs=[],
                                                   state_changes=unfinished_changes, session_id=session)
        action_digest = sha256_bytes(canonical_json_bytes(unfinished_action))
        challenge_bytes = operator_challenge_bytes(engagement_id=engagement.name,
                                                   scope_hash=unfinished_state["scope_hash"],
                                                   ledger_hash=read_ledger(open_work, "event")[-1]["record_hash"],
                                                   operation=f"override-ending:{action_digest}",
                                                   operator_id="operator-synthetic")
        override_challenge = root / "unfinished-override-challenge.json"
        override_challenge.write_bytes(challenge_bytes)
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key),
                        "-n", "llm-redteam-harness-operator-v1", str(override_challenge)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        override_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(override_challenge) + ".sig",
                        "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed)}
        unfinished_override = cli("override-ending", "--engagement", str(open_work),
                                  "--terminal-kind", "engagement", "--status", "blocked",
                                  "--operator-id", "operator-synthetic", "--session-id", session,
                                  "--recorded-at", at(10), "--reason", unfinished_reason, env=override_env)
        assert unfinished_override["returncode"] == 0, unfinished_override
        assert read_ledger(open_work, "event")[-1]["event_type"] == "engagement.ending_overridden"
        blocked_close = close(open_work, 12)
        assert blocked_close["returncode"] != 0, blocked_close
        assert blocked_close["error"]["code"] == "engagement_closure_work_remaining", blocked_close
        assert "candidate_undisposed" in blocked_close["error"]["message"] and "candidate-unfinished" in blocked_close["error"]["message"], blocked_close
        results["unfinished_exit"] = {"terminal_event": unfinished_override["event_id"],
                                       "closure_error": blocked_close["error"]["code"],
                                       "queue_blocker": "candidate_undisposed:candidate-unfinished"}

        closed = close(engagement, 11)
        assert closed["returncode"] == 0 and read_ledger(engagement, "event")[-1]["event_type"] == "engagement.closed", closed
        restarted_closed = cli("reduce", "--engagement", str(engagement))
        assert restarted_closed["returncode"] == 0 and read_ledger(engagement, "event")[-1]["event_type"] == "engagement.closed", restarted_closed
        results["normal_closure"] = "closed with empty blocking queue"
        closed_count = len(read_ledger(engagement, "event"))
        late_open = cli("record-cleanup", "--scoped", "--engagement", str(engagement),
                        "--file", str(blocked_proposal("open")), "--reason", "Late obligation.",
                        "--recorded-at", at(14), "--executor-id", broker, "--session-id", session)
        late_create = create(effect_name, 14)
        assert late_open["error"]["code"] == "scoped_cleanup_after_closure" and late_create["error"]["code"] == "scoped_effect_after_closure", (late_open, late_create)
        assert len(read_ledger(engagement, "event")) == closed_count and not effect_path.exists() and not (effect_root / blocked_name).exists()
        results["closed_is_terminal"] = "open and create rejected without a file or ledger append"
        print(json.dumps({"valid": True, "cases": results}, sort_keys=True))


if __name__ == "__main__":
    main()
