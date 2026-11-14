#!/usr/bin/env python3
"""Failure-first public installer workflows using owned archive fixtures.

Scenarios: both fixed layouts pass inspectors; no package script executes;
changed archive, changed installed tree, wrong ELF platform, stale Bun version,
traversal, archive links, truncated download and existing destination all fail
without replacing a prior installation or publishing a readiness receipt.
Fixture headers establish packaging mechanics only, never Linux execution.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import zipfile

ROOT = Path(__file__).resolve().parents[3]


def elf(machine=183):
    return b'\x7fELF\x02\x01' + b'\0' * 12 + machine.to_bytes(2, 'little')


def tar(files, *, link=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, data in files.items():
            row = tarfile.TarInfo(name)
            row.size, row.mode = len(data), 0o755
            archive.addfile(row, io.BytesIO(data))
        if link:
            row = tarfile.TarInfo('package/link')
            row.type, row.linkname = tarfile.SYMTYPE, link
            archive.addfile(row)
    return output.getvalue()


def zip_bun():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('bun-linux-aarch64/bun', elf())
    return output.getvalue()


def run(base):
    data = {}
    class Server(BaseHTTPRequestHandler):
        def log_message(self, *args):pass
        def do_GET(self):
            content = data[self.path]
            self.send_response(200)
            self.send_header('Content-Length', str(len(content) + (50 if self.path.endswith('truncated') else 0)))
            self.end_headers()
            self.wfile.write(content)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    def artifact(path, content, **fields):
        data[path] = content
        return {'url': 'http://127.0.0.1:' + str(server.server_port) + path,
                'integrity': 'sha256:' + hashlib.sha256(content).hexdigest(), **fields}
    def lock():
        return {'kind': 'native-tool-installation-lock-v1', 'codex_version': '0.166.0',
            'omp_version': '18.20.0', 'bun_version': '1.4.4', 'platforms': {'linux/arm64': {
                'codex': artifact('/codex.tgz', tar({'codex-linux': elf()}), member='codex-linux'),
                'bun': artifact('/bun.zip', zip_bun(), member='bun-linux-aarch64/bun')}},
            'packages': [artifact('/sdk.tgz', tar({'package/package.json': json.dumps({
                'name': '@oh-my-pi/pi-coding-agent', 'version': '18.20.0', 'engines': {'bun': '>=1.4.4'},
                'scripts': {'postinstall': 'touch ' + str(base / 'SCRIPT_EXECUTED')}}).encode(),
                'package/src/sdk.ts': b'// owned fixture only'}),
                destination='node_modules/@oh-my-pi/pi-coding-agent', name='@oh-my-pi/pi-coding-agent', version='18.20.0'),
                artifact('/addon.tgz', tar({'package/package.json': json.dumps({
                    'name': '@oh-my-pi/pi-natives-linux-arm64', 'version': '18.20.0',
                    'main': './pi_natives.linux-arm64.node'}).encode(), 'package/pi_natives.linux-arm64.node': elf()}),
                destination='node_modules/@oh-my-pi/pi-natives-linux-arm64', name='@oh-my-pi/pi-natives-linux-arm64', version='18.20.0')]}
    def cli(*arguments):
        process = subprocess.run([sys.executable, str(ROOT / 'tools/install_native_tools.py'), *arguments],
            capture_output=True, text=True, timeout=15)
        return process, json.loads(process.stdout) if process.stdout else {}
    rows = []
    try:
        for name in ('codex', 'omp', 'checksum', 'traversal', 'link', 'wrong-platform', 'bun-version', 'truncated', 'existing', 'receipt-alias'):
            root = base / name
            root.mkdir()
            current = lock()
            runtime = 'omp' if name in ('omp', 'traversal', 'link', 'bun-version') else 'codex'
            destination, receipt, pin = root / 'bundle', root / 'receipt.json', root / 'lock.json'
            if name == 'checksum':current['platforms']['linux/arm64']['codex']['integrity'] = 'sha256:' + '0' * 64
            if name == 'traversal':current['packages'][0] = artifact('/bad.tgz', tar({'package/../../ESCAPE': b'no'}), **{k:current['packages'][0][k] for k in ('destination','name','version')})
            if name == 'link':current['packages'][0] = artifact('/link.tgz', tar({}, link='/tmp'), **{k:current['packages'][0][k] for k in ('destination','name','version')})
            if name == 'wrong-platform':current['platforms']['linux/arm64']['codex'] = artifact('/wrong.tgz', tar({'codex-linux': elf(62)}), member='codex-linux')
            if name == 'bun-version':current['bun_version'] = '1.4.0'
            if name == 'truncated':current['platforms']['linux/arm64']['codex'] = artifact('/truncated', tar({'codex-linux': elf()}), member='codex-linux')
            if name == 'existing':
                destination.mkdir()
                (destination / 'keep').write_text('untouched')
            if name == 'receipt-alias':
                (root / 'alias').symlink_to(destination)
                receipt = root / 'alias/receipt.json'
            pin.write_text(json.dumps(current))
            try:
                result, document = cli('install', '--runtime', runtime, '--platform', 'linux/arm64',
                    '--destination', str(destination), '--receipt', str(receipt), '--lock', str(pin))
                if name in ('codex', 'omp'):
                    assert result.returncode == 0, result.stdout + result.stderr
                    assert document['status'] == 'installed' and document['execution_verified'] is False
                    readback, report = cli('preflight', '--receipt', str(receipt))
                    assert readback.returncode == 0 and report['status'] == 'ready_for_environment_check'
                    assert not (base / 'SCRIPT_EXECUTED').exists(), 'package script executed'
                    binary = destination / ('bin/codex' if runtime == 'codex' else 'bin/bun')
                    binary.write_bytes(binary.read_bytes() + b'changed')
                    changed, report = cli('preflight', '--receipt', str(receipt))
                    assert changed.returncode != 0 and report['error'] == 'native_bundle_manifest_mismatch', changed.stdout
                else:
                    assert result.returncode != 0, 'invalid install accepted'
                    expected = {'checksum': 'archive_digest_mismatch', 'traversal': 'archive_path_invalid',
                        'link': 'archive_entry_invalid', 'wrong-platform': 'native_bundle_platform_mismatch',
                        'bun-version': 'installation_version_unsupported', 'truncated': 'archive_download_failed',
                        'existing': 'installation_destination_exists',
                        'receipt-alias': 'installation_receipt_inside_bundle'}[name]
                    assert document.get('error') == expected, result.stdout + result.stderr
                    assert not receipt.exists(), 'invalid receipt published'
                    if name == 'existing':assert (destination / 'keep').read_text() == 'untouched'
                    else:assert not destination.exists(), 'failed partial install retained as usable'
                    assert not (root / 'ESCAPE').exists()
                rows.append({'check': name, 'status': 'passed'})
            except Exception as error:
                rows.append({'check': name, 'status': 'failed', 'error': str(error)})
    finally:
        server.shutdown()
        server.server_close()
    return {'status': 'passed' if all(row['status'] == 'passed' for row in rows) else 'failed',
            'classification': 'engineering_archive_fixture', 'provider_calls': 0, 'linux_execution': 'not_run', 'checks': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-install-check-') as root:
        result = run(Path(root).resolve())
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    sys.exit(result['status'] != 'passed')
