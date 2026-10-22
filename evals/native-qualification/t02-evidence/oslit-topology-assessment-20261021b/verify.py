#!/usr/bin/env python3
"""Verify the sanitized OSLIT topology receipt without network or Docker access."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RECEIPT = HERE / 'topology-assessment.json'
README = HERE / 'README.md'
RUNNER = ROOT / 'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
TRANSPORT = ROOT / 'experiments/native-network-preflight/v2_connect.py'
POLICY = Path('/etc/codex/network-policy.json')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proxy_facts(value):
    parsed = urlsplit(value)
    return {
        'scheme': parsed.scheme,
        'credentials_present': parsed.username is not None or parsed.password is not None,
    }


def receipt_checks(receipt, policy, public_text, readme, runner, transport):
    http_proxy = policy.get('http_proxy', '')
    tcp_proxy = policy.get('tcp_connect_proxy', '')
    live_gate = "if live:\n        parser.error('cloud_live_route_not_qualified')"
    gate_index = runner.find(live_gate)
    output_index = runner.find('output.mkdir(')
    return {
        'policy_hash_matches': receipt['managed_policy']['sha256'] == sha256(POLICY),
        'policy_mode_matches': (
            receipt['managed_policy']['mode'] == f'{POLICY.stat().st_mode & 0o777:04o}'),
        'policy_shape_matches': (
            receipt['managed_policy']['vpn_configured'] is policy.get('vpn_configured')
            and receipt['managed_policy']['http_policy_type']
            == policy.get('http_network_policy', {}).get('type')
            and receipt['managed_policy']['tcp_destination_domain_count']
            == len(policy.get('tcp_network_access', {}).get('domains', []))
            and receipt['managed_policy']['tcp_destination_ip_range_count']
            == len(policy.get('tcp_network_access', {}).get('ip_ranges', []))),
        'proxy_shapes_match_without_values': (
            receipt['managed_policy']['http_proxy'] | {'raw_value_retained': False}
            == proxy_facts(http_proxy) | {'raw_value_retained': False}
            and receipt['managed_policy']['tcp_connect_proxy'] | {'raw_value_retained': False}
            == proxy_facts(tcp_proxy) | {'raw_value_retained': False}),
        'raw_proxy_values_absent': (
            bool(http_proxy) and bool(tcp_proxy)
            and http_proxy not in public_text and tcp_proxy not in public_text
            and http_proxy not in readme and tcp_proxy not in readme),
        'runner_hash_matches': receipt['source']['runner_sha256'] == sha256(RUNNER),
        'transport_hash_matches': receipt['source']['transport_sha256'] == sha256(TRANSPORT),
        'live_gate_precedes_output': gate_index >= 0 and output_index >= 0 and gate_index < output_index,
        'transport_authority_fixed': 'AUTHORITY = "opencode.ai:443"' in transport,
        'managed_failure_limit_is_explicit': (
            receipt['prior_evidence']['managed_self_receiver']['availability'] == 'summary_only'
            and receipt['prior_evidence']['managed_self_receiver']['evidence_grade']
            == 'prior_run_summary_no_raw_probe_receipt'),
        'owned_receipt_limit_is_explicit': (
            receipt['prior_evidence']['owned_offline_receipts']['availability']
            == 'local_unpublished'
            and receipt['prior_evidence']['owned_offline_receipts']['evidence_grade']
            == 'hash_pointer_only'),
        'activity_is_not_upgraded_to_machine_evidence': (
            receipt['activity']['evidence_grade'] == 'agent_transcript_attestation'
            and receipt['verification']['checker_scope_only'] is True),
        'docker_readback_is_labeled_attestation': (
            receipt['docker_baseline']['evidence_grade'] == 'agent_transcript_attestation'
            and receipt['docker_baseline']['identifiers_retained'] is False),
        'issue_states_remain_open_or_no_go': (
            receipt['issue_state']['158'].startswith('incomplete_')
            and receipt['issue_state']['161'].startswith('incomplete_')
            and receipt['issue_state']['165'] == 'no_go_unchanged'),
        'readme_separates_inference': 'lack of a reverse route is an inference' in readme,
        'readme_names_evidence_limits': (
            'transcript attestations, not independent runtime observations' in readme
            and 'has no raw probe receipt' in readme),
    }


def core_receipt(receipt=None):
    receipt = receipt if receipt is not None else json.loads(RECEIPT.read_text())
    public_text = json.dumps(receipt, sort_keys=True)
    readme = README.read_text()
    policy = json.loads(POLICY.read_text())
    runner = RUNNER.read_text()
    transport = TRANSPORT.read_text()
    checks = receipt_checks(receipt, policy, public_text, readme, runner, transport)
    return {
        'schema_version': 1,
        'kind': 't02-oslit-topology-receipt-check',
        'status': 'unobserved' if all(checks.values()) else 'fail',
        'observation_complete': False,
        'checks': checks,
        'source_sha256': {
            'checker': sha256(Path(__file__)),
            'readme': sha256(README),
            'receipt': sha256(RECEIPT),
            'runner': sha256(RUNNER),
            'transport': sha256(TRANSPORT),
            'policy': sha256(POLICY),
        },
        'limits': {
            'whole_assessment_activity_independently_observed': False,
            'prior_managed_probe_raw_receipt_available': False,
            'owned_offline_receipts_published_here': False,
        },
    }


def self_test():
    original = json.loads(RECEIPT.read_text())
    base = core_receipt(original)
    wrong_policy = copy.deepcopy(original)
    wrong_policy['managed_policy']['sha256'] = '0' * 64
    upgraded_activity = copy.deepcopy(original)
    upgraded_activity['activity']['evidence_grade'] = 'machine_observed'
    results = {
        'valid_receipt_passes': base['status'] == 'unobserved',
        'wrong_policy_hash_fails': core_receipt(wrong_policy)['status'] == 'fail',
        'false_activity_upgrade_fails': core_receipt(upgraded_activity)['status'] == 'fail',
    }
    print(json.dumps({'kind': 't02-oslit-topology-receipt-self-test',
                      'status': 'pass' if all(results.values()) else 'fail',
                      'checks': results}, sort_keys=True))
    return 0 if all(results.values()) else 1


def observed_main():
    observer = shutil.which('strace')
    if observer is None:
        raise RuntimeError('network_observer_unavailable')
    with tempfile.TemporaryDirectory(prefix='t02-topology-receipt-') as directory:
        trace = Path(directory) / 'network.trace'
        result = subprocess.run([
            observer, '-qq', '-f', '-e', 'trace=network', '-e', 'signal=none', '-o', str(trace),
            sys.executable, str(Path(__file__).resolve()), '--unobserved-core'],
            capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('traced_receipt_check_failed')
        if trace.read_text().strip():
            raise RuntimeError('network_syscall_observed')
        try:
            result_receipt = json.loads(result.stdout)
        except (TypeError, ValueError):
            raise RuntimeError('traced_receipt_invalid') from None
        if (result_receipt.get('kind') != 't02-oslit-topology-receipt-check'
                or result_receipt.get('status') != 'unobserved'
                or result_receipt.get('observation_complete') is not False):
            raise RuntimeError('traced_receipt_invalid')
    result_receipt['status'] = 'pass'
    result_receipt['observation_complete'] = True
    result_receipt['network_observation'] = {
        'method': 'strace -qq -f -e trace=network -e signal=none',
        'scope': 'checker child and all descendants',
        'syscalls_observed': 0,
    }
    print(json.dumps(result_receipt, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unobserved-core', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        raise SystemExit(self_test())
    if args.unobserved_core:
        result = core_receipt()
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(0 if result['status'] == 'unobserved' else 1)
    observed_main()


if __name__ == '__main__':
    main()
