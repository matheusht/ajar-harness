#!/usr/bin/env python3
"""Offline checks for fail-closed live CA preparation and responder state."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / 'evals/native-qualification/smoke/opencode_v2_managed_owned.py'
RELAY = ROOT / ('experiments/native-network-preflight/tcp-relay-host-override/'
                'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')
RELAY_SHA = '33ef7484c2a2415915af399689e91e9efee8000b2c685a6b2b72eb4eddedf895'
CURRENT_MANIFEST = ROOT / 'evals/native-qualification/t02-source/SOURCE-MANIFEST.json'
EXCLUSIVE_CHECKER = ROOT / ('evals/native-qualification/smoke/'
                            'check_opencode_exclusive_trust.py')
EXCLUSIVE_PATCH = ROOT / ('evals/native-qualification/patches/'
                          'opencode-v2.0.32-exclusive-ca.patch')
EXCLUSIVE_RESEARCH = ROOT / ('evals/native-qualification/'
                             'T02-OPENCODE-EXCLUSIVE-TRUST-RESEARCH-20261021.md')
EXCLUSIVE_CONTRACT = ROOT / ('evals/native-qualification/'
                             'T02-OPENCODE-EXCLUSIVE-TRUST-CHECKS-20261021.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location('live_preparation_runner_check', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_exclusive_checker():
    spec = importlib.util.spec_from_file_location('exclusive_trust_source_check', EXCLUSIVE_CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_case(temp, name, extra, live=True, env_overrides=None):
    output = temp / ('runner-output-' + name)
    marker = temp / ('docker-called-' + name)
    args = [sys.executable, str(RUNNER), '--output', str(output),
            '--cloud-platform', 'linux/amd64',
            '--cloud-image-id', 'sha256:' + 'a' * 64,
            '--cloud-relay', str(RELAY), '--cloud-relay-sha256', RELAY_SHA,
            '--cloud-internal-subnet', '172.28.225.0/24',
            '--cloud-external-subnet', '172.28.224.0/24',
            '--cloud-listen-address', '172.28.224.1',
            '--cloud-relay-peer', '172.28.224.10',
            '--cloud-upstream-route', 'HTTPS_PROXY']
    if live:
        args.append('--live-free')
    args += extra
    env = os.environ.copy()
    env['HTTPS_PROXY'] = 'http://127.0.0.1:3128'
    env['T02_DOCKER_MARKER'] = str(marker)
    env['PATH'] = str(temp / 'fake-bin') + os.pathsep + env.get('PATH', '')
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=15)
    return result, output, marker


def expect_denied(checks, temp, name, extra, code, live=True):
    result, output, marker = run_case(temp, name, extra, live)
    passed = (result.returncode != 0 and ('error: ' + code) in result.stderr
              and not output.exists() and not marker.exists())
    checks.append({'name': name, 'pass': passed, 'error_code': code})
    if not passed:
        raise AssertionError(name)


def write_file(path, data, mode=0o600):
    path.write_bytes(data)
    path.chmod(mode)
    return path


def observed_main(args):
    observer = shutil.which('strace')
    if observer is None:
        raise RuntimeError('network_observer_unavailable')
    with tempfile.TemporaryDirectory(prefix='t02-live-preparation-observer-') as directory:
        trace = Path(directory) / 'network.trace'
        result = subprocess.run([
            observer, '-qq', '-f', '-e', 'trace=network', '-e', 'signal=none', '-o', str(trace),
            sys.executable, str(Path(__file__).resolve()), '--unobserved-core'],
            capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError('traced_source_check_failed')
        if trace.read_text().strip():
            raise RuntimeError('network_syscall_observed')
        try:
            receipt = json.loads(result.stdout)
        except (TypeError, ValueError):
            raise RuntimeError('traced_receipt_invalid') from None
        if (receipt.get('kind') != 't02-live-preparation-unobserved-core'
                or receipt.get('status') != 'unobserved'
                or receipt.get('observation_complete') is not False):
            raise RuntimeError('traced_receipt_invalid')
    receipt['kind'] = 't02-live-preparation-source-check'
    receipt['status'] = 'pass'
    receipt['observation_complete'] = True
    receipt['classification'] = ('offline source and parameter validation; '
                                 'no Docker invocation or network syscall observed')
    receipt['network_observation'] = {
        'method': 'strace -qq -f -e trace=network -e signal=none',
        'scope': 'checker child and all descendants',
        'syscalls_observed': 0,
    }
    if args.output:
        output = args.output.resolve()
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        (output / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS: fail-closed live CA preparation and responder state; '
          'no Docker invocation or network syscall observed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--unobserved-core', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.unobserved_core:
        observed_main(args)
        return
    checks = []
    with tempfile.TemporaryDirectory(prefix='t02-live-preparation-') as directory:
        temp = Path(directory)
        fake = temp / 'fake-bin/docker'
        fake.parent.mkdir()
        fake.write_text('#!/bin/sh\nprintf called >> "$T02_DOCKER_MARKER"\nexit 99\n')
        fake.chmod(0o700)

        key = temp / 'ca.key'
        ca = temp / 'ca.pem'
        generated = subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc', '-days', '1',
            '-sha256', '-subj', '/CN=T02 benign preparation CA',
            '-addext', 'basicConstraints=critical,CA:TRUE',
            '-keyout', str(key), '-out', str(ca)], capture_output=True, text=True, timeout=15)
        if generated.returncode:
            raise RuntimeError('benign_ca_generation_failed')
        key.chmod(0o600)
        ca.chmod(0o600)
        ca_sha = sha(ca)
        pair = ['--live-runtime-ca', str(ca), '--live-runtime-ca-sha256', ca_sha]

        expect_denied(checks, temp, 'missing-pair', [], 'live_runtime_ca_required')
        expect_denied(checks, temp, 'path-only', pair[:2], 'live_runtime_ca_required')
        expect_denied(checks, temp, 'hash-only', pair[2:], 'live_runtime_ca_required')
        expect_denied(checks, temp, 'offline-pair', pair, 'runtime_ca_live_only', live=False)
        expect_denied(checks, temp, 'relative-path',
                      ['--live-runtime-ca', os.path.relpath(ca, ROOT),
                       '--live-runtime-ca-sha256', ca_sha], 'live_runtime_ca_invalid')

        symlink = temp / 'ca-link.pem'
        symlink.symlink_to(ca)
        expect_denied(checks, temp, 'symlink',
                      ['--live-runtime-ca', str(symlink), '--live-runtime-ca-sha256', ca_sha],
                      'live_runtime_ca_invalid')
        expect_denied(checks, temp, 'directory',
                      ['--live-runtime-ca', str(temp), '--live-runtime-ca-sha256', '0' * 64],
                      'live_runtime_ca_invalid')
        fifo = temp / 'ca.fifo'
        os.mkfifo(fifo, 0o600)
        expect_denied(checks, temp, 'fifo',
                      ['--live-runtime-ca', str(fifo), '--live-runtime-ca-sha256', '0' * 64],
                      'live_runtime_ca_invalid')

        mutable = write_file(temp / 'mutable-ca.pem', ca.read_bytes(), 0o620)
        expect_denied(checks, temp, 'mutable',
                      ['--live-runtime-ca', str(mutable), '--live-runtime-ca-sha256', sha(mutable)],
                      'live_runtime_ca_invalid')
        empty = write_file(temp / 'empty.pem', b'')
        expect_denied(checks, temp, 'empty',
                      ['--live-runtime-ca', str(empty), '--live-runtime-ca-sha256', sha(empty)],
                      'live_runtime_ca_invalid')
        oversized = write_file(temp / 'oversized.pem', b'A' * (4 * 1024 * 1024 + 1))
        expect_denied(checks, temp, 'oversized',
                      ['--live-runtime-ca', str(oversized), '--live-runtime-ca-sha256', sha(oversized)],
                      'live_runtime_ca_invalid')
        expect_denied(checks, temp, 'private-key',
                      ['--live-runtime-ca', str(key), '--live-runtime-ca-sha256', sha(key)],
                      'live_runtime_ca_invalid')
        malformed = write_file(temp / 'malformed.pem', b'not a certificate\n')
        expect_denied(checks, temp, 'malformed-pem',
                      ['--live-runtime-ca', str(malformed), '--live-runtime-ca-sha256', sha(malformed)],
                      'live_runtime_ca_invalid')
        mixed = write_file(temp / 'mixed.pem', ca.read_bytes() + b'unparsed trailing bytes\n')
        expect_denied(checks, temp, 'mixed-valid-malformed-pem',
                      ['--live-runtime-ca', str(mixed), '--live-runtime-ca-sha256', sha(mixed)],
                      'live_runtime_ca_invalid')
        expect_denied(checks, temp, 'malformed-hash',
                      ['--live-runtime-ca', str(ca), '--live-runtime-ca-sha256', 'not-a-hash'],
                      'live_runtime_ca_sha256_invalid')
        expect_denied(checks, temp, 'hash-mismatch',
                      ['--live-runtime-ca', str(ca), '--live-runtime-ca-sha256', '0' * 64],
                      'live_runtime_ca_hash_mismatch')
        expect_denied(checks, temp, 'valid-still-blocked', pair,
                      'cloud_live_route_not_qualified')
        keylog = temp / 'unexpected-ssl-keylog'
        result, output, marker = run_case(
            temp, 'ambient-keylog-still-blocked', pair,
            env_overrides={'SSLKEYLOGFILE': str(keylog)})
        ambient_keylog_safe = (result.returncode != 0
                               and 'error: cloud_live_route_not_qualified' in result.stderr
                               and not output.exists() and not marker.exists() and not keylog.exists())
        checks.append({'name': 'ambient SSLKEYLOGFILE has no pre-denial effect',
                       'pass': ambient_keylog_safe,
                       'error_code': 'cloud_live_route_not_qualified'})
        if not ambient_keylog_safe:
            raise AssertionError('ambient_sslkeylogfile_effect')

        module = load_runner()
        runner_source = RUNNER.read_text()
        gate_offset = runner_source.index("parser.error('cloud_live_route_not_qualified')")
        output_offset = runner_source.index('output = args.output.resolve()')
        dormant = ('check_opencode_exclusive_trust' not in runner_source
                   and 'OPENCODE_EXCLUSIVE_CA_FILE' not in runner_source
                   and gate_offset < output_offset)
        checks.append({'name': 'exclusive checker is dormant behind the unchanged live gate',
                       'pass': dormant})
        if not dormant:
            raise AssertionError('exclusive_checker_not_dormant')

        patch_source = EXCLUSIVE_PATCH.read_text()
        patch_shape = all(fragment in patch_source for fragment in (
            'packages/core/src/effect/app-node-platform.ts',
            'if (path === undefined) return rejectExclusiveCa("path_required")',
            'path !== EXCLUSIVE_CA_PATH',
            'return rejectExclusiveCa("digest_required")',
            'constants.O_NOFOLLOW | constants.O_NONBLOCK',
            'createHash("sha256").update(ca).digest("hex") !== expected',
            'tls: { ca, rejectUnauthorized: true }',
            'Effect.orDie(Effect.try({ try: exclusiveRequestInit, catch: normalizeExclusiveCaError }))',
            'Effect.provideService(response, FetchHttpClient.RequestInit, requestInit)',
            'OPENCODE_EXCLUSIVE_CA_REJECT:',
        )) and 'yield* Effect.sync(exclusiveRequestInit)' not in patch_source
        checks.append({'name': 'native HTTP patch uses a required fixed replacement CA',
                       'pass': patch_shape})
        if not patch_shape:
            raise AssertionError('exclusive_patch_shape')

        exclusive = load_exclusive_checker()
        exclusive.self_test()
        checks.append({'name': 'exclusive trust receipt evaluator passes its offline self-test',
                       'pass': True})

        exclusive_source = EXCLUSIVE_CHECKER.read_text()
        cleanup_and_identity_shape = all(fragment in exclusive_source for fragment in (
            'def _exact_absence_claim(',
            'def _stdout_proves_no_objects(',
            'return len(lines) == 1 and lines[0] in expected',
            'post_remove_engine_responding',
            'prior_remove_reverified',
            '_fsync_directory(parent)',
            'def _remove_workspace_durably(',
            'sync(path.parent)',
            'def _run_passes(',
            'path.lstat()',
            'create_result_unconfirmed',
            "'cleanup_recovery':",
            'def _begin_create(',
            'create_journal.append(record)',
            'def _confirm_create(',
            'def _create_journal_confirmed(',
            "'create_journal': create_journal",
            "'retained_temporary_workspace': str(work)",
            'def _require_fixture_identities(',
            'def _mounted_ca_hashes(',
            "'ambient_ca_sha256': mounted_before['ambient']",
            "'mounted_ca_hashes_stable': True",
            "'structured_rejection_verified': True",
            "'server_alive_after_rejection': True",
            "'baseline_zero_verified': True",
            'def _observation_delta(',
            'ARM_MARKER_HEADER',
            "get('MemorySwap') != 1024 * 1024 * 1024",
            "get('LogConfig') != {",
        ))
        checks.append({'name': 'exclusive checker keeps exact cleanup and fixture identity proofs',
                       'pass': cleanup_and_identity_shape})
        if not cleanup_and_identity_shape:
            raise AssertionError('exclusive_cleanup_or_identity_shape')

        research = EXCLUSIVE_RESEARCH.read_text()
        contract = EXCLUSIVE_CONTRACT.read_text()
        documented_holds = all(fragment in research + '\n' + contract for fragment in (
            '843a6c514e606b436a7fe713422ace0a93ad3d61',
            '744846f844374847c902b5e7fd59b4342a51ef99',
            'cloud_live_route_not_qualified',
            'WebSocket',
            'AI SDK',
        ))
        checks.append({'name': 'exclusive trust sources pin identities and retain transport holds',
                       'pass': documented_holds})
        if not documented_holds:
            raise AssertionError('exclusive_trust_holds')

        private = temp / 'private'
        private.mkdir(mode=0o700)
        snapshot = module.private_snapshot(private / 'runtime-ca.pem', ca.read_bytes())
        snapshot_ok = (snapshot.read_bytes() == ca.read_bytes()
                       and snapshot.stat().st_mode & 0o077 == 0)
        checks.append({'name': 'validated bytes use a private exact snapshot', 'pass': snapshot_ok})
        if not snapshot_ok:
            raise AssertionError('runtime_ca_snapshot')
        plan = module.researcher_trust(True, snapshot, None)
        expected_mount = 'type=bind,src=' + str(snapshot) + ',dst=/fixture/runtime-ca.pem,readonly'
        check = (plan == {'mounts': [expected_mount],
                          'env': ['SSL_CERT_FILE=/fixture/runtime-ca.pem'],
                          'container_path': '/fixture/runtime-ca.pem'})
        checks.append({'name': 'live trust plan is exact and read-only', 'pass': check})
        if not check:
            raise AssertionError('live_trust_plan')
        try:
            module.researcher_trust(True, None, None)
        except RuntimeError as error:
            missing_fails = str(error) == 'live_runtime_ca_unavailable'
        else:
            missing_fails = False
        checks.append({'name': 'live trust plan refuses missing snapshot', 'pass': missing_fails})
        if not missing_fails:
            raise AssertionError('missing_live_trust')

        identifier = 'container-id'
        requested_env = ['SSL_CERT_FILE=/fixture/runtime-ca.pem']
        for name, value in (('NODE_TLS_REJECT_UNAUTHORIZED', '0'),
                            ('GIT_SSL_NO_VERIFY', '1'),
                            ('SSLKEYLOGFILE', '/fixture/tls.keys')):
            info = {'Id': identifier, 'Image': 'sha256:' + 'b' * 64,
                    'State': {'Status': 'created'}, 'Mounts': [],
                    'Config': {'Image': 'sha256:' + 'b' * 64,
                               'Env': requested_env + [name + '=' + value]}}
            unexpected_rejected = not module.created_matches(
                info, identifier, [], requested_env, 'sha256:' + 'b' * 64)
            checks.append({'name': name + ' presence is rejected', 'pass': unexpected_rejected})
            if not unexpected_rejected:
                raise AssertionError('unexpected_trust_override_' + name.lower())

        database = temp / 'provider.sqlite3'
        with sqlite3.connect(database) as db:
            db.executescript('''
                CREATE TABLE pool(bytes INTEGER);
                INSERT INTO pool VALUES(9);
                CREATE TABLE tunnels(id INTEGER, phase TEXT, uploaded INTEGER, downloaded INTEGER);
                INSERT INTO tunnels VALUES(1, 'closed', 4, 5);
                CREATE TABLE events(kind TEXT);
                INSERT INTO events VALUES('closed');
            ''')
        without = module.provider_state(database, None)
        responder = type('Responder', (), {'rows': [1, 2], 'health_rows': 3})()
        with_owned = module.provider_state(database, responder)
        state_ok = (without['owned_responses'] is None and without['owned_health'] is None
                    and with_owned['owned_responses'] == 2 and with_owned['owned_health'] == 3
                    and module.owned_health_count(None) is None
                    and module.owned_health_count(responder) == 3
                    and without['charged_bytes'] == 9 and without['tunnels'] == [(1, 'closed', 4, 5)])
        checks.append({'name': 'provider state supports missing or owned responder', 'pass': state_ok})
        if not state_ok:
            raise AssertionError('provider_state')

        ca_text = ca.read_text()
        private_key_present = any(marker in ca_text for marker in
                                  ('-----BEGIN PRIVATE KEY-----',
                                   '-----BEGIN RSA PRIVATE KEY-----',
                                   '-----BEGIN EC PRIVATE KEY-----'))
        receipt = {'schema_version': 1, 'kind': 't02-live-preparation-unobserved-core',
                   'status': 'unobserved', 'observation_complete': False,
                   'classification': 'offline source and parameter validation',
                   'checks': checks,
                   'source_sha256': {'runner': sha(RUNNER), 'checker': sha(Path(__file__)),
                                     'manifest': sha(CURRENT_MANIFEST),
                                     'exclusive_checker': sha(EXCLUSIVE_CHECKER),
                                     'exclusive_patch': sha(EXCLUSIVE_PATCH),
                                     'exclusive_research': sha(EXCLUSIVE_RESEARCH),
                                     'exclusive_contract': sha(EXCLUSIVE_CONTRACT)},
                   'synthetic_ca': {'sha256': ca_sha, 'bytes': ca.stat().st_size,
                                    'certificate_count': ca_text.count('-----BEGIN CERTIFICATE-----'),
                                    'private_key_present': private_key_present},
                   'docker_called': False,
                   'live_gate': 'cloud_live_route_not_qualified'}
        if private_key_present:
            raise AssertionError('synthetic_ca_contains_private_key')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
