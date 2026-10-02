#!/usr/bin/env python3
"""E2E checks that conformance scans reject hostile filesystem entries."""
import contextlib
import hashlib
import io
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).with_name("check-conformance.py")


def scan(root, mode):
    spec = importlib.util.spec_from_file_location("check_conformance", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = str(root)
    rows = []
    module.record = lambda ok, label, detail="": rows.append((ok, label, detail))
    with contextlib.redirect_stdout(io.StringIO()):
        if mode == "secrets":
            module.check_secrets()
            result = rows
        elif mode == "oracles":
            module.check_oracles()
            result = rows
        elif mode == "casebooks":
            module.subprocess.run = lambda *args, **kwargs: type(
                "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            module.check_casebooks({"pattern.safe"})
            result = rows
        elif mode == "capabilities":
            ids = module.collect_capability_ids()
            module.check_capabilities()
            module.check_capability_classes()
            result = {"ids": sorted(ids), "rows": rows}
        elif mode == "capability-fixtures":
            module.check_capability_must_reject()
            result = rows
        elif mode == "finding-fixtures":
            module.validate_record = lambda *args, **kwargs: []
            module.check_finding_fixtures()
            result = rows
        elif mode == "tool-families":
            module.check_tool_family_manifests()
            module.check_tool_family_must_reject()
            result = rows
        elif mode == "payload-proposals":
            module.check_payload_proposals()
            result = rows
        elif mode == "static-corpora":
            module.check_false_discovery_corpus()
            module.check_adversarial_candidates()
            result = rows
        elif mode == "framing-probe":
            module.check_framing_probe()
            result = rows
        elif mode == "interventions":
            module.check_intervention_corpus()
            result = rows
        else:
            ids = module.collect_pattern_ids()
            module.check_cards("patterns", ids, set())
            result = {"ids": ids, "rows": rows}
    print(json.dumps(result))


def run_scan(root, mode="secrets"):
    result = subprocess.run(
        [sys.executable, __file__, "--scan", mode, str(root)],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--scan":
        scan(sys.argv[3], sys.argv[2])
        return

    with tempfile.TemporaryDirectory(prefix="secret-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        for name in ("casebooks", "fixtures", "evals"):
            (root / name).mkdir(parents=True)

        fifo_root = root / "evals"
        os.mkfifo(fifo_root / "blocked.fifo")
        rows = run_scan(root)
        assert rows and not rows[0][0] and "blocked.fifo" in rows[0][2], rows

        (fifo_root / "blocked.fifo").unlink()
        outside = Path(tmp) / "outside.txt"
        outside.write_text("EVIDENCE-ABCDEF secret-shaped marker")
        (fifo_root / "outside-link.txt").symlink_to(outside)
        rows = run_scan(root)
        assert rows and not rows[0][0] and "outside-link.txt" in rows[0][2], rows
        assert "EVIDENCE-ABCDEF" not in rows[0][2], rows

        (fifo_root / "outside-link.txt").unlink()
        outside_dir = Path(tmp) / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "hidden.txt").write_text("EVIDENCE-ABCDEF")
        (fifo_root / "outside-dir").symlink_to(outside_dir, target_is_directory=True)
        rows = run_scan(root)
        assert rows and not rows[0][0] and "outside-dir" in rows[0][2], rows
        assert "EVIDENCE-ABCDEF" not in rows[0][2], rows

        (fifo_root / "outside-dir").unlink()
        (fifo_root / "ordinary.txt").write_text("EVIDENCE-ABCDEF")
        rows = run_scan(root)
        assert rows and not rows[0][0] and "EVIDENCE-ABCDEF" in rows[0][2], rows

    oracle_failures = []
    with tempfile.TemporaryDirectory(prefix="oracle-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        oracle_dir = root / "skills" / "oracles"
        oracle_dir.mkdir(parents=True)

        fifo = oracle_dir / "blocked.md"
        os.mkfifo(fifo)
        try:
            rows = run_scan(root, "oracles")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"FIFO: {exc}")
        fifo.unlink()

        oracle = "---\nid: oracle.test\ntype: oracle\n---\nRegular fixture.\n"
        outside = Path(tmp) / "outside.md"
        outside.write_text(oracle)
        link = oracle_dir / "outside.md"
        link.symlink_to(outside)
        try:
            rows = run_scan(root, "oracles")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"file symlink: {exc}")
        link.unlink()

        (oracle_dir / "regular.md").write_text(oracle)
        try:
            rows = run_scan(root, "oracles")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"regular card: {exc}")

        oracle_dir.rename(root / "skills" / "oracles-saved")
        outside_root = Path(tmp) / "outside-oracles"
        outside_root.mkdir()
        (outside_root / "external.md").write_text(oracle)
        oracle_dir.symlink_to(outside_root, target_is_directory=True)
        try:
            rows = run_scan(root, "oracles")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            oracle_failures.append(f"oracle root symlink: {exc}")

    assert not oracle_failures, "\n".join(oracle_failures)

    capability_failures = []
    with tempfile.TemporaryDirectory(prefix="capability-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        capability_dir = root / "capabilities"
        capability_dir.mkdir(parents=True)
        external = Path(tmp) / "outside-registry.yaml"
        external.write_text(
            "- id: capability.external\n"
            "  authority: sensor_only\n"
            "  forbidden_actions: [injector]\n"
            "  source: fixture\n"
            "  license: test\n"
            "  allowed_actions: [observe]\n"
        )
        (capability_dir / "registry.yaml").symlink_to(external)
        try:
            result = run_scan(root, "capabilities")
            assert "capability.external" not in result["ids"], result
            assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        except Exception as exc:
            capability_failures.append(f"registry file symlink: {exc}")

        (capability_dir / "registry.yaml").unlink()
        os.mkfifo(capability_dir / "registry.yaml")
        try:
            result = run_scan(root, "capabilities")
            assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        except Exception as exc:
            capability_failures.append(f"registry FIFO: {exc}")

        (capability_dir / "registry.yaml").unlink()
        capability_dir.rmdir()
        external_dir = Path(tmp) / "outside-capabilities"
        external_dir.mkdir()
        (external_dir / "registry.yaml").write_text(external.read_text())
        capability_dir.symlink_to(external_dir, target_is_directory=True)
        try:
            result = run_scan(root, "capabilities")
            assert "capability.external" not in result["ids"], result
            assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        except Exception as exc:
            capability_failures.append(f"capability directory symlink: {exc}")

        capability_dir.unlink()
        capability_dir.mkdir()
        outside_classes = Path(tmp) / "outside-classes.yaml"
        outside_classes.write_text("- id: oracle\n  authority: oracle\n")
        (capability_dir / "classes.yaml").symlink_to(outside_classes)
        try:
            result = run_scan(root, "capabilities")
            assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        except Exception as exc:
            capability_failures.append(f"class file symlink: {exc}")

    assert not capability_failures, "\n".join(capability_failures)

    fixture_failures = []
    with tempfile.TemporaryDirectory(prefix="capability-fixture-e2e-") as tmp:
        root = Path(tmp) / "repo"
        fixture_dir = root / "fixtures" / "capabilities" / "_must_reject"
        fixture_dir.mkdir(parents=True)
        rejected_fixture = (
            "- id: external.fixture\n"
            "  authority: sensor_only\n"
            "  forbidden_actions: [injector]\n"
            "  source: fixture\n"
            "  license: test\n"
            "  allowed_actions: [injector]\n"
        )
        outside = Path(tmp) / "outside.yaml"
        outside.write_text(rejected_fixture)
        (fixture_dir / "external.yaml").symlink_to(outside)
        try:
            rows = run_scan(root, "capability-fixtures")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            fixture_failures.append(f"fixture file symlink: {exc}")

        (fixture_dir / "external.yaml").unlink()
        os.mkfifo(fixture_dir / "blocked.yaml")
        try:
            rows = run_scan(root, "capability-fixtures")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            fixture_failures.append(f"fixture FIFO: {exc}")

        (fixture_dir / "blocked.yaml").unlink()
        fixture_dir.rmdir()
        outside_dir = Path(tmp) / "outside-fixtures"
        outside_dir.mkdir()
        (outside_dir / "external.yaml").write_text(rejected_fixture)
        fixture_dir.symlink_to(outside_dir, target_is_directory=True)
        try:
            rows = run_scan(root, "capability-fixtures")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            fixture_failures.append(f"fixture root symlink: {exc}")

        fixture_dir.unlink()
        fixture_dir.mkdir()
        (fixture_dir / "local.yaml").write_text(rejected_fixture)
        try:
            rows = run_scan(root, "capability-fixtures")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            fixture_failures.append(f"regular fixture: {exc}")

        (fixture_dir / "local.yaml").unlink()
        fixture_dir.rmdir()
        (root / "fixtures" / "capabilities").rmdir()
        (root / "fixtures").rmdir()
        external_root = Path(tmp) / "outside-fixture-root"
        external_base = external_root / "capabilities" / "_must_reject"
        external_base.mkdir(parents=True)
        (external_base / "external.yaml").write_text(rejected_fixture)
        (root / "fixtures").symlink_to(external_root, target_is_directory=True)
        try:
            rows = run_scan(root, "capability-fixtures")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            fixture_failures.append(f"fixtures parent symlink: {exc}")

    assert not fixture_failures, "\n".join(fixture_failures)

    finding_fixture_failures = []
    with tempfile.TemporaryDirectory(prefix="finding-fixture-e2e-") as tmp:
        root = Path(tmp) / "repo"
        finding_dir = root / "fixtures" / "findings"
        finding_dir.mkdir(parents=True)
        valid_finding = {
            "id": "finding.external", "engagement": "fixture", "owasp": "LLM01",
            "surface": "chat", "objective": "benign", "scope_class": "self",
            "severity": "info", "confidence": "low", "attempt_id": "attempt-1",
            "control_attempt_id": "attempt-0", "oracle_verdict": "needs_review",
            "dedup_key": "external", "status": "unproven", "recorded_date": "2020-01-01",
        }
        outside = Path(tmp) / "outside.json"
        outside.write_text(json.dumps(valid_finding))
        (finding_dir / "external.json").symlink_to(outside)
        try:
            rows = run_scan(root, "finding-fixtures")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            finding_fixture_failures.append(f"finding file symlink: {exc}")

        (finding_dir / "external.json").unlink()
        os.mkfifo(finding_dir / "blocked.json")
        try:
            rows = run_scan(root, "finding-fixtures")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            finding_fixture_failures.append(f"top-level finding FIFO: {exc}")

        (finding_dir / "blocked.json").unlink()
        reject_dir = finding_dir / "_must_reject"
        reject_dir.mkdir()
        os.mkfifo(reject_dir / "blocked.json")
        try:
            rows = run_scan(root, "finding-fixtures")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            finding_fixture_failures.append(f"must-reject FIFO: {exc}")

        (reject_dir / "blocked.json").unlink()
        reject_dir.rmdir()
        outside_reject = Path(tmp) / "outside-must-reject"
        outside_reject.mkdir()
        (outside_reject / "external.json").write_text(json.dumps({"recorded_date": "2026-10-01"}))
        reject_dir.symlink_to(outside_reject, target_is_directory=True)
        try:
            rows = run_scan(root, "finding-fixtures")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            finding_fixture_failures.append(f"must-reject directory symlink: {exc}")

        reject_dir.unlink()
        (finding_dir / "regular.json").write_text(json.dumps(valid_finding))
        try:
            rows = run_scan(root, "finding-fixtures")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            finding_fixture_failures.append(f"regular finding fixture: {exc}")

        (finding_dir / "regular.json").unlink()
        finding_dir.rmdir()
        (root / "fixtures").rmdir()
        outside_fixtures = Path(tmp) / "outside-fixtures"
        outside_findings = outside_fixtures / "findings"
        outside_findings.mkdir(parents=True)
        (outside_findings / "external.json").write_text(json.dumps(valid_finding))
        (root / "fixtures").symlink_to(outside_fixtures, target_is_directory=True)
        try:
            rows = run_scan(root, "finding-fixtures")
            assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            finding_fixture_failures.append(f"finding corpus root symlink: {exc}")

    assert not finding_fixture_failures, "\n".join(finding_fixture_failures)

    family_failures = []
    with tempfile.TemporaryDirectory(prefix="tool-family-e2e-") as tmp:
        root = Path(tmp) / "repo"
        family_dir = root / "tool-families" / "st3gg"
        family_dir.mkdir(parents=True)
        valid_manifest = (
            "family_id: st3gg\n"
            "reviewed_commit: abc123\n"
            "license: MIT\n"
            "integration: detection-only\n"
            "allowed_actions: [observe]\n"
        )
        outside_manifest = Path(tmp) / "outside-manifest.yaml"
        outside_manifest.write_text(valid_manifest)
        (family_dir / "manifest.yaml").symlink_to(outside_manifest)
        try:
            rows = run_scan(root, "tool-families")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            family_failures.append(f"family manifest symlink: {exc}")

        (family_dir / "manifest.yaml").unlink()
        (family_dir / "manifest.yaml").write_text(valid_manifest)
        outside_agent = Path(tmp) / "outside-agent.md"
        outside_agent.write_text("Plane 1/2 does not store raw payloads.\n")
        (family_dir / "AGENT.md").symlink_to(outside_agent)
        try:
            rows = run_scan(root, "tool-families")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            family_failures.append(f"family guidance symlink: {exc}")

        (family_dir / "AGENT.md").unlink()
        fixture_dir = root / "fixtures" / "tool-families" / "_must_reject"
        fixture_dir.mkdir(parents=True)
        outside_fixture = Path(tmp) / "outside-family-fixture.yaml"
        outside_fixture.write_text("not a valid family manifest\n")
        (fixture_dir / "external.yaml").symlink_to(outside_fixture)
        try:
            rows = run_scan(root, "tool-families")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            family_failures.append(f"must-reject fixture symlink: {exc}")

        (fixture_dir / "external.yaml").unlink()
        os.mkfifo(fixture_dir / "blocked.yaml")
        try:
            rows = run_scan(root, "tool-families")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            family_failures.append(f"must-reject fixture FIFO: {exc}")

        (fixture_dir / "blocked.yaml").unlink()
        fixture_dir.rmdir()
        outside_corpus = Path(tmp) / "outside-family-corpus"
        outside_corpus.mkdir()
        (outside_corpus / "external.yaml").write_text("not a valid family manifest\n")
        fixture_dir.symlink_to(outside_corpus, target_is_directory=True)
        try:
            rows = run_scan(root, "tool-families")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            family_failures.append(f"must-reject corpus symlink: {exc}")

        outside_families = Path(tmp) / "outside-families"
        outside_family = outside_families / "st3gg"
        outside_family.mkdir(parents=True)
        (outside_family / "manifest.yaml").write_text(valid_manifest)
        (root / "tool-families").rename(root / "tool-families-saved")
        (root / "tool-families").symlink_to(outside_families, target_is_directory=True)
        try:
            rows = run_scan(root, "tool-families")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            family_failures.append(f"tool-families root symlink: {exc}")

    assert not family_failures, "\n".join(family_failures)

    proposal_failures = []
    with tempfile.TemporaryDirectory(prefix="payload-proposal-e2e-") as tmp:
        root = Path(tmp) / "repo"
        proposal_dir = root / "fixtures" / "payload-proposals"
        proposal_dir.mkdir(parents=True)
        valid_proposal = {
            "objective_id": "obj.safe", "payload_class": "text_prompt", "risk_tier": "benign_canary",
            "approved_objective_ref": "scope#objective", "generator_capability_id": "generator.safe",
            "artifact_metadata": {}, "required_controls": ["scope"], "containment_plan": "local",
            "cleanup_plan": "delete", "non_authority_attestation": {
                "proposal_only": True, "executes_nothing": True, "emits_no_verdict": True,
            },
        }
        outside = Path(tmp) / "outside-proposal.json"
        outside.write_text(json.dumps(valid_proposal))
        (proposal_dir / "external.json").symlink_to(outside)
        try:
            rows = run_scan(root, "payload-proposals")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            proposal_failures.append(f"proposal file symlink: {exc}")

        (proposal_dir / "external.json").unlink()
        os.mkfifo(proposal_dir / "blocked.json")
        try:
            rows = run_scan(root, "payload-proposals")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            proposal_failures.append(f"top-level proposal FIFO: {exc}")

        (proposal_dir / "blocked.json").unlink()
        reject_dir = proposal_dir / "_must_reject"
        reject_dir.mkdir()
        os.mkfifo(reject_dir / "blocked.json")
        try:
            rows = run_scan(root, "payload-proposals")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            proposal_failures.append(f"must-reject FIFO: {exc}")

        (reject_dir / "blocked.json").unlink()
        reject_dir.rmdir()
        outside_reject = Path(tmp) / "outside-proposal-rejects"
        outside_reject.mkdir()
        (outside_reject / "external.json").write_text("{}\n")
        reject_dir.symlink_to(outside_reject, target_is_directory=True)
        try:
            rows = run_scan(root, "payload-proposals")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            proposal_failures.append(f"must-reject directory symlink: {exc}")

        reject_dir.unlink()
        (proposal_dir / "regular.json").write_text(json.dumps(valid_proposal))
        (reject_dir := proposal_dir / "_must_reject").mkdir()
        (reject_dir / "invalid.json").write_text("{}\n")
        try:
            rows = run_scan(root, "payload-proposals")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            proposal_failures.append(f"regular proposal fixtures: {exc}")

        (proposal_dir / "regular.json").unlink()
        (reject_dir / "invalid.json").unlink()
        reject_dir.rmdir()
        proposal_dir.rmdir()
        (root / "fixtures").rmdir()
        outside_fixtures = Path(tmp) / "outside-proposal-fixtures"
        outside_proposals = outside_fixtures / "payload-proposals"
        outside_proposals.mkdir(parents=True)
        (outside_proposals / "external.json").write_text(json.dumps(valid_proposal))
        (root / "fixtures").symlink_to(outside_fixtures, target_is_directory=True)
        try:
            rows = run_scan(root, "payload-proposals")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            proposal_failures.append(f"fixture root symlink: {exc}")

    assert not proposal_failures, "\n".join(proposal_failures)

    static_corpus_failures = []
    with tempfile.TemporaryDirectory(prefix="static-corpus-e2e-") as tmp:
        root = Path(tmp) / "repo"
        false_dir = root / "fixtures" / "false-discovery"
        adversarial_dir = root / "fixtures" / "adversarial-candidates"
        false_dir.mkdir(parents=True)
        adversarial_dir.mkdir(parents=True)
        valid_false = {"entries": [{
            "id": "trap-1", "trap_class": "missing-control", "observation": "observation",
            "correct_verdict": "needs_review", "missing_control": "oracle", "why": "control absent",
        }]}
        valid_adversarial = {"entries": [
            {"id": "additive", "expected_disposition": "retain", "touches_immutable": False},
            {"id": "gaming", "expected_disposition": "block", "touches_immutable": True},
        ]}
        outside_false = Path(tmp) / "outside-false.json"
        outside_false.write_text(json.dumps(valid_false))
        outside_adversarial = Path(tmp) / "outside-adversarial.json"
        outside_adversarial.write_text(json.dumps(valid_adversarial))
        (false_dir / "corpus.json").symlink_to(outside_false)
        (adversarial_dir / "corpus.json").symlink_to(outside_adversarial)
        try:
            rows = run_scan(root, "static-corpora")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            static_corpus_failures.append(f"corpus file symlinks: {exc}")

        (false_dir / "corpus.json").unlink()
        (adversarial_dir / "corpus.json").unlink()
        os.mkfifo(false_dir / "corpus.json")
        os.mkfifo(adversarial_dir / "corpus.json")
        try:
            rows = run_scan(root, "static-corpora")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            static_corpus_failures.append(f"corpus FIFOs: {exc}")

        (false_dir / "corpus.json").unlink()
        (adversarial_dir / "corpus.json").unlink()
        (false_dir / "corpus.json").write_text(json.dumps(valid_false))
        (adversarial_dir / "corpus.json").write_text(json.dumps(valid_adversarial))
        try:
            rows = run_scan(root, "static-corpora")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            static_corpus_failures.append(f"regular corpora: {exc}")

    assert not static_corpus_failures, "\n".join(static_corpus_failures)

    packet_failures = []
    with tempfile.TemporaryDirectory(prefix="framing-probe-e2e-") as tmp:
        root = Path(tmp) / "repo"
        packet_dir = root / "fixtures" / "framing-probe" / "packets-v2"
        packet_dir.mkdir(parents=True)
        body = "Sanitized evidence without a severity label."
        packet = {"finding_id": "F-TEST", "body": body,
                  "body_sha256": hashlib.sha256(body.encode()).hexdigest()}
        outside = Path(tmp) / "outside.packet.json"
        outside.write_text(json.dumps(packet))
        (packet_dir / "external.packet.json").symlink_to(outside)
        try:
            rows = run_scan(root, "framing-probe")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            packet_failures.append(f"packet file symlink: {exc}")

        (packet_dir / "external.packet.json").unlink()
        os.mkfifo(packet_dir / "blocked.packet.json")
        try:
            rows = run_scan(root, "framing-probe")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            packet_failures.append(f"packet FIFO: {exc}")

        (packet_dir / "blocked.packet.json").unlink()
        packet_dir.rmdir()
        outside_packets = Path(tmp) / "outside-packets"
        outside_packets.mkdir()
        for index in range(3):
            data = dict(packet, finding_id=f"F-OUTSIDE-{index}")
            (outside_packets / f"{index}.packet.json").write_text(json.dumps(data))
        packet_dir.symlink_to(outside_packets, target_is_directory=True)
        try:
            rows = run_scan(root, "framing-probe")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            packet_failures.append(f"packet directory symlink: {exc}")

        packet_dir.unlink()
        packet_dir.mkdir()
        for index in range(3):
            data = dict(packet, finding_id=f"F-LOCAL-{index}")
            (packet_dir / f"{index}.packet.json").write_text(json.dumps(data))
        try:
            rows = run_scan(root, "framing-probe")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            packet_failures.append(f"regular packets: {exc}")

    assert not packet_failures, "\n".join(packet_failures)

    intervention_failures = []
    with tempfile.TemporaryDirectory(prefix="intervention-ledger-e2e-") as tmp:
        root = Path(tmp) / "repo"
        ledger_dir = root / "fixtures" / "interventions"
        ledger_dir.mkdir(parents=True)
        valid_ledger = {"method": "controlled fixture", "entries": [{
            "intervention_id": "I-1", "source_refs": [{"quote": "Observed operator action."}],
            "provenance": "live",
        }]}
        outside = Path(tmp) / "outside-ledger.json"
        outside.write_text(json.dumps(valid_ledger))
        (ledger_dir / "external.json").symlink_to(outside)
        try:
            rows = run_scan(root, "interventions")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            intervention_failures.append(f"ledger file symlink: {exc}")

        (ledger_dir / "external.json").unlink()
        os.mkfifo(ledger_dir / "blocked.json")
        try:
            rows = run_scan(root, "interventions")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            intervention_failures.append(f"ledger FIFO: {exc}")

        (ledger_dir / "blocked.json").unlink()
        (ledger_dir / "regular.json").write_text(json.dumps(valid_ledger))
        try:
            rows = run_scan(root, "interventions")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            intervention_failures.append(f"regular ledger: {exc}")

        (ledger_dir / "regular.json").unlink()
        ledger_dir.rmdir()
        (root / "fixtures").rmdir()
        outside_fixtures = Path(tmp) / "outside-fixtures"
        outside_ledger = outside_fixtures / "interventions"
        outside_ledger.mkdir(parents=True)
        (outside_ledger / "external.json").write_text(json.dumps(valid_ledger))
        (root / "fixtures").symlink_to(outside_fixtures, target_is_directory=True)
        try:
            rows = run_scan(root, "interventions")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            intervention_failures.append(f"fixtures root symlink: {exc}")

    assert not intervention_failures, "\n".join(intervention_failures)

    card_failures = []
    with tempfile.TemporaryDirectory(prefix="card-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        patterns = root / "skills" / "patterns"
        patterns.mkdir(parents=True)

        fifo_dir = patterns / "fifo-card"
        fifo_dir.mkdir()
        os.mkfifo(fifo_dir / "SKILL.md")
        try:
            result = run_scan(root, "cards")
            rows = result["rows"]
            assert any(not row[0] and "unsafe" in row[2] for row in rows), result
        except Exception as exc:
            card_failures.append(f"FIFO card: {exc}")
        (fifo_dir / "SKILL.md").unlink()
        fifo_dir.rmdir()

        card = "---\nid: pattern.external\ntype: pattern\nactivation:\n  strong: evidence\n  weak: signal\n  negative: control\n---\n"
        outside = Path(tmp) / "outside.md"
        outside.write_text(card)
        leaf_dir = patterns / "leaf-link"
        leaf_dir.mkdir()
        leaf = leaf_dir / "SKILL.md"
        leaf.symlink_to(outside)
        try:
            result = run_scan(root, "cards")
            assert "pattern.external" not in result["ids"], result
            assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        except Exception as exc:
            card_failures.append(f"card file symlink: {exc}")
        leaf.unlink()
        leaf_dir.rmdir()

        outside_dir = Path(tmp) / "outside-card-dir"
        outside_dir.mkdir()
        (outside_dir / "SKILL.md").write_text(card)
        dir_link = patterns / "dir-link"
        dir_link.symlink_to(outside_dir, target_is_directory=True)
        try:
            result = run_scan(root, "cards")
            assert "pattern.external" not in result["ids"], result
            assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        except Exception as exc:
            card_failures.append(f"card directory symlink: {exc}")
        dir_link.unlink()

        regular_dir = patterns / "regular-card"
        regular_dir.mkdir()
        (regular_dir / "SKILL.md").write_text(card.replace("pattern.external", "pattern.regular"))
        try:
            result = run_scan(root, "cards")
            assert "pattern.regular" in result["ids"], result
            assert all(row[0] for row in result["rows"]), result
        except Exception as exc:
            card_failures.append(f"regular pattern card: {exc}")

    with tempfile.TemporaryDirectory(prefix="card-root-symlink-e2e-") as tmp:
        root = Path(tmp) / "repo"
        skills = root / "skills"
        skills.mkdir(parents=True)
        outside = Path(tmp) / "outside-patterns"
        outside.mkdir()
        (outside / "external").mkdir()
        (outside / "external" / "SKILL.md").write_text(
            "---\nid: pattern.external\ntype: pattern\nactivation:\n  strong: x\n  weak: y\n  negative: z\n---\n"
        )
        (skills / "patterns").symlink_to(outside, target_is_directory=True)
        result = run_scan(root, "cards")
        assert "pattern.external" not in result["ids"], result
        assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result

    with tempfile.TemporaryDirectory(prefix="skills-root-symlink-e2e-") as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        outside = Path(tmp) / "outside-skills"
        patterns = outside / "patterns" / "external"
        patterns.mkdir(parents=True)
        (patterns / "SKILL.md").write_text(
            "---\nid: pattern.external\ntype: pattern\nactivation:\n  strong: x\n  weak: y\n  negative: z\n---\n"
        )
        oracles = outside / "oracles"
        oracles.mkdir()
        (oracles / "external.md").write_text("---\nid: oracle.external\ntype: oracle\n---\n")
        (root / "skills").symlink_to(outside, target_is_directory=True)
        result = run_scan(root, "cards")
        assert "pattern.external" not in result["ids"], result
        assert any(not row[0] and "unsafe" in row[2] for row in result["rows"]), result
        rows = run_scan(root, "oracles")
        assert rows and any(not row[0] and "unsafe" in row[2] for row in rows), rows

    assert not card_failures, "\n".join(card_failures)

    casebook_failures = []
    with tempfile.TemporaryDirectory(prefix="casebook-scan-e2e-") as tmp:
        root = Path(tmp) / "repo"
        casebooks = root / "casebooks"
        casebooks.mkdir(parents=True)

        fifo_dir = casebooks / "fifo-book"
        fifo_dir.mkdir()
        os.mkfifo(fifo_dir / "refs.md")
        try:
            rows = run_scan(root, "casebooks")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            casebook_failures.append(f"FIFO casebook: {exc}")
        (fifo_dir / "refs.md").unlink()
        fifo_dir.rmdir()

        outside_file = Path(tmp) / "outside-refs.md"
        outside_file.write_text("pattern.safe")
        file_link_dir = casebooks / "file-link"
        file_link_dir.mkdir()
        file_link = file_link_dir / "refs.md"
        file_link.symlink_to(outside_file)
        try:
            rows = run_scan(root, "casebooks")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            casebook_failures.append(f"casebook file symlink: {exc}")
        file_link.unlink()
        file_link_dir.rmdir()

        outside_dir = Path(tmp) / "outside-casebook"
        outside_dir.mkdir()
        (outside_dir / "refs.md").write_text("pattern.safe")
        dir_link = casebooks / "dir-link"
        dir_link.symlink_to(outside_dir, target_is_directory=True)
        try:
            rows = run_scan(root, "casebooks")
            assert any(not row[0] and "unsafe" in row[2] for row in rows), rows
        except Exception as exc:
            casebook_failures.append(f"casebook directory symlink: {exc}")
        dir_link.unlink()

        regular = casebooks / "regular-book"
        regular.mkdir()
        (regular / "refs.md").write_text("pattern.safe")
        try:
            rows = run_scan(root, "casebooks")
            assert rows and all(row[0] for row in rows), rows
        except Exception as exc:
            casebook_failures.append(f"regular casebook: {exc}")

    with tempfile.TemporaryDirectory(prefix="casebook-root-symlink-e2e-") as tmp:
        root = Path(tmp) / "repo"
        outside = Path(tmp) / "outside-casebooks"
        outside.mkdir()
        (outside / "external").mkdir()
        (outside / "external" / "refs.md").write_text("pattern.safe")
        root.mkdir()
        (root / "casebooks").symlink_to(outside, target_is_directory=True)
        rows = run_scan(root, "casebooks")
        assert any(not row[0] and "unsafe" in row[2] for row in rows), rows

    assert not casebook_failures, "\n".join(casebook_failures)
    print("conformance filesystem E2E passed (secret, oracle, card, casebook, capability, finding, payload, static, framing, intervention, and tool-family scans)")


if __name__ == "__main__":
    main()
