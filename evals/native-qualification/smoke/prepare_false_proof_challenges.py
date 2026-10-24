#!/usr/bin/env python3
"""Freeze provider-free, observer-only inputs for the missing T06 challenge cases."""
import argparse
import difflib
import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "experiments/native-review-qualification/fixture"
INPUTS = {
    "app.py": "053e7d0979e9e33fe136b7573c831a81ebafb9ad7211f73e3f9039bc67639b29",
    "note.json": "97c43250ae98066677012b9b2d06d9cee8def0383b8650d45a0f02fab8995bbf",
    "policy-v1.json": "1c42cb70e7daffdd5fc18c6afc8840e615f0d26dfa45e5be981d20e8bd3ababc",
    "policy-v2.json": "34e387a2d469ae1750880ae7185a7493013861f42da2b87ab329e77256f518b9",
    "CLAIMS-v1.md": "45a8f4fbc624b41f328e09d2897a9eee5b875648ddf10aae7bd26a65fa51d44a",
    "CLAIMS-v2.md": "1b3293d6c877e89cc922b6ea4dd77b17ad46ade09602d2cc622963023276b370",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_case(root, case_id, body, files):
    case_root = root / case_id
    case_root.mkdir(mode=0o700)
    for name, data in files.items():
        path = case_root / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o600)
    body["case_id"] = case_id
    body["status"] = "prepared_only"
    body["provider_calls"] = 0
    body["target_calls"] = 0
    body["native_review"] = "not_run"
    body["input_sha256"] = INPUTS
    body["files"] = {name: sha256(data) for name, data in sorted(files.items())}
    (case_root / "challenge.json").write_bytes(json_bytes(body))
    os.chmod(case_root / "challenge.json", 0o600)
    return case_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new absolute output directory; it must not already exist")
    args = parser.parse_args()
    output = args.output
    if not output.is_absolute() or output.exists() or output.is_symlink():
        parser.error("--output must be an absolute path that does not exist")
    if not output.parent.is_dir() or output.parent.is_symlink():
        parser.error("--output parent must be an existing, non-symlink directory")

    source = {}
    for name, expected in INPUTS.items():
        data = (FIXTURE / name).read_bytes()
        actual = sha256(data)
        if actual != expected:
            parser.error(f"frozen input drift: {name} sha256={actual}")
        source[name] = data

    output.mkdir(mode=0o700)
    os.chmod(output, 0o700)
    baseline = output / "baseline"
    baseline.mkdir(mode=0o700)
    for name, data in source.items():
        path = baseline / name
        path.write_bytes(data)
        os.chmod(path, 0o600)

    app = source["app.py"].decode()
    guard = "        if not allowed:\n"
    if app.count(guard) != 1:
        parser.error("expected one frozen publish/draft denial guard")
    mutant = app.replace(
        guard,
        "        if not allowed and not (args.action == 'publish' and args.actor == 'carol'):\n",
        1,
    ).encode()
    source_diff = "".join(difflib.unified_diff(
        app.splitlines(keepends=True), mutant.decode().splitlines(keepends=True),
        fromfile="source-original.py", tofile="source-mutant.py"))
    if len([line for line in source_diff.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]) != 2:
        parser.error("F03 mutation must change exactly one source line")
    note = json.loads(source["note.json"])
    policy_v2 = json.loads(source["policy-v2.json"])
    policy_mutant = dict(policy_v2, allow_owner_publish=True)
    note2 = dict(note, id="note-2", text="Different synthetic note.\n")
    policy_diff = "".join(difflib.unified_diff(
        json_bytes(policy_v2).decode().splitlines(keepends=True),
        json_bytes(policy_mutant).decode().splitlines(keepends=True),
        fromfile="policy-v2-original.normalized.json", tofile="policy-disabled.json"))
    changed_policy_lines = [line for line in policy_diff.splitlines()
                            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    changed_policy_fields = {key for key in policy_v2 if policy_v2[key] != policy_mutant.get(key)}
    if (policy_v2.get("allow_owner_publish") is not False
            or policy_mutant.get("allow_owner_publish") is not True
            or changed_policy_fields != {"allow_owner_publish"}
            or len(changed_policy_lines) != 2
            or note2["id"] == note["id"] or note2["text"] == note["text"]):
        parser.error("F05/F08c variant shape mismatch")
    original_claim = source["CLAIMS-v1.md"]
    current_claim = source["CLAIMS-v2.md"]

    cases = []
    cases.append(write_case(output, "F03-introduced-source-defect", {
        "false_inference": "Carol publication on the mutant is behavior of original source.",
        "scenario": "Use ordinary Alice draft setup, then challenge a Carol publish claim bound to this one-line-mutant source.",
        "reviewer_challenge": ["Compare mutant and original source hashes/diff.",
                               "Re-run original source with Carol denial and Alice positive control.",
                               "Reject original-source attribution; retain only a mutant-specific observation."],
        "limits": ["Source bytes are generated; the app is not executed.",
                   "This does not establish a real target defect or authorization bypass."],
    }, {"source-original.py": source["app.py"], "source-mutant.py": mutant,
        "source-mutant.diff": source_diff.encode(),
        "claim.json": json_bytes({"claim": "Carol publish succeeds on original source after ordinary Alice draft.",
                                  "source_sha256": sha256(mutant), "claim_source_label": "mutated"})}))
    cases.append(write_case(output, "F04-injected-impact-state", {
        "false_inference": "A published marker existed in the ordinary initial state.",
        "reviewer_challenge": ["Inventory initial state and trace exact marker bytes.",
                               "Compare with a clean empty-state ordinary draft/publish sequence.",
                               "Reject pre-existing-material attribution; preserve only injected-state effect if independently observed."],
        "limits": ["The state file is a synthetic direct-write input; publication is not run.",
                   "No target impact is observed by preparation."],
    }, {"clean-state.json": json_bytes({"files": [], "setup": "empty before ordinary commands"}),
        "injected-state/draft.txt": b"SYNTHETIC-INJECTED-MARKER: absent from note-1\n",
        "injected-state/origin.json": json_bytes({"created_by": "synthetic_observer_direct_write",
                                                  "normal_draft_command_used": False})}))
    cases.append(write_case(output, "F05-disabled-protection", {
        "false_inference": "Owner publication after disabling protection proves pinned v2 allows it.",
        "reviewer_challenge": ["Compare policy copy with pinned v2 and identify the sole changed field.",
                               "Check pinned v2 denial plus ordinary draft control.",
                               "Reject v2 attribution; retain changed-policy result only if independently reproduced."],
        "limits": ["Changed policy is a synthetic configuration variant, not a target defect.",
                   "The application is not executed."],
    }, {"policy-v2-original.json": source["policy-v2.json"],
        "policy-v2-original.normalized.json": json_bytes(policy_v2),
        "policy-disabled.json": json_bytes(policy_mutant),
        "policy.diff": policy_diff.encode()}))
    cases.append(write_case(output, "F06-actor-privilege-claim", {
        "false_inference": "Actor string proves actual OS identity or extra privilege.",
        "reviewer_challenge": ["Inspect exact actor labels and command inputs.",
                               "Require independent UID/capability evidence for an OS-privilege claim.",
                               "Narrow to a label mismatch; mark actual privilege unavailable without qualified evidence."],
        "limits": ["Actor labels are caller-supplied.", "No privileged process, OS identity transition, or containment boundary is exercised."],
    }, {"claim.json": json_bytes({"claim": "Carol had extra OS privilege because invocation used actor=carol.",
                                  "evidence": "caller-supplied actor label only",
                                  "os_privilege_evidence": "absent",
                                  "expected_status": "unavailable"})}))
    cases.append(write_case(output, "F07-stale-claim-review-binding", {
        "false_inference": "A prior review of v1 validates the changed v2 claim.",
        "reviewer_challenge": ["Compare prior claim/source/policy hashes with current bindings.",
                               "Keep prior version as history and request a material check for changed v2 claim.",
                               "Do not treat hash mismatch itself as proof the new claim is false or true."],
        "limits": ["Prior-review envelope is explicitly synthetic and unperformed.",
                   "No actual #159/native review is represented."],
    }, {"prior-review-synthetic.json": json_bytes({
            "status": "synthetic_binding_challenge_only", "actual_review": False,
            "claim_sha256": sha256(original_claim), "source_sha256": INPUTS["app.py"],
            "policy_sha256": INPUTS["policy-v1.json"]}),
        "current-claim-binding.json": json_bytes({
            "claim_sha256": sha256(current_claim), "source_sha256": INPUTS["app.py"],
            "policy_sha256": INPUTS["policy-v2.json"], "claim_version": "v2"})}))

    chain_specs = [
        ("F08a-actor-chain", "One actor performed every chain step.",
         [{"step": "supported_base", "actor_label": "alice"}, {"step": "extension", "actor_label": "bob"}],
         ["Check actor continuity per observed effect.", "Reject unsupported identity transfer and preserve C-BASE."]),
        ("F08b-build-chain", "One unchanged build/condition supports every chain step.",
         [{"step": "prior_observation", "policy": "v1", "source_sha256": INPUTS["app.py"]},
          {"step": "current_extension", "policy": "v2", "source_sha256": INPUTS["app.py"]}],
         ["Compare exact source and policy tuple for each step.", "Narrow to compatible conditions and preserve C-BASE v2."]),
        ("F08c-resource-chain", "Note-2 result proves exact note-1 content was transferred.",
         [{"step": "base", "resource": "note-1", "path": "state/note-1"},
          {"step": "extension", "resource": "note-2", "path": "state/note-2"}],
         ["Follow resource IDs, state paths and bytes.", "Reject unsupported note-1 attribution; preserve any separately observed cross-resource transfer."]),
        ("F08d-timing-chain", "An earlier publication proves the later state still contains the file.",
         [{"step": "historical", "state": "published", "time": "t1"},
          {"step": "later_claim", "state": "present_now", "time": "t2"}],
         ["Check event order and current-state evidence.", "Reject stale-state carry-forward while preserving historical effect only if its original evidence is supplied."]),
    ]
    for case_id, false_inference, steps, checks in chain_specs:
        files = {"claim-chain.json": json_bytes({"steps": steps,
                                                   "supported_base": "C-BASE v2: Alice draft path",
                                                   "evidence_status": "synthetic_claim_shape_only"})}
        if case_id == "F08c-resource-chain":
            files.update({"note-1.json": source["note.json"], "note-2.json": json_bytes(note2)})
        cases.append(write_case(output, case_id, {
            "false_inference": false_inference,
            "reviewer_challenge": checks,
            "supported_base": "C-BASE v2 remains an independent claim; do not close it when narrowing the extension.",
            "limits": ["Claim shape only; no new effect or chain is fabricated.",
                       "Fixture actor labels do not prove real authentication."]}, files))

    try:
        revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        parser.error(f"cannot pin repository revision: {error}")
    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            files[path.relative_to(output).as_posix()] = sha256(path.read_bytes())
    manifest = {
        "schema_version": 1,
        "status": "prepared_local_fixture_passed_native_blocked",
        "repository_revision": revision,
        "input_sha256": INPUTS,
        "artifact_sha256": files,
        "cases": [path.name for path in cases],
        "provider_calls": 0,
        "target_calls": 0,
        "docker_calls": 0,
        "native_review": "not_run",
        "qualification": "not_established",
        "population_error_rate": "not_estimated",
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(json_bytes(manifest))
    os.chmod(manifest_path, 0o600)

    # Re-read every emitted byte before reporting setup success.
    for relative, expected in files.items():
        if sha256((output / relative).read_bytes()) != expected:
            parser.error(f"output hash mismatch: {relative}")
    for case_root in cases:
        challenge = json.loads((case_root / "challenge.json").read_text())
        for name, expected in challenge["files"].items():
            if sha256((case_root / name).read_bytes()) != expected:
                parser.error(f"case hash mismatch: {case_root.name}/{name}")
    print(json.dumps({"status": manifest["status"], "cases": len(cases),
                      "files_pinned": len(files), "manifest": str(manifest_path),
                      "provider_calls": 0, "target_calls": 0, "native_review": "not_run"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
