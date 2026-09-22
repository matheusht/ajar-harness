#!/usr/bin/env python3
"""Compile one deterministic, current-only hunter cognitive projection."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from engagement_records import canonical_json_bytes, sha256_bytes
from engagement_state import read_governed_file, read_ledger


VIEW_VERSION = "hunter-current-v1"
COMPILER_VERSION = 1
DEFAULT_BYTE_BUDGET = 512 * 1024
EXCLUDED_CLASSES = (
    "engagement-ledgers", "findings", "reviews", "reports", "submissions", "cleanup",
    "portable-memory", "casebooks", "evaluation-gold", "other-hypotheses",
    "unselected-methodology", "peer-or-task-notice-feed", "git-metadata", "environment-secrets",
)
REQUIRED_HYPOTHESIS_FIELDS = (
    "status", "statement", "suspected_invariant", "trust_boundary", "attacker_path",
    "impact_ceiling", "bounded_space", "lens_ids", "card_ids",
    "expected_confirming_evidence", "decisive_falsifiers", "constraints",
    "next_experiment", "completion_criteria", "running_event_ref",
)
EXPOSED_HYPOTHESIS_FIELDS = REQUIRED_HYPOTHESIS_FIELDS + (
    "supporting_evidence_refs", "conflicting_evidence_refs", "unresolved_questions", "next_route",
)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class HunterViewError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _front_matter(data: bytes) -> tuple[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HunterViewError("hunter_view_methodology_invalid") from exc
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise HunterViewError("hunter_view_methodology_invalid")
    header = text[4:text.index("\n---\n", 4)]
    identifier = re.search(r"(?m)^id:\s*([^#\n]+?)\s*$", header)
    kind = re.search(r"(?m)^type:\s*(vuln|technique|oracle)\s*$", header)
    if identifier is None or kind is None:
        raise HunterViewError("hunter_view_methodology_invalid")
    return identifier.group(1).strip(), kind.group(1)


def _read_relative_regular(root: Path, relative: Path, *, max_bytes: int, one_link: bool) -> bytes:
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise HunterViewError("hunter_view_input_invalid")
    directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        for part in relative.parts[:-1]:
            child_fd = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            os.close(directory_fd); directory_fd = child_fd
        file_fd = os.open(relative.parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode) or (one_link and before.st_nlink != 1) or before.st_size > max_bytes:
                raise HunterViewError("hunter_view_input_type")
            chunks: list[bytes] = []; remaining = max_bytes + 1
            while remaining:
                chunk = os.read(file_fd, min(64 * 1024, remaining))
                if not chunk: break
                chunks.append(chunk); remaining -= len(chunk)
            after = os.fstat(file_fd)
            data = b"".join(chunks)
            if len(data) > max_bytes or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise HunterViewError("hunter_view_input_changed")
            return data
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise HunterViewError("hunter_view_input_invalid") from exc
    finally:
        os.close(directory_fd)


def _valid_safe_signal(header: str) -> bool:
    match = re.search(r"(?ms)^safe_signal:\s*(?:#.*)?\n(?P<body>(?:^[ \t]+.*\n?)+)", header)
    if match is None:
        return False
    values = {key: value.strip().strip('"\'') for key, value in re.findall(r"(?m)^\s+(proxy|never):\s*(.+?)\s*$", match.group("body"))}
    return set(values) == {"proxy", "never"} and all(values.values())


def _methodology_cards(root: Path, selected: Sequence[str]) -> list[dict[str, Any]]:
    if not root.is_absolute() or not root.is_dir() or any(not isinstance(value, str) or not _ID.fullmatch(value) for value in selected):
        raise HunterViewError("hunter_view_methodology_invalid")
    found: dict[str, tuple[str, bytes]] = {}
    for card_id in selected:
        suffix = card_id.split(".", 1)[-1]
        slugs = dict.fromkeys((card_id, card_id.replace(".", "-"), suffix))
        candidates = [
            *(Path("vulns") / slug / "SKILL.md" for slug in slugs),
            *(Path("techniques") / slug / "SKILL.md" for slug in slugs),
            Path("oracles") / f"{card_id}.md",
            Path("oracles") / f"{card_id.removeprefix('oracles.')}.md",
            Path("oracles") / card_id / "SKILL.md",
        ]
        matches: list[tuple[str, bytes]] = []
        for relative in dict.fromkeys(candidates):
            try:
                data = _read_relative_regular(root, relative, max_bytes=DEFAULT_BYTE_BUDGET, one_link=False)
            except HunterViewError:
                continue
            identifier, kind = _front_matter(data)
            if card_id in {identifier, identifier.removeprefix("oracles.")}:
                matches.append((kind, data))
        if len(matches) != 1:
            raise HunterViewError("hunter_view_methodology_missing" if not matches else "hunter_view_methodology_ambiguous")
        kind, data = matches[0]
        header = data.decode("utf-8").split("\n---\n", 1)[0][4:]
        if kind == "vuln" and not _valid_safe_signal(header):
            raise HunterViewError("hunter_view_safe_signal_missing")
        found[card_id] = (kind, data)
    kinds = {kind for kind, _ in found.values()}
    if "vuln" not in kinds or "oracle" not in kinds:
        raise HunterViewError("hunter_view_methodology_missing")
    return [
        {"id": card_id, "type": found[card_id][0], "bytes": found[card_id][1], "digest": sha256_bytes(found[card_id][1])}
        for card_id in selected
    ]


def _regular_target_input(workspace: Path, supplied: Path) -> tuple[str, bytes]:
    if not supplied.is_absolute():
        raise HunterViewError("hunter_view_target_input_invalid")
    absolute = Path(os.path.abspath(supplied))
    try:
        relative = absolute.relative_to(workspace)
    except ValueError as exc:
        raise HunterViewError("hunter_view_target_input_invalid") from exc
    if not relative.parts or any(part in {".git", "engagements"} for part in relative.parts):
        raise HunterViewError("hunter_view_target_input_forbidden")
    try:
        data = _read_relative_regular(workspace, relative, max_bytes=DEFAULT_BYTE_BUDGET, one_link=True)
    except HunterViewError as exc:
        raise HunterViewError("hunter_view_target_input_invalid") from exc
    return relative.as_posix(), data


def _stable_action(item: dict[str, Any]) -> dict[str, Any]:
    action = item.get("next_action")
    if not isinstance(action, dict) or action.get("principal") != "hunter":
        raise HunterViewError("hunter_view_action_invalid")
    return {
        "action_id": action.get("action_id"), "command": action.get("command"),
        "principal": action.get("principal"), "session_kind": action.get("session_kind"),
        "admission": copy.deepcopy(action.get("admission")),
    }


def _hunter_hypothesis_id(state: dict[str, Any], item: dict[str, Any]) -> str | None:
    entity = item.get("entity")
    entity_id = entity.get("id") if isinstance(entity, dict) else None
    if item.get("class") == "hypothesis_running_unattempted":
        return entity_id
    if item.get("class") == "review_obligation_open":
        row = next((row for row in state.get("outstanding_reviews", []) if row.get("review_ref") == entity_id), None)
        return row.get("hypothesis_ref") if isinstance(row, dict) else None
    if item.get("class") == "control_candidate_unverified":
        row = next((row for row in state.get("control_candidates", []) if row.get("routing_event_id") == entity_id), None)
        return row.get("hypothesis_ref") if isinstance(row, dict) else None
    return None


def _admitted_value(action: dict[str, Any], path: list[str], default: Any) -> Any:
    constraints = action.get("admission", {}).get("constraints", [])
    match = next((row for row in constraints if row.get("document") == "proposal" and row.get("path") == path and row.get("operator") in {"equals", "set_equals", "nonempty_subset_of", "one_of"}), None)
    if not isinstance(match, dict):
        return copy.deepcopy(default)
    value = copy.deepcopy(match.get("value"))
    if match.get("operator") == "nonempty_subset_of":
        return value[:1] if isinstance(value, list) else default
    if match.get("operator") == "one_of":
        return value[0] if isinstance(value, list) and value else default
    return value


def _attempt_template(*, state: dict[str, Any], action: dict[str, Any], hypothesis_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "attempt_id": "attempt-REPLACE-WITH-UNIQUE-ID",
        "engagement_id": state.get("engagement_id"),
        "recorded_at": "REPLACE-WITH-CURRENT-RFC3339-TIMESTAMP",
        "actor": {"role": "broker", "id": "broker-placeholder"},
        "operation_class": "notebook",
        "provenance": {"actor": {"role": "broker", "id": "broker-placeholder"}, "session_id": "session-placeholder", "runtime_session_ref": None, "model": None, "provider": None, "prompt_version": None, "card_versions": [], "tool_versions": []},
        "scope_hash": state.get("scope_hash"),
        "environment_ref": state.get("active_environment_ref"),
        "escalation_confirmation_event_ref": None,
        "hypothesis_ref": _admitted_value(action, ["hypothesis_ref"], hypothesis_id),
        "experiment_ref": _admitted_value(action, ["experiment_ref"], None),
        "surface": "REPLACE-WITH-EXACT-TESTED-SURFACE",
        "action_summary": "REPLACE-WITH-BOUNDED-ACTION",
        "redaction_attestation": True,
        "observation": {"source": "source_inspection", "statement": "REPLACE-WITH-TRUTHFUL-OBSERVATION"},
        "evidence_refs": _admitted_value(action, ["evidence_refs"], []),
        "kind": _admitted_value(action, ["kind"], "primary"),
        "control_of": _admitted_value(action, ["control_of"], []),
        "assessment": "inconclusive",
        "contamination": {"status": "none_observed", "sources": [], "note": "Current-only compiled view; report any observed contamination instead."},
        "cost": {"wall_seconds": 0, "model_seconds": 0, "tool_seconds": 0, "target_calls": 0, "model_calls": 1, "input_tokens": None, "output_tokens": None, "cost_usd": None, "human_review_seconds": 0},
    }


def _evidence_inputs(engagement: Path, state: dict[str, Any], hypothesis: dict[str, Any]) -> list[tuple[dict[str, Any], bytes]]:
    selected = set(hypothesis.get("supporting_evidence_refs", [])) | set(hypothesis.get("conflicting_evidence_refs", []))
    if not selected:
        return []
    artifacts = {record["artifact_id"]: record for record in read_ledger(engagement, "artifact") if record.get("artifact_id") in selected}
    rows: list[tuple[dict[str, Any], bytes]] = []
    for reference in sorted(artifacts):
        artifact = artifacts[reference]
        if (
            artifact.get("environment_ref") != state.get("active_environment_ref")
            or artifact.get("advisory_zone") != "clear_local"
            or artifact.get("redaction_status") not in {"not_needed", "redacted"}
            or artifact.get("contains_executable_capability") is not False
            or artifact.get("sensitivity") == "restricted"
        ):
            raise HunterViewError("hunter_view_evidence_not_exposable")
        relative = Path(str(artifact.get("relative_path")))
        if not relative.parts or relative.parts[0] != "evidence":
            raise HunterViewError("hunter_view_evidence_invalid")
        try:
            data = read_governed_file(engagement / relative)
        except OSError as exc:
            raise HunterViewError("hunter_view_evidence_invalid") from exc
        if len(data) != artifact.get("size") or sha256_bytes(data) != artifact.get("sha256"):
            raise HunterViewError("hunter_view_evidence_changed")
        rows.append(({
            "slot": f"evidence-{len(rows):03d}", "reference": reference,
            "reason": "explicit_current_hypothesis_evidence", "digest": artifact["sha256"],
            "size": artifact["size"], "media_type": artifact["media_type"],
        }, data))
    return rows


@dataclass
class HunterView:
    projection: Path
    runtime: Path
    view_digest: str
    input_corpus_digest: str
    manifest: dict[str, Any]
    _lifetime_fd: int
    _watchdog: subprocess.Popen[bytes]
    _root: Path

    def close(self) -> None:
        if self._lifetime_fd >= 0:
            os.close(self._lifetime_fd)
            self._lifetime_fd = -1
        try:
            self._watchdog.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._watchdog.kill(); self._watchdog.wait(timeout=2)
            raise HunterViewError("hunter_view_cleanup_failed")
        if self._watchdog.returncode != 0 or self._root.exists():
            raise HunterViewError("hunter_view_cleanup_failed")

    def __enter__(self) -> "HunterView":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def assert_current(self, *, workspace: Path, engagement: Path, state: dict[str, Any], item: dict[str, Any], methodology_root: Path, schema_root: Path | None = None) -> None:
        hypothesis_id = self.manifest["hypothesis_id"]
        current_hypothesis = state.get("hypotheses", {}).get(hypothesis_id)
        current_view = {field: copy.deepcopy(current_hypothesis.get(field)) for field in EXPOSED_HYPOTHESIS_FIELDS} if isinstance(current_hypothesis, dict) else None
        if _stable_action(item) != self.manifest["action"] or current_view != self.manifest["hypothesis"] or state.get("scope_hash") != self.manifest["scope_digest"]:
            raise HunterViewError("hunter_view_stale")
        current_cards = _methodology_cards(methodology_root.resolve(strict=True), [row["id"] for row in self.manifest["methodology"]])
        if [card["digest"] for card in current_cards] != [row["digest"] for row in self.manifest["methodology"]]:
            raise HunterViewError("hunter_view_stale")
        current_inputs = [_regular_target_input(workspace, workspace / row["target_relative_path"]) for row in self.manifest["target_inputs"]]
        if [sha256_bytes(data) for _path, data in current_inputs] != [row["digest"] for row in self.manifest["target_inputs"]]:
            raise HunterViewError("hunter_view_stale")
        try:
            current_evidence = _evidence_inputs(engagement, state, current_view)
        except HunterViewError as exc:
            raise HunterViewError("hunter_view_stale") from exc
        if [metadata for metadata, _data in current_evidence] != self.manifest["evidence_inputs"]:
            raise HunterViewError("hunter_view_stale")
        schemas = Path(__file__).resolve().parents[1] / "schemas" if schema_root is None else schema_root.resolve(strict=True)
        current_template = _attempt_template(state=state, action=self.manifest["action"], hypothesis_id=hypothesis_id)
        current_contract = {
            "proposal_template_digest": sha256_bytes(canonical_json_bytes(current_template)),
            "attempt_schema_digest": sha256_bytes(_read_relative_regular(schemas, Path("attempt-v2.schema.json"), max_bytes=DEFAULT_BYTE_BUDGET, one_link=False)),
            "common_schema_digest": sha256_bytes(_read_relative_regular(schemas, Path("research-common.schema.json"), max_bytes=DEFAULT_BYTE_BUDGET, one_link=False)),
            "recorder_owned_fields": self.manifest["output_contract"]["recorder_owned_fields"],
        }
        if current_contract != self.manifest["output_contract"]:
            raise HunterViewError("hunter_view_stale")


def compile_hunter_view(*, workspace: Path, engagement: Path, state: dict[str, Any], item: dict[str, Any], target_inputs: Sequence[Path], methodology_root: Path, schema_root: Path | None = None, byte_budget: int = DEFAULT_BYTE_BUDGET) -> HunterView:
    workspace = Path(os.path.abspath(workspace))
    engagement = Path(os.path.abspath(engagement))
    if not workspace.is_dir() or engagement.parent.parent != workspace or type(byte_budget) is not int or not 1 <= byte_budget <= 8 * 1024 * 1024:
        raise HunterViewError("hunter_view_context_invalid")
    hypothesis_id = _hunter_hypothesis_id(state, item)
    hypothesis = state.get("hypotheses", {}).get(hypothesis_id)
    if not isinstance(hypothesis, dict) or hypothesis.get("status") != "running" or any(field not in hypothesis or hypothesis[field] is None for field in REQUIRED_HYPOTHESIS_FIELDS):
        raise HunterViewError("hunter_view_hypothesis_invalid")
    hypothesis_view = {field: copy.deepcopy(hypothesis.get(field)) for field in EXPOSED_HYPOTHESIS_FIELDS}
    action = _stable_action(item)
    cards = _methodology_cards(methodology_root.resolve(strict=True), hypothesis_view["card_ids"])
    scope_hash = state.get("scope_hash")
    scope_path = engagement / "scope-attestations" / f"{str(scope_hash).removeprefix('sha256:')}.md"
    try:
        scope_bytes = read_governed_file(scope_path)
    except OSError as exc:
        raise HunterViewError("hunter_view_scope_invalid") from exc
    if sha256_bytes(scope_bytes) != scope_hash:
        raise HunterViewError("hunter_view_scope_invalid")
    inputs = [_regular_target_input(workspace, Path(path)) for path in target_inputs]
    if not inputs:
        raise HunterViewError("hunter_view_target_inputs_missing")
    if len({path for path, _ in inputs}) != len(inputs):
        raise HunterViewError("hunter_view_target_input_duplicate")
    inputs.sort(key=lambda value: value[0])
    input_entries = [
        {"slot": f"input-{index:03d}", "target_relative_path": path, "reason": "explicitly_allowlisted_for_admitted_experiment", "digest": sha256_bytes(data), "size": len(data)}
        for index, (path, data) in enumerate(inputs)
    ]
    evidence = _evidence_inputs(engagement, state, hypothesis_view)
    evidence_entries = [metadata for metadata, _data in evidence]
    corpus_digest = sha256_bytes(canonical_json_bytes({"target_inputs": input_entries, "evidence_inputs": evidence_entries}))
    proposal_template = _attempt_template(state=state, action=action, hypothesis_id=hypothesis_id)
    schemas = Path(__file__).resolve().parents[1] / "schemas" if schema_root is None else schema_root.resolve(strict=True)
    attempt_schema = _read_relative_regular(schemas, Path("attempt-v2.schema.json"), max_bytes=DEFAULT_BYTE_BUDGET, one_link=False)
    common_schema = _read_relative_regular(schemas, Path("research-common.schema.json"), max_bytes=DEFAULT_BYTE_BUDGET, one_link=False)
    output_contract = {
        "proposal_template_digest": sha256_bytes(canonical_json_bytes(proposal_template)),
        "attempt_schema_digest": sha256_bytes(attempt_schema),
        "common_schema_digest": sha256_bytes(common_schema),
        "recorder_owned_fields": ["sequence", "previous_hash", "record_hash", "actor", "provenance.actor", "provenance.session_id", "provenance.runtime_session_ref", "provenance.model", "provenance.provider", "provenance.cognitive_principal", "provenance.view_type", "provenance.view_digest", "provenance.input_corpus_digest", "provenance.treatment"],
    }
    commitment = {
        "compiler_version": COMPILER_VERSION, "view_type": VIEW_VERSION, "principal": "hunter",
        "action": action, "hypothesis_id": hypothesis_id, "hypothesis": hypothesis_view,
        "scope_digest": scope_hash,
        "methodology": [{key: card[key] for key in ("id", "type", "digest")} for card in cards],
        "target_inputs": input_entries, "evidence_inputs": evidence_entries, "input_corpus_digest": corpus_digest,
        "exclusion_policy": list(EXCLUDED_CLASSES), "byte_budget": byte_budget,
        "output_contract": output_contract, "treatment": "compiled_current_only",
    }
    view_digest = sha256_bytes(canonical_json_bytes(commitment))
    manifest = {**commitment, "view_digest": view_digest}
    brief = {
        "schema_version": 1, "principal": "hunter", "view_digest": view_digest,
        "task": f"Execute exactly one bounded experiment and submit exactly one truthful {proposal_template['kind']} attempt through the authenticated broker.",
        "hypothesis": hypothesis_view, "action": action,
        "safety_constraints": {"signed_scope": "scope.md", "scope_digest": scope_hash, "impact_ceiling": hypothesis_view["impact_ceiling"], "constraints": hypothesis_view["constraints"]},
        "target_inputs": [{"slot": entry["slot"], "path": f"target-inputs/{entry['slot']}", "reason": entry["reason"], "digest": entry["digest"]} for entry in input_entries],
        "evidence_inputs": [{"reference": entry["reference"], "path": f"evidence/{entry['slot']}", "reason": entry["reason"], "digest": entry["digest"], "media_type": entry["media_type"]} for entry in evidence_entries],
        "unknowns": list(hypothesis_view.get("unresolved_questions", [])),
        "stop_conditions": ["one broker-accepted attempt is recorded", "the experiment reaches a scope or capability ceiling", "required evidence is unavailable"],
        "forbidden": list(EXCLUDED_CLASSES),
    }
    submit = b"Read brief.json and contracts/proposal-template.json. Replace every REPLACE value truthfully. Do not add sequence, previous_hash, or record_hash; the broker materializes them. Save the proposal in /scratch and invoke the exact container_action_transport argv from the session prompt. The broker overwrites recorder and cognitive provenance and accepts the action once.\n"
    files: list[tuple[str, bytes]] = [
        ("manifest.json", canonical_json_bytes(manifest)), ("brief.json", canonical_json_bytes(brief)), ("scope.md", scope_bytes),
        ("contracts/proposal-template.json", canonical_json_bytes(proposal_template)),
        ("contracts/attempt-v2.schema.json", attempt_schema), ("contracts/research-common.schema.json", common_schema),
        ("SUBMIT.md", submit),
    ]
    files.extend((f"methodology/{card['type']}/{card['id']}.md", card["bytes"]) for card in cards)
    files.extend((f"target-inputs/input-{index:03d}", data) for index, (_path, data) in enumerate(inputs))
    files.extend((f"evidence/{metadata['slot']}", data) for metadata, data in evidence)
    if sum(len(data) for _path, data in files) > byte_budget:
        raise HunterViewError("hunter_view_budget_exceeded")
    root = Path(tempfile.mkdtemp(prefix=f".hunter-view-{view_digest[7:19]}-", dir=workspace))
    projection = root / "view"
    runtime = root / "runtime"
    try:
        projection.mkdir()
        for relative, data in files:
            destination = projection / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data); os.chmod(destination, 0o444)
        for directory in sorted((path for path in projection.rglob("*") if path.is_dir()), reverse=True):
            os.chmod(directory, 0o555)
        runtime_tools = runtime / "tools"
        runtime_tools.mkdir(parents=True)
        for name in ("container_session_supervisor.py", "container_broker_client.py"):
            destination = runtime_tools / name
            shutil.copyfile(Path(__file__).with_name(name), destination)
            os.chmod(destination, 0o444)
        os.chmod(runtime_tools, 0o555); os.chmod(runtime, 0o555); os.chmod(projection, 0o555); os.chmod(root, 0o555)
        entry = root.stat(follow_symlinks=False)
        lifetime_read, lifetime_write = os.pipe(); ready_read, ready_write = os.pipe()
        watchdog = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("_hunter_view_watchdog.py")), str(lifetime_read), str(ready_write), str(root), str(entry.st_dev), str(entry.st_ino)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(lifetime_read, ready_write), start_new_session=True,
        )
        os.close(lifetime_read); os.close(ready_write)
        if os.read(ready_read, 1) != b"1":
            raise HunterViewError("hunter_view_watchdog_unavailable")
        os.close(ready_read)
        return HunterView(projection, runtime, view_digest, corpus_digest, manifest, lifetime_write, watchdog, root)
    except BaseException:
        try:
            os.chmod(root, 0o700)
            shutil.rmtree(root)
        except OSError: pass
        raise


def inspect_hunter_view(view: HunterView) -> dict[str, Any]:
    return {
        "schema_version": 1, "view_type": VIEW_VERSION, "principal": "hunter",
        "view_digest": view.view_digest, "input_corpus_digest": view.input_corpus_digest,
        "treatment": "compiled_current_only", "included": [
            {"class": "signed_scope", "digest": view.manifest["scope_digest"], "reason": "signed_safety_constraints"},
            *({"class": "methodology", "digest": row["digest"], "reason": "selected_card_or_oracle"} for row in view.manifest["methodology"]),
            *({"class": "target_input", "digest": row["digest"], "reason": row["reason"]} for row in view.manifest["target_inputs"]),
            *({"class": "current_hypothesis_evidence", "digest": row["digest"], "reason": row["reason"]} for row in view.manifest["evidence_inputs"]),
            {"class": "proposal_template", "digest": view.manifest["output_contract"]["proposal_template_digest"], "reason": "exact_admitted_output_shape"},
            {"class": "attempt_schema", "digest": view.manifest["output_contract"]["attempt_schema_digest"], "reason": "self_contained_output_validation"},
            {"class": "common_schema", "digest": view.manifest["output_contract"]["common_schema_digest"], "reason": "referenced_output_definitions"},
        ],
        "excluded_classes": list(EXCLUDED_CLASSES), "byte_budget": view.manifest["byte_budget"],
    }
