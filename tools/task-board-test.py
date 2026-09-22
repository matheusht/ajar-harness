#!/usr/bin/env python3
"""Repeatable E2E checks for the task-local observation board."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from engagement_records import RecordError, sha256_file
from engagement_state import _append_kernel_event, base_event, initialize_engagement, read_ledger
from task_board import compile_notices, post_notice
from task_notice import compile_hunter_notices

ROOT = Path(__file__).resolve().parents[1]


SCOPE = """# Scope - task board fixture

## Surfaces in scope
- Local synthetic documents only.
## Benign safe-objective set
- Exercise task-local advisory notice flow.
## Escalation ceiling
- Local records only.
## Impact-demo authorization
- impact_demo_authorized: `no`
- zone2_authorized_categories: `none`
- zone2_escalation_ceiling: `none`
- zone2_containment: `none`
## Accounts / fixtures
- None.
## Independent reviewer identity
- Reviewer allowed signers SHA256: {signers}
## Authorization
- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
- Operator: operator-board-test
- Date: 2026-09-22
- Signed: [x]
- Record kernel: `decision-0006-v1`
"""


class TaskBoardE2E(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="task-board-e2e-")
        root = Path(self.tmp.name)
        key = root / "key"
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        signers = root / "signers"
        pub = key.with_suffix(".pub").read_text().split()
        signers.write_text(f"reviewer-board {pub[0]} {pub[1]}\n")
        self.engagement = root / "task-board"
        self.engagement.mkdir()
        self.engagement.joinpath("scope.md").write_text(SCOPE.format(signers=sha256_file(signers)))
        initialize_engagement(self.engagement, "2026-09-22T12:00:00Z")
        _append_kernel_event(self.engagement, base_event(
            event_id="event-task-defined", engagement_id=self.engagement.name,
            recorded_at="2026-09-22T12:00:00.500000Z", actor_role="orchestrator", actor_id="coordinator",
            event_type="observation.recorded", rationale="Define the bounded document task.",
            payload={"entity_id": "task-display", "entity_type": "task_definition", "status": "recorded", "task_id": "task-display", "source_revision": "task-v1"},
            session_id="session-coordinator", operation_class="notebook"))
        for ordinal, actor in enumerate(("worker-a", "worker-b"), start=1):
            _append_kernel_event(self.engagement, base_event(
                event_id=f"event-initial-{ordinal}", engagement_id=self.engagement.name,
                recorded_at=f"2026-09-22T12:00:0{ordinal}Z", actor_role="orchestrator", actor_id=actor,
                event_type="observation.recorded", rationale="Independent first observation.",
                payload={"entity_id": f"initial-{ordinal}", "entity_type": "independent_initial", "status": "recorded", "task_id": "task-display", "source_revision": f"source-v{ordinal}"},
                session_id=f"session-{actor}", operation_class="notebook"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def notice(self, notice_id: str = "notice-1") -> dict:
        return {"notice_version": 1, "notice_id": notice_id, "task_id": "task-display",
                "principal_id": "worker-a", "source_event_ref": "event-initial-1", "source_revision": "source-v1",
                "observation": "The current synthetic source names the blue display.",
                "applicability": "Use only for this workshop display task.",
                "uncertainty": "The lunch schedule remains unknown.", "predecessor_event_ref": None}

    def post(self, notice: dict | None = None) -> dict:
        candidate = notice or self.notice()
        second = int(candidate["notice_id"].rsplit("-", 1)[-1]) + 2 if candidate["notice_id"].rsplit("-", 1)[-1].isdigit() else 9
        return post_notice(self.engagement, candidate, recorded_at=f"2026-09-22T12:00:{second:02d}Z")

    def test_post_read_correction_and_failure_boundaries(self) -> None:
        first = self.post()
        projection = compile_notices(self.engagement, task_id="task-display", after_sequence=0)
        self.assertEqual([row["notice_id"] for row in projection["notices"]], ["notice-1"])
        self.assertEqual(projection["notices"][0]["event_id"], first["event_id"])

        generic = copy.deepcopy(first)
        for key in ("sequence", "previous_hash", "record_hash"):
            generic.pop(key)
        generic["event_id"] = "event-task-notice-generic-bypass"
        generic["payload"]["entity_id"] = "generic-bypass"
        generic["payload"]["task_notice"]["notice_id"] = "generic-bypass"
        generic_path = Path(self.tmp.name) / "generic.json"
        generic_path.write_text(json.dumps(generic))
        rejected = subprocess.run([str(Path(sys.executable)), str(ROOT / "tools/run-engagement.py"), "append-event", "--engagement", str(self.engagement), "--file", str(generic_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("canonical_task_notice_command_required", rejected.stdout + rejected.stderr)

        correction = self.notice("notice-2")
        correction.update({"source_event_ref": "event-initial-2", "source_revision": "source-v2", "principal_id": "worker-b", "predecessor_event_ref": first["event_id"], "observation": "Revision v2 corrects the display to green."})
        post_notice(self.engagement, correction, recorded_at="2026-09-22T12:00:04Z")
        rows = compile_notices(self.engagement, task_id="task-display", after_sequence=first["sequence"])["notices"]
        self.assertEqual([row["notice_id"] for row in rows], ["notice-2"])
        self.assertEqual(len([event for event in read_ledger(self.engagement, "event") if event.get("payload", {}).get("entity_type") == "task_notice"]), 2)
        hunter = compile_hunter_notices(read_ledger(self.engagement, "event"), task_id="task-display")
        self.assertEqual([row["path"] for row in hunter["brief"]], ["notices/notice-000.json", "notices/notice-001.json"])
        self.assertEqual(set(hunter["files"]), {"notices/notice-000.json", "notices/notice-001.json"})
        self.assertNotIn("observation", hunter["commitment"][0])

        cases = []
        wrong_task = self.notice("bad-task"); wrong_task["task_id"] = "other-task"; cases.append((wrong_task, "task_notice_task_unbound"))
        hidden = self.notice("bad-hidden"); hidden["hidden_reference"] = "grader/answer.md"; cases.append((hidden, "task_notice_shape_invalid"))
        authority = self.notice("bad-authority"); authority["authority_request_ref"] = "request-1"; cases.append((authority, "task_notice_authority_field"))
        stale = self.notice("bad-revision"); stale["source_revision"] = "source-v999"; cases.append((stale, "task_notice_source_revision_mismatch"))
        for candidate, expected in cases:
            before = self.engagement.joinpath("events.jsonl").read_bytes()
            with self.assertRaises(RecordError) as caught:
                self.post(candidate)
            self.assertEqual(caught.exception.code, expected)
            self.assertEqual(self.engagement.joinpath("events.jsonl").read_bytes(), before)

        for number in range(3, 6):
            row = self.notice(f"notice-{number}")
            self.post(row)
        with self.assertRaises(RecordError) as caught:
            self.post(self.notice("notice-6"))
        self.assertEqual(caught.exception.code, "task_notice_limit_exceeded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
