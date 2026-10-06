#!/usr/bin/env python3
"""Public-command, synthetic clean-start verification for issue 119."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from engagement_state import base_event, blocking_work_identities, project_current_terminal_work_state, read_ledger  # noqa: E402

TOOL = ROOT / "tools" / "run-engagement.py"
STAMP = "2026-10-06T12:00:00Z"
ENVIRONMENT_REF = "preflight-clean-start"


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    transcripts = output / "commands"
    transcripts.mkdir()
    proposals = output / "proposals"
    proposals.mkdir()
    workspace = output / "target"
    engagement = workspace / "engagements" / "clean-start"
    engagement.mkdir(parents=True)
    source = workspace / "inert-source.txt"
    source.write_text(
        "The legacy route accepts a caller-supplied owner id. The new route calls an owner guard before reading the record.\n",
        encoding="utf-8",
    )
    source_hash = digest(source.read_bytes())
    sequence = 0

    def run(name: str, argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
        nonlocal sequence
        sequence += 1
        result = subprocess.run(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        (transcripts / f"{sequence:02d}-{name}.json").write_bytes(encoded({
            "argv": argv, "exit_code": result.returncode,
            "stdout": result.stdout.decode("utf-8", "replace"),
            "stderr": result.stderr.decode("utf-8", "replace"),
        }))
        return result

    with tempfile.TemporaryDirectory(prefix="clean-start-key-") as key_dir:
        key_root = Path(key_dir)
        key = key_root / "operator"
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        pub = key.with_suffix(".pub").read_text().split()
        signers = key_root / "allowed-signers"
        signers.write_text(f"operator-clean-start {pub[0]} {pub[1]}\n")
        scope = engagement / "scope.md"
        scope.write_text(
            "# Synthetic signed scope\n\n"
            "## Engagement\n- id: clean-start\n- target: inert local source only\n- environment: local fixture\n\n"
            "## Surfaces in scope\n- One target-local inert text file. No target execution.\n\n"
            "## Benign safe-objective set\n- Identify a possible local guard difference for later testing.\n\n"
            "## Escalation ceiling\n- Local source inspection only.\n\n"
            "## Impact-demo authorization\n- impact_demo_authorized: `no`\n\n"
            "## Accounts / fixtures\n- None.\n\n"
            "## Source intake\n"
            "- Intake source path: `inert-source.txt`\n"
            f"- Intake source SHA256: `{source_hash}`\n"
            "- Intake allowed cards: `pattern.legacy-route-differential`\n\n"
            "## Authorization\n"
            f"- Operator allowed signers SHA256: {digest(signers.read_bytes())}\n"
            "- Operator: operator-clean-start\n"
            "- Date: 2026-10-06\n"
            "- Signed: [x]\n"
            "- Record kernel: `decision-0006-v1`\n",
            encoding="utf-8",
        )
        challenge = key_root / "init-challenge.json"
        challenge.write_bytes(encoded({
            "schema_version": 1, "namespace": "llm-redteam-harness-operator-v1",
            "engagement_id": engagement.name, "scope_hash": digest(scope.read_bytes()),
            "ledger_hash": None, "operation": f"initialize-engagement:{STAMP}",
            "operator_id": "operator-clean-start",
        }))
        subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n", "llm-redteam-harness-operator-v1", str(challenge)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        signed_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
        initialized = run("init", [sys.executable, str(TOOL), "init", "--engagement", str(engagement), "--recorded-at", STAMP], env=signed_env)

        negative_inits: list[dict[str, object]] = []
        original_scope = scope.read_text()
        source_data = source.read_bytes()
        variants = ("unsigned", "escape", "bad-hash", "missing-card", "symlink", "directory", "secret")
        for name in variants:
            variant_root = output / "negative-init" / name
            variant_engagement = variant_root / "target" / "engagements" / name
            variant_engagement.mkdir(parents=True)
            variant_source = variant_root / "target" / "inert-source.txt"
            variant_scope = original_scope.replace("- id: clean-start", f"- id: {name}")
            if name == "unsigned":
                variant_scope = variant_scope.replace("- Signed: [x]", "- Signed: [ ]")
            elif name == "escape":
                variant_scope = variant_scope.replace("`inert-source.txt`", "`../outside.txt`")
            elif name == "bad-hash":
                variant_scope = variant_scope.replace(source_hash, "sha256:" + "0" * 64)
            elif name == "missing-card":
                variant_scope = variant_scope.replace("pattern.legacy-route-differential", "pattern.nonexistent-fixture-card")
            elif name == "symlink":
                outside = variant_root / "inert-data.txt"
                outside.write_bytes(source_data)
                variant_source.symlink_to(outside)
            elif name == "directory":
                variant_source.mkdir()
            elif name == "secret":
                secret_shape = b"Authorization: " + b"Bearer " + b"syntheticlocaltoken12345\n"
                variant_scope = variant_scope.replace(source_hash, digest(secret_shape))
                variant_source.write_bytes(secret_shape)
            if name not in {"symlink", "directory", "secret"}:
                variant_source.write_bytes(source_data)
            (variant_engagement / "scope.md").write_text(variant_scope)
            variant_challenge = key_root / f"{name}-challenge.json"
            variant_challenge.write_bytes(encoded({"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1", "engagement_id": name, "scope_hash": digest(variant_scope.encode()), "ledger_hash": None, "operation": f"initialize-engagement:{STAMP}", "operator_id": "operator-clean-start"}))
            subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(key), "-n", "llm-redteam-harness-operator-v1", str(variant_challenge)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            variant_env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(variant_challenge) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(signers)}
            rejected = run(f"init-{name}", [sys.executable, str(TOOL), "init", "--engagement", str(variant_engagement), "--recorded-at", STAMP], env=variant_env)
            try:
                error_code = json.loads(rejected.stdout)["error"]["code"]
            except (KeyError, ValueError):
                error_code = None
            negative_inits.append({"case": name, "exit_code": rejected.returncode, "error_code": error_code, "event_count": len((variant_engagement / "events.jsonl").read_text().splitlines()) if (variant_engagement / "events.jsonl").exists() else 0})
            if name == "secret":
                variant_source.unlink()

    outcome: dict[str, object] = {"source_sha256": source_hash, "init_exit": initialized.returncode, "negative_inits": negative_inits, "queue_classes": [], "writes": []}
    if initialized.returncode != 0:
        (output / "result.json").write_bytes(encoded(outcome))
        return 1

    identity_result = run("identity", [sys.executable, str(TOOL), "runtime-identity", "--role", "broker"])
    if identity_result.returncode != 0:
        (output / "result.json").write_bytes(encoded(outcome))
        return 1
    identity = json.loads(identity_result.stdout)
    scope_hash = digest(scope.read_bytes())
    no_preflight_workspace = output / "negative-no-preflight" / "target"
    shutil.copytree(workspace, no_preflight_workspace)
    no_preflight_engagement = no_preflight_workspace / "engagements" / engagement.name
    no_preflight_event = base_event(
        event_id="event-observation-without-preflight", engagement_id=engagement.name,
        recorded_at="2026-10-06T12:00:01Z", actor_role="broker",
        actor_id=identity["actor_id"], event_type="observation.recorded",
        rationale="This source observation must be refused before a ready preflight.",
        payload={"entity_id": "source-observation-without-preflight", "entity_type": "source_intake", "status": "recorded", "source_path": "inert-source.txt", "source_hash": source_hash, "source_size": source.stat().st_size, "scope_hash": scope_hash, "environment_ref": None},
        session_id=identity["session_id"], operation_class="notebook",
    )
    no_preflight_proposal = proposals / "observation-without-preflight.json"
    no_preflight_proposal.write_bytes(encoded(no_preflight_event))
    no_preflight_write = run("observation-without-preflight", [sys.executable, str(TOOL), "append-event", "--engagement", str(no_preflight_engagement), "--file", str(no_preflight_proposal)])
    try:
        no_preflight_code = json.loads(no_preflight_write.stdout)["error"]["code"]
    except (KeyError, ValueError):
        no_preflight_code = None
    outcome["no_preflight"] = {"exit_code": no_preflight_write.returncode, "error_code": no_preflight_code, "event_count": len((no_preflight_engagement / "events.jsonl").read_text().splitlines())}
    no_preflight_driver = run("driver-without-preflight", [sys.executable, str(Path(__file__).with_name("host_replay.py")), "--workspace", str(no_preflight_workspace), "--output", str(output / "negative-no-preflight" / "run")])
    no_preflight_driver_summary = json.loads((output / "negative-no-preflight" / "run" / "result.json").read_text())
    outcome["no_preflight_driver"] = {"exit_code": no_preflight_driver.returncode, "error": no_preflight_driver_summary.get("error"), "event_count": len((no_preflight_engagement / "events.jsonl").read_text().splitlines()), "session_transcripts": len(list((output / "negative-no-preflight" / "run").glob("fake-session-*.json")))}
    preflight = run("preflight", [
        sys.executable, str(TOOL), "preflight", "--engagement", str(engagement),
        "--preflight-id", ENVIRONMENT_REF, "--mode", "local_runtime",
        "--target", str(source), "--expected-identity", source_hash,
        "--runtime", "/usr/bin/true", "--reproduction-argv", '["/usr/bin/true"]',
        "--actor-role", "broker", "--actor-id", identity["actor_id"],
        "--session-id", identity["session_id"], "--recorded-at", "2026-10-06T12:00:00.500Z",
    ])
    preflight_summary = json.loads(preflight.stdout) if preflight.returncode == 0 else {}
    outcome["preflight"] = {"exit_code": preflight.returncode, "status": preflight_summary.get("status"), "environment_ref": json.loads((engagement / "state.snapshot.json").read_text()).get("active_environment_ref")}
    if preflight.returncode != 0 or preflight_summary.get("status") != "ready":
        (output / "result.json").write_bytes(encoded(outcome))
        return 1

    def terminal_source_projection(target: Path, source_class: str) -> dict[str, object]:
        state = json.loads((target / "state.snapshot.json").read_text())
        attempts = read_ledger(target, "attempt")
        result: dict[str, object] = {}
        for coverage in ("coverage_dry", "budget_bounded"):
            projected = project_current_terminal_work_state(state, attempts, coverage=coverage)
            source_rows = [item for item in projected["work_queue"] if item["class"] == source_class and item["entity"]["id"] == engagement.name]
            blockers = blocking_work_identities(projected)
            result[coverage] = {"source_rows": len(source_rows), "blocking": len(source_rows) == 1 and source_rows[0]["blocking"] is True, "in_blockers": {"class": source_class, "entity": {"type": "engagement", "id": engagement.name, "detail": None}} in blockers}
        return result

    outcome["terminal_projection_initial"] = terminal_source_projection(engagement, "source_unobserved")

    host_workspace = output / "host-replay" / "target"
    shutil.copytree(workspace, host_workspace)
    host_result = run("host-replay", [sys.executable, str(Path(__file__).with_name("host_replay.py")), "--workspace", str(host_workspace), "--output", str(output / "host-replay" / "run")])
    host_summary = json.loads((output / "host-replay" / "run" / "result.json").read_text()) if host_result.returncode == 0 else {}
    outcome["host_replay"] = {"exit_code": host_result.returncode, "passed": host_summary.get("passed"), "sessions_started": host_summary.get("sessions_started"), "source_read_visible_in_observation": host_summary.get("source_read_visible_in_observation"), "status": host_summary.get("status")}
    drift_workspace = output / "host-drift" / "target"
    shutil.copytree(workspace, drift_workspace)
    (drift_workspace / "inert-source.txt").write_text("Changed after the signed source pin.\n")
    drift_result = run("host-drift", [sys.executable, str(Path(__file__).with_name("host_replay.py")), "--workspace", str(drift_workspace), "--output", str(output / "host-drift" / "run")])
    drift_summary = json.loads((output / "host-drift" / "run" / "result.json").read_text())
    drift_events = (drift_workspace / "engagements" / engagement.name / "events.jsonl").read_text().splitlines()
    outcome["host_drift"] = {"exit_code": drift_result.returncode, "error": drift_summary.get("error"), "event_count": len(drift_events)}

    def next_item(expected: str) -> dict[str, object]:
        result = run("next", [sys.executable, str(TOOL), "next", "--engagement", str(engagement)])
        if result.returncode != 0:
            raise RuntimeError(f"next failed before {expected}")
        item = json.loads(result.stdout)["item"]
        outcome["queue_classes"].append(item["class"])
        if item["class"] != expected or item["next_action"]["launchable"] is not True:
            raise RuntimeError(f"expected {expected}, got {item['class']}")
        return item

    def append(name: str, event: dict[str, object], target: Path = engagement) -> subprocess.CompletedProcess[bytes]:
        path = proposals / f"{name}.json"
        path.write_bytes(encoded(event))
        result = run(name, [sys.executable, str(TOOL), "append-event", "--engagement", str(target), "--file", str(path)])
        outcome["writes"].append({"name": name, "exit_code": result.returncode})
        return result

    def event(name: str, timestamp: str, kind: str, rationale: str, payload: dict[str, object], *, refs: list[str] | None = None, changes: list[dict[str, object]] | None = None) -> dict[str, object]:
        return base_event(event_id=name, engagement_id=engagement.name, recorded_at=timestamp, actor_role="broker", actor_id=identity["actor_id"], event_type=kind, rationale=rationale, payload=payload, entity_refs=refs or [], state_changes=changes or [], session_id=identity["session_id"], operation_class="notebook", model="deterministic-fixture", provider="local", tool_versions=["clean-start-119"])

    try:
        next_item("source_unobserved")
        initial_intake = json.loads((engagement / "state.snapshot.json").read_text())["intake"]
        outcome["initial_intake"] = {"denominator": initial_intake["denominator"], "status": initial_intake["status"], "observation_ref": initial_intake["observation_ref"]}
        observation_id = "event-intake-observation"
        observation = event(observation_id, "2026-10-06T12:00:01Z", "observation.recorded", "The inert source names two route variants and a guard difference; reachability is untested.", {"entity_id": "source-observation", "entity_type": "source_intake", "status": "recorded", "source_path": "inert-source.txt", "source_hash": source_hash, "source_size": source.stat().st_size, "scope_hash": scope_hash, "environment_ref": ENVIRONMENT_REF})
        if append("observation", observation).returncode != 0:
            raise RuntimeError("observation append failed")

        refresh_root = output / "preflight-refresh" / "target"
        shutil.copytree(workspace, refresh_root)
        refresh_engagement = refresh_root / "engagements" / engagement.name
        refresh_ref = "preflight-clean-start-refreshed"
        refresh_preflight = run("preflight-refresh", [
            sys.executable, str(TOOL), "preflight", "--engagement", str(refresh_engagement),
            "--preflight-id", refresh_ref, "--mode", "local_runtime",
            "--target", str(refresh_root / "inert-source.txt"), "--expected-identity", source_hash,
            "--runtime", "/usr/bin/true", "--reproduction-argv", '["/usr/bin/true"]',
            "--actor-role", "broker", "--actor-id", identity["actor_id"],
            "--session-id", identity["session_id"], "--recorded-at", "2026-10-06T12:00:01.500Z",
        ])
        refresh_state = json.loads((refresh_engagement / "state.snapshot.json").read_text())
        refresh_next = run("next-after-preflight-refresh", [sys.executable, str(TOOL), "next", "--engagement", str(refresh_engagement)])
        refreshed_observation = copy.deepcopy(observation)
        refreshed_observation["event_id"] = "event-intake-observation-refreshed"
        refreshed_observation["recorded_at"] = "2026-10-06T12:00:01.600Z"
        refreshed_observation["payload"]["entity_id"] = "source-observation-refreshed"
        refreshed_observation["payload"]["environment_ref"] = refresh_ref
        refresh_write = append("observation-after-preflight-refresh", refreshed_observation, refresh_engagement)
        refresh_after = json.loads((refresh_engagement / "state.snapshot.json").read_text())
        outcome["preflight_refresh"] = {
            "preflight_exit": refresh_preflight.returncode,
            "preflight_status": json.loads(refresh_preflight.stdout).get("status") if refresh_preflight.returncode == 0 else None,
            "active_environment_ref": refresh_state["active_environment_ref"],
            "intake_after_preflight": refresh_state["intake"],
            "next_class": json.loads(refresh_next.stdout)["item"]["class"] if refresh_next.returncode == 0 else None,
            "reobservation_exit": refresh_write.returncode,
            "intake_after_reobservation": refresh_after["intake"],
        }

        next_item("source_unrouted")
        negative_route_root = output / "negative-events" / "routing" / "target"
        shutil.copytree(workspace, negative_route_root)
        negative_route_engagement = negative_route_root / "engagements" / engagement.name
        deferred_root = output / "negative-events" / "deferred" / "target"
        shutil.copytree(workspace, deferred_root)
        deferred_engagement = deferred_root / "engagements" / engagement.name
        routing_id = "event-intake-routing"
        routing = event(routing_id, "2026-10-06T12:00:02Z", "routing.assessed", "The text weakly activates a legacy-route differential; execution and access control are unproven.", {"entity_id": "source-routing", "source_observation_ref": observation_id, "activation_strength": "weak", "card_ids": ["pattern.legacy-route-differential"], "status": "assessed", "source_path": "inert-source.txt", "source_hash": source_hash, "source_size": source.stat().st_size, "scope_hash": scope_hash, "environment_ref": ENVIRONMENT_REF}, refs=[observation_id])
        deferred = copy.deepcopy(routing)
        deferred["event_id"] = "event-intake-deferred"
        deferred["payload"]["activation_strength"] = "none"
        deferred["payload"]["card_ids"] = []
        deferred["payload"]["status"] = "deferred"
        deferred["rationale"] = "No card is justified by this synthetic source assessment; keep the source unresolved."
        deferred_write = append("deferred-no-route", deferred, deferred_engagement)
        deferred_next = run("deferred-next", [sys.executable, str(TOOL), "next", "--engagement", str(deferred_engagement)])
        deferred_state = json.loads((deferred_engagement / "state.snapshot.json").read_text()) if deferred_write.returncode == 0 else {}
        deferred_queue = json.loads(deferred_next.stdout) if deferred_next.returncode == 0 else {}
        outcome["deferred_no_route"] = {"append_exit": deferred_write.returncode, "next_exit": deferred_next.returncode, "denominator": deferred_state.get("intake", {}).get("denominator"), "status": deferred_state.get("intake", {}).get("status"), "hypothesis_ref": deferred_state.get("intake", {}).get("hypothesis_ref"), "next_class": deferred_queue.get("item", {}).get("class"), "should_block": deferred_queue.get("queue", {}).get("should_block")}
        outcome["terminal_projection_deferred"] = terminal_source_projection(deferred_engagement, "source_unrouted") if deferred_write.returncode == 0 else {}
        negative_routes: list[dict[str, object]] = []
        for name, payload_key, value in (
            ("offscope-card", "card_ids", ["pattern.ui-only-policy-enforcement"]),
            ("wrong-source", "source_hash", "sha256:" + "0" * 64),
            ("wrong-scope", "scope_hash", "sha256:" + "0" * 64),
            ("wrong-environment", "environment_ref", "environment-fake"),
            ("wrong-observation", "source_observation_ref", "event-nonexistent"),
        ):
            bad = copy.deepcopy(routing)
            bad["event_id"] = f"event-intake-{name}"
            bad["payload"][payload_key] = value
            rejected = append(name, bad, negative_route_engagement)
            try:
                error_code = json.loads(rejected.stdout)["error"]["code"]
            except (KeyError, ValueError):
                error_code = None
            negative_routes.append({"case": name, "exit_code": rejected.returncode, "error_code": error_code, "event_count": len((negative_route_engagement / "events.jsonl").read_text().splitlines())})
        outcome["negative_routes"] = negative_routes
        if append("routing", routing).returncode != 0:
            raise RuntimeError("routing append failed")

        next_item("source_unhypothesized")
        negative_hypothesis_root = output / "negative-events" / "hypothesis" / "target"
        shutil.copytree(workspace, negative_hypothesis_root)
        negative_hypothesis_engagement = negative_hypothesis_root / "engagements" / engagement.name
        hypothesis_id = "hypothesis-intake-route"
        cost = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "human_review_seconds": 0}
        hypothesis = event("event-intake-hypothesis", "2026-10-06T12:00:03Z", "hypothesis.created", "The source difference warrants one bounded local experiment, not a finding.", {"hypothesis_id": hypothesis_id, "origin_type": "target_model", "origin_ref": observation_id, "routing_review_ref": routing_id, "source_hash": source_hash, "scope_hash": scope_hash, "environment_ref": ENVIRONMENT_REF, "hypothesis_statement": "A local fixture may show the legacy route omits the owner guard used by the new route.", "suspected_invariant": "Both route variants must apply the same owner guard.", "trust_boundary": "caller owner id to route authorization guard", "attacker_path": ["inert fixture request", "legacy route", "owner guard"], "impact_ceiling": "local inert fixture only", "bounded_space": "Compare exactly two route variants using one benign owner id.", "lens_ids": ["authorization"], "card_ids": ["pattern.legacy-route-differential"], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "local traces show different guard decisions for the same benign request", "required": True}], "decisive_falsifiers": ["both variants call the same guard before reading"], "cost_estimate": cost, "constraints": ["no live target", "no impact demonstration"], "next_experiment": "Run one inert, same-actor route comparison in a contained local fixture and capture guard traces.", "completion_criteria": ["both route decisions and the guard trace are recorded"], "status": "queued"}, refs=[observation_id, routing_id], changes=[{"dimension": "search", "entity_id": hypothesis_id, "previous": None, "current": "queued"}])
        negative_hypotheses: list[dict[str, object]] = []
        for name, payload_key, value in (
            ("wrong-routing", "routing_review_ref", "event-nonexistent"),
            ("wrong-origin", "origin_ref", "event-nonexistent"),
            ("offscope-hypothesis-card", "card_ids", ["pattern.ui-only-policy-enforcement"]),
        ):
            bad = copy.deepcopy(hypothesis)
            bad["event_id"] = f"event-intake-{name}"
            bad["payload"][payload_key] = value
            rejected = append(name, bad, negative_hypothesis_engagement)
            try:
                error_code = json.loads(rejected.stdout)["error"]["code"]
            except (KeyError, ValueError):
                error_code = None
            negative_hypotheses.append({"case": name, "exit_code": rejected.returncode, "error_code": error_code, "event_count": len((negative_hypothesis_engagement / "events.jsonl").read_text().splitlines())})
        outcome["negative_hypotheses"] = negative_hypotheses
        if append("hypothesis", hypothesis).returncode != 0:
            raise RuntimeError("hypothesis append failed")

        next_item("hypothesis_unrouted")
        snapshot = json.loads((engagement / "state.snapshot.json").read_text())
        outcome["hypothesis_ref"] = hypothesis_id
        outcome["ledger_events"] = [json.loads(line)["event_type"] for line in (engagement / "events.jsonl").read_text().splitlines()]
        outcome["snapshot_intake"] = snapshot.get("intake") if isinstance(snapshot, dict) else None
        source.write_text("The source changed after the signed pin.\n")
        drift_next = run("drift-next", [sys.executable, str(TOOL), "next", "--engagement", str(engagement)])
        drift_probe = event("event-drift-observation", "2026-10-06T12:00:04Z", "observation.recorded", "This append must fail before touching research history.", {"entity_id": "drift-observation", "entity_type": "observation", "status": "recorded"})
        drift_append = append("drift-append", drift_probe)
        try:
            drift_code = json.loads(drift_append.stdout)["error"]["code"]
        except (KeyError, ValueError):
            drift_code = None
        outcome["source_drift"] = {"next_exit": drift_next.returncode, "append_exit": drift_append.returncode, "append_error": drift_code, "event_count": len((engagement / "events.jsonl").read_text().splitlines())}
        source.write_bytes(source_data)
        outcome["passed"] = (
            outcome["queue_classes"] == ["source_unobserved", "source_unrouted", "source_unhypothesized", "hypothesis_unrouted"]
            and outcome["initial_intake"] == {"denominator": 1, "status": "unread", "observation_ref": None}
            and outcome["deferred_no_route"] == {"append_exit": 0, "next_exit": 0, "denominator": 1, "status": "deferred", "hypothesis_ref": None, "next_class": "source_unrouted", "should_block": True}
            and all(case == {"source_rows": 1, "blocking": True, "in_blockers": True} for case in outcome["terminal_projection_initial"].values())
            and all(case == {"source_rows": 1, "blocking": True, "in_blockers": True} for case in outcome["terminal_projection_deferred"].values())
            and outcome["preflight_refresh"]["preflight_exit"] == 0
            and outcome["preflight_refresh"]["preflight_status"] == "ready"
            and outcome["preflight_refresh"]["active_environment_ref"] == "preflight-clean-start-refreshed"
            and outcome["preflight_refresh"]["intake_after_preflight"]["source_hash"] == source_hash
            and outcome["preflight_refresh"]["intake_after_preflight"]["denominator"] == 1
            and outcome["preflight_refresh"]["intake_after_preflight"]["status"] == "unread"
            and outcome["preflight_refresh"]["intake_after_preflight"]["observation_ref"] is None
            and outcome["preflight_refresh"]["next_class"] == "source_unobserved"
            and outcome["preflight_refresh"]["reobservation_exit"] == 0
            and outcome["preflight_refresh"]["intake_after_reobservation"]["environment_ref"] == "preflight-clean-start-refreshed"
            and outcome["preflight_refresh"]["intake_after_reobservation"]["status"] == "observed"
            and snapshot["intake"]["hypothesis_ref"] == hypothesis_id
            and snapshot["intake"]["denominator"] == 1
            and snapshot["intake"]["status"] == "hypothesized"
            and all(row["exit_code"] != 0 and row["event_count"] == 0 for row in negative_inits)
            and outcome["preflight"] == {"exit_code": 0, "status": "ready", "environment_ref": ENVIRONMENT_REF}
            and outcome["no_preflight"] == {"exit_code": 1, "error_code": "intake_environment_not_ready", "event_count": 1}
            and outcome["no_preflight_driver"] == {"exit_code": 1, "error": "driver_intake_environment_not_ready", "event_count": 1, "session_transcripts": 0}
            and snapshot["intake"]["environment_ref"] == ENVIRONMENT_REF
            and host_summary.get("intake", {}).get("environment_ref") == ENVIRONMENT_REF
            and all(row["exit_code"] != 0 and row["event_count"] == 4 for row in negative_routes)
            and all(row["exit_code"] != 0 and row["event_count"] == 5 for row in negative_hypotheses)
            and drift_next.returncode == 0 and drift_append.returncode != 0 and outcome["source_drift"]["event_count"] == 6
            and host_result.returncode == 0 and host_summary.get("passed") is True
            and drift_result.returncode != 0 and drift_summary.get("error") == "driver_intake_source_digest_mismatch" and len(drift_events) == 3
        )
    except (RuntimeError, KeyError, ValueError) as exc:
        outcome["error"] = str(exc)
        outcome["passed"] = False
    (output / "result.json").write_bytes(encoded(outcome))
    return 0 if outcome["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
