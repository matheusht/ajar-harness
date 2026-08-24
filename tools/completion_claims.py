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


def _manifest_bytes() -> tuple[bytes, tuple[int, int, int, int, int]]:
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
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode)
            if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode) or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
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


def _read_regular(parent_fd: int, name: str) -> tuple[bytes, tuple[int, int, int, int, int]]:
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise _failure("completion_claims_tree_unsafe")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise _failure("completion_claims_tree_changed")
        return b"".join(chunks), (*identity, before.st_mode)
    finally:
        os.close(fd)


def _scan_markdown(bound: Path, first_scope_hash: str) -> tuple[tuple[tuple[Any, ...], ...], tuple[tuple[str, str, int], ...]]:
    """Return a complete Markdown identity/content snapshot and non-generated claims."""
    root_fd = os.dup(int(bound.parts[3]))
    trees: list[tuple[Any, ...]] = []
    claims: list[tuple[str, str, int]] = []

    def walk(directory_fd: int, prefix: tuple[str, ...]) -> None:
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise _failure("completion_claims_tree_unreadable", first_scope_hash) from exc
        for name in names:
            try:
                name.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise _failure("completion_claims_tree_path_invalid", first_scope_hash) from exc
            relative_parts = (*prefix, name)
            relative = "/".join(relative_parts)
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise _failure("completion_claims_tree_unreadable", first_scope_hash) from exc
            if stat.S_ISLNK(entry.st_mode):
                raise _failure("completion_claims_tree_unsafe", first_scope_hash)
            if stat.S_ISDIR(entry.st_mode):
                trees.append((relative, "directory", entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_mode))
                child = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
                try:
                    walk(child, relative_parts)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(entry.st_mode):
                raise _failure("completion_claims_tree_unsafe", first_scope_hash)
            if not name.lower().endswith(".md"):
                trees.append((relative, "regular", entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_mode))
                continue
            try:
                data, identity = _read_regular(directory_fd, name)
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
                    path_hash = "sha256:" + hashlib.sha256(PATH_DOMAIN + first_scope_hash.encode("ascii") + b"\0" + relative.encode("utf-8")).hexdigest()
                    claims.append((path_hash, "sha256:" + content_hash, count))

    try:
        walk(root_fd, ())
    finally:
        os.close(root_fd)
    return tuple(trees), tuple(claims)


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


def assert_completion_claims_clear_bound(engagement: Path) -> dict[str, Any]:
    """Assert completion prose is justified, returning the reducer state used by a writer.

    ``engagement`` must be the exact root alias produced by an existing kernel lock.
    """
    if not _is_bound(engagement):
        raise _failure("completion_claims_bound_alias_required")
    if inspect_quarantine(engagement)["quarantined"]:
        raise _failure("completion_claims_quarantined")
    try:
        first = reduce_engagement(engagement)
        events = read_ledger(engagement, "event")
        first_scope = events[0]["payload"]["scope_hash"]
    except (OSError, IndexError, KeyError, RecordError) as exc:
        raise _failure("completion_claims_state_invalid") from exc
    try:
        manifest_one, manifest_identity_one = _manifest_bytes()
        pins = _parse_pins(manifest_one)
        tree_one, claims_one = _scan_markdown(engagement, first_scope)
        state_one = canonical_json_bytes(first)
        events_one = _bound_file_digest(engagement, "events.jsonl", first_scope)
        second = reduce_engagement(engagement)
        # This reducer-valid event list is captured as part of snapshot two and is the only
        # evidence examined for the terminal review linkage below.
        events_two_records = read_ledger(engagement, "event")
        tree_two, claims_two = _scan_markdown(engagement, first_scope)
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
    return second


def assert_completion_claims_clear(engagement: Path) -> dict[str, Any]:
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
