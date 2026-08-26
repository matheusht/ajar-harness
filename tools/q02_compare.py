#!/usr/bin/env python3
"""Q-02 prompt-ablation adjudicator (Phase 5).

Roadmap Q-02: does the hand-authored per-target goal prompt earn what it costs? One target, two
arms, one variable. This computes the comparison from two arm directories and applies the
PREREGISTERED decision rule.

The design rule here is the one this repository keeps re-learning: **do not let a tool assert what
it cannot compute.**

  computable from the ledgers   M1 findings, M2 candidates, M5 cost
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
from contextlib import ExitStack
import glob
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
    is_quarantined,
    quarantined_ancestor,
    read_safe_offline_file,
    require_safe_offline_output,
)
from engagement_records import RecordError
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


def count_packages(arm, sub):
    d = os.path.join(arm, sub)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.basename(p.rstrip("/"))
        for p in glob.glob(os.path.join(d, "*/"))
    )


def jsonl_rows(path):
    if not os.path.isfile(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def severity_profile(arm):
    prof = {}
    for pkg in glob.glob(os.path.join(arm, "findings", "*/")):
        fj = os.path.join(pkg, "finding.json")
        if not os.path.isfile(fj):
            continue
        try:
            band = (json.load(open(fj)).get("severity") or {})
            band = band.get("band") if isinstance(band, dict) else band
        except Exception:
            band = None
        prof[band or "unstated"] = prof.get(band or "unstated", 0) + 1
    return prof


def subagent_spend(arm):
    """Read the per-round spend the brief required in progress.md. Absent is reported, not zeroed."""
    p = os.path.join(arm, "progress.md")
    if not os.path.isfile(p):
        return None
    nums = [int(n) for n in re.findall(r"(?:subagents?|agents?)[^0-9\n]{0,20}(\d{1,3})",
                                       open(p).read(), re.I)]
    return sum(nums) if nums else None


def measure_arm(arm):
    return {
        "path": os.path.relpath(arm, ROOT),
        "M1_findings": count_packages(arm, "findings"),
        "M2_candidates": count_packages(arm, "unproven"),
        "M3_severity": severity_profile(arm),
        "M5_attempts": len(jsonl_rows(os.path.join(arm, "attempts.jsonl"))),
        "M5_events": len(jsonl_rows(os.path.join(arm, "events.jsonl"))),
        "M5_subagents": subagent_spend(arm),
    }


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
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
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
    return len([json.loads(line) for line in data.splitlines() if line.strip()])


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
        "M1_findings": package_ids("findings"),
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


def cmd_measure(args):
    if args.worksheet:
        try:
            require_safe_offline_output(Path(args.worksheet))
        except ValueError:
            raise SystemExit("worksheet destination is quarantined or reserved")
    engagement_path = Path(args.engagement).absolute()
    root_fd = -1
    arm_fds = []
    try:
        root_fd = os.open(
            engagement_path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        root_identity = os.fstat(root_fd)
        with bound_engagement_lock(root_fd, create=False) as bound_engagement:
            for arm_name in ("arm-a", "arm-b"):
                try:
                    arm_fds.append(
                        os.open(
                            arm_name,
                            os.O_RDONLY
                            | getattr(os, "O_DIRECTORY", 0)
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=root_fd,
                        )
                    )
                except OSError as error:
                    raise SystemExit("missing ablation arm directory") from error
            with ExitStack() as locks:
                bound_arms = [
                    locks.enter_context(bound_engagement_lock(fd, create=False)) for fd in arm_fds
                ]
                trees = [_snapshot_bound_tree(fd) for fd in arm_fds]
                require_not_quarantined(bound_engagement)
                for bound_arm in bound_arms:
                    require_not_quarantined(bound_arm)
                try:
                    current_root = os.stat(engagement_path, follow_symlinks=False)
                except OSError as error:
                    raise SystemExit("ablation evidence changed during measurement") from error
                if (
                    stat.S_ISLNK(current_root.st_mode)
                    or (current_root.st_dev, current_root.st_ino)
                    != (root_identity.st_dev, root_identity.st_ino)
                ):
                    raise SystemExit("ablation evidence changed during measurement")
                out = {
                    "engagement": os.path.relpath(args.engagement, ROOT),
                    "arm_a": _measure_arm_snapshot(
                        trees[0], os.path.relpath(os.path.join(args.engagement, "arm-a"), ROOT)
                    ),
                    "arm_b": _measure_arm_snapshot(
                        trees[1], os.path.relpath(os.path.join(args.engagement, "arm-b"), ROOT)
                    ),
                    "computed_only": "M6 and M7 are judged, not computed. Fill the worksheet.",
                }
                # Admission and every publication share the source locks. A signed quarantine
                # marker that wins before this point is excluded; one waiting on these locks is
                # ordered after the measurement has been emitted.
                require_not_quarantined(bound_engagement)
                for bound_arm in bound_arms:
                    require_not_quarantined(bound_arm)
                try:
                    final_root = os.stat(engagement_path, follow_symlinks=False)
                except OSError as error:
                    raise SystemExit("ablation evidence changed during measurement") from error
                if (
                    stat.S_ISLNK(final_root.st_mode)
                    or (final_root.st_dev, final_root.st_ino)
                    != (root_identity.st_dev, root_identity.st_ino)
                ):
                    raise SystemExit("ablation evidence changed during measurement")
                if args.worksheet:
                    try:
                        require_safe_offline_output(Path(args.worksheet))
                    except ValueError:
                        raise SystemExit("worksheet destination is quarantined or reserved")
                    if os.path.exists(args.worksheet) and not args.force:
                        raise SystemExit(f"{args.worksheet} exists; pass --force to overwrite")
                    atomic_write_offline(
                        Path(args.worksheet),
                        (json.dumps(WORKSHEET, indent=2) + "\n").encode("utf-8"),
                    )
                print(json.dumps(out, indent=2, sort_keys=True))
                if args.worksheet:
                    sys.stderr.write(f"\nworksheet written to {args.worksheet}\n")
                return 0
    except RecordError as error:
        if error.code in {"engagement_quarantined", "engagement_coordination_unavailable"}:
            raise SystemExit("ablation evidence is quarantined or uncoordinated") from error
        raise
    except OSError as error:
        raise SystemExit("ablation evidence is unavailable or unsafe") from error
    finally:
        for fd in arm_fds:
            os.close(fd)
        if root_fd >= 0:
            os.close(root_fd)


def decide(m, w, threshold):
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


def cmd_verdict(args):
    sources = tuple(Path(path) for path in (args.measurements, args.worksheet, args.prereg))
    if any(quarantined_ancestor(path) for path in sources):
        raise SystemExit("ablation evidence is quarantined")
    try:
        measurement_bytes, worksheet_bytes, prereg_bytes = (
            _stable_regular_bytes(path) for path in sources
        )
        threshold, doc = _threshold_from_bytes(prereg_bytes)
        m = json.loads(measurement_bytes)
        w = json.loads(worksheet_bytes)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise SystemExit("cannot read ablation evidence")
    if any(quarantined_ancestor(path) for path in sources):
        raise SystemExit("ablation evidence became quarantined during adjudication")
    verdict, reasons, blockers = decide(m, w, threshold)
    if any(quarantined_ancestor(path) for path in sources):
        raise SystemExit("ablation evidence became quarantined during adjudication")
    print(f"portable checkpoint: {doc['checkpoint_id']}")
    print(f"VERDICT: {verdict}\n")
    for r in reasons:
        print("  -", r)
    if blockers:
        print("\nblocked by:")
        for b in blockers:
            print("  !", b)
    print("\nlicenses: " + _license_text_for_verdict(doc, verdict))
    return 0


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
    v, _, _ = decide(_m(5, 2), _w(), th)
    check("gap >= 2 earns its keep", v == "prompt_earns_its_keep", v)
    v, _, _ = decide(_m(0, 0), _w(), th)
    check("both zero is inconclusive", v == "inconclusive", v)
    check(
        "an inconclusive verdict licenses no prompt conclusion",
        "no prompt conclusion" in _license_text_for_verdict(prereg, v).casefold(),
    )
    v, _, _ = decide(_m(2, 4), _w(), th)
    check("arm B ahead does not earn its keep", v == "prompt_does_not_earn_its_keep", v)

    print("[self-test] a gap of one is NOT a result")
    v, _, _ = decide(_m(3, 2, sa=60, sb=12), _w(), th)
    check("gap 1 + A costs more -> does not earn its keep", v == "prompt_does_not_earn_its_keep", v)
    v, _, _ = decide(_m(3, 2), _w(), th)
    check("gap 1 + no cost data -> inconclusive, never a win", v == "inconclusive", v)

    print("[self-test] the waste clause")
    v, _, _ = decide(_m(1, 1), _w(M7_waste={"waste_class_a_avoided_that_b_hit": "misattribution"}), th)
    check("a documented waste class A avoided earns its keep", v == "prompt_earns_its_keep", v)

    print("[self-test] guards refuse a verdict rather than issuing a wrong one")
    v, _, bl = decide(_m(9, 0), _w(blinding_held=False), th)
    check("blinding failure blocks even a landslide", v == "inconclusive" and bl, v)
    w = _w(); w["run_record"]["limit_truncated_an_arm"] = True
    v, _, bl = decide(_m(9, 0), w, th)
    check("a truncated arm blocks", v == "inconclusive" and bl, v)
    w = _w(); w["run_record"]["cross_arm_read_occurred"] = True
    v, _, bl = decide(_m(9, 0), w, th)
    check("a cross-arm read blocks", v == "inconclusive" and bl, v)
    w = _w(); w["M6_overlap"]["arm_b_only"] = None
    v, _, bl = decide(_m(9, 0), w, th)
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
