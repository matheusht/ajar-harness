#!/usr/bin/env python3
"""Issue #97 workflow check, written before the implementation.

Failure inventory exercised here: incomplete hypothesis semantics; missing/changed/unsafe
methodology; traversal, symlink, hardlink, special-file and Git-object input escapes; byte-budget
overflow; hidden verdict/memory/gold leakage; nondeterministic manifests; stale source/action/scope
bindings; principal/view replay; unsafe inspection output; and projection residue after normal or
abnormal parent termination.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from engagement_records import canonical_json_bytes, sha256_bytes  # noqa: E402
from engagement_state import materialize_ledger_record  # noqa: E402
from hunter_view import HunterViewError, compile_hunter_view, inspect_hunter_view  # noqa: E402


SAFE_VULN = """---
id: fixture-vuln
type: vuln
safe_signal:
  proxy: fixture-only distinctive marker
  never: do not access anything outside the owned fixture
---
# Fixture vulnerability
"""
ORACLE = """---
id: fixture-oracle
type: oracle
---
# Fixture oracle
Reject unless the marker is specific and the matched control holds.
"""
TECHNIQUE = """---
id: fixture-technique
type: technique
operates_only_against: safe_signal-gated objective
---
# Fixture technique
Use the bounded local marker only.
"""


class HunterViewWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="hunter-view-workflow-")
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "target"
        self.engagement = self.workspace / "engagements" / "fixture"
        self.engagement.mkdir(parents=True)
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "route.txt").write_text("owned marker\n", encoding="utf-8")
        scope_bytes = b"# signed scope\n- objective: owned fixture marker\n- ceiling: clear_local\n"
        self.scope = self.engagement / "scope-attestations" / (sha256_bytes(scope_bytes).removeprefix("sha256:") + ".md")
        self.scope.parent.mkdir()
        self.scope.write_bytes(scope_bytes)
        self.cards = self.root / "cards"
        for family, card_id, text in (
            ("vulns", "fixture-vuln", SAFE_VULN),
            ("techniques", "fixture-technique", TECHNIQUE),
            ("oracles", "fixture-oracle", ORACLE),
        ):
            path = self.cards / family / card_id / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(text, encoding="utf-8")
        self.state = {
            "engagement_id": "fixture",
            "scope_hash": sha256_bytes(self.scope.read_bytes()),
            "active_environment_ref": "environment-fixture",
            "ledger_hash": "sha256:" + "b" * 64,
            "source_hashes": {"events.jsonl": "sha256:" + "c" * 64, "attempts.jsonl": "sha256:" + "d" * 64, "artifacts.jsonl": "sha256:" + "e" * 64},
            "hypotheses": {
                "hypothesis-fixture": {
                    "status": "running",
                    "statement": "The owned route exposes the distinctive marker.",
                    "suspected_invariant": "The marker stays behind the route guard.",
                    "trust_boundary": "owned caller to owned fixture",
                    "attacker_path": ["owned caller", "route", "marker"],
                    "impact_ceiling": "clear_local fixture only",
                    "bounded_space": "one exact source file",
                    "lens_ids": ["authorization"],
                    "card_ids": ["fixture-vuln", "fixture-technique", "fixture-oracle"],
                    "expected_confirming_evidence": [{"evidence_type": "trace", "description": "marker crosses guard", "required": True}],
                    "decisive_falsifiers": ["guard blocks the marker"],
                    "cost_estimate": {"model_calls": 1, "tool_calls": 1, "wall_clock_minutes": 1, "external_side_effects": "none"},
                    "constraints": ["read only", "clear_local"],
                    "next_experiment": "Inspect the exact route file and record one primary attempt.",
                    "completion_criteria": ["specific marker result", "falsifier disposition"],
                    "experiment_refs": [], "control_refs": [], "supporting_evidence_refs": [],
                    "conflicting_evidence_refs": [], "unresolved_questions": [], "next_route": None,
                    "running_event_ref": "event-running-fixture",
                    "prior_verdict": "confirmed hidden answer",
                }
            },
        }
        self.item = {
            "class": "hypothesis_running_unattempted",
            "entity": {"type": "hypothesis", "id": "hypothesis-fixture", "detail": None},
            "next_action": {
                "action_id": "record_hunter_primary", "principal": "hunter",
                "session_kind": "ordinary_bounded", "command": "append-attempt",
                "arguments": ["--engagement", str(self.engagement), "--file", "<hunter-primary-attempt-json>"],
                "admission": {"schema_version": 1, "constraints": []},
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def compile(self, **overrides):
        values = dict(workspace=self.workspace, engagement=self.engagement, state=self.state,
                      item=self.item, target_inputs=(self.workspace / "src" / "route.txt",),
                      methodology_root=self.cards, byte_budget=64 * 1024)
        values.update(overrides)
        return compile_hunter_view(**values)

    def write_artifacts(self, entries: list[tuple[str, bytes]]) -> None:
        records = []
        evidence = self.engagement / "evidence"
        evidence.mkdir(exist_ok=True)
        for artifact_id, data in entries:
            relative = f"evidence/{artifact_id}.txt"
            (self.engagement / relative).write_bytes(data)
            proposal = {
                "schema_version": 1, "artifact_id": artifact_id, "engagement_id": "fixture",
                "relative_path": relative, "sha256": sha256_bytes(data), "size": len(data),
                "media_type": "text/plain", "created_at": "2026-09-22T12:00:00Z",
                "producer": {"role": "operator", "id": "operator-fixture"},
                "acquisition_method": "source_inspection", "target_refs": [],
                "environment_ref": "environment-fixture", "sensitivity": "internal",
                "redaction_status": "not_needed", "contains_executable_capability": False,
                "advisory_zone": "clear_local", "escalation_confirmation_event_ref": None,
                "cleanup_obligation_ref": None, "immutable": True, "supersedes_artifact_id": None,
            }
            record = materialize_ledger_record("artifact", proposal, records)
            records.append(record)
        (self.engagement / "artifacts.jsonl").write_bytes(b"".join(canonical_json_bytes(row) for row in records))

    def test_determinism_noninterference_and_visibility(self) -> None:
        with self.compile() as first:
            first_digest = first.view_digest
            manifest = json.loads((first.projection / "manifest.json").read_text())
            exposed = "\n".join(path.read_text(errors="ignore") for path in first.projection.rglob("*") if path.is_file())
            self.assertEqual(manifest["principal"], "hunter")
            self.assertIn("fixture-vuln", exposed)
            self.assertIn("decisive_falsifiers", exposed)
            self.assertNotIn(str(self.workspace), exposed)
            self.assertNotIn("prior verdict", exposed.lower())
            self.assertNotIn("confirmed hidden answer", exposed)
            self.assertFalse((first.projection / ".git").exists())
        (self.engagement / "reviews").mkdir()
        (self.engagement / "reviews" / "hidden.json").write_text('{"verdict":"confirmed"}')
        with self.compile() as second:
            self.assertEqual(first_digest, second.view_digest)
        hidden_state = json.loads(json.dumps(self.state))
        hidden_state["ledger_hash"] = "sha256:" + "1" * 64
        hidden_state["source_hashes"]["events.jsonl"] = "sha256:" + "2" * 64
        with self.compile(state=hidden_state) as hidden_commitment_changed:
            self.assertEqual(first_digest, hidden_commitment_changed.view_digest)
        (self.workspace / "src" / "route.txt").write_text("changed marker\n", encoding="utf-8")
        with self.compile() as changed:
            self.assertNotEqual(first_digest, changed.view_digest)

    def test_adversarial_inputs_and_methodology_fail_closed(self) -> None:
        outside = self.root / "outside.txt"; outside.write_text("secret")
        link = self.workspace / "src" / "link"; link.symlink_to(outside)
        linked_directory = self.workspace / "linked-dir"; linked_directory.symlink_to(outside.parent, target_is_directory=True)
        hard = self.workspace / "src" / "hard"; os.link(self.workspace / "src" / "route.txt", hard)
        git = self.workspace / ".git"; git.mkdir(); (git / "object").write_text("hidden")
        fifo = self.workspace / "src" / "fifo"; os.mkfifo(fifo)
        for path in (outside, link, linked_directory / outside.name, hard, fifo, git / "object"):
            with self.subTest(path=path), self.assertRaises(HunterViewError):
                self.compile(target_inputs=(path,))
        with self.assertRaises(HunterViewError):
            self.compile(byte_budget=1)
        vuln = self.cards / "vulns" / "fixture-vuln" / "SKILL.md"
        vuln.write_text(SAFE_VULN.replace("safe_signal:", "unsafe_signal:"), encoding="utf-8")
        with self.assertRaises(HunterViewError):
            self.compile()

    def test_included_input_and_methodology_staleness_reject_launch(self) -> None:
        packet = self.compile()
        try:
            (self.workspace / "src" / "route.txt").write_text("changed after compile\n", encoding="utf-8")
            with self.assertRaises(HunterViewError):
                packet.assert_current(workspace=self.workspace, engagement=self.engagement, state=self.state, item=self.item, methodology_root=self.cards)
        finally:
            packet.close()
        schemas = self.root / "schemas"
        schemas.mkdir()
        for name in ("attempt-v2.schema.json", "research-common.schema.json"):
            shutil.copyfile(ROOT / "schemas" / name, schemas / name)
        packet = self.compile(schema_root=schemas)
        try:
            with (schemas / "attempt-v2.schema.json").open("ab") as stream:
                stream.write(b"\n")
            with self.assertRaises(HunterViewError):
                packet.assert_current(workspace=self.workspace, engagement=self.engagement, state=self.state, item=self.item, methodology_root=self.cards, schema_root=schemas)
        finally:
            packet.close()
        (self.workspace / "src" / "route.txt").write_text("owned marker\n", encoding="utf-8")
        packet = self.compile()
        try:
            oracle = self.cards / "oracles" / "fixture-oracle" / "SKILL.md"
            oracle.write_text(ORACLE + "\nchanged\n", encoding="utf-8")
            with self.assertRaises(HunterViewError):
                packet.assert_current(workspace=self.workspace, engagement=self.engagement, state=self.state, item=self.item, methodology_root=self.cards)
        finally:
            packet.close()

    def test_only_explicit_current_evidence_is_projected_and_rechecked(self) -> None:
        allowed = b"allowed current trace marker\n"
        neighboring = b"neighboring hidden review answer\n"
        self.write_artifacts([("artifact-allowed", allowed), ("artifact-neighbor", neighboring)])
        hypothesis = self.state["hypotheses"]["hypothesis-fixture"]
        hypothesis["supporting_evidence_refs"] = ["artifact-allowed"]
        packet = self.compile()
        try:
            self.assertEqual((packet.projection / "evidence" / "evidence-000").read_bytes(), allowed)
            projected = b"\n".join(path.read_bytes() for path in packet.projection.rglob("*") if path.is_file())
            self.assertNotIn(neighboring, projected)
            self.assertNotIn(b"artifact-neighbor", projected)
            (self.engagement / "evidence" / "artifact-allowed.txt").write_bytes(b"changed after compile\n")
            with self.assertRaisesRegex(HunterViewError, "hunter_view_stale"):
                packet.assert_current(workspace=self.workspace, engagement=self.engagement, state=self.state, item=self.item, methodology_root=self.cards)
        finally:
            packet.close()

    def test_review_and_control_hunter_actions_preserve_exact_action(self) -> None:
        cases = (
            ("review_obligation_open", "review-fixture", "outstanding_reviews", {"review_ref": "review-fixture", "hypothesis_ref": "hypothesis-fixture"}, "collect_review_evidence"),
            ("control_candidate_unverified", "routing-fixture", "control_candidates", {"routing_event_id": "routing-fixture", "hypothesis_ref": "hypothesis-fixture"}, "record_control_primary"),
        )
        for item_class, entity_id, state_key, row, action_id in cases:
            with self.subTest(action_id=action_id):
                state = json.loads(json.dumps(self.state))
                state[state_key] = [row]
                item = json.loads(json.dumps(self.item))
                item["class"] = item_class
                item["entity"]["id"] = entity_id
                item["next_action"]["action_id"] = action_id
                with self.compile(state=state, item=item) as packet:
                    self.assertEqual(packet.manifest["action"]["action_id"], action_id)
                    self.assertEqual(json.loads((packet.projection / "brief.json").read_text())["action"]["action_id"], action_id)

    def test_safe_inspection_and_normal_cleanup(self) -> None:
        packet = self.compile()
        projection = packet.projection
        summary = inspect_hunter_view(packet)
        rendered = canonical_json_bytes(summary).decode()
        self.assertIn(packet.view_digest, rendered)
        self.assertNotIn(str(self.workspace), rendered)
        self.assertNotIn("owned marker", rendered)
        packet.close()
        self.assertFalse(projection.exists())

    def test_parent_death_cleanup(self) -> None:
        marker = self.root / "projection-path"
        script = f'''import pathlib,sys,time\nsys.path.insert(0,{str(ROOT / "tools")!r})\nfrom hunter_view import compile_hunter_view\nimport json\nstate=json.loads({json.dumps(self.state)!r})\nitem=json.loads({json.dumps(self.item)!r})\np=compile_hunter_view(workspace=pathlib.Path({str(self.workspace)!r}),engagement=pathlib.Path({str(self.engagement)!r}),state=state,item=item,target_inputs=(pathlib.Path({str(self.workspace / "src" / "route.txt")!r}),),methodology_root=pathlib.Path({str(self.cards)!r}),byte_budget=65536)\npathlib.Path({str(marker)!r}).write_text(str(p.projection))\ntime.sleep(60)\n'''
        process = subprocess.Popen([sys.executable, "-c", script])
        for _ in range(100):
            if marker.exists(): break
            import time; time.sleep(.02)
        projection = Path(marker.read_text())
        process.kill(); process.wait()
        for _ in range(100):
            if not projection.exists(): break
            import time; time.sleep(.02)
        self.assertFalse(projection.exists())


if __name__ == "__main__":
    unittest.main()
