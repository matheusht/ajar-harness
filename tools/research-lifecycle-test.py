#!/usr/bin/env python3
"""Hermetic focused test for the decision-0006 research lifecycle commands.

Builds a synthetic engagement in a temporary directory (operator-signed scope +
``init`` + a clean local-runtime preflight), then exercises ``attempt-start``,
``attempt-finish``, ``record-negative``, ``register-bundle``, the lifecycle
append events, and ``ledger-health`` in-process.

No real engagement, target-specific record, or external evidence bundle is read
or written; every input is generated inside the test's temporary directory.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
RUNNER = TOOLS / "run-engagement.py"

SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
OPERATOR_NAMESPACE = "llm-redteam-harness-operator-v1"

BROKER_ROLE = "broker"
OPERATOR_ID = "operator-lifecycle-test"
OPERATOR_KEY_COMMENT = "lifecycle-test-operator"

INIT_AT = "2026-07-10T00:00:00Z"
PREFLIGHT_AT = "2026-07-10T00:01:00Z"
STARTED_AT = "2026-07-10T00:02:00Z"
FINISHED_AT = "2026-07-10T00:03:00Z"
LIFECYCLE_AT = "2026-07-10T00:04:00Z"
NEGATIVE_AT = "2026-07-10T00:05:00Z"

PREFLIGHT_ID = "preflight-lifecycle-synthetic"
ATTEMPT_ID = "attempt-lifecycle-test-1"
MISSING_START_ATTEMPT_ID = "attempt-lifecycle-test-missing-start"
NEGATIVE_ID = "negative-lifecycle-test-1"
BAD_NEGATIVE_ID = "negative-lifecycle-test-bad-attempt"
BUNDLE_ID = "bundle-lifecycle-test"
SECRET_BUNDLE_ID = "bundle-lifecycle-test-secret"

SECRET_LITERAL = "hunter2-not-a-real-credential"

DRIVER_ENV_VARS = (
    "HARNESS_DRIVER_ACTION_BROKER",
    "HARNESS_EXPECTED_ACTION_TOKEN",
    "HARNESS_EXPECTED_RUNTIME_SESSION_REF",
)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(passed), detail))


def load_runner() -> object:
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("research_lifecycle_cli", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("run-engagement loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StdoutCapture:
    """Stdout stand-in that exposes the ``buffer`` attribute ``emit`` writes to."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        pass


@contextlib.contextmanager
def temporary_environment(values: dict[str, str]):
    saved = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def invoke(
    runner: object, arguments: list[str], *, extra_env: dict[str, str] | None = None
) -> tuple[int, dict | None, str, str]:
    capture = _StdoutCapture()
    errors = io.StringIO()
    saved_argv = sys.argv
    sys.argv = ["run-engagement.py", *arguments]
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(errors):
            if extra_env:
                with temporary_environment(extra_env):
                    returncode = int(runner.main())
            else:
                returncode = int(runner.main())
    finally:
        sys.argv = saved_argv
    raw = capture.buffer.getvalue().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    return returncode, payload, raw, errors.getvalue()


def error_code(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("code")
    return None


def write_json(path: Path, value: object) -> None:
    path.write_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def scope_text(signers_digest: str) -> str:
    return f"""# Scope — synthetic lifecycle fixture

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Deterministic ledger test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `yes`
- zone2_authorized_categories: `zone2_artifact_creation`
- zone2_escalation_ceiling: `artifact_creation`
- zone2_containment: `synthetic temporary-directory fixture`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {signers_digest}
## Authorization
- Operator allowed signers SHA256: {signers_digest}
- Operator: {OPERATOR_ID}
- Date: 2026-07-10
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


def build_synthetic_engagement(
    runner: object, workspace: Path, *, actor_id: str, session_id: str
) -> tuple[Path, dict]:
    """Sign a synthetic scope, initialize it, and record one clean preflight."""

    engagement = workspace / "synthetic-lifecycle-engagement"
    engagement.mkdir()

    key = workspace / "operator-ed25519"
    subprocess.run(
        [str(SSH_KEYGEN), "-q", "-t", "ed25519", "-N", "", "-f", str(key), "-C", OPERATOR_KEY_COMMENT],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    public_parts = key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = workspace / "allowed-signers"
    allowed_signers.write_text(
        f"{OPERATOR_ID} {public_parts[0]} {public_parts[1]}\n", encoding="utf-8"
    )
    signers_digest = runner.sha256_file(allowed_signers)

    (engagement / "scope.md").write_text(scope_text(signers_digest), encoding="utf-8")
    scope_hash = runner.sha256_file(engagement / "scope.md")
    operation = f"initialize-engagement:{INIT_AT}"
    challenge_path = workspace / "init-challenge.json"
    challenge_path.write_bytes(
        runner.operator_challenge_bytes(
            engagement_id=engagement.name,
            scope_hash=scope_hash,
            ledger_hash=None,
            operation=operation,
            operator_id=OPERATOR_ID,
        )
    )
    subprocess.run(
        [
            str(SSH_KEYGEN),
            "-q",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            OPERATOR_NAMESPACE,
            str(challenge_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    init_rc, init_payload, init_raw, init_err = invoke(
        runner,
        ["init", "--engagement", str(engagement), "--recorded-at", INIT_AT],
        extra_env={
            "HARNESS_OPERATOR_SIGNATURE_FILE": str(challenge_path) + ".sig",
            "HARNESS_OPERATOR_ALLOWED_SIGNERS_FILE": str(allowed_signers),
        },
    )
    if init_rc != 0:
        raise RuntimeError(f"init failed: {(init_raw + init_err).strip()}")

    target = workspace / "package-fixture.bin"
    target.write_bytes(b"pinned synthetic package fixture\n")
    runtime = Path(sys.executable).resolve()
    preflight_rc, preflight_payload, preflight_raw, preflight_err = invoke(
        runner,
        [
            "preflight",
            "--engagement",
            str(engagement),
            "--preflight-id",
            PREFLIGHT_ID,
            "--mode",
            "package",
            "--target",
            str(target),
            "--expected-identity",
            runner.sha256_file(target),
            "--runtime",
            str(runtime),
            "--reproduction-argv",
            json.dumps([str(runtime), "-c", "pass"]),
            "--actor-role",
            BROKER_ROLE,
            "--actor-id",
            actor_id,
            "--session-id",
            session_id,
            "--recorded-at",
            PREFLIGHT_AT,
        ],
    )
    if preflight_rc != 0 or (preflight_payload or {}).get("status") != "ready":
        raise RuntimeError(f"preflight failed: {(preflight_raw + preflight_err).strip()}")

    state = runner.reduce_engagement(engagement.absolute())
    if state.get("active_environment_ref") != PREFLIGHT_ID:
        raise RuntimeError(f"preflight did not become the active environment: {state.get('active_environment_ref')}")
    return engagement, state


def scope_event_ref(state: dict) -> str:
    return f"event-scope-{state['scope_hash'][-12:]}"


def attempt_proposal(
    state: dict,
    *,
    attempt_id: str,
    actor_id: str,
    session_id: str,
) -> dict:
    actor = {"role": BROKER_ROLE, "id": actor_id}
    return {
        "schema_version": 2,
        "attempt_id": attempt_id,
        "engagement_id": state["engagement_id"],
        "recorded_at": FINISHED_AT,
        "actor": actor,
        "operation_class": "notebook",
        "provenance": {"actor": actor, "session_id": session_id},
        "scope_hash": state["scope_hash"],
        "environment_ref": PREFLIGHT_ID,
        "escalation_confirmation_event_ref": None,
        "hypothesis_ref": None,
        "experiment_ref": scope_event_ref(state),
        "surface": "synthetic local package fixture",
        "action_summary": "Hypothesis-free source_trace attempt over the synthetic fixture; no target contact.",
        "redaction_attestation": True,
        "observation": {
            "source": "source_inspection",
            "statement": "The synthetic fixture produced no signal; this record exists only to exercise the lifecycle contracts.",
        },
        "evidence_refs": [],
        "kind": "source_trace",
        "control_of": [],
        "assessment": "no_signal",
        "contamination": {
            "status": "none_observed",
            "sources": [],
            "note": "Synthetic temporary-directory fixture; no external target was contacted.",
        },
        "cost": {
            "human_review_seconds": 0,
            "model_calls": 0,
            "model_seconds": 0,
            "target_calls": 0,
            "tool_seconds": 0,
            "wall_seconds": 0,
        },
        "cost_status": "unavailable",
        "cost_note": "Synthetic fixture; no metered runtime.",
    }


def negative_proposal(state: dict, *, negative_id: str, attempt_refs: list[str], refs: dict) -> dict:
    return {
        "negative_result_id": negative_id,
        "scope_hash": state["scope_hash"],
        "recorded_at": NEGATIVE_AT,
        "status": "bounded",
        "goal_status": "open",
        "hypothesis_refs": [],
        "attempt_refs": attempt_refs,
        "evidence_bundle_ref": refs["bundle"],
        "coverage_ref": refs["coverage"],
        "provenance_ref": refs["provenance"],
        "reproducibility_ref": refs["reproducibility"],
        "limits": ["synthetic temporary-directory fixture only"],
        "residual_candidates": ["none"],
        "review_ref": None,
        "operator_signoff": None,
        "rationale": "Synthetic lifecycle test negative result; bounded by the local fixture and no target contact.",
    }


def lifecycle_event(
    runner: object,
    *,
    event_id: str,
    engagement_id: str,
    event_type: str,
    payload: dict,
    actor_id: str,
    session_id: str,
) -> dict:
    return runner.base_event(
        event_id=event_id,
        engagement_id=engagement_id,
        recorded_at=LIFECYCLE_AT,
        actor_role=BROKER_ROLE,
        actor_id=actor_id,
        event_type=event_type,
        rationale="Synthetic lifecycle test record; no target contact.",
        payload=payload,
        session_id=session_id,
        operation_class="notebook",
    )


def main() -> int:
    for name in DRIVER_ENV_VARS:
        os.environ.pop(name, None)

    runner = load_runner()
    uid = os.getuid()
    actor_id = f"local-uid-{uid}:broker"
    session_id = f"session-posix-{uid}-{os.getsid(0)}"
    hex_digest = "a" * 64

    with tempfile.TemporaryDirectory(prefix="research-lifecycle-test-") as temporary:
        workspace = Path(temporary)
        try:
            engagement, state = build_synthetic_engagement(
                runner, workspace, actor_id=actor_id, session_id=session_id
            )
        except Exception as exc:  # noqa: BLE001 - setup failure must be reported, not hidden
            print(f"FAIL synthetic lifecycle setup: {exc}")
            return 1

        scratch = workspace / "scratch"
        scratch.mkdir()

        # --- 1. attempt-start (hypothesis-free source_trace) ------------------
        start_rc, start_payload, start_raw, start_err = invoke(
            runner,
            [
                "attempt-start",
                "--engagement",
                str(engagement),
                "--attempt-id",
                ATTEMPT_ID,
                "--environment-ref",
                PREFLIGHT_ID,
                "--surface",
                "synthetic local package fixture",
                "--plan",
                "Exercise attempt-start and attempt-finish against a synthetic engagement.",
                "--started-at",
                STARTED_AT,
                "--expected-evidence",
                "start event bound to the attempt",
                "--stop-condition",
                "one lifecycle test attempt recorded",
                "--actor-role",
                BROKER_ROLE,
                "--actor-id",
                actor_id,
                "--session-id",
                session_id,
            ],
        )
        start_event_id = f"event-{ATTEMPT_ID}-start"
        events_after_start = runner.read_ledger(engagement, "event")
        start_event = next((event for event in events_after_start if event.get("event_id") == start_event_id), None)
        start_attempt = (start_event or {}).get("payload", {}).get("attempt", {})
        check(
            "attempt-start creates event-<attempt>-start with an attempt payload",
            start_rc == 0
            and isinstance(start_payload, dict)
            and start_payload.get("start_ref") == start_event_id
            and isinstance(start_event, dict)
            and start_event.get("event_type") == "attempt.started"
            and start_attempt.get("attempt_id") == ATTEMPT_ID
            and start_attempt.get("hypothesis_ref") is None
            and start_attempt.get("environment_ref") == PREFLIGHT_ID,
            (start_raw + start_err).strip(),
        )

        # --- 2. attempt-finish with the exact start ref -----------------------
        finish_file = scratch / "attempt-finish.json"
        write_json(
            finish_file,
            attempt_proposal(state, attempt_id=ATTEMPT_ID, actor_id=actor_id, session_id=session_id),
        )
        finish_rc, finish_payload, finish_raw, finish_err = invoke(
            runner,
            [
                "attempt-finish",
                "--engagement",
                str(engagement),
                "--file",
                str(finish_file),
                "--start-ref",
                start_event_id,
            ],
        )
        attempts = runner.read_ledger(engagement, "attempt")
        finished = next((item for item in attempts if item.get("attempt_id") == ATTEMPT_ID), None)
        check(
            "attempt-finish with --start-ref records start_ref on the attempt ledger",
            finish_rc == 0
            and isinstance(finish_payload, dict)
            and finish_payload.get("start_ref") == start_event_id
            and isinstance(finished, dict)
            and finished.get("start_ref") == start_event_id
            and finished.get("kind") == "source_trace"
            and finished.get("hypothesis_ref") is None,
            (finish_raw + finish_err).strip(),
        )

        # --- 3. attempt-finish without a valid start --------------------------
        missing_file = scratch / "attempt-finish-missing.json"
        write_json(
            missing_file,
            attempt_proposal(
                state,
                attempt_id=MISSING_START_ATTEMPT_ID,
                actor_id=actor_id,
                session_id=session_id,
            ),
        )
        missing_rc, missing_payload, missing_raw, missing_err = invoke(
            runner,
            [
                "attempt-finish",
                "--engagement",
                str(engagement),
                "--file",
                str(missing_file),
                "--start-ref",
                "event-does-not-exist-start",
            ],
        )
        attempts_after_missing = runner.read_ledger(engagement, "attempt")
        check(
            "attempt-finish without a valid start fails with attempt_start_missing",
            missing_rc != 0
            and error_code(missing_payload) == "attempt_start_missing"
            and not any(item.get("attempt_id") == MISSING_START_ATTEMPT_ID for item in attempts_after_missing),
            (missing_raw + missing_err).strip(),
        )

        # --- 4. generic append-event cannot forge attempt.started -------------
        forged_file = scratch / "forged-attempt-start.json"
        write_json(
            forged_file,
            lifecycle_event(
                runner,
                event_id="event-forged-attempt-start",
                engagement_id=state["engagement_id"],
                event_type="attempt.started",
                payload={"entity_id": "forged-attempt", "status": "started"},
                actor_id=actor_id,
                session_id=session_id,
            ),
        )
        forged_rc, forged_payload, forged_raw, forged_err = invoke(
            runner,
            ["append-event", "--engagement", str(engagement), "--file", str(forged_file)],
        )
        check(
            "generic append-event rejects attempt.started with canonical_notebook_command_required",
            forged_rc != 0
            and error_code(forged_payload) == "canonical_notebook_command_required"
            and not any(
                event.get("event_id") == "event-forged-attempt-start"
                for event in runner.read_ledger(engagement, "event")
            ),
            (forged_raw + forged_err).strip(),
        )

        # --- 7a. lifecycle append events --------------------------------------
        lifecycle_proposals = {
            "provenance": lifecycle_event(
                runner,
                event_id="event-provenance-lifecycle-test",
                engagement_id=state["engagement_id"],
                event_type="provenance.recorded",
                payload={
                    "entity_id": "provenance-lifecycle-test",
                    "status": "recorded",
                    "provenance": {
                        "source_commit": "000000000000",
                        "source_manifest_sha256": f"sha256:{hex_digest}",
                        "live_build_id": "live-lifecycle-test",
                        "binding": "exact",
                        "normalizations": [],
                        "source_observed_at": STARTED_AT,
                        "live_observed_at": STARTED_AT,
                    },
                },
                actor_id=actor_id,
                session_id=session_id,
            ),
            "coverage": lifecycle_event(
                runner,
                event_id="event-coverage-lifecycle-test",
                engagement_id=state["engagement_id"],
                event_type="coverage.lane_recorded",
                payload={
                    "entity_id": "coverage-lifecycle-test",
                    "status": "recorded",
                    "coverage": {
                        "lanes": [
                            {
                                "name": "source",
                                "status": "tested",
                                "evidence_refs": [],
                                "blocked_reason": None,
                            }
                        ]
                    },
                },
                actor_id=actor_id,
                session_id=session_id,
            ),
            "reproducibility": lifecycle_event(
                runner,
                event_id="event-reproducibility-lifecycle-test",
                engagement_id=state["engagement_id"],
                event_type="reproducibility.recorded",
                payload={
                    "entity_id": "reproducibility-lifecycle-test",
                    "status": "recorded",
                    "reproducibility": {
                        "command": "python tools/research-lifecycle-test.py",
                        "seed": None,
                        "inputs": [],
                        "output_sha256": None,
                        "replayable": True,
                        "notes": "Synthetic lifecycle fixture.",
                    },
                },
                actor_id=actor_id,
                session_id=session_id,
            ),
        }
        lifecycle_refs = {}
        lifecycle_details = []
        for name, proposal in lifecycle_proposals.items():
            path = scratch / f"lifecycle-{name}.json"
            write_json(path, proposal)
            rc, payload, raw, err = invoke(
                runner,
                ["append-event", "--engagement", str(engagement), "--file", str(path)],
            )
            if rc == 0 and isinstance(payload, dict):
                lifecycle_refs[name] = payload.get("event_id")
            lifecycle_details.append(f"{name}:{rc}:{error_code(payload)}:{(raw + err).strip()}")
        recorded_events = {event.get("event_id") for event in runner.read_ledger(engagement, "event")}
        check(
            "provenance.recorded, coverage.lane_recorded, reproducibility.recorded append via append-event",
            len(lifecycle_refs) == 3
            and all(event_id in recorded_events for event_id in lifecycle_refs.values()),
            " | ".join(lifecycle_details),
        )

        # --- 6a. register-bundle on a tiny synthetic source directory ---------
        bundle_source = workspace / "bundle-source"
        bundle_source.mkdir()
        (bundle_source / "alpha.txt").write_text("alpha lifecycle evidence\n", encoding="utf-8")
        (bundle_source / "beta.md").write_text("# beta lifecycle evidence\n", encoding="utf-8")
        bundle_relative = "evidence/bundles/bundle-lifecycle-test.json"
        bundle_rc, bundle_payload, bundle_raw, bundle_err = invoke(
            runner,
            [
                "register-bundle",
                "--engagement",
                str(engagement),
                "--source-dir",
                str(bundle_source),
                "--artifact-id",
                BUNDLE_ID,
                "--relative-path",
                bundle_relative,
                "--created-at",
                LIFECYCLE_AT,
                "--recorded-at",
                LIFECYCLE_AT,
                "--actor-role",
                BROKER_ROLE,
                "--actor-id",
                actor_id,
                "--session-id",
                session_id,
            ],
        )
        manifest_path = engagement / bundle_relative
        artifact_ids = {item.get("artifact_id") for item in runner.read_ledger(engagement, "artifact")}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        check(
            "register-bundle writes a manifest under evidence/bundles and registers the artifact",
            bundle_rc == 0
            and isinstance(bundle_payload, dict)
            and bundle_payload.get("artifact_id") == BUNDLE_ID
            and manifest_path.is_file()
            and manifest.get("bundle_id") == BUNDLE_ID
            and manifest.get("file_count") == 2
            and BUNDLE_ID in artifact_ids,
            (bundle_raw + bundle_err).strip(),
        )

        # --- 6b. a secret-shaped source file is rejected without echoing ------
        secret_source = workspace / "bundle-source-secret"
        secret_source.mkdir()
        (secret_source / "notes.txt").write_text(
            f"alpha lifecycle evidence\npassword = {SECRET_LITERAL}\n", encoding="utf-8"
        )
        secret_relative = "evidence/bundles/bundle-lifecycle-test-secret.json"
        secret_rc, secret_payload, secret_raw, secret_err = invoke(
            runner,
            [
                "register-bundle",
                "--engagement",
                str(engagement),
                "--source-dir",
                str(secret_source),
                "--artifact-id",
                SECRET_BUNDLE_ID,
                "--relative-path",
                secret_relative,
                "--created-at",
                LIFECYCLE_AT,
                "--recorded-at",
                LIFECYCLE_AT,
                "--actor-role",
                BROKER_ROLE,
                "--actor-id",
                actor_id,
                "--session-id",
                session_id,
            ],
        )
        secret_output = secret_raw + secret_err
        check(
            "register-bundle rejects a secret-shaped source without echoing the value",
            secret_rc != 0
            and error_code(secret_payload) == "bundle_secret_content"
            and SECRET_LITERAL not in secret_output
            and not (engagement / secret_relative).exists()
            and SECRET_BUNDLE_ID
            not in {item.get("artifact_id") for item in runner.read_ledger(engagement, "artifact")},
            secret_output.strip(),
        )

        # --- 5a. record-negative for the hypothesis-free source_trace --------
        refs = {
            "bundle": BUNDLE_ID,
            "coverage": lifecycle_refs.get("coverage"),
            "provenance": lifecycle_refs.get("provenance"),
            "reproducibility": lifecycle_refs.get("reproducibility"),
        }
        negative_file = scratch / "negative-valid.json"
        write_json(
            negative_file,
            negative_proposal(state, negative_id=NEGATIVE_ID, attempt_refs=[ATTEMPT_ID], refs=refs),
        )
        negative_rc, negative_payload, negative_raw, negative_err = invoke(
            runner,
            [
                "record-negative",
                "--engagement",
                str(engagement),
                "--file",
                str(negative_file),
                "--actor-role",
                BROKER_ROLE,
                "--actor-id",
                actor_id,
                "--session-id",
                session_id,
            ],
        )
        negative_event_id = f"event-{NEGATIVE_ID}-recorded"
        negative_event = next(
            (
                event
                for event in runner.read_ledger(engagement, "event")
                if event.get("event_id") == negative_event_id
            ),
            None,
        )
        negative_payload_value = (negative_event or {}).get("payload", {}).get("negative_result", {})
        check(
            "record-negative succeeds for the finished attempt and cites the lifecycle refs",
            negative_rc == 0
            and isinstance(negative_payload, dict)
            and negative_payload.get("event_id") == negative_event_id
            and isinstance(negative_event, dict)
            and negative_event.get("event_type") == "negative_result.recorded"
            and negative_payload_value.get("attempt_refs") == [ATTEMPT_ID]
            and negative_payload_value.get("hypothesis_refs") == []
            and negative_payload_value.get("coverage_ref") == refs["coverage"]
            and negative_payload_value.get("provenance_ref") == refs["provenance"]
            and negative_payload_value.get("reproducibility_ref") == refs["reproducibility"],
            (negative_raw + negative_err).strip(),
        )

        # --- 5b. record-negative with an invalid attempt ref ------------------
        bad_file = scratch / "negative-bad-attempt.json"
        write_json(
            bad_file,
            negative_proposal(
                state,
                negative_id=BAD_NEGATIVE_ID,
                attempt_refs=["attempt-does-not-exist"],
                refs=refs,
            ),
        )
        bad_rc, bad_payload, bad_raw, bad_err = invoke(
            runner,
            [
                "record-negative",
                "--engagement",
                str(engagement),
                "--file",
                str(bad_file),
                "--actor-role",
                BROKER_ROLE,
                "--actor-id",
                actor_id,
                "--session-id",
                session_id,
            ],
        )
        check(
            "record-negative rejects an invalid attempt ref with negative_result_attempt_ref_invalid",
            bad_rc != 0
            and error_code(bad_payload) == "negative_result_attempt_ref_invalid"
            and not any(
                event.get("event_id") == f"event-{BAD_NEGATIVE_ID}-recorded"
                for event in runner.read_ledger(engagement, "event")
            ),
            (bad_raw + bad_err).strip(),
        )

        # --- 8. the synthetic engagement stays healthy -----------------------
        health_rc, health_payload, health_raw, health_err = invoke(
            runner,
            ["ledger-health", "--engagement", str(engagement)],
        )
        check(
            "ledger-health reports the synthetic engagement healthy and reducible",
            health_rc == 0
            and isinstance(health_payload, dict)
            and health_payload.get("status") == "healthy"
            and health_payload.get("reducible") is True
            and health_payload.get("error") is None,
            (health_raw + health_err).strip(),
        )

    failures = [(name, detail) for name, passed, detail in CHECKS if not passed]
    for name, passed, detail in CHECKS:
        if passed:
            print(f"PASS {name}")
        else:
            print(f"FAIL {name}: {detail}")
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
