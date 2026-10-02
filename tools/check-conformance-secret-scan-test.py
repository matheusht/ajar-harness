#!/usr/bin/env python3
"""E2E checks that conformance scans reject hostile filesystem entries."""
import contextlib
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
    print("conformance filesystem E2E passed (secret, oracle, card, casebook, capability, and fixture scans)")


if __name__ == "__main__":
    main()
