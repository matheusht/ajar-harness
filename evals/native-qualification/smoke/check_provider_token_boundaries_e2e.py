#!/usr/bin/env python3
"""Failure-first source-manifest and publication secret-boundary workflows.

Copy the two real SDK advisory files into a disposable source tree and admit its
manifest. Preserve rejection of standalone provider keys, quoted/punctuated keys,
keys in paths, embedded keys in credential assignments, other provider formats,
known-secret embeddings and file-stream chunk crossings. No real credentials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PROBE = '''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from engagement_records import detect_secret_classes,scan_file_secret_classes
from engagement_contract import ContractError,canonical,digest,safe_publication,source_manifest
path=Path(sys.argv[3]);mode=sys.argv[2]
try:
 if mode=='manifest':result={'status':'accepted','digest':digest(canonical(source_manifest(path)))}
 elif mode=='scan':result={'status':'rejected' if scan_file_secret_classes(path) else 'accepted'}
 else:
  content=path.read_bytes()
  safe_publication(content,known_secrets=(b'sk-'+b'Aa1_'*8,) if mode=='known' else ())
  result={'status':'accepted'}
except ContractError as error:result={'status':'rejected','code':str(error)}
print(json.dumps(result))
'''


def run(base, sdk):
    metadata = json.loads((sdk / 'package.json').read_bytes())
    assert metadata['name'] == '@oh-my-pi/pi-coding-agent' and metadata['version'] == '18.20.0'
    source = base / 'source'
    source.mkdir()
    files = []
    for name in ('task-specialization-advisory.md', 'task-coordination-advisory.md'):
        relative = Path('node_modules/@oh-my-pi/pi-coding-agent/src/prompts/tools') / name
        original = sdk / 'src/prompts/tools' / name
        copied = source / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copied)
        files.append({'path': str(relative), 'sha256': 'sha256:' + hashlib.sha256(original.read_bytes()).hexdigest()})
    cases = [('actual_sdk_manifest', 'manifest', source, 'accepted')]
    key = b'sk-' + b'Aa1_' * 8
    fixtures = [
        ('advisory_path', 'scan', str(source / files[0]['path']).encode(), 'accepted'),
        ('advisory_publication', 'public', b'Inspected task-specialization-advisory.md and task-coordination-advisory.md.', 'accepted'),
        ('standalone', 'scan', key, 'rejected'),
        ('quoted', 'scan', b'"' + key + b'"', 'rejected'),
        ('punctuation', 'scan', b'(' + key + b'),', 'rejected'),
        ('url_path', 'scan', b'https://invalid.example/' + key, 'rejected'),
        ('underscore_delimiter', 'scan', b'token_' + key, 'rejected'),
        ('credential_field', 'scan', b'{"api_key":"' + key + b'"}', 'rejected'),
        ('embedded_field', 'scan', b'{"api_key":"prefix' + key + b'"}', 'rejected'),
        ('embedded_environment_assignment', 'scan', b'OPENAI_API_KEY=prefix' + key, 'rejected'),
        ('embedded_access_assignment', 'scan', b'access_token=prefix' + key, 'rejected'),
        ('encoded_json_key', 'public', json.dumps({'text': key.decode()}).replace('s', '\\u0073', 1).encode(), 'rejected'),
        ('known_embedding', 'known', b'prefix' + key + b'suffix', 'rejected'),
        ('github_key', 'scan', b'ghp_' + b'A' * 24, 'rejected'),
        ('aws_key', 'scan', b'AKIA' + b'A' * 16, 'rejected'),
        ('chunk_boundary', 'scan', b'.' * (1024 * 1024 - 8) + key, 'rejected'),
    ]
    for name, mode, data, expected in fixtures:
        path = base / (name + '.txt')
        path.write_bytes(data)
        cases.append((name, mode, path, expected))
    checks = []
    for name, mode, path, expected in cases:
        process = subprocess.run([sys.executable, '-c', PROBE, str(ROOT / 'tools'), mode, str(path)],
            capture_output=True, text=True, timeout=10)
        result = json.loads(process.stdout) if process.stdout else {'status': 'unavailable'}
        checks.append({'check': name, 'status': 'passed' if process.returncode == 0 and result['status'] == expected else 'failed',
                       'expected': expected, 'observed': result['status']})
    return {'status': 'passed' if all(row['status'] == 'passed' for row in checks) else 'failed',
            'classification': 'actual_sdk_source_and_synthetic_secret_controls', 'sdk_files': files,
            'provider_calls': 0, 'real_credentials_used': False, 'checks': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--omp-sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='provider-token-boundaries-') as root:
        result = run(Path(root).resolve(), args.omp_sdk.resolve())
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'failed': [row['check'] for row in result['checks'] if row['status'] != 'passed']}))
    sys.exit(result['status'] != 'passed')
