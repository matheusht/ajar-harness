#!/usr/bin/env python3
"""Provider-free T01 source and broker protocol checks; never starts Kanboard."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
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

    retained = json.loads((ROOT / "evals/native-qualification/observer-evidence-final/"
                           "vulnerable-requests.json").read_text())
    denied = [row for row in retained if row.get("actor") == "bob"
              and row.get("method") == "getProjectById"]
    if len(denied) != 1 or denied[0].get("http_status") != 403:
        raise SystemExit("FAIL retained_denial_missing")
    denial = json.loads(denied[0]["raw_response"])
    if denial.get("id", "missing") is not None or denial.get("error", {}).get("code") != 403:
        raise SystemExit("FAIL retained_denial_shape")

    # The fake value is a protocol fixture, never a real credential. Production
    # broker code is included but its CLI server entrypoint is not executed.
    php = r'''
require $argv[1];
$db = new PDO('sqlite::memory:');
$db->exec('CREATE TABLE objects (id INTEGER, project_id INTEGER, name TEXT)');
$safe = t01_safe_keys($db);
$changed = false;
$reply = ['jsonrpc'=>'2.0', 'result'=>['id'=>17, 'project_id'=>9,
    'name'=>'sensitive-text', 'opaqueNeutral'=>'fixture-only'], 'id'=>1];
$value = t01_scrub_reply($reply, $safe, 'fixture-hmac-key', $changed);
$error = t01_scrub_reply(['jsonrpc'=>'2.0',
    'error'=>['code'=>403, 'message'=>'opaque-error'], 'id'=>2],
    $safe, 'fixture-hmac-key', $changed);
$denial = t01_scrub_reply(json_decode($argv[2], true, 32, JSON_THROW_ON_ERROR),
    $safe, 'fixture-hmac-key', $changed);
$body = json_encode(['jsonrpc'=>'2.0', 'method'=>'getMe', 'id'=>'opaque-id']);
$pair = stream_socket_pair(STREAM_PF_UNIX, STREAM_SOCK_STREAM, 0);
fwrite($pair[0], "POST /jsonrpc.php HTTP/1.1\r\nHost: fixture\r\n"
    ."Content-Type: application/json\r\nX-Native-Actor: A\r\n"
    .'Content-Length: '.strlen($body)."\r\n\r\n".$body);
$stringIdRejected = false;
try { t01_read_request($pair[1]); }
catch (RuntimeException $problem) { $stringIdRejected = true; }
fclose($pair[0]); fclose($pair[1]);
echo json_encode(['result'=>$value, 'error'=>$error, 'retained_denial'=>$denial,
    'changed'=>$changed, 'string_id_rejected'=>$stringIdRejected]);
'''
    result = subprocess.run(["php", "-r", php, str(broker), json.dumps(denial)],
                            capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("FAIL broker_scrub_function")
    value = json.loads(result.stdout)
    reply = value.get("result", {})
    payload = reply.get("result", {})
    error = value.get("error", {})
    retained_denial = value.get("retained_denial", {})
    dynamic = [key for key in payload if key not in ("id", "project_id", "name")]
    if (reply.get("jsonrpc") != "2.0" or reply.get("id") != 1
            or payload.get("id") != 17 or payload.get("project_id") != 9
            or payload.get("name") != "[REDACTED]"
            or len(dynamic) != 1 or not dynamic[0].startswith("field_")
            or payload.get(dynamic[0]) != "[REDACTED]"
            or error.get("jsonrpc") != "2.0" or error.get("id") != 2
            or error.get("error", {}).get("code") != 403
            or error.get("error", {}).get("message") != "[REDACTED]"
            or retained_denial.get("jsonrpc") != "2.0"
            or retained_denial.get("id", "missing") is not None
            or retained_denial.get("error", {}).get("code") != 403
            or retained_denial.get("error", {}).get("message") != "[REDACTED]"
            or value.get("changed") is not True
            or value.get("string_id_rejected") is not True
            or any(secret in result.stdout for secret in
                   ("fixture-only", "opaqueNeutral", "sensitive-text", "opaque-error"))):
        raise SystemExit("FAIL broker_scrub_result")
    if "Authorization" in collector.read_text() or "Cookie" in collector.read_text():
        raise SystemExit("FAIL receipt_schema_secret_field")
    print(json.dumps({"status": "pass", "source_manifest_sha256": manifest,
                      "php_lint": 2, "scrub_fixture": "pass", "provider_calls": 0,
                      "target_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
