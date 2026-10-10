#!/usr/bin/env python3
"""Cross-engagement knowledge base (Phase 8 / Workstream B).

There is no cross-engagement memory in this harness. `winners.md` exists once per engagement and
nothing reads it afterwards, so every engagement starts cold in both directions. This is the gap
BETWEEN engagements only -- `engine/multi-round-orchestration.md` already handles the within-run
family registry, and this does not rebuild it.

One mechanism, two entry kinds. Four rules, each answering a way this fails (B.1):

  1. A loss must NAME THE CONTROL that held. Enforced by the schema for kind=loser.
  2. Each entry declares its TRANSFER SCOPE. This is what stops a Backstage result from
     suppressing a Kubernetes route.
  3. BOUNDED and ABANDONED are different and must be said.
  4. It changes ORDER, never removal.

Rule 4 is the one with teeth. ZSec's version multiplies a hardened target's priority down, which
buries a target that later went soft. `route` here applies a BOUNDED delta and always annotates;
`_assert_never_removes` fails loudly if the output route set ever differs from the input set.

D-09: never kills. A loser entry records that WE failed to find something -- evidence about our
search, not about the target. Killing on it converts "we did not find it" into "it is not there",
which is the omission error Skitka measured as untrainable.

Commands:
  add       validate one entry against the schema and append it to memory/kb.jsonl
  query     structured (not fuzzy) lookup -- CLAUDE.md 3 chose determinism on purpose
  route     apply the KB to a base routing order; emits reordering + annotations
  ablate    the promotion gate (B.3): an entry must change a routing decision or it is not promoted
  --self-test
"""

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from engagement_quarantine import quarantined_ancestor, require_safe_offline_output
from engagement_state import bound_engagement_lock
from ledger_health import probe_ledger_health

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(ROOT, "memory", "kb.jsonl")
SCHEMA_PATH = os.path.join(ROOT, "schemas", "kb-entry.schema.json")

# Rule 4: the delta is bounded so repeated losses cannot bury a route.
DELTA = {"winner": +1, "loser": -1}
DELTA_FLOOR, DELTA_CEIL = -1, +1


def _inside(path, directory):
    try:
        Path(path).resolve(strict=True).relative_to(Path(directory).resolve(strict=True))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _require_input_admissible(path, *, source_engagement=None, offline_only=False):
    """Keep portable KB inputs out of quarantined or unrelated governed evidence.

    A local source engagement is the one intentional exception: its operator-authorized promotion
    is serialized by ``bound_engagement_lock`` in ``cmd_add``. Explicit synthetic/public inputs
    and the portable KB itself must remain outside every engagement tree.
    """

    candidate = Path(os.path.abspath(path))
    if quarantined_ancestor(candidate):
        raise ValueError("knowledge-base input is quarantined")
    if offline_only or source_engagement is None or not _inside(candidate, source_engagement):
        # This helper is also the common governed-boundary predicate. It performs no write.
        require_safe_offline_output(candidate)


def _read_bound_relative(root_fd, relative):
    parts = Path(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("knowledge-base source-relative path is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            child = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        fd = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("knowledge-base input is not a regular file")
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("knowledge-base input changed during read")
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _read_stable_bytes(
    path, *, source_engagement=None, source_fd=None, offline_only=False
):
    """Read one regular file without following its leaf and recheck its source boundary."""

    absolute = Path(os.path.abspath(path))
    _require_input_admissible(
        absolute, source_engagement=source_engagement, offline_only=offline_only
    )
    if source_fd is not None and source_engagement is not None and _inside(
        absolute, source_engagement
    ):
        try:
            relative = absolute.resolve(strict=True).relative_to(
                Path(source_engagement).resolve(strict=True)
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("knowledge-base source-relative path is unsafe") from exc
        data = _read_bound_relative(source_fd, relative)
        _require_input_admissible(absolute, source_engagement=source_engagement)
        return data
    try:
        terminal = absolute.lstat()
        if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISREG(terminal.st_mode):
            raise ValueError("knowledge-base input is not a regular file")
        parent = absolute.parent.resolve(strict=True)
        parent_fd = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError("knowledge-base input could not be opened safely") from exc
    try:
        fd = os.open(
            absolute.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        try:
            before = os.fstat(fd)
            named = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(named.st_mode)
                or not stat.S_ISREG(named.st_mode)
                or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
            ):
                raise ValueError("knowledge-base input identity is unsafe")
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(fd)
            current = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("knowledge-base input changed during read")
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)
    _require_input_admissible(
        absolute, source_engagement=source_engagement, offline_only=offline_only
    )
    return b"".join(chunks)


def _load_json_file(path, *, source_engagement=None, source_fd=None):
    try:
        return json.loads(
            _read_stable_bytes(
                path, source_engagement=source_engagement, source_fd=source_fd
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("knowledge-base JSON input is malformed") from exc


def _open_kb_for_append(path):
    """Open a portable KB sink through one stable parent directory descriptor."""

    absolute = Path(os.path.abspath(path))
    require_safe_offline_output(absolute)
    try:
        parent = absolute.parent.resolve(strict=True)
        parent_entry = parent.lstat()
        if stat.S_ISLNK(parent_entry.st_mode) or not stat.S_ISDIR(parent_entry.st_mode):
            raise ValueError("knowledge-base output parent is unsafe")
        parent_fd = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise ValueError("knowledge-base output parent must already exist") from exc
    fd = -1
    try:
        parent_identity = os.fstat(parent_fd)
        fd = os.open(
            absolute.name,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        leaf = os.fstat(fd)
        named = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(leaf.st_mode)
            or stat.S_ISLNK(named.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (leaf.st_dev, leaf.st_ino) != (named.st_dev, named.st_ino)
        ):
            os.close(fd)
            raise ValueError("knowledge base is not a safely bound regular file")
        return absolute, parent, parent_fd, parent_identity, fd
    except Exception:
        if fd >= 0:
            os.close(fd)
        os.close(parent_fd)
        raise


def _require_kb_output_current(absolute, parent, parent_fd, parent_identity, fd):
    require_safe_offline_output(absolute)
    require_safe_offline_output(parent / absolute.name)
    current_parent = parent.lstat()
    current_leaf = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
    bound_leaf = os.fstat(fd)
    if (
        stat.S_ISLNK(current_parent.st_mode)
        or not stat.S_ISDIR(current_parent.st_mode)
        or (current_parent.st_dev, current_parent.st_ino)
        != (parent_identity.st_dev, parent_identity.st_ino)
        or stat.S_ISLNK(current_leaf.st_mode)
        or not stat.S_ISREG(current_leaf.st_mode)
        or (current_leaf.st_dev, current_leaf.st_ino) != (bound_leaf.st_dev, bound_leaf.st_ino)
    ):
        raise ValueError("knowledge-base output identity changed")


def _open_bound_source(path):
    """Open one source directory and retain its canonical pathname identity."""

    source = Path(os.path.abspath(path))
    fd = -1
    try:
        terminal = source.lstat()
        if stat.S_ISLNK(terminal.st_mode) or not stat.S_ISDIR(terminal.st_mode):
            raise ValueError("source engagement is not a regular directory")
        canonical = source.resolve(strict=True)
        fd = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        identity = os.fstat(fd)
        current = canonical.lstat()
        if (
            not stat.S_ISDIR(identity.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (identity.st_dev, identity.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ValueError("source engagement identity changed while opening")
        return fd, canonical, identity
    except Exception:
        if fd >= 0:
            os.close(fd)
        raise


def _require_bound_source_current(path, fd, identity):
    """Fail closed if the canonical pathname no longer names the opened source."""

    bound = os.fstat(fd)
    current = path.lstat()
    expected = (identity.st_dev, identity.st_ino)
    if (
        (bound.st_dev, bound.st_ino) != expected
        or not stat.S_ISDIR(bound.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != expected
    ):
        raise ValueError("source engagement identity changed during promotion")


def _parse_kb_bytes(data):
    out = []
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError("knowledge base is malformed") from exc
    return out


def _read_kb_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("knowledge base is not a regular file")
    chunks = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise ValueError("knowledge base changed during read")
    try:
        return _parse_kb_bytes(b"".join(chunks))
    except UnicodeDecodeError as exc:
        raise ValueError("knowledge base is malformed") from exc


def load_kb(path=KB_PATH):
    try:
        data = _read_stable_bytes(path, offline_only=True)
    except FileNotFoundError:
        return []
    try:
        return _parse_kb_bytes(data)
    except UnicodeDecodeError as exc:
        raise ValueError("knowledge base is malformed") from exc


def validate(entry):
    """Return a list of problems. Uses jsonschema when available, plus the rules it cannot express."""
    problems = []
    try:
        import jsonschema
        schema = json.load(open(SCHEMA_PATH))
        for err in sorted(jsonschema.Draft7Validator(schema).iter_errors(entry), key=str):
            problems.append(err.message)
    except ImportError:
        for field in ("schema_version", "id", "kind", "recorded_at", "mechanism_class",
                      "transfer_scope", "boundedness", "summary", "writer"):
            if field not in entry:
                problems.append(f"'{field}' is a required property")

    # Rule 1, restated here so it holds even without jsonschema installed.
    #
    # The first version of this check was `len(control) >= 20`, and the self-test caught it:
    # "we looked and found nothing" is 27 characters and sailed through. Length does not measure
    # whether a control was NAMED. Structure does -- a shrug cannot produce an evidence ref. Same
    # lesson as the attestable-vs-computable split in the promotion gates.
    if entry.get("kind") == "loser":
        control = entry.get("control")
        if not isinstance(control, dict):
            problems.append("kind=loser requires `control` as an object with `mechanism` and "
                            "`evidence`. A named control is evidenced; 'we looked and found "
                            "nothing' is an absence of work, not a loss.")
        else:
            if len(str(control.get("mechanism", "")).strip()) < 20:
                problems.append("control.mechanism must say HOW the control holds, in mechanism terms")
            if not control.get("evidence"):
                problems.append("control.evidence must carry at least one ref (file:line, record, "
                                "or attempt id). This is the gate a shrug cannot pass.")
    # Scrubbing: a mechanism_class carrying a target name defeats the whole point of transfer_scope.
    if entry.get("transfer_scope") == "this-mechanism-class" and entry.get("applies_to"):
        problems.append("transfer_scope=this-mechanism-class must not pin applies_to; that is a "
                        "narrower scope wearing a wider label")
    return problems


def matches(entry, ctx):
    """Does this entry bear on a target described by ctx? Structured and exact, never fuzzy."""
    scope = entry["transfer_scope"]
    at = entry.get("applies_to") or {}
    if scope == "this-mechanism-class":
        return True
    key = {"this-target": "target", "this-framework": "framework", "this-language": "language"}[scope]
    want, got = at.get(key), ctx.get(key)
    return want is not None and got is not None and want == got


def _assert_never_removes(base, out):
    """Rule 4 as an assertion, not a comment. Order may change; membership may not."""
    if {r["route"] for r in base} != {r["route"] for r in out}:
        raise SystemExit("BUG: routing output changed the route SET. The KB reorders, never removes.")


def route(base, ctx, kb):
    """Apply the KB to a base order.

    `base` is [{"route": str, "family": str, "priority": int}, ...] -- higher priority runs first.
    Returns the reordered list, each row carrying the annotations that moved it.
    """
    out = []
    for row in base:
        delta, notes = 0, []
        for e in kb:
            if not matches(e, ctx):
                continue
            fams, cards = set(e.get("family", [])), set(e.get("cards", []))
            if row["route"] not in cards and row.get("family") not in fams:
                continue
            delta += DELTA.get(e["kind"], 0)
            notes.append({
                "id": e["id"],
                "kind": e["kind"],
                "boundedness": e["boundedness"],
                "control_is_proven": bool(e.get("control_is_proven")),
                "summary": e["summary"],
                "reopen_on": e.get("reopen_on"),
            })
        delta = max(DELTA_FLOOR, min(DELTA_CEIL, delta))
        out.append({**row, "priority": row["priority"] + delta, "kb_delta": delta, "kb_notes": notes})
    # Stable: equal priority keeps the base order, so the KB only ever breaks ties it earned.
    out.sort(key=lambda r: -r["priority"])
    _assert_never_removes(base, out)
    return out


def order_of(rows):
    return [r["route"] for r in rows]


def ablate(entry, fixture, kb=None):
    """B.3 promotion gate: run routing with and without the entry. No order change -> not a lesson.

    Reuses the rule `tools/ablation.py` already encodes: a promoted lesson must change an outcome.
    """
    base, ctx = fixture["base"], fixture["context"]
    others = [e for e in (kb or []) if e["id"] != entry["id"]]
    without = order_of(route(base, ctx, others))
    with_ = order_of(route(base, ctx, others + [entry]))
    changed = with_ != without
    return changed, {"without": without, "with": with_}


def cmd_add(args):
    source_engagement = getattr(args, "source_engagement", None)
    source_kind = getattr(args, "source_kind", None)
    if bool(source_engagement) == bool(source_kind):
        print("REJECTED: choose exactly one local --source-engagement or explicit --source-kind synthetic/public.")
        return 1
    try:
        if source_engagement:
            source_fd, source, source_identity = _open_bound_source(source_engagement)
            try:
                # The lock, health read, and append all refer to one opened directory inode. A
                # pathname ABA therefore cannot substitute a healthy stale copy for a quarantined
                # source during the authorization check.
                with bound_engagement_lock(source_fd, create=False):
                    health = probe_ledger_health(Path(f"/dev/fd/{source_fd}"))
                    if health.get("status") != "healthy":
                        print("REJECTED: source engagement is not healthy and admissible.")
                        return 1
                    _require_bound_source_current(source, source_fd, source_identity)
                    return _cmd_add_authorized(
                        args,
                        source_engagement=source,
                        source_fd=source_fd,
                        source_guard=lambda: _require_bound_source_current(
                            source, source_fd, source_identity
                        ),
                    )
            finally:
                os.close(source_fd)
        return _cmd_add_authorized(args)
    except Exception:
        # Record, parser, and filesystem failures are deliberately collapsed: a portable KB
        # command must not echo target-local paths, parser details, or identifiers.
        if source_engagement:
            print("REJECTED: source engagement could not be verified as healthy and admissible.")
        else:
            print("REJECTED: knowledge-base entry could not be safely appended.")
        return 1


def _cmd_add_authorized(
    args, *, source_engagement=None, source_fd=None, source_guard=None
):
    entry = _load_json_file(
        args.file, source_engagement=source_engagement, source_fd=source_fd
    )
    problems = validate(entry)
    if problems:
        print("REJECTED:")
        for p in problems:
            print("  -", p)
        return 1
    if source_engagement is not None and (
        "engagement" in entry
        or ("ablation_fixture" in entry and not args.fixture)
    ):
        # The local engagement is an authorization source, never portable provenance. The
        # command owns ablation_fixture derivation so a target-local path cannot arrive through
        # a pre-populated entry when no fixture was actually checked.
        print("REJECTED: source-derived entry contains non-portable provenance.")
        return 1
    fixture_bytes = None
    fixture = None
    if args.fixture:
        fixture_bytes = _read_stable_bytes(
            args.fixture, source_engagement=source_engagement, source_fd=source_fd
        )
        try:
            fixture = json.loads(fixture_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("knowledge-base JSON input is malformed") from exc
    absolute, parent, parent_fd, parent_identity, lock_fd = _open_kb_for_append(args.kb)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        _require_kb_output_current(absolute, parent, parent_fd, parent_identity, lock_fd)
        kb = _read_kb_fd(lock_fd)
        if any(e["id"] == entry["id"] for e in kb):
            print(f"REJECTED: {entry['id']} already exists. The KB is append-only.")
            return 1

        if fixture is not None:
            changed, detail = ablate(entry, fixture, kb)
            if not changed:
                print("REJECTED by the ablation gate: the entry changes no routing decision.")
                print(f"  order without: {detail['without']}")
                print(f"  order with   : {detail['with']}")
                print("  An entry that changes nothing is noise. Drop it, or write a fixture that "
                      "shows what it actually moves.")
                return 1
            fixture_path = Path(os.path.abspath(args.fixture))
            try:
                portable_relative = fixture_path.resolve(strict=True).relative_to(
                    (Path(ROOT) / "fixtures").resolve(strict=True)
                )
            except (OSError, RuntimeError, ValueError):
                # Target-local paths are disclosure-sensitive. Preserve only the opaque content
                # commitment needed to identify the exact ablation input.
                entry["ablation_fixture"] = "sha256:" + hashlib.sha256(
                    fixture_bytes
                ).hexdigest()
            else:
                entry["ablation_fixture"] = (Path("fixtures") / portable_relative).as_posix()
            print(f"ablation gate: PASS  {detail['without']} -> {detail['with']}")
        elif not args.no_fixture:
            print("REJECTED: pass --fixture (the B.3 gate) or --no-fixture with a reason recorded "
                  "in the entry's writer.note.")
            return 1

        original_size = os.lseek(lock_fd, 0, os.SEEK_END)
        data = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
        try:
            _require_input_admissible(
                args.file, source_engagement=source_engagement
            )
            if args.fixture:
                _require_input_admissible(
                    args.fixture, source_engagement=source_engagement
                )
            if source_guard is not None:
                source_guard()
            _require_kb_output_current(
                absolute, parent, parent_fd, parent_identity, lock_fd
            )
            view = memoryview(data)
            written = 0
            while written < len(view):
                count = os.write(lock_fd, view[written:])
                if count <= 0:
                    raise OSError("append made no progress")
                written += count
            os.fsync(lock_fd)
            _require_input_admissible(
                args.file, source_engagement=source_engagement
            )
            if args.fixture:
                _require_input_admissible(
                    args.fixture, source_engagement=source_engagement
                )
            if source_guard is not None:
                source_guard()
            _require_kb_output_current(
                absolute, parent, parent_fd, parent_identity, lock_fd
            )
        except Exception:
            os.ftruncate(lock_fd, original_size)
            os.fsync(lock_fd)
            raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(parent_fd)
    print(f"added {entry['id']} ({entry['kind']}, {entry['transfer_scope']}, {entry['boundedness']})")
    return 0


def cmd_query(args):
    kb = load_kb(args.kb)
    ctx = {"target": args.target, "framework": args.framework, "language": args.language}
    hits = [e for e in kb if matches(e, ctx)]
    if args.family:
        hits = [e for e in hits if args.family in e.get("family", [])]
    if args.kind:
        hits = [e for e in hits if e["kind"] == args.kind]
    _require_input_admissible(args.kb, offline_only=True)
    if args.json:
        print(json.dumps(hits, indent=2, sort_keys=True))
        return 0
    if not hits:
        print("no entries bear on this context")
        return 0
    for e in hits:
        proven = " [control proven]" if e.get("control_is_proven") else ""
        print(f"{e['id']}  {e['kind']:7s} {e['boundedness']:9s} {e['transfer_scope']}{proven}")
        print(f"    {e['summary']}")
        if e.get("control"):
            print(f"    control: {e['control']['mechanism']}")
            print(f"    evidence: {', '.join(e['control']['evidence'])}")
        if e.get("reopen_on"):
            print(f"    reopens on: {e['reopen_on']}")
    return 0


def cmd_route(args):
    fx = _load_json_file(args.fixture)
    kb = load_kb(args.kb)
    rows = route(fx["base"], fx["context"], kb)
    _require_input_admissible(args.fixture)
    _require_input_admissible(args.kb, offline_only=True)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    print(f"base : {order_of(fx['base'])}")
    print(f"routed: {order_of(rows)}")
    for r in rows:
        if r["kb_notes"]:
            print(f"  {r['route']}  delta={r['kb_delta']:+d}")
            for n in r["kb_notes"]:
                print(f"     {n['id']} ({n['kind']}, {n['boundedness']}) {n['summary']}")
                if n["reopen_on"]:
                    print(f"        reopens on: {n['reopen_on']}")
    return 0


def cmd_ablate(args):
    entry = _load_json_file(args.file)
    fx = _load_json_file(args.fixture)
    changed, detail = ablate(entry, fx, load_kb(args.kb))
    _require_input_admissible(args.file)
    _require_input_admissible(args.fixture)
    _require_input_admissible(args.kb, offline_only=True)
    print(f"without: {detail['without']}")
    print(f"with   : {detail['with']}")
    print("ABLATION:", "PASS (changes a routing decision)" if changed else "FAIL (changes nothing)")
    return 0 if changed else 1


# ---------------------------------------------------------------- self-test

def _fx():
    return {
        "context": {"target": "acme-api", "framework": "express", "language": "javascript"},
        "base": [
            {"route": "path-traversal", "family": "traversal", "priority": 5},
            {"route": "ssrf-egress", "family": "ssrf", "priority": 5},
            {"route": "deser-gadget", "family": "deserialization", "priority": 4},
        ],
    }


def _loser():
    return {
        "schema_version": 1, "id": "KB-20260821-selftest-loser", "kind": "loser",
        "recorded_at": "2026-08-21", "mechanism_class": "path traversal via normalise-before-guard",
        "family": ["traversal"], "transfer_scope": "this-framework",
        "applies_to": {"framework": "express"}, "boundedness": "bounded",
        "control": {
            "mechanism": "the router normalises the path before the allowlist guard runs, so the "
                         "traversal family cannot reach the sink",
            "evidence": ["router/dispatch.js:88", "att-selftest-traversal-control"],
        },
        "summary": "traversal bounded by normalise-before-guard", "writer": {"role": "operator"},
        "reopen_on": "a sink reached without passing the router normaliser",
    }


def self_test():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  -> {detail}" if not cond and detail else ""))

    print("[self-test] rule 1 -- a loss must name the control")
    bare = {**_loser(), "control": {"mechanism": "we looked and found nothing", "evidence": []}}
    check("a shrug is rejected", validate(bare))
    unevidenced = {**_loser()}
    unevidenced["control"] = {**unevidenced["control"], "evidence": []}
    check("an unevidenced control is rejected", validate(unevidenced))
    check("a named control is accepted", not validate(_loser()), validate(_loser()))

    print("[self-test] rule 2 -- transfer scope stops false transfer")
    e = _loser()
    check("matches its own framework", matches(e, {"framework": "express"}))
    check("does NOT match another framework", not matches(e, {"framework": "django"}))
    check("does NOT match an absent framework", not matches(e, {"target": "other"}))
    wide = {**e, "transfer_scope": "this-mechanism-class", "applies_to": None}
    wide.pop("applies_to")
    check("mechanism-class transfers everywhere", matches(wide, {"framework": "django"}))

    print("[self-test] rule 4 -- reorders, never removes")
    fx, kb = _fx(), [_loser()]
    rows = route(fx["base"], fx["context"], kb)
    check("route set is unchanged", {r["route"] for r in rows} == {r["route"] for r in fx["base"]})
    check("the loser lost priority", [r for r in rows if r["route"] == "path-traversal"][0]["kb_delta"] == -1)
    check("it was demoted, not dropped", "path-traversal" in order_of(rows))
    moved = [r for r in rows if r["route"] == "path-traversal"][0]
    check("annotation carried", moved["kb_notes"] and moved["kb_notes"][0]["reopen_on"])
    check("order actually changed", order_of(rows) != order_of(fx["base"]))

    print("[self-test] delta is bounded -- repeated losses cannot bury a route")
    many = [{**_loser(), "id": f"KB-20260821-dup-{i}"} for i in range(9)]
    r2 = route(fx["base"], fx["context"], many)
    check("nine losers still move it by exactly -1",
          [r for r in r2 if r["route"] == "path-traversal"][0]["kb_delta"] == -1)

    print("[self-test] ablation gate")
    changed, _ = ablate(_loser(), _fx(), [])
    check("an entry that reorders PASSES", changed)
    inert = {**_loser(), "id": "KB-20260821-inert", "family": ["no-such-family"]}
    changed2, _ = ablate(inert, _fx(), [])
    check("an entry that changes nothing FAILS", not changed2)

    print("[self-test] D-09 -- it never kills")
    winner = {**_loser(), "id": "KB-20260821-w", "kind": "winner"}
    winner.pop("control")
    r3 = route(fx["base"], fx["context"], [winner])
    check("a winner promotes without removing anything",
          {r["route"] for r in r3} == {r["route"] for r in fx["base"]})

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--kb", default=KB_PATH)

    a = sub.add_parser("add"); common(a)
    a.add_argument("--file", required=True); a.add_argument("--fixture")
    source = a.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-engagement", type=Path)
    source.add_argument("--source-kind", choices=["synthetic", "public"])
    a.add_argument("--no-fixture", action="store_true"); a.set_defaults(fn=cmd_add)

    q = sub.add_parser("query"); common(q)
    for f in ("target", "framework", "language", "family", "kind"):
        q.add_argument(f"--{f}")
    q.add_argument("--json", action="store_true"); q.set_defaults(fn=cmd_query)

    r = sub.add_parser("route"); common(r)
    r.add_argument("--fixture", required=True); r.add_argument("--json", action="store_true")
    r.set_defaults(fn=cmd_route)

    b = sub.add_parser("ablate"); common(b)
    b.add_argument("--file", required=True); b.add_argument("--fixture", required=True)
    b.set_defaults(fn=cmd_ablate)

    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not getattr(args, "fn", None):
        ap.print_help(); return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
