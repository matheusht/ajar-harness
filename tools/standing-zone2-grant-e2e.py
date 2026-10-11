#!/usr/bin/env python3
"""Synthetic public-CLI E2E for the signed local_only_v1 Zone-2 grant.

Run: python3 tools/standing-zone2-grant-e2e.py [--output DIR]
Requires Python dependencies for this repository and /usr/bin/ssh-keygen.
See docs/engineering/standing-zone2-grant-failure-contract.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engagement_records import canonical_json_bytes, sha256_bytes, sha256_file
from engagement_state import SCOPED_EFFECT_BYTES, _append_kernel_event, base_event, read_ledger, reduce_engagement


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/run-engagement.py"
SHELL = str(Path("/bin/sh").resolve(strict=True))
BROKER = f"local-uid-{os.getuid()}:broker"
SESSION = f"session-posix-{os.getuid()}-{os.getsid(0)}"
GOOD_ONE = b"synthetic local artifact one\n"
GOOD_TWO = b"synthetic local artifact two\n"
SECRET_SHAPE = b"Authorization: Bearer synthetic-shape-only-1234567890\n"
OPERATOR = "operator-synthetic"
CLEANUP_ID = "cleanup-local-artifacts"
CLEANUP_EVENT = "event-cleanup-open"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or ROOT / "artifacts/standing-zone2-grant" / f"{timestamp}-{os.getpid()}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    summary: dict[str, object] = {"command": f"{sys.executable} tools/standing-zone2-grant-e2e.py --output {output}",
                                  "result_dir": str(output), "cases": {}}
    base = datetime.now(timezone.utc) - timedelta(seconds=20)

    def at(seconds: float) -> str:
        return (base + timedelta(seconds=seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def at_recorded(recorded: float | datetime, offset: float = 0) -> str:
        origin = base + timedelta(seconds=recorded) if isinstance(recorded, (int, float)) else recorded
        return (origin + timedelta(seconds=offset)).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def command(name: str, *argv: str, input_bytes: bytes | None = None, env: dict[str, str] | None = None) -> dict:
        run = subprocess.run([sys.executable, str(CLI), *argv], cwd=ROOT, input=input_bytes,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
        stdout, stderr = run.stdout.decode(errors="replace"), run.stderr.decode(errors="replace")
        try:
            response = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{name}: CLI did not return JSON: {stdout} {stderr}") from exc
        row = {"name": name, "argv": list(argv), "returncode": run.returncode, "response": response, "stderr": stderr}
        with (output / "commands.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
        return {**response, "returncode": run.returncode}

    def success(result: dict, name: str) -> dict:
        assert result["returncode"] == 0, (name, result)
        return result

    def denied(result: dict, name: str, engagement: Path, destination: Path, before: int) -> str:
        assert result["returncode"] != 0, (name, result)
        assert not destination.exists(), (name, destination)
        assert len(read_ledger(engagement, "artifact")) == before, name
        return result["error"]["code"]

    def scope_text(signers: Path, *, standing: bool, containment: str,
                   mode_fields: str = "", template_authorization: bool = False) -> str:
        grant = mode_fields if mode_fields else ("" if not standing else """- zone2_confirmation_mode: `standing`
- zone2_standing_grant: `yes`
- zone2_standing_grant_contract: `local_only_v1`
- zone2_per_act_confirmation_required: `no`
""")
        scope = f"""# Signed synthetic scope
## Surfaces in scope
- Inert local engagement evidence files only.
## Benign safe-objective set
- Verify exact local artifact creation and cleanup tracking.
## Escalation ceiling
- Local synthetic artifact creation only.
## Impact-demo authorization
- impact_demo_authorized: `yes`
- zone2_authorized_categories: `zone2_artifact_creation`
- zone2_escalation_ceiling: `artifact_creation`
- zone2_containment: `{containment}`
{grant}## Accounts / fixtures
- Synthetic files only; no target, account, provider, or network endpoint.
## Authorization
- Operator allowed signers SHA256: {sha256_file(signers)}
- Operator: {OPERATOR}
- Date: 2026-10-10
- Signed: [x]
- Record kernel: `decision-0006-v2`
"""
        if not template_authorization:
            return scope
        source = (ROOT / "engagements/_TEMPLATE/scope.md").read_text(encoding="utf-8")
        template_block = source.split("## Impact-demo authorization (Zone-2)\n", 1)[1].split(
            "## Impact-maximization mandate", 1)[0]
        replacement = {"impact_demo_authorized": "yes", "zone2_authorized_categories": "zone2_artifact_creation",
                       "zone2_escalation_ceiling": "artifact_creation", "zone2_containment": containment}
        lines = []
        for line in template_block.splitlines():
            field = next((name for name in replacement if line.startswith(f"- **{name}:**")), None)
            lines.append(f"- **{field}:** `{replacement[field]}`" if field else line)
        template_block = "## Impact-demo authorization (Zone-2)\n" + "\n".join(lines).rstrip() + "\n" + grant + "\n"
        head, tail = scope.split("## Impact-demo authorization\n", 1)
        _, tail = tail.split("## Accounts / fixtures\n", 1)
        return head + template_block + "## Accounts / fixtures\n" + tail

    try:
        with tempfile.TemporaryDirectory(prefix="standing-zone2-e2e-") as temporary:
            root = Path(temporary).resolve()
            key = root / "synthetic-ed25519"
            subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                           check=True, stdout=subprocess.DEVNULL)
            signers = root / "allowed-signers"
            signers.write_text(f"{OPERATOR} {key.with_suffix('.pub').read_text().strip()}\n", encoding="utf-8")
            source = root / "inert-source.txt"
            source.write_bytes(b"synthetic preflight identity\n")

            def setup(name: str, *, standing: bool = True, containment: str = "local engagement/evidence/ files inside this engagement only; a prior open cleanup obligation is required; no external effects",
                      mode_fields: str = "", template_authorization: bool = False,
                      scoped_root: Path | None = None) -> tuple[Path, str]:
                engagement = root / name / "synthetic"
                engagement.mkdir(parents=True, exist_ok=True)
                signed_scope = scope_text(
                    signers, standing=standing, containment=containment,
                    mode_fields=mode_fields, template_authorization=template_authorization)
                if scoped_root is not None:
                    signed_scope += ("\n## Scoped cleanup and closure\n"
                                     "- scoped_cleanup_closure: `yes`\n"
                                     f"- scoped_cleanup_root: `{scoped_root}`\n")
                (engagement / "scope.md").write_text(signed_scope, encoding="utf-8")
                challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                             "engagement_id": engagement.name, "scope_hash": sha256_file(engagement / "scope.md"),
                             "ledger_hash": None, "operation": f"initialize-engagement:{at(0)}", "operator_id": OPERATOR}
                challenge_path = root / f"{name}-challenge.json"
                challenge_path.write_bytes(canonical_json_bytes(challenge))
                subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n",
                                "llm-redteam-harness-operator-v1", str(challenge_path)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                signed_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig",
                              "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
                success(command(f"{name}-init", "init", "--engagement", str(engagement),
                                "--recorded-at", at(0), env=signed_env), f"{name}-init")
                (engagement / "evidence").mkdir(exist_ok=True)
                success(command(f"{name}-preflight", "preflight", "--engagement", str(engagement),
                                "--preflight-id", "env-local", "--mode", "local_runtime", "--target", str(source),
                                "--expected-identity", sha256_file(source), "--runtime", SHELL,
                                "--reproduction-argv", json.dumps([SHELL, "-c", "true"]),
                                "--actor-role", "broker", "--actor-id", BROKER, "--session-id", SESSION,
                                "--recorded-at", at(1)), f"{name}-preflight")
                state = reduce_engagement(engagement)
                cleanup_at = at(2)
                cleanup = base_event(event_id=CLEANUP_EVENT, engagement_id=engagement.name,
                                     recorded_at=cleanup_at, actor_role="operator", actor_id=OPERATOR,
                                     event_type="cleanup.updated", rationale="Track both inert local artifacts.",
                                     payload={"entity_id": CLEANUP_ID, "status": "open", "scope_hash": state["scope_hash"],
                                              "operator_id": OPERATOR, "updated_at": cleanup_at,
                                              "cleanup_obligations": [{"obligation_id": CLEANUP_ID, "kind": "local_fixture",
                                                                       "status": "open", "artifact_refs": [],
                                                                       "rationale": "Remove inert synthetic artifacts after this test.", "closed_at": None}]},
                                     state_changes=[{"dimension": "cleanup", "entity_id": CLEANUP_ID,
                                                     "previous": None, "current": "open"}],
                                     session_id="session-operator-synthetic", operation_class="authority")
                # Fixture setup only: this private append does not test public operator authority.
                _append_kernel_event(engagement, cleanup)
                attested = next(event["event_id"] for event in read_ledger(engagement, "event")
                                if event["event_type"] == "scope.attested")
                return engagement, attested

            standing_seed, scope_event = setup("standing-seed")

            def clone(name: str) -> Path:
                destination = root / name / "synthetic"
                destination.parent.mkdir()
                shutil.copytree(standing_seed, destination)
                return destination

            def metadata(engagement: Path, artifact_id: str, *, created: float | datetime,
                         confirmation_ref: str = scope_event, cleanup_ref: str = CLEANUP_EVENT,
                         cleanup_id: str = CLEANUP_ID, environment: str = "env-local") -> Path:
                value = {"schema_version": 1, "artifact_id": artifact_id, "engagement_id": engagement.name,
                         "created_at": at_recorded(created), "producer": {"role": "broker", "id": BROKER},
                         "producer_session_id": SESSION, "operation_class": "real_world",
                         "acquisition_method": "generated_local", "target_refs": [], "environment_ref": environment,
                         "sensitivity": "internal", "redaction_status": "not_needed",
                         "contains_executable_capability": False, "advisory_zone": "review_required",
                         "escalation_confirmation_event_ref": confirmation_ref,
                         "cleanup_obligation_ref": cleanup_ref, "cleanup_obligation_id": cleanup_id,
                         "supersedes_artifact_id": None, "media_type": "text/plain"}
                path = root / f"{engagement.parent.name}-{artifact_id}-metadata.json"
                path.write_bytes(canonical_json_bytes(value))
                return path

            def classify(name: str, engagement: Path, meta: Path, data: bytes, relative: str,
                         *, when: float | datetime = 3) -> tuple[dict, Path]:
                permit = root / f"{name}-permit.json"
                result = command(name, "classify-artifact", "--engagement", str(engagement),
                                 "--metadata", str(meta), "--planned-sha256", sha256_bytes(data),
                                 "--planned-size", str(len(data)), "--relative-path", relative,
                                 "--recorded-at", at_recorded(when), "--actor-role", "broker",
                                 "--actor-id", BROKER, "--session-id", SESSION, "--output", str(permit))
                return result, permit

            def create(name: str, engagement: Path, meta: Path, permit: Path, data: bytes) -> dict:
                return command(name, "create-artifact", "--engagement", str(engagement),
                               "--metadata", str(meta), "--classification", str(permit),
                               "--actor-id", BROKER, "--session-id", SESSION, input_bytes=data)

            def approved_scope_reattestation(name: str, engagement: Path, *, recorded: float | datetime) -> tuple[Path, str, str]:
                draft = root / f"{name}-scope-draft.md"
                draft.write_text((engagement / "scope.md").read_text(encoding="utf-8") +
                                 f"\n## Synthetic amendment\n- {name}\n", encoding="utf-8")
                proposed = success(command(f"{name}-propose", "propose-scope", "--engagement", str(engagement),
                                           "--draft", str(draft), "--actor-id", BROKER, "--session-id", SESSION,
                                           "--recorded-at", at_recorded(recorded), "--reason", "Propose an inert scope edit."),
                                   f"{name}-propose")
                draft_digest = proposed["draft_digest"]
                lane_id, request_id = f"lane-{name}", f"request-{name}"
                apply_at = at_recorded(recorded, 3)
                action = {"action_kind": "reattest-scope", "lane_id": lane_id, "executor_id": BROKER,
                          "session_id": SESSION, "draft_digest": draft_digest,
                          "operator_id": OPERATOR, "recorded_at": apply_at}
                action_file = root / f"{name}-authority-action.json"
                action_file.write_bytes(canonical_json_bytes(action))
                success(command(f"{name}-request", "request-authority", "--engagement", str(engagement),
                                "--request-id", request_id, "--action-kind", "reattest-scope",
                                "--action-file", str(action_file), "--lane-id", lane_id,
                                "--actor-role", "broker", "--actor-id", BROKER, "--session-id", SESSION,
                                "--recorded-at", at_recorded(recorded, 1), "--expires-at", at_recorded(recorded, 600),
                                "--reason", "Request exact synthetic scope re-attestation."), f"{name}-request")
                latest_events = read_ledger(engagement, "event")
                challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                             "engagement_id": engagement.name,
                             "scope_hash": reduce_engagement(engagement)["scope_hash"],
                             "ledger_hash": latest_events[-1]["record_hash"],
                             "operation": f"resolve-authority:{request_id}:{sha256_bytes(canonical_json_bytes(action))}:approved:{at_recorded(recorded, 2)}",
                             "operator_id": OPERATOR}
                challenge_file = root / f"{name}-resolve-challenge.json"
                challenge_file.write_bytes(canonical_json_bytes(challenge))
                subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n",
                                "llm-redteam-harness-operator-v1", str(challenge_file)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                signed_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_file) + ".sig",
                              "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
                success(command(f"{name}-resolve", "resolve-authority", "--engagement", str(engagement),
                                "--request-id", request_id, "--resolution", "approved",
                                "--operator-id", OPERATOR, "--session-id", SESSION,
                                "--recorded-at", at_recorded(recorded, 2),
                                "--reason", "Approve exact inert scope edit.", env=signed_env), f"{name}-resolve")
                return draft, request_id, lane_id

            def reattest(name: str, engagement: Path, draft: Path, request_id: str,
                         lane_id: str, *, recorded: float | datetime) -> dict:
                return command(name, "reattest-scope", "--engagement", str(engagement), "--draft", str(draft),
                               "--operator-id", OPERATOR, "--recorded-at", at_recorded(recorded, 3),
                               "--reason", "Apply exact inert scope edit.", "--authority-request-id", request_id,
                               "--lane-id", lane_id, "--executor-id", BROKER, "--session-id", SESSION)

            def public_fresh_creation(name: str, engagement: Path) -> dict:
                artifact_id, event_id = f"artifact-{name}", f"event-confirm-{name}"
                relative = f"evidence/{name}.txt"
                fresh_at = datetime.now(timezone.utc)
                meta = metadata(engagement, artifact_id, created=fresh_at + timedelta(seconds=2),
                                confirmation_ref=event_id)
                state = reduce_engagement(engagement)
                plan = {"artifact_id": artifact_id, "metadata_digest": sha256_bytes(meta.read_bytes()),
                        "planned_sha256": sha256_bytes(GOOD_ONE), "planned_size": len(GOOD_ONE),
                        "relative_path": relative, "scope_hash": state["scope_hash"],
                        "environment_ref": "env-local", "cleanup_obligation_ref": CLEANUP_EVENT,
                        "cleanup_obligation_id": CLEANUP_ID}
                action_digest = sha256_bytes(canonical_json_bytes(plan))
                confirm_at, expires_at = at_recorded(fresh_at), at_recorded(fresh_at, 300)
                proposal = base_event(event_id=event_id, engagement_id=engagement.name,
                                      recorded_at=confirm_at, actor_role="operator", actor_id=OPERATOR,
                                      event_type="escalation.confirmed", rationale="Confirm one exact inert file.",
                                      payload={"entity_id": artifact_id, "status": "confirmed",
                                               "confirmation_scope": "zone2_artifact_creation",
                                               "environment_ref": "env-local", "expires_at": expires_at,
                                               "cleanup_obligation_ref": CLEANUP_EVENT,
                                               "cleanup_obligation_id": CLEANUP_ID,
                                               "action_digest": action_digest,
                                               "confirmation": {"category": "zone2_artifact_creation",
                                                                "bounded_action": artifact_id,
                                                                "scope_hash": state["scope_hash"],
                                                                "operator_id": OPERATOR,
                                                                "confirmed_at": confirm_at,
                                                                "expires_at": expires_at}},
                                      session_id=SESSION, operation_class="real_world")
                plan_file = root / f"{name}-plan.json"
                proposal_file = root / f"{name}-confirm-event.json"
                plan_file.write_bytes(canonical_json_bytes(plan))
                proposal_file.write_bytes(canonical_json_bytes(proposal))
                challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
                             "engagement_id": engagement.name, "scope_hash": state["scope_hash"],
                             "ledger_hash": read_ledger(engagement, "event")[-1]["record_hash"],
                             "operation": f"confirm-zone2:{action_digest}:{event_id}:{confirm_at}:{expires_at}",
                             "operator_id": OPERATOR}
                challenge_file = root / f"{name}-confirm-challenge.json"
                challenge_file.write_bytes(canonical_json_bytes(challenge))
                subprocess.run(["/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n",
                                "llm-redteam-harness-operator-v1", str(challenge_file)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                signed_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_file) + ".sig",
                              "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
                confirmed = success(command(f"{name}-public-confirm", "confirm-zone2", "--engagement",
                                            str(engagement), "--file", str(proposal_file), "--plan", str(plan_file),
                                            "--operator-id", OPERATOR, env=signed_env), f"{name}-public-confirm")
                classified, permit = classify(f"{name}-classify", engagement, meta, GOOD_ONE, relative,
                                              when=fresh_at + timedelta(seconds=1))
                success(classified, f"{name}-classify")
                assert classified["decision"] == "allow_confirmed_creation", classified
                created = success(create(f"{name}-create", engagement, meta, permit, GOOD_ONE), f"{name}-create")
                assert (engagement / relative).read_bytes() == GOOD_ONE
                success(command(f"{name}-check-resume", "check-resume", "--engagement", str(engagement)),
                        f"{name}-check-resume")
                return {"confirmation_event_ref": confirmed["event_id"], "artifact_id": artifact_id,
                        "artifact_record_hash": created["record_hash"]}

            def scoped_cleanup(name: str, engagement: Path, *, obligation_id: str,
                               effect_name: str, status: str, recorded: float) -> dict:
                proposal = {"entity_id": obligation_id, "status": status,
                            "cleanup_obligations": [{"obligation_id": obligation_id,
                                                     "kind": "scoped_local_file", "status": status,
                                                     "artifact_refs": [],
                                                     "rationale": "Track one exact inert transient effect; evidence remains immutable.",
                                                     "closed_at": None if status == "open" else at(recorded),
                                                     "effect_name": effect_name,
                                                     "effect_sha256": sha256_bytes(SCOPED_EFFECT_BYTES)}]}
                proposal_file = root / f"{name}-{status}-cleanup.json"
                proposal_file.write_bytes(canonical_json_bytes(proposal))
                return command(f"{name}-{status}-scoped-cleanup", "record-cleanup", "--engagement",
                               str(engagement), "--file", str(proposal_file), "--scoped",
                               "--executor-id", BROKER, "--session-id", SESSION,
                               "--recorded-at", at(recorded),
                               "--reason", "Track one exact inert transient effect.")

            def scoped_effect(name: str, engagement: Path, *, obligation_id: str,
                              effect_name: str, recorded: float) -> dict:
                return command(name, "create-scoped-effect", "--engagement", str(engagement),
                               "--obligation-id", obligation_id, "--effect-name", effect_name,
                               "--recorded-at", at(recorded), "--executor-id", BROKER,
                               "--session-id", SESSION)

            def seed_pending_journal(engagement: Path, artifact_id: str, relative: str,
                                     meta: Path, permit_path: Path, opening_ref: str,
                                     obligation_id: str, scope_event_ref: str) -> tuple[Path, bytes]:
                permit_value = json.loads(permit_path.read_text(encoding="utf-8"))
                plan = {"artifact_id": artifact_id, "metadata_digest": sha256_bytes(meta.read_bytes()),
                        "planned_sha256": permit_value["source_digest"],
                        "planned_size": permit_value["source_size"], "relative_path": relative,
                        "scope_hash": permit_value["scope_hash"],
                        "environment_ref": permit_value["environment_ref"],
                        "cleanup_obligation_ref": opening_ref, "cleanup_obligation_id": obligation_id}
                journal = {"schema_version": 1, "artifact_id": artifact_id,
                           "action_digest": sha256_bytes(canonical_json_bytes(plan)),
                           "classification_digest": sha256_bytes(canonical_json_bytes({
                               key: value for key, value in permit_value.items()
                               if key != "classification_event_ref"})),
                           "relative_path": relative, "source_digest": permit_value["source_digest"],
                           "source_size": permit_value["source_size"],
                           "confirmation_event_ref": scope_event_ref}
                journal_path = engagement / "legacy/zone2-pending" / f"{artifact_id}.json"
                journal_path.parent.mkdir(parents=True, exist_ok=True)
                journal_bytes = canonical_json_bytes(journal)
                journal_path.write_bytes(journal_bytes)
                return journal_path, journal_bytes

            positive = clone("two-artifacts")
            positive_rows = []
            positive_permits = []
            for index, data in enumerate((GOOD_ONE, GOOD_TWO), start=1):
                artifact_id = f"artifact-{index}"
                relative = f"evidence/{artifact_id}.txt"
                meta = metadata(positive, artifact_id, created=index * 2 + 2)
                classified, permit = classify(f"positive-classify-{index}", positive, meta, data, relative,
                                              when=index * 2 + 1)
                success(classified, f"positive-classify-{index}")
                assert classified["decision"] == "allow_scope_grant_creation", classified
                positive_permits.append(json.loads(permit.read_text()))
                success(create(f"positive-create-{index}", positive, meta, permit, data), f"positive-create-{index}")
                assert (positive / relative).read_bytes() == data
                positive_rows.append(artifact_id)
            artifacts = read_ledger(positive, "artifact")
            assert [row["artifact_id"] for row in artifacts] == positive_rows, artifacts
            assert all(row["sha256"] == sha256_bytes(data) and
                       row["classified_source_digest"] == sha256_bytes(data) and
                       row["classified_source_size"] == len(data) and
                       row["precreation_classification_event_ref"] == permit["classification_event_ref"] and
                       row["precreation_classification_digest"] == sha256_bytes(canonical_json_bytes({
                           key: value for key, value in permit.items() if key != "classification_event_ref"})) and
                       row["cleanup_obligation_ref"] == CLEANUP_EVENT and
                       row["cleanup_obligation_id"] == CLEANUP_ID and
                       row["escalation_confirmation_event_ref"] == scope_event and
                       row["environment_ref"] == "env-local" and
                       row["precreation_classification_digest"]
                       for row, data, permit in zip(artifacts, (GOOD_ONE, GOOD_TWO), positive_permits)), artifacts
            success(command("positive-check-resume", "check-resume", "--engagement", str(positive)), "positive-check-resume")
            summary["cases"]["two_artifacts_one_grant"] = {"artifact_ids": positive_rows,
                                                          "artifact_bindings": [{**{key: row[key] for key in (
                                                              "artifact_id", "record_hash", "sha256",
                                                              "environment_ref", "cleanup_obligation_ref", "cleanup_obligation_id",
                                                              "escalation_confirmation_event_ref", "precreation_classification_event_ref",
                                                              "precreation_classification_digest", "classified_source_digest",
                                                              "classified_source_size")}, "scope_hash": permit["scope_hash"]}
                                                              for row, permit in zip(artifacts, positive_permits)],
                                                          "scope_attestation_event_ref": scope_event,
                                                          "cleanup_obligation_ref": CLEANUP_EVENT}

            equal_time = clone("equal-time-reattest")
            equal_time_rows = []
            equal_apply_at = datetime.now(timezone.utc) + timedelta(seconds=45)
            for index, (created, classified_at) in enumerate((
                (equal_apply_at - timedelta(seconds=4), equal_apply_at - timedelta(seconds=6)),
                (equal_apply_at, equal_apply_at - timedelta(seconds=5)),
            ), start=1):
                artifact_id = f"artifact-equal-time-{index}"
                relative = f"evidence/equal-time-{index}.txt"
                meta = metadata(equal_time, artifact_id, created=created)
                classified, permit = classify(f"equal-time-{index}-classify", equal_time,
                                              meta, GOOD_ONE, relative, when=classified_at)
                success(classified, f"equal-time-{index}-classify")
                success(create(f"equal-time-{index}-create", equal_time,
                               meta, permit, GOOD_ONE), f"equal-time-{index}-create")
                equal_time_rows.append(artifact_id)
            prior_scope = reduce_engagement(equal_time)["scope_hash"]
            equal_events = read_ledger(equal_time, "event")
            second_classification = next(event for event in equal_events
                                         if event["event_id"] == "event-classification-artifact-equal-time-2")
            equal_authority_at = equal_apply_at - timedelta(seconds=3)
            equal_draft, equal_request, equal_lane = approved_scope_reattestation(
                "equal-time-reattest", equal_time, recorded=equal_authority_at)
            equal_result = success(reattest("equal-time-reattest-apply", equal_time,
                                            equal_draft, equal_request, equal_lane, recorded=equal_authority_at),
                                   "equal-time-reattest-apply")
            equal_event = next(event for event in read_ledger(equal_time, "event")
                               if event["event_id"] == equal_result["event_id"])
            assert equal_event["recorded_at"] == at_recorded(equal_apply_at)
            assert equal_event["sequence"] > second_classification["sequence"]
            assert [item["artifact_id"] for item in read_ledger(equal_time, "artifact")] == equal_time_rows
            success(command("equal-time-reattest-check-resume", "check-resume",
                            "--engagement", str(equal_time)), "equal-time-reattest-check-resume")
            summary["cases"]["equal_time_reattest_history"] = {
                "artifact_ids": equal_time_rows, "prior_scope_hash": prior_scope,
                "later_scope_event_ref": equal_result["event_id"],
                "same_recorded_at": at_recorded(equal_apply_at)}

            completed = clone("completed-stale-journal")
            completed_id = "artifact-completed-stale-journal"
            completed_relative = "evidence/completed-stale-journal.txt"
            completed_meta = metadata(completed, completed_id, created=5)
            classified, completed_permit = classify("completed-stale-journal-classify", completed,
                                                     completed_meta, GOOD_ONE, completed_relative, when=3)
            success(classified, "completed-stale-journal-classify")
            success(create("completed-stale-journal-create", completed,
                           completed_meta, completed_permit, GOOD_ONE), "completed-stale-journal-create")
            original_artifacts = (completed / "artifacts.jsonl").read_bytes()
            permit_value = json.loads(completed_permit.read_text(encoding="utf-8"))
            completed_plan = {"artifact_id": completed_id,
                              "metadata_digest": sha256_bytes(completed_meta.read_bytes()),
                              "planned_sha256": permit_value["source_digest"],
                              "planned_size": permit_value["source_size"],
                              "relative_path": completed_relative, "scope_hash": permit_value["scope_hash"],
                              "environment_ref": permit_value["environment_ref"],
                              "cleanup_obligation_ref": CLEANUP_EVENT, "cleanup_obligation_id": CLEANUP_ID}
            completed_journal = {"schema_version": 1, "artifact_id": completed_id,
                                 "action_digest": sha256_bytes(canonical_json_bytes(completed_plan)),
                                 "classification_digest": sha256_bytes(canonical_json_bytes({
                                     key: value for key, value in permit_value.items()
                                     if key != "classification_event_ref"})),
                                 "relative_path": completed_relative,
                                 "source_digest": permit_value["source_digest"],
                                 "source_size": permit_value["source_size"],
                                 "confirmation_event_ref": scope_event}
            completed_journal_path = completed / "legacy/zone2-pending" / f"{completed_id}.json"
            completed_journal_path.parent.mkdir(parents=True, exist_ok=True)
            completed_journal_path.write_bytes(canonical_json_bytes(completed_journal))
            closure_at = at(6)
            closure = base_event(event_id="event-completed-stale-journal-cleanup-closed",
                                 engagement_id=completed.name, recorded_at=closure_at,
                                 actor_role="operator", actor_id=OPERATOR, event_type="cleanup.updated",
                                 rationale="Close the separate synthetic cleanup obligation after artifact commit.",
                                 payload={"entity_id": CLEANUP_ID, "status": "completed",
                                          "scope_hash": reduce_engagement(completed)["scope_hash"],
                                          "operator_id": OPERATOR, "updated_at": closure_at,
                                          "cleanup_obligations": [{"obligation_id": CLEANUP_ID,
                                                                   "kind": "local_fixture", "status": "completed",
                                                                   "artifact_refs": [completed_id],
                                                                   "rationale": "Synthetic transient work is complete; evidence remains immutable.",
                                                                   "closed_at": closure_at}]},
                                 state_changes=[{"dimension": "cleanup", "entity_id": CLEANUP_ID,
                                                 "previous": "open", "current": "completed"}],
                                 session_id="session-operator-synthetic", operation_class="authority")
            _append_kernel_event(completed, closure)
            retried = success(create("completed-stale-journal-retry", completed,
                                     completed_meta, completed_permit, GOOD_ONE),
                              "completed-stale-journal-retry")
            assert retried["resumed"] is True, retried
            assert not completed_journal_path.exists()
            assert (completed / completed_relative).read_bytes() == GOOD_ONE
            assert (completed / "artifacts.jsonl").read_bytes() == original_artifacts
            success(command("completed-stale-journal-check-resume", "check-resume",
                            "--engagement", str(completed)), "completed-stale-journal-check-resume")
            summary["cases"]["completed_stale_journal"] = {"artifact_id": completed_id,
                                                                "record_hash": retried["record_hash"],
                                                                "journal_cleared": True}

            no_grant, no_grant_scope_event = setup("no-grant", standing=False)
            no_grant_meta = metadata(no_grant, "artifact-no-grant", created=4, confirmation_ref=no_grant_scope_event)
            rejected, _ = classify("no-grant-classify", no_grant, no_grant_meta, GOOD_ONE, "evidence/no-grant.txt")
            summary["cases"]["no_grant"] = denied(rejected, "no-grant", no_grant,
                                                   no_grant / "evidence/no-grant.txt", 0)

            template_fresh, _ = setup("template-fresh", standing=False, template_authorization=True)
            summary["cases"]["template_fresh_public_confirmation"] = public_fresh_creation(
                "template-fresh", template_fresh)

            explicit_fresh_fields = """- zone2_confirmation_mode: `fresh`
- zone2_standing_grant: `no`
- zone2_standing_grant_contract: `none`
- zone2_per_act_confirmation_required: `yes`
"""
            explicit_fresh, _ = setup("explicit-fresh", standing=False, mode_fields=explicit_fresh_fields)
            summary["cases"]["explicit_fresh_public_confirmation"] = public_fresh_creation(
                "explicit-fresh", explicit_fresh)

            incomplete_fields = """- zone2_confirmation_mode: `standing`
- zone2_standing_grant: `yes`
- zone2_per_act_confirmation_required: `no`
"""
            incomplete, incomplete_event = setup("incomplete-standing", standing=False,
                                                  mode_fields=incomplete_fields)
            incomplete_meta = metadata(incomplete, "artifact-incomplete-standing", created=4,
                                       confirmation_ref=incomplete_event)
            rejected, _ = classify("incomplete-standing-classify", incomplete, incomplete_meta,
                                   GOOD_ONE, "evidence/incomplete-standing.txt")
            summary["cases"]["incomplete_standing"] = denied(rejected, "incomplete-standing", incomplete,
                                                                  incomplete / "evidence/incomplete-standing.txt", 0)

            v2_root = root / "v2-scoped" / "synthetic" / "sandbox"
            v2_root.mkdir(parents=True, mode=0o700)
            v2_scoped, v2_scope_event = setup("v2-scoped", scoped_root=v2_root)
            v2_obligation, v2_effect_name = "cleanup-v2-scoped", "effect-v2-scoped.txt"
            opened = success(scoped_cleanup("v2-scoped", v2_scoped, obligation_id=v2_obligation,
                                            effect_name=v2_effect_name, status="open", recorded=3),
                             "v2-scoped-open")
            v2_artifact_ids = []
            for index, (created, classified_at) in enumerate(((5, 4), (7, 6)), start=1):
                artifact_id = f"artifact-v2-scoped-{index}"
                relative = f"evidence/v2-scoped-{index}.txt"
                meta = metadata(v2_scoped, artifact_id, created=created,
                                confirmation_ref=v2_scope_event, cleanup_ref=opened["event_id"],
                                cleanup_id=v2_obligation)
                classified, permit = classify(f"v2-scoped-{index}-classify", v2_scoped,
                                              meta, GOOD_ONE, relative, when=classified_at)
                success(classified, f"v2-scoped-{index}-classify")
                assert classified["decision"] == "allow_scope_grant_creation", classified
                success(create(f"v2-scoped-{index}-create", v2_scoped,
                               meta, permit, GOOD_ONE), f"v2-scoped-{index}-create")
                v2_artifact_ids.append(artifact_id)
            created_effect = success(scoped_effect("v2-scoped-create-effect", v2_scoped,
                                                   obligation_id=v2_obligation,
                                                   effect_name=v2_effect_name, recorded=7),
                                     "v2-scoped-create-effect")
            assert (v2_root / v2_effect_name).read_bytes() == SCOPED_EFFECT_BYTES
            closed_effect = success(scoped_cleanup("v2-scoped", v2_scoped, obligation_id=v2_obligation,
                                                   effect_name=v2_effect_name, status="completed", recorded=7),
                                    "v2-scoped-complete")
            assert not (v2_root / v2_effect_name).exists()
            assert [item["artifact_id"] for item in read_ledger(v2_scoped, "artifact")] == v2_artifact_ids
            assert all((v2_scoped / f"evidence/v2-scoped-{index}.txt").read_bytes() == GOOD_ONE
                       for index in (1, 2))
            success(command("v2-scoped-check-resume", "check-resume", "--engagement", str(v2_scoped)),
                    "v2-scoped-check-resume")
            summary["cases"]["v2_public_scoped_cleanup"] = {
                "opening_event_ref": opened["event_id"], "effect_event_ref": created_effect["event_id"],
                "completion_event_ref": closed_effect["event_id"], "artifact_ids": v2_artifact_ids,
                "effect_absent": True}
            completed_event = next(event for event in read_ledger(v2_scoped, "event")
                                   if event["event_id"] == closed_effect["event_id"])
            second_artifact = next(item for item in read_ledger(v2_scoped, "artifact")
                                   if item["artifact_id"] == v2_artifact_ids[1])
            assert completed_event["recorded_at"] == second_artifact["created_at"]
            summary["cases"]["same_timestamp_cleanup_after_create"] = {
                "artifact_id": second_artifact["artifact_id"],
                "artifact_record_hash": second_artifact["record_hash"],
                "completion_event_ref": completed_event["event_id"],
                "same_recorded_at": completed_event["recorded_at"]}

            pending_root = root / "v2-scoped-pending" / "synthetic" / "sandbox"
            pending_root.mkdir(parents=True, mode=0o700)
            pending_scope, pending_scope_event = setup("v2-scoped-pending", scoped_root=pending_root)
            pending_id, pending_effect = "cleanup-v2-pending", "effect-v2-pending.txt"
            pending_open = success(scoped_cleanup("v2-pending-open", pending_scope,
                                                  obligation_id=pending_id, effect_name=pending_effect,
                                                  status="open", recorded=3), "v2-pending-open")
            pending_artifact_id, pending_relative = "artifact-v2-pending", "evidence/v2-pending.txt"
            pending_meta = metadata(pending_scope, pending_artifact_id, created=5,
                                    confirmation_ref=pending_scope_event,
                                    cleanup_ref=pending_open["event_id"], cleanup_id=pending_id)
            classified, pending_permit = classify("v2-pending-classify", pending_scope, pending_meta,
                                                   GOOD_ONE, pending_relative, when=4)
            success(classified, "v2-pending-classify")
            pending_journal_path, pending_journal_bytes = seed_pending_journal(
                pending_scope, pending_artifact_id, pending_relative, pending_meta, pending_permit,
                pending_open["event_id"], pending_id, pending_scope_event)
            pending_event_bytes = (pending_scope / "events.jsonl").read_bytes()
            attempt = scoped_cleanup("v2-pending-not-applicable", pending_scope,
                                     obligation_id=pending_id, effect_name=pending_effect,
                                     status="not_applicable", recorded=6)
            assert attempt["returncode"] != 0, attempt
            assert attempt["error"]["code"] == "scoped_cleanup_zone2_pending", attempt
            assert "create-artifact" in attempt["error"]["message"], attempt
            settlement_denials = {"not_applicable": attempt["error"]["code"]}
            assert (pending_scope / "events.jsonl").read_bytes() == pending_event_bytes
            assert pending_journal_path.read_bytes() == pending_journal_bytes
            assert not (pending_scope / pending_relative).exists()
            recovered = success(create("v2-pending-recover", pending_scope, pending_meta,
                                       pending_permit, GOOD_ONE), "v2-pending-recover")
            assert not pending_journal_path.exists()
            settled = success(scoped_cleanup("v2-pending-settle", pending_scope,
                                             obligation_id=pending_id, effect_name=pending_effect,
                                             status="not_applicable", recorded=6), "v2-pending-settle")
            success(command("v2-pending-check-resume", "check-resume", "--engagement", str(pending_scope)),
                    "v2-pending-check-resume")

            effect_pending_root = root / "v2-scoped-effect-pending" / "synthetic" / "sandbox"
            effect_pending_root.mkdir(parents=True, mode=0o700)
            effect_pending_scope, effect_pending_scope_event = setup(
                "v2-scoped-effect-pending", scoped_root=effect_pending_root)
            effect_pending_id, effect_pending_name = "cleanup-v2-effect-pending", "effect-v2-effect-pending.txt"
            effect_pending_open = success(scoped_cleanup("v2-effect-pending-open", effect_pending_scope,
                                                         obligation_id=effect_pending_id,
                                                         effect_name=effect_pending_name,
                                                         status="open", recorded=3), "v2-effect-pending-open")
            success(scoped_effect("v2-effect-pending-create-effect", effect_pending_scope,
                                  obligation_id=effect_pending_id, effect_name=effect_pending_name,
                                  recorded=4), "v2-effect-pending-create-effect")
            effect_pending_artifact, effect_pending_relative = (
                "artifact-v2-effect-pending", "evidence/v2-effect-pending.txt")
            effect_pending_meta = metadata(effect_pending_scope, effect_pending_artifact, created=6,
                                           confirmation_ref=effect_pending_scope_event,
                                           cleanup_ref=effect_pending_open["event_id"],
                                           cleanup_id=effect_pending_id)
            classified, effect_pending_permit = classify(
                "v2-effect-pending-classify", effect_pending_scope, effect_pending_meta, GOOD_ONE,
                effect_pending_relative, when=5)
            success(classified, "v2-effect-pending-classify")
            effect_pending_journal_path, effect_pending_journal_bytes = seed_pending_journal(
                effect_pending_scope, effect_pending_artifact, effect_pending_relative,
                effect_pending_meta, effect_pending_permit, effect_pending_open["event_id"],
                effect_pending_id, effect_pending_scope_event)
            effect_pending_events = (effect_pending_scope / "events.jsonl").read_bytes()
            for status in ("blocked", "completed"):
                attempt = scoped_cleanup(f"v2-effect-pending-{status}", effect_pending_scope,
                                         obligation_id=effect_pending_id, effect_name=effect_pending_name,
                                         status=status, recorded=7)
                assert attempt["returncode"] != 0, (status, attempt)
                assert attempt["error"]["code"] == "scoped_cleanup_zone2_pending", (status, attempt)
                assert "create-artifact" in attempt["error"]["message"], (status, attempt)
                settlement_denials[status] = attempt["error"]["code"]
            assert (effect_pending_scope / "events.jsonl").read_bytes() == effect_pending_events
            assert effect_pending_journal_path.read_bytes() == effect_pending_journal_bytes
            assert (effect_pending_root / effect_pending_name).read_bytes() == SCOPED_EFFECT_BYTES
            effect_recovered = success(create("v2-effect-pending-recover", effect_pending_scope,
                                              effect_pending_meta, effect_pending_permit, GOOD_ONE),
                                       "v2-effect-pending-recover")
            assert not effect_pending_journal_path.exists()
            effect_settled = success(scoped_cleanup("v2-effect-pending-settle", effect_pending_scope,
                                                    obligation_id=effect_pending_id,
                                                    effect_name=effect_pending_name,
                                                    status="completed", recorded=7), "v2-effect-pending-settle")
            assert not (effect_pending_root / effect_pending_name).exists()
            success(command("v2-effect-pending-check-resume", "check-resume",
                            "--engagement", str(effect_pending_scope)), "v2-effect-pending-check-resume")
            summary["cases"]["v2_pending_journal_settlement"] = {
                "denials": settlement_denials, "artifact_id": pending_artifact_id,
                "artifact_record_hash": recovered["record_hash"],
                "settlement_event_ref": settled["event_id"],
                "effect_artifact_id": effect_pending_artifact,
                "effect_artifact_record_hash": effect_recovered["record_hash"],
                "effect_settlement_event_ref": effect_settled["event_id"],
                "journals_cleared": True}

            alone_root = root / "v2-scoped-alone-root"
            alone_root.mkdir(mode=0o700)
            scoped_alone, _ = setup("v2-scoped-alone", standing=False, scoped_root=alone_root)
            alone_before = (scoped_alone / "events.jsonl").read_bytes()
            alone_open = scoped_cleanup("v2-scoped-alone", scoped_alone,
                                        obligation_id="cleanup-v2-scoped-alone",
                                        effect_name="effect-v2-alone.txt", status="open", recorded=3)
            assert alone_open["returncode"] != 0 and (scoped_alone / "events.jsonl").read_bytes() == alone_before
            assert not (alone_root / "effect-v2-alone.txt").exists()
            summary["cases"]["v2_scoped_without_standing"] = alone_open["error"]["code"]

            missing_root = root / "v2-scoped-missing-root"
            wrong_root_scope, _ = setup("v2-scoped-wrong-root", scoped_root=missing_root)
            wrong_root_before = (wrong_root_scope / "events.jsonl").read_bytes()
            wrong_root_open = scoped_cleanup("v2-scoped-wrong-root", wrong_root_scope,
                                             obligation_id="cleanup-v2-wrong-root",
                                             effect_name="effect-v2-wrong-root.txt", status="open", recorded=3)
            assert wrong_root_open["returncode"] != 0
            assert (wrong_root_scope / "events.jsonl").read_bytes() == wrong_root_before
            assert not missing_root.exists()
            summary["cases"]["v2_scoped_missing_root"] = wrong_root_open["error"]["code"]

            identity_root = root / "v2-scoped-identity-root"
            identity_root.mkdir(mode=0o700)
            identity_scope, _ = setup("v2-scoped-moved-root", scoped_root=identity_root)
            identity_obligation, identity_effect = "cleanup-v2-moved-root", "effect-v2-moved-root.txt"
            success(scoped_cleanup("v2-scoped-moved-root", identity_scope, obligation_id=identity_obligation,
                                   effect_name=identity_effect, status="open", recorded=3), "v2-scoped-moved-open")
            identity_root.rename(root / "v2-scoped-original-root")
            identity_root.mkdir(mode=0o700)
            moved_before = (identity_scope / "events.jsonl").read_bytes()
            moved_result = scoped_effect("v2-scoped-moved-create", identity_scope,
                                         obligation_id=identity_obligation,
                                         effect_name=identity_effect, recorded=4)
            assert moved_result["returncode"] != 0
            assert (identity_scope / "events.jsonl").read_bytes() == moved_before
            assert not (identity_root / identity_effect).exists()
            summary["cases"]["v2_scoped_moved_root"] = moved_result["error"]["code"]

            identity_check_root = root / "v2-scoped-effect-identity-root"
            identity_check_root.mkdir(mode=0o700)
            identity_check, _ = setup("v2-scoped-effect-identity", scoped_root=identity_check_root)
            identity_check_id, bound_effect = "cleanup-v2-identity", "effect-v2-bound.txt"
            success(scoped_cleanup("v2-scoped-effect-identity", identity_check,
                                   obligation_id=identity_check_id, effect_name=bound_effect,
                                   status="open", recorded=3), "v2-scoped-identity-open")
            identity_before = (identity_check / "events.jsonl").read_bytes()
            wrong_identity = scoped_effect("v2-scoped-wrong-effect", identity_check,
                                            obligation_id=identity_check_id,
                                            effect_name="effect-v2-unbound.txt", recorded=4)
            assert wrong_identity["returncode"] != 0
            assert (identity_check / "events.jsonl").read_bytes() == identity_before
            assert not (identity_check_root / "effect-v2-unbound.txt").exists()
            summary["cases"]["v2_scoped_wrong_effect_identity"] = wrong_identity["error"]["code"]

            tampered_root = root / "v2-scoped-tampered-root"
            tampered_root.mkdir(mode=0o700)
            tampered, _ = setup("v2-scoped-tampered", scoped_root=tampered_root)
            tampered_id, tampered_name = "cleanup-v2-tampered", "effect-v2-tampered.txt"
            success(scoped_cleanup("v2-scoped-tampered", tampered, obligation_id=tampered_id,
                                   effect_name=tampered_name, status="open", recorded=3),
                    "v2-scoped-tampered-open")
            tampered_bytes = b"different inert local bytes\n"
            (tampered_root / tampered_name).write_bytes(tampered_bytes)
            tampered_before = (tampered / "events.jsonl").read_bytes()
            tampered_create = scoped_effect("v2-scoped-tampered-create", tampered,
                                            obligation_id=tampered_id, effect_name=tampered_name,
                                            recorded=4)
            tampered_complete = scoped_cleanup("v2-scoped-tampered", tampered,
                                               obligation_id=tampered_id, effect_name=tampered_name,
                                               status="completed", recorded=5)
            assert tampered_create["returncode"] != 0 and tampered_complete["returncode"] != 0
            assert (tampered / "events.jsonl").read_bytes() == tampered_before
            assert (tampered_root / tampered_name).read_bytes() == tampered_bytes
            summary["cases"]["v2_scoped_tampered_effect"] = {
                "create_denial": tampered_create["error"]["code"],
                "complete_denial": tampered_complete["error"]["code"]}
            arbitrary_effect = scoped_effect("v2-scoped-arbitrary-effect", identity_check,
                                              obligation_id="cleanup-v2-unknown",
                                              effect_name="effect-v2-arbitrary.txt", recorded=4)
            assert arbitrary_effect["returncode"] != 0
            assert (identity_check / "events.jsonl").read_bytes() == identity_before
            assert not (identity_check_root / "effect-v2-arbitrary.txt").exists()
            summary["cases"]["v2_scoped_arbitrary_effect"] = arbitrary_effect["error"]["code"]

            stale = clone("stale-scope")
            stale_meta = metadata(stale, "artifact-stale", created=4)
            classified, stale_permit = classify("stale-classify", stale, stale_meta, GOOD_ONE, "evidence/stale.txt")
            success(classified, "stale-classify")
            (stale / "scope.md").write_text((stale / "scope.md").read_text() + "\nStale local edit.\n")
            resume = command("stale-check-resume", "check-resume", "--engagement", str(stale))
            success(resume, "stale-check-resume")  # The old attestation remains readable during a draft edit.
            rejected_create = create("stale-create", stale, stale_meta, stale_permit, GOOD_ONE)
            summary["cases"]["stale_scope"] = {"resume": "old attestation readable",
                                                 "create": denied(rejected_create, "stale-create", stale,
                                                                  stale / "evidence/stale.txt", 0)}

            repeated_scope = clone("same-hash-reattest")
            old_permit_meta = metadata(repeated_scope, "artifact-before-repeat", created=5)
            classified, old_permit = classify("before-repeat-classify", repeated_scope, old_permit_meta,
                                              GOOD_ONE, "evidence/before-repeat.txt", when=2.5)
            success(classified, "before-repeat-classify")
            scope_hash = reduce_engagement(repeated_scope)["scope_hash"]
            old_cleanup_closed_at = at(2.75)
            old_cleanup_closed = base_event(event_id="event-cleanup-closed-before-repeat",
                                            engagement_id=repeated_scope.name, recorded_at=old_cleanup_closed_at,
                                            actor_role="operator", actor_id=OPERATOR, event_type="cleanup.updated",
                                            rationale="Close unused prior obligation before a new preflight.",
                                            payload={"entity_id": CLEANUP_ID, "status": "completed",
                                                     "scope_hash": scope_hash, "operator_id": OPERATOR,
                                                     "updated_at": old_cleanup_closed_at,
                                                     "cleanup_obligations": [{"obligation_id": CLEANUP_ID,
                                                                              "kind": "local_fixture", "status": "completed",
                                                                              "artifact_refs": [], "rationale": "No artifact was created.",
                                                                              "closed_at": old_cleanup_closed_at}]},
                                            state_changes=[{"dimension": "cleanup", "entity_id": CLEANUP_ID,
                                                            "previous": "open", "current": "completed"}],
                                            session_id="session-operator-synthetic", operation_class="authority")
            _append_kernel_event(repeated_scope, old_cleanup_closed)
            repeated_event_id = "event-scope-same-hash-repeat"
            repeated_attestation = base_event(event_id=repeated_event_id, engagement_id=repeated_scope.name,
                                              recorded_at=at(3), actor_role="operator", actor_id=OPERATOR,
                                              event_type="scope.attested", rationale="Synthetic same-byte scope renewal.",
                                              payload={"scope_hash": scope_hash,
                                                       "scope_snapshot_path": f"scope-attestations/{scope_hash.removeprefix('sha256:')}.md",
                                                       "operator_id": OPERATOR, "signed_date": "2026-10-10",
                                                       "record_kernel": "decision-0006-v2",
                                                       "supersedes_scope_hash": scope_hash},
                                              entity_refs=[repeated_scope.name],
                                              session_id="session-operator-synthetic", operation_class="authority")
            # Fixture setup only: this private append does not test public re-attestation authority.
            _append_kernel_event(repeated_scope, repeated_attestation)
            ready_preflight = success(command("repeat-preflight", "preflight", "--engagement", str(repeated_scope),
                                              "--preflight-id", "env-after-repeat", "--mode", "local_runtime",
                                              "--target", str(source), "--expected-identity", sha256_file(source),
                                              "--runtime", SHELL,
                                              "--reproduction-argv", json.dumps([SHELL, "-c", "true"]),
                                              "--actor-role", "broker", "--actor-id", BROKER, "--session-id", SESSION,
                                              "--recorded-at", at(3.5)), "repeat-preflight")
            assert ready_preflight["status"] == "ready", ready_preflight
            later_cleanup_id = "cleanup-after-repeat"
            later_cleanup_ref = "event-cleanup-after-repeat"
            later_cleanup_at = at(3.75)
            later_cleanup = base_event(event_id=later_cleanup_ref, engagement_id=repeated_scope.name,
                                       recorded_at=later_cleanup_at, actor_role="operator", actor_id=OPERATOR,
                                       event_type="cleanup.updated", rationale="Open current synthetic artifact cleanup.",
                                       payload={"entity_id": later_cleanup_id, "status": "open", "scope_hash": scope_hash,
                                                "operator_id": OPERATOR, "updated_at": later_cleanup_at,
                                                "cleanup_obligations": [{"obligation_id": later_cleanup_id,
                                                                         "kind": "local_fixture", "status": "open",
                                                                         "artifact_refs": [], "rationale": "Remove the inert local artifact.",
                                                                         "closed_at": None}]},
                                       state_changes=[{"dimension": "cleanup", "entity_id": later_cleanup_id,
                                                       "previous": None, "current": "open"}],
                                       session_id="session-operator-synthetic", operation_class="authority")
            _append_kernel_event(repeated_scope, later_cleanup)
            old_permit_result = create("old-permit-after-repeat-create", repeated_scope,
                                       old_permit_meta, old_permit, GOOD_ONE)
            old_permit_error = denied(old_permit_result, "old-permit-after-repeat", repeated_scope,
                                      repeated_scope / "evidence/before-repeat.txt", 0)
            stale_ref_meta = metadata(repeated_scope, "artifact-after-repeat", created=6,
                                      confirmation_ref=scope_event, environment="env-after-repeat",
                                      cleanup_ref=later_cleanup_ref, cleanup_id=later_cleanup_id)
            stale_ref_classified, stale_ref_permit = classify("old-ref-after-repeat-classify", repeated_scope,
                                                              stale_ref_meta, GOOD_TWO,
                                                              "evidence/after-repeat.txt", when=4)
            stale_ref_created = (create("old-ref-after-repeat-create", repeated_scope,
                                        stale_ref_meta, stale_ref_permit, GOOD_TWO)
                                 if stale_ref_classified["returncode"] == 0 else None)
            repeated_destination = repeated_scope / "evidence/after-repeat.txt"
            summary["cases"]["same_hash_supersession"] = {
                "old_permit_create": old_permit_error,
                "old_attestation_ref_classify": ("allowed" if stale_ref_classified["returncode"] == 0
                                                else stale_ref_classified["error"]["code"]),
                "old_attestation_ref_create": (None if stale_ref_created is None else
                                               ("allowed" if stale_ref_created["returncode"] == 0
                                                else stale_ref_created["error"]["code"])),
                "destination_exists": repeated_destination.exists(),
                "artifact_count": len(read_ledger(repeated_scope, "artifact")),
            }
            assert stale_ref_classified["returncode"] != 0, summary["cases"]["same_hash_supersession"]
            assert stale_ref_created is None or stale_ref_created["returncode"] != 0, summary["cases"]["same_hash_supersession"]
            assert not repeated_destination.exists() and len(read_ledger(repeated_scope, "artifact")) == 0

            no_pending = clone("reattest-no-pending")
            no_pending_time = datetime.now(timezone.utc)
            draft, request_id, lane_id = approved_scope_reattestation("reattest-no-pending", no_pending,
                                                                      recorded=no_pending_time)
            reattested = success(reattest("reattest-no-pending-apply", no_pending, draft, request_id,
                                         lane_id, recorded=no_pending_time), "reattest-no-pending-apply")
            assert (no_pending / "scope.md").read_bytes() == draft.read_bytes()
            success(command("reattest-no-pending-check-resume", "check-resume", "--engagement", str(no_pending)),
                    "reattest-no-pending-check-resume")
            summary["cases"]["reattest_no_pending_control"] = {"scope_hash": reattested["scope_hash"],
                                                                   "scope_event_ref": reattested["event_id"]}

            for phase, written in (("before-write", False), ("after-write", True)):
                pending = clone(f"reattest-pending-{phase}")
                artifact_id = f"artifact-pending-{phase}"
                relative = f"evidence/{artifact_id}.txt"
                pending_meta = metadata(pending, artifact_id, created=10)
                classified, pending_permit = classify(f"reattest-pending-{phase}-classify", pending,
                                                       pending_meta, GOOD_ONE, relative, when=3)
                success(classified, f"reattest-pending-{phase}-classify")
                pending_time = datetime.now(timezone.utc)
                draft, request_id, lane_id = approved_scope_reattestation(
                    f"reattest-pending-{phase}", pending, recorded=pending_time)
                permit = json.loads(pending_permit.read_text(encoding="utf-8"))
                plan = {"artifact_id": artifact_id,
                        "metadata_digest": sha256_bytes(pending_meta.read_bytes()),
                        "planned_sha256": permit["source_digest"], "planned_size": permit["source_size"],
                        "relative_path": relative, "scope_hash": permit["scope_hash"],
                        "environment_ref": permit["environment_ref"],
                        "cleanup_obligation_ref": CLEANUP_EVENT, "cleanup_obligation_id": CLEANUP_ID}
                journal = {"schema_version": 1, "artifact_id": artifact_id,
                           "action_digest": sha256_bytes(canonical_json_bytes(plan)),
                           "classification_digest": sha256_bytes(canonical_json_bytes({
                               key: value for key, value in permit.items() if key != "classification_event_ref"})),
                           "relative_path": relative, "source_digest": permit["source_digest"],
                           "source_size": permit["source_size"], "confirmation_event_ref": scope_event}
                journal_path = pending / "legacy/zone2-pending" / f"{artifact_id}.json"
                journal_path.parent.mkdir(parents=True, exist_ok=True)
                journal_path.write_bytes(canonical_json_bytes(journal))
                destination = pending / relative
                if written:
                    destination.write_bytes(GOOD_ONE)
                before = {name: (pending / name).read_bytes() for name in
                          ("scope.md", "events.jsonl", "state.snapshot.json", "artifacts.jsonl")}
                attestation_snapshots = sorted(path.name for path in (pending / "scope-attestations").iterdir())
                attempted = reattest(f"reattest-pending-{phase}-apply", pending, draft,
                                     request_id, lane_id, recorded=pending_time)
                assert attempted["returncode"] != 0, (phase, attempted)
                assert attempted["error"]["code"] == "scope_reattestation_zone2_pending", (phase, attempted)
                assert all((pending / name).read_bytes() == value for name, value in before.items()), phase
                assert sorted(path.name for path in (pending / "scope-attestations").iterdir()) == attestation_snapshots
                assert journal_path.read_bytes() == canonical_json_bytes(journal)
                assert (destination.read_bytes() == GOOD_ONE) if written else not destination.exists()
                resumed = success(create(f"reattest-pending-{phase}-resume", pending,
                                         pending_meta, pending_permit, GOOD_ONE),
                                  f"reattest-pending-{phase}-resume")
                assert destination.read_bytes() == GOOD_ONE
                assert not journal_path.exists(), phase
                assert [item["artifact_id"] for item in read_ledger(pending, "artifact")] == [artifact_id]
                success(command(f"reattest-pending-{phase}-check-resume", "check-resume",
                                "--engagement", str(pending)), f"reattest-pending-{phase}-check-resume")
                summary["cases"][f"reattest_pending_{phase.replace('-', '_')}"] = {
                    "reattest_denial": attempted["error"]["code"], "artifact_id": artifact_id,
                    "artifact_record_hash": resumed["record_hash"], "journal_cleared": True,
                    "artifact_sha256": sha256_bytes(GOOD_ONE)}

            wrong_bytes = clone("wrong-bytes")
            wrong_meta = metadata(wrong_bytes, "artifact-wrong-bytes", created=4)
            classified, wrong_permit = classify("wrong-bytes-classify", wrong_bytes, wrong_meta, GOOD_ONE,
                                                "evidence/wrong-bytes.txt")
            success(classified, "wrong-bytes-classify")
            altered = b"X" + GOOD_ONE[1:]
            rejected = create("wrong-bytes-create", wrong_bytes, wrong_meta, wrong_permit, altered)
            summary["cases"]["wrong_bytes"] = denied(rejected, "wrong-bytes", wrong_bytes,
                                                        wrong_bytes / "evidence/wrong-bytes.txt", 0)

            missing_cleanup = clone("missing-cleanup")
            missing_meta = metadata(missing_cleanup, "artifact-missing-cleanup", created=4,
                                    cleanup_ref="event-does-not-exist")
            rejected, _ = classify("missing-cleanup-classify", missing_cleanup, missing_meta,
                                   GOOD_ONE, "evidence/missing-cleanup.txt")
            summary["cases"]["missing_cleanup"] = denied(rejected, "missing-cleanup", missing_cleanup,
                                                            missing_cleanup / "evidence/missing-cleanup.txt", 0)

            wrong_cleanup = clone("wrong-cleanup-id")
            wrong_cleanup_meta = metadata(wrong_cleanup, "artifact-wrong-cleanup-id", created=4,
                                          cleanup_id="cleanup-not-open")
            rejected, _ = classify("wrong-cleanup-id-classify", wrong_cleanup, wrong_cleanup_meta,
                                   GOOD_ONE, "evidence/wrong-cleanup-id.txt")
            summary["cases"]["wrong_cleanup_id"] = denied(rejected, "wrong-cleanup-id", wrong_cleanup,
                                                             wrong_cleanup / "evidence/wrong-cleanup-id.txt", 0)

            early_created = clone("created-before-cleanup")
            early_artifact_id = "artifact-created-before-cleanup"
            early_relative = "evidence/created-before-cleanup.txt"
            early_meta = metadata(early_created, early_artifact_id, created=1.75)
            classified, early_permit = classify("created-before-cleanup-classify", early_created,
                                                 early_meta, GOOD_ONE, early_relative, when=3)
            success(classified, "created-before-cleanup-classify")
            rejected = create("created-before-cleanup-create", early_created,
                              early_meta, early_permit, GOOD_ONE)
            error = denied(rejected, "created-before-cleanup", early_created,
                           early_created / early_relative, 0)
            assert not (early_created / "legacy/zone2-pending" / f"{early_artifact_id}.json").exists()
            summary["cases"]["created_before_cleanup"] = error

            before_environment = clone("created-before-environment")
            preflight_artifact_id = "artifact-created-before-environment"
            preflight_relative = "evidence/created-before-environment.txt"
            preflight_meta = metadata(before_environment, preflight_artifact_id, created=0.75)
            classified, preflight_permit = classify("created-before-environment-classify", before_environment,
                                                    preflight_meta, GOOD_ONE, preflight_relative, when=3)
            success(classified, "created-before-environment-classify")
            rejected = create("created-before-environment-create", before_environment,
                              preflight_meta, preflight_permit, GOOD_ONE)
            error = denied(rejected, "created-before-environment", before_environment,
                           before_environment / preflight_relative, 0)
            assert not (before_environment / "legacy/zone2-pending" / f"{preflight_artifact_id}.json").exists()
            summary["cases"]["created_before_environment"] = error

            closed = clone("closed-cleanup")
            closed_meta = metadata(closed, "artifact-closed-cleanup", created=4)
            classified, closed_permit = classify("closed-classify", closed, closed_meta, GOOD_ONE,
                                                 "evidence/closed-cleanup.txt")
            success(classified, "closed-classify")
            closed_at = at(3.5)
            closed_event = base_event(event_id="event-cleanup-closed", engagement_id=closed.name,
                                      recorded_at=closed_at, actor_role="operator", actor_id=OPERATOR,
                                      event_type="cleanup.updated", rationale="Close the synthetic obligation before creation.",
                                      payload={"entity_id": CLEANUP_ID, "status": "completed",
                                               "scope_hash": reduce_engagement(closed)["scope_hash"],
                                               "operator_id": OPERATOR, "updated_at": closed_at,
                                               "cleanup_obligations": [{"obligation_id": CLEANUP_ID,
                                                                        "kind": "local_fixture", "status": "completed",
                                                                        "artifact_refs": [], "rationale": "No artifact created.",
                                                                        "closed_at": closed_at}]},
                                      state_changes=[{"dimension": "cleanup", "entity_id": CLEANUP_ID,
                                                      "previous": "open", "current": "completed"}],
                                      session_id="session-operator-synthetic", operation_class="authority")
            _append_kernel_event(closed, closed_event)
            rejected = create("closed-create", closed, closed_meta, closed_permit, GOOD_ONE)
            summary["cases"]["closed_cleanup"] = denied(rejected, "closed-cleanup", closed,
                                                           closed / "evidence/closed-cleanup.txt", 0)

            wrong_environment = clone("wrong-environment")
            wrong_environment_meta = metadata(wrong_environment, "artifact-wrong-environment", created=4,
                                              environment="env-other")
            rejected, _ = classify("wrong-environment-classify", wrong_environment,
                                   wrong_environment_meta, GOOD_ONE, "evidence/wrong-environment.txt")
            summary["cases"]["wrong_environment"] = denied(rejected, "wrong-environment", wrong_environment,
                                                              wrong_environment / "evidence/wrong-environment.txt", 0)

            off_scope = clone("off-scope-path")
            off_scope_meta = metadata(off_scope, "artifact-off-scope", created=4)
            rejected, _ = classify("off-scope-classify", off_scope, off_scope_meta, GOOD_ONE, "../outside.txt")
            summary["cases"]["off_scope_path"] = denied(rejected, "off-scope", off_scope,
                                                          off_scope.parent / "outside.txt", 0)

            secret_metadata = clone("secret-metadata")
            secret_meta = metadata(secret_metadata, "artifact-secret-metadata", created=4)
            secret_value = json.loads(secret_meta.read_text())
            secret_value["synthetic_note"] = SECRET_SHAPE.decode().strip()
            secret_meta.write_bytes(canonical_json_bytes(secret_value))
            rejected, _ = classify("secret-metadata-classify", secret_metadata, secret_meta,
                                   GOOD_ONE, "evidence/secret-metadata.txt")
            summary["cases"]["secret_metadata"] = denied(rejected, "secret-metadata", secret_metadata,
                                                            secret_metadata / "evidence/secret-metadata.txt", 0)

            secret_content = clone("secret-content")
            secret_content_meta = metadata(secret_content, "artifact-secret-content", created=4)
            classified, secret_permit = classify("secret-content-classify", secret_content,
                                                 secret_content_meta, SECRET_SHAPE,
                                                 "evidence/secret-content.txt")
            success(classified, "secret-content-classify")
            rejected = create("secret-content-create", secret_content, secret_content_meta,
                              secret_permit, SECRET_SHAPE)
            summary["cases"]["secret_content"] = denied(rejected, "secret-content", secret_content,
                                                           secret_content / "evidence/secret-content.txt", 0)

            nonlocal_scope, nonlocal_event = setup("nonlocal-containment", containment="remote production network endpoint")
            nonlocal_meta = metadata(nonlocal_scope, "artifact-nonlocal-grant", created=4,
                                     confirmation_ref=nonlocal_event)
            rejected, _ = classify("nonlocal-classify", nonlocal_scope, nonlocal_meta,
                                   GOOD_ONE, "evidence/nonlocal.txt")
            summary["cases"]["nonlocal_containment"] = denied(rejected, "nonlocal-containment",
                                                                 nonlocal_scope, nonlocal_scope / "evidence/nonlocal.txt", 0)

            tmp_scope, tmp_event = setup("tmp-only-containment",
                                         containment="local /tmp/ synthetic-only material with a prior open cleanup obligation")
            tmp_meta = metadata(tmp_scope, "artifact-tmp-only", created=4, confirmation_ref=tmp_event)
            rejected, _ = classify("tmp-only-classify", tmp_scope, tmp_meta,
                                   GOOD_ONE, "evidence/tmp-only.txt")
            summary["cases"]["tmp_only_containment"] = denied(rejected, "tmp-only-containment",
                                                                   tmp_scope, tmp_scope / "evidence/tmp-only.txt", 0)

            # Fresh-confirmation control: only synthetic setup uses the private append path.
            fresh = no_grant
            fresh_state = reduce_engagement(fresh)
            fresh_meta = metadata(fresh, "artifact-fresh", created=5, confirmation_ref="event-fresh-confirm")
            fresh_plan = {"artifact_id": "artifact-fresh", "metadata_digest": sha256_bytes(fresh_meta.read_bytes()),
                          "planned_sha256": sha256_bytes(GOOD_TWO), "planned_size": len(GOOD_TWO),
                          "relative_path": "evidence/fresh.txt", "scope_hash": fresh_state["scope_hash"],
                          "environment_ref": "env-local", "cleanup_obligation_ref": CLEANUP_EVENT,
                          "cleanup_obligation_id": CLEANUP_ID}
            confirm_at, expires_at = at(3), at(600)
            confirmation = base_event(event_id="event-fresh-confirm", engagement_id=fresh.name,
                                      recorded_at=confirm_at, actor_role="operator", actor_id=OPERATOR,
                                      event_type="escalation.confirmed", rationale="Confirm one inert synthetic file.",
                                      payload={"entity_id": "artifact-fresh", "status": "confirmed",
                                               "confirmation_scope": "zone2_artifact_creation",
                                               "environment_ref": "env-local", "expires_at": expires_at,
                                               "cleanup_obligation_ref": CLEANUP_EVENT,
                                               "cleanup_obligation_id": CLEANUP_ID,
                                               "action_digest": sha256_bytes(canonical_json_bytes(fresh_plan)),
                                               "confirmation": {"category": "zone2_artifact_creation",
                                                                "bounded_action": "artifact-fresh",
                                                                "scope_hash": fresh_state["scope_hash"],
                                                                "operator_id": OPERATOR, "confirmed_at": confirm_at,
                                                                "expires_at": expires_at}},
                                      session_id="session-operator-synthetic", operation_class="real_world")
            _append_kernel_event(fresh, confirmation)
            classified, fresh_permit = classify("fresh-classify", fresh, fresh_meta, GOOD_TWO,
                                                "evidence/fresh.txt", when=4)
            success(classified, "fresh-classify")
            assert classified["decision"] == "allow_confirmed_creation", classified
            success(create("fresh-create", fresh, fresh_meta, fresh_permit, GOOD_TWO), "fresh-create")
            assert (fresh / "evidence/fresh.txt").read_bytes() == GOOD_TWO
            success(command("fresh-check-resume", "check-resume", "--engagement", str(fresh)), "fresh-check-resume")
            summary["cases"]["fresh_confirmation"] = {"artifact_id": "artifact-fresh",
                                                        "confirmation_event_ref": "event-fresh-confirm"}

            assert len(summary["cases"]) == 34, summary["cases"]
            summary["status"] = "passed"
    except Exception as exc:
        summary["status"] = "failed"
        summary["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (output / "results.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": summary["status"], "results": str(output / "results.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
