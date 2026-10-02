#!/usr/bin/env python3
"""Workflow checks for the external network authorization boundary.

The default lane is credential-free and uses only loopback fixtures.  The Docker lane is selected
with ``HARNESS_RUN_EGRESS_DOCKER=1`` and never pulls an image.  Results can be saved with
``--result PATH``; the emitted JSON contains the exact image and checks that ran.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import time
import unittest
from pathlib import Path
from unittest import mock

import container_session_supervisor as supervisor
from network_scope_test_support import scope_with_network_policy


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_IMAGE = (
    "golang@sha256:699337d620559a59b4a2bb298ad59611e535d2ee755a34cf2d2a98f37578dc80"
)
RESULTS: list[dict[str, object]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    RESULTS.append({"name": name, "passed": passed, "detail": detail})


class ExternalNetworkPolicyWorkflow(unittest.TestCase):
    def test_provider_body_is_bound_to_admitted_model_and_output_ceiling(self) -> None:
        import driver_action_admission as admission

        valid = json.dumps({"model": "admitted-model", "max_tokens": 32, "messages": []}).encode()
        admission._validate_provider_inference_body(
            valid, expected_model="admitted-model", max_tokens=32
        )
        for changed in (
            {"model": "other-model", "max_tokens": 32, "messages": []},
            {"model": "admitted-model", "max_tokens": 33, "messages": []},
        ):
            with self.assertRaises(admission.RecordError):
                admission._validate_provider_inference_body(
                    json.dumps(changed).encode(),
                    expected_model="admitted-model",
                    max_tokens=32,
                )

    def test_provider_proxy_accepts_only_exact_optional_beta_query(self) -> None:
        allowed = (
            b"POST /v1/messages HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
            b"POST /v1/messages?beta=true HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
        )
        for request in allowed:
            left, right = socket.socketpair()
            try:
                left.sendall(request)
                _headers, body, path = supervisor._ProviderProxy._read_request(right)
                self.assertEqual(body, b"")
                self.assertIn(path, {"/v1/messages", "/v1/messages?beta=true"})
            finally:
                left.close(); right.close()
        for path in ("/v1/messages?beta=false", "/v1/messages?beta=true&x=1", "/v1/messages/"):
            left, right = socket.socketpair()
            try:
                left.sendall(f"POST {path} HTTP/1.1\r\nContent-Length: 0\r\n\r\n".encode())
                with self.assertRaises(supervisor.SupervisorError):
                    supervisor._ProviderProxy._read_request(right)
            finally:
                left.close(); right.close()

    def test_provider_request_read_has_one_total_deadline(self) -> None:
        clock = {"now": 0.0}

        class SlowConnection:
            def __init__(self) -> None:
                self.chunks = [
                    b"POST /v1/messages HTTP/1.1\r\nContent-Length: 3\r\n\r\n",
                    b"a",
                    b"b",
                    b"c",
                ]
                self.timeout: float | None = None

            def settimeout(self, timeout: float) -> None:
                self.timeout = timeout

            def recv(self, _size: int) -> bytes:
                delay = 0.4
                if self.timeout is not None and self.timeout < delay:
                    raise socket.timeout("total request deadline")
                clock["now"] += delay
                return self.chunks.pop(0)

        connection = SlowConnection()
        with (
            mock.patch.object(supervisor, "PROVIDER_IO_TIMEOUT_SECONDS", 1.0),
            mock.patch.object(supervisor.time, "monotonic", side_effect=lambda: clock["now"]),
            self.assertRaises(socket.timeout),
        ):
            supervisor._ProviderProxy._read_request(connection)  # type: ignore[arg-type]

    def test_provider_stream_accepts_exact_optional_beta_query(self) -> None:
        import container_broker_client as client

        manifest = {"endpoint": {"host": "127.0.0.1", "port": 1}}
        response_frames = iter((
            {
                "returncode": 0,
                "output": client.canonical_json_bytes(
                    {"stream": "headers", "status": 200, "headers": []}
                ),
            },
            {
                "returncode": 0,
                "output": client.canonical_json_bytes({"stream": "end", "sequence": 0}),
            },
        ))
        connection = mock.Mock()
        received_headers: list[tuple[int, list[list[str]]]] = []
        with (
            mock.patch.object(client, "validate_manifest", return_value=manifest),
            mock.patch.object(client, "_envelope", return_value={"nonce": "fixture"}),
            mock.patch.object(client, "send_frame"),
            mock.patch.object(client, "recv_frame", side_effect=lambda _connection: next(response_frames)),
            mock.patch.object(client, "_validate_response", side_effect=lambda _manifest, _key, frame, _nonce: frame),
            mock.patch.object(client.socket, "socket", return_value=connection),
        ):
            total = client.stream_provider(
                manifest,
                b"key",
                path="/v1/messages?beta=true",
                headers={},
                body=b"{}",
                on_headers=lambda status, headers: received_headers.append((status, headers)),
                on_chunk=lambda _chunk: self.fail("unexpected provider chunk"),
            )
        self.assertEqual(total, 0)
        self.assertEqual(received_headers, [(200, [])])
    def test_expired_absolute_deadline_stops_before_dns(self) -> None:
        import network_scope

        scope = scope_with_network_policy(
            host="fixture.invalid", path="/allowed", method="GET"
        )
        policy = network_scope.parse_network_policy(
            scope, expected_scope_hash=network_scope.sha256_bytes(scope)
        )
        resolver = mock.Mock(side_effect=AssertionError("expired request reached DNS"))
        with self.assertRaises(network_scope.NetworkScopeError):
            network_scope.pinned_request(
                policy=policy, operation="target_fetch",
                url="https://fixture.invalid/allowed", method="GET",
                deadline=time.monotonic() - 0.001, resolver=resolver,
            )
        self.assertEqual(resolver.call_count, 0)

    def test_socket_matrix_is_fail_closed(self) -> None:
        decide = getattr(supervisor, "_socket_policy", None)
        self.assertTrue(callable(decide), "missing inherited socket policy")
        allowed = (
            (socket.AF_UNIX, socket.SOCK_STREAM, 0),
            (socket.AF_UNIX, socket.SOCK_SEQPACKET, 0),
            (socket.AF_INET, socket.SOCK_STREAM, 0),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP),
        )
        denied = (
            (socket.AF_INET6, socket.SOCK_STREAM, 0),
            (socket.AF_INET, socket.SOCK_DGRAM, 0),
            (socket.AF_INET, socket.SOCK_RAW, 0),
            (getattr(socket, "AF_PACKET", 17), socket.SOCK_RAW, 0),
            (getattr(socket, "AF_NETLINK", 16), socket.SOCK_RAW, 0),
            (getattr(socket, "AF_VSOCK", 40), socket.SOCK_STREAM, 0),
        )
        for values in allowed:
            with self.subTest(values=values):
                self.assertTrue(decide(*values))
        for values in denied:
            with self.subTest(values=values):
                self.assertFalse(decide(*values))
        record("socket-family-type-protocol-matrix", True)

    def test_connect_copies_sockaddr_once_and_emulates_on_exact_duplicate(self) -> None:
        emulate = getattr(supervisor, "_emulate_brokered_connect", None)
        self.assertTrue(callable(emulate), "missing connect emulator")
        notification = supervisor._SeccompNotif()
        notification.identifier = 9
        notification.pid = 123
        notification.data.architecture = supervisor.AUDIT_ARCH_AARCH64
        notification.data.number = supervisor.AARCH64_NR_CONNECT
        notification.data.arguments[0] = 7
        notification.data.arguments[1] = 0x1000
        notification.data.arguments[2] = 16
        copied = (
            struct.pack("=H", socket.AF_INET)
            + struct.pack("!H", 443)
            + socket.inet_aton("203.0.113.9")
            + b"\0" * 8
        )
        calls: list[tuple[str, object]] = []

        class Duplicate:
            family = socket.AF_INET
            type = socket.SOCK_STREAM
            proto = socket.IPPROTO_TCP

            def connect(self, address: object) -> None:
                calls.append(("connect", address))

            def detach(self) -> int:
                return 71

        with (
            mock.patch.object(supervisor, "_notification_id_valid"),
            mock.patch.object(supervisor, "_read_tracee_memory", return_value=copied) as read,
            mock.patch.object(supervisor, "_pidfd_getfd", return_value=71),
            mock.patch.object(supervisor.socket, "socket", return_value=Duplicate()),
            mock.patch.object(supervisor.os, "close"),
        ):
            result = emulate(notification, 55, ("127.0.0.1", 48123))
        self.assertEqual(result.error, 0)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(calls, [("connect", ("127.0.0.1", 48123))])
        record("single-copy-connect-emulation", True)

    def test_signed_scope_policy_defaults_deny_and_detects_tamper(self) -> None:
        try:
            import network_scope
        except ImportError as exc:
            self.fail(f"missing parent network policy gateway: {exc}")
        scope = scope_with_network_policy(
            host="fixture.invalid", path="/allowed", method="GET"
        )
        digest = network_scope.sha256_bytes(scope)
        policy = network_scope.parse_network_policy(scope, expected_scope_hash=digest)
        self.assertTrue(policy.allows("target_fetch", "https", "fixture.invalid", 443, "/allowed", "GET"))
        boolean_version_scope = scope.replace(b'"schema_version":1', b'"schema_version":true')
        with self.assertRaises(network_scope.NetworkScopeError):
            network_scope.parse_network_policy(
                boolean_version_scope,
                expected_scope_hash=network_scope.sha256_bytes(boolean_version_scope),
            )
        for values in (
            ("target_fetch", "https", "denied.invalid", 443, "/allowed", "GET"),
            ("target_fetch", "https", "fixture.invalid", 443, "/denied", "GET"),
            ("target_fetch", "https", "fixture.invalid", 443, "/allowed", "POST"),
        ):
            with self.subTest(values=values):
                self.assertFalse(policy.allows(*values))
        with self.assertRaises(network_scope.NetworkScopeError):
            network_scope.parse_network_policy(scope + b"tamper", expected_scope_hash=digest)
        record("signed-scope-destination-path-method-and-tamper", True)

    def test_policy_rejects_request_smuggling_and_ambiguous_hosts(self) -> None:
        import network_scope

        for host, path in (
            ("fixture.invalid", "/allowed\r\nX-Injected: yes"),
            ("fixture.invalid", "/allowed\x00suffix"),
            ("bad_host.invalid", "/allowed"),
            ("127.0.0.1", "/allowed"),
            ("fixture.invalid.", "/allowed"),
        ):
            with self.subTest(host=host, path=path):
                scope = scope_with_network_policy(
                    host=host, path=path, method="GET"
                )
                with self.assertRaises(network_scope.NetworkScopeError):
                    network_scope.parse_network_policy(
                        scope, expected_scope_hash=network_scope.sha256_bytes(scope)
                    )
        record("policy-rejects-smuggling-controls-and-ambiguous-hosts", True)

    def test_address_budget_and_uncertain_replay_rules(self) -> None:
        try:
            import network_scope
        except ImportError as exc:
            self.fail(f"missing parent network policy gateway: {exc}")
        forbidden = (
            "127.0.0.1", "0.0.0.0", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"
        )
        for address in forbidden:
            with self.subTest(address=address):
                self.assertFalse(network_scope.address_allowed(address))
        gateway = network_scope.NetworkGateway(request_budget=1, deadline=time.monotonic() + 1)
        self.assertEqual(gateway.request_budget, 1)
        gateway.mark_uncertain("request-1")
        with self.assertRaises(network_scope.NetworkScopeError):
            gateway.begin("request-1")
        record("address-budget-and-no-uncertain-replay", True)

    def test_parent_transport_rejects_alias_and_headers_before_sink_contact(self) -> None:
        import network_scope

        scope = scope_with_network_policy(
            host="fixture.invalid", path="/allowed", method="GET"
        )
        policy = network_scope.parse_network_policy(
            scope, expected_scope_hash=network_scope.sha256_bytes(scope)
        )
        with (
            mock.patch.object(
                network_scope.socket,
                "create_connection",
                side_effect=AssertionError("forbidden alias reached socket creation"),
            ),
            self.assertRaises(network_scope.NetworkScopeError),
        ):
            network_scope.pinned_request(
                policy=policy,
                operation="target_fetch",
                url="https://fixture.invalid/allowed",
                method="GET",
                resolver=lambda *_args: "127.0.0.1",
            )
        resolver = mock.Mock(side_effect=AssertionError("invalid header reached DNS"))
        with self.assertRaises(network_scope.NetworkScopeError):
            network_scope.pinned_request(
                policy=policy,
                operation="target_fetch",
                url="https://fixture.invalid/allowed",
                method="GET",
                headers={"Authorization": "secret"},
                resolver=resolver,
            )
        self.assertEqual(resolver.call_count, 0)
        record("parent-transport-precontact-alias-and-header-rejection", True)

    def test_child_environment_contains_only_local_provider_authority(self) -> None:
        environment = supervisor._child_environment(
            {
                "HARNESS_ACTIVE_ENGAGEMENT": "/workspace/engagements/test",
                "HARNESS_EXPECTED_LEDGER_HASH": "sha256:" + "1" * 64,
                "HARNESS_EXPECTED_SOURCE_HASHES": json.dumps({
                    "events.jsonl": "sha256:" + "2" * 64,
                    "attempts.jsonl": "sha256:" + "3" * 64,
                    "artifacts.jsonl": "sha256:" + "4" * 64,
                }),
                "HARNESS_EXPECTED_RUNTIME_SESSION_REF": "00000000-0000-4000-8000-000000000000",
            },
            {
                "ANTHROPIC_API_KEY": "real-secret",
                "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            },
            provider_endpoint="http://127.0.0.1:48123",
        )
        self.assertEqual(environment["ANTHROPIC_BASE_URL"], "http://127.0.0.1:48123")
        self.assertNotEqual(environment.get("ANTHROPIC_API_KEY"), "real-secret")
        self.assertNotIn("real-secret", json.dumps(environment))
        record("provider-credentials-and-url-remain-parent-owned", True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path)
    arguments, unittest_arguments = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExternalNetworkPolicyWorkflow)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    payload = {
        "schema_version": 1,
        "fixture_image": FIXTURE_IMAGE,
        "docker_requested": os.environ.get("HARNESS_RUN_EGRESS_DOCKER") == "1",
        "real_provider_auth_qualified": False,
        "checks": RESULTS,
        "successful": result.wasSuccessful(),
        "failures": len(result.failures),
        "errors": len(result.errors),
    }
    if arguments.result is not None:
        arguments.result.parent.mkdir(parents=True, exist_ok=True)
        arguments.result.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
