#!/usr/bin/env python3
"""Q-02 prompt-ablation adjudicator (Phase 5).

Roadmap Q-02: does the hand-authored per-target goal prompt earn what it costs? One target, two
arms, one variable. This computes the comparison from two arm directories and applies the
PREREGISTERED decision rule.

The design rule here is the one this repository keeps re-learning: **do not let a tool assert what
it cannot compute.**

  computable from source bytes package inventory, M2 candidates, M5 cost proxies
  admitted by bound assessment M1 legacy packages
  partly computable             M3 severity profile, M4 family coverage
  JUDGED, never computed        M6 overlap (needs the same-finding root-cause rule)
                                M7 waste (needs a human reading rounds)

M6 and M7 are the two that decide the verdict, and neither can be derived from a file listing. The
tool emits a worksheet for them and REFUSES to issue a verdict until a blinded adjudicator fills it
in. A tool that guessed M6 would be the harness grading its own homework, which is the failure mode
the whole preregistration exists to prevent.

The threshold and licensing boundary are read from a frozen portable decision-rule checkpoint,
never hardcoded here. Its source rule's pre-data status is operator-attested, not Git-proven. The
tracked checkpoint is deliberately not a portable copy of the engagement outcome: it contains only
the target-agnostic fields this adjudicator consumes and opaque hashes of complete local sources
whose current location and resolution this repository does not establish.

Commands:
  measure   compute what is computable; emit the judged-metric worksheet
  verdict   apply the preregistered rule to measurements + a filled worksheet
  --self-test
"""

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath

from engagement_quarantine import (
    _current_directory_path,
    atomic_write_offline,
    quarantined_ancestor,
    read_safe_offline_file,
    require_safe_offline_output,
)
from engagement_records import RecordError, validate_record
from engagement_state import bound_engagement_lock, require_not_quarantined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREREG = os.path.join(
    ROOT,
    "fixtures",
    "preregistration",
    "phase5-q02-prompt-ablation-portable.json",
)

_TOP_LEVEL_KEYS = {
    "schema_version",
    "artifact_kind",
    "checkpoint_id",
    "checkpointed_at",
    "source_preregistration_id",
    "source_pins",
    "portable_boundary",
    "decision_rule",
}
_SOURCE_PIN_KEYS = {
    "complete_preregistration_sha256",
    "complete_outcome_sha256",
    "resolution",
    "historical_provenance",
}
_BOUNDARY_KEYS = {
    "complete_preregistration_included",
    "outcome_content_included",
    "target_or_engagement_details_included",
}
_DECISION_RULE_KEYS = {
    "m1_gap_threshold",
    "threshold_expression",
    "maximum_license_if_decisive",
    "maximum_license_text_if_decisive",
    "inconclusive_license_text",
}
_LICENSE_SCOPE_KEYS = {
    "hypothesis_and_second_target",
    "doctrine_change",
    "candidate_promotion",
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FROZEN_CHECKPOINT_SHA256 = "f69a2258f4c939005781d5882caabd48888ae0cada7646d73ddfd71aa21d78d6"


def _stable_regular_bytes(path):
    return read_safe_offline_file(Path(path))


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has missing or unexpected fields")


def _validate_portable_prereg(doc):
    """Validate the portable boundary before consuming any rule field."""

    _require_exact_keys(doc, _TOP_LEVEL_KEYS, "portable checkpoint")
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("unsupported portable checkpoint schema")
    if doc["artifact_kind"] != "q02_portable_decision_rule":
        raise ValueError("wrong portable checkpoint kind")
    if doc["checkpoint_id"] != "Q02-PROMPT-ABLATION-PORTABLE-v1":
        raise ValueError("wrong portable checkpoint id")
    if not isinstance(doc["checkpointed_at"], str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}",
        doc["checkpointed_at"],
    ):
        raise ValueError("portable checkpoint has no bounded timestamp")
    if doc["source_preregistration_id"] != "PREREG-20260816-phase5-q02-prompt-ablation":
        raise ValueError("wrong operator-attested source id")

    source_pins = doc["source_pins"]
    _require_exact_keys(source_pins, _SOURCE_PIN_KEYS, "source pins")
    hashes = (
        source_pins["complete_preregistration_sha256"],
        source_pins["complete_outcome_sha256"],
    )
    if any(not isinstance(value, str) or not _SHA256.fullmatch(value) for value in hashes):
        raise ValueError("source pin is not a lowercase SHA-256 digest")
    if hashes[0] == hashes[1]:
        raise ValueError("distinct source records cannot share one opaque pin")
    if source_pins["resolution"] != "opaque_local_unresolved":
        raise ValueError("portable checkpoint overstates source resolution")
    if source_pins["historical_provenance"] != "operator_attested_not_git_proven":
        raise ValueError("portable checkpoint overstates historical provenance")

    boundary = doc["portable_boundary"]
    _require_exact_keys(boundary, _BOUNDARY_KEYS, "portable boundary")
    if any(type(boundary[key]) is not bool or boundary[key] for key in _BOUNDARY_KEYS):
        raise ValueError("portable checkpoint claims to include non-portable content")

    rule = doc["decision_rule"]
    _require_exact_keys(rule, _DECISION_RULE_KEYS, "decision rule")
    threshold = rule["m1_gap_threshold"]
    if type(threshold) is not int or not 1 <= threshold <= 99:
        raise ValueError("invalid preregistered threshold")
    expression = rule["threshold_expression"]
    if not isinstance(expression, str):
        raise ValueError("threshold expression is not text")
    match = re.fullmatch(r"M1\(A\)\s*-\s*M1\(B\)\s*>=\s*(\d+)", expression)
    if not match or int(match.group(1)) != threshold:
        raise ValueError("threshold fields disagree")

    license_scope = rule["maximum_license_if_decisive"]
    _require_exact_keys(license_scope, _LICENSE_SCOPE_KEYS, "license scope")
    if license_scope != {
        "hypothesis_and_second_target": True,
        "doctrine_change": False,
        "candidate_promotion": False,
    }:
        raise ValueError("portable checkpoint grants a stronger license")
    decisive_text = rule["maximum_license_text_if_decisive"]
    inconclusive_text = rule["inconclusive_license_text"]
    for license_text in (decisive_text, inconclusive_text):
        if (
            not isinstance(license_text, str)
            or license_text != license_text.strip()
            or not 80 <= len(license_text) <= 1000
            or any(ord(character) < 32 for character in license_text)
        ):
            raise ValueError("invalid licensing text")
    normalized_license = decisive_text.casefold()
    if not all(
        marker in normalized_license
        for marker in (
            "n=1",
            "decisive result",
            "hypothesis",
            "second target",
            "does not license",
        )
    ):
        raise ValueError("licensing text contradicts the bounded license scope")
    if not all(
        marker in inconclusive_text.casefold()
        for marker in ("no prompt conclusion", "candidate promotion", "vendor filing")
    ):
        raise ValueError("inconclusive licensing text grants a prompt conclusion")
    return threshold, doc


def _threshold_from_bytes(data):
    """Pull the >=N finding gap out of frozen bytes. Never hardcode it here."""

    if hashlib.sha256(data).hexdigest() != _FROZEN_CHECKPOINT_SHA256:
        raise ValueError("portable checkpoint does not match its repository trust anchor")
    doc = json.loads(data, object_pairs_hook=_reject_duplicate_keys)
    return _validate_portable_prereg(doc)


def read_threshold(prereg_path=PREREG):
    return _threshold_from_bytes(_stable_regular_bytes(prereg_path))


def _snapshot_bound_tree(root_fd):
    """Snapshot one locked arm without reopening its public pathname."""

    result = {}

    def visit(directory_fd, prefix):
        current_path = _current_directory_path(directory_fd)
        if current_path is not None and quarantined_ancestor(current_path):
            raise RecordError("engagement_quarantined", "ablation source is quarantined")
        before_directory = os.fstat(directory_fd)
        names = sorted(os.listdir(directory_fd))
        for name in names:
            if name == ".record-kernel.lock":
                continue
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            relative = (*prefix, name)
            if stat.S_ISLNK(entry.st_mode):
                raise RecordError("q02_source_unsafe", "ablation source contains a symbolic link")
            if stat.S_ISDIR(entry.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    visit(child, relative)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(entry.st_mode):
                raise RecordError("q02_source_unsafe", "ablation source contains a non-regular entry")
            fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                dir_fd=directory_fd,
            )
            try:
                before = os.fstat(fd)
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
                ) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    raise RecordError("q02_source_changed", "ablation source changed during read")
            finally:
                os.close(fd)
            result["/".join(relative)] = b"".join(chunks)
        after_directory = os.fstat(directory_fd)
        if (
            before_directory.st_dev,
            before_directory.st_ino,
            before_directory.st_mtime_ns,
            before_directory.st_ctime_ns,
        ) != (
            after_directory.st_dev,
            after_directory.st_ino,
            after_directory.st_mtime_ns,
            after_directory.st_ctime_ns,
        ) or names != sorted(os.listdir(directory_fd)):
            raise RecordError("q02_source_changed", "ablation source changed during read")
        current_path = _current_directory_path(directory_fd)
        if current_path is not None and quarantined_ancestor(current_path):
            raise RecordError("engagement_quarantined", "ablation source is quarantined")

    visit(root_fd, ())
    return result


def _jsonl_count_bytes(data):
    if data is None:
        return 0
    return len([_load_json(line) for line in data.splitlines() if line.strip()])


def _measure_arm_snapshot(tree, display_path):
    def package_ids(directory):
        return sorted(
            {
                parts[1]
                for relative in tree
                if len(parts := PurePosixPath(relative).parts) >= 3 and parts[0] == directory
            }
        )

    severity = {}
    for relative, data in tree.items():
        parts = PurePosixPath(relative).parts
        if len(parts) != 3 or parts[0] != "findings" or parts[2] != "finding.json":
            continue
        try:
            band = (json.loads(data).get("severity") or {})
            band = band.get("band") if isinstance(band, dict) else band
        except Exception:
            band = None
        severity[band or "unstated"] = severity.get(band or "unstated", 0) + 1
    progress = tree.get("progress.md")
    subagents = None
    if progress is not None:
        try:
            text = progress.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        numbers = [
            int(value)
            for value in re.findall(
                r"(?:subagents?|agents?)[^0-9\n]{0,20}(\d{1,3})", text, re.I
            )
        ]
        subagents = sum(numbers) if numbers else None
    return {
        "path": display_path,
        "package_inventory": package_ids("findings"),
        "M2_candidates": package_ids("unproven"),
        "M3_severity": severity,
        "M5_attempts": _jsonl_count_bytes(tree.get("attempts.jsonl")),
        "M5_events": _jsonl_count_bytes(tree.get("events.jsonl")),
        "M5_subagents": subagents,
    }


WORKSHEET = {
    "_instructions": "Filled by an adjudicator who ran NEITHER arm, judging packages with arm "
                     "labels, paths and timestamps stripped. See the preregistration's "
                     "same_finding_rule: two findings are the same only if they share a root cause "
                     "-- the same defective decision in the same function or config key.",
    "adjudicator": None,
    "blinding_held": None,
    "run_record": {
        "ran_concurrently": None,
        "sequence_order_if_sequential": None,
        "cross_arm_read_occurred": None,
        "limit_truncated_an_arm": None
    },
    "M6_overlap": {"both_arms": None, "arm_a_only": None, "arm_b_only": None},
    "M7_waste": {"arm_a_wasted_rounds": None, "arm_b_wasted_rounds": None,
                 "waste_class_a_avoided_that_b_hit": None},
    "M4_families": {"arm_a": None, "arm_b": None}
}


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _source_commitment(root, trees):
    payload = {"root": str(root), "arms": {
        arm: {path: _digest(data) for path, data in sorted(tree.items())}
        for arm, tree in zip(("arm_a", "arm_b"), trees)
    }}
    return {**payload, "sha256": _digest(_json_bytes(payload))}


@contextmanager
def _bound_sources(source_root):
    """Hold existing source locks; the caller rechecks immediately before publication."""
    root = Path(source_root).absolute()
    descriptors = []
    try:
        root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                          | getattr(os, "O_NOFOLLOW", 0))
        descriptors.append(root_fd)
        with ExitStack() as locks:
            bounds = [locks.enter_context(bound_engagement_lock(root_fd, create=False))]
            for arm in ("arm-a", "arm-b"):
                fd = os.open(arm, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                             | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
                descriptors.append(fd)
                bounds.append(locks.enter_context(bound_engagement_lock(fd, create=False)))
            identities = [(os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in descriptors]
            trees = [_snapshot_bound_tree(fd) for fd in descriptors[1:]]

            def recheck():
                for bound in bounds:
                    require_not_quarantined(bound)
                for path, identity in zip((root, root / "arm-a", root / "arm-b"), identities):
                    current = os.stat(path, follow_symlinks=False)
                    if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != identity:
                        raise ValueError("ablation source identity changed")
                if trees != [_snapshot_bound_tree(fd) for fd in descriptors[1:]]:
                    raise ValueError("ablation source bytes changed")

            recheck()
            yield trees, recheck
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def cmd_measure(args):
    try:
        if args.worksheet:
            require_safe_offline_output(Path(args.worksheet))
            if os.path.exists(args.worksheet) and not args.force:
                raise ValueError("worksheet exists; pass --force to overwrite")
        for name in ("case_id", "run_id"):
            value = getattr(args, name, None)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("case/run identity must be nonblank text")
        source_root = Path(args.engagement).absolute()
        with _bound_sources(source_root) as (trees, recheck):
            out = {
                "schema_version": 1,
                "case_id": getattr(args, "case_id", None),
                "run_id": getattr(args, "run_id", None),
                "source": _source_commitment(source_root, trees),
                "arm_a": _measure_arm_snapshot(trees[0], str(source_root / "arm-a")),
                "arm_b": _measure_arm_snapshot(trees[1], str(source_root / "arm-b")),
                "computed_only": "Inventory is not M1 eligibility. M6 and M7 require bound adjudication.",
            }
            output = _json_bytes(out)
            worksheet = {**WORKSHEET, "schema_version": 1,
                         "case_id": out["case_id"], "run_id": out["run_id"],
                         "measurement_sha256": _digest(output),
                         "source_sha256": out["source"]["sha256"],
                         "eligibility_ref": None, "waste_ref": None}
            recheck()
            if args.worksheet:
                require_safe_offline_output(Path(args.worksheet))
                atomic_write_offline(Path(args.worksheet), _json_bytes(worksheet))
            sys.stdout.write(output.decode("utf-8"))
            if args.worksheet:
                sys.stderr.write(f"\nworksheet written to {args.worksheet}\n")
        return 0
    except (RecordError, OSError, ValueError, TypeError, RecursionError) as error:
        raise SystemExit("cannot measure ablation evidence: unsafe, changed, or malformed input") from error


def _decide_frozen(m, w, threshold):
    """Apply the preregistered rule. Returns (verdict, reasons, blockers)."""
    blockers = []
    if w.get("blinding_held") is False:
        blockers.append("blinding failed: the M6 split is unreliable and must be reported as such")
    rr = w.get("run_record") or {}
    if rr.get("limit_truncated_an_arm"):
        blockers.append("an account/rate limit truncated one arm: the equal-budget rule broke, so "
                        "a full arm would be compared against a cut-short one")
    if rr.get("cross_arm_read_occurred"):
        blockers.append("a cross-arm read occurred: the arms are not independent")
    for k in ("both_arms", "arm_a_only", "arm_b_only"):
        if (w.get("M6_overlap") or {}).get(k) is None:
            blockers.append(f"M6_overlap.{k} is unfilled -- it is judged, and the tool will not guess it")
    if blockers:
        return "inconclusive", ["preregistration guard tripped"], blockers

    a, b = len(m["arm_a"]["M1_findings"]), len(m["arm_b"]["M1_findings"])
    gap = a - b
    reasons = [f"M1(A)={a}, M1(B)={b}, gap={gap:+d}, preregistered threshold >= {threshold}"]

    if a == 0 and b == 0:
        reasons.append("both arms found nothing; a two-arm null says nothing about prompts")
        return "inconclusive", reasons, []

    waste = (w.get("M7_waste") or {}).get("waste_class_a_avoided_that_b_hit")
    if gap >= threshold:
        reasons.append("the finding gap meets the preregistered threshold")
        return "prompt_earns_its_keep", reasons, []
    if waste:
        reasons.append(f"arm A avoided a documented waste class arm B hit: {waste}")
        return "prompt_earns_its_keep", reasons, []
    if b >= a:
        reasons.append("arm B matched or beat arm A")
        return "prompt_does_not_earn_its_keep", reasons, []

    sa, sb = m["arm_a"].get("M5_subagents"), m["arm_b"].get("M5_subagents")
    if abs(gap) <= 1:
        if sa is not None and sb is not None and sa > sb:
            reasons.append(f"gap <= 1 while arm A cost more (subagents {sa} vs {sb})")
            return "prompt_does_not_earn_its_keep", reasons, []
        reasons.append("gap <= 1 and cost is not recorded on both arms, so the cost clause cannot "
                       "be evaluated; a gap of one was preregistered as noise")
        return "inconclusive", reasons, []
    return "inconclusive", reasons + ["no preregistered branch matched"], []


def _license_text_for_verdict(doc, verdict):
    rule = doc["decision_rule"]
    if verdict == "inconclusive":
        return rule["inconclusive_license_text"]
    return rule["maximum_license_text_if_decisive"]


def _load_json(data):
    def reject_constant(value):
        raise ValueError("nonfinite JSON number")

    return json.loads(data, object_pairs_hook=_reject_duplicate_keys, parse_constant=reject_constant)


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    return value


def _text(value, label):
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(label + ' must be nonblank text')
    return value


def _count(value, label):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(label + ' must be a nonnegative integer')


def _ids(value, label):
    if not isinstance(value, list):
        raise ValueError(label + ' must be an array')
    for item in value:
        if _text(item, label) is None:
            raise ValueError(label + ' contains a null identity')
    if len(set(value)) != len(value):
        raise ValueError(label + ' contains duplicate identities')
    return value


def _hash(value, label):
    if value is not None and (not isinstance(value, str) or not _SHA256.fullmatch(value)):
        raise ValueError(label + ' must be a lowercase SHA-256')
    return value


@contextmanager
def _admitted_decision(m, w, threshold, *, measurement_bytes=None, reference_base=None):
    """Validate every present dimension before applying incomplete-input handling or the rule."""
    missing = []
    references = []
    _object(m, 'measurement'); _object(w, 'worksheet')
    if measurement_bytes is not None and _load_json(measurement_bytes) != m:
        raise ValueError('measurement object differs from declared bytes')

    def required(value, label):
        if value is None:
            missing.append(label + ' is missing')
        return value

    def version(record, label):
        if 'schema_version' not in record:
            missing.append(label + ' version is missing')
        elif type(record['schema_version']) is not int:
            raise ValueError(label + ' version must be an integer')
        elif record['schema_version'] != 1:
            missing.append(label + ' version is unsupported')

    def identity(record, field, label):
        return required(_text(record.get(field), label + '.' + field), label + '.' + field)

    def answer(record, field, label):
        value = record.get(field)
        if value is not None and type(value) is not bool:
            raise ValueError(label + '.' + field + ' must be boolean')
        return required(value, label + '.' + field)

    def reference(value, label):
        if value is None:
            missing.append(label + ' reference is missing')
            return None
        _object(value, label)
        path = required(_text(value.get('path'), label + '.path'), label + '.path')
        expected = required(_hash(value.get('sha256'), label + '.sha256'), label + '.sha256')
        if path is None:
            return None
        path = Path(path)
        if not path.is_absolute():
            if reference_base is None:
                missing.append(label + ' has no reference base')
                return None
            path = reference_base / path
        if quarantined_ancestor(path):
            raise ValueError('reference is quarantined')
        try:
            data = _stable_regular_bytes(path)
        except (OSError, ValueError) as error:
            cause = error.__cause__
            if isinstance(error, FileNotFoundError) or isinstance(cause, FileNotFoundError):
                missing.append(label + ' reference is unavailable')
                return None
            raise
        references.append((path, data))
        if expected is not None and _digest(data) != expected:
            raise ValueError(label + ' byte commitment mismatch')
        return data

    for record, label in ((m, 'measurement'), (w, 'worksheet')):
        version(record, label)
        for field in ('case_id', 'run_id'):
            identity(record, field, label)
    identity(w, 'adjudicator', 'worksheet')
    answer(w, 'blinding_held', 'worksheet')
    rr = _object(w.get('run_record', {}), 'run_record')
    for field in ('ran_concurrently', 'cross_arm_read_occurred', 'limit_truncated_an_arm'):
        answer(rr, field, 'run_record')
    order = rr.get('sequence_order_if_sequential')
    if order is not None and order not in ('arm_a_then_arm_b', 'arm_b_then_arm_a'):
        raise ValueError('invalid sequential order')
    if rr.get('ran_concurrently') is False and order is None:
        missing.append('sequential run order is missing')
    overlap = _object(w.get('M6_overlap', {}), 'M6_overlap')
    for field in ('both_arms', 'arm_a_only', 'arm_b_only'):
        _count(overlap.get(field), 'M6_overlap.' + field)
        required(overlap.get(field), 'M6_overlap.' + field)
    waste = _object(w.get('M7_waste', {}), 'M7_waste')
    for field in ('arm_a_wasted_rounds', 'arm_b_wasted_rounds'):
        _count(waste.get(field), field)
    assertion = _text(waste.get('waste_class_a_avoided_that_b_hit'), 'waste assertion')
    families = _object(w.get('M4_families', {}), 'M4_families')
    for arm in ('arm_a', 'arm_b'):
        if families.get(arm) is not None:
            _ids(families[arm], 'M4_families.' + arm)
        record = _object(m.get(arm, {}), arm)
        for field in ('package_inventory', 'M1_findings', 'M2_candidates'):
            if field in record:
                _ids(record[field], arm + '.' + field)
        if 'package_inventory' not in record:
            missing.append(arm + ' source inventory is missing (old M1 input is not eligibility)')
        for field in ('M5_attempts', 'M5_events', 'M5_subagents'):
            _count(record.get(field), arm + '.' + field)
        if 'M3_severity' in record:
            for band, count in _object(record['M3_severity'], 'severity').items():
                _text(band, 'severity band'); _count(count, 'severity count')
                if count is None:
                    raise ValueError('null severity count')

    source = _object(m.get('source', {}), 'source')
    source_root = required(_text(source.get('root'), 'source.root'), 'source.root')
    source_hash = required(_hash(source.get('sha256'), 'source.sha256'), 'source.sha256')
    manifest = _object(source.get('arms', {}), 'source.arms')
    for arm in ('arm_a', 'arm_b'):
        if arm not in manifest:
            missing.append('source manifest for ' + arm + ' is missing')
        for path, digest in _object(manifest.get(arm, {}), 'manifest arm').items():
            _text(path, 'manifest path')
            if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
                raise ValueError('unsafe manifest path')
            if _hash(digest, 'manifest digest') is None:
                raise ValueError('null manifest digest')
    if source_hash is not None and source_root is not None and set(manifest) == {'arm_a', 'arm_b'}:
        if source_hash != _digest(_json_bytes({'root': source_root, 'arms': manifest})):
            raise ValueError('source commitment mismatch')
    elif set(manifest) - {'arm_a', 'arm_b'}:
        raise ValueError('unknown source arm')

    def binding(record, label):
        for field in ('case_id', 'run_id', 'adjudicator'):
            value = identity(record, field, label)
            expected = w.get(field)
            if value is not None and expected is not None and value != expected:
                raise ValueError(label + ' identity mismatch')
        for field, expected in (('source_sha256', source_hash),
                                ('measurement_sha256', _digest(measurement_bytes)
                                 if measurement_bytes is not None else None)):
            actual = required(_hash(record.get(field), label + '.' + field), label + '.' + field)
            if actual is not None and expected is not None and actual != expected:
                raise ValueError(label + ' binding mismatch')

    binding(w, 'worksheet')
    for field in ('case_id', 'run_id'):
        if m.get(field) is not None and w.get(field) is not None and m[field] != w[field]:
            raise ValueError('measurement/worksheet identity mismatch')
    if measurement_bytes is None:
        missing.append('exact measurement bytes are unavailable')
    assessment_bytes = reference(w.get('eligibility_ref'), 'eligibility')
    assessment = _load_json(assessment_bytes) if assessment_bytes is not None else None
    package_map = {}
    if assessment is not None:
        _object(assessment, 'eligibility'); version(assessment, 'eligibility'); binding(assessment, 'eligibility')
        compatibility = _object(assessment.get('compatibility', {}), 'compatibility')
        compatible = answer(compatibility, 'compatible', 'compatibility')
        for field, expected in (('M1_unit', 'legacy_packages'), ('M6_unit', 'root_cause_groups')):
            unit = identity(compatibility, field, 'compatibility')
            if unit is not None and unit != expected:
                missing.append(field + ' interpretation is unsupported')
        identity(compatibility, 'basis', 'compatibility')
        if compatible is not True:
            missing.append('frozen-rule M1/M6 unit compatibility is unestablished')
        packages = assessment.get('packages')
        if packages is None:
            missing.append('package eligibility assessment is missing')
            packages = []
        if not isinstance(packages, list):
            raise ValueError('eligibility packages must be an array')
        for package in packages:
            _object(package, 'package assessment')
            arm = identity(package, 'arm', 'package')
            package_id = identity(package, 'package_id', 'package')
            if arm is not None and arm not in ('arm_a', 'arm_b'):
                raise ValueError('unknown package arm')
            eligible = answer(package, 'eligible', 'package')
            group = _text(package.get('root_cause_group'), 'root cause group')
            if eligible is True:
                required(group, 'eligible package root cause group')
            elif eligible is False and group is not None:
                raise ValueError('excluded package has root cause group')
            if arm is None or package_id is None:
                continue
            key = (arm, package_id)
            if key in package_map:
                raise ValueError('duplicate arm-scoped package identity')
            package_map[key] = package
        inventory = {(arm, package_id) for arm in ('arm_a', 'arm_b')
                     for package_id in m.get(arm, {}).get('package_inventory', [])}
        if set(package_map) - inventory:
            raise ValueError('assessment names an unknown package')
        if inventory - set(package_map):
            missing.append('inventory has unassessed packages')
        groups = {arm: {record['root_cause_group'] for (record_arm, _), record in package_map.items()
                        if record_arm == arm and record.get('eligible') is True
                        and record.get('root_cause_group') is not None}
                  for arm in ('arm_a', 'arm_b')}
        derived = {'both_arms': len(groups['arm_a'] & groups['arm_b']),
                   'arm_a_only': len(groups['arm_a'] - groups['arm_b']),
                   'arm_b_only': len(groups['arm_b'] - groups['arm_a'])}
        mapping_complete = all(type(record.get('eligible')) is bool and
                               (not record['eligible'] or record.get('root_cause_group') is not None)
                               for record in package_map.values())
        if mapping_complete and not (inventory - set(package_map)):
            for field, value in derived.items():
                if overlap.get(field) is not None and overlap[field] != value:
                    raise ValueError('M6 overlap contradicts package root cause mapping')

    waste_bytes = reference(w.get('waste_ref'), 'waste') if assertion is not None or w.get('waste_ref') is not None else None
    if waste_bytes is not None:
        record = _object(_load_json(waste_bytes), 'waste evidence')
        version(record, 'waste evidence'); binding(record, 'waste evidence')
        evidence_assertion = identity(record, 'assertion', 'waste evidence')
        if assertion is not None and evidence_assertion is not None and assertion != evidence_assertion:
            raise ValueError('waste assertion mismatch')
        refs = record.get('source_refs')
        if refs is None:
            missing.append('waste source references are missing')
            refs = []
        if not isinstance(refs, list):
            raise ValueError('waste source references must be an array')
        if not refs:
            missing.append('waste source references are empty')
        for ref in refs:
            reference(ref, 'waste source')

    def references_unchanged():
        if any(data != _stable_regular_bytes(path) for path, data in references):
            raise ValueError('adjudication reference bytes changed')

    def result():
        if missing:
            # Preserve the old adverse integrity blockers alongside admission explanations.
            _, _, adverse = _decide_frozen({'arm_a': {'M1_findings': []},
                                            'arm_b': {'M1_findings': []}}, w, threshold)
            return 'inconclusive', ['Q02 input eligibility is unestablished'], list(dict.fromkeys(missing + adverse))
        admitted = {arm: {**m[arm], 'M1_findings': sorted(package_id
                    for (record_arm, package_id), record in package_map.items()
                    if record_arm == arm and record['eligible'])} for arm in ('arm_a', 'arm_b')}
        return _decide_frozen(admitted, w, threshold)

    # Even incomplete metadata cannot hide changed bytes or unsupported claimed packages.
    if source_root is not None:
        try:
            Path(source_root).stat()
        except FileNotFoundError:
            missing.append('declared source root is unavailable')
        else:
            with _bound_sources(source_root) as (trees, source_recheck):
                actual = _source_commitment(Path(source_root).absolute(), trees)
                if source_hash is not None and actual['sha256'] != source_hash:
                    raise ValueError('current source bytes do not match measurement')
                for arm, tree in zip(('arm_a', 'arm_b'), trees):
                    current = _measure_arm_snapshot(tree, m.get(arm, {}).get('path'))
                    for field, value in current.items():
                        if field != 'path' and field in m.get(arm, {}) and m[arm][field] != value:
                            raise ValueError('measurement disagrees with source inventory/cost')
                    for (record_arm, package_id), record in package_map.items():
                        if record_arm != arm or record.get('eligible') is not True:
                            continue
                        prefix = 'findings/' + package_id + '/'
                        data = tree.get(prefix + 'finding.json')
                        if data is None or any(path.startswith(prefix + 'revisions/') for path in tree):
                            missing.append('eligible package has unsupported legacy layout')
                            continue
                        finding = _load_json(data)
                        if (not isinstance(finding, dict) or finding.get('schema_version') not in (None, 2)
                                or validate_record(finding, 'finding-v2-legacy')):
                            missing.append('eligible package does not match the supported legacy schema')
                        elif finding.get('id') != package_id:
                            raise ValueError('legacy finding identity does not match package ID')
                        elif finding.get('confidence') != 'confirmed' or not all(
                            finding['oracle_verdict'][field] for field in
                            ('signal', 'adjudication', 'contamination_ruled_out')) or finding['status'] == 'withdrawn':
                            missing.append('eligible legacy finding lacks the declared confirmation state')

                def recheck():
                    source_recheck(); references_unchanged()

                yield result(), recheck
                return
    yield result(), references_unchanged


def decide(m, w, threshold, *, measurement_bytes=None, reference_base=None):
    """Public helper uses the same admission as verdict; unbound dictionaries cannot be decisive."""
    with _admitted_decision(m, w, threshold, measurement_bytes=measurement_bytes,
                            reference_base=reference_base) as (result, recheck):
        recheck()
        return result


def cmd_verdict(args):
    sources = tuple(Path(path).absolute() for path in (args.measurements, args.worksheet, args.prereg))
    try:
        if any(quarantined_ancestor(path) for path in sources):
            raise ValueError("ablation evidence is quarantined")
        original = tuple(_stable_regular_bytes(path) for path in sources)
        if any(quarantined_ancestor(path) for path in sources):
            raise ValueError("ablation evidence became quarantined")
        measurement_bytes, worksheet_bytes, prereg_bytes = original
        threshold, doc = _threshold_from_bytes(prereg_bytes)
        m, w = (_load_json(data) for data in (measurement_bytes, worksheet_bytes))
        with _admitted_decision(m, w, threshold, measurement_bytes=measurement_bytes,
                                reference_base=sources[1].parent) as (result, recheck):
            verdict, reasons, blockers = result
            lines = [f"portable checkpoint: {doc['checkpoint_id']}", f"VERDICT: {verdict}\n"]
            lines.extend("  - " + reason for reason in reasons)
            if blockers:
                lines.append("\nblocked by:")
                lines.extend("  ! " + blocker for blocker in blockers)
            lines.append("\nlicenses: " + _license_text_for_verdict(doc, verdict))
            recheck()
            if any(quarantined_ancestor(path) for path in sources):
                raise ValueError("ablation evidence became quarantined")
            if original != tuple(_stable_regular_bytes(path) for path in sources):
                raise ValueError("ablation input bytes changed before publication")
            print("\n".join(lines))
        return 0
    except (RecordError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise SystemExit("cannot read ablation evidence: malformed, mismatched, quarantined, or unsafe input") from error


# ---------------------------------------------------------------- self-test

def _m(a, b, sa=None, sb=None):
    return {"arm_a": {"M1_findings": ["f"] * a, "M5_subagents": sa},
            "arm_b": {"M1_findings": ["f"] * b, "M5_subagents": sb}}


def _w(**kw):
    w = json.loads(json.dumps(WORKSHEET))
    w["blinding_held"] = True
    w["run_record"] = {"ran_concurrently": True, "cross_arm_read_occurred": False,
                       "limit_truncated_an_arm": False}
    w["M6_overlap"] = {"both_arms": 0, "arm_a_only": 0, "arm_b_only": 0}
    w.update(kw)
    return w


def self_test():
    ok = True
    th, prereg = read_threshold()

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  -> {detail}" if not cond else ""))

    print(f"[self-test] threshold is read from the frozen portable checkpoint (got {th})")
    check("threshold is 2", th == 2)

    print("[self-test] malformed or non-portable checkpoints fail closed")

    def rejected(name, mutate):
        candidate = json.loads(json.dumps(prereg))
        mutate(candidate)
        try:
            _threshold_from_bytes(json.dumps(candidate).encode("utf-8"))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            check(name, True)
        else:
            check(name, False, "checkpoint was accepted")

    def rejected_bytes(name, data):
        try:
            _threshold_from_bytes(data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            check(name, True)
        else:
            check(name, False, "checkpoint was accepted")

    rejected_bytes("malformed JSON is rejected", b"{")
    rejected_bytes(
        "duplicate JSON keys are rejected",
        b'{"schema_version":1,"schema_version":1}',
    )
    rejected("unknown fields are rejected", lambda doc: doc.update({"target": "hidden"}))
    rejected(
        "malformed source pins are rejected",
        lambda doc: doc["source_pins"].update({"complete_outcome_sha256": "not-a-hash"}),
    )
    rejected(
        "different well-formed source pins are rejected",
        lambda doc: doc["source_pins"].update(
            {
                "complete_preregistration_sha256": "a" * 64,
                "complete_outcome_sha256": "b" * 64,
            }
        ),
    )
    rejected(
        "one pin cannot stand for both source records",
        lambda doc: doc["source_pins"].update(
            {
                "complete_outcome_sha256": doc["source_pins"][
                    "complete_preregistration_sha256"
                ]
            }
        ),
    )
    rejected(
        "historical provenance cannot be strengthened",
        lambda doc: doc["source_pins"].update({"historical_provenance": "git_proven"}),
    )
    rejected(
        "inconsistent threshold fields are rejected",
        lambda doc: doc["decision_rule"].update({"threshold_expression": "M1(A) - M1(B) >= 3"}),
    )
    rejected(
        "coordinated threshold changes are rejected",
        lambda doc: doc["decision_rule"].update(
            {"m1_gap_threshold": 3, "threshold_expression": "M1(A) - M1(B) >= 3"}
        ),
    )
    rejected(
        "non-portable content claims are rejected",
        lambda doc: doc["portable_boundary"].update({"outcome_content_included": True}),
    )
    rejected(
        "candidate-promotion licenses are rejected",
        lambda doc: doc["decision_rule"]["maximum_license_if_decisive"].update(
            {"candidate_promotion": True}
        ),
    )
    rejected(
        "missing licensing text is rejected",
        lambda doc: doc["decision_rule"].pop("maximum_license_text_if_decisive"),
    )
    rejected(
        "target-specific licensing text is rejected",
        lambda doc: doc["decision_rule"].update(
            {
                "maximum_license_text_if_decisive": doc["decision_rule"][
                    "maximum_license_text_if_decisive"
                ]
                + " Hidden engagement mechanism: engagements/private/secret-workflow."
            }
        ),
    )
    rejected(
        "contradictory promotion wording is rejected",
        lambda doc: doc["decision_rule"].update(
            {
                "maximum_license_text_if_decisive": doc["decision_rule"][
                    "maximum_license_text_if_decisive"
                ]
                + " Candidate promotion and vendor filing are licensed."
            }
        ),
    )

    print("[self-test] the three preregistered outcomes")
    v, _, _ = _decide_frozen(_m(5, 2), _w(), th)
    check("gap >= 2 earns its keep", v == "prompt_earns_its_keep", v)
    v, _, _ = _decide_frozen(_m(0, 0), _w(), th)
    check("both zero is inconclusive", v == "inconclusive", v)
    check(
        "an inconclusive verdict licenses no prompt conclusion",
        "no prompt conclusion" in _license_text_for_verdict(prereg, v).casefold(),
    )
    v, _, _ = _decide_frozen(_m(2, 4), _w(), th)
    check("arm B ahead does not earn its keep", v == "prompt_does_not_earn_its_keep", v)

    print("[self-test] a gap of one is NOT a result")
    v, _, _ = _decide_frozen(_m(3, 2, sa=60, sb=12), _w(), th)
    check("gap 1 + A costs more -> does not earn its keep", v == "prompt_does_not_earn_its_keep", v)
    v, _, _ = _decide_frozen(_m(3, 2), _w(), th)
    check("gap 1 + no cost data -> inconclusive, never a win", v == "inconclusive", v)

    print("[self-test] the waste clause")
    v, _, _ = _decide_frozen(_m(1, 1), _w(M7_waste={"waste_class_a_avoided_that_b_hit": "misattribution"}), th)
    check("a documented waste class A avoided earns its keep", v == "prompt_earns_its_keep", v)

    print("[self-test] guards refuse a verdict rather than issuing a wrong one")
    v, _, bl = _decide_frozen(_m(9, 0), _w(blinding_held=False), th)
    check("blinding failure blocks even a landslide", v == "inconclusive" and bl, v)
    w = _w(); w["run_record"]["limit_truncated_an_arm"] = True
    v, _, bl = _decide_frozen(_m(9, 0), w, th)
    check("a truncated arm blocks", v == "inconclusive" and bl, v)
    w = _w(); w["run_record"]["cross_arm_read_occurred"] = True
    v, _, bl = _decide_frozen(_m(9, 0), w, th)
    check("a cross-arm read blocks", v == "inconclusive" and bl, v)
    w = _w(); w["M6_overlap"]["arm_b_only"] = None
    v, _, bl = _decide_frozen(_m(9, 0), w, th)
    check("an unfilled judged metric blocks (never guessed)", v == "inconclusive" and bl, v)

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("measure")
    m.add_argument("--engagement", required=True)
    m.add_argument("--case-id"); m.add_argument("--run-id")
    m.add_argument("--worksheet"); m.add_argument("--force", action="store_true")
    m.set_defaults(fn=cmd_measure)
    v = sub.add_parser("verdict")
    v.add_argument("--measurements", required=True); v.add_argument("--worksheet", required=True)
    v.add_argument("--prereg", default=PREREG); v.set_defaults(fn=cmd_verdict)
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not getattr(args, "fn", None):
        ap.print_help(); return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
