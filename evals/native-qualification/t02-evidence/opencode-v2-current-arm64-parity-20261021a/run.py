#!/usr/bin/env python3
"""Repeat the local arm64, two-arm Kanboard app check under the current V2 image."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import observer_case as case  # noqa: E402

IMAGE = "nq-kanboard-current:arm64-20261021"
IMAGE_ID = "sha256:76bd7fcb18d052bd7bd744db6ce0db324c78210de8c5c52433bce6f27aecb513"
PINS = {
    "Dockerfile.opencode-kanboard-runtime": "7a1ab9b257fb36a216fc1baafabc757436d0a15ffcb9498b6fbe697da3a9bf4b",
    "observer_case.py": "72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf",
    "RESEARCHER-BRIEF.md": "8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a",
    "observer-evidence-final/observer-results.json": "9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, required=True, help="directory with pinned vulnerable.tar.gz and fixed.tar.gz")
    parser.add_argument("--output", type=Path, required=True, help="new private directory outside the repository")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(HERE.parent.parent):
        parser.error("output must be outside the repository")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "evidence").mkdir(mode=0o700)
    report = {"classification": "offline current-Dockerfile arm64 app parity; no model/provider calls",
              "status": "running", "image": IMAGE, "image_id": IMAGE_ID, "checks": [],
              "source_sha256": {name: sha(HERE / name) for name in PINS}}

    def check(name, passed):
        report["checks"].append({"name": name, "pass": bool(passed)})
        if not passed:
            raise RuntimeError(name)

    try:
        check("frozen source and T01 receipt", all(report["source_sha256"][name] == digest for name, digest in PINS.items()))
        image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True))[0]
        check("exact local arm64 image", image["Id"] == IMAGE_ID and image["Architecture"] == "arm64")
        def in_image(entrypoint, *command):
            return subprocess.check_output(["docker", "run", "--rm", "--pull", "never", "--network", "none",
                                            "--entrypoint", entrypoint, IMAGE, *command], text=True)
        version = in_image("php", "-v").splitlines()[0]
        modules = {line.lower() for line in in_image("php", "-m").splitlines()}
        check("PHP 8.4.26 and OpenCode V2", version.startswith("PHP 8.4.26 ")
              and {"gd", "pdo_sqlite"} <= modules and in_image("opencode", "--version").strip() == "opencode v2.0.32")
        for label, (_, digest) in case.PINS.items():
            archive = args.archives / (label + ".tar.gz")
            check(label + " archive hash", archive.is_file() and sha(archive) == digest)
            shutil.copy2(archive, output / archive.name)

        case.PHP_IMAGE = IMAGE
        case.PHP_IMAGE_DIGEST = IMAGE + "@" + IMAGE_ID
        summaries = []
        for label, (commit, digest) in case.PINS.items():
            source = case.prepare_source(output, label, commit, digest)
            with tempfile.TemporaryDirectory(prefix=label + "-run-", dir=output) as temporary:
                run_dir = Path(temporary)
                summary = case.run_arm(label, source, run_dir, output / "evidence", True)
            summary["cleanup"].update({"run_dir_absent": not run_dir.exists(),
                                       "db_absent": not (run_dir / "app/data/db.sqlite").exists()})
            summary.update({"commit": commit, "archive_sha256": digest})
            summaries.append(summary)
            check(label + " exact cleanup", all(summary["cleanup"][key] for key in
                  ("container_absent", "port_closed", "run_dir_absent", "db_absent")))

        old = json.loads((HERE / "observer-evidence-final/observer-results.json").read_text())
        keys = ("release", "loopback", "project_id", "swimlane_id", "authorized_project",
                "authorized_swimlane", "private_project_control", "cross_role_read", "commit", "archive_sha256")
        check("both arms match T01 app outcomes", len(summaries) == len(old["arms"]) == 2 and all(
              {key: arm[key] for key in keys} == {key: prior[key] for key in keys}
              for arm, prior in zip(summaries, old["arms"])))
        check("both arms use current local image", all(arm["runtime"] == IMAGE + "@" + IMAGE_ID
              and arm["php"].startswith("PHP 8.4.26 ") for arm in summaries))
        report["arms"] = summaries
        report["status"] = "pass"
    except Exception as error:
        report["status"] = "fail"
        report["error"] = type(error).__name__ + ": " + str(error)
    (output / "result.private.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "output": str(output)}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
