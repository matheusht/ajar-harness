"""End-to-end regression for exact archived secret-shaped fixture exceptions."""

import importlib.util
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO / "tools" / "check-conformance.py"
ARCHIVES = (
    "evals/native-qualification/team-evidence/linux-native-request-diagnostics-20261114/diagnostic-e2e.py",
    "evals/native-qualification/team-evidence/linux-startup-diagnostics-20261114/diagnostic-e2e.py",
    "evals/native-qualification/team-evidence/linux-native-preflight-20261114/installer-diagnostic-e2e.py",
)


def load_checker():
    sys.path.insert(0, str(CHECKER_PATH.parent))
    spec = importlib.util.spec_from_file_location("conformance_checker", CHECKER_PATH)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def run_case(checker, files, expected_clean):
    with tempfile.TemporaryDirectory() as root:
        for relative, content in files.items():
            path = Path(root) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        checker.ROOT = root
        checker.FAILS.clear()
        checker.CHECKS = 0
        checker.check_secrets()
        assert bool(checker.FAILS) is not expected_clean, checker.FAILS


def main():
    checker = load_checker()
    originals = {relative: (REPO / relative).read_bytes() for relative in ARCHIVES}

    # The three unchanged historical records are the only expected clean corpus.
    run_case(checker, originals, True)

    request = ARCHIVES[0]
    token = b"Bearer diagnostic-private-canary"
    run_case(checker, {request: originals[request], "evals/other.py": token}, False)
    run_case(checker, {request: originals[request] + b"\n# modified\n"}, False)
    run_case(checker, {request: originals[request] + b"\nBearer newly-added-private-token\n"}, False)
    run_case(checker, {"evals/other.py": b"user_ABCDEFGHIJKLMNOPQRSTUVWXYZ"}, False)
    print("secret scanner archived allowlist E2E passed")


if __name__ == "__main__":
    main()
