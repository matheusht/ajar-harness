#!/usr/bin/env python3
"""Adversarial launched-process tests for the Darwin filesystem-read policy."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from darwin_read_isolation import (
    MAX_EXPLICIT_INPUTS,
    ReadIsolationError,
    _profile_lines,
    _runtime_dependency_closure,
    build_read_policy,
)


DARWIN = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()
TIFFSPLIT = Path("/opt/homebrew/Cellar/libtiff/4.7.2/bin/tiffsplit")
WEBP_INSTALL_NAME = Path("/opt/homebrew/opt/webp/lib/libwebp.7.dylib")


class PortableDependencyClosureTest(unittest.TestCase):
    def test_executable_path_uses_top_level_invocation_alias(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dri-executable-") as temporary:
            root = Path(temporary).resolve()
            bundle = root / "cellar" / "bundle"
            bundle.mkdir(parents=True)
            tool = bundle / "tool"
            dependency = bundle / "libchild.dylib"
            for image in (tool, dependency):
                image.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            invocation_root = root / "opt"
            invocation_root.symlink_to(bundle, target_is_directory=True)
            tool_invocation = invocation_root / tool.name
            dependency_invocation = invocation_root / dependency.name

            def fake_otool(argv: object) -> bytes:
                command = tuple(argv)
                operation = command[1]
                image = Path(command[2])
                if operation == "-L" and image == tool:
                    return (
                        f"{tool}:\n"
                        "\t@executable_path/libchild.dylib (compatibility version 1.0.0, "
                        "current version 1.0.0)\n"
                    ).encode("utf-8")
                return f"{image}:\n".encode("utf-8")

            with mock.patch(
                "darwin_read_isolation._bounded_command",
                side_effect=fake_otool,
            ):
                closure = _runtime_dependency_closure((tool_invocation,))

            self.assertIn(tool_invocation, closure)
            self.assertIn(dependency_invocation, closure)
            self.assertIn(dependency, closure)

    def test_absolute_install_name_alias_and_canonical_target_reach_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dri-portable-") as temporary:
            root = Path(temporary).resolve()
            tool = root / "tool"
            tool.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            cellar = root / "cellar"
            cellar.mkdir()
            canonical_dependency = cellar / "libfixture.dylib"
            canonical_dependency.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            opt = root / "opt"
            opt.symlink_to(cellar, target_is_directory=True)
            install_name = opt / canonical_dependency.name

            def fake_otool(argv: object) -> bytes:
                command = tuple(argv)
                operation = command[1]
                image = Path(command[2])
                if operation == "-L" and image == tool:
                    return (
                        f"{tool}:\n"
                        f"\t{install_name} (compatibility version 1.0.0, "
                        "current version 1.0.0)\n"
                    ).encode("utf-8")
                return f"{image}:\n".encode("utf-8")

            with mock.patch(
                "darwin_read_isolation._bounded_command",
                side_effect=fake_otool,
            ):
                closure = _runtime_dependency_closure((tool,))
            profile = "\n".join(_profile_lines(directories=(), files=closure))

            self.assertIn(install_name, closure)
            self.assertIn(canonical_dependency, closure)
            self.assertIn(
                f'(literal {json.dumps(str(install_name))})',
                profile,
            )
            self.assertIn(
                f'(literal {json.dumps(str(canonical_dependency))})',
                profile,
            )
            self.assertNotIn(
                f'(subpath {json.dumps(str(opt))})',
                profile,
            )

    def test_rpath_keeps_declared_order_and_raw_symlink_spelling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dri-rpath-") as temporary:
            root = Path(temporary).resolve()
            tool = root / "tool"
            tool.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            cellar = root / "cellar"
            cellar.mkdir()
            canonical_dependency = cellar / "librpath.dylib"
            canonical_dependency.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            first_rpath = root / "z-first-rpath"
            second_rpath = root / "a-second-rpath"
            first_rpath.symlink_to(cellar, target_is_directory=True)
            second_rpath.symlink_to(cellar, target_is_directory=True)
            first_install_name = first_rpath / canonical_dependency.name
            second_install_name = second_rpath / canonical_dependency.name

            def fake_otool(argv: object) -> bytes:
                command = tuple(argv)
                operation = command[1]
                image = Path(command[2])
                if operation == "-l" and image == tool:
                    return (
                        "Load command 1\n"
                        "          cmd LC_RPATH\n"
                        f"         path {first_rpath} (offset 12)\n"
                        "Load command 2\n"
                        "          cmd LC_RPATH\n"
                        f"         path {second_rpath} (offset 12)\n"
                    ).encode("utf-8")
                if operation == "-L" and image == tool:
                    return (
                        f"{tool}:\n"
                        "\t@rpath/librpath.dylib (compatibility version 1.0.0, "
                        "current version 1.0.0)\n"
                    ).encode("utf-8")
                return f"{image}:\n".encode("utf-8")

            with mock.patch(
                "darwin_read_isolation._bounded_command",
                side_effect=fake_otool,
            ):
                closure = _runtime_dependency_closure((tool,))
            profile = "\n".join(_profile_lines(directories=(), files=closure))

            self.assertIn(first_install_name, closure)
            self.assertIn(canonical_dependency, closure)
            self.assertNotIn(second_install_name, closure)
            self.assertIn(
                f'(literal {json.dumps(str(first_install_name))})',
                profile,
            )

    def test_nested_loader_path_uses_parent_install_name_alias(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dri-loader-") as temporary:
            root = Path(temporary).resolve()
            tool = root / "tool"
            tool.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            cellar = root / "cellar"
            cellar.mkdir()
            parent = cellar / "libparent.dylib"
            child = cellar / "libchild.dylib"
            for image in (parent, child):
                image.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 32)
            opt = root / "opt"
            opt.symlink_to(cellar, target_is_directory=True)
            parent_install_name = opt / parent.name
            child_install_name = opt / child.name

            def fake_otool(argv: object) -> bytes:
                command = tuple(argv)
                operation = command[1]
                image = Path(command[2])
                if operation == "-L" and image == tool:
                    return (
                        f"{tool}:\n"
                        f"\t{parent_install_name} (compatibility version 1.0.0, "
                        "current version 1.0.0)\n"
                    ).encode("utf-8")
                if operation == "-L" and image == parent:
                    return (
                        f"{parent}:\n"
                        "\t@loader_path/libchild.dylib (compatibility version 1.0.0, "
                        "current version 1.0.0)\n"
                    ).encode("utf-8")
                return f"{image}:\n".encode("utf-8")

            with mock.patch(
                "darwin_read_isolation._bounded_command",
                side_effect=fake_otool,
            ):
                closure = _runtime_dependency_closure((tool,))

            self.assertIn(parent_install_name, closure)
            self.assertIn(child_install_name, closure)
            self.assertIn(child, closure)


@unittest.skipUnless(DARWIN, "Darwin sandbox-exec integration unavailable")
class DarwinReadIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="dri-", dir="/tmp")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.harness = self.root / "harness"
        self.scratch = self.root / "scratch"
        self.explicit_directory = self.root / "explicit-directory"
        for directory in (
            self.workspace,
            self.harness,
            self.scratch,
            self.explicit_directory,
        ):
            directory.mkdir()
        self.runtime = self.root / "runtime"
        self.runtime.write_text(
            "#!/bin/sh\nexit 0\n",
            encoding="utf-8",
        )
        self.runtime.chmod(self.runtime.stat().st_mode | stat.S_IXUSR)
        self.launcher = self.harness / "launcher.py"
        self.launcher.write_text("raise SystemExit(0)\n", encoding="utf-8")
        self.sentinel = self.root / "sentinel"
        self.sentinel.write_text("sentinel", encoding="utf-8")
        self.endpoint = self.root / "broker.sock"
        self.explicit_file = self.root / "explicit-file"
        self.explicit_file.write_text("explicit", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _policy(self, **overrides: object):
        values = {
            "workspace": self.workspace,
            "harness": self.harness,
            "scratch": self.scratch,
            "executable": self.runtime,
            "python": Path("/bin/sh"),
            "launcher": self.launcher,
            "containment_sentinel": self.sentinel,
            "internal_endpoints": (self.endpoint,),
            "explicit_inputs": (self.explicit_file, self.explicit_directory),
        }
        values.update(overrides)
        return build_read_policy(**values)

    def _sandbox(self, policy: object, *command: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", policy.profile, *command],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(self.scratch),
                "TMPDIR": str(self.scratch),
            },
            cwd=self.workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_real_process_and_descendant_cannot_read_or_stat_unrelated_path(self) -> None:
        allowed = {
            "workspace": self.workspace / "allowed",
            "harness": self.harness / "allowed",
            "scratch": self.scratch / "allowed",
            "runtime": self.runtime,
            "explicit_file": self.explicit_file,
            "explicit_directory": self.explicit_directory / "allowed",
        }
        for label, path in allowed.items():
            if label not in {"runtime", "explicit_file"}:
                path.write_text(label, encoding="utf-8")
        outsider = self.root / "unrelated-sentinel"
        outsider.write_text("must-not-read", encoding="utf-8")
        symlink_escape = self.workspace / "escape"
        symlink_escape.symlink_to(outsider)
        policy = self._policy()
        for label, path in allowed.items():
            with self.subTest(label=label, operation="read"):
                self.assertEqual(
                    self._sandbox(policy, "/bin/cat", str(path)).returncode,
                    0,
                )
            with self.subTest(label=label, operation="stat"):
                self.assertEqual(
                    self._sandbox(
                        policy,
                        "/usr/bin/stat",
                        "-L",
                        "-f",
                        "%z",
                        str(path),
                    ).returncode,
                    0,
                )
            with self.subTest(label=label, operation="exists"):
                self.assertEqual(
                    self._sandbox(
                        policy,
                        "/bin/sh",
                        "-c",
                        'test -e "$1"',
                        "probe",
                        str(path),
                    ).returncode,
                    0,
                )

        for label, path in (("outsider", outsider), ("symlink_escape", symlink_escape)):
            with self.subTest(label=label, operation="read"):
                self.assertNotEqual(
                    self._sandbox(policy, "/bin/cat", str(path)).returncode,
                    0,
                )
            with self.subTest(label=label, operation="stat"):
                self.assertNotEqual(
                    self._sandbox(
                        policy,
                        "/usr/bin/stat",
                        "-L",
                        "-f",
                        "%z",
                        str(path),
                    ).returncode,
                    0,
                )
            with self.subTest(label=label, operation="exists"):
                self.assertNotEqual(
                    self._sandbox(
                        policy,
                        "/bin/sh",
                        "-c",
                        'test -e "$1"',
                        "probe",
                        str(path),
                    ).returncode,
                    0,
                )
        self.assertNotEqual(
            self._sandbox(
                policy,
                "/bin/sh",
                "-c",
                '/bin/cat "$1" >/dev/null',
                "descendant",
                str(outsider),
            ).returncode,
            0,
        )

    def test_policy_has_no_global_metadata_or_existence_allow(self) -> None:
        profile = self._policy().profile
        self.assertIn("(deny file-read* file-test-existence)", profile)
        self.assertNotIn("(allow file-read-metadata)", profile)
        self.assertNotIn("(allow file-test-existence)", profile)
        self.assertNotIn('(subpath "/private/tmp")', profile)

    def test_future_file_in_same_uid_runtime_prefix_remains_denied(self) -> None:
        writable_prefix = self.root / "same-uid-runtime-prefix"
        writable_prefix.mkdir()
        with (
            mock.patch.object(sys, "prefix", str(writable_prefix)),
            mock.patch.object(sys, "base_prefix", str(writable_prefix)),
        ):
            policy = self._policy()
        self.assertEqual(policy.runtime_directories, ())
        self.assertNotIn(
            f'(subpath {json.dumps(str(writable_prefix))})',
            policy.profile,
        )

        future_secret = writable_prefix / "future-secret"
        future_secret.write_text("must-not-read", encoding="utf-8")
        self.assertNotEqual(
            self._sandbox(policy, "/bin/cat", str(future_secret)).returncode,
            0,
        )
        self.assertNotEqual(
            self._sandbox(
                policy,
                "/bin/sh",
                "-c",
                'test -e "$1"',
                "probe",
                str(future_secret),
            ).returncode,
            0,
        )

    def test_exact_runtime_symlink_chain_is_preserved_without_parent_authority(self) -> None:
        links = self.root / "runtime-links"
        links.mkdir()
        first = links / "python"
        second = links / "python-hop"
        first.symlink_to(second.name)
        second.symlink_to("/bin/sh")
        policy = self._policy(python=first)

        self.assertIn(f'(literal {json.dumps(str(first))})', policy.profile)
        self.assertIn(f'(literal {json.dumps(str(second))})', policy.profile)
        self.assertNotIn(f'(subpath {json.dumps(str(links))})', policy.profile)
        completed = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", policy.profile, str(first), "-c", "exit 0"],
            cwd=self.workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))

    @unittest.skipUnless(
        TIFFSPLIT.is_file() and WEBP_INSTALL_NAME.is_file(),
        "Homebrew Mach-O install-name fixture unavailable",
    )
    def test_real_macho_dependency_keeps_install_name_and_symlink_chain(self) -> None:
        policy = self._policy(executable=TIFFSPLIT)
        canonical_webp = WEBP_INSTALL_NAME.resolve(strict=True)

        self.assertIn(
            f'(literal {json.dumps(str(WEBP_INSTALL_NAME))})',
            policy.profile,
        )
        self.assertIn(
            f'(literal {json.dumps(str(canonical_webp))})',
            policy.profile,
        )
        self.assertNotIn(
            f'(subpath {json.dumps(str(WEBP_INSTALL_NAME.parent))})',
            policy.profile,
        )
        completed = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", policy.profile, str(TIFFSPLIT)],
            cwd=self.workspace,
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.scratch)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"dyld", completed.stderr.lower())

    def test_explicit_file_and_directory_symlinks_keep_exact_invocation_paths(self) -> None:
        file_target = self.root / "declared-cert-target.pem"
        file_target.write_text("declared-cert", encoding="utf-8")
        file_alias = self.root / "declared-cert.pem"
        file_alias.symlink_to(file_target.name)
        directory_target = self.root / "declared-cert-directory-target"
        directory_target.mkdir()
        (directory_target / "nested.pem").write_text("nested-cert", encoding="utf-8")
        directory_alias = self.root / "declared-cert-directory"
        directory_alias.symlink_to(directory_target.name)

        policy = self._policy(explicit_inputs=(file_alias, directory_alias))
        self.assertIn(file_alias, policy.explicit_files)
        self.assertIn(file_target, policy.explicit_files)
        self.assertIn(directory_alias, policy.explicit_directories)
        self.assertIn(directory_target, policy.explicit_directories)
        self.assertIn(
            f'(literal {json.dumps(str(file_alias))})',
            policy.profile,
        )
        self.assertNotIn(
            f'(subpath {json.dumps(str(file_alias.parent))})',
            policy.profile,
        )
        self.assertIn(
            f'(subpath {json.dumps(str(directory_alias))})',
            policy.profile,
        )
        self.assertIn(
            f'(subpath {json.dumps(str(directory_target))})',
            policy.profile,
        )
        completed = self._sandbox(
            policy,
            "/bin/sh",
            "-c",
            '[ "$(/bin/cat "$1")" = declared-cert ] && '
            '[ "$(/bin/cat "$2/nested.pem")" = nested-cert ]',
            "probe",
            str(file_alias),
            str(directory_alias),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))

        unrelated_file = self.root / "unrelated-retarget-sentinel"
        unrelated_file.write_text("must-not-read", encoding="utf-8")
        unrelated_directory = self.root / "unrelated-retarget-directory"
        unrelated_directory.mkdir()
        (unrelated_directory / "nested.pem").write_text(
            "must-not-read",
            encoding="utf-8",
        )
        file_alias.unlink()
        file_alias.symlink_to(unrelated_file.name)
        directory_alias.unlink()
        directory_alias.symlink_to(unrelated_directory.name)
        for label, path in (
            ("file", file_alias),
            ("directory", directory_alias / "nested.pem"),
        ):
            with self.subTest(label=label, operation="read"):
                self.assertNotEqual(
                    self._sandbox(policy, "/bin/cat", str(path)).returncode,
                    0,
                )
            with self.subTest(label=label, operation="stat"):
                self.assertNotEqual(
                    self._sandbox(
                        policy,
                        "/usr/bin/stat",
                        "-L",
                        "-f",
                        "%z",
                        str(path),
                    ).returncode,
                    0,
                )
            with self.subTest(label=label, operation="exists"):
                self.assertNotEqual(
                    self._sandbox(
                        policy,
                        "/bin/sh",
                        "-c",
                        'test -e "$1"',
                        "probe",
                        str(path),
                    ).returncode,
                    0,
                )

    def test_workspace_and_harness_symlink_components_fail_before_launch(self) -> None:
        workspace_parent = self.root / "workspace-parent"
        workspace_parent.mkdir()
        real_workspace = workspace_parent / "real"
        real_workspace.mkdir()
        workspace_alias = self.root / "workspace-parent-alias"
        workspace_alias.symlink_to(workspace_parent.name)
        with self.assertRaises(ReadIsolationError) as workspace_error:
            self._policy(workspace=workspace_alias / real_workspace.name)
        self.assertEqual(workspace_error.exception.code, "read_input_invalid")

        harness_parent = self.root / "harness-parent"
        harness_parent.mkdir()
        real_harness = harness_parent / "real"
        real_harness.mkdir()
        harness_alias = self.root / "harness-parent-alias"
        harness_alias.symlink_to(harness_parent.name)
        aliased_launcher = harness_alias / real_harness.name / "launcher.py"
        aliased_launcher.write_text("raise SystemExit(0)\n", encoding="utf-8")
        with self.assertRaises(ReadIsolationError) as harness_error:
            self._policy(
                harness=harness_alias / real_harness.name,
                launcher=aliased_launcher,
            )
        self.assertEqual(harness_error.exception.code, "read_isolation_unavailable")

    def test_missing_input_and_unsafe_script_fail_closed(self) -> None:
        with self.assertRaises(ReadIsolationError) as missing:
            self._policy(explicit_inputs=(self.root / "missing",))
        self.assertEqual(missing.exception.code, "read_input_invalid")

        unsafe = self.root / "env-script"
        unsafe.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        unsafe.chmod(unsafe.stat().st_mode | stat.S_IXUSR)
        with self.assertRaises(ReadIsolationError) as unresolved:
            self._policy(executable=unsafe)
        self.assertEqual(unresolved.exception.code, "runtime_dependencies_unresolved")

    def test_unsupported_host_and_bounds_fail_closed(self) -> None:
        with self.assertRaises(ReadIsolationError) as unsupported:
            self._policy(platform="linux")
        self.assertEqual(unsupported.exception.code, "read_isolation_unavailable")
        inputs = []
        for index in range(MAX_EXPLICIT_INPUTS + 1):
            path = self.root / f"input-{index}"
            path.write_text("x", encoding="utf-8")
            inputs.append(path)
        with self.assertRaises(ReadIsolationError) as bounded:
            self._policy(explicit_inputs=tuple(inputs))
        self.assertEqual(bounded.exception.code, "read_input_invalid")

    def test_unresolved_dependency_output_fails_closed(self) -> None:
        with mock.patch(
            "darwin_read_isolation._bounded_command",
            return_value=(str(self.runtime) + ":\n\t@rpath/escape.dylib (compatibility version 1.0.0)\n").encode(),
        ), self.assertRaises(ReadIsolationError) as unresolved:
            self._policy()
        self.assertEqual(unresolved.exception.code, "runtime_dependencies_unresolved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
