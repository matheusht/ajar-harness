#!/usr/bin/env python3
"""Focused adversarial tests for the authenticated container broker seam."""

from __future__ import annotations

import base64
import copy
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import container_broker_client as client
import driver_action_admission as admission
from engagement_records import RecordError, canonical_json_bytes, sha256_bytes


CONTAINER_ID = "a" * 64
CONFIG_DIGEST = "sha256:" + "b" * 64
RUNTIME_REF = "88888888-8888-4888-8888-888888888888"
ACTION_ID = "fixture-container-action"
KEY = bytes(range(32))
HOOK_REF = sha256_bytes(client.STOP_SESSION_DOMAIN + RUNTIME_REF.encode("utf-8"))


def predicate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "documents": [{"name": "proposal", "argument": "--file"}],
        "constraints": [
            {
                "document": "proposal",
                "path": ["kind"],
                "operator": "equals",
                "value": "fixture",
            }
        ],
    }


def docker_identity() -> dict[str, str]:
    return {
        "kind": "docker_container",
        "container_id": CONTAINER_ID,
        "container_config_digest": CONFIG_DIGEST,
    }


def broker_admission() -> dict[str, object]:
    return {
        "status": "armed",
        "runtime_session_ref": RUNTIME_REF,
        "runtime_model": "fixture-container-model",
        "runtime_session_kind": "ordinary_bounded",
        "hook_session_ref": HOOK_REF,
        "os_session_id": None,
        "runtime_identity": None,
        "action_id": ACTION_ID,
        "command": "append-event",
        "argument_template": [
            "--engagement",
            "/target/engagements/fixture",
            "--file",
            "<event-json>",
        ],
        "predicate": predicate(),
    }


def inline_item(argument: str, raw: bytes) -> dict[str, object]:
    return {
        "argument": argument,
        "size": len(raw),
        "sha256": sha256_bytes(raw),
        "content_base64": base64.b64encode(raw).decode("ascii"),
    }


class ContainerBrokerProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="container-broker-test-")
        self.root = Path(self.temporary.name)
        self.engagement_fd = os.open(
            self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        self.broker = admission.DriverActionBroker(
            engagement_fd=self.engagement_fd,
            logical_engagement=self.root,
            admission=broker_admission(),
            execution_deadline=time.monotonic() + 30.0,
            docker_identity={
                "container_id": CONTAINER_ID,
                "container_config_digest": CONFIG_DIGEST,
            },
            docker_session_key=KEY,
        )
        self.broker.activate_docker()
        self.manifest = self.broker.container_manifest()

    def tearDown(self) -> None:
        self.broker.close()
        os.close(self.engagement_fd)
        self.temporary.cleanup()

    def test_authenticated_action_inlines_exact_bytes_and_never_sends_host_authority(self) -> None:
        proposal = self.root / "proposal.json"
        raw = canonical_json_bytes({"kind": "fixture", "secret": "semantic-only"})
        proposal.write_bytes(raw)
        observed: list[tuple[dict[str, object], dict[str, bytes] | None]] = []

        def execute(
            request: dict[str, object], inline_inputs: dict[str, bytes] | None
        ) -> tuple[int, bytes]:
            observed.append((copy.deepcopy(request), copy.deepcopy(inline_inputs)))
            return 0, canonical_json_bytes({"valid": True})

        self.broker._execute = execute  # type: ignore[method-assign]
        returncode, output = client.forward_action(
            self.manifest,
            KEY,
            command="append-event",
            arguments=[
                "--engagement",
                "/workspace/engagements/fixture",
                "--file",
                str(proposal),
            ],
        )
        self.assertEqual((returncode, json.loads(output)), (0, {"valid": True}))
        self.assertEqual(len(observed), 1)
        request, inline_inputs = observed[0]
        self.assertEqual(request["runtime_session_ref"], RUNTIME_REF)
        self.assertEqual(inline_inputs, {"--file": raw})
        self.assertNotIn(str(proposal), repr(inline_inputs))

    def test_admitted_action_waits_for_its_authoritative_response(self) -> None:
        proposal = self.root / "proposal.json"
        proposal.write_bytes(canonical_json_bytes({"kind": "fixture"}))

        def execute(
            _request: dict[str, object], _inline_inputs: dict[str, bytes] | None
        ) -> tuple[int, bytes]:
            time.sleep(0.1)
            return 0, canonical_json_bytes({"valid": True})

        self.broker._execute = execute  # type: ignore[method-assign]
        with mock.patch.object(client, "IO_TIMEOUT_SECONDS", 0.025):
            returncode, output = client.forward_action(
                self.manifest,
                KEY,
                command="append-event",
                arguments=["--file", str(proposal)],
            )
        self.assertEqual((returncode, json.loads(output)), (0, {"valid": True}))

    def test_authenticated_stop_uses_the_same_exact_container_binding(self) -> None:
        observed: list[dict[str, object]] = []

        def execute_stop(request: dict[str, object]) -> tuple[int, bytes]:
            observed.append(copy.deepcopy(request))
            return 0, canonical_json_bytes({})

        self.broker._execute_stop = execute_stop  # type: ignore[method-assign]
        returncode, output = client.forward_stop(
            self.manifest,
            KEY,
            hook_session_ref=HOOK_REF,
            stop_hook_active=False,
            request_ref="sha256:" + "d" * 64,
        )
        self.assertEqual((returncode, json.loads(output)), (0, {}))
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["runtime_session_ref"], RUNTIME_REF)

    def test_stdin_stop_hook_matches_claude_derivations_and_fail_opens_silently(self) -> None:
        key_path = self.root / "hook-session.key"
        key_path.write_bytes(KEY)
        os.chmod(key_path, 0o400)
        environment = {
            **os.environ,
            client.MANIFEST_ENV: json.dumps(
                self.manifest, sort_keys=True, separators=(",", ":")
            ),
            client.KEY_FILE_ENV: str(key_path),
        }
        environment.pop(client.MANIFEST_FILE_ENV, None)
        environment.pop(client.KEY_FD_ENV, None)
        observed: list[dict[str, object]] = []

        def execute_stop(request: dict[str, object]) -> tuple[int, bytes]:
            observed.append(copy.deepcopy(request))
            return 0, canonical_json_bytes(
                {"decision": "block", "reason": "fixture continuation"}
            )

        self.broker._execute_stop = execute_stop  # type: ignore[method-assign]

        def invoke(raw: bytes, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                [sys.executable, str(Path(client.__file__).resolve()), "stop-hook"],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment if env is None else env,
                check=False,
            )

        raw = json.dumps(
            {
                "session_id": RUNTIME_REF,
                "hook_event_name": "Stop",
                "stop_hook_active": False,
                "transcript_path": "/container/private/transcript.jsonl",
                "last_assistant_message": "must never cross the hook boundary",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        valid = invoke(raw)
        self.assertEqual(valid.returncode, 0)
        self.assertEqual(valid.stderr, b"")
        self.assertEqual(
            valid.stdout,
            canonical_json_bytes(
                {"decision": "block", "reason": "fixture continuation"}
            ),
        )
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["hook_session_ref"], HOOK_REF)
        self.assertEqual(
            observed[0]["request_ref"],
            sha256_bytes(client.STOP_REQUEST_DOMAIN + raw),
        )
        self.assertNotIn("transcript", repr(observed[0]))
        self.assertNotIn("assistant", repr(observed[0]))

        malformed = (
            b"{",
            (
                b'{"session_id":"a","session_id":"b","hook_event_name":"Stop",'
                b'"stop_hook_active":false}\n'
            ),
            json.dumps(
                {
                    "session_id": RUNTIME_REF,
                    "hook_event_name": "Stop",
                    "stop_hook_active": False,
                    "agent_id": "subagent-1",
                }
            ).encode("utf-8"),
            b"x" * (client.MAX_STOP_HOOK_STDIN_BYTES + 1),
        )
        for value in malformed:
            with self.subTest(value=value[:40]):
                released = invoke(value)
                self.assertEqual(
                    (released.returncode, released.stdout, released.stderr),
                    (0, canonical_json_bytes({}), b""),
                )
        self.assertEqual(len(observed), 1)

        rejected_raw = json.dumps(
            {
                "session_id": "different-session",
                "hook_event_name": "Stop",
                "stop_hook_active": False,
            }
        ).encode("utf-8")
        rejected = invoke(rejected_raw)
        self.assertEqual(
            (rejected.returncode, rejected.stdout, rejected.stderr),
            (0, canonical_json_bytes({}), b""),
        )
        self.assertEqual(len(observed), 1)

        missing_authority = dict(environment)
        missing_authority.pop(client.KEY_FILE_ENV)
        unavailable = invoke(raw, env=missing_authority)
        self.assertEqual(
            (unavailable.returncode, unavailable.stdout, unavailable.stderr),
            (0, canonical_json_bytes({}), b""),
        )
        self.assertEqual(len(observed), 1)

    def test_wrong_key_binding_replay_and_tampered_response_fail_closed(self) -> None:
        proposal = self.root / "proposal.json"
        proposal.write_bytes(canonical_json_bytes({"kind": "fixture"}))
        calls: list[dict[str, object]] = []

        def execute(
            request: dict[str, object], _inline_inputs: dict[str, bytes] | None
        ) -> tuple[int, bytes]:
            calls.append(copy.deepcopy(request))
            return 0, canonical_json_bytes({"valid": True})

        self.broker._execute = execute  # type: ignore[method-assign]
        arguments = [
            "--engagement",
            "/workspace/engagements/fixture",
            "--file",
            str(proposal),
        ]
        payload = {
            "request_kind": "action",
            "command": "append-event",
            "arguments": arguments,
            "runtime_session_ref": RUNTIME_REF,
            "inline_inputs": client._inline_inputs(self.manifest, arguments),
        }
        fixed_nonce = b"n" * client.NONCE_BYTES
        first = client._exchange(self.manifest, KEY, payload, nonce=fixed_nonce)
        second = client._exchange(self.manifest, KEY, payload, nonce=fixed_nonce)
        self.assertEqual(first["returncode"], 0)
        self.assertEqual(second["returncode"], 1)
        self.assertEqual(json.loads(second["output"])["error"]["code"], "driver_action_broker_replay")
        self.assertEqual(len(calls), 1)

        with self.assertRaises(client.ContainerBrokerClientError) as wrong_key:
            client._exchange(self.manifest, b"x" * 32, payload)
        self.assertEqual(wrong_key.exception.code, "container_broker_response_auth_invalid")
        self.assertEqual(len(calls), 1)

        wrong_manifest = copy.deepcopy(self.manifest)
        wrong_manifest["runtime_identity"]["container_id"] = "e" * 64
        with self.assertRaises(client.ContainerBrokerClientError):
            client._exchange(wrong_manifest, KEY, payload)
        self.assertEqual(len(calls), 1)

        response = self.broker._container_response(
            request_nonce=base64.b64encode(b"r" * 32).decode("ascii"),
            returncode=0,
            output=b"{}\n",
        )
        response["payload"]["returncode"] = 1
        with self.assertRaises(client.ContainerBrokerClientError) as tampered:
            client._validate_response(
                self.manifest, KEY, response, response["request_nonce"]
            )
        self.assertEqual(tampered.exception.code, "container_broker_response_auth_invalid")

        wrong_domain = self.broker._container_response(
            request_nonce=base64.b64encode(b"s" * 32).decode("ascii"),
            returncode=0,
            output=b"{}\n",
        )
        wrong_domain_unsigned = dict(wrong_domain)
        wrong_domain_unsigned.pop("mac_base64")
        wrong_domain["mac_base64"] = client._mac(
            KEY, client.REQUEST_DOMAIN, wrong_domain_unsigned
        )
        with self.assertRaises(client.ContainerBrokerClientError) as separated:
            client._validate_response(
                self.manifest,
                KEY,
                wrong_domain,
                wrong_domain["request_nonce"],
            )
        self.assertEqual(
            separated.exception.code, "container_broker_response_auth_invalid"
        )

    def test_every_runtime_binding_and_the_host_deadline_fail_closed(self) -> None:
        proposal = self.root / "proposal.json"
        proposal.write_bytes(canonical_json_bytes({"kind": "fixture"}))
        arguments = ["--file", str(proposal)]
        payload = {
            "request_kind": "action",
            "command": "append-event",
            "arguments": arguments,
            "runtime_session_ref": RUNTIME_REF,
            "inline_inputs": client._inline_inputs(self.manifest, arguments),
        }
        mutations = {
            "runtime session": lambda value: value.__setitem__(
                "runtime_session_ref", "99999999-9999-4999-8999-999999999999"
            ),
            "action": lambda value: value.__setitem__("action_id", "other-action"),
            "deadline": lambda value: value.__setitem__(
                "deadline_ref", "sha256:" + "0" * 64
            ),
            "container": lambda value: value["runtime_identity"].__setitem__(
                "container_id", "e" * 64
            ),
            "config": lambda value: value["runtime_identity"].__setitem__(
                "container_config_digest", "sha256:" + "f" * 64
            ),
        }
        for name, mutate in mutations.items():
            manifest = copy.deepcopy(self.manifest)
            mutate(manifest)
            envelope = client._envelope(manifest, KEY, payload)
            with self.subTest(name=name), self.assertRaises(RecordError) as rejected:
                self.broker._authenticate_container_request(envelope)
            self.assertEqual(rejected.exception.code, "driver_action_scope_mismatch")

        envelope = client._envelope(self.manifest, KEY, payload)
        with (
            mock.patch.object(
                admission.time,
                "monotonic",
                return_value=self.broker._execution_deadline,
            ),
            self.assertRaises(RecordError) as expired,
        ):
            self.broker._authenticate_container_request(envelope)
        self.assertEqual(
            expired.exception.code, "driver_action_execution_deadline_exceeded"
        )
        self.assertEqual(self.broker._admission["status"], "armed")

    def test_inline_set_rejects_missing_extra_duplicate_size_digest_and_oversize(self) -> None:
        record = broker_admission()
        raw = canonical_json_bytes({"kind": "fixture"})
        valid = inline_item("--file", raw)
        cases = {
            "missing": [],
            "extra": [valid, inline_item("--other", b"x")],
            "duplicate": [valid, valid],
            "size": [{**valid, "size": len(raw) + 1}],
            "digest": [{**valid, "sha256": "sha256:" + "0" * 64}],
            "oversize": [inline_item("--file", b"x" * (admission._MODEL_JSON_LIMIT + 1))],
        }
        for name, value in cases.items():
            with self.subTest(name=name), self.assertRaises(RecordError):
                admission._decode_container_inline_inputs(record, value)
        self.assertEqual(
            admission._decode_container_inline_inputs(record, [valid]),
            {"--file": raw},
        )

        payload = {
            "request_kind": "action",
            "command": "append-event",
            "arguments": ["--file", "/container-only/proposal.json"],
            "runtime_session_ref": RUNTIME_REF,
            "inline_inputs": [{**valid, "sha256": "sha256:" + "0" * 64}],
        }
        with mock.patch.object(
            self.broker,
            "_execute",
            side_effect=AssertionError("execution began before inline admission"),
        ):
            rejected = client._exchange(self.manifest, KEY, payload)
        self.assertEqual(rejected["returncode"], 1)
        self.assertEqual(
            json.loads(rejected["output"])["error"]["code"],
            "driver_action_predicate_input_invalid",
        )
        self.assertEqual(self.broker._admission["status"], "armed")

    def test_record_review_requires_predicates_and_signature_material_inline(self) -> None:
        record = broker_admission()
        record["command"] = "record-review"
        record["predicate"] = {
            "schema_version": 1,
            "documents": [
                {"name": "proposal", "argument": "--file"},
                {"name": "event", "argument": "--event"},
            ],
            "constraints": [],
        }
        raw_inputs = {
            "--file": canonical_json_bytes({"kind": "review"}),
            "--event": canonical_json_bytes({"event_type": "review.coverage_completed"}),
            "--signature": b"-----BEGIN SSH SIGNATURE-----\nfixture\n",
            "--allowed-signers": b"reviewer ssh-ed25519 fixture\n",
        }
        encoded = [inline_item(argument, raw) for argument, raw in raw_inputs.items()]
        self.assertEqual(
            admission._decode_container_inline_inputs(record, encoded), raw_inputs
        )
        expected = admission._expected_inline_inputs(record)
        self.assertEqual(
            {entry["argument"] for entry in expected}, set(raw_inputs)
        )
        self.assertEqual(
            {entry["argument"]: entry["format"] for entry in expected},
            {
                "--file": "json",
                "--event": "json",
                "--signature": "bytes",
                "--allowed-signers": "bytes",
            },
        )
        for omitted in raw_inputs:
            with self.subTest(omitted=omitted), self.assertRaises(RecordError):
                admission._decode_container_inline_inputs(
                    record,
                    [entry for entry in encoded if entry["argument"] != omitted],
                )

    def test_inline_json_is_duplicate_safe_and_host_paths_are_never_opened(self) -> None:
        pred = predicate()
        arguments = ["--file", "/container-only/proposal.json"]
        raw = canonical_json_bytes({"kind": "fixture"})
        with mock.patch.object(
            admission,
            "_read_regular_json_bytes",
            side_effect=AssertionError("host path dereference"),
        ):
            documents, admitted = admission._evaluate_predicate(
                pred, arguments, {"--file": raw}
            )
        self.assertEqual(documents, {"proposal": {"kind": "fixture"}})
        self.assertEqual(admitted["file"]["bytes"], raw)

        with self.assertRaises(RecordError) as duplicate:
            admission._evaluate_predicate(
                pred,
                arguments,
                {"--file": b'{"kind":"fixture","kind":"forged"}\n'},
            )
        self.assertEqual(
            duplicate.exception.code, "duplicate_json_key"
        )

        with self.assertRaises(RecordError) as overlong_integer:
            admission._evaluate_predicate(
                pred,
                arguments,
                {"--file": b'{"kind":' + b"1" * 5000 + b"}\n"},
            )
        self.assertEqual(
            overlong_integer.exception.code,
            "driver_action_predicate_input_invalid",
        )

    def test_full_admit_uses_inline_bytes_before_executing_state(self) -> None:
        raw = canonical_json_bytes({"kind": "fixture"})
        record = broker_admission()
        record["runtime_identity"] = docker_identity()
        record["engagement_identity"] = {
            "device": os.fstat(self.engagement_fd).st_dev,
            "inode": os.fstat(self.engagement_fd).st_ino,
        }
        record["state_binding"] = {}
        broker = object.__new__(admission.DriverActionBroker)
        broker._admission = record
        broker._engagement_fd = os.dup(self.engagement_fd)
        broker._execution_deadline = time.monotonic() + 30.0

        @contextmanager
        def bound(*_args: object, **_kwargs: object):
            yield self.root

        try:
            with (
                mock.patch.object(admission, "bound_engagement_lock", bound),
                mock.patch.object(admission, "_reduce_engagement_unchecked", return_value={}),
                mock.patch.object(admission, "_neutral_tail_is_allowed", return_value=True),
                mock.patch.object(admission, "_verify_current_selected_action"),
                mock.patch.object(
                    admission,
                    "_read_regular_json_bytes",
                    side_effect=AssertionError("host path dereference"),
                ),
            ):
                admitted = broker._admit(
                    {
                        "command": "append-event",
                        "arguments": [
                            "--engagement",
                            "/target/engagements/fixture",
                            "--file",
                            "/container-only/proposal.json",
                        ],
                        "runtime_session_ref": RUNTIME_REF,
                    },
                    {"--file": raw},
                )
            self.assertEqual(admitted["file"]["bytes"], raw)
            self.assertEqual(record["status"], "armed")
        finally:
            os.close(broker._engagement_fd)

    def test_frame_and_typed_identity_validation_are_bounded(self) -> None:
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack("!I", admission._CONTAINER_FRAME_LIMIT + 1))
            with self.assertRaises(RecordError):
                admission._recv_container_frame(right)
        finally:
            left.close()
            right.close()

        left, right = socket.socketpair()
        try:
            malformed = b'{"value":' + b"1" * 5000 + b"}\n"
            left.sendall(struct.pack("!I", len(malformed)) + malformed)
            with self.assertRaises(RecordError) as rejected:
                admission._recv_container_frame(right)
            self.assertEqual(
                rejected.exception.code, "driver_action_broker_request_invalid"
            )
        finally:
            left.close()
            right.close()

        self.assertEqual(
            admission._active_runtime_identity({"os_session_id": 123}),
            {"kind": "posix_session", "os_session_id": 123},
        )
        self.assertEqual(
            admission._active_runtime_identity(
                {"os_session_id": None, "runtime_identity": docker_identity()}
            ),
            docker_identity(),
        )
        with self.assertRaises(RecordError):
            admission._active_runtime_identity(
                {
                    "os_session_id": 123,
                    "runtime_identity": docker_identity(),
                }
            )
        self.assertEqual(self.broker.tcp_endpoint[0], "127.0.0.1")

        canonical_nonce = base64.b64encode(b"\0" * client.NONCE_BYTES).decode("ascii")
        noncanonical_nonce = canonical_nonce[:-2] + "B="
        self.assertEqual(
            base64.b64decode(noncanonical_nonce, validate=True),
            base64.b64decode(canonical_nonce, validate=True),
        )
        with self.assertRaises(RecordError):
            admission.DriverActionBroker._container_nonce(noncanonical_nonce)

        invalid_manifest = copy.deepcopy(self.manifest)
        invalid_manifest["runtime_identity"]["container_id"] = "A" * 64
        with self.assertRaises(client.ContainerBrokerClientError):
            client._validate_manifest(invalid_manifest)

    def test_environment_loading_keeps_the_session_key_private(self) -> None:
        key_path = self.root / "session.key"
        key_path.write_bytes(KEY)
        os.chmod(key_path, 0o644)
        with (
            mock.patch.dict(
                os.environ,
                {client.KEY_FILE_ENV: str(key_path)},
                clear=True,
            ),
            self.assertRaises(client.ContainerBrokerClientError) as exposed,
        ):
            client.load_key_from_environment()
        self.assertEqual(exposed.exception.code, "container_broker_key_invalid")

        os.chmod(key_path, 0o400)
        with mock.patch.dict(
            os.environ,
            {client.KEY_FILE_ENV: str(key_path)},
            clear=True,
        ):
            self.assertEqual(client.load_key_from_environment(), KEY)

        inline_manifest = json.dumps(self.manifest, separators=(",", ":"))
        with mock.patch.dict(
            os.environ,
            {client.MANIFEST_ENV: inline_manifest},
            clear=True,
        ):
            self.assertEqual(client.load_manifest_from_environment(), self.manifest)

        with (
            mock.patch.dict(
                os.environ,
                {
                    client.KEY_FILE_ENV: str(key_path),
                    client.KEY_FD_ENV: "0",
                },
                clear=True,
            ),
            self.assertRaises(client.ContainerBrokerClientError) as ambiguous,
        ):
            client.load_key_from_environment()
        self.assertEqual(ambiguous.exception.code, "container_broker_key_missing")

        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, KEY + b"x")
            os.close(write_fd)
            write_fd = -1
            with (
                mock.patch.dict(
                    os.environ,
                    {client.KEY_FD_ENV: str(read_fd)},
                    clear=True,
                ),
                self.assertRaises(client.ContainerBrokerClientError) as overlong,
            ):
                client.load_key_from_environment()
            self.assertEqual(overlong.exception.code, "container_broker_key_invalid")
        finally:
            os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)

    def test_stalled_frame_does_not_terminate_the_broker(self) -> None:
        endpoint = self.broker.tcp_endpoint
        self.assertIsNotNone(endpoint)
        with mock.patch.object(admission, "_BROKER_IO_TIMEOUT_SECONDS", 0.05):
            stalled = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                stalled.connect(endpoint)
                stalled.sendall(struct.pack("!I", 10) + b"{")
                time.sleep(0.15)
            finally:
                stalled.close()

        poisoned = {
            "schema_version": 1,
            "message_kind": "request",
            "runtime_identity": docker_identity(),
            "runtime_session_ref": RUNTIME_REF,
            "action_id": ACTION_ID,
            "deadline_ref": self.manifest["deadline_ref"],
            "nonce": base64.b64encode(b"u" * client.NONCE_BYTES).decode("ascii"),
            "payload_sha256": "sha256:" + "0" * 64,
            "payload": {"request_kind": "\ud800"},
            "mac_base64": "",
        }
        poisoned_raw = json.dumps(
            poisoned, ensure_ascii=True, separators=(",", ":")
        ).encode("ascii")
        corrupt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            corrupt.connect(endpoint)
            corrupt.sendall(struct.pack("!I", len(poisoned_raw)) + poisoned_raw)
            corrupt.shutdown(socket.SHUT_WR)
            while corrupt.recv(65536):
                pass
        finally:
            corrupt.close()

        observed: list[dict[str, object]] = []

        def execute_stop(request: dict[str, object]) -> tuple[int, bytes]:
            observed.append(copy.deepcopy(request))
            return 0, canonical_json_bytes({})

        self.broker._execute_stop = execute_stop  # type: ignore[method-assign]
        returncode, output = client.forward_stop(
            self.manifest,
            KEY,
            hook_session_ref=HOOK_REF,
            stop_hook_active=False,
            request_ref="sha256:" + "f" * 64,
        )
        self.assertEqual((returncode, json.loads(output)), (0, {}))
        self.assertEqual(len(observed), 1)

    def test_action_request_budget_cannot_starve_stop(self) -> None:
        raw = canonical_json_bytes({"kind": "fixture"})
        action_payload = {
            "request_kind": "action",
            "command": "append-event",
            "arguments": ["--file", "/container-only/proposal.json"],
            "runtime_session_ref": RUNTIME_REF,
            "inline_inputs": [inline_item("--file", raw)],
        }
        for value in range(admission._CONTAINER_ACTION_NONCE_BUDGET):
            envelope = client._envelope(
                self.manifest,
                KEY,
                action_payload,
                nonce=value.to_bytes(client.NONCE_BYTES, "big"),
            )
            request, inline_inputs, _nonce = self.broker._authenticate_container_request(
                envelope
            )
            self.assertEqual(request["command"], "append-event")
            self.assertEqual(inline_inputs, {"--file": raw})

        exhausted = client._envelope(
            self.manifest,
            KEY,
            action_payload,
            nonce=(100).to_bytes(client.NONCE_BYTES, "big"),
        )
        with self.assertRaises(RecordError) as rejected:
            self.broker._authenticate_container_request(exhausted)
        self.assertEqual(
            rejected.exception.code,
            "driver_action_broker_request_budget_exhausted",
        )

        stop_payload = {
            "request_kind": "session_end_check",
            "runtime_session_ref": RUNTIME_REF,
            "hook_session_ref": HOOK_REF,
            "stop_hook_active": False,
            "request_ref": "sha256:" + "d" * 64,
        }
        stop = client._envelope(
            self.manifest,
            KEY,
            stop_payload,
            nonce=(101).to_bytes(client.NONCE_BYTES, "big"),
        )
        request, inline_inputs, _nonce = self.broker._authenticate_container_request(
            stop
        )
        self.assertEqual(request["request_kind"], "session_end_check")
        self.assertIsNone(inline_inputs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
