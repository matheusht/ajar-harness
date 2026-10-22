#!/usr/bin/env python3
"""Provider-free T01 source and broker protocol checks; never starts Kanboard."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PINS = {
    "jsonrpc.php": "fe930f53e4a7c264249f3cb1629788ce4362112b2aef6226a42dfc0197aeff84",
    "app/Api/Middleware/AuthenticationMiddleware.php": "b58767b343bcbfaa1d9ae461cf39dc72e7f489ba3899dea2246541153bdd3c4f",
    "app/Api/Procedure/MeProcedure.php": "70b879a3e98bd92c7e28b52d401f74fd1b857d0cbc699ec57928a5323691d3d0",
    "app/Api/Procedure/SwimlaneProcedure.php": "0bdaf617b9b26f9ca4bc21766b08ae5989a858bfc4d991d8899f01b24332ac16",
    "app/Api/Authorization/ProjectAuthorization.php": "e05d0f980eaed023e5a8b118c888b67768a4384c8e58203b5131aac13c5b8591",
}
SOURCE_MANIFEST = "5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    inventory = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source).as_posix()
        if path.is_symlink():
            raise SystemExit("FAIL source_symlink")
        if path.is_file():
            inventory[relative] = sha(path)
    manifest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    if manifest != SOURCE_MANIFEST or any(sha(source / p) != digest for p, digest in PINS.items()):
        raise SystemExit("FAIL t01_source_pin")

    broker = ROOT / "evals/native-qualification/smoke/t01_jsonrpc_broker.php"
    collector = ROOT / "evals/native-qualification/smoke/t01_receipt_collector.php"
    runner = ROOT / "tools/native_research.py"
    for path in (broker, collector):
        if not path.is_file():
            raise SystemExit(f"FAIL missing_{path.name}")
        checked = subprocess.run(["php", "-l", str(path)], capture_output=True, text=True)
        if checked.returncode:
            raise SystemExit(f"FAIL php_lint_{path.name}: {checked.stderr.strip()}")
    if "--t01-capture" not in runner.read_text() or "--kanboard-capture" not in runner.read_text():
        raise SystemExit("FAIL capture_mode_separation")

    # The fake value is a protocol fixture, never a real credential. Production
    # broker code is included but its CLI server entrypoint is not executed.
    php = r'''require $argv[1]; $v = t01_scrub(["id"=>17,"token"=>"fixture-only","nested"=>["password"=>"fixture-only","project_id"=>9]]); echo json_encode($v);'''
    result = subprocess.run(["php", "-r", php, str(broker)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("FAIL broker_scrub_function")
    value = json.loads(result.stdout)
    if (value.get("id") != 17 or value.get("nested", {}).get("project_id") != 9
            or "fixture-only" in result.stdout):
        raise SystemExit("FAIL broker_scrub_result")
    if "Authorization" in collector.read_text() or "Cookie" in collector.read_text():
        raise SystemExit("FAIL receipt_schema_secret_field")
    print(json.dumps({"status": "pass", "source_manifest_sha256": manifest,
                      "php_lint": 2, "scrub_fixture": "pass", "provider_calls": 0,
                      "target_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
