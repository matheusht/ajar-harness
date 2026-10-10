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
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import container_broker_client as client
import driver_action_admission as admission
import network_scope
from engagement_records import RecordError, canonical_json_bytes, sha256_bytes
from network_scope_test_support import scope_with_network_policy


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
        "provider_max_tokens": 32768,
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
        (self.root / ".record-kernel.lock").touch()
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

    def test_target_fetch_uncertainty_and_stale_admission_block_real_broker_replay(self) -> None:
        scope = scope_with_network_policy(
            host="sink.invalid", path="/allowed", method="GET"
        )
        (self.root / "scope.md").write_bytes(scope)
        state = {"scope_hash": sha256_bytes(scope)}
        self.broker._admission["state_binding"] = {"scope_hash": state["scope_hash"]}
        logical_request = client.target_fetch_request_id(
            self.manifest, url="https://sink.invalid/allowed", method="GET"
        )

        @contextmanager
        def bound(*_args: object, **_kwargs: object):
            yield self.root

        with (
            mock.patch.object(admission, "bound_engagement_lock", bound),
            mock.patch.object(admission, "_reduce_engagement_unchecked", return_value=state),
            mock.patch.object(admission, "_neutral_tail_is_allowed", return_value=True),
            mock.patch.object(
                network_scope,
                "pinned_request",
                side_effect=TimeoutError("lost receipt"),
            ) as effect,
        ):
            first = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=logical_request,
                url="https://sink.invalid/allowed",
                method="GET",
            )
            replay = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=logical_request,
                url="https://sink.invalid/allowed",
                method="GET",
            )
        self.assertEqual((first[0], replay[0]), (1, 1))
        self.assertEqual(effect.call_count, 1)

        changed_scope = scope_with_network_policy(
            host="sink.invalid", path="/reattested", method="GET"
        )
        (self.root / "scope.md").write_bytes(changed_scope)
        changed_state = {"scope_hash": sha256_bytes(changed_scope)}
        with (
            mock.patch.object(admission, "bound_engagement_lock", bound),
            mock.patch.object(
                admission, "_reduce_engagement_unchecked", return_value=changed_state
            ),
            mock.patch.object(admission, "_neutral_tail_is_allowed", return_value=True),
            mock.patch.object(
                network_scope,
                "pinned_request",
                side_effect=AssertionError("effect began for stale admission"),
            ),
        ):
            stale = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=client.target_fetch_request_id(
                    self.manifest,
                    url="https://sink.invalid/reattested",
                    method="GET",
                ),
                url="https://sink.invalid/reattested",
                method="GET",
            )
        self.assertEqual(stale[0], 1)

    def test_target_fetch_real_broker_reaches_only_the_approved_owned_sink(self) -> None:
        sink = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sink.bind(("127.0.0.1", 0))
        sink.listen(1)
        sink.settimeout(5.0)
        sink_port = sink.getsockname()[1]
        sink_requests: list[bytes] = []

        def serve() -> None:
            try:
                connection, _ = sink.accept()
                with connection:
                    request = bytearray()
                    while b"\r\n\r\n" not in request:
                        request.extend(connection.recv(4096))
                    sink_requests.append(bytes(request))
                    connection.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
                    )
            finally:
                sink.close()

        server = threading.Thread(target=serve, daemon=True)
        server.start()
        scope = scope_with_network_policy(
            host="sink.invalid", path="/allowed", method="GET"
        )
        state = {"scope_hash": sha256_bytes(scope)}
        self.broker._admission["state_binding"] = {"scope_hash": state["scope_hash"]}

        @contextmanager
        def bound(*_args: object, **_kwargs: object):
            yield self.root

        class FixtureTls:
            @staticmethod
            def wrap_socket(raw: socket.socket, *, server_hostname: str) -> socket.socket:
                self.assertEqual(server_hostname, "sink.invalid")
                return raw

        original_request = network_scope.pinned_request
        governed_read = admission.read_governed_file
        real_create_connection = socket.create_connection

        def fixture_request(**arguments: object) -> tuple[int, list[tuple[str, str]], bytes]:
            return original_request(
                **arguments,
                resolver=lambda _host, _port: "93.184.216.34",
            )

        def fixture_connection(_address: object, *, timeout: float) -> socket.socket:
            return real_create_connection(("127.0.0.1", sink_port), timeout=timeout)

        with (
            mock.patch.object(admission, "bound_engagement_lock", bound),
            mock.patch.object(admission, "_reduce_engagement_unchecked", return_value=state),
            mock.patch.object(
                admission,
                "read_governed_file",
                side_effect=lambda path, **kwargs: (
                    scope
                    if Path(path).name == "scope.md"
                    else governed_read(path, **kwargs)
                ),
            ),
            mock.patch.object(admission, "_neutral_tail_is_allowed", return_value=True),
            mock.patch.object(network_scope, "pinned_request", side_effect=fixture_request),
            mock.patch.object(
                network_scope.socket,
                "create_connection",
                side_effect=fixture_connection,
            ),
            mock.patch.object(
                network_scope.ssl,
                "create_default_context",
                return_value=FixtureTls(),
            ),
        ):
            approved = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=client.target_fetch_request_id(
                    self.manifest, url="https://sink.invalid/allowed", method="GET"
                ),
                url="https://sink.invalid/allowed",
                method="GET",
            )
            denied_host = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=client.target_fetch_request_id(
                    self.manifest, url="https://other.invalid/allowed", method="GET"
                ),
                url="https://other.invalid/allowed",
                method="GET",
            )
            denied_path = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=client.target_fetch_request_id(
                    self.manifest, url="https://sink.invalid/denied", method="GET"
                ),
                url="https://sink.invalid/denied",
                method="GET",
            )
            with self.assertRaises(client.ContainerBrokerClientError):
                client.forward_target_fetch(
                    self.manifest,
                    KEY,
                    request_id=client.target_fetch_request_id(
                        self.manifest, url="https://sink.invalid/allowed", method="POST"
                    ),
                    url="https://sink.invalid/allowed",
                    method="POST",
                )
        server.join(timeout=5.0)
        self.assertEqual((approved[0], denied_host[0], denied_path[0]), (0, 1, 1))
        self.assertEqual(len(sink_requests), 1)
        self.assertIn(b"GET /allowed HTTP/1.1", sink_requests[0])

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

    def test_wire_schema_versions_require_integer_one(self) -> None:
        invalid_manifest = copy.deepcopy(self.manifest)
        invalid_manifest["schema_version"] = True
        with self.assertRaises(client.ContainerBrokerClientError):
            client.validate_manifest(invalid_manifest)

        invalid_manifest = copy.deepcopy(self.manifest)
        invalid_manifest["inline_inputs"][0]["format"] = []
        with self.assertRaises(client.ContainerBrokerClientError):
            client.validate_manifest(invalid_manifest)

        with self.assertRaises(client.ContainerBrokerClientError):
            client._validate_relay_request(
                {
                    "schema_version": True,
                    "request_kind": "action",
                    "command": "validate",
                    "arguments": [],
                }
            )

        request_pair = socket.socketpair()
        try:
            request_pair[0].sendall(
                canonical_json_bytes(
                    {
                        "schema_version": True,
                        "command": "validate",
                        "arguments": [],
                        "runtime_session_ref": RUNTIME_REF,
                    }
                )
            )
            request_pair[0].shutdown(socket.SHUT_WR)
            with self.assertRaises(RecordError) as bad_request:
                self.broker._read_request(request_pair[1])
            self.assertEqual(
                bad_request.exception.code,
                "driver_action_broker_request_invalid",
            )
        finally:
            request_pair[0].close()
            request_pair[1].close()

        response = self.broker._container_response(
            request_nonce=base64.b64encode(b"v" * 32).decode("ascii"),
            returncode=0,
            output=b"{}\n",
        )
        response["schema_version"] = True
        unsigned = dict(response)
        unsigned.pop("mac_base64")
        response["mac_base64"] = client._mac(KEY, client.RESPONSE_DOMAIN, unsigned)
        with self.assertRaises(client.ContainerBrokerClientError):
            client._validate_response(
                self.manifest, KEY, response, response["request_nonce"]
            )

        envelope = client._envelope(
            self.manifest,
            KEY,
            {
                "request_kind": "action",
                "command": "validate",
                "arguments": [],
                "runtime_session_ref": RUNTIME_REF,
                "inline_inputs": [],
            },
        )
        envelope["schema_version"] = True
        unsigned_envelope = dict(envelope)
        unsigned_envelope.pop("mac_base64")
        envelope["mac_base64"] = client._mac(
            KEY, client.REQUEST_DOMAIN, unsigned_envelope
        )
        with self.assertRaises(RecordError) as bad_envelope:
            self.broker._authenticate_container_request(envelope)
        self.assertEqual(bad_envelope.exception.code, "driver_action_scope_mismatch")

    def test_unhashable_target_fetch_methods_fail_as_protocol_errors(self) -> None:
        url = "https://sink.invalid/allowed"
        request_id = client.target_fetch_request_id(
            self.manifest, url=url, method=[]  # type: ignore[arg-type]
        )
        with self.assertRaises(client.ContainerBrokerClientError):
            client._validate_relay_request(
                {
                    "schema_version": 1,
                    "request_kind": "target_fetch",
                    "request_id": request_id,
                    "url": url,
                    "method": [],
                }
            )
        with self.assertRaises(client.ContainerBrokerClientError):
            client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=request_id,
                url=url,
                method=[],  # type: ignore[arg-type]
            )

        envelope = client._envelope(
            self.manifest,
            KEY,
            {
                "request_kind": "target_fetch",
                "operation": "target_fetch",
                "request_id": request_id,
                "url": url,
                "method": [],
                "runtime_session_ref": RUNTIME_REF,
            },
        )
        with self.assertRaises(RecordError) as rejected:
            self.broker._authenticate_container_request(envelope)
        self.assertEqual(rejected.exception.code, "driver_target_fetch_invalid")

        provider_payload = {
            "request_kind": "provider_request",
            "method": "POST",
            "path": [],
            "headers": {},
            "body_base64": base64.b64encode(b"{}").decode("ascii"),
            "runtime_session_ref": RUNTIME_REF,
        }
        provider_envelope = client._envelope(self.manifest, KEY, provider_payload)
        with self.assertRaises(RecordError) as provider_rejected:
            self.broker._authenticate_container_request(provider_envelope)
        self.assertEqual(
            provider_rejected.exception.code, "driver_provider_request_invalid"
        )

        malformed_body = canonical_json_bytes(
            {
                "model": "fixture-container-model",
                "max_tokens": 1,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": [],
                                "source": {
                                    "type": "url",
                                    "url": "https://untrusted.invalid/document",
                                },
                            }
                        ],
                    }
                ],
            }
        )
        capability_payload = {
            **provider_payload,
            "path": "/v1/messages",
            "body_base64": base64.b64encode(malformed_body).decode("ascii"),
        }
        capability_envelope = client._envelope(
            self.manifest, KEY, capability_payload
        )
        with self.assertRaises(RecordError) as capability_rejected:
            self.broker._authenticate_container_request(capability_envelope)
        self.assertEqual(
            capability_rejected.exception.code, "driver_provider_request_invalid"
        )

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
            client.validate_manifest(invalid_manifest)

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
        original_recv_exact = admission._recv_exact
        frame_timed_out = threading.Event()

        def observe_frame_timeout(
            connection: socket.socket,
            size: int,
            *,
            cancel_event: threading.Event | None = None,
        ) -> bytes:
            try:
                return original_recv_exact(connection, size, cancel_event=cancel_event)
            except socket.timeout:
                if size == 10:
                    frame_timed_out.set()
                raise

        with (
            mock.patch.object(admission, "_BROKER_IO_TIMEOUT_SECONDS", 0.05),
            mock.patch.object(admission, "_recv_exact", side_effect=observe_frame_timeout),
        ):
            stalled = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                stalled.connect(endpoint)
                stalled.sendall(struct.pack("!I", 10) + b"{")
                self.assertTrue(frame_timed_out.wait(1.0))
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

    def test_unix_broker_request_has_one_total_read_deadline(self) -> None:
        clock = {"now": 0.0}
        raw = canonical_json_bytes(
            {
                "schema_version": 1,
                "command": "validate",
                "arguments": [],
                "runtime_session_ref": RUNTIME_REF,
            }
        )

        class SlowConnection:
            def __init__(self) -> None:
                self.data = bytearray(raw)
                self.timeout: float | None = 2.0

            def gettimeout(self) -> float | None:
                return self.timeout

            def settimeout(self, timeout: float | None) -> None:
                self.timeout = timeout

            def recv(self, size: int) -> bytes:
                if not self.data:
                    return b""
                delay = 0.5
                if self.timeout is not None and self.timeout < delay:
                    raise socket.timeout("total request deadline")
                clock["now"] += delay
                count = min(16, size, len(self.data))
                chunk = bytes(self.data[:count])
                del self.data[:count]
                return chunk

        connection = SlowConnection()
        with (
            mock.patch.object(admission.time, "monotonic", side_effect=lambda: clock["now"]),
            self.assertRaises(socket.timeout),
        ):
            self.broker._read_request(connection)  # type: ignore[arg-type]
        self.assertEqual(connection.timeout, 2.0)

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

    def test_v3_filing_action_is_stamped_to_the_authenticated_broker(self) -> None:
        forged = {
            "action": {
                "argument": "--action-file",
                "value": {
                    "action_kind": "revise-finding",
                    "action_version": 3,
                    "executor_id": "forged-executor",
                    "session_id": "forged-session",
                },
            }
        }
        with mock.patch.object(
            admission,
            "_parent_recorder_identity",
            return_value=("local-uid-501:broker", "session-posix-501-77"),
        ):
            stamped = admission._stamp_parent_recorder_documents(
                forged,
                command="request-authority",
                runtime_session_ref=RUNTIME_REF,
                runtime_model="fixture-container-model",
            )
        action = stamped["action"]["value"]
        self.assertEqual(action["action_version"], 3)
        self.assertEqual(action["executor_id"], "local-uid-501:broker")
        self.assertEqual(action["session_id"], "session-posix-501-77")
        malformed_version = {
            "action": {
                "argument": "--action-file",
                "value": {"action_version": []},
            }
        }
        with mock.patch.object(
            admission,
            "_parent_recorder_identity",
            return_value=("local-uid-501:broker", "session-posix-501-77"),
        ):
            untouched = admission._stamp_parent_recorder_documents(
                malformed_version,
                command="request-authority",
                runtime_session_ref=RUNTIME_REF,
                runtime_model="fixture-container-model",
            )
        self.assertEqual(untouched["action"]["value"]["action_version"], [])

    def test_network_receipt_is_redacted_bounded_and_persistent(self) -> None:
        receipt = {
            "operation": "provider_request", "method": "POST",
            "host": "api.anthropic.com", "path": "/v1/messages?beta=true",
            "status": "uncertain",
        }
        self.broker._persist_network_receipt(receipt)
        path = self.root / admission.NETWORK_RECEIPTS_FILE
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(rows[-1]["status"], "uncertain")
        self.assertEqual(rows[-1]["runtime_session_ref"], RUNTIME_REF)
        self.assertNotIn("headers", rows[-1])
        self.assertNotIn("body", rows[-1])

        self.broker.close()
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
        self.assertEqual(self.broker.network_audit[-1]["status"], "uncertain")

    def test_recovered_target_receipt_tombstones_only_same_admission_request(self) -> None:
        scope = scope_with_network_policy(
            host="sink.invalid", path="/allowed", method="GET"
        )
        state = {"scope_hash": sha256_bytes(scope)}
        admission_value = broker_admission()
        admission_value["state_binding"] = {"scope_hash": state["scope_hash"]}
        self.broker._admission["state_binding"] = {"scope_hash": state["scope_hash"]}
        request_id = client.target_fetch_request_id(
            self.manifest, url="https://sink.invalid/allowed", method="GET"
        )
        self.broker._persist_network_receipt({
            "operation": "target_fetch",
            "request_id": request_id,
            "method": "GET",
            "url_sha256": sha256_bytes(b"https://sink.invalid/allowed"),
            "status": 200,
        })
        # A prior session must remain auditable without consuming this admission's request budget.
        self.broker._persist_network_receipt({
            "operation": "target_fetch",
            "request_id": "sha256:" + "f" * 64,
            "method": "GET",
            "url_sha256": sha256_bytes(b"https://sink.invalid/other"),
            "status": "denied_or_uncertain",
        })
        path = self.root / admission.NETWORK_RECEIPTS_FILE
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]["runtime_session_ref"] = "other-session"
        path.write_bytes(b"".join(canonical_json_bytes(row) for row in rows))

        self.broker.close()
        self.broker = admission.DriverActionBroker(
            engagement_fd=self.engagement_fd,
            logical_engagement=self.root,
            admission=admission_value,
            execution_deadline=time.monotonic() + 30.0,
            docker_identity={
                "container_id": CONTAINER_ID,
                "container_config_digest": CONFIG_DIGEST,
            },
            docker_session_key=KEY,
        )
        self.broker.activate_docker()
        self.manifest = self.broker.container_manifest()

        @contextmanager
        def bound(*_args: object, **_kwargs: object):
            yield self.root

        with (
            mock.patch.object(admission, "bound_engagement_lock", bound),
            mock.patch.object(admission, "_reduce_engagement_unchecked", return_value=state),
            mock.patch.object(admission, "read_governed_file", return_value=scope),
            mock.patch.object(admission, "_neutral_tail_is_allowed", return_value=True),
            mock.patch.object(network_scope, "pinned_request") as sink,
        ):
            replay = client.forward_target_fetch(
                self.manifest,
                KEY,
                request_id=request_id,
                url="https://sink.invalid/allowed",
                method="GET",
            )
        self.assertEqual(replay[0], 1)
        sink.assert_not_called()
        self.assertEqual(self.broker._network_gateway.request_budget, 32)
        self.assertEqual(self.broker._network_gateway._started, set())
        self.assertEqual(self.broker._network_gateway._uncertain, {request_id})

    def test_target_contact_crash_retains_request_tombstone(self) -> None:
        # Failure modes: death after contact but before response, then a restarted parent
        # with the same admission must neither forget the ID nor contact the target again.
        scope = network_scope.scope_with_network_policy(
            host="sink.invalid", path="/allowed", method="GET"
        )
        (self.root / "scope.md").write_bytes(scope)
        state = {"scope_hash": sha256_bytes(scope)}
        self.broker._admission["state_binding"] = {"scope_hash": state["scope_hash"]}
        request_id = client.target_fetch_request_id(
            self.manifest, url="https://sink.invalid/allowed", method="GET"
        )
        request = {
            "request_id": request_id,
            "url": "https://sink.invalid/allowed",
            "method": "GET",
        }
        with (
            mock.patch.object(admission, "_reduce_engagement_unchecked", return_value=state),
            mock.patch.object(admission, "_neutral_tail_is_allowed", return_value=True),
            mock.patch.object(network_scope, "pinned_request", side_effect=SystemExit("parent died")) as sink,
        ):
            with self.assertRaises(SystemExit):
                self.broker._execute_target_fetch(request)
        sink.assert_called_once()
        receipt_path = self.root / admission.NETWORK_RECEIPTS_FILE
        self.assertTrue(receipt_path.exists(), "contact began without a durable request marker")
        self.broker.close()
        recovered_admission = broker_admission()
        recovered_admission["state_binding"] = {"scope_hash": state["scope_hash"]}
        self.broker = admission.DriverActionBroker(
            engagement_fd=self.engagement_fd,
            logical_engagement=self.root,
            admission=recovered_admission,
            execution_deadline=time.monotonic() + 30.0,
            docker_identity={"container_id": CONTAINER_ID, "container_config_digest": CONFIG_DIGEST},
            docker_session_key=KEY,
        )
        self.broker.activate_docker()
        with mock.patch.object(network_scope, "pinned_request") as repeated_contact:
            result = self.broker._execute_target_fetch(request)
        self.assertEqual(result[0], 1)
        repeated_contact.assert_not_called()
        receipts = [json.loads(line) for line in receipt_path.read_bytes().splitlines()]
        self.assertTrue(any(row.get("request_id") == request_id for row in receipts))

    def test_receipt_rotation_keeps_current_target_request_marker(self) -> None:
        # Failure mode: unrelated provider receipts evict the only marker before restart.
        request_id = "sha256:" + "a" * 64
        marker = {
            "operation": "target_fetch", "request_id": request_id,
            "method": "GET", "url_sha256": sha256_bytes(b"https://sink.invalid/allowed"),
            "status": "begun",
        }
        with mock.patch.object(admission, "NETWORK_RECEIPTS_MAX_ROWS", 4):
            self.broker._persist_network_receipt(marker)
            for _ in range(5):
                self.broker._persist_network_receipt({
                    "operation": "provider_request", "method": "POST",
                    "host": "api.anthropic.com", "path": "/v1/messages",
                    "status": "complete",
                })
        rows = [json.loads(line) for line in (self.root / admission.NETWORK_RECEIPTS_FILE).read_bytes().splitlines()]
        self.assertTrue(any(row.get("request_id") == request_id for row in rows))

    def test_corrupt_network_receipt_blocks_restart_and_persist_failure_is_not_acknowledged(self) -> None:
        path = self.root / admission.NETWORK_RECEIPTS_FILE
        before = list(self.broker.network_audit)
        with mock.patch.object(admission, "atomic_write", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                self.broker._persist_network_receipt({
                    "operation": "target_fetch", "method": "GET",
                    "request_id": "sha256:" + "b" * 64,
                    "url_sha256": "sha256:" + "a" * 64, "status": "uncertain",
                })
        self.assertEqual(self.broker.network_audit, before)

        self.broker.close()
        path.write_bytes(b'{"schema_version":1')
        with self.assertRaises(RecordError) as corrupt:
            admission.DriverActionBroker(
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
        self.assertEqual(corrupt.exception.code, "driver_network_receipt_invalid")

        path.write_text('{"schema_version":1,"operation":[]}\n')
        with self.assertRaises(RecordError) as malformed_operation:
            admission.DriverActionBroker(
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
        self.assertEqual(
            malformed_operation.exception.code, "driver_network_receipt_invalid"
        )
        with self.assertRaises(RecordError) as boolean_version:
            admission.DriverActionBroker._decode_network_receipts(
                admission.canonical_json_bytes(
                    {
                        "schema_version": True,
                        "runtime_session_ref": "session",
                        "action_id": "action",
                        "operation": "provider_request",
                        "method": "POST",
                        "status": "ok",
                    }
                )
            )
        self.assertEqual(
            boolean_version.exception.code, "driver_network_receipt_invalid"
        )

        path.unlink()
        outside = self.root / "outside-receipt"
        outside.write_text('{}\n')
        path.symlink_to(outside)
        with self.assertRaises(RecordError) as symlinked:
            admission.DriverActionBroker(
                engagement_fd=self.engagement_fd,
                logical_engagement=self.root,
                admission=broker_admission(),
                execution_deadline=time.monotonic() + 30.0,
                docker_identity={"container_id": CONTAINER_ID, "container_config_digest": CONFIG_DIGEST},
                docker_session_key=KEY,
            )
        self.assertEqual(symlinked.exception.code, "driver_network_receipt_invalid")

        path.unlink()
        os.link(outside, path)
        with self.assertRaises(RecordError) as hardlinked:
            admission.DriverActionBroker(
                engagement_fd=self.engagement_fd,
                logical_engagement=self.root,
                admission=broker_admission(),
                execution_deadline=time.monotonic() + 30.0,
                docker_identity={"container_id": CONTAINER_ID, "container_config_digest": CONFIG_DIGEST},
                docker_session_key=KEY,
            )
        self.assertEqual(hardlinked.exception.code, "driver_network_receipt_invalid")

    def test_close_cancels_stalled_container_worker_within_absolute_deadline(self) -> None:
        assert self.broker.tcp_endpoint is not None

        class ObservedStopEvent(threading.Event):
            def __init__(self) -> None:
                super().__init__()
                self.read_waiting = threading.Event()

            def wait(self, timeout: float | None = None) -> bool:
                self.read_waiting.set()
                return super().wait(timeout)

        stop = ObservedStopEvent()
        self.broker._stop = stop
        peer = socket.create_connection(self.broker.tcp_endpoint, timeout=1.0)
        try:
            # Withhold the body until the worker reaches the cancellation-aware read wait.
            peer.sendall(struct.pack("!I", 1))
            self.assertTrue(stop.read_waiting.wait(1.0))
            with self.broker._container_workers_lock:
                self.assertTrue(self.broker._container_workers)
            started = time.monotonic()
            self.broker.close()
            self.assertLess(time.monotonic() - started, 0.5)
            with self.broker._container_workers_lock:
                self.assertFalse(self.broker._container_workers)
        finally:
            peer.close()

    def test_expired_deadline_shutdown_is_bounded_closes_descriptors_and_is_retry_safe(self) -> None:
        worker = threading.Thread(target=lambda: time.sleep(1.0), daemon=True)
        with self.broker._container_workers_lock:
            self.broker._container_workers.add(worker)
        worker.start()
        self.broker._execution_deadline = time.monotonic() - 1.0
        started = time.monotonic()
        with self.assertRaises(RecordError) as raised:
            self.broker.close()
        self.assertEqual(raised.exception.code, "driver_action_broker_shutdown_timeout")
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(self.broker._closed)
        self.assertEqual(self.broker._engagement_fd, -1)
        self.broker.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
