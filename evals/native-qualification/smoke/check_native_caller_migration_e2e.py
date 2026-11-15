#!/usr/bin/env python3
"""Exercise public native engagement CLI routing without external services."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'tools/native_engagement.py'


def write_json(path: Path, value: dict) -> bytes:
    data = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    path.write_bytes(data)
    path.chmod(0o600)
    return data


def invoke(*args: str) -> tuple[int, str, str]:
    result = subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return result.returncode, result.stdout, result.stderr


def document(stdout: str) -> dict:
    try:
        value = json.loads(stdout)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'native-caller-migration-check-v1',
              'classification': 'local_cli_routing_simulation',
              'provider_calls': 0, 'target_calls': 0, 'docker_calls': 0,
              'ssh_calls': 0, 'checks': []}

    def record(name: str, ok: bool, detail: str = '') -> None:
        result['checks'].append({'name': name, 'status': 'passed' if ok else 'failed',
                                 **({'detail': detail[:1000]} if detail else {})})

    with tempfile.TemporaryDirectory(prefix='native-caller-migration-') as tmp:
        base = Path(tmp).resolve()
        # Help must describe the default v2 public route and its preserved v1 route.
        code, stdout, stderr = invoke('--help')
        help_text = stdout + stderr
        expected_commands = ('inspect', 'run', 'status', 'direction', 'resume', 'stop', 'export')
        record('default_help_lists_v2_commands', code == 0 and all(x in help_text for x in expected_commands),
               help_text)
        record('default_help_exposes_legacy_route', code == 0 and 'v1' in help_text.lower(), help_text)

        # Kind alone selects v2; invalid inputs must fail before a root or legacy state exists.
        v2_inputs = base / 'incomplete-v2.json'
        write_json(v2_inputs, {'kind': 'native-engagement-inputs-v2'})
        v2_root = base / 'v2-run'
        code, stdout, stderr = invoke('run', f'--inputs={v2_inputs}', f'--engagement-root={v2_root}')
        body = document(stdout)
        record('equals_form_v2_inputs_select_v2_and_fail_closed',
               code == 2 and body.get('status') == 'rejected'
               and body.get('code') not in ('engagement_inputs_invalid', 'input_file_invalid')
               and not v2_root.exists(), stdout + stderr + f' root_exists={v2_root.exists()}')

        # Malformed input cannot be guessed as v1 or initialize a v1 state file.
        malformed = base / 'malformed.json'
        malformed.write_text('{')
        malformed.chmod(0o600)
        malformed_root = base / 'malformed-run'
        code, stdout, stderr = invoke('run', f'--inputs={malformed}', f'--engagement-root={malformed_root}')
        body = document(stdout)
        record('malformed_equals_form_input_rejects_without_legacy_init',
               code == 2 and body.get('status') == 'rejected'
               and body.get('code') not in ('input_json_invalid', 'engagement_inputs_invalid')
               and not malformed_root.exists(),
               stdout + stderr + f' root_exists={malformed_root.exists()}')

        # Construct a minimal v1 input accepted by the old driver parser. Deliberately
        # invalid trust/runtime material stops during provider-free prepare validation.
        old = base / 'v1'
        old.mkdir(mode=0o700)
        source = old / 'source'
        source.mkdir(mode=0o700)
        (source / 'README').write_text('harmless source fixture\n')
        brief = old / 'brief.md'
        brief.write_text('Inspect harmless source bytes.\n')
        scope = old / 'scope.md'
        scope.write_text('```native-engagement-scope-v1\n{"kind":"native-engagement-scope-v1"}\n```\n')
        signature = old / 'scope.sig'
        signers = old / 'allowed_signers'
        relay = old / 'relay'
        ca = old / 'ca.pem'
        catalog = old / 'catalog.json'
        for path, value in ((signature, b''), (signers, b''), (relay, b''), (ca, b''),
                            (catalog, b'{}')):
            path.write_bytes(value)
            path.chmod(0o600)
        inputs = old / 'inputs.json'
        write_json(inputs, {'kind': 'native-engagement-inputs-v1', 'source': str(source),
            'brief': str(brief), 'scope_file': str(scope), 'scope_signature': str(signature),
            'allowed_signers': str(signers), 'trusted_fingerprint': 'sha256:' + '0' * 64,
            'relay': str(relay), 'runtime_ca': str(ca), 'dependency_catalog': str(catalog)})
        for form, invocation in (
            ('separate', ('--inputs', str(inputs))),
            ('equals', (f'--inputs={inputs}',)),
        ):
            v1_root = old / f'engagement-{form}'
            code, stdout, stderr = invoke('run', *invocation, '--engagement-root', str(v1_root))
            try:
                state = json.loads((v1_root / 'state.json').read_bytes())
            except (OSError, ValueError):
                state = {}
            record(f'{form}_form_v1_inputs_keep_legacy_driver',
                   state.get('kind') == 'native-engagement-driver-v1'
                   and not (v1_root / 'events').exists(),
                   stdout + stderr + f" state_kind={state.get('kind')} phase={state.get('phase')}")

        equals_root = old / 'equals-status'
        equals_root.mkdir(mode=0o700)
        raw_inputs = b'{"legacy":true}\n'
        inputs_bytes = equals_root / 'inputs.json'
        inputs_bytes.write_bytes(raw_inputs)
        inputs_bytes.chmod(0o600)
        write_json(equals_root / 'state.json', {'kind': 'native-engagement-driver-v1',
            'phase': 'initialized', 'pending': None,
            'inputs_sha256': hashlib.sha256(raw_inputs).hexdigest(),
            'scope_sha256': 'a' * 64, 'error': None, 'cleanup': None})
        code, stdout, stderr = invoke('status', f'--engagement-root={equals_root}')
        body = document(stdout)
        record('equals_form_state_only_root_keeps_legacy_reader',
               code == 0 and body.get('status') == 'initialized'
               and not (equals_root / 'contract').exists() and not (equals_root / 'events').exists(),
               stdout + stderr)

        conflict = old / 'conflicting-root'
        conflict.mkdir(mode=0o700)
        write_json(conflict / 'state.json', {'kind': 'native-engagement-driver-v1'})
        (conflict / 'events').mkdir(mode=0o700)
        code, stdout, stderr = invoke('status', '--engagement-root', str(conflict))
        body = document(stdout)
        record('mixed_v1_v2_root_is_rejected',
               code == 2 and body.get('status') == 'rejected'
               and body.get('code') == 'route_conflict', stdout + stderr)

    result['status'] = ('passed' if all(row['status'] == 'passed' for row in result['checks'])
                        else 'failed')
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    args.output.chmod(0o600)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
