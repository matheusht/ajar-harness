#!/usr/bin/env python3
"""Hash the frozen inputs of a GEPA campaign (Phase 2 helper).

Every input that affects acceptance — routing gold, crosswalk, false-discovery / adversarial corpora,
hermetic targets, the scorers themselves — is hashed into the campaign manifest's `frozen_inputs`
block. tools/check-campaign.py recomputes those hashes and BLOCKS on drift, so this helper is how you
freeze a campaign and how CI proves the benchmark wasn't tampered with mid-run.

Usage:
  python3 tools/hash-campaign-inputs.py <path> [<path> ...]   # emit a frozen_inputs JSON block
  python3 tools/hash-campaign-inputs.py --check <campaign.json> # re-hash, report drift (exit 1 on drift)
  python3 tools/hash-campaign-inputs.py --self-test
"""

import json
import os
import sys
import tempfile

from frozen_inputs import check_manifest, sha256_file
from frozen_inputs import emit as emit_frozen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def emit(paths):
    return emit_frozen(paths, ROOT)


def check(campaign_path):
    drift = check_manifest(campaign_path)
    for d in drift:
        print(f"  DRIFT {d}")
    print("frozen inputs:", "DRIFT" if drift else "intact")
    return 1 if drift else 0


def self_test():
    ok = True
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "x.json")
        with open(f, "w") as handle:
            handle.write('{"a":1}\n')
        h1 = sha256_file(f)
        h2 = sha256_file(f)
        if h1 != h2:
            ok = False
            print("[self-test] hash not stable")
        with open(f, "w") as handle:
            handle.write('{"a":2}\n')
        if sha256_file(f) == h1:
            ok = False
            print("[self-test] hash did not change on edit")
        legacy_manifest = os.path.join(d, "legacy-campaign.json")
        legacy_input = os.path.join(ROOT, "requirements-ci.txt")
        document = {
            "frozen_inputs": {
                "requirements-ci": {
                    "path": "requirements-ci.txt",
                    "sha256": sha256_file(legacy_input),
                }
            }
        }
        with open(legacy_manifest, "w") as handle:
            json.dump(document, handle)
        if check_manifest(legacy_manifest):
            ok = False
            print("[self-test] repository-relative legacy manifest did not verify")
        document["frozen_inputs"]["requirements-ci"]["sha256"] = "0" * 64
        with open(legacy_manifest, "w") as handle:
            json.dump(document, handle)
        if not check_manifest(legacy_manifest):
            ok = False
            print("[self-test] legacy manifest drift was not detected")
    print("[self-test] hash stable + change-sensitive:", "ok" if ok else "FAIL")
    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if len(argv) == 2 and argv[1] == "--self-test":
        return self_test()
    if len(argv) == 3 and argv[1] == "--check":
        return check(argv[2])
    if len(argv) >= 2:
        print(json.dumps(emit(argv[1:]), indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
