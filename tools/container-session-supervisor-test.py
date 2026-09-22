#!/usr/bin/env python3
"""Focused tests for the container PID-1 session handoff."""

from __future__ import annotations

import base64
import errno
import io
import json
import os
import signal
import stat
import struct
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import container_session_supervisor as supervisor


def source_hashes() -> str:
    return supervisor._canonical_json_bytes(
        {
            "events.jsonl": "sha256:" + "1" * 64,
            "attempts.jsonl": "sha256:" + "2" * 64,
            "artifacts.jsonl": "sha256:" + "3" * 64,
        }
    ).decode("utf-8")


def session(command: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "command": command,
        "environment": {
            "HARNESS_ACTIVE_ENGAGEMENT": "/workspace/engagements/fixture",
            "HARNESS_EXPECTED_LEDGER_HASH": "sha256:" + "4" * 64,
            "HARNESS_EXPECTED_SOURCE_HASHES": source_hashes(),
            "HARNESS_EXPECTED_RUNTIME_SESSION_REF": "11111111-1111-4111-8111-111111111111",
        },
    }


def write_notification(
    *,
    number: int = supervisor.AARCH64_NR_WRITE,
    descriptor: int = 9,
    address: int = 0x1000,
    count: int = 8,
    offset: int = 0,
) -> supervisor._SeccompNotif:
    value = supervisor._SeccompNotif()
    value.identifier = 1234
    value.pid = 77
    value.flags = 0
    value.data.number = number
    value.data.architecture = supervisor.AUDIT_ARCH_AARCH64
    value.data.arguments[:] = (descriptor, address, count, offset, 0, 0)
    return value


class ContainerSessionSupervisorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="container-supervisor-")
        self.root = Path(self.temporary.name)
        self.control = self.root / "control"
        self.control.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.session_path = self.control / "session.json"
        self.manifest_path = self.control / "broker-manifest.json"
        self.relay_path = self.root / "relay.sock"
        self.manifest_path.write_bytes(b"{}\n")
        os.chmod(self.manifest_path, 0o400)
        self.patches = (
            mock.patch.object(supervisor, "SESSION_PATH", self.session_path),
            mock.patch.object(supervisor, "BROKER_MANIFEST_PATH", self.manifest_path),
            mock.patch.object(supervisor, "BROKER_RELAY_PATH", self.relay_path),
            mock.patch.object(supervisor, "WORKSPACE_PATH", self.workspace),
        )
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()
        self.temporary.cleanup()

    def write_session(self, value: dict[str, object]) -> str:
        raw = supervisor._canonical_json_bytes(value)
        self.session_path.write_bytes(raw)
        os.chmod(self.session_path, 0o400)
        return supervisor._sha256(raw)

    def run_boundary_patches(self):
        relay = mock.Mock()
        return (
            mock.patch.object(supervisor, "_require_zero_runtime_privileges"),
            mock.patch.object(supervisor, "_load_broker_manifest", return_value={}),
            mock.patch.object(
                supervisor, "_read_bootstrap", return_value=({}, b"k" * 32)
            ),
            mock.patch.object(supervisor, "_BrokerRelay", return_value=relay),
        )

    def test_exact_digest_and_private_control_material_run_one_child(self) -> None:
        output = self.root / "child-output"
        digest = self.write_session(
            session(
                [
                    "/bin/sh",
                    "-c",
                    f"printf %s \"$HARNESS_EXPECTED_RUNTIME_SESSION_REF\" > {output}",
                ]
            )
        )
        first, second, third, fourth = self.run_boundary_patches()
        with first, second, third, fourth, mock.patch.object(
            supervisor, "_storage_exhausted", return_value=False
        ), mock.patch.object(
            supervisor,
            "_run_traced_command",
            side_effect=lambda command, environment, _provider_endpoint: subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environment,
                cwd=self.workspace,
                check=False,
            ).returncode,
        ):
            self.assertEqual(supervisor.run(expected_session_hash=digest), 0)
        self.assertEqual(
            output.read_text(encoding="utf-8"),
            "11111111-1111-4111-8111-111111111111",
        )

        with (
            mock.patch.object(supervisor, "_require_zero_runtime_privileges"),
            self.assertRaises(supervisor.SupervisorError) as mismatch,
        ):
            supervisor.run(expected_session_hash="sha256:" + "0" * 64)
        self.assertEqual(str(mismatch.exception), "session_hash_mismatch")

    def test_storage_exhaustion_is_reserved_and_propagated(self) -> None:
        marker = self.root / "child-finished"
        digest = self.write_session(
            session(["/bin/sh", "-c", f"sleep 10; touch {marker}"])
        )
        began = time.monotonic()
        first, second, third, fourth = self.run_boundary_patches()
        with first, second, third, fourth, mock.patch.object(
            supervisor, "_storage_exhausted", return_value=False
        ), mock.patch.object(
            supervisor,
            "_run_traced_command",
            return_value=supervisor.STORAGE_EXIT_CODE,
        ):
            self.assertEqual(
                supervisor.run(expected_session_hash=digest),
                supervisor.STORAGE_EXIT_CODE,
            )
        self.assertLess(time.monotonic() - began, 2.0)
        self.assertFalse(marker.exists())
        self.assertEqual(
            supervisor._returncode(supervisor.STORAGE_EXIT_CODE),
            supervisor.INTERNAL_FAILURE_EXIT_CODE,
        )

    def test_syscall_exit_permanently_latches_storage_errors(self) -> None:
        entry = bytearray(128)
        entry[0] = supervisor.PTRACE_SYSCALL_INFO_ENTRY
        struct.pack_into("Q", entry, 24, supervisor.AARCH64_NR_WRITE)
        struct.pack_into("6Q", entry, 32, 9, 0x1000, 4096, 0, 0, 0)
        decoded = supervisor._decode_syscall_info(bytes(entry), 80)
        self.assertEqual(decoded.number, supervisor.AARCH64_NR_WRITE)
        self.assertEqual(decoded.arguments[:3], (9, 0x1000, 4096))

        for error_number in (errno.ENOSPC, errno.EDQUOT):
            raw = bytearray(128)
            raw[0] = supervisor.PTRACE_SYSCALL_INFO_EXIT
            struct.pack_into("q", raw, 24, -error_number)
            raw[32] = 1
            self.assertTrue(
                supervisor._syscall_info_is_storage_failure(bytes(raw), 33)
            )

        successful = bytearray(raw)
        struct.pack_into("q", successful, 24, 0)
        successful[32] = 0
        self.assertFalse(
            supervisor._syscall_info_is_storage_failure(bytes(successful), 33)
        )
        with self.assertRaises(supervisor.SupervisorError):
            supervisor._syscall_info_is_storage_failure(bytes(raw[:32]), 32)

    def test_inherited_filter_closes_unobservable_storage_paths(self) -> None:
        instructions = supervisor._tracee_filter_instructions()

        def evaluate(
            number: int,
            *,
            architecture: int = supervisor.AUDIT_ARCH_AARCH64,
            argument0: int = 0,
            argument2: int = 0,
            argument3: int = 0,
        ) -> int:
            accumulator = 0
            cursor = 0
            while cursor < len(instructions):
                instruction = instructions[cursor]
                if instruction.code == supervisor.BPF_LD | supervisor.BPF_W | supervisor.BPF_ABS:
                    accumulator = {
                        supervisor.SECCOMP_DATA_ARCH_OFFSET: architecture,
                        supervisor.SECCOMP_DATA_NR_OFFSET: number,
                        supervisor.SECCOMP_DATA_ARG0_OFFSET: argument0,
                        supervisor.SECCOMP_DATA_ARG2_OFFSET: argument2,
                        supervisor.SECCOMP_DATA_ARG3_OFFSET: argument3,
                    }[instruction.k]
                    cursor += 1
                    continue
                if instruction.code == supervisor.BPF_JMP | supervisor.BPF_JEQ | supervisor.BPF_K:
                    cursor += 1 + (instruction.jt if accumulator == instruction.k else instruction.jf)
                    continue
                if instruction.code == supervisor.BPF_JMP | supervisor.BPF_JSET | supervisor.BPF_K:
                    cursor += 1 + (instruction.jt if accumulator & instruction.k else instruction.jf)
                    continue
                if instruction.code == supervisor.BPF_JMP | supervisor.BPF_JGE | supervisor.BPF_K:
                    cursor += 1 + (instruction.jt if accumulator >= instruction.k else instruction.jf)
                    continue
                if instruction.code == supervisor.BPF_RET | supervisor.BPF_K:
                    return instruction.k
                self.fail(f"unexpected BPF instruction {instruction.code}")
            self.fail("seccomp program did not return")

        unavailable = supervisor.SECCOMP_RET_ERRNO | errno.ENOSYS
        self.assertEqual(
            set(supervisor._UNAVAILABLE_TRACE_SYSCALLS),
            {
                supervisor.AARCH64_NR_IO_SETUP,
                supervisor.AARCH64_NR_IO_DESTROY,
                supervisor.AARCH64_NR_IO_SUBMIT,
                supervisor.AARCH64_NR_IO_CANCEL,
                supervisor.AARCH64_NR_IO_GETEVENTS,
                supervisor.AARCH64_NR_WRITEV,
                supervisor.AARCH64_NR_PWRITEV,
                supervisor.AARCH64_NR_SENDFILE,
                supervisor.AARCH64_NR_SPLICE,
                supervisor.AARCH64_NR_PROCESS_VM_WRITEV,
                supervisor.AARCH64_NR_SECCOMP,
                supervisor.AARCH64_NR_COPY_FILE_RANGE,
                supervisor.AARCH64_NR_PWRITEV2,
                supervisor.AARCH64_NR_IO_PGETEVENTS,
                supervisor.AARCH64_NR_IO_URING_SETUP,
                supervisor.AARCH64_NR_IO_URING_ENTER,
                supervisor.AARCH64_NR_IO_URING_REGISTER,
                supervisor.AARCH64_NR_CLONE3,
            },
        )
        for syscall_number in supervisor._UNAVAILABLE_TRACE_SYSCALLS:
            with self.subTest(syscall_number=syscall_number):
                self.assertEqual(evaluate(syscall_number), unavailable)
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_MMAP, argument3=supervisor.MAP_SHARED),
            unavailable,
        )
        self.assertEqual(
            evaluate(
                supervisor.AARCH64_NR_MMAP,
                argument3=supervisor.MAP_SHARED | supervisor.MAP_ANONYMOUS,
            ),
            supervisor.SECCOMP_RET_ALLOW,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_WRITE),
            supervisor.SECCOMP_RET_USER_NOTIF,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_PWRITE64),
            supervisor.SECCOMP_RET_USER_NOTIF,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_REVIEWED_SYSCALL_LIMIT - 1),
            supervisor.SECCOMP_RET_ALLOW,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_REVIEWED_SYSCALL_LIMIT),
            unavailable,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_CLONE, argument0=supervisor.CLONE_UNTRACED),
            supervisor.SECCOMP_RET_ERRNO | errno.EPERM,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_CLONE, argument0=supervisor.CLONE_THREAD),
            supervisor.SECCOMP_RET_ERRNO | errno.EPERM,
        )
        self.assertEqual(
            evaluate(
                supervisor.AARCH64_NR_CLONE,
                argument0=supervisor.CLONE_THREAD | supervisor.CLONE_FILES,
            ),
            supervisor.SECCOMP_RET_ALLOW,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_UNSHARE, argument0=supervisor.CLONE_FILES),
            supervisor.SECCOMP_RET_ERRNO | errno.EPERM,
        )
        self.assertEqual(
            evaluate(
                supervisor.AARCH64_NR_CLOSE_RANGE,
                argument2=supervisor.CLOSE_RANGE_UNSHARE,
            ),
            supervisor.SECCOMP_RET_ERRNO | errno.EPERM,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_PRCTL, argument0=supervisor.PR_SET_SECCOMP),
            unavailable,
        )
        self.assertEqual(
            evaluate(supervisor.AARCH64_NR_WRITE, architecture=0),
            supervisor.SECCOMP_RET_KILL_PROCESS,
        )

    def test_broker_uses_one_stable_duplicate_for_classification_and_write(self) -> None:
        base_descriptor = os.open(os.devnull, os.O_WRONLY)
        duplicate = os.dup(base_descriptor)
        real_close = os.close
        try:
            with (
                mock.patch.object(supervisor, "_pidfd_getfd", return_value=duplicate) as getfd,
                mock.patch.object(supervisor, "_read_tracee_memory", return_value=b"abcdefgh"),
                mock.patch.object(supervisor, "_notification_id_valid") as validate,
                mock.patch.object(
                    supervisor.os,
                    "fstat",
                    return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_dev=41),
                ) as fstat_call,
                mock.patch.object(supervisor.os, "write", return_value=8) as write_call,
                mock.patch.object(supervisor.os, "close", side_effect=real_close) as close_call,
            ):
                result = supervisor._emulate_brokered_write(
                    write_notification(), frozenset({41}), 55
                )
            self.assertEqual(result, supervisor._BrokeredWriteResult(8, 0, False))
            getfd.assert_called_once_with(77, 9)
            fstat_call.assert_called_once_with(duplicate)
            write_call.assert_called_once_with(duplicate, b"abcdefgh")
            close_call.assert_called_once_with(duplicate)
            self.assertEqual(validate.call_args_list, [mock.call(55, 1234), mock.call(55, 1234)])
        finally:
            real_close(base_descriptor)

    def test_broker_classifies_only_bounded_regular_file_results(self) -> None:
        cases = (
            ("bounded-short", stat.S_IFREG, 41, 3, None, True, 3, 0),
            ("bounded-zero", stat.S_IFREG, 41, 0, None, False, 0, 0),
            ("bounded-full", stat.S_IFREG, 41, 8, None, False, 8, 0),
            ("bounded-enospc", stat.S_IFREG, 41, None, errno.ENOSPC, True, 0, -errno.ENOSPC),
            ("bounded-edquot", stat.S_IFREG, 41, None, errno.EDQUOT, True, 0, -errno.EDQUOT),
            ("pipe-short", stat.S_IFIFO, 41, 3, None, False, 3, 0),
            ("outside-short", stat.S_IFREG, 99, 3, None, False, 3, 0),
            ("outside-enospc", stat.S_IFREG, 99, None, errno.ENOSPC, False, 0, -errno.ENOSPC),
        )
        for name, kind, device, returned, raised_errno, exhausted, value, error in cases:
            with self.subTest(name=name):
                side_effect = (
                    OSError(raised_errno, os.strerror(raised_errno))
                    if raised_errno is not None
                    else None
                )
                with (
                    mock.patch.object(supervisor, "_pidfd_getfd", return_value=71),
                    mock.patch.object(supervisor, "_read_tracee_memory", return_value=b"abcdefgh"),
                    mock.patch.object(supervisor, "_notification_id_valid"),
                    mock.patch.object(
                        supervisor.os,
                        "fstat",
                        return_value=SimpleNamespace(st_mode=kind | 0o600, st_dev=device),
                    ),
                    mock.patch.object(
                        supervisor.os,
                        "write",
                        return_value=returned,
                        side_effect=side_effect,
                    ),
                    mock.patch.object(supervisor.os, "close"),
                ):
                    result = supervisor._emulate_brokered_write(
                        write_notification(), frozenset({41}), 55
                    )
                self.assertEqual(
                    result,
                    supervisor._BrokeredWriteResult(value, error, exhausted),
                )

    def test_broker_pwrite_uses_signed_offset_and_rejects_oversize_before_duplication(self) -> None:
        with (
            mock.patch.object(supervisor, "_pidfd_getfd", return_value=71),
            mock.patch.object(supervisor, "_read_tracee_memory", return_value=b"abcdefgh"),
            mock.patch.object(supervisor, "_notification_id_valid"),
            mock.patch.object(
                supervisor.os,
                "fstat",
                return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_dev=41),
            ),
            mock.patch.object(supervisor.os, "pwrite", return_value=8) as pwrite_call,
            mock.patch.object(supervisor.os, "write") as write_call,
            mock.patch.object(supervisor.os, "close"),
        ):
            result = supervisor._emulate_brokered_write(
                write_notification(
                    number=supervisor.AARCH64_NR_PWRITE64,
                    offset=(1 << 64) - 2,
                ),
                frozenset({41}),
                55,
            )
        self.assertEqual(result, supervisor._BrokeredWriteResult(8, 0, False))
        pwrite_call.assert_called_once_with(71, b"abcdefgh", -2)
        write_call.assert_not_called()

        with (
            mock.patch.object(supervisor, "_pidfd_getfd") as getfd,
            mock.patch.object(supervisor, "_notification_id_valid"),
        ):
            with self.assertRaises(supervisor.SupervisorError):
                supervisor._emulate_brokered_write(
                    write_notification(count=supervisor.MAX_EMULATED_WRITE_BYTES + 1),
                    frozenset({41}),
                    55,
                )
        getfd.assert_not_called()

    def test_filter_install_requests_killable_notification_waits(self) -> None:
        fake_libc = SimpleNamespace(prctl=mock.Mock(return_value=0))
        with (
            mock.patch.object(supervisor.sys, "platform", "linux"),
            mock.patch.object(
                supervisor.os,
                "uname",
                return_value=SimpleNamespace(machine="aarch64"),
            ),
            mock.patch.object(supervisor.ctypes, "CDLL", return_value=fake_libc),
            mock.patch.object(supervisor, "_syscall", return_value=55) as syscall,
        ):
            self.assertEqual(supervisor._install_tracee_filter(), 55)
        arguments = syscall.call_args.args
        self.assertEqual(arguments[0], supervisor.AARCH64_NR_SECCOMP)
        self.assertEqual(arguments[1].value, supervisor.SECCOMP_SET_MODE_FILTER)
        self.assertEqual(
            arguments[2].value,
            supervisor.SECCOMP_FILTER_FLAG_NEW_LISTENER
            | supervisor.SECCOMP_FILTER_FLAG_WAIT_KILLABLE_RECV,
        )

    def test_unexpected_broker_failure_kills_the_exact_tracee(self) -> None:
        reader, writer = os.pipe()
        broker = supervisor._WriteBroker(reader, frozenset({41}), 321)
        try:
            with (
                mock.patch.object(broker, "_serve", side_effect=RuntimeError("fixture")),
                mock.patch.object(supervisor.os, "kill") as kill,
            ):
                broker.start()
                broker._thread.join(timeout=1.0)
            self.assertFalse(broker._thread.is_alive())
            self.assertTrue(broker.failed.is_set())
            kill.assert_called_once_with(321, signal.SIGKILL)
        finally:
            broker.close()
            os.close(writer)

    def test_auth_and_child_environment_are_allowlisted(self) -> None:
        clean = supervisor._child_environment(
            session(["/bin/true"])["environment"],  # type: ignore[arg-type]
            {"ANTHROPIC_API_KEY": "fixture-secret"},
        )
        self.assertEqual(clean["ANTHROPIC_API_KEY"], "lrh-parent-owned")
        self.assertEqual(clean["ANTHROPIC_BASE_URL"], "http://127.0.0.1:9")
        self.assertNotIn("fixture-secret", json.dumps(clean))
        self.assertEqual(
            clean[supervisor.broker_client.RELAY_SOCKET_ENV], str(self.relay_path)
        )
        self.assertNotIn(supervisor.broker_client.KEY_FILE_ENV, clean)
        self.assertNotIn(supervisor.broker_client.KEY_FD_ENV, clean)
        with mock.patch.dict(
            os.environ,
            {
                "UNRELATED_OPERATOR_SECRET": "must-not-pass",
                "PATH": "/usr/bin:/bin",
            },
            clear=True,
        ):
            filtered = supervisor._child_environment(
                session(["/bin/true"])["environment"],  # type: ignore[arg-type]
                {},
            )
        self.assertNotIn("UNRELATED_OPERATOR_SECRET", filtered)
        self.assertEqual(filtered["PATH"], "/usr/bin:/bin")

    def test_bootstrap_key_is_canonical_and_never_materialized_for_child(self) -> None:
        key = b"s" * supervisor.broker_client.SESSION_KEY_BYTES
        raw = supervisor._canonical_json_bytes(
            {
                "schema_version": 1,
                "environment": {"ANTHROPIC_API_KEY": "fixture-secret"},
                "broker_session_key_base64": base64.b64encode(key).decode("ascii"),
            }
        )
        stream = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
        with mock.patch.object(supervisor.sys, "stdin", stream):
            auth, parsed_key = supervisor._read_bootstrap()
        self.assertEqual(auth, {"ANTHROPIC_API_KEY": "fixture-secret"})
        self.assertEqual(parsed_key, key)
        self.assertFalse((self.control / "broker-session.key").exists())

    def test_local_relay_retains_key_and_returns_only_bounded_result(self) -> None:
        key = b"r" * supervisor.broker_client.SESSION_KEY_BYTES
        manifest = mock.Mock()
        request_seen: list[dict[str, object]] = []

        def handle(_manifest, received_key, request):
            self.assertEqual(received_key, key)
            request_seen.append(request)
            time.sleep(0.1)
            return 0, b'{"valid":true}\n'

        with (
            mock.patch.object(
                supervisor.broker_client, "validate_manifest", return_value=manifest
            ),
            mock.patch.object(
                supervisor.broker_client, "handle_relay_request", side_effect=handle
            ),
        ):
            relay = supervisor._BrokerRelay(manifest={}, key=key)
            relay.start()
            try:
                with mock.patch.dict(
                    os.environ,
                    {
                        supervisor.broker_client.RELAY_SOCKET_ENV: str(self.relay_path),
                    },
                    clear=True,
                ), mock.patch.object(
                    supervisor.broker_client,
                    "RELAY_PATH_RE",
                    supervisor.re.compile(
                        supervisor.re.escape(str(self.relay_path)) + r"\Z"
                    ),
                ), mock.patch.object(
                    supervisor.broker_client, "IO_TIMEOUT_SECONDS", 0.025
                ):
                    self.assertEqual(
                        supervisor.broker_client.relay_action(
                            command="record-attempt", arguments=["--fixture", "one"]
                        ),
                        (0, b'{"valid":true}\n'),
                    )
            finally:
                relay.close()
        self.assertEqual(len(request_seen), 1)
        self.assertEqual(request_seen[0]["request_kind"], "action")
        self.assertNotIn(key, supervisor._canonical_json_bytes(request_seen[0]))

    def test_session_shape_rejects_redirects_and_duplicate_source_keys(self) -> None:
        valid = session(["/bin/true"])
        command, environment = supervisor._validate_session(valid)
        self.assertEqual(command, ["/bin/true"])
        self.assertEqual(set(environment), supervisor._LEDGER_KEYS)

        redirected = session(["relative-command"])
        with self.assertRaises(supervisor.SupervisorError):
            supervisor._validate_session(redirected)

        duplicate = session(["/bin/true"])
        duplicate["environment"]["HARNESS_EXPECTED_SOURCE_HASHES"] = (  # type: ignore[index]
            '{"events.jsonl":"sha256:'
            + "1" * 64
            + '","events.jsonl":"sha256:'
            + "2" * 64
            + '","attempts.jsonl":"sha256:'
            + "3" * 64
            + '","artifacts.jsonl":"sha256:'
            + "4" * 64
            + '"}'
        )
        with self.assertRaises(supervisor.SupervisorError):
            supervisor._validate_session(duplicate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
