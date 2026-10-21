#!/usr/bin/env python3
"""Offline verifier for the sanitized same-image PHP 8.4.27 receipt."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]

IMAGE_ID = "sha256:4aae0f3a516cd2fcde717e5f2ac055105a04e3a5bb81afe6c484f0c3953b769f"
SEALED_IMAGE_ID = "sha256:241dd8f788c62d5c9ef87bdab07ce1f05aca7db0199d532a68b5910c7397f7de"
EXCLUDED_IMAGE_ID = "sha256:76af9c070c17a94c3804f4729abef7e417a1b3404b0b0bc16a6f0691b18c2263"
SOURCE_COMMIT = "1781eb457b633f9391c89a911ebd3c66c378d3f4"
BASELINE_SHA256 = "91a7a28d7ec6e52022f6c534aa35facc447a72a8f65b14c84944366af6c418a5"

PUBLIC_FILE_SHA256 = {
    "README.md": "95e5493faf4333348cbcfe65f07137b0671ad088714c2dc14bd862f5b7f2155d",
    "inputs.json": "d2e7181e0f72e6986c9c1fbea3b4fb60cb324acb66c39b0b33f73eb50e907192",
    "result.json": "12c040ca3d81572373e89a0a8ce08c867bc74ba8a9533c39ae4890bd73b46cfb",
    "run-command.txt": "ae37848c4fe81ffc19b052a2805eda5d92fc60bec67372b800d6166ae2d8427f",
}

EXPECTED_COMMAND = (
    "python3 evals/native-qualification/smoke/check_v2_managed_owned_amd64_php8427.py "
    "--output \"${T02_PRIVATE_OUTPUT}\" --managed-ca \"${T02_MANAGED_CA_FILE}\" "
    "--parity-source-root \"${T02_PR182_SOURCE_ROOT}\" "
    "--source-commit 1781eb457b633f9391c89a911ebd3c66c378d3f4\n"
).encode()

SENSITIVE_PATTERNS = {
    "quoted sensitive key": re.compile(
        r'(?i)"(?:authorization|api[_-]?key|access[_-]?token|password|cookie)"\s*:'
    ),
    "authorization or bearer value": re.compile(r"(?i)(?:authorization\s*[:=]|bearer\s+[A-Za-z0-9._~+/-]{8,})"),
    "embedded URL credential": re.compile(r"(?i)https?://[^\s/:@]+:[^\s/@]+@"),
    "private filesystem path": re.compile(r"(?i)/(?:workspace|tmp|private/tmp|home|var/(?:lib|run))/"),
    "private key material": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


class EvidenceError(RuntimeError):
    pass


class Checks:
    def __init__(self) -> None:
        self.count = 0

    def equal(self, actual: Any, expected: Any, label: str) -> None:
        self.count += 1
        if actual != expected:
            raise EvidenceError(f"{label}: expected {expected!r}, got {actual!r}")

    def true(self, condition: bool, label: str) -> None:
        self.count += 1
        if not condition:
            raise EvidenceError(label)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(data, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{label}: invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise EvidenceError(f"{label}: root must be an object")
    return parsed


def exact_keys(checks: Checks, value: dict[str, Any], expected: set[str], label: str) -> None:
    checks.equal(set(value), expected, f"{label} keys")


def validate_inputs(value: dict[str, Any], checks: Checks) -> None:
    exact_keys(
        checks,
        value,
        {
            "schema_version",
            "kind",
            "completed_at",
            "source",
            "parity_source",
            "image",
            "archives",
            "execution_policy",
            "historical_boundaries",
            "private_receipt_sha256",
        },
        "inputs",
    )
    checks.equal(value["schema_version"], 1, "inputs schema version")
    checks.equal(value["kind"], "t02-managed-owned-amd64-php8427-same-image-inputs", "inputs kind")
    checks.equal(value["completed_at"], "2026-10-21T22:15:14Z", "inputs completion time")

    source = value["source"]
    exact_keys(
        checks,
        source,
        {"integration_head", "run_source_commit", "image_and_parity_source_head", "files"},
        "source",
    )
    checks.equal(source["integration_head"], "b8f0453575740cb1482dc716fa1807c195459f58", "integration head")
    checks.equal(source["run_source_commit"], SOURCE_COMMIT, "run source commit")
    checks.equal(source["image_and_parity_source_head"], "03c936e3e6e17947b6d061ab5bd8025904e3f0a7", "image source head")
    expected_source_files = {
        "evals/native-qualification/Dockerfile.opencode-kanboard-runtime-php8427": "be4948ac34c02f1cf84560f86874f07dc4d6c4b4efc8b1141956d2bf16f7497e",
        "evals/native-qualification/T02-AMD64-MANAGED-OWNED-PHP8427-CHECKS-20261021.md": "9eca021870ac7b52b974c58f65de511e950481c246ecf3d34552ed6bad71290d",
        "evals/native-qualification/smoke/check_v2_managed_owned_amd64_php8427.py": "3c91fca0a6fe7af4570248de5d6f18ebe6b4f709118fc3c75a31b6b68d726164",
        "evals/native-qualification/smoke/opencode_v2_managed_owned.py": "e5f442ddcda8515cb0fb29b9a601cdea068e6c66da795c4b8c8da0e351569475",
        "evals/native-qualification/smoke/same_image_php8427_parity.py": "3e5a43cb5b3f6eda3ceb6a189a01f62822f9bcb8876bc9fe5f65856b214c48dd",
        "evals/native-qualification/t02-source/SOURCE-MANIFEST.json": "d228a9d5f52ea85d1ece385d33cffb32be238f94f2d53455bed1093e50154085",
        "experiments/native-network-preflight/tcp-relay-host-override/cloud-linux-amd64-20261020a/tcp-relay-linux-amd64": "33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895",
    }
    checks.equal(source["files"], expected_source_files, "source file pins")

    parity = value["parity_source"]
    exact_keys(
        checks,
        parity,
        {
            "adapter_sha256",
            "runner_sha256",
            "observer_sha256",
            "historical_comparator_sha256",
            "researcher_brief_sha256",
            "checks_sha256",
        },
        "parity source",
    )
    expected_parity = {
        "adapter_sha256": "100cebaaf715e42fa9c10e4c396a5075c931f6f780baac64f590844308d0973d",
        "runner_sha256": "bf983ccc93fac42033c7785fab35aa10e263c9035ee8680a3896c183df281927",
        "observer_sha256": "72273bfd4e1c1aa9f7f53279e525ec1c74c2669324fa62f1b6b22abf65d596bf",
        "historical_comparator_sha256": "9db3bc220484a7a786729847f3c8fa8cc1d364a74b1e4a81d2bb78f80dc924fa",
        "researcher_brief_sha256": "8f2b5604870cf86719ae94ac180cb6cbe0c5c12cdd2356bc90f4104bb7179a5a",
        "checks_sha256": "eac607c837d9d356f79662cc0050958d0cf67384565a298be108fedc2636bc94",
    }
    checks.equal(parity, expected_parity, "parity source pins")

    image = value["image"]
    exact_keys(checks, image, {"platform", "tag", "id", "base", "managed_ca"}, "image")
    checks.equal(image["platform"], "linux/amd64", "image platform")
    checks.equal(image["tag"], "t02-managed-runtime:amd64-php8427-20261021d", "image tag")
    checks.equal(image["id"], IMAGE_ID, "image ID")
    checks.equal(
        image["base"],
        "ghcr.io/anomalyco/opencode@sha256:85986f556e985e377bd24cd68a5ccfbc647bb49e591194edda8a0e4542303319",
        "base image digest",
    )
    managed_ca = image["managed_ca"]
    exact_keys(
        checks,
        managed_ca,
        {"source_class", "sha256", "size_bytes", "buildkit_secret_only", "system_trust_changed"},
        "managed CA",
    )
    checks.equal(managed_ca["source_class"], "existing managed combined CA bundle", "managed CA class")
    checks.equal(managed_ca["sha256"], "43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73", "managed CA hash")
    checks.equal(managed_ca["size_bytes"], 230249, "managed CA size")
    checks.equal(managed_ca["buildkit_secret_only"], True, "managed CA build use")
    checks.equal(managed_ca["system_trust_changed"], False, "system trust unchanged")

    archives = value["archives"]
    exact_keys(checks, archives, {"vulnerable", "fixed"}, "archives")
    for label, commit, digest in (
        ("vulnerable", "f0f7d27007f5a788f14416c548421efd740b7bce", "3f24269475bf00137d4b0d957d97a2567a5249101dad89067a49d609f4df2edf"),
        ("fixed", "a98bc5f855d4e7e47eb3425a6c7da6c6cc6748a3", "44db3df81a25bbd56c768c8b3180a1f05879e2c7fbaa6ac73707e7f3e9098f56"),
    ):
        exact_keys(checks, archives[label], {"commit", "sha256"}, f"{label} archive")
        checks.equal(archives[label], {"commit": commit, "sha256": digest}, f"{label} archive pin")

    policy = value["execution_policy"]
    exact_keys(
        checks,
        policy,
        {
            "runtime_pull",
            "runtime_probe_network",
            "live_admission_enabled",
            "provider_calls_permitted",
            "model_calls_permitted",
            "live_targets_permitted",
            "external_credentials_permitted",
        },
        "execution policy",
    )
    checks.equal(policy["runtime_pull"], "never", "runtime pull policy")
    checks.equal(policy["runtime_probe_network"], "none", "runtime network policy")
    for key in (
        "live_admission_enabled",
        "provider_calls_permitted",
        "model_calls_permitted",
        "live_targets_permitted",
        "external_credentials_permitted",
    ):
        checks.equal(policy[key], False, f"execution policy {key}")

    history = value["historical_boundaries"]
    exact_keys(
        checks,
        history,
        {"sealed_removed_pr182_image", "sealed_receipt_reused", "excluded_managed_only_image", "excluded_managed_only_reason"},
        "historical boundaries",
    )
    checks.equal(history["sealed_removed_pr182_image"], SEALED_IMAGE_ID, "sealed historical image")
    checks.equal(history["sealed_receipt_reused"], False, "sealed receipt not reused")
    checks.equal(history["excluded_managed_only_image"], EXCLUDED_IMAGE_ID, "excluded managed-only image")
    checks.equal(
        history["excluded_managed_only_reason"],
        "same-image application parity was not run before the managed workflow",
        "excluded image reason",
    )
    checks.true(len({image["id"], history["sealed_removed_pr182_image"], history["excluded_managed_only_image"]}) == 3, "current and historical image IDs must differ")

    receipts = value["private_receipt_sha256"]
    exact_keys(
        checks,
        receipts,
        {
            "candidate",
            "runtime_admission",
            "controller_result",
            "baseline_before",
            "baseline_after",
            "build_cache_registration",
            "same_image_summary",
            "registration_compatibility",
            "archive_admission",
            "parity_result",
            "public_observer_result",
        },
        "private receipt hashes",
    )
    checks.equal(receipts["candidate"], "cb597456de4af1c4ace7bf98d5dfa6cceedf2def5cb46d56af914f3de3501be5", "candidate receipt hash")
    checks.equal(receipts["runtime_admission"], "89866098b9f57ed53e23ebe5d94b1d7ec2f549e197eeb2c7612932d3ce22834d", "runtime receipt hash")
    checks.equal(receipts["controller_result"], "bee99f69610fea4b358eeb2ed8cd22abbb3b67f939003bfb6ebbad9e1c6bfaf5", "controller result hash")
    checks.equal(receipts["same_image_summary"], "cbd792fa50424d3da3f923ef0455d6b04a99ce2a61ea56e6ed7c30f7c43ce5f6", "same-image summary hash")
    checks.equal(receipts["baseline_before"], BASELINE_SHA256, "baseline-before receipt hash")
    checks.equal(receipts["baseline_after"], BASELINE_SHA256, "baseline-after receipt hash")
    for key, digest in receipts.items():
        checks.true(bool(re.fullmatch(r"[0-9a-f]{64}", digest)), f"{key} must be a SHA-256 digest")


def validate_result(value: dict[str, Any], checks: Checks) -> None:
    exact_keys(
        checks,
        value,
        {
            "schema_version",
            "kind",
            "completed_at",
            "status",
            "failure",
            "source_commit",
            "image_id",
            "runtime_admission",
            "application_parity",
            "managed_owned",
            "same_image_chain",
            "external_activity",
            "live_admission_enabled",
            "cleanup",
            "claim_limits",
        },
        "result",
    )
    checks.equal(value["schema_version"], 1, "result schema version")
    checks.equal(value["kind"], "t02-managed-owned-amd64-php8427-same-image-public-result", "result kind")
    checks.equal(value["completed_at"], "2026-10-21T22:15:14Z", "result completion time")
    checks.equal(value["status"], "pass", "result status")
    checks.equal(value["failure"], None, "result failure")
    checks.equal(value["source_commit"], SOURCE_COMMIT, "result source commit")
    checks.equal(value["image_id"], IMAGE_ID, "result image ID")

    runtime = value["runtime_admission"]
    exact_keys(checks, runtime, {"status", "image_id", "platform", "php_package_revision", "php_version", "opencode_version", "pull", "network"}, "runtime admission")
    checks.equal(
        runtime,
        {
            "status": "pass",
            "image_id": IMAGE_ID,
            "platform": "linux/amd64",
            "php_package_revision": "8.4.27-r0",
            "php_version": "8.4.27",
            "opencode_version": "v2.0.32",
            "pull": "never",
            "network": "none",
        },
        "runtime admission result",
    )

    parity = value["application_parity"]
    exact_keys(
        checks,
        parity,
        {
            "status",
            "image_id",
            "arm_image_ids",
            "checks_passed",
            "checks_total",
            "archives_verified_before_first_arm",
            "both_arms_same_image",
            "historical_semantic_comparison_complete",
            "inner_docker_baseline_restored",
        },
        "application parity",
    )
    checks.equal(parity["status"], "pass", "application parity status")
    checks.equal(parity["image_id"], IMAGE_ID, "application parity image")
    checks.equal(
        parity["arm_image_ids"],
        {"vulnerable": IMAGE_ID, "fixed": IMAGE_ID},
        "application parity arm images",
    )
    checks.equal((parity["checks_passed"], parity["checks_total"]), (32, 32), "application parity checks")
    checks.equal(parity["archives_verified_before_first_arm"], 2, "archives verified before first arm")
    for key in ("both_arms_same_image", "historical_semantic_comparison_complete", "inner_docker_baseline_restored"):
        checks.equal(parity[key], True, f"application parity {key}")

    managed = value["managed_owned"]
    exact_keys(
        checks,
        managed,
        {
            "status",
            "image_id",
            "classification",
            "review_status",
            "checks_passed",
            "checks_total",
            "native_stages",
            "cleanup_complete",
            "temporary_secret_files_removed",
            "source_pins_stable",
            "source_copies_match",
        },
        "managed owned",
    )
    checks.equal(managed["status"], "pass", "managed status")
    checks.equal(managed["image_id"], IMAGE_ID, "managed image")
    checks.equal(managed["classification"], "owned TLS/native managed CONNECT offline E2E; zero provider calls", "managed classification")
    checks.equal(managed["review_status"], "unqualified_owned_synthetic_response", "managed review status")
    checks.equal((managed["checks_passed"], managed["checks_total"]), (80, 80), "managed checks")
    checks.equal(managed["native_stages"], ["first", "reviewer", "resume"], "managed native stages")
    for key in ("cleanup_complete", "temporary_secret_files_removed", "source_pins_stable", "source_copies_match"):
        checks.equal(managed[key], True, f"managed {key}")

    chain = value["same_image_chain"]
    exact_keys(checks, chain, {"candidate_runtime_parity_and_managed_ids_equal", "image_rebuilt_between_stages", "historical_receipt_reused"}, "same-image chain")
    checks.equal(chain["candidate_runtime_parity_and_managed_ids_equal"], True, "same-image equality")
    checks.equal(chain["image_rebuilt_between_stages"], False, "no interstage rebuild")
    checks.equal(chain["historical_receipt_reused"], False, "no historical receipt reuse")

    external = value["external_activity"]
    exact_keys(
        checks,
        external,
        {
            "public_source_archives_retrieved",
            "provider_calls",
            "model_calls",
            "live_targets_contacted",
            "external_credentials_used",
            "engagements_started",
            "researcher_bundle_created",
        },
        "external activity",
    )
    checks.equal(external["public_source_archives_retrieved"], 2, "public archive retrieval count")
    for key in ("provider_calls", "model_calls", "live_targets_contacted", "external_credentials_used", "engagements_started"):
        checks.equal(external[key], 0, f"external activity {key}")
    checks.equal(external["researcher_bundle_created"], False, "no researcher bundle")
    checks.equal(value["live_admission_enabled"], False, "live admission disabled")

    cleanup = value["cleanup"]
    exact_keys(
        checks,
        cleanup,
        {
            "image_removed",
            "registered_build_cache_records_removed",
            "unresolved_build_cache_records",
            "errors",
            "baseline_before_sha256",
            "baseline_after_sha256",
            "baseline_restored",
            "controller_post_cleanup_readback",
        },
        "cleanup",
    )
    checks.equal(cleanup["image_removed"], True, "task image removed")
    checks.equal(cleanup["registered_build_cache_records_removed"], 7, "task build-cache records removed")
    checks.equal(cleanup["unresolved_build_cache_records"], 0, "unresolved task cache records")
    checks.equal(cleanup["errors"], [], "cleanup errors")
    checks.equal(cleanup["baseline_before_sha256"], BASELINE_SHA256, "baseline before")
    checks.equal(cleanup["baseline_after_sha256"], BASELINE_SHA256, "baseline after")
    checks.equal(cleanup["baseline_restored"], True, "outer baseline restored")
    readback = cleanup["controller_post_cleanup_readback"]
    exact_keys(checks, readback, {"containers", "images", "volumes", "build_cache_records", "default_networks_unchanged"}, "cleanup readback")
    checks.equal(readback, {"containers": 0, "images": 0, "volumes": 0, "build_cache_records": 0, "default_networks_unchanged": True}, "cleanup readback result")

    limits = value["claim_limits"]
    exact_keys(
        checks,
        limits,
        {
            "owned_offline_current_runtime_only",
            "provider_or_model_route_qualified",
            "live_tls_qualified",
            "receiver_qualified",
            "target_qualified",
            "hosted_ci_qualified",
            "independent_cleanup_readback_verified",
            "default_adoption",
            "issue_165_unblocked",
            "retirement_work_authorized",
        },
        "claim limits",
    )
    checks.equal(limits["owned_offline_current_runtime_only"], True, "owned offline current-runtime claim")
    for key in set(limits) - {"owned_offline_current_runtime_only"}:
        checks.equal(limits[key], False, f"claim limit {key}")


def validate_relationships(inputs: dict[str, Any], result: dict[str, Any], checks: Checks) -> None:
    checks.equal(inputs["source"]["run_source_commit"], result["source_commit"], "source commit relationship")
    image_ids = {
        inputs["image"]["id"],
        result["image_id"],
        result["runtime_admission"]["image_id"],
        result["application_parity"]["image_id"],
        *result["application_parity"]["arm_image_ids"].values(),
        result["managed_owned"]["image_id"],
    }
    checks.equal(image_ids, {IMAGE_ID}, "same-image relationship")
    checks.equal(
        inputs["private_receipt_sha256"]["baseline_before"],
        result["cleanup"]["baseline_before_sha256"],
        "baseline-before relationship",
    )
    checks.equal(
        inputs["private_receipt_sha256"]["baseline_after"],
        result["cleanup"]["baseline_after_sha256"],
        "baseline-after relationship",
    )
    checks.equal(inputs["execution_policy"]["live_admission_enabled"], result["live_admission_enabled"], "live-admission relationship")


def scan_text(label: str, text: str, checks: Checks) -> None:
    for pattern_label, pattern in SENSITIVE_PATTERNS.items():
        checks.true(pattern.search(text) is None, f"{label}: found {pattern_label}")


def verify_public() -> tuple[int, dict[str, Any], dict[str, Any]]:
    checks = Checks()
    expected_files = set(PUBLIC_FILE_SHA256) | {"verify.py"}
    actual_entries = {path.name for path in HERE.iterdir()}
    checks.equal(actual_entries, expected_files, "public evidence file set")
    for name in sorted(expected_files):
        path = HERE / name
        checks.true(path.is_file() and not path.is_symlink(), f"public evidence entry must be a regular file: {name}")

    public_bytes: dict[str, bytes] = {}
    for name, digest in PUBLIC_FILE_SHA256.items():
        data = (HERE / name).read_bytes()
        public_bytes[name] = data
        checks.equal(sha256_bytes(data), digest, f"{name} SHA-256")
    checks.equal(public_bytes["run-command.txt"], EXPECTED_COMMAND, "exact replay command bytes")

    inputs = load_json_bytes(public_bytes["inputs.json"], "inputs.json")
    result = load_json_bytes(public_bytes["result.json"], "result.json")
    validate_inputs(inputs, checks)
    validate_result(result, checks)
    validate_relationships(inputs, result, checks)

    for relative_path, expected_digest in inputs["source"]["files"].items():
        path = REPO_ROOT / relative_path
        checks.true(path.is_file(), f"missing pinned source file: {relative_path}")
        checks.equal(sha256_bytes(path.read_bytes()), expected_digest, f"source SHA-256: {relative_path}")

    for name, data in public_bytes.items():
        scan_text(name, data.decode("utf-8"), checks)

    return checks.count, inputs, result


def expect_rejected(label: str, action: Callable[[], None]) -> None:
    try:
        action()
    except EvidenceError:
        return
    raise EvidenceError(f"negative self-test was accepted: {label}")


def run_self_tests(inputs: dict[str, Any], result: dict[str, Any]) -> int:
    count = 0

    expect_rejected("duplicate JSON key", lambda: load_json_bytes(b'{"status":"pass","status":"fail"}', "mutation"))
    count += 1

    def reject_result(mutator: Callable[[dict[str, Any]], None]) -> None:
        changed = copy.deepcopy(result)
        mutator(changed)
        validate_result(changed, Checks())
        validate_relationships(inputs, changed, Checks())

    expect_rejected("changed managed image", lambda: reject_result(lambda value: value["managed_owned"].__setitem__("image_id", EXCLUDED_IMAGE_ID)))
    count += 1
    expect_rejected("changed PHP runtime", lambda: reject_result(lambda value: value["runtime_admission"].__setitem__("php_version", "8.4.26")))
    count += 1
    expect_rejected("changed fixed-arm image", lambda: reject_result(lambda value: value["application_parity"]["arm_image_ids"].__setitem__("fixed", EXCLUDED_IMAGE_ID)))
    count += 1
    expect_rejected("provider call", lambda: reject_result(lambda value: value["external_activity"].__setitem__("provider_calls", 1)))
    count += 1
    expect_rejected("live admission", lambda: reject_result(lambda value: value.__setitem__("live_admission_enabled", True)))
    count += 1
    expect_rejected("baseline mismatch", lambda: reject_result(lambda value: value["cleanup"].__setitem__("baseline_after_sha256", "0" * 64)))
    count += 1
    expect_rejected("independent cleanup claim", lambda: reject_result(lambda value: value["claim_limits"].__setitem__("independent_cleanup_readback_verified", True)))
    count += 1

    changed_inputs = copy.deepcopy(inputs)
    changed_inputs["historical_boundaries"]["sealed_receipt_reused"] = True
    expect_rejected("sealed receipt reuse", lambda: validate_inputs(changed_inputs, Checks()))
    count += 1

    expect_rejected("unreachable replay command", lambda: _check_command(b"if false; then\n" + EXPECTED_COMMAND + b"fi\n"))
    count += 1
    expect_rejected("quoted Authorization key", lambda: scan_text("mutation", '{"Authorization":"Bearer owned-test-value"}', Checks()))
    count += 1
    expect_rejected("quoted api_key key", lambda: scan_text("mutation", '{"api_key":"owned-test-value"}', Checks()))
    count += 1
    expect_rejected("private path", lambda: scan_text("mutation", '{"output":"/workspace/private/result.json"}', Checks()))
    count += 1
    return count


def _check_command(value: bytes) -> None:
    if value != EXPECTED_COMMAND:
        raise EvidenceError("replay command bytes changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="also run bounded negative mutation checks")
    args = parser.parse_args()
    try:
        checks, inputs, result = verify_public()
        print(f"PASS: {checks}/{checks} public checks")
        if args.self_test:
            negative = run_self_tests(inputs, result)
            print(f"PASS: {negative}/{negative} negative self-tests")
    except (EvidenceError, OSError, KeyError, TypeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
