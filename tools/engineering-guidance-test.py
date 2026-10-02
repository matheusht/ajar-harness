#!/usr/bin/env python3
"""Public-command regressions for #107, using only temporary documentation and pins."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="engineering-guidance-") as directory:
        root = Path(directory)
        for name in (
            "tools/check-conformance.py", "tools/overlay_pins.py", "README.md", "AGENTS.md",
            "CLAUDE.md", "docs/architecture.md", "docs/decisions/README.md", "docs/wiki/index.md",
            "docs/decision-0005-implementation-architecture.md",
        ):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        env = dict(os.environ, PYTHONPATH=str(ROOT / "tools"), PYTHONDONTWRITEBYTECODE="1")

        def run(tool, *args, code=0, contains=""):
            result = subprocess.run([sys.executable, str(root / "tools" / tool), *args],
                                    cwd=root, env=env, capture_output=True, text=True)
            assert result.returncode == code, result.stdout + result.stderr
            assert contains in result.stdout, result.stdout
            return result.stdout

        def guidance(**kwargs):
            return run("check-conformance.py", "--engineering-guidance", **kwargs)

        guidance(contains="0 failing")
        index = root / "docs/decisions/README.md"
        index.unlink()
        guidance(code=1, contains="FAIL guidance/")
        shutil.copyfile(ROOT / "docs/decisions/README.md", index)
        agents = root / "AGENTS.md"
        original = agents.read_bytes()
        agents.write_bytes(original + b"\nmirror drift\n")
        guidance(code=1, contains="FAIL AGENTS.md is byte-identical")
        agents.write_bytes(original)
        for name in ("AGENTS.md", "CLAUDE.md"):
            (root / name).write_bytes(original + b"\nSee `docs/agents/domain.md`.\n")
        guidance(code=1, contains="FAIL guidance/AGENTS.md: absent setup reference")
        for name in ("AGENTS.md", "CLAUDE.md"):
            (root / name).write_bytes(original)
        # A dated historical scaffold description is not a current-navigation failure.
        with (root / "docs/architecture.md").open("a") as handle:
            handle.write("\nHistorical observation (2026-01-01): v0 scaffold.\n")
        guidance(contains="0 failing")

        prereg = root / "evals/synthetic/preregistration.json"
        prereg.parent.mkdir(parents=True)
        doc = {"status": "draft_not_authorized", "execution_authorized": False,
               "common_safety_overlay": {"files": [{"path": "AGENTS.md", "sha256": "sha256:old"}]}}
        prereg.write_text(json.dumps(doc))
        draft = json.loads(run("overlay_pins.py", "check", "--json"))
        assert (draft["stale"], draft["failures"]) == (1, 0)
        guidance(code=1, contains="1 stale pin(s) reported")
        run("overlay_pins.py", "repin", "--apply", contains="refreshed 1 pin(s)")
        refreshed = json.loads(prereg.read_text())
        assert refreshed["common_safety_overlay"]["files"][0]["sha256"] == "sha256:" + hashlib.sha256(original).hexdigest()
        assert refreshed["execution_authorized"] is False
        guidance(contains="0 failing")
        doc["execution_authorized"] = True
        prereg.write_text(json.dumps(doc))
        before = prereg.read_bytes()
        frozen = json.loads(run("overlay_pins.py", "check", "--json", code=1))
        assert (frozen["stale"], frozen["failures"]) == (0, 1)
        guidance(code=1, contains="authorized record's pins are intact")
        run("overlay_pins.py", "repin", "--apply", code=1, contains="REFUSING")
        assert prereg.read_bytes() == before
        prereg.unlink()

        outside = root.parent / f"{root.name}-outside.txt"
        outside.write_text("external pin target\n")
        try:
            link = root / "outside-link.txt"
            link.symlink_to(outside)
            hardlink = root / "outside-hardlink.txt"
            hardlink.hardlink_to(outside)
            digest = "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest()
            escaped_paths = [os.path.relpath(outside, root), str(outside), "outside-link.txt",
                             "outside-hardlink.txt"]
            escaped_prereg = root / "evals/synthetic/escape/preregistration.json"
            escaped_prereg.parent.mkdir(parents=True)
            escaped_doc = {"status": "frozen", "execution_authorized": True,
                           "common_safety_overlay": {"files": [{"path": p, "sha256": digest} for p in escaped_paths]}}
            escaped_prereg.write_text(json.dumps(escaped_doc))
            checked = subprocess.run([sys.executable, str(root / "tools/overlay_pins.py"), "check", "--json"],
                                      cwd=root, env=env, capture_output=True, text=True)
            checked_doc = json.loads(checked.stdout)
            escaped_rows = next(r["rows"] for r in checked_doc["results"]
                                if r["preregistration"] == "evals/synthetic/escape/preregistration.json")
            assert all(r["actual"] is None and r["state"] == "missing" for r in escaped_rows), (checked.stdout, checked.stderr)

            escaped_doc["execution_authorized"] = False
            escaped_doc["common_safety_overlay"]["files"][0]["sha256"] = "sha256:old"
            escaped_prereg.write_text(json.dumps(escaped_doc))
            before = escaped_prereg.read_bytes()
            run("overlay_pins.py", "repin", "--apply", code=1, contains="no longer exist")
            assert escaped_prereg.read_bytes() == before

            # Discovery must not follow a preregistration symlink outside the repository.
            escaped_prereg.unlink()
            outside_prereg = root.parent / f"{root.name}-outside-preregistration.json"
            outside_prereg.write_text(json.dumps({
                "status": "draft_not_authorized", "execution_authorized": False,
                "common_safety_overlay": {"files": [{"path": "AGENTS.md", "sha256": "sha256:old"}]},
            }))
            prereg_link = root / "evals/synthetic/link/preregistration.json"
            prereg_link.parent.mkdir(parents=True)
            prereg_link.symlink_to(outside_prereg)
            outside_before = outside_prereg.read_bytes()
            run("overlay_pins.py", "repin", "--apply", contains="nothing to refresh")
            assert outside_prereg.read_bytes() == outside_before
            prereg_link.unlink()
            outside_prereg.write_text(json.dumps({
                "status": "draft_not_authorized", "execution_authorized": False,
                "common_safety_overlay": {"files": [{"path": "AGENTS.md", "sha256": "sha256:old"}]},
            }))
            prereg_link.hardlink_to(outside_prereg)
            outside_before = outside_prereg.read_bytes()
            run("overlay_pins.py", "repin", "--apply", contains="nothing to refresh")
            assert outside_prereg.read_bytes() == outside_before
        finally:
            outside.unlink(missing_ok=True)
            (root.parent / f"{root.name}-outside-preregistration.json").unlink(missing_ok=True)
    print("engineering guidance: public CLI navigation, mirror, history and draft/frozen pin controls passed")


if __name__ == "__main__":
    main()
