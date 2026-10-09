#!/usr/bin/env python3
"""Public KB promotion workflow over a saved signed synthetic finding."""

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
ENTRY = {
    "schema_version": 1, "id": "KB-20261009-owned-source-comparison", "kind": "winner",
    "recorded_at": "2026-10-09", "mechanism_class": "matched-source-comparison",
    "cards": ["task-reframing"], "transfer_scope": "this-mechanism-class",
    "boundedness": "bounded", "summary": "Compare an owned benign source marker with a matched control and fresh replay.",
    "writer": {"role": "orchestrator", "note": "Checked signed source, independent review, replay, relevance, and redaction."},
}
FIXTURE = {"base": [{"route": "other", "family": "other", "priority": 1},
                    {"route": "task-reframing", "family": "source-comparison", "priority": 1}],
           "context": {"target": "future-synthetic", "framework": "owned", "language": "python"}}


def run(source: Path, kb: Path, entry_file: Path, fixture: Path, *, finding_id="F-canonical-public", revision=1,
        replay_id="attempt-canonical-replay") -> subprocess.CompletedProcess[str]:
    return subprocess.run([PYTHON, str(ROOT / "tools/kb.py"), "promote-confirmed",
                           "--source-engagement", str(source), "--finding-id", finding_id,
                           "--revision", str(revision), "--replay-id", replay_id,
                           "--entry-file", str(entry_file), "--fixture", str(fixture), "--kb", str(kb)],
                          text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="saved output from internal-filing-workflow-test.py")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="learning-126-") as temporary:
        root = Path(temporary)
        source = root / "source"
        shutil.copytree(args.source.resolve() / "engagement", source)
        kb = root / "kb.jsonl"
        entry_file = root / "entry.json"
        entry_file.write_text(json.dumps(ENTRY, sort_keys=True))
        fixture = root / "route.json"
        fixture.write_text(json.dumps(FIXTURE, sort_keys=True))
        positive = run(source, kb, entry_file, fixture)
        assert positive.returncode == 0, positive.stdout + positive.stderr
        before = kb.read_bytes()
        repeated = run(source, kb, entry_file, fixture)
        assert repeated.returncode == 0 and kb.read_bytes() == before, repeated.stdout + repeated.stderr
        held = copy.deepcopy(ENTRY)
        held.update({"id": "KB-20261009-held-source-control", "kind": "loser",
                     "cards": ["adjudication-oracle"],
                     "summary": "An owned matched source without the marker remained blocked by its held control.",
                     "control": {"mechanism": "The matched source omitted the bounded marker."}})
        held_file = root / "held.json"
        held_file.write_text(json.dumps(held, sort_keys=True))
        held_fixture = copy.deepcopy(FIXTURE)
        held_fixture["base"].reverse()
        held_fixture["base"][0]["route"] = "adjudication-oracle"
        held_route = root / "held-route.json"
        held_route.write_text(json.dumps(held_fixture, sort_keys=True))
        accepted_held = run(source, kb, held_file, held_route)
        assert accepted_held.returncode == 0, accepted_held.stdout + accepted_held.stderr
        before = kb.read_bytes()
        denials = {}

        def deny(name: str, entry: dict, *, finding_id="F-canonical-public", revision=1,
                 replay_id="attempt-canonical-replay", route_fixture=FIXTURE) -> None:
            proposal = root / f"{name}.json"
            proposal.write_text(json.dumps(entry, sort_keys=True))
            test_fixture = root / f"{name}-route.json"
            test_fixture.write_text(json.dumps(route_fixture, sort_keys=True))
            result = run(source, kb, proposal, test_fixture, finding_id=finding_id,
                         revision=revision, replay_id=replay_id)
            assert result.returncode != 0 and kb.read_bytes() == before, (name, result.stdout, result.stderr)
            denials[name] = result.stdout.strip().splitlines()[0]

        deny("unproved", ENTRY, finding_id="F-unproven")
        deny("stale", ENTRY, revision=2)
        deny("wrong-replay", ENTRY, replay_id="attempt-canonical-negative")
        sensitive = copy.deepcopy(ENTRY); sensitive["summary"] += " eng-selftest"
        deny("source-identifier", sensitive)
        secret = copy.deepcopy(ENTRY); secret["summary"] += " password=synthetic-secret-value"
        deny("secret", secret)
        irrelevant = copy.deepcopy(ENTRY); irrelevant["cards"] = ["unrouted-card"]
        deny("irrelevant", irrelevant)
        overbroad = copy.deepcopy(ENTRY); overbroad["family"] = ["unreviewed-family"]
        deny("overbroad-family", overbroad)
        unproved_control = copy.deepcopy(ENTRY); unproved_control["control_is_proven"] = True
        deny("unproved-control", unproved_control)
        loser = copy.deepcopy(ENTRY); loser["kind"] = "loser"
        deny("unsupported-loser", loser)
        if args.output:
            output = args.output.resolve()
            output.mkdir(parents=True, exist_ok=False)
            shutil.copytree(source, output / "source")
            shutil.copy2(kb, output / "kb.jsonl")
            shutil.copy2(entry_file, output / "entry.json")
            shutil.copy2(fixture, output / "route.json")
            shutil.copy2(held_file, output / "held.json")
            shutil.copy2(held_route, output / "held-route.json")
            (output / "result.json").write_text(json.dumps({"source_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip(), "denials": denials, "replayed": repeated.stdout.strip(), "provider": "none", "target_contact": False}, sort_keys=True))
        print(json.dumps({"ok": True, "kb_entries": len(before.splitlines()), "denials": sorted(denials)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
