#!/usr/bin/env python3
"""Public-command synthetic E2E for issue #123; see fixtures/reasoned-escalation/README.md."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from engagement_records import build_reference_index, canonical_json_bytes, sha256_bytes, sha256_file
from engagement_state import base_event, compute_review_input_hash, reduce_engagement, utc_now


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "tools/run-engagement.py"
BROKER = f"local-uid-{os.getuid()}:broker"
SESSION = f"session-posix-{os.getuid()}-{os.getsid(0)}"
ZERO_COST = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}
CARD_ID = "bola.broken-object-level-authz"
CARD = ROOT / "skills/vulns/broken-object-level-authz/SKILL.md"


def command(output: Path, name: str, *argv: str, env: dict[str, str] | None = None, ok: bool = True, error: str | None = None) -> dict:
    result = subprocess.run(argv, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    row = {"name": name, "argv": list(argv), "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    with (output / "commands.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    if ok != (result.returncode == 0) or (error and error not in result.stdout + result.stderr):
        raise AssertionError(f"{name}: unexpected command result {row}")
    return json.loads(result.stdout) if result.stdout.strip().startswith("{") else row


def key(private_dir: Path, output: Path, identity: str) -> tuple[Path, Path]:
    private = private_dir / identity
    subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)], check=True, stdout=subprocess.DEVNULL)
    signers = output / f"{identity}.signers"
    signers.write_text(f"{identity} {private.with_suffix('.pub').read_text().strip()}\n", encoding="utf-8")
    return private, signers


def event(engagement: Path, event_id: str, event_type: str, payload: dict, *, origin: str, changes: list[dict] | None = None, reviews: list[str] | None = None) -> dict:
    value = base_event(
        event_id=event_id, engagement_id=engagement.name, recorded_at=utc_now(),
        actor_role="broker", actor_id=BROKER, event_type=event_type,
        rationale=f"Synthetic {event_type} for reasoned escalation acceptance.", payload=payload,
        entity_refs=[origin] if origin else [], review_refs=reviews or [],
        state_changes=changes or [], session_id=SESSION, operation_class="notebook",
        model="proposer-model-e2e", provider="synthetic",
    )
    value["provenance"]["runtime_session_ref"] = "proposer-session-e2e"
    return value


def append(output: Path, engagement: Path, value: dict, *, ok: bool = True, error: str | None = None) -> None:
    path = output / f"{value['event_id']}.json"
    path.write_bytes(canonical_json_bytes(value))
    command(output, value["event_id"], sys.executable, str(RUN), "append-event", "--engagement", str(engagement), "--file", str(path), ok=ok, error=error)


def scope_text(operator_signers: Path, reviewer_signers: Path, *, ceiling: str = "cross-user") -> str:
    return f"""# Signed synthetic scope
## Surfaces in scope
- [x] local owned canary fixture
## Benign safe-objective set
- [x] owned canary read
## Escalation ceiling
- self → stored/persistent → cross-user: ceiling = `{ceiling}`
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `none`
## Accounts / fixtures
- owned synthetic principals only
## Independent reviewer identity
- Reviewer allowed signers SHA256: {sha256_file(reviewer_signers)}
## Authorization
- Frozen corpus enumeration SHA256: `none`
- Operator allowed signers SHA256: {sha256_file(operator_signers)}
- Operator: operator-e2e
- Date: 2026-10-06
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


def setup(output: Path, operator_key: Path, operator_signers: Path, reviewer_signers: Path, *, ceiling: str = "cross-user") -> Path:
    engagement = output / "target/engagements/synthetic"
    engagement.mkdir(parents=True)
    scope = engagement / "scope.md"
    scope.write_text(scope_text(operator_signers, reviewer_signers, ceiling=ceiling), encoding="utf-8")
    now = utc_now()
    challenge = {"schema_version": 1, "namespace": "llm-redteam-harness-operator-v1", "engagement_id": engagement.name, "scope_hash": sha256_file(scope), "ledger_hash": None, "operation": f"initialize-engagement:{now}", "operator_id": "operator-e2e"}
    challenge_file = output / "init-challenge.json"
    challenge_file.write_bytes(canonical_json_bytes(challenge))
    subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(operator_key), "-n", "llm-redteam-harness-operator-v1", str(challenge_file)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = {**os.environ, "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_file) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(operator_signers)}
    command(output, "signed-init", sys.executable, str(RUN), "init", "--engagement", str(engagement), "--recorded-at", now, env=env)
    source = output / "owned-canary-source.txt"
    source.write_text("synthetic owned canary source only\n", encoding="utf-8")
    command(output, "preflight", sys.executable, str(RUN), "preflight", "--engagement", str(engagement), "--preflight-id", "env-owned", "--mode", "local_runtime", "--target", str(source), "--expected-identity", sha256_file(source), "--runtime", "/bin/sh", "--reproduction-argv", json.dumps(["/bin/sh", "-c", "true"]), "--actor-role", "broker", "--actor-id", BROKER, "--session-id", SESSION, "--recorded-at", utc_now())
    append(output, engagement, event(engagement, "event-observed", "observation.recorded", {"entity_id": "owned-canary", "entity_type": "target_model", "status": "observed", "environment_ref": "env-owned"}, origin=""))
    return engagement


def route(engagement: Path, *, effect: str = "cross-user", signal: bool = True, control: bool = True, test: bool = True, evidence: list[str] | None = None, surface: str = "local owned canary fixture") -> dict:
    state = reduce_engagement(engagement)
    return {
        "scope_hash": state["scope_hash"], "environment_ref": state["active_environment_ref"],
        "evidence_refs": evidence if evidence is not None else ["event-observed"],
        "surface": surface, "effect_rung": effect,
        "source_output": "The owned first principal can supply the object selector.",
        "target_precondition": "The second owned principal's canary object is addressable by that selector.",
        "discriminating_test": "Compare second-principal canary output with a same-principal control." if test else "",
        "control_plan": "A missing or same-principal selector must not return the second canary." if control else "",
        "safe_signal_card_id": CARD_ID if signal else "",
        "safe_signal_card_digest": sha256_file(CARD) if signal else "",
        "safe_signal_card_snapshot": CARD.read_text(encoding="utf-8") if signal else "",
        "safe_signal_objective": "owned canary read" if signal else "",
        "proposed_impact": "A planted canary crosses between two controlled principals only.",
    }


def propose(output: Path, engagement: Path, *, route_value: dict | None, hypothesis_id: str = "hyp-route", select: bool = True) -> None:
    payload = {"hypothesis_id": hypothesis_id, "origin_type": "target_model", "origin_ref": "event-observed", "hypothesis_statement": "A direct canary route may cross the owned-principal boundary.", "suspected_invariant": "An owner guard must bind the object selector.", "trust_boundary": "owned principal A to owned principal B", "attacker_path": ["owned selector", "canary read"], "impact_ceiling": "owned fixture only", "bounded_space": "One canary and matched control.", "lens_ids": ["authorization"], "card_ids": [CARD_ID], "expected_confirming_evidence": [{"evidence_type": "trace", "description": "canary output", "required": True}], "decisive_falsifiers": ["owner guard blocks selector"], "cost_estimate": ZERO_COST, "constraints": ["local synthetic only"], "next_experiment": "compare owned canary and control", "completion_criteria": ["canary and control recorded"], "status": "queued"}
    if route_value:
        payload["higher_impact_route"] = route_value
    append(output, engagement, event(engagement, f"event-{hypothesis_id}-created", "hypothesis.created", payload, origin="event-observed", changes=[{"dimension": "search", "entity_id": hypothesis_id, "previous": None, "current": "queued"}]))
    if select:
        append(output, engagement, event(engagement, f"event-{hypothesis_id}-selected", "hypothesis.status_changed", {"hypothesis_id": hypothesis_id, "status": "selected", "reason": "select bounded direct route", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Selected direct owned-canary test.", "unresolved_questions": [], "next_route": None}, origin=hypothesis_id, changes=[{"dimension": "search", "entity_id": hypothesis_id, "previous": "queued", "current": "selected"}]))


def next_action(output: Path, engagement: Path) -> dict:
    return command(output, "next", sys.executable, str(RUN), "next", "--engagement", str(engagement))["item"]["next_action"]


def review(output: Path, engagement: Path, reviewer_key: Path, reviewer_signers: Path, *, verdict: str, edge: bool = True, bounded: bool = True, reason: str | None = None, same_model: bool = False, ok: bool = True, error: str | None = None) -> str:
    state = reduce_engagement(engagement)
    route_value = state["hypotheses"]["hyp-route"]["higher_impact_route"]
    review_id = f"review-route-{verdict}-{int(edge)}-{int(bounded)}"
    row = {"schema_version": 1, "review_id": review_id, "engagement_id": engagement.name, "review_type": "higher_impact_route", "proposed_finding_id": None, "recorded_at": utc_now(), "entity_ref": "hyp-route", "finding_revision": None, "input_refs": ["event-hyp-route-created", *route_value["evidence_refs"]], "input_hash": "sha256:" + "0" * 64, "evidence_refs": [], "rationale": "Independently challenge the observed output-to-precondition edge and the bounded canary test.", "conflicting_evidence": [], "verdict": verdict, "corrections": [], "required_next_actions": [], "route_digest": sha256_bytes(canonical_json_bytes(route_value)), "causal_edge_valid": edge, "test_discriminates": True, "controls_present": True, "severity_bounded": bounded, "blocked_reason": reason, "independence": {"reviewer_id": "reviewer-e2e", "reviewer_run_id": f"run-{review_id}", "reviewer_session_id": f"session-{review_id}", "reviewer_signer_fingerprint": None, "reviewer_model": "reviewer-model-e2e", "fresh_context": True, "prior_verdict_visible": False, "disconfirming_objective": "Find a broken causal edge or overclaim before the direct test.", "originating_run_id": "event-hyp-route-created"}}
    row["independence"].pop("reviewer_signer_fingerprint")
    if same_model:
        row["independence"]["reviewer_model"] = "proposer-model-e2e"
    row["input_hash"] = compute_review_input_hash(engagement, row, build_reference_index(engagement))
    review_file = output / f"{review_id}.json"
    review_file.write_bytes(canonical_json_bytes(row))
    subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(reviewer_key), "-n", "llm-redteam-harness-review-v1", str(review_file)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    completed = event(engagement, f"event-{review_id}", "review.higher_impact_route_completed", {"review_type": "higher_impact_route", "hypothesis_id": "hyp-route", "review_ref": review_id, "reviewer_id": "reviewer-e2e", "verdict": verdict, "route_digest": row["route_digest"]}, origin="hyp-route", reviews=[review_id])
    completed_file = output / f"event-{review_id}.json"
    completed_file.write_bytes(canonical_json_bytes(completed))
    command(output, "record-route-review", sys.executable, str(RUN), "record-review", "--engagement", str(engagement), "--file", str(review_file), "--event", str(completed_file), "--actor-id", BROKER, "--session-id", SESSION, "--signature", str(review_file) + ".sig", "--allowed-signers", str(reviewer_signers), ok=ok, error=error)
    return review_id


def run_event(engagement: Path, review_id: str | None = None, *, event_id: str = "event-hyp-route-running") -> dict:
    state = reduce_engagement(engagement)
    route_value = state["hypotheses"]["hyp-route"]["higher_impact_route"]
    payload = {"hypothesis_id": "hyp-route", "status": "running", "reason": "run reviewed direct route", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Reviewed test route entered running state, not confirmed impact.", "unresolved_questions": [], "next_route": None, "route_digest": sha256_bytes(canonical_json_bytes(route_value))}
    if review_id:
        payload["route_review_ref"] = review_id
    return event(engagement, event_id, "hypothesis.status_changed", payload, origin="hyp-route", reviews=[review_id] if review_id else [], changes=[{"dimension": "search", "entity_id": "hyp-route", "previous": "selected", "current": "running"}])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    private_dir = Path(tempfile.mkdtemp(prefix="issue123-e2e-keys-"))
    atexit.register(shutil.rmtree, private_dir, ignore_errors=True)
    operator_key, operator_signers = key(private_dir, output, "operator-e2e")
    reviewer_key, reviewer_signers = key(private_dir, output, "reviewer-e2e")
    base = output / "base"
    base.mkdir()
    engagement = setup(base, operator_key, operator_signers, reviewer_signers)
    cases = {}

    def case(name: str, *, ceiling: str = "cross-user", **route_changes: object) -> tuple[Path, Path]:
        directory = output / name
        if ceiling == "cross-user":
            shutil.copytree(base, directory)
            selected = directory / "target/engagements/synthetic"
        else:
            directory.mkdir()
            selected = setup(directory, operator_key, operator_signers, reviewer_signers, ceiling=ceiling)
        proposal = route(selected, **route_changes)
        propose(directory, selected, route_value=proposal)
        return directory, selected

    positive_dir, positive = case("positive")
    assert next_action(positive_dir, positive)["action_id"] == "record_higher_impact_route_review"
    append(positive_dir, positive, run_event(positive, event_id="event-hyp-route-unreviewed"), ok=False, error="higher_impact_review_missing")
    accepted = review(positive_dir, positive, reviewer_key, reviewer_signers, verdict="admit")
    run_action = next_action(positive_dir, positive)
    assert run_action["action_id"] == "run_higher_impact_hypothesis"
    exact = {(tuple(item["path"]), item["operator"], json.dumps(item["value"], sort_keys=True)) for item in run_action["admission"]["constraints"]}
    expected_digest = sha256_bytes(canonical_json_bytes(reduce_engagement(positive)["hypotheses"]["hyp-route"]["higher_impact_route"]))
    assert (("payload", "route_digest"), "equals", json.dumps(expected_digest)) in exact
    assert (("payload", "route_review_ref"), "equals", json.dumps(accepted)) in exact
    wrong_digest = run_event(positive, accepted, event_id="event-hyp-route-wrong-digest")
    wrong_digest["payload"]["route_digest"] = "sha256:" + "0" * 64
    append(positive_dir, positive, wrong_digest, ok=False, error="higher_impact_run_binding_invalid")
    wrong_review = run_event(positive, accepted, event_id="event-hyp-route-wrong-review")
    wrong_review["payload"]["route_review_ref"] = "review-unrelated"
    append(positive_dir, positive, wrong_review, ok=False, error="higher_impact_run_binding_invalid")
    append(positive_dir, positive, run_event(positive, accepted))
    snapshot = reduce_engagement(positive)
    assert snapshot["hypotheses"]["hyp-route"]["status"] == "running"
    assert not snapshot["findings"] and not (positive / "attempts.jsonl").read_text().strip()
    cases["direct_allowed"] = "running, no impact confirmation"

    broken_dir, broken = case("broken-edge")
    challenged = review(broken_dir, broken, reviewer_key, reviewer_signers, verdict="hold", edge=False, reason="causal_edge_broken")
    assert next_action(broken_dir, broken)["action_id"] == "hold_higher_impact_hypothesis"
    append(broken_dir, broken, run_event(broken, challenged), ok=False, error="higher_impact_review_held")
    held = event(broken, "event-hyp-route-held", "hypothesis.status_changed", {"hypothesis_id": "hyp-route", "status": "held", "reason": "causal edge broken", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "Independent reviewer found no valid edge.", "unresolved_questions": [], "next_route": None}, origin="hyp-route", changes=[{"dimension": "search", "entity_id": "hyp-route", "previous": "selected", "current": "held"}])
    append(broken_dir, broken, held)
    propose(broken_dir, broken, route_value=None, hypothesis_id="zzz-ordinary", select=False)
    assert next_action(broken_dir, broken)["action_id"] == "record_hypothesis_disposition"
    cases["broken_edge"] = "held before run"
    cases["other_work_continues"] = "ordinary queued hypothesis selected next"

    same_model_dir, same_model_target = case("same-model")
    review(same_model_dir, same_model_target, reviewer_key, reviewer_signers, verdict="admit", same_model=True, ok=False, error="review_freshness_not_bound")
    assert next_action(same_model_dir, same_model_target)["action_id"] == "record_higher_impact_route_review"
    cases["same_model_review"] = "rejected before admission"

    stale_dir, stale = case("stale-environment")
    stale_review = review(stale_dir, stale, reviewer_key, reviewer_signers, verdict="admit")
    source = stale_dir / "owned-canary-source.txt"
    command(stale_dir, "second-preflight", sys.executable, str(RUN), "preflight", "--engagement", str(stale), "--preflight-id", "env-new", "--mode", "local_runtime", "--target", str(source), "--expected-identity", sha256_file(source), "--runtime", "/bin/sh", "--reproduction-argv", json.dumps(["/bin/sh", "-c", "true"]), "--actor-role", "broker", "--actor-id", BROKER, "--session-id", SESSION, "--recorded-at", utc_now())
    assert next_action(stale_dir, stale)["action_id"] == "hold_higher_impact_hypothesis"
    append(stale_dir, stale, run_event(stale, stale_review), ok=False, error="higher_impact_authority_stale")
    cases["stale_environment"] = "held after new preflight"

    for name, changes, expected in (
        ("ceiling", {"effect": "cross-user"}, "higher_impact_effect_ceiling_exceeded"),
        ("missing-signal", {"signal": False}, "higher_impact_safe_signal_missing"),
        ("missing-control", {"control": False}, "higher_impact_control_plan_missing"),
        ("missing-test", {"test": False}, "higher_impact_discriminating_test_missing"),
        ("offscope", {"surface": "external user"}, "higher_impact_surface_out_of_scope"),
    ):
        directory, target = case(name, ceiling="self" if name == "ceiling" else "cross-user", **changes)
        action = next_action(directory, target)
        requirements = [value for field in action["required_inputs"] for value in field["requirements"]]
        assert action["action_id"] == "hold_higher_impact_hypothesis" and expected in requirements
        cases[name] = expected

    severity_dir, severity = case("overclaim")
    review(severity_dir, severity, reviewer_key, reviewer_signers, verdict="hold", bounded=False, reason="severity_overclaimed")
    assert next_action(severity_dir, severity)["action_id"] == "hold_higher_impact_hypothesis"
    cases["overclaim"] = "held before run"

    (output / "results.json").write_bytes(canonical_json_bytes({"schema_version": 1, "cases": cases, "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}))
    print(json.dumps({"passed": True, "cases": cases, "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
