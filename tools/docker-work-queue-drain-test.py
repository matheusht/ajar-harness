#!/usr/bin/env python3
"""Guarded real-Docker acceptance tests for reducer-owned work.

The hunter workflow check fails unless the current task board alone is projected, an unrelated
task leaves the view digest unchanged, a correction stales the prior admission, the isolated
process submits one broker-stamped primary attempt, and the reducer exposes adjudication.  The
same recorded attempt then has to survive a separately signed fixture review and an exact v3
authority request before a finding revision can become active.  Forged review bindings,
historical v2 authority, interrupted sessions, and duplicate settlement must leave no extra
records behind.

Set ``HARNESS_DOCKER_QUEUE_TEST_IMAGE`` to an already-cached immutable Python image
(``repository@sha256:...``).  The test never pulls or builds an image.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import work_queue_driver as queue_driver
from claude_work_session import MODEL_AUTH_ENV_KEYS
from docker_session_runtime import (
    OWNER_LABEL,
    OWNER_LABEL_VALUE,
    DockerRuntimeLimits,
)
from engagement_records import (
    build_reference_index,
    canonical_json_bytes,
    sha256_file,
    validate_record,
)
from engagement_state import (
    _append_kernel_event,
    base_event,
    compute_review_input_hash,
    finding_revision_lane_id,
    initialize_engagement,
    read_ledger,
    reduce_engagement,
)
from hunter_view import HunterViewError, compile_hunter_view
from operator_signature import operator_challenge_bytes
from task_board import post_notice
from environment_preflight import _collect_preflight_core as collect_preflight
from work_queue_actions import queue_command_payload
from work_queue_driver import DockerQueueBackend, DriverBudget, run_driver


ROOT = Path(__file__).resolve().parents[1]
LIVE_IMAGE = os.environ.get("HARNESS_DOCKER_QUEUE_TEST_IMAGE", "")
LIVE_PYTHON = os.environ.get("HARNESS_DOCKER_QUEUE_TEST_PYTHON", "/usr/local/bin/python3")
SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
WORKER_MODEL = "claude-docker-queue-worker-20260826"
REVIEWER_MODEL = "claude-docker-queue-reviewer-20260826"
REVIEW_ID = "review-docker-queue-coverage-dry"
REVIEW_EVENT_ID = "event-docker-queue-coverage-reviewed"
COVERAGE_EVENT_ID = "event-docker-queue-coverage-dry"


SCOPE = """# Scope - Docker work queue acceptance fixture

## Surfaces in scope
- One target-local synthetic engagement.
## Benign safe-objective set
- Drain one reducer-owned coverage transition through the Docker broker.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `none`
## Accounts / fixtures
- No target or vendor accounts.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {reviewer_allowed_signers_hash}
## Authorization
- Operator allowed signers SHA256: {operator_allowed_signers_hash}
- Operator: operator-docker-queue-test
- Date: 2026-08-26
- Signed: [x]
- Record kernel: `decision-0006-v2`
"""


FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import shlex
import subprocess
import sys
from datetime import datetime, timezone


def require(condition, code):
    if not condition:
        raise SystemExit(code)


def raw_write_is_denied(path):
    try:
        path.write_bytes(b"forbidden raw model write\n")
    except OSError:
        return True
    try:
        path.unlink()
    except OSError:
        pass
    return False


def canonical_json_bytes(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n").encode("utf-8")


prompt = json.loads(sys.argv[-1])
action = prompt["item"]["next_action"]
transport = prompt["container_action_transport"]
require(action["action_id"] == "record_coverage_dry", 81)
require(action["command"] == "append-event", 82)
require(transport["kind"] == "authenticated_supervisor_relay", 83)
require(transport["client"] == "/harness/tools/container_broker_client.py", 84)
require(raw_write_is_denied(pathlib.Path("/workspace/.docker-queue-target-write")), 85)
require(raw_write_is_denied(pathlib.Path("/harness/.docker-queue-harness-write")), 86)

engagement = pathlib.Path(os.environ["HARNESS_ACTIVE_ENGAGEMENT"])
state = json.loads((engagement / "state.snapshot.json").read_bytes())
latest = state["latest_coverage_review"]
require(state["coverage"] == "active", 87)
require(latest["verdict"] == "coverage_dry", 88)
require(latest["event_ref"] == "event-docker-queue-coverage-reviewed", 89)

uid = os.getuid()
actor = {"role": "broker", "id": f"local-uid-{uid}:broker"}
event = {
    "schema_version": 1,
    "event_id": "event-docker-queue-coverage-dry",
    "engagement_id": state["engagement_id"],
    "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "actor": actor,
    "event_type": "coverage.status_changed",
    "entity_refs": [latest["event_ref"]],
    "rationale": "Close the bounded Docker queue fixture from its exact current cold review.",
    "evidence_refs": [],
    "review_refs": [],
    "finding_refs": [],
    "provenance": {
        "actor": actor,
        "session_id": f"session-posix-{uid}-{os.getsid(0)}",
        "model": None,
        "provider": None,
        "prompt_version": None,
        "card_versions": [],
        "tool_versions": [],
    },
    "ex_ante": None,
    "state_changes": [{
        "dimension": "coverage",
        "entity_id": state["engagement_id"],
        "previous": "active",
        "current": "coverage_dry",
    }],
    "payload": {
        "entity_id": state["engagement_id"],
        "status": "coverage_dry",
        "coverage_review_ref": latest["event_ref"],
    },
    "operation_class": "notebook",
}
event_path = pathlib.Path("/scratch/docker-queue-coverage-event.json")
event_path.write_bytes(canonical_json_bytes(event))

arguments = list(action["arguments"])
require(arguments.count("<coverage-status-event-json>") == 1, 90)
arguments = [
    str(event_path) if value == "<coverage-status-event-json>" else value
    for value in arguments
]
action_result = subprocess.run(
    [
        transport["python"],
        transport["client"],
        "action",
        "--command",
        action["command"],
        "--arguments-json",
        json.dumps(arguments, sort_keys=True, separators=(",", ":")),
    ],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
try:
    action_output = json.loads(action_result.stdout)
except json.JSONDecodeError:
    raise SystemExit(91)
require(action_result.returncode == 0, 92)
require(action_result.stderr == b"", 93)
require(action_output.get("ok") is True, 94)
require(action_output.get("event_id") == "event-docker-queue-coverage-dry", 95)

settings = json.loads(sys.argv[sys.argv.index("--settings") + 1])
hook_command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
stop_delivery = json.dumps(
    {
        "session_id": os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"],
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
stop_result = subprocess.run(
    shlex.split(hook_command),
    input=stop_delivery,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
try:
    stop_output = json.loads(stop_result.stdout)
except json.JSONDecodeError:
    raise SystemExit(96)
require(stop_result.returncode == 0, 97)
require(stop_result.stderr == b"", 98)
require(stop_output == {}, 99)

print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01}))
'''

FAKE_HUNTER = r'''#!/usr/local/bin/python3
import json
import os
import pathlib
import shlex
import subprocess
import sys
from datetime import datetime, timezone

view = pathlib.Path("/workspace")
required = ["brief.json", "manifest.json", "scope.md", "contracts/proposal-template.json", "contracts/attempt-v2.schema.json", "contracts/research-common.schema.json", "SUBMIT.md"]
if not all((view / name).is_file() for name in required):
    raise SystemExit(71)
if (view / "engagements").exists() or (view / ".git").exists():
    raise SystemExit(72)
prompt = json.loads(sys.argv[-1])
transport = prompt["container_action_transport"]
brief = json.loads((view / "brief.json").read_text())
manifest = json.loads((view / "manifest.json").read_text())
if manifest.get("treatment") != "compiled_current_only_with_task_notices":
    raise SystemExit(74)
notice_paths = [row["path"] for row in brief.get("task_notices", [])]
if notice_paths != ["notices/notice-000.json", "notices/notice-001.json"]:
    raise SystemExit(75)
notice_text = "\n".join((view / path).read_text() for path in notice_paths)
if "corrects the owned marker to green" not in notice_text or "UNRELATED SECRET" in notice_text:
    raise SystemExit(76)
proposal = json.loads((view / "contracts/proposal-template.json").read_text())
proposal["attempt_id"] = "attempt-docker-hunter-view"
proposal["recorded_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
proposal["surface"] = "owned synthetic route file"
proposal["action_summary"] = "Read the single allowlisted route and compare its benign marker."
proposal["observation"]["statement"] = "The allowlisted route contains the expected owned marker."
proposal_path = pathlib.Path("/scratch/attempt.json")
proposal_path.write_text(json.dumps(proposal, sort_keys=True, separators=(",", ":")) + "\n")
argv = list(transport["argv"])
argument_index = argv.index("--arguments-json") + 1
arguments = json.loads(argv[argument_index])
argv[argument_index] = json.dumps([str(proposal_path) if value == "/scratch/hunter-action-input.json" else value for value in arguments], separators=(",", ":"))
result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if result.returncode != 0 or json.loads(result.stdout).get("ok") is not True:
    raise SystemExit(73)
print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01}))
'''


def _docker_owned_ids(docker: Path, kind: str) -> frozenset[str]:
    if kind == "container":
        arguments = [
            "container",
            "ls",
            "-aq",
            "--filter",
            f"label={OWNER_LABEL}={OWNER_LABEL_VALUE}",
        ]
    elif kind == "network":
        arguments = [
            "network",
            "ls",
            "-q",
            "--filter",
            f"label={OWNER_LABEL}={OWNER_LABEL_VALUE}",
        ]
    else:  # pragma: no cover - test-internal closed call set
        raise AssertionError(kind)
    result = subprocess.run(
        [str(docker), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"Docker {kind} inventory failed without cleanup evidence")
    return frozenset(line for line in result.stdout.splitlines() if line)


class DockerWorkQueueDrainAcceptanceTest(unittest.TestCase):
    def _run_cli(self, workspace: Path, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "run-engagement.py"), *arguments],
            cwd=workspace, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, check=False,
        )

    def _seed_current_signed_dry_review(
        self, root: Path, workspace: Path, engagement: Path
    ) -> None:
        reviewer_key = root / "reviewer-ed25519"
        subprocess.run(
            [
                str(SSH_KEYGEN),
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(reviewer_key),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        public_parts = reviewer_key.with_suffix(".pub").read_text(
            encoding="utf-8"
        ).split()
        allowed_signers = root / "reviewer-allowed-signers"
        allowed_signers.write_text(
            f"reviewer-docker-queue {public_parts[0]} {public_parts[1]}\n"
            f"operator-docker-queue-test {public_parts[0]} {public_parts[1]}\n",
            encoding="utf-8",
        )
        self.fixture_key = reviewer_key
        self.allowed_signers = allowed_signers
        engagement.joinpath("scope.md").write_text(
            SCOPE.format(
                reviewer_allowed_signers_hash=sha256_file(allowed_signers),
                operator_allowed_signers_hash=sha256_file(allowed_signers),
            ),
            encoding="utf-8",
        )
        initialize_engagement(engagement, "2026-08-26T12:00:00Z")
        _append_kernel_event(
            engagement,
            base_event(
                event_id="event-docker-queue-origin",
                engagement_id=engagement.name,
                recorded_at="2026-08-26T12:00:01Z",
                actor_role="orchestrator",
                actor_id="orchestrator-docker-queue",
                event_type="observation.recorded",
                rationale="Establish the bounded synthetic search challenged by the cold review.",
                payload={
                    "entity_id": "observation-docker-queue-origin",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-docker-queue-origin",
                operation_class="notebook",
                model="fixture-origin-model",
            ),
        )

        review = {
            "schema_version": 1,
            "review_id": REVIEW_ID,
            "engagement_id": engagement.name,
            "review_type": "coverage",
            "proposed_finding_id": None,
            "recorded_at": "2026-08-26T12:00:02Z",
            "entity_ref": engagement.name,
            "finding_revision": None,
            "input_refs": [],
            "input_hash": "sha256:" + "0" * 64,
            "evidence_refs": [],
            "rationale": "The empty synthetic search space has no omitted material branch.",
            "conflicting_evidence": [],
            "verdict": "coverage_dry",
            "corrections": [],
            "required_next_actions": [],
            "independence": {
                "reviewer_id": "reviewer-docker-queue",
                "reviewer_run_id": "run-docker-queue-review",
                "reviewer_session_id": "session-docker-queue-review",
                "reviewer_model": REVIEWER_MODEL,
                "fresh_context": True,
                "prior_verdict_visible": False,
                "disconfirming_objective": "Find any omitted branch in the empty fixture space.",
                "originating_run_id": "event-docker-queue-origin",
            },
            "bounded_space": "The fixture declares no hypotheses or live target surfaces.",
            "hypothesis_dispositions": [],
            "omitted_branch_challenge": "No branch exists outside the empty fixture space.",
            "residual_uncertainty": [],
        }
        review["input_hash"] = compute_review_input_hash(
            engagement, review, build_reference_index(engagement)
        )
        review_path = root / f"{REVIEW_ID}.json"
        review_path.write_bytes(canonical_json_bytes(review))
        subprocess.run(
            [
                str(SSH_KEYGEN),
                "-q",
                "-Y",
                "sign",
                "-f",
                str(reviewer_key),
                "-n",
                "llm-redteam-harness-review-v1",
                str(review_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )

        uid = os.getuid()
        sid = os.getsid(0)
        actor_id = f"local-uid-{uid}:broker"
        session_id = f"session-posix-{uid}-{sid}"
        event_path = root / f"{REVIEW_EVENT_ID}.json"
        event_path.write_bytes(
            canonical_json_bytes(
                base_event(
                    event_id=REVIEW_EVENT_ID,
                    engagement_id=engagement.name,
                    recorded_at="2026-08-26T12:00:03Z",
                    actor_role="broker",
                    actor_id=actor_id,
                    event_type="review.coverage_completed",
                    rationale="Record the host-prepared independent dry coverage review.",
                    payload={
                        "review_type": "coverage",
                        "verdict": "coverage_dry",
                        "review_ref": REVIEW_ID,
                        "reviewer_id": "reviewer-docker-queue",
                    },
                    review_refs=[REVIEW_ID],
                    session_id=session_id,
                    operation_class="notebook",
                )
            )
        )
        recorded = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "run-engagement.py"),
                "record-review",
                "--engagement",
                str(engagement),
                "--file",
                str(review_path),
                "--event",
                str(event_path),
                "--actor-id",
                actor_id,
                "--session-id",
                session_id,
                "--signature",
                str(review_path) + ".sig",
                "--allowed-signers",
                str(allowed_signers),
            ],
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

    def _seed_running_hypothesis(self, engagement: Path) -> None:
        zero_cost = {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0}
        cards = ["llm07.system-prompt-leakage", "task-reframing", "adjudication-oracle"]
        events = [
            base_event(event_id="event-hunter-observation", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:04Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="observation.recorded", rationale="Record the owned synthetic route marker before choosing a bounded experiment.", payload={"entity_id": "observation-hunter", "entity_type": "observation", "status": "recorded"}),
            base_event(event_id="event-hunter-routing", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:05Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="routing.assessed", rationale="Route the owned marker to the exact safe-signal cards.", payload={"entity_id": "routing-hunter", "source_observation_ref": "event-hunter-observation", "activation_strength": "strong", "card_ids": cards, "status": "assessed"}, entity_refs=["event-hunter-observation"]),
        ]
        candidate = base_event(event_id="event-hunter-candidate", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:06Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="candidate.proposed", rationale="Select one local source inspection with no target contact.", payload={"candidate_id": "candidate-hunter", "source_observation_ref": "event-hunter-observation", "routing_review_ref": "event-hunter-routing", "activation_strength": "strong", "card_ids": cards, "status": "queued", "expected_information_gain": 1, "safety_class": "clear_local", "cost_estimate": zero_cost}, entity_refs=["event-hunter-observation", "event-hunter-routing"], state_changes=[{"dimension": "search", "entity_id": "candidate-hunter", "previous": None, "current": "queued"}])
        candidate["ex_ante"] = {"probability": 0.5, "ordinal": "strong", "recorded_before_outcome": True}
        events.extend([
            candidate,
            base_event(event_id="event-hunter-selected", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:07Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="candidate.selected", rationale="Choose the only bounded synthetic candidate.", payload={"candidate_id": "candidate-hunter", "status": "selected", "reason": "only bounded synthetic candidate"}, state_changes=[{"dimension": "search", "entity_id": "candidate-hunter", "previous": "queued", "current": "selected"}]),
            base_event(event_id="event-hunter-hypothesis", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:08Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="hypothesis.created", rationale="Create the one bounded current hypothesis.", payload={"hypothesis_id": "hypothesis-hunter", "origin_type": "candidate", "origin_ref": "candidate-hunter", "candidate_ref": "candidate-hunter", "hypothesis_statement": "The owned route contains the distinctive benign marker.", "suspected_invariant": "Only the allowlisted route exposes the marker.", "trust_boundary": "owned source reader to owned route", "attacker_path": ["owned reader", "route"], "impact_ceiling": "clear_local source inspection", "bounded_space": "one allowlisted route file", "lens_ids": ["authorization"], "card_ids": cards, "expected_confirming_evidence": [{"evidence_type": "trace", "description": "exact benign marker", "required": True}], "decisive_falsifiers": ["marker absent"], "cost_estimate": zero_cost, "constraints": ["read only", "no target contact"], "next_experiment": "read the exact allowlisted route once", "completion_criteria": ["truthful primary attempt"], "status": "queued"}, entity_refs=["candidate-hunter"], state_changes=[{"dimension": "search", "entity_id": "hypothesis-hunter", "previous": None, "current": "queued"}]),
            base_event(event_id="event-hunter-hypothesis-selected", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:09Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="hypothesis.status_changed", rationale="Select the bounded hypothesis.", payload={"hypothesis_id": "hypothesis-hunter", "status": "selected", "reason": "execute bounded source inspection", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "selected for one attempt", "unresolved_questions": [], "next_route": "read exact route"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-hunter", "previous": "queued", "current": "selected"}]),
            base_event(event_id="event-hunter-hypothesis-running", engagement_id=engagement.name, recorded_at="2026-08-26T12:00:10Z", actor_role="orchestrator", actor_id="orchestrator-docker-queue", event_type="hypothesis.status_changed", rationale="Begin the bounded source inspection.", payload={"hypothesis_id": "hypothesis-hunter", "status": "running", "reason": "execute bounded source inspection", "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [], "conflicting_evidence_refs": [], "disposition_rationale": "await one primary attempt", "unresolved_questions": [], "next_route": "read exact route"}, state_changes=[{"dimension": "search", "entity_id": "hypothesis-hunter", "previous": "selected", "current": "running"}]),
        ])
        for event in events:
            _append_kernel_event(engagement, event)

    def _seed_task_notices(self, engagement: Path) -> tuple[dict, dict, dict]:
        for task_index, task_id in enumerate(("hypothesis-hunter", "unrelated-hypothesis")):
            base_micros = task_index * 3 + 1
            _append_kernel_event(engagement, base_event(
                event_id=f"event-task-defined-{task_id}", engagement_id=engagement.name,
                recorded_at=f"2026-08-26T12:00:10.{base_micros}00000Z", actor_role="orchestrator",
                actor_id="orchestrator-docker-queue", event_type="observation.recorded",
                rationale="Define one bounded synthetic task before advisory delivery.",
                payload={"entity_id": task_id, "entity_type": "task_definition", "status": "recorded", "task_id": task_id, "source_revision": "task-v1"},
                session_id="session-task-definition", operation_class="notebook"))
            for ordinal, principal in enumerate(("worker-a", "worker-b"), start=1):
                _append_kernel_event(engagement, base_event(
                    event_id=f"event-initial-{task_id}-{ordinal}", engagement_id=engagement.name,
                    recorded_at=f"2026-08-26T12:00:10.{base_micros + ordinal}00000Z", actor_role="orchestrator",
                    actor_id=principal, event_type="observation.recorded",
                    rationale="Record an independent observation before advisory delivery.",
                    payload={"entity_id": f"initial-{task_id}-{ordinal}", "entity_type": "independent_initial", "status": "recorded", "task_id": task_id, "source_revision": f"source-v{ordinal}"},
                    session_id=f"session-{principal}", operation_class="notebook"))
        first_notice = {
            "notice_version": 1, "notice_id": "hunter-notice-1", "task_id": "hypothesis-hunter",
            "principal_id": "worker-a", "source_event_ref": "event-initial-hypothesis-hunter-1",
            "source_revision": "source-v1", "observation": "The owned marker is blue.",
            "applicability": "Use only for the current synthetic hypothesis.",
            "uncertainty": "A later revision may correct the marker.", "predecessor_event_ref": None,
        }
        first = post_notice(engagement, first_notice, recorded_at="2026-08-26T12:00:10.700000Z")
        unrelated_notice = {
            **first_notice, "notice_id": "unrelated-notice-1", "task_id": "unrelated-hypothesis",
            "source_event_ref": "event-initial-unrelated-hypothesis-1",
            "observation": "UNRELATED SECRET MARKER MUST NOT APPEAR.",
        }
        correction = {
            **first_notice, "notice_id": "hunter-notice-2", "principal_id": "worker-b",
            "source_event_ref": "event-initial-hypothesis-hunter-2", "source_revision": "source-v2",
            "observation": "Revision v2 corrects the owned marker to green.",
            "uncertainty": "Only the allowlisted route remains authoritative.",
            "predecessor_event_ref": first["event_id"],
        }
        return first, unrelated_notice, correction

    def _adjudicate_and_activate_refuted_finding(
        self, root: Path, workspace: Path, engagement: Path, attempt_id: str
    ) -> None:
        """Take the isolated attempt through signed review and exact v3 filing authority."""
        uid, sid = os.getuid(), os.getsid(0)
        broker_id, local_session = f"local-uid-{uid}:broker", f"session-posix-{uid}-{sid}"
        finding_id, review_id = "F-docker-hunter", "review-docker-hunter-refuted"
        review_time = datetime.now(timezone.utc)
        review_time_text = review_time.isoformat().replace("+00:00", "Z")
        review = {
            "schema_version": 1, "review_id": review_id, "engagement_id": engagement.name,
            "review_type": "claim_adjudication", "proposed_finding_id": finding_id,
            "recorded_at": review_time_text, "entity_ref": finding_id, "finding_revision": None,
            "input_refs": [attempt_id], "input_hash": "sha256:" + "0" * 64,
            "evidence_refs": [attempt_id],
            "rationale": "The isolated observation describes the benign marker but does not establish a security mechanism or impact.",
            "conflicting_evidence": [attempt_id], "verdict": "refuted",
            "corrections": ["Retain this as a negative record rather than a supported finding."],
            "required_next_actions": [],
            "independence": {
                "reviewer_id": "reviewer-docker-queue", "reviewer_run_id": "run-docker-hunter-refutation",
                "reviewer_session_id": "session-docker-hunter-refutation", "reviewer_model": REVIEWER_MODEL,
                "fresh_context": True, "prior_verdict_visible": False,
                "disconfirming_objective": "Determine whether the benign marker proves a security claim.",
                "originating_run_id": attempt_id,
            },
            "control_applicability": [{"attempt_ref": attempt_id, "applicable": False, "rationale": "The sole primary attempt is evidence under review, not a control."}],
        }
        review["input_hash"] = compute_review_input_hash(
            engagement, review, build_reference_index(engagement)
        )
        initial_review = json.loads(json.dumps(review))
        initial_review.update({
            "review_id": "review-docker-hunter-supported",
            "verdict": "supported",
            "rationale": "The benign observation is coherent enough to open the claim, pending an adversarial independent refutation pass.",
            "conflicting_evidence": [], "corrections": [],
        })
        initial_review["independence"].update({
            "reviewer_run_id": "run-docker-hunter-review",
            "reviewer_session_id": "session-docker-hunter-review",
        })
        initial_review["input_hash"] = compute_review_input_hash(
            engagement, initial_review, build_reference_index(engagement)
        )
        initial_review_path = root / "review-docker-hunter-supported.json"
        initial_review_path.write_bytes(canonical_json_bytes(initial_review))
        subprocess.run(
            [str(SSH_KEYGEN), "-q", "-Y", "sign", "-f", str(self.fixture_key),
             "-n", "llm-redteam-harness-review-v1", str(initial_review_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True,
        )
        initial_event = base_event(
            event_id="event-docker-hunter-supported", engagement_id=engagement.name,
            recorded_at=review_time_text, actor_role="broker", actor_id=broker_id,
            event_type="claim.adjudicated", rationale="Record the initial signed adjudication before the disconfirming pass.",
            payload={"entity_id": finding_id, "status": "supported", "review_ref": initial_review["review_id"],
                     "reviewer_id": "reviewer-docker-queue", "review_digest": sha256_file(initial_review_path)},
            entity_refs=[attempt_id], review_refs=[initial_review["review_id"]], evidence_refs=[attempt_id],
            state_changes=[{"dimension": "claim", "entity_id": finding_id, "previous": None, "current": "supported"}],
            session_id=local_session, operation_class="notebook",
        )
        initial_event_path = root / "event-docker-hunter-supported.json"
        initial_event_path.write_bytes(canonical_json_bytes(initial_event))
        initial_recorded = self._run_cli(
            workspace, "record-review", "--engagement", str(engagement), "--file", str(initial_review_path),
            "--event", str(initial_event_path), "--actor-id", broker_id, "--session-id", local_session,
            "--signature", str(initial_review_path) + ".sig", "--allowed-signers", str(self.allowed_signers),
        )
        self.assertEqual(initial_recorded.returncode, 0, initial_recorded.stdout + initial_recorded.stderr)
        review_path = root / f"{review_id}.json"
        review_path.write_bytes(canonical_json_bytes(review))
        subprocess.run(
            [str(SSH_KEYGEN), "-q", "-Y", "sign", "-f", str(self.fixture_key),
             "-n", "llm-redteam-harness-review-v1", str(review_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True,
        )
        event = base_event(
            event_id="event-docker-hunter-refuted", engagement_id=engagement.name,
            recorded_at=review_time_text, actor_role="broker", actor_id=broker_id,
            event_type="claim.adjudicated",
            rationale="Record an independently signed negative adjudication of the isolated attempt.",
            payload={"entity_id": finding_id, "status": "refuted", "review_ref": review_id,
                     "reviewer_id": "reviewer-docker-queue", "review_digest": sha256_file(review_path)},
            entity_refs=[attempt_id], review_refs=[review_id], evidence_refs=[attempt_id],
            state_changes=[{"dimension": "claim", "entity_id": finding_id, "previous": "supported", "current": "refuted"}],
            session_id=local_session, operation_class="notebook",
        )
        event_path = root / "event-docker-hunter-refuted.json"
        event_path.write_bytes(canonical_json_bytes(event))
        forged = json.loads(json.dumps(event))
        forged["event_id"] = "event-docker-hunter-forged-reviewer"
        forged["payload"]["reviewer_id"] = "forged-reviewer"
        forged_path = root / "event-docker-hunter-forged-reviewer.json"
        forged_path.write_bytes(canonical_json_bytes(forged))
        before_review = engagement.joinpath("events.jsonl").read_bytes()
        forged_result = self._run_cli(
            workspace, "record-review", "--engagement", str(engagement), "--file", str(review_path),
            "--event", str(forged_path), "--actor-id", broker_id, "--session-id", local_session,
            "--signature", str(review_path) + ".sig", "--allowed-signers", str(self.allowed_signers),
        )
        self.assertNotEqual(forged_result.returncode, 0, forged_result.stdout + forged_result.stderr)
        self.assertIn("canonical_review_binding_invalid", forged_result.stdout + forged_result.stderr)
        self.assertEqual(engagement.joinpath("events.jsonl").read_bytes(), before_review)
        recorded = self._run_cli(
            workspace, "record-review", "--engagement", str(engagement), "--file", str(review_path),
            "--event", str(event_path), "--actor-id", broker_id, "--session-id", local_session,
            "--signature", str(review_path) + ".sig", "--allowed-signers", str(self.allowed_signers),
        )
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

        state = reduce_engagement(engagement)
        self.assertEqual(state["claim_adjudications"][finding_id]["status"], "refuted")
        fixture = json.loads((ROOT / "fixtures/engagement-records/suite.json").read_text())
        finding = next(row["record"] for row in fixture["cases"] if row["id"] == "finding-v3-rich")
        finding_time = datetime.now(timezone.utc).replace(microsecond=0)
        finding.update({
            "finding_id": finding_id, "engagement_id": engagement.name, "revision": 1,
            "supersedes_revision": None, "recorded_at": finding_time.isoformat().replace("+00:00", "Z"),
            "change_reason": "Retain the independently adjudicated negative result.", "claim_state": "refuted",
            "adjudication": {"review_ref": review_id, "justification": "Independent review refuted the security claim."},
            "privilege_context": {"claimed_position": "not-established", "execution_position": "not-established", "evidence_refs": []},
            "state_provenance": {"mode": "not-established", "evidence_refs": [], "synthesized_setup": []},
            "search_linkage": {"candidate_refs": ["candidate-hunter"], "hypothesis_refs": ["hypothesis-hunter"]},
        })
        finding["classification"]["severity"] = {"label": "informational", "system": "none", "vector": None, "score": None, "rationale": "A refuted synthetic claim has no security severity."}
        finding["scope_provenance"] = {
            "scope_hash": state["scope_hash"], "environment_ref": state["active_environment_ref"],
            "target_refs": [], "provenance": {
                "actor": {"role": "reviewer", "id": "reviewer-docker-queue"},
                "session_id": "session-docker-hunter-refutation", "model": REVIEWER_MODEL,
                "provider": None, "prompt_version": None, "card_versions": [], "tool_versions": [],
            },
        }
        for claim_name in ("mechanism", "reachability"):
            finding["claims"][claim_name]["evidence_refs"] = [attempt_id]
        for impact in finding["claims"]["impact_claims"]:
            impact.update({"evidence_refs": [attempt_id], "status": "not_demonstrated"})
        finding["proof"].update({
            "primary_attempt_refs": [attempt_id], "negative_control_refs": [],
            "positive_control_refs": [], "replay_refs": [], "evidence_refs": [attempt_id],
            "contamination_disposition": "not_applicable", "fresh_state_properties": [],
            "control_applicability": {"negative": "not_applicable", "positive": "not_applicable", "replay": "not_applicable", "rationale": "Negative records need no manufactured exploit controls."},
        })
        for proof in finding["proof"]["claim_proofs"]:
            proof.update({"attempt_refs": [attempt_id], "artifact_refs": [], "control_refs": [], "replay_refs": []})
        finding_path = root / f"{finding_id}.json"
        finding_path.write_bytes(canonical_json_bytes(finding))
        self.assertEqual(validate_record(finding, "finding-v3"), [])

        metadata = state["claim_adjudications"][finding_id]
        target = {
            "type": "finding", "id": finding_id, "expected_revision": metadata["expected_filing_revision"],
            "claim_state": metadata["status"], "adjudication_event_ref": metadata["event_ref"],
            "adjudication_review_ref": metadata["review_ref"], "resolves_review_refs": [],
            "file_digest": sha256_file(finding_path),
        }
        lane_id = finding_revision_lane_id(target)
        action = {
            "action_kind": "revise-finding", "action_version": 3, "lane_id": lane_id,
            "executor_id": broker_id, "session_id": local_session, "file_digest": target["file_digest"],
            "operator_id": "operator-docker-queue-test", "proposal": finding, "target": target,
        }
        historical = {**action, "action_version": 2}
        historical_path = root / "historical-finding-action.json"
        historical_path.write_bytes(canonical_json_bytes(historical))
        request_time = datetime.now(timezone.utc).replace(microsecond=0)
        expires = request_time + timedelta(minutes=10)
        common_request = [
            "--engagement", str(engagement), "--action-kind", "revise-finding", "--lane-id", lane_id,
            "--actor-role", "broker", "--actor-id", broker_id, "--session-id", local_session,
            "--recorded-at", request_time.isoformat().replace("+00:00", "Z"),
            "--expires-at", expires.isoformat().replace("+00:00", "Z"), "--reason", "Request exact negative finding activation.",
        ]
        before_authority = engagement.joinpath("events.jsonl").read_bytes()
        rejected = self._run_cli(
            workspace, "request-authority", "--request-id", "request-historical-v2",
            "--action-file", str(historical_path), *common_request,
        )
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
        self.assertIn("historical_finding_action_not_activatable", rejected.stdout + rejected.stderr)
        self.assertEqual(engagement.joinpath("events.jsonl").read_bytes(), before_authority)

        action_path = root / "finding-action-v3.json"
        action_path.write_bytes(canonical_json_bytes(action))
        request_id = "request-docker-hunter-finding-v3"
        requested = self._run_cli(
            workspace, "request-authority", "--request-id", request_id,
            "--action-file", str(action_path), *common_request,
        )
        self.assertEqual(requested.returncode, 0, requested.stdout + requested.stderr)
        pending = reduce_engagement(engagement)["authority_requests"][request_id]
        resolution_time = datetime.now(timezone.utc).replace(microsecond=0)
        operation = f"resolve-authority:{request_id}:{pending['action_digest']}:approved:{resolution_time.isoformat().replace('+00:00', 'Z')}"
        challenge = operator_challenge_bytes(
            engagement_id=engagement.name, scope_hash=state["scope_hash"],
            ledger_hash=read_ledger(engagement, "event")[-1]["record_hash"],
            operation=operation, operator_id="operator-docker-queue-test",
        )
        challenge_path = root / "operator-authority-challenge.json"
        challenge_path.write_bytes(challenge)
        subprocess.run(
            [str(SSH_KEYGEN), "-q", "-Y", "sign", "-f", str(self.fixture_key),
             "-n", "llm-redteam-harness-operator-v1", str(challenge_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True,
        )
        signed_env = {key: value for key, value in os.environ.items() if key not in {"HARNESS_OPERATOR_SIGNATURE_FILE", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE"}}
        signed_env.update({"HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig", "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(self.allowed_signers)})
        resolved = self._run_cli(
            workspace, "resolve-authority", "--engagement", str(engagement), "--request-id", request_id,
            "--resolution", "approved", "--operator-id", "operator-docker-queue-test",
            "--session-id", local_session, "--recorded-at", resolution_time.isoformat().replace("+00:00", "Z"),
            "--reason", "Approve the exact signed negative finding revision.", env=signed_env,
        )
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        settlement_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        settlement_args = [
            "settle-approved-revision", "--engagement", str(engagement), "--file", str(finding_path),
            "--operator-id", "operator-docker-queue-test", "--recorded-at", settlement_time,
            "--authority-request-id", request_id, "--lane-id", lane_id,
            "--executor-id", broker_id, "--session-id", local_session,
        ]
        settled = self._run_cli(workspace, *settlement_args)
        self.assertEqual(settled.returncode, 0, settled.stdout + settled.stderr)
        applied_state = reduce_engagement(engagement)
        self.assertEqual(applied_state["findings"][finding_id]["revision"], 1)
        before_retry = engagement.joinpath("events.jsonl").read_bytes()
        retry = self._run_cli(workspace, *settlement_args)
        self.assertNotEqual(retry.returncode, 0, retry.stdout + retry.stderr)
        self.assertEqual(engagement.joinpath("events.jsonl").read_bytes(), before_retry)

    def test_interrupted_docker_session_without_commit_remains_unrecorded(self) -> None:
        if not SSH_KEYGEN.is_file():
            self.skipTest("ssh-keygen unavailable for the signed queue fixture")
        with tempfile.TemporaryDirectory(prefix="docker-interrupt-no-commit-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "target"
            engagement = workspace / "engagements" / "docker-queue"
            engagement.mkdir(parents=True)
            self._seed_current_signed_dry_review(root, workspace, engagement)
            backend = DockerQueueBackend(
                image="python@sha256:" + "a" * 64,
            python_executable=LIVE_PYTHON,
                docker_executable=Path("/usr/local/bin/docker"),
                limits=DockerRuntimeLimits(),
            )
            interrupted = queue_driver._QueueSessionExecution(
                session=queue_driver.SessionResult(
                    "11111111-1111-4111-8111-111111111111",
                    True,
                    False,
                    137,
                    False,
                    None,
                    None,
                ),
                interrupted=True,
            )
            with mock.patch(
                "work_queue_driver._run_docker_queue_session",
                return_value=interrupted,
            ):
                result = run_driver(
                    workspace=workspace,
                    engagement=engagement,
                    executable=Path("/workspace/not-executed"),
                    model=WORKER_MODEL,
                    reviewer_model=REVIEWER_MODEL,
                    budget=DriverBudget(1, 30.0, 10.0, None),
                    docker_backend=backend,
                )
        self.assertEqual(result["status"], "interrupted_unrecorded")
        self.assertFalse(result["completed"])
        self.assertEqual(result["sessions_started"], 1)
        self.assertEqual(result["history"], [])

    def test_hunter_run_retains_target_local_manifest_after_projection_cleanup(self) -> None:
        # Failure modes: cleanup deletes the only manifest, run history loses its path,
        # or the retained bytes do not match the admitted cognitive view digest.
        if not SSH_KEYGEN.is_file():
            self.skipTest("ssh-keygen unavailable for the signed queue fixture")
        with tempfile.TemporaryDirectory(prefix="docker-hunter-manifest-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "target"
            engagement = workspace / "engagements" / "docker-hunter"
            engagement.mkdir(parents=True)
            self._seed_current_signed_dry_review(root, workspace, engagement)
            route = workspace / "src" / "route.txt"
            route.parent.mkdir()
            route.write_text("owned synthetic marker\n", encoding="utf-8")
            collect_preflight(
                engagement, preflight_id="preflight-docker-hunter", mode="package",
                target=route, expected_identity=sha256_file(route),
                runtime=Path(sys.executable).resolve(),
                reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"],
                operator_id="operator-docker-queue-test", recorded_at="2026-08-26T12:00:03.500000Z",
                operator_redaction_attested=True, endpoint_identity="local", account_role="owner",
            )
            self._seed_running_hypothesis(engagement)
            backend = DockerQueueBackend(
                image="python@sha256:" + "a" * 64,
                python_executable=LIVE_PYTHON,
                docker_executable=Path("/usr/local/bin/docker"),
                limits=DockerRuntimeLimits(),
            )
            execution = queue_driver._QueueSessionExecution(
                session=queue_driver.SessionResult(
                    "11111111-1111-4111-8111-111111111111", True, False, 0, True, False, None,
                ),
                interrupted=False,
            )
            with mock.patch("work_queue_driver._run_docker_queue_session", return_value=execution):
                result = run_driver(
                    workspace=workspace, engagement=engagement,
                    executable=Path("/workspace/not-executed"), model=WORKER_MODEL,
                    reviewer_model=REVIEWER_MODEL, budget=DriverBudget(1, 30.0, 10.0, None),
                    docker_backend=backend, read_only_inputs=(route,),
                )
            entry = result["history"][0]
            retained = entry["view_manifest"]
            self.assertEqual(retained["relative_path"], f"driver-view-manifests/{result['run_ref']}-1.json")
            manifest = json.loads((engagement / retained["relative_path"]).read_bytes())
            self.assertEqual(sha256_bytes(canonical_json_bytes(manifest)), retained["digest"])
            self.assertEqual(manifest["view_digest"], entry["cognitive_view"]["view_digest"])
            self.assertIn("exclusion_policy", manifest)
            self.assertEqual(validate_record(result, "work-queue-driver"), [])

    @unittest.skipUnless(
        LIVE_IMAGE,
        "set HARNESS_DOCKER_QUEUE_TEST_IMAGE to an already-cached immutable Python image",
    )
    def test_real_docker_hunter_uses_only_projection_and_records_bound_attempt(self) -> None:
        if sys.platform != "darwin":
            self.skipTest("the strong Docker runtime currently supports local Docker Desktop on Darwin")
        docker_text = shutil.which("docker")
        if docker_text is None or not SSH_KEYGEN.is_file():
            self.skipTest("Docker or ssh-keygen unavailable")
        docker = Path(docker_text).resolve(strict=True)
        before_containers = _docker_owned_ids(docker, "container")
        before_networks = _docker_owned_ids(docker, "network")
        with tempfile.TemporaryDirectory(prefix="docker-hunter-view-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "target"
            engagement = workspace / "engagements" / "docker-hunter"
            engagement.mkdir(parents=True)
            self._seed_current_signed_dry_review(root, workspace, engagement)
            route = workspace / "src" / "route.txt"
            route.parent.mkdir()
            route.write_text("owned synthetic marker\n", encoding="utf-8")
            collect_preflight(
                engagement,
                preflight_id="preflight-docker-hunter",
                mode="package",
                target=route,
                expected_identity=sha256_file(route),
                runtime=Path(sys.executable).resolve(),
                reproduction_argv=[str(Path(sys.executable).resolve()), "-c", "pass"],
                operator_id="operator-docker-queue-test",
                recorded_at="2026-08-26T12:00:03.500000Z",
                operator_redaction_attested=True,
                endpoint_identity="local",
                account_role="owner",
            )
            self._seed_running_hypothesis(engagement)
            state = reduce_engagement(engagement)
            payload = queue_command_payload("next", state, engagement)
            self.assertEqual(payload["item"]["next_action"]["action_id"], "record_hunter_primary")
            first_notice, unrelated_notice, correction = self._seed_task_notices(engagement)
            state = reduce_engagement(engagement)
            item = queue_command_payload("next", state, engagement)["item"]
            stale_view = compile_hunter_view(
                workspace=workspace, engagement=engagement, state=state, item=item,
                target_inputs=(route,), methodology_root=ROOT / "skills")
            self.assertEqual(stale_view.manifest["treatment"], "compiled_current_only_with_task_notices")
            self.assertEqual([row["event_id"] for row in stale_view.manifest["task_notices"]], [first_notice["event_id"]])
            initial_view_digest = stale_view.view_digest
            post_notice(engagement, unrelated_notice, recorded_at="2026-08-26T12:00:10.800000Z")
            unrelated_state = reduce_engagement(engagement)
            unrelated_item = queue_command_payload("next", unrelated_state, engagement)["item"]
            with compile_hunter_view(
                workspace=workspace, engagement=engagement, state=unrelated_state,
                item=unrelated_item, target_inputs=(route,), methodology_root=ROOT / "skills",
            ) as unrelated_view:
                self.assertEqual(unrelated_view.view_digest, initial_view_digest)
                self.assertNotIn(b"UNRELATED SECRET", (unrelated_view.projection / "brief.json").read_bytes())
            post_notice(engagement, correction, recorded_at="2026-08-26T12:00:10.900000Z")
            corrected_state = reduce_engagement(engagement)
            corrected_item = queue_command_payload("next", corrected_state, engagement)["item"]
            with self.assertRaises(HunterViewError) as stale:
                stale_view.assert_current(
                    workspace=workspace, engagement=engagement, state=corrected_state,
                    item=corrected_item, methodology_root=ROOT / "skills")
            self.assertEqual(str(stale.exception), "hunter_view_stale")
            stale_view.close()
            state = corrected_state

            original_compile = queue_driver.compile_hunter_view
            observed_roots: list[Path] = []

            def compile_with_test_provider(**arguments: object) -> object:
                packet = original_compile(**arguments)  # type: ignore[arg-type]
                os.chmod(packet.runtime, 0o700)
                provider = packet.runtime / "fake-claude"
                provider.write_text(textwrap.dedent(FAKE_HUNTER).replace("/usr/local/bin/python3", LIVE_PYTHON), encoding="utf-8")
                provider.chmod(0o555)
                os.chmod(packet.runtime, 0o555)
                observed_roots.append(packet.projection)
                return packet

            backend = DockerQueueBackend(
                image=LIVE_IMAGE,
                python_executable=LIVE_PYTHON,
                docker_executable=docker,
                limits=DockerRuntimeLimits(memory_bytes=256 * 1024 * 1024, cpu_count=1.0, pids=64, nofile=256, scratch_bytes=16 * 1024 * 1024, scratch_inodes=2048, shm_bytes=4 * 1024 * 1024, shm_inodes=256),
            )
            try:
                with (
                    mock.patch("work_queue_driver.compile_hunter_view", side_effect=compile_with_test_provider),
                    mock.patch.dict(
                        os.environ,
                        {
                            **{key: "" for key in MODEL_AUTH_ENV_KEYS},
                            "ANTHROPIC_API_KEY": "fixture-parent-api-key",
                        },
                        clear=False,
                    ),
                ):
                    result = run_driver(
                        workspace=workspace,
                        engagement=engagement,
                        executable=Path("/harness/fake-claude"),
                        model=WORKER_MODEL,
                        reviewer_model=REVIEWER_MODEL,
                        budget=DriverBudget(1, 45.0, 30.0, None),
                        docker_backend=backend,
                        read_only_inputs=(route,),
                    )
            finally:
                self.assertEqual(_docker_owned_ids(docker, "container"), before_containers)
                self.assertEqual(_docker_owned_ids(docker, "network"), before_networks)
            attempts = read_ledger(engagement, "attempt")
            recorded = [row for row in attempts if row.get("attempt_id") == "attempt-docker-hunter-view"]
            self.assertEqual(len(recorded), 1, result)
            after_attempt = reduce_engagement(engagement)
            self.assertIn("hypothesis_ran_unadjudicated", {row["class"] for row in after_attempt["work_queue"]})
            adjudication = queue_command_payload("next", after_attempt, engagement)["item"]
            self.assertEqual(adjudication["next_action"]["action_id"], "record_hypothesis_disposition")
            self.assertEqual(adjudication["next_action"]["principal"], "orchestrator")
            attempt = recorded[0]
            self.assertEqual(attempt["kind"], "primary")
            self.assertEqual(attempt["hypothesis_ref"], "hypothesis-hunter")
            self.assertEqual(attempt["experiment_ref"], "event-hunter-hypothesis-running")
            self.assertEqual(attempt["provenance"]["cognitive_principal"], "hunter")
            self.assertEqual(attempt["provenance"]["view_type"], "hunter-current-v1")
            self.assertEqual(attempt["provenance"]["runtime_session_ref"], result["history"][0]["runtime"]["session_ref"])
            self.assertEqual(result["history"][0]["runtime"]["returncode"], 0)
            self.assertTrue(result["history"][0]["runtime"]["output_was_json"])
            self.assertEqual(result["history"][0]["admission_state_binding"]["source_hashes"], state["source_hashes"])
            self.assertEqual(validate_record(result, "work-queue-driver"), [])
            self.assertTrue(observed_roots)
            self.assertTrue(all(not path.exists() for path in observed_roots))
            self._adjudicate_and_activate_refuted_finding(
                root, workspace, engagement, "attempt-docker-hunter-view"
            )

    @unittest.skipUnless(
        LIVE_IMAGE,
        "set HARNESS_DOCKER_QUEUE_TEST_IMAGE to an already-cached immutable Python image",
    )
    def test_real_docker_reducer_drains_one_brokered_action_and_cleans_exactly(self) -> None:
        if sys.platform != "darwin":
            self.skipTest("the strong Docker runtime currently supports local Docker Desktop on Darwin")
        docker_text = shutil.which("docker")
        if docker_text is None:
            self.skipTest("Docker CLI unavailable")
        if not SSH_KEYGEN.is_file():
            self.skipTest("ssh-keygen unavailable for the host-prepared signed review")
        docker = Path(docker_text).resolve(strict=True)
        before_containers = _docker_owned_ids(docker, "container")
        before_networks = _docker_owned_ids(docker, "network")

        with tempfile.TemporaryDirectory(prefix="docker-work-queue-drain-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "target"
            engagement = workspace / "engagements" / "docker-queue"
            engagement.mkdir(parents=True)
            self._seed_current_signed_dry_review(root, workspace, engagement)

            before_state = reduce_engagement(engagement)
            payload = queue_command_payload("next", before_state, engagement)
            self.assertEqual(before_state["coverage"], "active")
            self.assertEqual(len(before_state["work_queue"]), 1)
            self.assertEqual(payload["queue"]["blocking_count"], 1)
            self.assertEqual(
                payload["item"]["next_action"]["action_id"],
                "record_coverage_dry",
            )

            fake_claude = workspace / "fake-claude"
            fake_claude.write_text(textwrap.dedent(FAKE_CLAUDE).replace("/usr/local/bin/python3", LIVE_PYTHON), encoding="utf-8")
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IXUSR)
            target_probe = workspace / ".docker-queue-target-write"
            harness_probe = ROOT / ".docker-queue-harness-write"
            self.assertFalse(target_probe.exists())
            self.assertFalse(harness_probe.exists())

            backend = DockerQueueBackend(
                image=LIVE_IMAGE,
                python_executable=LIVE_PYTHON,
                docker_executable=docker,
                limits=DockerRuntimeLimits(
                    memory_bytes=256 * 1024 * 1024,
                    cpu_count=1.0,
                    pids=64,
                    nofile=256,
                    scratch_bytes=16 * 1024 * 1024,
                    scratch_inodes=2048,
                    shm_bytes=4 * 1024 * 1024,
                    shm_inodes=256,
                ),
            )
            observed_specs: list[object] = []
            broker_traffic: list[str] = []
            original_prepare = queue_driver.prepare_docker_session
            original_docker_session = queue_driver._run_docker_queue_session

            def observed_prepare(spec: object) -> object:
                observed_specs.append(spec)
                return original_prepare(spec)  # type: ignore[arg-type]

            def interrupt_after_broker_commit(**arguments: object) -> object:
                execution = original_docker_session(**arguments)  # type: ignore[arg-type]
                return queue_driver._QueueSessionExecution(
                    session=execution.session,
                    interrupted=True,
                )

            class ObservedBroker(queue_driver.DriverActionBroker):
                def _authenticate_container_request(self, envelope: dict) -> tuple:
                    authenticated = super()._authenticate_container_request(envelope)
                    payload_value = envelope.get("payload")
                    if isinstance(payload_value, dict):
                        request_kind = payload_value.get("request_kind")
                        if isinstance(request_kind, str):
                            broker_traffic.append(request_kind)
                    return authenticated

            try:
                with (
                    mock.patch(
                        "work_queue_driver.prepare_docker_session",
                        side_effect=observed_prepare,
                    ),
                    mock.patch(
                        "work_queue_driver.DriverActionBroker", ObservedBroker
                    ),
                    mock.patch(
                        "work_queue_driver._run_docker_queue_session",
                        side_effect=interrupt_after_broker_commit,
                    ),
                    mock.patch.dict(
                        os.environ,
                        {
                            **{key: "" for key in MODEL_AUTH_ENV_KEYS},
                            "ANTHROPIC_API_KEY": "fixture-parent-api-key",
                        },
                        clear=False,
                    ),
                ):
                    result = run_driver(
                        workspace=workspace,
                        engagement=engagement,
                        executable=Path("/workspace/fake-claude"),
                        model=WORKER_MODEL,
                        reviewer_model=REVIEWER_MODEL,
                        budget=DriverBudget(1, 45.0, 30.0, None),
                        docker_backend=backend,
                    )
            finally:
                after_containers = _docker_owned_ids(docker, "container")
                after_networks = _docker_owned_ids(docker, "network")
                self.assertEqual(after_containers, before_containers)
                self.assertEqual(after_networks, before_networks)

            state = reduce_engagement(engagement)
            self.assertEqual(result["status"], "completed", result)
            self.assertTrue(result["completed"])
            self.assertEqual(result["sessions_started"], 1)
            self.assertEqual(result["queue"]["blocking_count"], 0)
            self.assertEqual(result["queue"]["total_count"], 0)
            self.assertEqual(len(result["history"]), 1)
            history = result["history"][0]
            self.assertEqual(history["action_id"], "record_coverage_dry")
            self.assertEqual(history["item_class"], "coverage_review_missing")
            self.assertEqual(history["runtime_model"], WORKER_MODEL)
            self.assertNotEqual(history["before_state_hash"], history["after_state_hash"])
            self.assertEqual(history["runtime"]["returncode"], 0)
            self.assertTrue(history["runtime"]["output_was_json"])
            self.assertFalse(history["runtime"]["runtime_reported_error"])
            self.assertEqual(history["runtime"]["cost_usd"], 0.01)
            self.assertEqual(state["coverage"], "coverage_dry")
            self.assertEqual(state["work_queue"], [])
            self.assertEqual(broker_traffic, ["action", "session_end_check"])
            self.assertEqual(len(observed_specs), 1)
            runtime_spec = observed_specs[0]
            self.assertEqual(runtime_spec.workspace, workspace)
            self.assertEqual(runtime_spec.harness, ROOT)
            self.assertEqual(runtime_spec.read_only_inputs, ())
            self.assertTrue(runtime_spec.supervisor_write_broker)

            events = read_ledger(engagement, "event")
            closure = [
                event for event in events if event.get("event_id") == COVERAGE_EVENT_ID
            ]
            self.assertEqual(len(closure), 1)
            self.assertEqual(
                closure[0]["payload"]["coverage_review_ref"], REVIEW_EVENT_ID
            )
            self.assertEqual(
                closure[0]["provenance"]["runtime_session_ref"],
                history["runtime"]["session_ref"],
            )
            self.assertEqual(closure[0]["provenance"]["model"], WORKER_MODEL)
            self.assertFalse(target_probe.exists())
            self.assertFalse(harness_probe.exists())
            self.assertEqual(validate_record(result, "work-queue-driver"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
