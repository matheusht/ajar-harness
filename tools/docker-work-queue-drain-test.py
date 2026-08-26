#!/usr/bin/env python3
"""Guarded real-Docker acceptance test for one reducer-owned queue drain.

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
    initialize_engagement,
    read_ledger,
    reduce_engagement,
)
from work_queue_actions import queue_command_payload
from work_queue_driver import DockerQueueBackend, DriverBudget, run_driver


ROOT = Path(__file__).resolve().parents[1]
LIVE_IMAGE = os.environ.get("HARNESS_DOCKER_QUEUE_TEST_IMAGE", "")
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
- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- Operator: operator-docker-queue-test
- Date: 2026-08-26
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


FAKE_CLAUDE = r'''#!/usr/local/bin/python3
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
            f"reviewer-docker-queue {public_parts[0]} {public_parts[1]}\n",
            encoding="utf-8",
        )
        engagement.joinpath("scope.md").write_text(
            SCOPE.format(
                reviewer_allowed_signers_hash=sha256_file(allowed_signers)
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
                python_executable="/usr/local/bin/python3",
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
            fake_claude.write_text(textwrap.dedent(FAKE_CLAUDE), encoding="utf-8")
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IXUSR)
            target_probe = workspace / ".docker-queue-target-write"
            harness_probe = ROOT / ".docker-queue-harness-write"
            self.assertFalse(target_probe.exists())
            self.assertFalse(harness_probe.exists())

            backend = DockerQueueBackend(
                image=LIVE_IMAGE,
                python_executable="/usr/local/bin/python3",
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
                        {key: "" for key in MODEL_AUTH_ENV_KEYS},
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
