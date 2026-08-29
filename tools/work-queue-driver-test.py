#!/usr/bin/env python3
"""Direct contract tests for the external work-queue driver."""

from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import driver_action_admission as admission_module

from corpus_enumeration import CAVEAT, COLUMNS

from engagement_records import (
    RecordError,
    build_reference_index,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_record,
)
from decision6_capabilities import classify_command, classify_event
from driver_action_admission import (
    DriverActionBroker,
    _MODEL_JSON_LIMIT,
    _REVIEW_ALLOWED_SIGNERS_LIMIT,
    _REVIEW_SIGNATURE_LIMIT,
    _neutral_tail_is_allowed,
    _read_regular_bytes,
    _read_regular_json_bytes,
    _run_engagement_module,
)
from engagement_state import (
    _append_kernel_event,
    _open_absolute_directory,
    _register_legacy_artifact,
    append_event,
    base_event,
    blocking_work_identities,
    compute_review_input_hash,
    initialize_engagement,
    reduce_engagement,
)
from work_queue_driver import (
    DriverBudget,
    DriverError,
    ROOT,
    _reduce,
    _result,
    _select_reviewer_model,
    _state_stop,
    _validate_action_binding,
    bind_run,
    record_budget_boundary,
    run_driver,
)


SCOPE = """# Scope — work queue driver fixture

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic driver test.
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
- Reviewer allowed signers SHA256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
## Authorization
- Frozen corpus enumeration SHA256: `none`
- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- Operator: operator-driver-test
- Date: 2026-08-24
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""

DARWIN_SESSION_INTEGRATION = (
    sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()
)
DARWIN_SESSION_SKIP = (
    "unsupported Darwin sandbox-exec work-session integration; not exercised"
)
PEER_CREDENTIAL_INTEGRATION = hasattr(socket, "SO_PEERCRED") or sys.platform == "darwin"
PEER_CREDENTIAL_SKIP = "AF_UNIX peer PID credential API unavailable; not exercised"


FIXTURE_RUNTIME_BODY = r'''import copy
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile

prompt = json.loads(sys.argv[-1])
action = prompt["item"]["next_action"]
action_id = action["action_id"]
runtime_model = sys.argv[sys.argv.index("--model") + 1]
argv = list(action["local_invocation"]["argv"])
tool_dir = pathlib.Path(argv[1]).parent
sys.path.insert(0, str(tool_dir))

from engagement_records import build_reference_index, canonical_json_bytes  # noqa: E402
from engagement_state import (  # noqa: E402
    base_event,
    compute_review_input_hash,
    reduce_engagement,
    utc_now,
)

engagement = pathlib.Path(os.environ["HARNESS_ACTIVE_ENGAGEMENT"])
workspace = engagement.parent.parent
scratch = pathlib.Path(os.environ["HARNESS_DRIVER_SCRATCH"])
state = reduce_engagement(engagement)
uid = os.getuid()
sid = os.getsid(0)
broker_id = f"local-uid-{uid}:broker"
broker_session = f"session-posix-{uid}-{sid}"
substitutions = {}
attack = {
    "pure_reduce_succeeded": state.get("engagement_id") == engagement.name,
    "action_token_absent": "HARNESS_EXPECTED_ACTION_TOKEN" not in os.environ,
    "token_name_absent_from_prompt": "HARNESS_EXPECTED_ACTION_TOKEN" not in sys.argv[-1],
    "token_name_absent_from_argv": all("HARNESS_EXPECTED_ACTION_TOKEN" not in value for value in sys.argv),
    "broker_endpoint": os.environ.get("HARNESS_DRIVER_ACTION_BROKER"),
    "scratch": os.environ.get("HARNESS_DRIVER_SCRATCH"),
}
write_probes = {
    "raw_target_write_denied": engagement / ".model-raw-write",
    "raw_harness_write_denied": tool_dir / ".model-harness-write",
    "raw_outside_write_denied": workspace.parent / ".model-outside-write",
}
for key, path in write_probes.items():
    try:
        path.write_text("forbidden", encoding="utf-8")
    except OSError:
        attack[key] = True
    else:
        attack[key] = False
scratch_probe = scratch / ".model-scratch-write"
scratch_probe.write_text("allowed", encoding="utf-8")
attack["scratch_write_allowed"] = scratch_probe.read_text(encoding="utf-8") == "allowed"

if action_id == "record_cold_coverage_review":
    review_id = "review-driver-cold-coverage"
    reviewer_id = "reviewer-driver-fixture"
    recorded_at = utc_now()
    review = {
        "schema_version": 1,
        "review_id": review_id,
        "engagement_id": state["engagement_id"],
        "review_type": "coverage",
        "proposed_finding_id": None,
        "recorded_at": recorded_at,
        "entity_ref": state["engagement_id"],
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
            "reviewer_id": reviewer_id,
            "reviewer_run_id": "run-driver-cold-coverage",
            "reviewer_session_id": os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"],
            "reviewer_model": runtime_model,
            "fresh_context": True,
            "prior_verdict_visible": False,
            "disconfirming_objective": "Find any omitted branch in the declared empty fixture space.",
            "originating_run_id": "event-driver-review-origin",
        },
        "bounded_space": "The fixture declares no hypotheses or live target surfaces.",
        "hypothesis_dispositions": [],
        "omitted_branch_challenge": "No branch exists outside the empty synthetic fixture space.",
        "residual_uncertainty": [],
    }
    review["input_hash"] = compute_review_input_hash(
        engagement,
        review,
        build_reference_index(engagement),
    )
    review_path = scratch / ".driver-fixture-review.json"
    review_path.write_bytes(canonical_json_bytes(review))
    subprocess.run(
        [
            "/usr/bin/ssh-keygen",
            "-q",
            "-Y",
            "sign",
            "-f",
            str(workspace / ".driver-fixture-reviewer-key"),
            "-n",
            "llm-redteam-harness-review-v1",
            str(review_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    event = base_event(
        event_id="event-driver-cold-coverage",
        engagement_id=state["engagement_id"],
        recorded_at=utc_now(),
        actor_role="broker",
        actor_id=broker_id,
        event_type="review.coverage_completed",
        rationale="Record the fixture's independent cold coverage review.",
        payload={
            "review_type": "coverage",
            "verdict": "coverage_dry",
            "review_ref": review_id,
            "reviewer_id": reviewer_id,
        },
        review_refs=[review_id],
        session_id=broker_session,
        operation_class="notebook",
    )
    event_path = scratch / ".driver-fixture-review-event.json"
    event_path.write_bytes(canonical_json_bytes(event))
    substitutions = {
        "<review-json>": str(review_path),
        "<review-event-json>": str(event_path),
        "<broker-id>": broker_id,
        "<broker-session-id>": broker_session,
        "<review-signature>": str(review_path) + ".sig",
        "<reviewer-allowed-signers>": str(workspace / ".driver-fixture-allowed-signers"),
    }
elif action_id == "record_coverage_dry":
    latest = state["latest_coverage_review"]
    event = base_event(
        event_id="event-driver-coverage-dry",
        engagement_id=state["engagement_id"],
        recorded_at=utc_now(),
        actor_role="broker",
        actor_id=broker_id,
        event_type="coverage.status_changed",
        rationale="Close the fixture from its exact current cold review.",
        payload={
            "entity_id": state["engagement_id"],
            "status": "coverage_dry",
            "coverage_review_ref": latest["event_ref"],
        },
        entity_refs=[latest["event_ref"]],
        state_changes=[{
            "dimension": "coverage",
            "entity_id": state["engagement_id"],
            "previous": "active",
            "current": "coverage_dry",
        }],
        session_id=broker_session,
        operation_class="notebook",
    )
    event_path = scratch / ".driver-fixture-coverage-event.json"
    event_path.write_bytes(canonical_json_bytes(event))
    substitutions = {"<coverage-status-event-json>": str(event_path)}
else:
    raise SystemExit(90)

argv = [substitutions.get(value, value) for value in argv]
if action_id == "record_cold_coverage_review":
    nonselected = [
        argv[0], argv[1], "append-event", "--engagement", str(engagement),
        "--file", str(event_path),
    ]
    nonselected_result = subprocess.run(
        nonselected,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    attack["nonselected_command_denied"] = nonselected_result.returncode != 0

    unscoped_env = dict(os.environ)
    unscoped_env.pop("HARNESS_DRIVER_ACTION_BROKER", None)
    unset_named = subprocess.run(
        nonselected,
        env=unscoped_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    engagement_fd = os.open(engagement, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        unset_fd = subprocess.run(
            [
                argv[0], argv[1], "append-event", "--engagement",
                f"/dev/fd/{engagement_fd}", "--file", str(event_path),
            ],
            env=unscoped_env,
            pass_fds=(engagement_fd,),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        os.close(engagement_fd)
    attack["unset_endpoint_named_denied"] = unset_named.returncode != 0
    attack["unset_endpoint_fd_denied"] = unset_fd.returncode != 0

    original_endpoint = os.environ["HARNESS_DRIVER_ACTION_BROKER"]
    os.environ["HARNESS_DRIVER_ACTION_BROKER"] = str(scratch / "forged-broker.sock")
    forged_endpoint = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    os.environ["HARNESS_DRIVER_ACTION_BROKER"] = original_endpoint
    attack["forged_endpoint_denied"] = forged_endpoint.returncode != 0

    wrong_review = copy.deepcopy(review)
    wrong_review["independence"]["reviewer_session_id"] = "forged-reviewer-session"
    wrong_review["independence"]["reviewer_model"] = "claude-forged-reviewer-20260824"
    wrong_review_path = scratch / ".driver-fixture-wrong-review.json"
    wrong_review_path.write_bytes(canonical_json_bytes(wrong_review))
    subprocess.run(
        [
            "/usr/bin/ssh-keygen", "-q", "-Y", "sign", "-f",
            str(workspace / ".driver-fixture-reviewer-key"), "-n",
            "llm-redteam-harness-review-v1", str(wrong_review_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wrong_argv = [
        str(wrong_review_path) if value == str(review_path)
        else str(wrong_review_path) + ".sig" if value == str(review_path) + ".sig"
        else value
        for value in argv
    ]
    wrong_result = subprocess.run(
        wrong_argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    attack["signed_runtime_rewrite_denied"] = wrong_result.returncode != 0
result = subprocess.run(
    argv,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if result.returncode != 0:
    raise SystemExit(result.returncode)
if action_id == "record_cold_coverage_review":
    ledger_after_success = (engagement / "events.jsonl").read_bytes()
    sidecar = engagement / ".work-queue-action-admission.json"
    try:
        sidecar.write_text(json.dumps({
            "status": "armed", "action_id": "forged", "state_hash": "forged",
            "runtime_model": "forged", "runtime_session_ref": "forged",
        }), encoding="utf-8")
    except OSError:
        attack["sidecar_rewrite_denied"] = True
    else:
        attack["sidecar_rewrite_denied"] = False
    registry = pathlib.Path(tempfile.gettempdir()) / f"llm-redteam-harness-driver-{uid}" / f"session-{sid}.json"
    try:
        registry.write_text(json.dumps({
            "status": "armed", "action_id": "forged", "state_hash": "forged",
            "runtime_session_ref": "forged", "runtime_model": "forged",
        }), encoding="utf-8")
    except OSError:
        attack["registry_rewrite_denied"] = True
    else:
        attack["registry_rewrite_denied"] = False
    original_session = os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"]
    os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"] = "forged-runtime-session"
    forged_scope = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"] = original_session
    second_exact = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    attack["forged_runtime_scope_denied"] = forged_scope.returncode != 0
    attack["second_exact_denied"] = second_exact.returncode != 0
    attack["no_second_ledger_mutation"] = (engagement / "events.jsonl").read_bytes() == ledger_after_success
    required = {
        "pure_reduce_succeeded", "action_token_absent", "token_name_absent_from_prompt",
        "token_name_absent_from_argv", "raw_target_write_denied", "raw_harness_write_denied",
        "raw_outside_write_denied", "scratch_write_allowed", "nonselected_command_denied",
        "unset_endpoint_named_denied", "unset_endpoint_fd_denied", "forged_endpoint_denied",
        "signed_runtime_rewrite_denied", "sidecar_rewrite_denied", "registry_rewrite_denied",
        "forged_runtime_scope_denied", "second_exact_denied", "no_second_ledger_mutation",
    }
    if not all(attack.get(key) is True for key in required):
        raise SystemExit(91)
settings = json.loads(sys.argv[sys.argv.index("--settings") + 1])
hook_command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
before_hook = reduce_engagement(engagement)
hook_result = subprocess.run(
    shlex.split(hook_command),
    input=canonical_json_bytes({
        "session_id": os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"],
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
after_hook = reduce_engagement(engagement)
try:
    hook_output = json.loads(hook_result.stdout)
except json.JSONDecodeError:
    raise SystemExit(92)
if action_id == "record_cold_coverage_review":
    events = (engagement / "events.jsonl").read_text(encoding="utf-8").splitlines()
    last_event = json.loads(events[-1])
    if not (
        hook_result.returncode == 0
        and after_hook["event_count"] == before_hook["event_count"] + 1
        and last_event.get("event_type") == "session.end_checked"
        and last_event.get("provenance", {}).get("runtime_session_ref")
        == os.environ["HARNESS_EXPECTED_RUNTIME_SESSION_REF"]
        and set(hook_output) == {"systemMessage"}
    ):
        raise SystemExit(93)
elif not (
    hook_result.returncode == 0
    and after_hook["event_count"] == before_hook["event_count"]
    and hook_output == {}
):
    raise SystemExit(94)
print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01}))
'''


def _corpus_freeze_documents(row_count: int) -> tuple[bytes, bytes]:
    """Build the exact TSV and manifest bytes committed by the signed scope."""

    rows = [
        [
            "enumerated",
            "fixture",
            "1.0.0",
            "a" * 40,
            f"entry-{index}.js",
            "declared",
            f"{index + 1:064x}",
        ]
        for index in range(row_count)
    ]
    tsv_bytes = (
        "\n".join([CAVEAT, "\t".join(COLUMNS), *("\t".join(row) for row in rows)])
        + "\n"
    ).encode("utf-8")
    linked = {
        "path": "corpus-enumeration.tsv",
        "sha256": sha256_bytes(tsv_bytes).removeprefix("sha256:"),
    }
    manifest = {
        "schema_version": 1,
        "artifact_type": "corpus-enumeration",
        "frozen_at": "2026-08-24T11:59:59Z",
        "generated_by": {
            "tool": "tools/corpus_enumeration.py",
            "tool_sha256": "4" * 64,
            "mode": "syntactic",
            "model_involvement": False,
            "parser_versions": {
                "tree-sitter": "test",
                "tree-sitter-javascript": "test",
                "tree-sitter-typescript": "test",
            },
        },
        "granularity": ["package", "entrypoint"],
        "columns": COLUMNS,
        "coverage_semantics": {
            "closes_on": "visitation",
            "does_not_establish": "understanding",
            "necessary_for_coverage": True,
            "sufficient_for_coverage": False,
        },
        "artifact": {**linked, "row_count": row_count, "package_count": 1},
        "source": {"pins_path": "package-pins.tsv", "tarballs_path": "tarballs"},
        "frozen_inputs_base": "manifest",
        "frozen_inputs": {
            "corpus-enumeration": linked,
            "package-pins": {"path": "package-pins.tsv", "sha256": "5" * 64},
            "enumerator": {
                "path": "../../tools/corpus_enumeration.py",
                "sha256": "4" * 64,
            },
            "schema": {
                "path": "../../schemas/corpus-enumeration.schema.json",
                "sha256": "6" * 64,
            },
            "tarball:0000": {"path": "tarballs/fixture.tgz", "sha256": "7" * 64},
        },
    }
    return tsv_bytes, canonical_json_bytes(manifest)


class WorkQueueDriverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="work-queue-driver-test-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "target"
        self.engagement = self.workspace / "engagements" / "fixture"
        self.engagement.mkdir(parents=True)
        self.corpus_documents = _corpus_freeze_documents(3)
        corpus_pin = sha256_bytes(self.corpus_documents[1])
        scope = SCOPE.replace(
            "- Frozen corpus enumeration SHA256: `none`",
            f"- Frozen corpus enumeration SHA256: `{corpus_pin}`",
        )
        (self.engagement / "scope.md").write_text(scope, encoding="utf-8")
        initialize_engagement(self.engagement, "2026-08-24T12:00:00Z")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _new_corpus_fixture(
        self, row_count: int, suffix: str
    ) -> tuple[Path, Path, tuple[bytes, bytes]]:
        """Create an engagement whose genesis scope pins the requested frozen corpus."""

        workspace = self.root / f"target-{suffix}"
        engagement = workspace / "engagements" / f"fixture-{suffix}"
        engagement.mkdir(parents=True)
        documents = _corpus_freeze_documents(row_count)
        scope = SCOPE.replace(
            "- Frozen corpus enumeration SHA256: `none`",
            f"- Frozen corpus enumeration SHA256: `{sha256_bytes(documents[1])}`",
        )
        engagement.joinpath("scope.md").write_text(scope, encoding="utf-8")
        initialize_engagement(engagement, "2026-08-24T12:00:00Z")
        return workspace, engagement, documents

    def _register_corpus_freeze(
        self,
        row_count: int = 3,
        *,
        engagement: Path | None = None,
        documents: tuple[bytes, bytes] | None = None,
    ) -> str:
        """Register a small, exact denominator for driver boundary tests."""

        target = engagement or self.engagement
        if documents is None:
            if row_count != 3:
                raise ValueError("the default driver fixture scope pins the three-row corpus")
            documents = self.corpus_documents
        tsv_bytes, manifest_bytes = documents
        evidence = target / "evidence"
        tsv_path = evidence / "corpus-enumeration.tsv"
        tsv_path.write_bytes(tsv_bytes)
        common = {
            "schema_version": 1,
            "engagement_id": target.name,
            "created_at": "2026-08-24T12:00:00Z",
            "producer": {"role": "operator", "id": "operator-driver-test"},
            "acquisition_method": "generated_local",
            "target_refs": [],
            "environment_ref": None,
            "sensitivity": "internal",
            "redaction_status": "not_needed",
            "contains_executable_capability": False,
            "advisory_zone": "clear_local",
            "escalation_confirmation_event_ref": None,
            "cleanup_obligation_ref": None,
            "supersedes_artifact_id": None,
        }
        tsv_ref = "artifact-driver-corpus-tsv"
        _register_legacy_artifact(
            target,
            tsv_path,
            {**common, "artifact_id": tsv_ref, "media_type": "text/tab-separated-values"},
        )
        manifest_path = evidence / "corpus-enumeration.freeze.json"
        manifest_path.write_bytes(manifest_bytes)
        manifest_ref = "artifact-driver-corpus-manifest"
        _register_legacy_artifact(
            target,
            manifest_path,
            {**common, "artifact_id": manifest_ref, "media_type": "application/json"},
        )
        return manifest_ref

    def _coverage_review_fixture(self) -> tuple[Path, Path, Path]:
        engagement = self.root / "coverage-target" / "engagements" / "coverage-fixture"
        engagement.mkdir(parents=True)
        reviewer_key = self.root / "coverage-reviewer-ed25519"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(reviewer_key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        public_parts = reviewer_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        allowed_signers = self.root / "coverage-reviewer-allowed-signers"
        allowed_signers.write_text(
            f"reviewer-driver-fixture {public_parts[0]} {public_parts[1]}\n",
            encoding="utf-8",
        )
        engagement.joinpath("scope.md").write_text(
            SCOPE.replace(
                "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                sha256_file(allowed_signers),
            ),
            encoding="utf-8",
        )
        initialize_engagement(engagement, "2026-08-24T12:00:00Z")
        _append_kernel_event(
            engagement,
            base_event(
                event_id="event-coverage-review-origin",
                engagement_id=engagement.name,
                recorded_at="2026-08-24T12:00:01Z",
                actor_role="orchestrator",
                actor_id="orchestrator-coverage-fixture",
                event_type="observation.recorded",
                rationale="Establish the bounded synthetic search a cold reviewer challenges.",
                payload={
                    "entity_id": "observation-coverage-origin",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-coverage-origin",
                operation_class="notebook",
                model="fixture-origin-model",
            ),
        )
        return engagement, reviewer_key, allowed_signers

    def _record_blocked_coverage_review(
        self,
        engagement: Path,
        reviewer_key: Path,
        allowed_signers: Path,
        suffix: str,
        recorded_at: str,
        event_at: str,
    ) -> str:
        reviewer_id = "reviewer-driver-fixture"
        review_id = f"review-coverage-blocked-{suffix}"
        review = {
            "schema_version": 1,
            "review_id": review_id,
            "engagement_id": engagement.name,
            "review_type": "coverage",
            "proposed_finding_id": None,
            "recorded_at": recorded_at,
            "entity_ref": engagement.name,
            "finding_revision": None,
            "input_refs": [],
            "input_hash": "sha256:" + "0" * 64,
            "evidence_refs": [],
            "rationale": "The cold reviewer cannot close coverage because the bounded fixture is blocked.",
            "conflicting_evidence": [],
            "verdict": "blocked",
            "corrections": [],
            "required_next_actions": ["Operator resolves the fixture blocker before another review."],
            "independence": {
                "reviewer_id": reviewer_id,
                "reviewer_run_id": f"run-coverage-blocked-{suffix}",
                "reviewer_session_id": f"session-coverage-reviewer-{suffix}",
                "reviewer_model": "fixture-independent-reviewer",
                "fresh_context": True,
                "prior_verdict_visible": False,
                "disconfirming_objective": "Find a safe path that clears the declared fixture blocker.",
                "originating_run_id": "event-coverage-review-origin",
            },
            "bounded_space": "The local empty fixture and its declared blocker.",
            "hypothesis_dispositions": [],
            "omitted_branch_challenge": "No undeclared target branch is available in the local fixture.",
            "residual_uncertainty": ["The operator-owned blocker remains unresolved."],
        }
        review["input_hash"] = compute_review_input_hash(
            engagement,
            review,
            build_reference_index(engagement),
        )
        review_path = self.root / f"{review_id}.json"
        review_path.write_bytes(canonical_json_bytes(review))
        subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-q",
                "-Y",
                "sign",
                "-f",
                str(reviewer_key),
                "-n",
                "llm-redteam-harness-review-v1",
                str(review_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        uid = os.getuid()
        sid = os.getsid(0)
        event_id = f"event-coverage-blocked-review-{suffix}"
        event_path = self.root / f"{event_id}.json"
        event_path.write_bytes(
            canonical_json_bytes(
                base_event(
                    event_id=event_id,
                    engagement_id=engagement.name,
                    recorded_at=event_at,
                    actor_role="broker",
                    actor_id=f"local-uid-{uid}:broker",
                    event_type="review.coverage_completed",
                    rationale="Record the fixture's fresh signed blocked coverage review.",
                    payload={
                        "review_type": "coverage",
                        "verdict": "blocked",
                        "review_ref": review_id,
                        "reviewer_id": reviewer_id,
                    },
                    review_refs=[review_id],
                    session_id=f"session-posix-{uid}-{sid}",
                    operation_class="notebook",
                )
            )
        )
        process = subprocess.run(
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
                f"local-uid-{uid}:broker",
                "--session-id",
                f"session-posix-{uid}-{sid}",
                "--signature",
                str(review_path) + ".sig",
                "--allowed-signers",
                str(allowed_signers),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return event_id

    @staticmethod
    def _coverage_blocked_event(engagement: Path, review_ref: str, event_id: str) -> dict[str, object]:
        return base_event(
            event_id=event_id,
            engagement_id=engagement.name,
            recorded_at="2026-08-24T12:05:00Z",
            actor_role="operator",
            actor_id="operator-driver-test",
            event_type="coverage.status_changed",
            rationale="Record the operator-visible blocked coverage state from the exact cold review.",
            payload={
                "entity_id": engagement.name,
                "status": "blocked",
                "coverage_review_ref": review_ref,
            },
            entity_refs=[review_ref],
            state_changes=[
                {
                    "dimension": "coverage",
                    "entity_id": engagement.name,
                    "previous": "active",
                    "current": "blocked",
                }
            ],
        )

    def test_budget_boundary_is_atomic_typed_noncompletion(self) -> None:
        budget = DriverBudget(1, 60.0, 10.0, None)
        manifest_ref = self._register_corpus_freeze(row_count=3)
        before_events = self.engagement.joinpath("events.jsonl").read_bytes()
        with bind_run(self.workspace, self.engagement) as bound:
            refused_status, refused_state = record_budget_boundary(
                bound=bound,
                run_ref="driver-budget-missing-freeze-test",
                budget_kind="max_sessions",
                budget=budget,
                sessions_started=1,
                elapsed_seconds=0.5,
                seen_item_refs=set(),
            )
            after_refusal = self.engagement.joinpath("events.jsonl").read_bytes()
            status, state = record_budget_boundary(
                bound=bound,
                run_ref="driver-budget-test",
                budget_kind="max_sessions",
                budget=budget,
                sessions_started=1,
                elapsed_seconds=0.5,
                seen_item_refs=set(),
                corpus_enumeration_ref=manifest_ref,
            )
            result = _result(
                run_ref="driver-budget-test",
                status=status,
                budget_kind="max_sessions",
                budget=budget,
                sessions_started=1,
                started_at=time.monotonic(),
                state=state,
                seen_item_refs=set(),
                history=[],
                model="claude-fixture-worker-20260825",
                reviewer_pool=("claude-fixture-reviewer-20260824",),
            )

        event = json.loads((self.engagement / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(refused_status, "operator_required")
        self.assertEqual(refused_state["coverage"], "active")
        self.assertEqual(after_refusal, before_events)
        self.assertEqual(status, "budget_spent")
        self.assertEqual(state["coverage"], "budget_bounded")
        self.assertEqual(state["coverage_counts"]["disposed_count"], 0)
        self.assertEqual(state["coverage_counts"]["enumerated_count"], 3)
        self.assertEqual(state["coverage_counts"]["corpus_enumeration_ref"], manifest_ref)
        self.assertEqual(
            state["coverage_counts"]["enumeration_artifact_ref"],
            "artifact-driver-corpus-tsv",
        )
        self.assertEqual(event["payload"]["driver_run_ref"], "driver-budget-test")
        self.assertEqual(event["payload"]["budget_kind"], "max_sessions")
        self.assertEqual(event["payload"]["enumerated_count"], 3)
        self.assertEqual(event["payload"]["sessions_started"], 1)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    def test_budget_boundary_never_counts_queue_dispositions_as_corpus_visits(self) -> None:
        workspace, engagement, documents = self._new_corpus_fixture(1, "one-row")
        manifest_ref = self._register_corpus_freeze(
            row_count=1,
            engagement=engagement,
            documents=documents,
        )
        # These identities represent queue progress only. There are deliberately more of them
        # than rows in the frozen corpus, so copying their count into coverage would mix units.
        seen_item_refs = {"sha256:" + "1" * 64, "sha256:" + "2" * 64}
        budget = DriverBudget(1, 60.0, 10.0, None)

        with bind_run(workspace, engagement) as bound:
            status, state = record_budget_boundary(
                bound=bound,
                run_ref="driver-budget-unit-separation-test",
                budget_kind="max_sessions",
                budget=budget,
                sessions_started=1,
                elapsed_seconds=0.5,
                seen_item_refs=seen_item_refs,
                corpus_enumeration_ref=manifest_ref,
            )
            result = _result(
                run_ref="driver-budget-unit-separation-test",
                status=status,
                budget_kind="max_sessions",
                budget=budget,
                sessions_started=1,
                started_at=time.monotonic(),
                state=state,
                seen_item_refs=seen_item_refs,
                history=[],
                model="claude-fixture-worker-20260825",
                reviewer_pool=("claude-fixture-reviewer-20260824",),
            )

        event = json.loads(
            engagement.joinpath("events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[-1]
        )
        self.assertEqual(status, "budget_spent")
        self.assertEqual(event["payload"]["enumerated_count"], 1)
        self.assertEqual(event["payload"]["disposed_count"], 0)
        self.assertEqual(state["coverage_counts"]["disposed_count"], 0)
        self.assertGreaterEqual(result["queue"]["disposed_count"], 2)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    def test_completed_result_reports_post_admission_wall_overrun(self) -> None:
        state = reduce_engagement(self.engagement)
        state["coverage"] = "coverage_dry"
        state["work_queue"] = []
        budget = DriverBudget(1, 0.01, 0.01, None)
        result = _result(
            run_ref="driver-completed-overrun-test",
            status="completed",
            budget_kind=None,
            budget=budget,
            sessions_started=1,
            started_at=time.monotonic() - 1.0,
            state=state,
            seen_item_refs=set(),
            history=[],
            model="claude-fixture-worker-20260825",
            reviewer_pool=("claude-fixture-reviewer-20260824",),
        )

        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["budget_kind"])
        self.assertGreater(result["wall_seconds"], budget.max_wall_seconds)
        self.assertGreater(result["wall_deadline_overrun_seconds"], 0)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    def test_decision6_matrix_closes_driver_and_terminal_block_capabilities(self) -> None:
        driver = classify_command("run-work-queue")
        self.assertEqual(driver["tier"], "notebook")
        self.assertEqual(driver["allowed_roles"], ["broker"])
        self.assertEqual(driver["blocking_scope"], "none")
        self.assertEqual(
            driver["required_evidence"],
            ["target_local_workspace", "reducer_owned_single_action", "external_budget"],
        )
        terminal_block = classify_event("engagement.blocked", {})
        self.assertEqual(terminal_block["tier"], "authority")
        self.assertEqual(terminal_block["allowed_roles"], ["operator"])
        self.assertEqual(terminal_block["blocking_scope"], "global")

    def test_generic_append_event_cannot_set_driver_loop_boundary(self) -> None:
        state = reduce_engagement(self.engagement)
        event = base_event(
            event_id="event-forged-budget-boundary",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T12:01:00Z",
            actor_role="broker",
            actor_id=f"local-uid-{os.getuid()}:broker",
            event_type="coverage.status_changed",
            rationale="A model-authored generic event must not set the driver boundary.",
            payload={
                "entity_id": state["engagement_id"],
                "status": "budget_bounded",
                "disposed_count": 0,
                "enumerated_count": 1,
            },
            state_changes=[
                {
                    "dimension": "coverage",
                    "entity_id": state["engagement_id"],
                    "previous": "active",
                    "current": "budget_bounded",
                }
            ],
            session_id=f"session-posix-{os.getuid()}-{os.getsid(0)}",
            operation_class="notebook",
        )
        with self.assertRaises(RecordError) as public_raised:
            append_event(self.engagement, event)
        self.assertEqual(public_raised.exception.code, "external_driver_budget_boundary_required")
        event_path = self.root / "forged-budget.json"
        event_path.write_bytes(canonical_json_bytes(event))
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "run-engagement.py"),
                "append-event",
                "--engagement",
                str(self.engagement),
                "--file",
                str(event_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)["error"]["code"], "external_driver_budget_boundary_required")
        self.assertEqual(reduce_engagement(self.engagement)["coverage"], "active")

    def test_coverage_blocked_rejects_an_arbitrary_existing_event_reference(self) -> None:
        initial_event_ref = json.loads(
            self.engagement.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )["event_id"]
        with self.assertRaises(RecordError) as raised:
            _append_kernel_event(
                self.engagement,
                self._coverage_blocked_event(
                    self.engagement,
                    initial_event_ref,
                    "event-coverage-blocked-arbitrary-ref",
                ),
            )
        self.assertEqual(raised.exception.code, "coverage_blocked_without_cold_review")
        self.assertEqual(reduce_engagement(self.engagement)["coverage"], "active")

    def test_coverage_blocked_requires_the_exact_current_signed_review(self) -> None:
        engagement, reviewer_key, allowed_signers = self._coverage_review_fixture()
        stale_ref = self._record_blocked_coverage_review(
            engagement,
            reviewer_key,
            allowed_signers,
            "stale",
            "2026-08-24T12:01:00Z",
            "2026-08-24T12:01:01Z",
        )
        current_ref = self._record_blocked_coverage_review(
            engagement,
            reviewer_key,
            allowed_signers,
            "current",
            "2026-08-24T12:02:00Z",
            "2026-08-24T12:02:01Z",
        )

        with self.assertRaises(RecordError) as stale_raised:
            _append_kernel_event(
                engagement,
                self._coverage_blocked_event(
                    engagement,
                    stale_ref,
                    "event-coverage-blocked-stale-review",
                ),
            )
        self.assertEqual(stale_raised.exception.code, "coverage_review_not_current")
        self.assertEqual(reduce_engagement(engagement)["coverage"], "active")

        _append_kernel_event(
            engagement,
            self._coverage_blocked_event(
                engagement,
                current_ref,
                "event-coverage-blocked-current-review",
            ),
        )
        self.assertEqual(reduce_engagement(engagement)["coverage"], "blocked")

    def test_broker_cannot_end_the_driver_with_engagement_blocked(self) -> None:
        state = reduce_engagement(self.engagement)
        forged = base_event(
            event_id="event-forged-broker-engagement-blocked",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T12:01:00Z",
            actor_role="broker",
            actor_id=f"local-uid-{os.getuid()}:broker",
            event_type="engagement.blocked",
            rationale="A broker-authored terminal escape must fail before changing reducer state.",
            payload={
                "entity_id": state["engagement_id"],
                "status": "blocked",
                "reason": "A broker-authored terminal escape must fail before changing reducer state.",
            },
            state_changes=[
                {
                    "dimension": "engagement",
                    "entity_id": state["engagement_id"],
                    "previous": "active",
                    "current": "blocked",
                },
                {
                    "dimension": "coverage",
                    "entity_id": state["engagement_id"],
                    "previous": "active",
                    "current": "blocked",
                },
            ],
            session_id=f"session-posix-{os.getuid()}-{os.getsid(0)}",
            operation_class="authority",
        )
        with self.assertRaises(RecordError) as raised:
            _append_kernel_event(self.engagement, forged)
        self.assertEqual(raised.exception.code, "engagement_block_not_operator")
        self.assertEqual(reduce_engagement(self.engagement)["coverage"], "active")

    def test_driver_budget_metadata_is_reserved_to_budget_event(self) -> None:
        state = reduce_engagement(self.engagement)
        forged = base_event(
            event_id="event-forged-driver-metadata",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T12:01:00Z",
            actor_role="orchestrator",
            actor_id="orchestrator-driver-test",
            event_type="observation.recorded",
            rationale="Driver metadata cannot decorate an unrelated notebook event.",
            payload={
                "entity_id": "observation-forged-driver-metadata",
                "entity_type": "observation",
                "status": "recorded",
                "driver_run_ref": "driver-forged",
            },
            session_id="session-driver-test",
            operation_class="notebook",
        )
        with self.assertRaises(RecordError) as raised:
            _append_kernel_event(self.engagement, forged)
        self.assertEqual(raised.exception.code, "driver_budget_metadata_wrong_event")

    def test_operator_park_wins_before_budget_boundary(self) -> None:
        state = reduce_engagement(self.engagement)
        _append_kernel_event(
            self.engagement,
            base_event(
                event_id="event-driver-test-park",
                engagement_id=state["engagement_id"],
                recorded_at="2026-08-24T12:01:00Z",
                actor_role="operator",
                actor_id="operator-driver-test",
                event_type="operator_stop.recorded",
                rationale="Operator parks the fixture queue.",
                payload={
                    "entity_id": state["engagement_id"],
                    "status": "parked",
                    "reason": "Operator parks the fixture queue.",
                    "operator_id": "operator-driver-test",
                },
                state_changes=[
                    {
                        "dimension": "queue",
                        "entity_id": state["engagement_id"],
                        "previous": "active",
                        "current": "parked",
                    }
                ],
                session_id="session-operator-driver-test",
                operation_class="authority",
            ),
        )
        with bind_run(self.workspace, self.engagement) as bound:
            status, after = record_budget_boundary(
                bound=bound,
                run_ref="driver-park-test",
                budget_kind="max_sessions",
                budget=DriverBudget(1, 60.0, 10.0, None),
                sessions_started=1,
                elapsed_seconds=1.0,
                seen_item_refs=set(),
            )
        self.assertEqual(status, "operator_parked")
        self.assertEqual(after["coverage"], "active")
        self.assertEqual(after["queue_control"]["status"], "parked")
        result = run_driver(
            workspace=self.workspace,
            engagement=self.engagement,
            executable=Path("/not-reached"),
            model="claude-fixture-worker-20260825",
            reviewer_model=[
                "claude-fixture-reviewer-20260824",
                "claude-fixture-reviewer-two-20260824",
            ],
            budget=DriverBudget(1, 60.0, 10.0, None),
        )
        self.assertEqual(result["status"], "operator_parked")
        self.assertEqual(result["sessions_started"], 0)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    def test_operator_only_queue_pauses_without_launching(self) -> None:
        state = reduce_engagement(self.engagement)
        _append_kernel_event(
            self.engagement,
            base_event(
                event_id="event-driver-operator-only",
                engagement_id=state["engagement_id"],
                recorded_at="2026-08-24T12:01:00Z",
                actor_role="orchestrator",
                actor_id="orchestrator-driver-test",
                event_type="authority.requested",
                rationale="Create one exact synthetic operator-only queue item.",
                payload={
                    "request_id": "request-driver-operator-only",
                    "action_kind": "synthetic-operator-only",
                    "action_digest": sha256_bytes(b"synthetic driver operator action\n"),
                    "lane_id": "lane-driver-operator-only",
                    "request_status": "pending_authority",
                    "scope_hash": state["scope_hash"],
                    "environment_ref": state["active_environment_ref"],
                    "expires_at": "2099-08-24T00:00:00Z",
                },
                session_id="session-driver-operator-only",
                operation_class="notebook",
            ),
        )
        result = run_driver(
            workspace=self.workspace,
            engagement=self.engagement,
            executable=Path("/not-reached"),
            model="claude-fixture-worker-20260825",
            reviewer_model="claude-fixture-reviewer-20260824",
            budget=DriverBudget(1, 60.0, 10.0, None),
        )
        self.assertEqual(result["status"], "operator_required")
        self.assertEqual(result["sessions_started"], 0)
        self.assertGreater(result["queue"]["total_count"], 0)
        self.assertEqual(result["queue"]["blocking_count"], 0)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    @unittest.skipUnless(DARWIN_SESSION_INTEGRATION, DARWIN_SESSION_SKIP)
    def test_real_subprocess_drains_known_queue_in_order_and_stops(self) -> None:
        workspace = self.root / "integration-target"
        engagement = workspace / "engagements" / "known-queue"
        engagement.mkdir(parents=True)
        reviewer_key = self.root / "driver-reviewer-ed25519"
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(reviewer_key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        public_parts = reviewer_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        allowed_signers = self.root / "driver-reviewer-allowed-signers"
        allowed_signers.write_text(
            f"reviewer-driver-fixture {public_parts[0]} {public_parts[1]}\n",
            encoding="utf-8",
        )
        scope = SCOPE.replace(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            sha256_file(allowed_signers),
        ).replace("fixture queue", "known queue")
        engagement.joinpath("scope.md").write_text(scope, encoding="utf-8")
        initialize_engagement(engagement, "2026-08-24T12:00:00Z")
        _append_kernel_event(
            engagement,
            base_event(
                event_id="event-driver-review-origin",
                engagement_id=engagement.name,
                recorded_at="2026-08-24T12:00:01Z",
                actor_role="orchestrator",
                actor_id="orchestrator-driver-fixture",
                event_type="observation.recorded",
                rationale="Establish the synthetic run that the cold review must independently challenge.",
                payload={
                    "entity_id": "observation-driver-origin",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-driver-origin",
                operation_class="notebook",
                model="fixture-origin-model",
            ),
        )
        runtime = self.root / "fixture-queue-runtime"
        runtime.write_text(f"#!{sys.executable}\n{FIXTURE_RUNTIME_BODY}", encoding="utf-8")
        runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)
        shutil.copyfile(reviewer_key, workspace / ".driver-fixture-reviewer-key")
        (workspace / ".driver-fixture-reviewer-key").chmod(0o600)
        shutil.copyfile(allowed_signers, workspace / ".driver-fixture-allowed-signers")
        result = run_driver(
            workspace=workspace,
            engagement=engagement,
            executable=runtime,
            model="claude-fixture-driver-20260825",
            reviewer_model=[
                "claude-fixture-reviewer-20260824",
                "claude-fixture-reviewer-two-20260824",
            ],
            budget=DriverBudget(4, 30.0, 10.0, None),
            read_only_inputs=tuple(dict.fromkeys((Path(sys.prefix), Path(sys.base_prefix)))),
        )

        state = reduce_engagement(engagement)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["completed"])
        self.assertEqual(result["sessions_started"], 2)
        self.assertEqual(
            [item["action_id"] for item in result["history"]],
            ["record_cold_coverage_review", "record_coverage_dry"],
        )
        self.assertEqual(
            [item["runtime_model"] for item in result["history"]],
            ["claude-fixture-reviewer-20260824", "claude-fixture-driver-20260825"],
        )
        self.assertEqual(
            result["models"]["reviewer_pool"],
            ["claude-fixture-reviewer-20260824", "claude-fixture-reviewer-two-20260824"],
        )
        self.assertEqual(state["coverage"], "coverage_dry")
        self.assertEqual(state["work_queue"], [])
        self.assertEqual(
            state["reviewer_run_models"]["run-driver-cold-coverage"],
            "claude-fixture-reviewer-20260824",
        )
        self.assertFalse(engagement.joinpath(".model-raw-write").exists())
        self.assertFalse(Path(__file__).with_name(".model-harness-write").exists())
        self.assertFalse(workspace.parent.joinpath(".model-outside-write").exists())
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    @unittest.skipUnless(DARWIN_SESSION_INTEGRATION, DARWIN_SESSION_SKIP)
    def test_noop_subprocess_spends_outer_session_budget_against_frozen_corpus(self) -> None:
        _append_kernel_event(
            self.engagement,
            base_event(
                event_id="event-noop-review-origin",
                engagement_id=self.engagement.name,
                recorded_at="2026-08-24T12:00:01Z",
                actor_role="orchestrator",
                actor_id="orchestrator-noop-fixture",
                event_type="observation.recorded",
                rationale="Give the no-op budget fixture an independently reviewable modeled origin.",
                payload={
                    "entity_id": "observation-noop-review-origin",
                    "entity_type": "observation",
                    "status": "recorded",
                },
                session_id="session-noop-review-origin",
                operation_class="notebook",
                model="claude-fixture-origin-20260824",
            ),
        )
        manifest_ref = self._register_corpus_freeze(row_count=3)
        runtime = self.root / "fixture-noop-runtime"
        runtime.write_text(
            f"#!{sys.executable}\nimport json\nprint(json.dumps({{'type': 'result', 'is_error': False}}))\n",
            encoding="utf-8",
        )
        runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)
        result = run_driver(
            workspace=self.workspace,
            engagement=self.engagement,
            executable=runtime,
            model="claude-fixture-worker-20260825",
            reviewer_model="claude-fixture-reviewer-20260824",
            budget=DriverBudget(1, 30.0, 10.0, None),
            read_only_inputs=tuple(dict.fromkeys((Path(sys.prefix), Path(sys.base_prefix)))),
            corpus_enumeration_ref=manifest_ref,
        )
        state = reduce_engagement(self.engagement)
        event = json.loads(self.engagement.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(result["status"], "budget_spent")
        self.assertEqual(result["budget_kind"], "max_sessions")
        self.assertEqual(result["sessions_started"], 1)
        self.assertEqual(state["coverage"], "budget_bounded")
        self.assertEqual(state["coverage_counts"]["enumerated_count"], 3)
        self.assertEqual(event["payload"]["budget_kind"], "max_sessions")
        self.assertEqual(event["payload"]["driver_run_ref"], result["run_ref"])
        self.assertEqual(event["payload"]["corpus_enumeration_ref"], manifest_ref)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    def test_missing_independent_reviewer_model_pauses_once_without_launch_or_write(self) -> None:
        before = {
            name: self.engagement.joinpath(name).read_bytes()
            for name in ("events.jsonl", "attempts.jsonl", "artifacts.jsonl")
        }
        result = run_driver(
            workspace=self.workspace,
            engagement=self.engagement,
            executable=Path("/not-reached"),
            model="claude-fixture-worker-20260825",
            reviewer_model="claude-fixture-reviewer-20260824",
            budget=DriverBudget(8, 60.0, 10.0, None),
        )
        after = {
            name: self.engagement.joinpath(name).read_bytes()
            for name in ("events.jsonl", "attempts.jsonl", "artifacts.jsonl")
        }
        self.assertEqual(result["status"], "reviewer_model_unavailable")
        self.assertEqual(result["sessions_started"], 0)
        self.assertEqual(result["history"], [])
        self.assertEqual(after, before)
        self.assertEqual(validate_record(result, "work-queue-driver"), [])

    def test_reviewer_pool_follows_claim_filing_regrade_and_poc_lineage(self) -> None:
        origins = (
            ("event-review-origin-worker", "claude-fixture-worker-20260825"),
            ("event-review-origin-author", "claude-reviewer-a-20260825"),
        )
        for ordinal, (event_id, origin_model) in enumerate(origins, start=1):
            _append_kernel_event(
                self.engagement,
                base_event(
                    event_id=event_id,
                    engagement_id=self.engagement.name,
                    recorded_at=f"2026-08-24T12:00:0{ordinal}Z",
                    actor_role="orchestrator",
                    actor_id=f"orchestrator-review-origin-{ordinal}",
                    event_type="observation.recorded",
                    rationale="Establish an exact modeled subject for deterministic reviewer selection.",
                    payload={
                        "entity_id": f"observation-review-origin-{ordinal}",
                        "entity_type": "observation",
                        "status": "recorded",
                    },
                    session_id=f"session-review-origin-{ordinal}",
                    operation_class="notebook",
                    model=origin_model,
                ),
            )

        def review_action(origin_ref: str, prior_runs: list[str]) -> dict[str, object]:
            constraints: list[dict[str, object]] = [
                {
                    "document": "proposal",
                    "path": ["independence", "originating_run_id"],
                    "operator": "equals",
                    "value": origin_ref,
                }
            ]
            if prior_runs:
                constraints.append(
                    {
                        "document": "proposal",
                        "path": ["prior_review_run_ids"],
                        "operator": "set_equals",
                        "value": prior_runs,
                    }
                )
            return {"admission": {"schema_version": 1, "constraints": constraints}}

        pool = (
            "claude-reviewer-a-20260825",
            "claude-reviewer-b-20260825",
            "claude-reviewer-c-20260825",
        )
        with bind_run(self.workspace, self.engagement) as bound:
            state = _reduce(bound)
            state["reviewer_run_models"] = {
                "run-claim-a": pool[0],
                "run-regrade-b": pool[1],
                "run-poc-c": pool[2],
            }
            # Claim A challenges the worker. Filing preserves A as the revised content author.
            self.assertEqual(
                _select_reviewer_model(
                    bound=bound,
                    state=state,
                    action=review_action("event-review-origin-worker", []),
                    reviewer_pool=pool,
                ),
                pool[0],
            )
            # Regrade cannot reuse content author / claim reviewer A, so it deterministically uses B.
            self.assertEqual(
                _select_reviewer_model(
                    bound=bound,
                    state=state,
                    action=review_action("event-review-origin-author", ["run-claim-a"]),
                    reviewer_pool=pool,
                ),
                pool[1],
            )
            # Pocinator cannot reuse author A or prior regrader B, so it uses C.
            self.assertEqual(
                _select_reviewer_model(
                    bound=bound,
                    state=state,
                    action=review_action("event-review-origin-author", ["run-regrade-b"]),
                    reviewer_pool=pool,
                ),
                pool[2],
            )
            # An exhausted exact lineage pauses instead of returning a model and retry-spinning.
            self.assertIsNone(
                _select_reviewer_model(
                    bound=bound,
                    state=state,
                    action=review_action(
                        "event-review-origin-author",
                        ["run-claim-a", "run-regrade-b", "run-poc-c"],
                    ),
                    reviewer_pool=pool,
                )
            )

    def test_driver_lock_is_structural_nonblocking_and_replacement_safe(self) -> None:
        legacy_lock = self.engagement / ".work-queue-driver.lock"
        moved = self.workspace / "engagements" / "fixture-moved-for-lock-test"
        with bind_run(self.workspace, self.engagement):
            legacy_lock.write_text("replaceable target bytes", encoding="utf-8")
            legacy_lock.unlink()
            with self.assertRaises(DriverError) as raised:
                with bind_run(self.workspace, self.engagement):
                    pass
            self.assertEqual(raised.exception.code, "driver_already_running")

            self.engagement.rename(moved)
            shutil.copytree(moved, self.engagement)
            try:
                with self.assertRaises(DriverError) as replacement_raised:
                    with bind_run(self.workspace, self.engagement):
                        pass
                self.assertEqual(replacement_raised.exception.code, "driver_already_running")
            finally:
                shutil.rmtree(self.engagement)
                moved.rename(self.engagement)
        self.assertFalse(legacy_lock.exists())

    def test_relative_target_inputs_are_rejected_before_normalization(self) -> None:
        with self.assertRaises(DriverError) as workspace_raised:
            with bind_run(Path("target"), self.engagement):
                pass
        self.assertEqual(workspace_raised.exception.code, "driver_target_layout_invalid")
        with self.assertRaises(DriverError) as engagement_raised:
            with bind_run(self.workspace, Path("target/engagements/fixture")):
                pass
        self.assertEqual(engagement_raised.exception.code, "driver_target_layout_invalid")

    def test_engagements_symlink_cannot_escape_bound_workspace_hierarchy(self) -> None:
        outside_workspace = self.root / "outside-target"
        outside_engagement = outside_workspace / "engagements" / "fixture"
        outside_engagement.mkdir(parents=True)
        aliased_workspace = self.root / "aliased-target"
        aliased_workspace.mkdir()
        aliased_workspace.joinpath("engagements").symlink_to(
            outside_workspace / "engagements",
            target_is_directory=True,
        )
        with self.assertRaises(DriverError) as raised:
            with bind_run(
                aliased_workspace,
                aliased_workspace / "engagements" / "fixture",
            ):
                pass
        self.assertEqual(raised.exception.code, "driver_target_unavailable")

    def test_cwd_relative_governed_open_keeps_nofollow_traversal(self) -> None:
        approved = self.workspace / "approved"
        approved.mkdir()
        outside = self.root / "outside-directory"
        outside.mkdir()
        (approved / "escape").symlink_to(outside, target_is_directory=True)
        original_cwd_fd = os.open(".", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        approved_fd: int | None = None
        try:
            os.chdir(self.workspace)
            approved_fd = _open_absolute_directory(approved)
            self.assertEqual(
                (os.fstat(approved_fd).st_dev, os.fstat(approved_fd).st_ino),
                (approved.stat().st_dev, approved.stat().st_ino),
            )
            with self.assertRaises(OSError):
                _open_absolute_directory(approved / "escape")
        finally:
            if approved_fd is not None:
                os.close(approved_fd)
            os.fchdir(original_cwd_fd)
            os.close(original_cwd_fd)

    def test_portable_harness_tree_cannot_be_used_as_target_workspace(self) -> None:
        with self.assertRaises(DriverError) as raised:
            with bind_run(ROOT, ROOT / "engagements" / "_TEMPLATE"):
                pass
        self.assertEqual(raised.exception.code, "driver_target_layout_invalid")

    def test_physical_alias_of_portable_harness_cannot_be_target_workspace(self) -> None:
        alias_parent = self.root / "portable-parent-alias"
        alias_parent.symlink_to(ROOT.parent, target_is_directory=True)
        aliased_root = alias_parent / ROOT.name
        with self.assertRaises(DriverError) as raised:
            with bind_run(aliased_root, aliased_root / "engagements" / "_TEMPLATE"):
                pass
        self.assertEqual(raised.exception.code, "driver_target_layout_invalid")

        case_alias = ROOT.with_name(ROOT.name.swapcase())
        if case_alias != ROOT and case_alias.exists() and os.path.samefile(case_alias, ROOT):
            with self.assertRaises(DriverError) as case_raised:
                with bind_run(case_alias, case_alias / "engagements" / "_TEMPLATE"):
                    pass
            self.assertEqual(case_raised.exception.code, "driver_target_layout_invalid")

    def test_rendered_action_cannot_redirect_execution_outside_bound_engagement(self) -> None:
        python = str(Path(sys.executable).absolute())
        tool = str((ROOT / "tools" / "run-engagement.py").resolve())
        action = {
            "command": "append-event",
            "operation": {"tool": "run-engagement", "command": "append-event"},
            "arguments": ["--engagement", str(self.engagement), "--file", "<event-json>"],
            "local_invocation": {
                "schema_version": 1,
                "launcher": {
                    "kind": "local_python_tool",
                    "resolution": "render_time",
                    "python": python,
                    "tool": tool,
                },
                "argv": [
                    python,
                    tool,
                    "append-event",
                    "--engagement",
                    str(self.engagement),
                    "--file",
                    "<event-json>",
                ],
            },
            "session_kind": "ordinary_bounded",
            "principal": "orchestrator",
            "execution_principal": "broker",
            "launchable": True,
            "recompute_after": True,
            "admission": {"schema_version": 1},
        }
        _validate_action_binding(action, self.engagement)
        redirected = copy.deepcopy(action)
        redirected["arguments"][1] = str(self.root / "other" / "engagements" / "wrong")
        with self.assertRaises(DriverError) as raised:
            _validate_action_binding(redirected, self.engagement)
        self.assertEqual(raised.exception.code, "driver_action_binding_invalid")

    def test_fresh_reviewer_model_must_be_distinct(self) -> None:
        with self.assertRaises(DriverError) as raised:
            run_driver(
                workspace=self.workspace,
                engagement=self.engagement,
                executable=Path("/not-reached"),
                model="claude-same-model-20260825",
                reviewer_model="claude-same-model-20260825",
                budget=DriverBudget(1, 1.0, 1.0, None),
            )
        self.assertEqual(raised.exception.code, "driver_reviewer_model_not_independent")

    def test_nonfinite_or_boolean_budgets_fail_before_dispatch(self) -> None:
        invalid = (
            (DriverBudget(True, 1.0, 1.0, None), "driver_max_sessions_invalid"),
            (DriverBudget(1, float("nan"), 1.0, None), "driver_max_wall_invalid"),
            (DriverBudget(1, 1.0, float("inf"), None), "driver_session_timeout_invalid"),
            (DriverBudget(1, 1.0, 1.0, float("nan")), "driver_session_budget_invalid"),
        )
        for budget, code in invalid:
            with self.subTest(code=code), self.assertRaises(DriverError) as raised:
                budget.validate()
            self.assertEqual(raised.exception.code, code)

    def test_named_directory_replacement_is_rejected(self) -> None:
        moved = self.workspace / "engagements" / "fixture-moved"
        with bind_run(self.workspace, self.engagement) as bound:
            self.engagement.rename(moved)
            self.engagement.mkdir()
            with self.assertRaises(DriverError) as raised:
                _reduce(bound)
            shutil.rmtree(self.engagement)
            moved.rename(self.engagement)
        self.assertEqual(raised.exception.code, "driver_target_identity_changed")

    def test_named_directory_replacement_cannot_receive_budget_event(self) -> None:
        moved = self.workspace / "engagements" / "fixture-moved"
        with bind_run(self.workspace, self.engagement) as bound:
            self.engagement.rename(moved)
            shutil.copytree(moved, self.engagement)
            original_events = moved.joinpath("events.jsonl").read_bytes()
            replacement_events = self.engagement.joinpath("events.jsonl").read_bytes()
            with self.assertRaises(DriverError) as raised:
                record_budget_boundary(
                    bound=bound,
                    run_ref="driver-replaced-target",
                    budget_kind="max_sessions",
                    budget=DriverBudget(1, 60.0, 10.0, None),
                    sessions_started=1,
                    elapsed_seconds=1.0,
                    seen_item_refs=set(),
                )
            self.assertEqual(moved.joinpath("events.jsonl").read_bytes(), original_events)
            self.assertEqual(self.engagement.joinpath("events.jsonl").read_bytes(), replacement_events)
            shutil.rmtree(self.engagement)
            moved.rename(self.engagement)
        self.assertEqual(raised.exception.code, "driver_target_identity_changed")

    def test_bound_handler_never_writes_identical_pathname_clone(self) -> None:
        state = reduce_engagement(self.engagement)
        uid = os.getuid()
        event = base_event(
            event_id="event-bound-handler-original-inode",
            engagement_id=state["engagement_id"],
            recorded_at="2026-08-24T12:01:00Z",
            actor_role="broker",
            actor_id=f"local-uid-{uid}:broker",
            event_type="observation.recorded",
            rationale="The trusted handler must retain the inode opened before pathname replacement.",
            payload={
                "entity_id": "observation-bound-handler-original-inode",
                "entity_type": "observation",
                "status": "recorded",
            },
            session_id=f"session-posix-{uid}-{os.getsid(0)}",
            operation_class="notebook",
            model="fixture-bound-handler-model",
        )
        event["provenance"]["runtime_session_ref"] = (
            "88888888-8888-4888-8888-888888888888"
        )
        engagement_fd = os.open(
            self.engagement,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        moved = self.engagement.with_name("fixture-bound-original")
        try:
            self.engagement.rename(moved)
            shutil.copytree(moved, self.engagement)
            clone_before = self.engagement.joinpath("events.jsonl").read_bytes()
            returncode, output = _run_engagement_module().execute_broker_command(
                command="append-event",
                arguments=[
                    "--engagement",
                    f"/dev/fd/{engagement_fd}",
                    "--file",
                    str(self.root / "untrusted-ignored-event.json"),
                ],
                admitted_documents={
                    "file": {
                        "value": event,
                        "bytes": canonical_json_bytes(event),
                    }
                },
                authenticated_runtime={
                    "runtime_session_ref": "88888888-8888-4888-8888-888888888888",
                    "model": "fixture-bound-handler-model",
                    "provider": None,
                },
            )
            self.assertEqual((returncode, json.loads(output)["event_id"]), (0, event["event_id"]))
            self.assertEqual(self.engagement.joinpath("events.jsonl").read_bytes(), clone_before)
            self.assertIn(event["event_id"], moved.joinpath("events.jsonl").read_text(encoding="utf-8"))
        finally:
            os.close(engagement_fd)
            if moved.exists():
                if self.engagement.exists():
                    shutil.rmtree(self.engagement)
                moved.rename(self.engagement)

    def test_broker_close_waits_for_fd_user_quiescence(self) -> None:
        source_fd = os.open(
            self.engagement,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        broker = object.__new__(DriverActionBroker)
        broker._engagement_fd = os.dup(source_fd)
        broker._close_lock = threading.Lock()
        broker._closed = False
        broker._stop = threading.Event()
        broker._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        broker._admission = {"action_id": "fixture-slow-handler"}
        broker.endpoint = self.root / "broker-quiescence-does-not-exist.sock"
        broker._endpoint_identity = (-1, -1)
        worker_errors: list[BaseException] = []

        def slow_fd_user() -> None:
            try:
                time.sleep(2.25)
                self.assertTrue(stat.S_ISDIR(os.fstat(broker._engagement_fd).st_mode))
            except BaseException as exc:
                worker_errors.append(exc)

        broker._thread = threading.Thread(target=slow_fd_user, daemon=True)
        broker._thread.start()
        started = time.monotonic()
        try:
            broker.close()
        finally:
            os.close(source_fd)
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 2.0)
        self.assertFalse(broker._thread.is_alive())
        self.assertEqual(broker._engagement_fd, -1)
        self.assertEqual(worker_errors, [])

    def test_parent_deadline_rejects_before_broker_admission(self) -> None:
        broker = object.__new__(DriverActionBroker)
        broker._execution_deadline = time.monotonic() - 1
        broker._admission = {"status": "armed", "action_id": "expired-action"}
        with self.assertRaises(RecordError) as raised:
            broker._admit(
                {
                    "command": "append-event",
                    "arguments": [],
                    "runtime_session_ref": "expired-runtime",
                }
            )
        self.assertEqual(
            raised.exception.code, "driver_action_execution_deadline_exceeded"
        )

    def test_parent_deadline_rechecks_after_model_input_validation(self) -> None:
        engagement_fd = os.open(
            self.engagement,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        broker = object.__new__(DriverActionBroker)
        opened = os.fstat(engagement_fd)
        broker._engagement_fd = engagement_fd
        broker._execution_deadline = 100.0
        broker._admission = {
            "status": "armed",
            "action_id": "deadline-crossing-action",
            "runtime_session_ref": "deadline-crossing-runtime",
            "runtime_session_kind": "ordinary_bounded",
            "os_session_id": os.getsid(0),
            "engagement_identity": {
                "device": opened.st_dev,
                "inode": opened.st_ino,
            },
            "command": "append-event",
            "argument_template": [],
            "predicate": {},
        }
        try:
            with (
                mock.patch.object(
                    admission_module.time,
                    "monotonic",
                    side_effect=[99.0, 101.0],
                ),
                mock.patch.object(
                    admission_module,
                    "_neutral_tail_is_allowed",
                    return_value=True,
                ),
                mock.patch.object(
                    admission_module,
                    "_verify_current_selected_action",
                ),
                mock.patch.object(
                    admission_module,
                    "_evaluate_predicate",
                    return_value=({}, {}),
                ),
                self.assertRaises(RecordError) as raised,
            ):
                broker._admit(
                    {
                        "command": "append-event",
                        "arguments": [],
                        "runtime_session_ref": "deadline-crossing-runtime",
                    }
                )
        finally:
            os.close(engagement_fd)
        self.assertEqual(
            raised.exception.code,
            "driver_action_execution_deadline_exceeded",
        )

    def test_model_inputs_are_nofollow_and_rejected_before_oversize_read(self) -> None:
        oversized_json = self.root / "oversized-proposal.json"
        descriptor = os.open(
            oversized_json, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            os.ftruncate(descriptor, _MODEL_JSON_LIMIT + 1)
        finally:
            os.close(descriptor)
        with mock.patch.object(
            admission_module.os,
            "read",
            side_effect=AssertionError("oversized input must fail at fstat"),
        ), self.assertRaises(RecordError) as oversized:
            _read_regular_json_bytes(
                oversized_json, error_code="driver_action_predicate_input_invalid"
            )
        self.assertEqual(
            oversized.exception.code, "driver_action_predicate_input_invalid"
        )

        signature = self.root / "review.sig"
        signature.write_bytes(b"fixture")
        signature_link = self.root / "review-link.sig"
        signature_link.symlink_to(signature)
        with self.assertRaises(RecordError) as linked:
            _read_regular_bytes(
                signature_link,
                max_bytes=_REVIEW_SIGNATURE_LIMIT,
                error_code="driver_action_predicate_input_invalid",
            )
        self.assertEqual(linked.exception.code, "driver_action_predicate_input_invalid")

        fifo = self.root / "proposal.fifo"
        os.mkfifo(fifo, 0o600)
        started = time.monotonic()
        with self.assertRaises(RecordError) as fifo_raised:
            _read_regular_bytes(
                fifo,
                max_bytes=_MODEL_JSON_LIMIT,
                error_code="driver_action_predicate_input_invalid",
            )
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(
            fifo_raised.exception.code,
            "driver_action_predicate_input_invalid",
        )

        oversized_signers = self.root / "oversized-allowed-signers"
        descriptor = os.open(
            oversized_signers, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            os.ftruncate(descriptor, _REVIEW_ALLOWED_SIGNERS_LIMIT + 1)
        finally:
            os.close(descriptor)
        with self.assertRaises(RecordError) as signers:
            _read_regular_bytes(
                oversized_signers,
                max_bytes=_REVIEW_ALLOWED_SIGNERS_LIMIT,
                error_code="driver_action_predicate_input_invalid",
            )
        self.assertEqual(signers.exception.code, "driver_action_predicate_input_invalid")

    def test_review_signature_limits_and_ssh_timeout_are_prewrite(self) -> None:
        engagement, _reviewer_key, allowed_signers = self._coverage_review_fixture()
        module = _run_engagement_module()
        original_events = engagement.joinpath("events.jsonl").read_bytes()
        with mock.patch.object(module.subprocess, "run") as run:
            with self.assertRaises(RecordError) as oversized:
                module._verify_review_signature(
                    engagement,
                    b"{}",
                    "reviewer-driver-fixture",
                    b"x" * (_REVIEW_SIGNATURE_LIMIT + 1),
                    allowed_signers.read_bytes(),
                )
            run.assert_not_called()
        self.assertEqual(oversized.exception.code, "reviewer_signature_invalid")

        timeout = subprocess.TimeoutExpired(["/usr/bin/ssh-keygen"], 0.01)
        with mock.patch.object(
            module.subprocess, "run", side_effect=timeout
        ) as run, self.assertRaises(RecordError) as hung:
            module._verify_review_signature(
                engagement,
                b"{}",
                "reviewer-driver-fixture",
                b"small-signature",
                allowed_signers.read_bytes(),
                timeout_seconds=0.01,
            )
        self.assertEqual(hung.exception.code, "reviewer_signature_invalid")
        self.assertEqual(run.call_args.kwargs["timeout"], 0.01)
        self.assertEqual(engagement.joinpath("events.jsonl").read_bytes(), original_events)

    def test_review_staging_tree_and_deadline_bounds_are_prewrite(self) -> None:
        module = _run_engagement_module()
        original_events = self.engagement.joinpath("events.jsonl").read_bytes()
        with mock.patch.object(module, "REVIEW_STAGING_MAX_ENTRIES", 1):
            with self.assertRaises(RecordError) as entries:
                module._copy_engagement_for_review_staging(
                    self.engagement,
                    self.root / "bounded-stage",
                    deadline=time.monotonic() + 5,
                )
        self.assertEqual(entries.exception.code, "record_review_staging_budget_exceeded")
        with self.assertRaises(RecordError) as deadline:
            module._copy_engagement_for_review_staging(
                self.engagement,
                self.root / "expired-stage",
                deadline=time.monotonic() - 1,
            )
        self.assertEqual(deadline.exception.code, "record_review_staging_budget_exceeded")
        self.assertEqual(self.engagement.joinpath("events.jsonl").read_bytes(), original_events)

    def test_stop_audit_rpc_is_bounded_and_retry_idempotent(self) -> None:
        engagement_fd = os.open(
            self.engagement,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        runtime_ref = "99999999-9999-4999-8999-999999999999"
        hook_ref = sha256_bytes(b"bounded-stop-hook")

        def broker_for(status: str, current_hook_ref: str) -> DriverActionBroker:
            current = reduce_engagement(self.engagement)
            broker = object.__new__(DriverActionBroker)
            broker._engagement_fd = engagement_fd
            opened = os.fstat(engagement_fd)
            broker._admission = {
                "runtime_session_ref": runtime_ref,
                "hook_session_ref": current_hook_ref,
                "os_session_id": os.getsid(0),
                "status": status,
                "action_id": "fixture-stop-action",
                "runtime_model": "fixture-stop-model",
                "engagement_identity": {
                    "device": opened.st_dev,
                    "inode": opened.st_ino,
                },
            }
            broker._stop_state_binding = {
                "event_count": current["event_count"],
                "ledger_hash": current["ledger_hash"],
                "source_hashes": copy.deepcopy(current["source_hashes"]),
            }
            broker._stop_request_results = {}
            broker._stop_release_recorded = False
            broker._post_consumption_release_recorded = False
            broker._lock = threading.Lock()
            return broker

        try:
            broker = broker_for("armed", hook_ref)

            def request(ordinal: int, active: bool) -> dict[str, object]:
                return {
                    "runtime_session_ref": runtime_ref,
                    "hook_session_ref": hook_ref,
                    "stop_hook_active": active,
                    "request_ref": sha256_bytes(f"stop-request-{ordinal}".encode()),
                }

            first = request(1, False)
            before_count = reduce_engagement(self.engagement)["event_count"]
            first_result = broker._execute_stop(first)
            self.assertEqual(first_result[0], 0)
            self.assertEqual(broker._execute_stop(first), first_result)
            self.assertEqual(
                reduce_engagement(self.engagement)["event_count"], before_count + 1
            )
            for ordinal in range(2, 7):
                self.assertEqual(broker._execute_stop(request(ordinal, True))[0], 0)
            release = broker._execute_stop(request(7, True))
            self.assertEqual(release[0], 0)
            self.assertIn("systemMessage", json.loads(release[1]))
            event_count = reduce_engagement(self.engagement)["event_count"]
            self.assertEqual(event_count, before_count + 7)
            self.assertNotEqual(broker._execute_stop(request(8, True))[0], 0)
            self.assertEqual(reduce_engagement(self.engagement)["event_count"], event_count)

            consumed_hook = sha256_bytes(b"consumed-stop-hook")
            consumed = broker_for("consumed", consumed_hook)
            consumed_request = {
                "runtime_session_ref": runtime_ref,
                "hook_session_ref": consumed_hook,
                "stop_hook_active": True,
                "request_ref": sha256_bytes(b"consumed-stop-request"),
            }
            consumed_result = consumed._execute_stop(consumed_request)
            self.assertEqual(consumed_result[0], 0)
            self.assertEqual(consumed._execute_stop(consumed_request), consumed_result)
            after_consumed = reduce_engagement(self.engagement)["event_count"]
            second_consumed = dict(consumed_request)
            second_consumed["request_ref"] = sha256_bytes(b"second-consumed-stop-request")
            self.assertNotEqual(consumed._execute_stop(second_consumed)[0], 0)
            self.assertEqual(
                reduce_engagement(self.engagement)["event_count"], after_consumed
            )
        finally:
            os.close(engagement_fd)

    def test_only_exact_authenticated_stop_tail_is_neutral(self) -> None:
        original = reduce_engagement(self.engagement)
        hook_session_ref = sha256_bytes(b"driver-fixture-hook-session")
        admission = {
            "hook_session_ref": hook_session_ref,
            "state_binding": {
                "event_count": original["event_count"],
                "ledger_hash": original["ledger_hash"],
                "source_hashes": copy.deepcopy(original["source_hashes"]),
            },
        }

        def append_stop(event_id: str, session_ref: str, ordinal: int) -> None:
            current = reduce_engagement(self.engagement)
            blocking = sum(
                1 for item in current["work_queue"] if item.get("blocking") is True
            )
            remaining = len(current["work_queue"])
            append_event(
                self.engagement,
                base_event(
                    event_id=event_id,
                    engagement_id=current["engagement_id"],
                    recorded_at=f"2026-08-24T12:01:0{ordinal}Z",
                    actor_role="broker",
                    actor_id="session-end-backstop",
                    event_type="session.end_checked",
                    rationale="Record an audit-only session-end backstop decision.",
                    payload={
                        "session_ref": session_ref,
                        "decision": "block" if blocking else "release",
                        "reason_code": (
                            "blocking_work_remaining" if blocking else "reentrant_state_unmatched"
                        ),
                        "confirmed_consecutive_blocks": ordinal if blocking else 0,
                        "blocking_work_count": blocking,
                        "remaining_work_count": remaining,
                        "queue_digest": sha256_bytes(canonical_json_bytes(current["work_queue"])),
                        "observed_state_hash": sha256_bytes(canonical_json_bytes(current)),
                    },
                    session_id=session_ref,
                    operation_class="notebook",
                ),
            )

        append_stop("event-neutral-stop-one", hook_session_ref, 1)
        self.assertTrue(
            _neutral_tail_is_allowed(admission, reduce_engagement(self.engagement), self.engagement)
        )
        append_stop("event-neutral-stop-two", hook_session_ref, 2)
        self.assertTrue(
            _neutral_tail_is_allowed(admission, reduce_engagement(self.engagement), self.engagement)
        )
        append_stop(
            "event-neutral-stop-foreign",
            sha256_bytes(b"another-driver-fixture-hook-session"),
            3,
        )
        self.assertFalse(
            _neutral_tail_is_allowed(admission, reduce_engagement(self.engagement), self.engagement)
        )

    @unittest.skipUnless(PEER_CREDENTIAL_INTEGRATION, PEER_CREDENTIAL_SKIP)
    def test_broker_rejects_same_uid_peer_from_another_os_session(self) -> None:
        endpoint = Path("/tmp") / f"lrh-peer-{os.getpid()}-{time.time_ns()}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(endpoint))
        listener.listen(1)
        broker = object.__new__(DriverActionBroker)
        broker._admission = {"os_session_id": os.getsid(0)}
        try:
            local = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            local.connect(str(endpoint))
            accepted, _ = listener.accept()
            try:
                self.assertTrue(broker._peer_is_runtime(accepted))
            finally:
                accepted.close()
                local.close()

            outsider = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import socket,sys,time; "
                        "s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); "
                        "time.sleep(1)"
                    ),
                    str(endpoint),
                ],
                start_new_session=True,
            )
            accepted, _ = listener.accept()
            try:
                self.assertFalse(broker._peer_is_runtime(accepted))
            finally:
                accepted.close()
                outsider.terminate()
                outsider.wait(timeout=5)
        finally:
            listener.close()
            endpoint.unlink(missing_ok=True)

    def test_state_stop_distinguishes_completion_pause_and_noncompletion(self) -> None:
        state = reduce_engagement(self.engagement)
        completed = copy.deepcopy(state)
        completed["coverage"] = "coverage_dry"
        completed["work_queue"] = []
        operator_only = copy.deepcopy(state)
        operator_only["work_queue"] = [
            {
                "class": "awaiting_operator",
                "entity": {"type": "authority_request", "id": "request-1", "detail": None},
                "blocking": False,
                "predicate": "pending authority",
                "closes_when": "resolved",
            }
        ]
        terminal_operator_only = copy.deepcopy(operator_only)
        terminal_operator_only["coverage"] = "coverage_dry"
        blocked = copy.deepcopy(state)
        blocked["coverage"] = "blocked"
        bounded = copy.deepcopy(state)
        bounded["coverage"] = "budget_bounded"
        self.assertEqual(_state_stop(completed), "completed")
        self.assertEqual(_state_stop(operator_only), "operator_required")
        self.assertEqual(_state_stop(terminal_operator_only), "completed")
        self.assertEqual(_state_stop(blocked), "coverage_blocked")
        self.assertEqual(_state_stop(bounded), "coverage_budget_bounded")

    def test_state_stop_accepts_exact_reducer_validated_coverage_dry_override(self) -> None:
        state = reduce_engagement(self.engagement)
        state["coverage"] = "coverage_dry"
        blockers = blocking_work_identities(state)
        self.assertTrue(blockers)
        state["ending_overrides"] = [
            {
                "event_ref": "event-ending-override-driver-fixture",
                "recorded_at": "2026-08-24T12:00:01Z",
                "terminal_kind": "coverage",
                "status": "coverage_dry",
                "reason": "The operator accepts these exact residual items.",
                "operator_id": "operator-driver-test",
                "blocking_items": blockers,
                "blocking_queue_digest": sha256_bytes(canonical_json_bytes(blockers)),
                "attempt_ledger_count": state["attempt_count"],
                "attempt_ledger_digest": state["source_hashes"]["attempts.jsonl"],
                "operator_signature_challenge_digest": "sha256:" + "3" * 64,
                "operator_signer_fingerprint": "sha256:" + "4" * 64,
            }
        ]
        state["coverage_relevant_event_ref"] = "event-ending-override-driver-fixture"

        self.assertEqual(_state_stop(state), "completed")

        state["ending_overrides"][0]["blocking_queue_digest"] = "sha256:" + "5" * 64
        with self.assertRaises(DriverError) as raised:
            _state_stop(state)
        self.assertEqual(raised.exception.code, "driver_terminal_queue_invariant")

        state["ending_overrides"][0]["blocking_queue_digest"] = sha256_bytes(canonical_json_bytes(blockers))
        state["attempt_count"] += 1
        state["source_hashes"]["attempts.jsonl"] = "sha256:" + "6" * 64
        with self.assertRaises(DriverError) as stale_context:
            _state_stop(state)
        self.assertEqual(stale_context.exception.code, "driver_terminal_queue_invariant")

        state["attempt_count"] = state["ending_overrides"][0]["attempt_ledger_count"]
        state["source_hashes"]["attempts.jsonl"] = state["ending_overrides"][0]["attempt_ledger_digest"]
        state["coverage_relevant_event_ref"] = "event-later-substantive-work"
        with self.assertRaises(DriverError) as stale_event_context:
            _state_stop(state)
        self.assertEqual(stale_event_context.exception.code, "driver_terminal_queue_invariant")


if __name__ == "__main__":
    unittest.main(verbosity=2)
