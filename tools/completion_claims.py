#!/usr/bin/env python3
"""Fail-closed admission for prose that claims coverage completion.

The public reader deliberately admits only an already-bound ``/dev/fd/N`` engagement.
The CLI acquires the existing kernel lock without creating it; callers that will mutate
hold their own lock and use :func:`assert_completion_claims_clear_bound` directly.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engagement_records import RecordError, canonical_json_bytes
from engagement_quarantine import inspect_quarantine
from engagement_state import bound_engagement_source, read_ledger, reduce_engagement

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "engine" / "completion-claim-grandfather-pins.json"
PATH_DOMAIN = b"llm-redteam-harness:completion-claim-path:v1\0"
GENERATED_VIEWS = frozenset({
    "cleanup.generated.md", "memory/README.md", "progress.md", "reviews/README.md",
    "views/report-index.md", "views/submission-index.md",
})
CLAIM_TOKEN = re.compile(r"(?i)(?<![A-Za-z0-9_-])(?:covered-dry|coverage_dry)(?![A-Za-z0-9_-])")
HEX = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_TREE_DEPTH = 512
FileIdentity = tuple[int, int, int, int, int, int]


def _identity(item: os.stat_result) -> FileIdentity:
    return (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
    )


@dataclass(frozen=True)
class CompletionClaimsToken:
    """The exact admission snapshot a writer must consume before its mutation."""

    scope_hash: str
    genesis_record_hash: str
    tree: tuple[tuple[Any, ...], ...]
    claims: tuple[tuple[str, str, int], ...]
    state_bytes: bytes
    events_digest: str
    manifest_bytes: bytes
    manifest_identity: FileIdentity


@dataclass(frozen=True)
class CompletionClaimsAdmission:
    """Reducer state plus its immutable, re-checkable source token."""

    state: dict[str, Any]
    token: CompletionClaimsToken

    # Preserve the small pre-token convenience surface for in-tree callers and tests.
    def __getitem__(self, key: str) -> Any:
        return self.state[key]


def _failure(code: str, scope_hash: str | None = None, path_hash: str | None = None) -> RecordError:
    # The scope salt makes a diagnostic correlatable within one engagement without exposing its
    # directory, identifiers, or the Markdown text that triggered it.
    salt = (scope_hash or "unbound").encode("utf-8", "replace")
    prefix = hashlib.sha256(b"llm-redteam-harness:completion-claims:v1\0" + salt + b"\0" + (path_hash or "none").encode("ascii")).hexdigest()[:12]
    return RecordError(code, f"digest_prefix={prefix}")


def _is_bound(path: Path) -> bool:
    parts = path.absolute().parts
    if not (len(parts) == 4 and parts[0] == "/" and parts[1:3] == ("dev", "fd") and parts[3].isdigit()):
        return False
    try:
        opened = os.fstat(int(parts[3]))
    except OSError:
        return False
    if not stat.S_ISDIR(opened.st_mode):
        return False
    try:
        named = os.stat(path, follow_symlinks=True)
    except OSError:
        # Darwin fdescfs may not reopen an fd alias as a directory pathname. Its descriptor is
        # still checked as a directory; platforms that name the alias receive inode comparison.
        duplicate = os.dup(int(parts[3]))
        try:
            return stat.S_ISDIR(os.fstat(duplicate).st_mode)
        finally:
            os.close(duplicate)
    return stat.S_ISDIR(named.st_mode) and opened.st_ino == named.st_ino


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _manifest_bytes() -> tuple[bytes, FileIdentity]:
    """Read the fixed manifest once without following it, retaining its exact identity."""
    try:
        fd = os.open(MANIFEST_PATH, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("not regular")
            raw_parts: list[bytes] = []
            while True:
                part = os.read(fd, 1024 * 1024)
                if not part:
                    break
                raw_parts.append(part)
            raw = b"".join(raw_parts)
            after = os.fstat(fd)
            named = os.stat(MANIFEST_PATH, follow_symlinks=False)
            identity = _identity(before)
            if identity != _identity(after) or identity != _identity(named):
                raise ValueError("changed")
            return raw, identity
        finally:
            os.close(fd)
    except (OSError, ValueError) as exc:
        raise _failure("completion_claims_manifest_invalid") from exc


def _parse_pins(raw: bytes) -> dict[str, tuple[str, int]]:
    """Load the fixed, repository-owned canonical manifest; no runtime override exists."""
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _failure("completion_claims_manifest_invalid") from exc
    if raw != canonical_json_bytes(value) or not isinstance(value, dict) or set(value) != {"schema_version", "pins"} or value.get("schema_version") != 1 or not isinstance(value["pins"], list):
        raise _failure("completion_claims_manifest_invalid")
    pins: dict[str, tuple[str, int]] = {}
    tuples: list[tuple[str, str, int]] = []
    for pin in value["pins"]:
        if not isinstance(pin, dict) or set(pin) != {"path_sha256", "content_sha256", "claim_count"}:
            raise _failure("completion_claims_manifest_invalid")
        path_hash, content_hash, count = pin.get("path_sha256"), pin.get("content_sha256"), pin.get("claim_count")
        if (not isinstance(path_hash, str) or not HEX.fullmatch(path_hash) or not isinstance(content_hash, str)
                or not HEX.fullmatch(content_hash) or not isinstance(count, int) or isinstance(count, bool) or count < 1):
            raise _failure("completion_claims_manifest_invalid")
        if path_hash in pins:
            raise _failure("completion_claims_manifest_invalid")
        pins[path_hash] = (content_hash, count)
        tuples.append((path_hash, content_hash, count))
    if tuples != sorted(tuples):
        raise _failure("completion_claims_manifest_invalid")
    return pins


def load_pins() -> dict[str, tuple[str, int]]:
    """Load the fixed, repository-owned canonical manifest; no runtime override exists."""
    raw, _identity = _manifest_bytes()
    return _parse_pins(raw)


@dataclass
class _DirectoryFrame:
    """One owned directory descriptor in the iterative Markdown walk."""

    fd: int
    prefix: tuple[str, ...]
    names: list[str]
    entries: dict[str, FileIdentity]
    identity: FileIdentity
    position: int = 0
    parent_fd: int | None = None
    entry_name: str | None = None


def _read_regular(parent_fd: int, name: str, expected: FileIdentity | None = None) -> tuple[bytes, FileIdentity]:
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise _failure("completion_claims_tree_unsafe")
        if expected is not None and _identity(before) != expected:
            raise _failure("completion_claims_tree_changed")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        identity = _identity(before)
        try:
            named_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            # The opened inode is not enough: a rename can leave the descriptor readable while
            # replacing or removing the directory entry that the snapshot claims to describe.
            raise _failure("completion_claims_tree_changed") from exc
        if identity != _identity(after) or identity != _identity(named_after):
            raise _failure("completion_claims_tree_changed")
        return b"".join(chunks), identity
    finally:
        os.close(fd)


def _scan_markdown(bound: Path, first_scope_hash: str, genesis_record_hash: str) -> tuple[tuple[tuple[Any, ...], ...], tuple[tuple[str, str, int], ...]]:
    """Return a complete Markdown identity/content snapshot and non-generated claims."""
    root_fd = os.dup(int(bound.parts[3]))
    trees: list[tuple[Any, ...]] = []
    claims: list[tuple[str, str, int]] = []

    def names_for(directory_fd: int) -> list[str]:
        try:
            return sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise _failure("completion_claims_tree_unreadable", first_scope_hash) from exc

    def snapshot_entries(directory_fd: int) -> tuple[list[str], dict[str, FileIdentity]]:
        names = names_for(directory_fd)
        entries: dict[str, FileIdentity] = {}
        for name in names:
            try:
                name.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise _failure("completion_claims_tree_path_invalid", first_scope_hash) from exc
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise _failure("completion_claims_tree_changed", first_scope_hash) from exc
            entries[name] = _identity(entry)
        return names, entries

    # Frames, rather than recursive calls, prevent a hostile/deep tree from exhausting Python's
    # interpreter stack.  Each child descriptor is identity-checked against its lstat before use.
    stack: list[_DirectoryFrame] = []
    try:
        try:
            try:
                root_opened = os.fstat(root_fd)
            except OSError as exc:
                raise _failure("completion_claims_tree_unreadable", first_scope_hash) from exc
            if not stat.S_ISDIR(root_opened.st_mode):
                raise _failure("completion_claims_tree_unsafe", first_scope_hash)
            root_identity = _identity(root_opened)
            root_names, root_entries = snapshot_entries(root_fd)
        except Exception:
            os.close(root_fd)
            raise
        stack.append(_DirectoryFrame(root_fd, (), root_names, root_entries, root_identity))
        while stack:
            frame = stack[-1]
            directory_fd, prefix = frame.fd, frame.prefix
            if frame.position >= len(frame.names):
                try:
                    names_after = sorted(os.listdir(directory_fd))
                    opened_after = os.fstat(directory_fd)
                except OSError as exc:
                    raise _failure("completion_claims_tree_changed", first_scope_hash) from exc
                if names_after != frame.names or frame.identity != _identity(opened_after):
                    raise _failure("completion_claims_tree_changed", first_scope_hash)
                for entry_name in frame.names:
                    try:
                        entry_after = os.stat(
                            entry_name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise _failure("completion_claims_tree_changed", first_scope_hash) from exc
                    if frame.entries[entry_name] != _identity(entry_after):
                        raise _failure("completion_claims_tree_changed", first_scope_hash)
                try:
                    opened_final = os.fstat(directory_fd)
                except OSError as exc:
                    raise _failure("completion_claims_tree_changed", first_scope_hash) from exc
                if frame.identity != _identity(opened_final):
                    raise _failure("completion_claims_tree_changed", first_scope_hash)
                if frame.parent_fd is not None:
                    if frame.entry_name is None:
                        raise _failure("completion_claims_tree_changed", first_scope_hash)
                    try:
                        named_after = os.stat(
                            frame.entry_name,
                            dir_fd=frame.parent_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise _failure("completion_claims_tree_changed", first_scope_hash) from exc
                    if frame.identity != _identity(named_after):
                        raise _failure("completion_claims_tree_changed", first_scope_hash)
                stack.pop()
                os.close(directory_fd)
                continue
            name = frame.names[frame.position]
            frame.position += 1
            relative_parts = (*prefix, name)
            relative = "/".join(relative_parts)
            entry = frame.entries[name]
            entry_mode = entry[-1]
            if stat.S_ISLNK(entry_mode):
                raise _failure("completion_claims_tree_unsafe", first_scope_hash)
            if stat.S_ISDIR(entry_mode):
                trees.append((relative, "directory", *entry))
                try:
                    child = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
                except OSError as exc:
                    raise _failure("completion_claims_tree_unreadable", first_scope_hash) from exc
                try:
                    opened = os.fstat(child)
                    if not stat.S_ISDIR(opened.st_mode):
                        raise _failure("completion_claims_tree_unsafe", first_scope_hash)
                    if _identity(opened) != entry:
                        raise _failure("completion_claims_tree_changed", first_scope_hash)
                    if len(stack) >= MAX_TREE_DEPTH:
                        raise _failure("completion_claims_tree_depth_exceeded", first_scope_hash)
                    child_identity = _identity(opened)
                    child_names, child_entries = snapshot_entries(child)
                    stack.append(_DirectoryFrame(
                        child,
                        relative_parts,
                        child_names,
                        child_entries,
                        child_identity,
                        parent_fd=directory_fd,
                        entry_name=name,
                    ))
                except Exception:
                    os.close(child)
                    raise
                continue
            if not stat.S_ISREG(entry_mode):
                raise _failure("completion_claims_tree_unsafe", first_scope_hash)
            if not name.lower().endswith(".md"):
                trees.append((relative, "regular", *entry))
                continue
            try:
                data, identity = _read_regular(directory_fd, name, entry)
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _failure("completion_claims_markdown_invalid_utf8", first_scope_hash) from exc
            except OSError as exc:
                raise _failure("completion_claims_tree_unreadable", first_scope_hash) from exc
            content_hash = hashlib.sha256(data).hexdigest()
            trees.append((relative, "regular", *identity, content_hash))
            if relative not in GENERATED_VIEWS:
                count = len(CLAIM_TOKEN.findall(text))
                if count:
                    path_hash = "sha256:" + hashlib.sha256(
                        PATH_DOMAIN + first_scope_hash.encode("ascii") + b"\0"
                        + genesis_record_hash.encode("ascii") + b"\0" + relative.encode("utf-8")
                    ).hexdigest()
                    claims.append((path_hash, "sha256:" + content_hash, count))
        return tuple(trees), tuple(claims)
    except UnicodeEncodeError as exc:
        raise _failure("completion_claims_tree_path_invalid", first_scope_hash) from exc
    finally:
        # A failing child open leaves its parent frame live; close every still-owned descriptor.
        while stack:
            fd = stack.pop().fd
            try:
                os.close(fd)
            except OSError:
                pass


def _bound_file_digest(bound: Path, name: str, scope_hash: str) -> str:
    root_fd = os.dup(int(bound.parts[3]))
    try:
        data, _identity = _read_regular(root_fd, name)
    except (OSError, RecordError) as exc:
        raise _failure("completion_claims_state_invalid", scope_hash) from exc
    finally:
        os.close(root_fd)
    return hashlib.sha256(data).hexdigest()


def _dry_review_current(state: dict[str, Any], events: list[dict[str, Any]]) -> bool:
    if state.get("coverage") != "coverage_dry":
        return False
    scope_positions = [index for index, event in enumerate(events) if event.get("event_type") == "scope.attested"]
    if not scope_positions:
        return False
    current_scope_position = scope_positions[-1]
    current_scope = events[current_scope_position].get("payload", {}).get("scope_hash")
    if current_scope != state.get("scope_hash"):
        return False
    dry_events = [event for event in events[current_scope_position + 1:] if event.get("event_type") == "coverage.status_changed" and event.get("payload", {}).get("status") == "coverage_dry"]
    if not dry_events:
        return False
    latest = dry_events[-1]
    review_ref = latest.get("payload", {}).get("coverage_review_ref")
    review = next((event for event in events[current_scope_position + 1:] if event.get("event_id") == review_ref), None)
    return bool(review and review.get("event_type") == "review.coverage_completed" and review.get("payload", {}).get("verdict") == "coverage_dry")


def assert_completion_claims_clear_bound(engagement: Path) -> CompletionClaimsAdmission:
    """Assert completion prose is justified, returning the reducer state used by a writer.

    ``engagement`` must be the exact root alias produced by an existing kernel lock.
    """
    if not _is_bound(engagement):
        raise _failure("completion_claims_bound_alias_required")
    if inspect_quarantine(engagement)["quarantined"]:
        raise _failure("completion_claims_quarantined")
    try:
        events = read_ledger(engagement, "event")
        first_scope = events[0]["payload"]["scope_hash"]
        genesis_record_hash = events[0]["record_hash"]
        if not isinstance(first_scope, str) or not HEX.fullmatch(first_scope) or not isinstance(genesis_record_hash, str) or not HEX.fullmatch(genesis_record_hash):
            raise ValueError("invalid genesis")
    except (OSError, IndexError, KeyError, ValueError, RecordError) as exc:
        raise _failure("completion_claims_state_invalid") from exc
    try:
        # Scan first so an intentionally deep/hostile source has a stable completion-claims
        # failure rather than reaching recursive legacy reducer helpers.
        manifest_one, manifest_identity_one = _manifest_bytes()
        pins = _parse_pins(manifest_one)
        tree_one, claims_one = _scan_markdown(engagement, first_scope, genesis_record_hash)
        first = reduce_engagement(engagement)
        state_one = canonical_json_bytes(first)
        events_one = _bound_file_digest(engagement, "events.jsonl", first_scope)
        second = reduce_engagement(engagement)
        # This reducer-valid event list is captured as part of snapshot two and is the only
        # evidence examined for the terminal review linkage below.
        events_two_records = read_ledger(engagement, "event")
        if (not events_two_records
                or events_two_records[0].get("payload", {}).get("scope_hash") != first_scope
                or events_two_records[0].get("record_hash") != genesis_record_hash):
            raise _failure("completion_claims_snapshot_changed", first_scope)
        tree_two, claims_two = _scan_markdown(engagement, first_scope, genesis_record_hash)
        state_two = canonical_json_bytes(second)
        events_two = _bound_file_digest(engagement, "events.jsonl", first_scope)
        manifest_two, manifest_identity_two = _manifest_bytes()
    except RecordError as exc:
        if exc.code.startswith("completion_claims_"):
            raise
        raise _failure("completion_claims_source_unavailable") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise _failure("completion_claims_tree_unreadable", first_scope) from exc
    if tree_one != tree_two or state_one != state_two or events_one != events_two or claims_one != claims_two or manifest_one != manifest_two or manifest_identity_one != manifest_identity_two:
        raise _failure("completion_claims_snapshot_changed", first_scope)
    if inspect_quarantine(engagement)["quarantined"]:
        raise _failure("completion_claims_quarantined", first_scope)
    dry = _dry_review_current(second, events_two_records)
    if not dry:
        for path_hash, content_hash, count in claims_two:
            if pins.get(path_hash) != (content_hash, count):
                raise _failure("completion_claims_unjustified", first_scope, path_hash)
    token = CompletionClaimsToken(
        scope_hash=first_scope,
        genesis_record_hash=genesis_record_hash,
        tree=tree_two,
        claims=claims_two,
        state_bytes=state_two,
        events_digest=events_two,
        manifest_bytes=manifest_two,
        manifest_identity=manifest_identity_two,
    )
    return CompletionClaimsAdmission(state=second, token=token)


def assert_completion_claims_token_current_bound(engagement: Path, token: CompletionClaimsToken) -> dict[str, Any]:
    """Revalidate an admitted snapshot immediately before a sanctioned writer mutation."""
    if not _is_bound(engagement):
        raise _failure("completion_claims_bound_alias_required", token.scope_hash)
    if inspect_quarantine(engagement)["quarantined"]:
        raise _failure("completion_claims_quarantined", token.scope_hash)
    try:
        state = reduce_engagement(engagement)
        events = read_ledger(engagement, "event")
        if (not events or events[0].get("payload", {}).get("scope_hash") != token.scope_hash
                or events[0].get("record_hash") != token.genesis_record_hash):
            raise ValueError("genesis changed")
        tree, found = _scan_markdown(engagement, token.scope_hash, token.genesis_record_hash)
        events_digest = _bound_file_digest(engagement, "events.jsonl", token.scope_hash)
        manifest, identity = _manifest_bytes()
        if (tree != token.tree or found != token.claims or canonical_json_bytes(state) != token.state_bytes
                or events_digest != token.events_digest or manifest != token.manifest_bytes
                or identity != token.manifest_identity):
            raise _failure("completion_claims_admission_stale", token.scope_hash)
        if inspect_quarantine(engagement)["quarantined"]:
            raise _failure("completion_claims_quarantined", token.scope_hash)
        return state
    except RecordError as exc:
        if exc.code.startswith("completion_claims_"):
            raise
        raise _failure("completion_claims_source_unavailable", token.scope_hash) from exc
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise _failure("completion_claims_admission_stale", token.scope_hash) from exc


def assert_completion_claims_clear(engagement: Path) -> CompletionClaimsAdmission:
    """Read-only public entrypoint.  It never creates a kernel lock or changes the tree."""
    try:
        with bound_engagement_source(engagement, allow_ungoverned=False) as bound:
            return assert_completion_claims_clear_bound(bound)
    except RecordError as exc:
        if exc.code.startswith("completion_claims_"):
            raise
        raise _failure("completion_claims_source_unavailable") from exc
    except OSError as exc:
        raise _failure("completion_claims_source_unavailable") from exc


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="verify Markdown completion claims against current coverage evidence")
    parser.add_argument("--engagement", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        assert_completion_claims_clear(args.engagement)
    except RecordError as exc:
        sys.stdout.buffer.write(canonical_json_bytes({"code": exc.code, "digest_prefix": exc.message.removeprefix("digest_prefix="), "valid": False}))
        return 1
    sys.stdout.buffer.write(b'{"code":"completion_claims_clear","valid":true}\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
