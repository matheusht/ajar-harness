#!/usr/bin/env python3
"""Prove optimized Python and symlinks cannot bypass no-write-under-skills guards."""

import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lifecycle_blocks(path):
    module = load_module("lifecycle_guard_test", "run-experiment-lifecycle.py")
    generated = []
    module.GR.generate = lambda campaign_path, **kwargs: generated.append(campaign_path)
    module.GR.behavioral_bridge = lambda *args, **kwargs: {}
    module.GR.render_all_promotions = lambda *args, **kwargs: 0
    module.GR.write_candidate_scores = lambda *args, **kwargs: None
    module.GR.discover_campaign_candidates = lambda *args, **kwargs: []
    module.load = lambda *args, **kwargs: {"campaign_id": "guard-test"}
    module.write_json = lambda *args, **kwargs: None
    try:
        module.run_lifecycle(path)
    except ValueError as exc:
        return "skills" in str(exc) and not generated
    return False


def renderer_blocks(path):
    module = load_module("renderer_guard_test", "render-promotion-bundle.py")
    output_attempts = []
    module.load = lambda value: (
        {"candidates": [{"candidate_id": "c"}], "baseline_scoreboard": {}}
        if value.endswith("report.json") else {}
    )
    module.read = lambda value: ""
    module._head_commit = lambda: "base"
    module.sha256_file = lambda value: "0" * 64
    module._benchmark_version = lambda campaign: "bench"
    module.APE.materialize_candidate = lambda *args: {}
    module.APE.materialization_summary = lambda result: {}
    module.build_bundle = lambda *args, **kwargs: ({}, True, {})
    module.validate_bundle = lambda bundle: []
    module.render_md = lambda *args: ""
    module.render_pr_body = lambda *args: ""
    original_makedirs = os.makedirs

    def capture_output(path, *args, **kwargs):
        output_attempts.append(path)
        raise OSError("test intercepted output")

    os.makedirs = capture_output
    try:
        try:
            module.render_cli(path, "c")
        except ValueError as exc:
            return "skills" in str(exc) and not output_attempts
        except OSError:
            return False
    finally:
        os.makedirs = original_makedirs
    return False


def main():
    with tempfile.TemporaryDirectory(prefix="skills-path-guard-") as temp:
        alias = os.path.join(temp, "skill-alias")
        os.symlink(os.path.join(ROOT, "skills"), alias)
        cases = (
            ("lifecycle optimized direct", lifecycle_blocks,
             os.path.join(ROOT, "skills", "guard-test", "campaign.json")),
            ("lifecycle optimized symlink", lifecycle_blocks,
             os.path.join(alias, "guard-test", "campaign.json")),
            ("lifecycle optimized case alias", lifecycle_blocks,
             os.path.join(ROOT, "SKILLS", "guard-test", "campaign.json")),
            ("renderer optimized direct", renderer_blocks,
             os.path.join(ROOT, "skills", "guard-test", "campaign.json")),
            ("renderer optimized symlink", renderer_blocks,
             os.path.join(alias, "guard-test", "campaign.json")),
            ("renderer optimized case alias", renderer_blocks,
             os.path.join(ROOT, "SKILLS", "guard-test", "campaign.json")),
        )
        failures = []
        for label, check, path in cases:
            passed = check(path)
            print(f"{'ok' if passed else 'FAIL'} {label}: {'blocked' if passed else 'guard bypassed'}")
            if not passed:
                failures.append(label)
        if failures:
            return 1
    print("SKILLS PATH GUARDS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
