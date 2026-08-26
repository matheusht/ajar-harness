#!/usr/bin/env python3
"""Black-box regression test for casebook source provenance and quarantine revocation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from engagement_quarantine import canonical_marker
from engagement_records import canonical_json_bytes
from engagement_state import initialize_engagement


TOOL = Path(__file__).with_name("casebook-retrieval-index.py")


def _run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )


def _query(casebooks: Path, term: str, resolver: Path | None = None) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    argv = ["--casebooks", str(casebooks), "--query", term]
    if resolver is not None:
        argv.extend(["--source-resolver", str(resolver)])
    result = _run(*argv)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = []
    return result, payload


def _healthy_source(path: Path, recorded_at: str = "2026-08-23T00:00:00Z") -> None:
    path.mkdir(parents=True)
    path.joinpath("scope.md").write_text(
        """# Scope - synthetic provenance test

## Surfaces in scope
- Local fixture only.
## Benign safe-objective set
- Retrieval provenance test.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
## Accounts / fixtures
- None.
## Authorization
- Operator: fixture-operator
- Date: 2026-08-23
- Signed: [x]
- Record kernel: `decision-0006-v1`
""",
        encoding="utf-8",
    )
    initialize_engagement(path, recorded_at)


def _casebook(path: Path, term: str) -> None:
    path.mkdir()
    path.joinpath("lessons.md").write_text(f"portable lesson {term}\n", encoding="utf-8")


def _identity_token(path: Path) -> dict[str, object]:
    identity = path.lstat()
    birthtime = getattr(identity, "st_birthtime", None)
    generation = getattr(identity, "st_gen", None)
    return {
        "device": identity.st_dev,
        "inode": identity.st_ino,
        "birthtime_ns": int(float(birthtime) * 1_000_000_000) if birthtime is not None else None,
        "generation": int(generation) if isinstance(generation, int) and generation > 0 else None,
    }


def _resolver_binding(path: Path, *, root_token: dict[str, object] | None = None) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    events = [json.loads(line) for line in resolved.joinpath("events.jsonl").read_text().splitlines()]
    snapshot = next(
        event["payload"]["scope_snapshot_path"]
        for event in reversed(events)
        if event.get("event_type") == "scope.attested"
    )
    return {
        "path": str(resolved),
        "instance": {
            "root": root_token or _identity_token(resolved),
            "events": _identity_token(resolved / "events.jsonl"),
            "scope_snapshot": _identity_token(resolved / snapshot),
        },
    }


def _run_with_aba(
    root: Path,
    *,
    source: Path,
    stale: Path,
    moved: Path,
    casebook: Path,
    argv: list[str],
) -> subprocess.CompletedProcess[str]:
    """Force a transient pathname swap after the source lock is acquired.

    The subprocess-only site hook is deliberately outside production code. It restores the
    original immediately before the portable casebook snapshot, reproducing the exact ABA that a
    path-open/path-check implementation would miss. FD-bound health/origin reads still see the
    quarantined original and fail before that snapshot.
    """

    hook = root / f"aba-hook-{casebook.name}"
    hook.mkdir()
    hook.joinpath("sitecustomize.py").write_text(
        """
import os

_source = os.environ["CASEBOOK_ABA_SOURCE"]
_stale = os.environ["CASEBOOK_ABA_STALE"]
_moved = os.environ["CASEBOOK_ABA_MOVED"]
_casebook = os.environ["CASEBOOK_ABA_CASEBOOK"]
_device = int(os.environ["CASEBOOK_ABA_DEVICE"])
_inode = int(os.environ["CASEBOOK_ABA_INODE"])
_real_open = os.open
_real_lstat = os.lstat
_armed = False
_swapped = False

def _open(path, flags, mode=0o777, *, dir_fd=None):
    global _armed
    fd = _real_open(path, flags, mode, dir_fd=dir_fd)
    try:
        if os.fsdecode(path) == ".record-kernel.lock" and dir_fd is not None:
            identity = os.fstat(dir_fd)
            if (identity.st_dev, identity.st_ino) == (_device, _inode):
                _armed = True
    except (OSError, TypeError, ValueError):
        pass
    return fd

def _bound_alias(path):
    text = os.fsdecode(path)
    pieces = text.split("/")
    if len(pieces) == 4 and pieces[1:3] == ["dev", "fd"] and pieces[3].isdigit():
        try:
            identity = os.fstat(int(pieces[3]))
            return (identity.st_dev, identity.st_ino) == (_device, _inode)
        except OSError:
            return False
    return False

def _lstat(path, *, dir_fd=None):
    global _swapped
    text = os.fsdecode(path)
    absolute = os.path.abspath(text)
    if _armed and not _swapped and dir_fd is None and (absolute == _source or _bound_alias(path)):
        os.rename(_source, _moved)
        os.rename(_stale, _source)
        _swapped = True
    elif _swapped and dir_fd is None and absolute == _casebook:
        os.rename(_source, _stale)
        os.rename(_moved, _source)
        _swapped = False
    return _real_lstat(path, dir_fd=dir_fd)

os.open = _open
os.lstat = _lstat
""".lstrip(),
        encoding="utf-8",
    )
    identity = source.lstat()
    env = os.environ.copy()
    env.update({
        "CASEBOOK_ABA_SOURCE": str(source),
        "CASEBOOK_ABA_STALE": str(stale),
        "CASEBOOK_ABA_MOVED": str(moved),
        "CASEBOOK_ABA_CASEBOOK": str(casebook),
        "CASEBOOK_ABA_DEVICE": str(identity.st_dev),
        "CASEBOOK_ABA_INODE": str(identity.st_ino),
        "PYTHONPATH": str(hook) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
    })
    result = _run(*argv, env=env)
    if moved.exists():
        source.rename(stale)
        moved.rename(source)
    return result


def _run_with_output_parent_relocated(
    root: Path,
    *,
    target_parent: Path,
    relocated_parent: Path,
    temporary_prefix: str,
    argv: list[str],
) -> tuple[subprocess.CompletedProcess[str], bool]:
    """Move a bound output parent under a governed root after its temp open.

    The move happens after open(2) has created the temporary leaf but before production code can
    write through that FD. A safe implementation notices that the bound parent no longer occupies
    its attested location, rolls the temporary entry back through the same parent FD, and rejects.
    """

    hook = root / f"output-parent-hook-{target_parent.name}"
    hook.mkdir()
    hook.joinpath("sitecustomize.py").write_text(
        """
import os

_target = os.environ["CASEBOOK_OUTPUT_PARENT"]
_relocated = os.environ["CASEBOOK_OUTPUT_RELOCATED"]
_prefix = os.environ["CASEBOOK_OUTPUT_TEMP_PREFIX"]
_device = int(os.environ["CASEBOOK_OUTPUT_PARENT_DEVICE"])
_inode = int(os.environ["CASEBOOK_OUTPUT_PARENT_INODE"])
_real_open = os.open
_moved = False

def _open(path, flags, mode=0o777, *, dir_fd=None):
    global _moved
    fd = _real_open(path, flags, mode, dir_fd=dir_fd)
    if (
        not _moved
        and dir_fd is not None
        and flags & os.O_CREAT
        and flags & os.O_EXCL
        and os.fsdecode(path).startswith(_prefix)
    ):
        identity = os.fstat(dir_fd)
        if (identity.st_dev, identity.st_ino) == (_device, _inode):
            os.rename(_target, _relocated)
            _moved = True
    return fd

os.open = _open
""".lstrip(),
        encoding="utf-8",
    )
    identity = target_parent.lstat()
    env = os.environ.copy()
    env.update({
        "CASEBOOK_OUTPUT_PARENT": str(target_parent),
        "CASEBOOK_OUTPUT_RELOCATED": str(relocated_parent),
        "CASEBOOK_OUTPUT_TEMP_PREFIX": temporary_prefix,
        "CASEBOOK_OUTPUT_PARENT_DEVICE": str(identity.st_dev),
        "CASEBOOK_OUTPUT_PARENT_INODE": str(identity.st_ino),
        "PYTHONPATH": str(hook) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
    })
    result = _run(*argv, env=env)
    relocated = relocated_parent.exists()
    if relocated:
        relocated_parent.rename(target_parent)
    return result, relocated


def _run_with_resolver_read_parent_relocated(
    root: Path,
    *,
    resolver: Path,
    relocated_parent: Path,
    argv: list[str],
) -> tuple[subprocess.CompletedProcess[str], bool]:
    """Move the resolver parent under quarantine immediately after its read FD opens."""

    hook = root / "resolver-read-parent-hook"
    hook.mkdir()
    hook.joinpath("sitecustomize.py").write_text(
        """
import os

_resolver = os.environ["CASEBOOK_READ_RESOLVER"]
_parent = os.environ["CASEBOOK_READ_PARENT"]
_relocated = os.environ["CASEBOOK_READ_RELOCATED"]
_device = int(os.environ["CASEBOOK_READ_PARENT_DEVICE"])
_inode = int(os.environ["CASEBOOK_READ_PARENT_INODE"])
_real_open = os.open
_moved = False

def _open(path, flags, mode=0o777, *, dir_fd=None):
    global _moved
    fd = _real_open(path, flags, mode, dir_fd=dir_fd)
    name = os.fsdecode(path)
    parent_matches = False
    if dir_fd is not None:
        identity = os.fstat(dir_fd)
        parent_matches = (identity.st_dev, identity.st_ino) == (_device, _inode)
    elif os.path.abspath(name) == _resolver:
        parent_matches = True
    if (
        not _moved
        and parent_matches
        and (name == os.path.basename(_resolver) or os.path.abspath(name) == _resolver)
        and flags & os.O_ACCMODE == os.O_RDONLY
    ):
        os.rename(_parent, _relocated)
        _moved = True
    return fd

os.open = _open
""".lstrip(),
        encoding="utf-8",
    )
    parent = resolver.parent
    identity = parent.lstat()
    env = os.environ.copy()
    env.update({
        "CASEBOOK_READ_RESOLVER": str(resolver),
        "CASEBOOK_READ_PARENT": str(parent),
        "CASEBOOK_READ_RELOCATED": str(relocated_parent),
        "CASEBOOK_READ_PARENT_DEVICE": str(identity.st_dev),
        "CASEBOOK_READ_PARENT_INODE": str(identity.st_ino),
        "PYTHONPATH": str(hook) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
    })
    result = _run(*argv, env=env)
    relocated = relocated_parent.exists()
    if relocated:
        relocated_parent.rename(parent)
    return result, relocated


def _run_with_transient_casebook_root_swap(
    root: Path,
    *,
    public_root: Path,
    marked_root: Path,
    targets: list[Path],
    argv: list[str],
) -> tuple[subprocess.CompletedProcess[str], int]:
    """Feed marked bytes only during pathname opens, restoring before every path check."""

    hook = root / "casebook-reuse-root-swap-hook"
    hook.mkdir()
    flag = root / "casebook-reuse-root-swap.flag"
    aside = root / "casebook-reuse-public-aside"
    hook.joinpath("sitecustomize.py").write_text(
        """
import json
import os

_public = os.environ["CASEBOOK_REUSE_PUBLIC_ROOT"]
_marked = os.environ["CASEBOOK_REUSE_MARKED_ROOT"]
_aside = os.environ["CASEBOOK_REUSE_ASIDE_ROOT"]
_targets = set(json.loads(os.environ["CASEBOOK_REUSE_TARGETS"]))
_target_names = {os.path.basename(value) for value in _targets}
_casebook_device = int(os.environ["CASEBOOK_REUSE_CASEBOOK_DEVICE"])
_casebook_inode = int(os.environ["CASEBOOK_REUSE_CASEBOOK_INODE"])
_flag = os.environ["CASEBOOK_REUSE_FLAG"]
_real_open = os.open
_active = False

def _open(path, flags, mode=0o777, *, dir_fd=None):
    global _active
    name = os.path.abspath(os.fsdecode(path)) if dir_fd is None else os.fsdecode(path)
    bound_casebook = False
    if dir_fd is not None:
        identity = os.fstat(dir_fd)
        bound_casebook = (identity.st_dev, identity.st_ino) == (
            _casebook_device, _casebook_inode
        )
    if (
        not _active
        and (name in _targets or (bound_casebook and name in _target_names))
        and flags & os.O_ACCMODE == os.O_RDONLY
    ):
        _active = True
        os.rename(_public, _aside)
        os.rename(_marked, _public)
        try:
            fd = _real_open(path, flags, mode, dir_fd=dir_fd)
        finally:
            os.rename(_public, _marked)
            os.rename(_aside, _public)
            _active = False
        with open(_flag, "a", encoding="utf-8") as handle:
            handle.write(name + "\\n")
        return fd
    return _real_open(path, flags, mode, dir_fd=dir_fd)

os.open = _open
""".lstrip(),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({
        "CASEBOOK_REUSE_PUBLIC_ROOT": str(public_root),
        "CASEBOOK_REUSE_MARKED_ROOT": str(marked_root),
        "CASEBOOK_REUSE_ASIDE_ROOT": str(aside),
        "CASEBOOK_REUSE_TARGETS": json.dumps([str(path) for path in targets]),
        "CASEBOOK_REUSE_CASEBOOK_DEVICE": str(targets[0].parent.stat().st_dev),
        "CASEBOOK_REUSE_CASEBOOK_INODE": str(targets[0].parent.stat().st_ino),
        "CASEBOOK_REUSE_FLAG": str(flag),
        "PYTHONPATH": str(hook) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
    })
    result = _run(*argv, env=env)
    if aside.exists():
        if public_root.exists() and not marked_root.exists():
            public_root.rename(marked_root)
        aside.rename(public_root)
    hits = len(flag.read_text(encoding="utf-8").splitlines()) if flag.is_file() else 0
    return result, hits


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="casebook-provenance-test-") as temporary:
        root = Path(temporary).resolve()
        casebooks = root / "casebooks"
        casebooks.mkdir()
        resolver = root / "local-source-resolver.json"

        legacy = casebooks / "legacy-unattested"
        _casebook(legacy, "legacyunattestedterm")
        legacy_result, legacy_rows = _query(casebooks, "legacyunattestedterm")
        checks.append((
            "unattested legacy casebooks fail closed",
            legacy_result.returncode == 0 and legacy_rows == [],
            legacy_result.stdout + legacy_result.stderr,
        ))

        synthetic = casebooks / "explicit-synthetic"
        _casebook(synthetic, "syntheticpositiveterm")
        synthetic_attest = _run(
            "attest", "--casebook", str(synthetic), "--source-kind", "synthetic"
        )
        synthetic_result, synthetic_rows = _query(casebooks, "syntheticpositiveterm")
        synthetic_provenance = (
            json.loads(synthetic.joinpath("source-provenance.json").read_text())
            if synthetic.joinpath("source-provenance.json").is_file()
            else {}
        )
        checks.append((
            "explicit synthetic attestation is a non-vacuous positive",
            synthetic_attest.returncode == 0
            and synthetic_result.returncode == 0
            and len(synthetic_rows) == 1
            and synthetic_provenance.get("source_kind") == "synthetic"
            and synthetic_provenance.get("origin_ref") is None
            and synthetic_provenance.get("source_instance_ref") is None,
            synthetic_attest.stdout + synthetic_attest.stderr + synthetic_result.stdout + synthetic_result.stderr,
        ))

        source = root / "source-fixture"
        _healthy_source(source)
        derived = casebooks / "engagement-derived"
        _casebook(derived, "dynamicrevocationterm")
        derived_attest = _run(
            "attest",
            "--casebook", str(derived),
            "--source-engagement", str(source),
            "--source-resolver", str(resolver),
        )
        resolved_result, resolved_rows = _query(casebooks, "dynamicrevocationterm", resolver)
        unresolved_result, unresolved_rows = _query(casebooks, "dynamicrevocationterm")
        provenance_path = derived / "source-provenance.json"
        provenance_bytes = provenance_path.read_bytes() if provenance_path.is_file() else b""
        checks.append((
            "engagement-derived reuse requires live target-local resolution",
            derived_attest.returncode == 0
            and resolved_result.returncode == 0
            and len(resolved_rows) == 1
            and unresolved_result.returncode == 0
            and unresolved_rows == []
            and source.name.encode() not in provenance_bytes
            and str(source).encode() not in provenance_bytes,
            derived_attest.stdout + derived_attest.stderr + resolved_result.stdout + resolved_result.stderr,
        ))

        resolver_document = json.loads(resolver.read_text())
        origin = next(iter(resolver_document["origins"]))
        correct_source = resolver_document["origins"][origin]

        stale_copy = root / "stale-parent" / source.name
        shutil.copytree(source, stale_copy)
        resolver_before_rebind = resolver.read_bytes()
        rejected_rebind = _run(
            "attest",
            "--casebook", str(derived),
            "--source-engagement", str(stale_copy),
            "--source-resolver", str(resolver),
        )
        checks.append((
            "the attestation command cannot rebind an origin to an identical stale copy",
            rejected_rebind.returncode != 0
            and resolver.read_bytes() == resolver_before_rebind,
            rejected_rebind.stdout + rejected_rebind.stderr,
        ))

        wrong_source = root / "wrong-source-fixture"
        _healthy_source(wrong_source)
        resolver_document["origins"][origin] = _resolver_binding(wrong_source)
        resolver.write_bytes(canonical_json_bytes(resolver_document))
        wrong_source_result, wrong_source_rows = _query(
            casebooks, "dynamicrevocationterm", resolver
        )
        resolver_document["origins"][origin] = {
            "path": str(root / "missing-source-fixture"),
            "instance": correct_source["instance"],
        }
        resolver.write_bytes(canonical_json_bytes(resolver_document))
        missing_source_result, missing_source_rows = _query(
            casebooks, "dynamicrevocationterm", resolver
        )
        same_identity_wrong_genesis = root / "wrong-parent" / source.name
        _healthy_source(same_identity_wrong_genesis, "2026-08-23T00:00:09Z")
        resolver_document["origins"][origin] = _resolver_binding(same_identity_wrong_genesis)
        resolver.write_bytes(canonical_json_bytes(resolver_document))
        wrong_genesis_result, wrong_genesis_rows = _query(
            casebooks, "dynamicrevocationterm", resolver
        )
        resolver_document["origins"][origin] = correct_source
        resolver.write_bytes(canonical_json_bytes(resolver_document))
        checks.append((
            "an opaque origin cannot be rebound to a wrong or missing healthy source",
            wrong_source_result.returncode == 0
            and wrong_source_rows == []
            and missing_source_result.returncode == 0
            and missing_source_rows == []
            and wrong_genesis_result.returncode == 0
            and wrong_genesis_rows == [],
            wrong_source_result.stdout + wrong_source_result.stderr
            + missing_source_result.stdout + missing_source_result.stderr
            + wrong_genesis_result.stdout + wrong_genesis_result.stderr,
        ))

        original_lesson = derived.joinpath("lessons.md").read_bytes()
        derived.joinpath("lessons.md").write_bytes(original_lesson + b"changed after attestation\n")
        drifted_result, drifted_rows = _query(casebooks, "dynamicrevocationterm", resolver)
        checks.append((
            "portable content drift invalidates the source attestation",
            drifted_result.returncode == 0 and drifted_rows == [],
            drifted_result.stdout + drifted_result.stderr,
        ))
        provenance_before_refresh = derived.joinpath("source-provenance.json").read_bytes()
        rejected_refresh = _run(
            "attest",
            "--casebook", str(derived),
            "--source-engagement", str(source),
            "--source-resolver", str(resolver),
        )
        checks.append((
            "an attestation collision cannot rewrite or relabel portable provenance",
            rejected_refresh.returncode != 0
            and derived.joinpath("source-provenance.json").read_bytes() == provenance_before_refresh,
            rejected_refresh.stdout + rejected_refresh.stderr,
        ))
        derived.joinpath("lessons.md").write_bytes(original_lesson)

        marker = {
            "schema_version": 1,
            "status": "quarantined",
            "operator_id": "fixture-operator",
            "reason": "operator-integrity-review",
            "recorded_at": "2026-08-23T00:01:00Z",
            "authority_challenge_digest": "sha256:" + "1" * 64,
            "record_fingerprint": "sha256:" + "2" * 64,
        }
        marker_path = source / "legacy" / "quarantine" / "ledger-quarantined.json"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_bytes(canonical_marker(marker))
        revoked_result, revoked_rows = _query(casebooks, "dynamicrevocationterm", resolver)
        checks.append((
            "a source marked after import drops out on the next reuse",
            revoked_result.returncode == 0
            and revoked_rows == []
            and "dynamicrevocationterm" not in revoked_result.stderr,
            revoked_result.stdout + revoked_result.stderr,
        ))

        resolver_document = json.loads(resolver.read_text())
        resolver_document["origins"][origin] = _resolver_binding(stale_copy)
        resolver.write_bytes(canonical_json_bytes(resolver_document))
        stale_rebind_result, stale_rebind_rows = _query(
            casebooks, "dynamicrevocationterm", resolver
        )
        checks.append((
            "manual resolver rebinding to a byte-identical stale copy cannot evade revocation",
            stale_rebind_result.returncode == 0 and stale_rebind_rows == [],
            stale_rebind_result.stdout + stale_rebind_result.stderr,
        ))

        resolver_document["origins"][origin] = _resolver_binding(
            stale_copy,
            root_token=correct_source["instance"]["root"],
        )
        resolver.write_bytes(canonical_json_bytes(resolver_document))
        root_collision_result, root_collision_rows = _query(
            casebooks, "dynamicrevocationterm", resolver
        )
        checks.append((
            "a mocked root-inode collision is rejected by child-file instance binding",
            root_collision_result.returncode == 0 and root_collision_rows == [],
            root_collision_result.stdout + root_collision_result.stderr,
        ))

        aba_source = root / "aba-source"
        _healthy_source(aba_source, "2026-08-23T00:01:30Z")
        aba_casebook = casebooks / "aba-derived"
        _casebook(aba_casebook, "abarevocationterm")
        aba_attest = _run(
            "attest",
            "--casebook", str(aba_casebook),
            "--source-engagement", str(aba_source),
            "--source-resolver", str(resolver),
        )
        aba_stale = root / "aba-stale"
        aba_moved = root / "aba-original-moved"
        shutil.copytree(aba_source, aba_stale)
        aba_marker = aba_source / "legacy" / "quarantine" / "ledger-quarantined.json"
        aba_marker.parent.mkdir(parents=True, exist_ok=True)
        aba_marker.write_bytes(canonical_marker(marker))
        aba_result = _run_with_aba(
            root,
            source=aba_source,
            stale=aba_stale,
            moved=aba_moved,
            casebook=aba_casebook,
            argv=[
                "--casebooks", str(casebooks),
                "--query", "abarevocationterm",
                "--source-resolver", str(resolver),
            ],
        )
        try:
            aba_rows = json.loads(aba_result.stdout)
        except json.JSONDecodeError:
            aba_rows = ["invalid-output"]
        checks.append((
            "a transient healthy-copy ABA cannot hide a quarantined source during reuse",
            aba_attest.returncode == 0
            and aba_result.returncode == 0
            and aba_rows == []
            and aba_marker.is_file(),
            aba_attest.stdout + aba_attest.stderr + aba_result.stdout + aba_result.stderr,
        ))

        aba_import_source = root / "aba-import-source"
        _healthy_source(aba_import_source, "2026-08-23T00:01:45Z")
        aba_import_stale = root / "aba-import-stale"
        aba_import_moved = root / "aba-import-original-moved"
        shutil.copytree(aba_import_source, aba_import_stale)
        aba_import_marker = (
            aba_import_source / "legacy" / "quarantine" / "ledger-quarantined.json"
        )
        aba_import_marker.parent.mkdir(parents=True, exist_ok=True)
        aba_import_marker.write_bytes(canonical_marker(marker))
        aba_import_casebook = casebooks / "aba-import-derived"
        _casebook(aba_import_casebook, "abaimportterm")
        aba_import_result = _run_with_aba(
            root,
            source=aba_import_source,
            stale=aba_import_stale,
            moved=aba_import_moved,
            casebook=aba_import_casebook,
            argv=[
                "attest",
                "--casebook", str(aba_import_casebook),
                "--source-engagement", str(aba_import_source),
                "--source-resolver", str(resolver),
            ],
        )
        checks.append((
            "a transient healthy-copy ABA cannot authorize engagement-derived import",
            aba_import_result.returncode != 0
            and not aba_import_casebook.joinpath("source-provenance.json").exists()
            and aba_import_marker.is_file(),
            aba_import_result.stdout + aba_import_result.stderr,
        ))

        swap_source = root / "rename-swap-source"
        _healthy_source(swap_source, "2026-08-23T00:02:00Z")
        swap_casebook = casebooks / "rename-swap-derived"
        _casebook(swap_casebook, "renameswapterm")
        swap_attest = _run(
            "attest",
            "--casebook", str(swap_casebook),
            "--source-engagement", str(swap_source),
            "--source-resolver", str(resolver),
        )
        stale_swap = root / "rename-swap-stale"
        moved_original = root / "rename-swap-original-moved"
        shutil.copytree(swap_source, stale_swap)
        swap_source.rename(moved_original)
        stale_swap.rename(swap_source)
        swap_result, swap_rows = _query(casebooks, "renameswapterm", resolver)
        checks.append((
            "a byte-identical directory rename-swap at the resolved path fails closed",
            swap_attest.returncode == 0
            and swap_result.returncode == 0
            and swap_rows == [],
            swap_attest.stdout + swap_attest.stderr + swap_result.stdout + swap_result.stderr,
        ))

        reuse_public_root = root / "casebook-reuse-public"
        reuse_public_casebooks = reuse_public_root / "casebooks"
        reuse_public_casebooks.mkdir(parents=True)
        reuse_public_casebook = reuse_public_casebooks / "ancestor-swap"
        _casebook(reuse_public_casebook, "healthycasebookterm")
        reuse_public_attest = _run(
            "attest", "--casebook", str(reuse_public_casebook), "--source-kind", "synthetic"
        )
        reuse_marked_root = root / "casebook-reuse-marked"
        reuse_marked_casebooks = reuse_marked_root / "casebooks"
        reuse_marked_casebooks.mkdir(parents=True)
        reuse_marked_casebook = reuse_marked_casebooks / "ancestor-swap"
        _casebook(reuse_marked_casebook, "SECRET-MARKED-CASEBOOK")
        reuse_marked_attest = _run(
            "attest", "--casebook", str(reuse_marked_casebook), "--source-kind", "synthetic"
        )
        reuse_marker = reuse_marked_root / "legacy" / "quarantine" / "ledger-quarantined.json"
        reuse_marker.parent.mkdir(parents=True)
        reuse_marker.write_bytes(canonical_marker(marker))
        reuse_swap_result, reuse_swap_hits = _run_with_transient_casebook_root_swap(
            root,
            public_root=reuse_public_root,
            marked_root=reuse_marked_root,
            targets=[
                reuse_public_casebook / "source-provenance.json",
                reuse_public_casebook / "lessons.md",
            ],
            argv=[
                "--casebooks", str(reuse_public_casebooks),
                "--query", "SECRET-MARKED-CASEBOOK",
            ],
        )
        try:
            reuse_swap_rows = json.loads(reuse_swap_result.stdout)
        except json.JSONDecodeError:
            reuse_swap_rows = ["invalid-output"]
        checks.append((
            "portable casebook reuse binds its tree across a transient marked ancestor swap",
            reuse_public_attest.returncode == 0
            and reuse_marked_attest.returncode == 0
            and reuse_swap_hits >= 2
            and reuse_swap_result.returncode == 0
            and reuse_swap_rows == []
            and reuse_marker.is_file()
            and "SECRET-MARKED-CASEBOOK" not in reuse_swap_result.stderr,
            reuse_public_attest.stdout + reuse_public_attest.stderr
            + reuse_marked_attest.stdout + reuse_marked_attest.stderr
            + reuse_swap_result.stdout + reuse_swap_result.stderr,
        ))

        blocked = casebooks / "blocked-import"
        _casebook(blocked, "blockedimportterm")
        blocked_attest = _run(
            "attest",
            "--casebook", str(blocked),
            "--source-engagement", str(source),
            "--source-resolver", str(resolver),
        )
        checks.append((
            "promotion/import refuses a quarantined local source before portable mutation",
            blocked_attest.returncode != 0
            and not blocked.joinpath("source-provenance.json").exists()
            and "dynamicrevocationterm" not in blocked_attest.stdout + blocked_attest.stderr,
            blocked_attest.stdout + blocked_attest.stderr,
        ))

        sink_engagement = root / "governed-sink"
        _healthy_source(sink_engagement, "2026-08-23T00:03:00Z")
        governed_casebooks = sink_engagement / "portable-casebooks"
        governed_casebooks.mkdir()
        query_casebook_staging = casebooks / "query-attested"
        _casebook(query_casebook_staging, "governedqueryterm")
        premark_attest = _run(
            "attest", "--casebook", str(query_casebook_staging), "--source-kind", "synthetic"
        )
        query_casebook = governed_casebooks / query_casebook_staging.name
        query_casebook_staging.rename(query_casebook)
        blocked_casebook = governed_casebooks / "blocked-write"
        _casebook(blocked_casebook, "governedwriteterm")
        sink_marker = sink_engagement / "legacy" / "quarantine" / "ledger-quarantined.json"
        sink_marker.parent.mkdir(parents=True, exist_ok=True)
        sink_marker.write_bytes(canonical_marker(marker))
        direct_sink = _run(
            "attest", "--casebook", str(blocked_casebook), "--source-kind", "synthetic"
        )
        linked_casebooks = root / "linked-governed-casebooks"
        linked_casebooks.symlink_to(governed_casebooks, target_is_directory=True)
        symlink_sink = _run(
            "attest",
            "--casebook", str(linked_casebooks / blocked_casebook.name),
            "--source-kind", "synthetic",
        )
        governed_query_result, governed_query_rows = _query(
            governed_casebooks, "governedqueryterm"
        )
        resolver_sink_casebook = casebooks / "resolver-sink-derived"
        _casebook(resolver_sink_casebook, "resolversinkterm")
        resolver_sink = _run(
            "attest",
            "--casebook", str(resolver_sink_casebook),
            "--source-engagement", str(wrong_source),
            "--source-resolver", str(sink_engagement / "local-resolver.json"),
        )
        checks.append((
            "casebook writes and reads reject direct and symlinked governed sinks",
            premark_attest.returncode == 0
            and direct_sink.returncode != 0
            and symlink_sink.returncode != 0
            and not blocked_casebook.joinpath("source-provenance.json").exists()
            and governed_query_result.returncode == 0
            and governed_query_rows == []
            and resolver_sink.returncode != 0
            and not resolver_sink_casebook.joinpath("source-provenance.json").exists()
            and not sink_engagement.joinpath("local-resolver.json").exists(),
            json.dumps({
                "premark": premark_attest.returncode,
                "direct": direct_sink.returncode,
                "symlink": symlink_sink.returncode,
                "blocked_provenance": blocked_casebook.joinpath("source-provenance.json").exists(),
                "query": governed_query_result.returncode,
                "rows": governed_query_rows,
                "resolver": resolver_sink.returncode,
                "resolver_provenance": resolver_sink_casebook.joinpath("source-provenance.json").exists(),
                "resolver_file": sink_engagement.joinpath("local-resolver.json").exists(),
            }, sort_keys=True)
            + premark_attest.stdout + premark_attest.stderr
            + direct_sink.stdout + direct_sink.stderr
            + symlink_sink.stdout + symlink_sink.stderr
            + governed_query_result.stdout + governed_query_result.stderr
            + resolver_sink.stdout + resolver_sink.stderr,
        ))

        resolver_read_parent = root / "resolver-read-parent-aba"
        resolver_read_parent.mkdir()
        resolver_read_path = resolver_read_parent / "resolver.json"
        resolver_read_casebook = casebooks / "resolver-read-parent-derived"
        _casebook(resolver_read_casebook, "resolverreadparentterm")
        resolver_read_attest = _run(
            "attest",
            "--casebook", str(resolver_read_casebook),
            "--source-engagement", str(wrong_source),
            "--source-resolver", str(resolver_read_path),
        )
        resolver_read_before = (
            resolver_read_path.read_bytes() if resolver_read_path.is_file() else b""
        )
        relocated_read_parent = sink_engagement / "relocated-resolver-read-parent"
        resolver_read_aba, resolver_read_moved = _run_with_resolver_read_parent_relocated(
            root,
            resolver=resolver_read_path,
            relocated_parent=relocated_read_parent,
            argv=[
                "--casebooks", str(casebooks),
                "--query", "resolverreadparentterm",
                "--source-resolver", str(resolver_read_path),
            ],
        )
        try:
            resolver_read_rows = json.loads(resolver_read_aba.stdout)
        except json.JSONDecodeError:
            resolver_read_rows = ["invalid-output"]
        resolver_read_after = (
            resolver_read_path.read_bytes() if resolver_read_path.is_file() else b"missing"
        )
        checks.append((
            "resolver read fails closed when its bound parent moves under quarantine",
            resolver_read_attest.returncode == 0
            and resolver_read_moved
            and resolver_read_aba.returncode == 0
            and resolver_read_rows == []
            and resolver_read_after == resolver_read_before,
            json.dumps({
                "attest": resolver_read_attest.returncode,
                "moved": resolver_read_moved,
                "query": resolver_read_aba.returncode,
                "rows": resolver_read_rows,
            }, sort_keys=True)
            + resolver_read_attest.stdout + resolver_read_attest.stderr
            + resolver_read_aba.stdout + resolver_read_aba.stderr,
        ))

        governed_parent_sink = root / "governed-parent-aba-sink"
        _healthy_source(governed_parent_sink, "2026-08-23T00:04:00Z")
        parent_aba_casebook = casebooks / "parent-aba-provenance"
        _casebook(parent_aba_casebook, "parentabaprovenanceterm")
        relocated_casebook = governed_parent_sink / "relocated-portable-casebook"
        provenance_parent_aba, provenance_parent_moved = _run_with_output_parent_relocated(
            root,
            target_parent=parent_aba_casebook,
            relocated_parent=relocated_casebook,
            temporary_prefix=".source-provenance.json.",
            argv=[
                "attest",
                "--casebook", str(parent_aba_casebook),
                "--source-kind", "synthetic",
            ],
        )
        provenance_entries = sorted(entry.name for entry in parent_aba_casebook.iterdir())
        checks.append((
            "portable provenance rolls back when its bound parent moves under governance",
            provenance_parent_moved
            and provenance_parent_aba.returncode != 0
            and provenance_entries == ["lessons.md"],
            json.dumps({
                "moved": provenance_parent_moved,
                "returncode": provenance_parent_aba.returncode,
                "entries": provenance_entries,
            }, sort_keys=True)
            + provenance_parent_aba.stdout + provenance_parent_aba.stderr,
        ))

        resolver_parent = root / "resolver-parent-aba"
        resolver_parent.mkdir()
        parent_aba_resolver = resolver_parent / "parent-aba-resolver.json"
        resolver_parent_casebook = casebooks / "parent-aba-resolver-derived"
        _casebook(resolver_parent_casebook, "parentabaresolverterm")
        relocated_resolver_parent = sink_engagement / "relocated-resolver-parent"
        resolver_parent_aba, resolver_parent_moved = _run_with_output_parent_relocated(
            root,
            target_parent=resolver_parent,
            relocated_parent=relocated_resolver_parent,
            temporary_prefix=".parent-aba-resolver.json.",
            argv=[
                "attest",
                "--casebook", str(resolver_parent_casebook),
                "--source-engagement", str(wrong_source),
                "--source-resolver", str(parent_aba_resolver),
            ],
        )
        resolver_entries = sorted(entry.name for entry in resolver_parent.iterdir())
        checks.append((
            "resolver write rolls back when its lock-bound parent moves under quarantine",
            resolver_parent_moved
            and resolver_parent_aba.returncode != 0
            and resolver_entries == [".parent-aba-resolver.json.lock"]
            and not resolver_parent_casebook.joinpath("source-provenance.json").exists(),
            json.dumps({
                "moved": resolver_parent_moved,
                "returncode": resolver_parent_aba.returncode,
                "resolver_entries": resolver_entries,
                "portable_provenance": resolver_parent_casebook.joinpath(
                    "source-provenance.json"
                ).exists(),
            }, sort_keys=True)
            + resolver_parent_aba.stdout + resolver_parent_aba.stderr,
        ))

    ok = True
    for label, passed, detail in checks:
        ok &= passed
        print(f"  {'ok  ' if passed else 'FAIL'} {label}")
        if not passed and detail:
            print("       " + detail.strip().replace("\n", " ")[:240])
    print("CASEBOOK-PROVENANCE: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
