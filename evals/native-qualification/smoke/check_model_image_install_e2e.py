#!/usr/bin/env python3
"""Failure-first model-image packaging through the public installer CLI.

Owned localhost assets contain synthetic ELF headers, never native executables.
No Docker/build/provider call is made. The two size-bound cases run the same CLI
with the general archive ceiling reduced to 256 bytes in an isolated subprocess.
This proves limit selection without allocating or downloading a 288 MB fixture.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import zipfile

from check_native_tool_install_e2e import elf, tar

ROOT = Path(__file__).resolve().parents[3]
BASE = 'python@sha256:' + 'a' * 64
HELPERS = ('engagement_network_bridge.py', 'native_runtime_bootstrap.py')


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def run(base):
    assets, requests = {}, []
    class Server(BaseHTTPRequestHandler):
        def log_message(self, *args):pass
        def do_GET(self):
            requests.append(self.path)
            content = assets[self.path]
            self.send_response(200)
            if not self.path.endswith('no-length'):
                self.send_header('Content-Length', str(len(content) + (50 if self.path.endswith('truncated') else 0)))
            self.end_headers()
            self.wfile.write(content)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fixture_repo = base / 'repository'
    tools = fixture_repo / 'tools'; tools.mkdir(parents=True)
    for name in ('install_native_tools.py', 'engagement_contract.py', 'engagement_records.py',
                 'operator_signature.py', 'native_runtime_transport.py'):
        shutil.copyfile(ROOT / 'tools' / name, tools / name)
    for name in (*HELPERS, 'native_runtime_codex_exec.mjs'):
        (tools / name).write_text('# frozen packaging fixture for ' + name + '\n')
    wrapper = tools / 'scaled_limit.py'
    wrapper.write_text('import install_native_tools as installer\ninstaller.MAX_ARCHIVE = 256\nraise SystemExit(installer.main())\n')

    def asset(name, content, **fields):
        assets['/' + name] = content
        return {'url': 'http://127.0.0.1:' + str(server.server_port) + '/' + name,
                'integrity': sha(content), **fields}

    def lock(platform, name):
        machine = 183 if platform == 'linux/arm64' else 62
        binary = elf(machine)
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, 'w') as archive:
            archive.writestr('bun/bun', binary)
        raw = binary + b'\0' * 492
        return {'kind': 'native-tool-installation-lock-v1', 'codex_version': '0.166.0',
                'omp_version': '18.20.0', 'bun_version': '1.4.4', 'platforms': {platform: {
                    'codex': asset(name + '-codex', tar({'codex': binary, 'codex-resources/bwrap': binary, 'codex-package.json': json.dumps({'version': '0.166.0',
                        'target': ('aarch64' if machine == 183 else 'x86_64') + '-unknown-linux-musl'}).encode()}), member='codex'),
                    'bun': asset(name + '-bun', zipped.getvalue(), member='bun/bun'),
                    'model_omp': asset(name + '-omp', raw, format='raw', size=len(raw))}}, 'packages': []}

    cases = [('codex-arm64', 'codex', 'linux/arm64'), ('codex-amd64', 'codex', 'linux/amd64'),
             ('omp-arm64', 'omp', 'linux/arm64'), ('omp-amd64', 'omp', 'linux/amd64')]
    failures = {'checksum': 'archive_digest_mismatch', 'raw-short': 'archive_size_mismatch',
        'raw-long': 'archive_size_mismatch', 'raw-no-length': 'archive_size_mismatch',
        'raw-invalid-size': 'model_asset_invalid', 'raw-format': 'model_asset_invalid',
        'truncated': 'archive_download_failed', 'wrong-platform': 'native_bundle_platform_mismatch',
        'wrong-bun-platform': 'native_bundle_platform_mismatch', 'missing-helper': 'model_helper_invalid',
        'helper-link': 'model_helper_invalid', 'existing': 'installation_destination_exists',
        'receipt-existing': 'installation_receipt_exists', 'receipt-alias': 'installation_receipt_inside_bundle',
        'base-tag': 'model_base_image_invalid', 'base-injection': 'model_base_image_invalid',
        'version': 'installation_version_unsupported', 'archive-limit': 'archive_too_large'}
    cases += [(name, 'codex' if name in ('wrong-bun-platform', 'archive-limit') else 'omp', 'linux/amd64')
              for name in failures]
    cases.append(('raw-over-general-limit', 'omp', 'linux/amd64'))
    checks = []
    try:
        for name, runtime, platform in cases:
            folder = base / name; folder.mkdir()
            destination, receipt = folder / 'context', folder / 'receipt.json'
            current = lock(platform, name)
            row = current['platforms'][platform]
            raw = row['model_omp']
            base_image = BASE
            helper = tools / HELPERS[1]
            original_helper = helper.read_bytes()
            if name == 'checksum':raw['integrity'] = 'sha256:' + '0' * 64
            if name == 'raw-short':raw['size'] += 1
            if name == 'raw-long':raw['size'] -= 1
            if name == 'raw-no-length':
                raw['url'] += '-no-length'
                assets['/' + name + '-omp-no-length'] = assets['/' + name + '-omp']
                raw['size'] += 1
            if name == 'raw-invalid-size':raw['size'] = True
            if name == 'raw-format':raw['format'] = 'tar'
            if name == 'truncated':
                raw['size'] += 50
                raw['url'] += '-truncated'
                assets['/' + name + '-omp-truncated'] = assets['/' + name + '-omp']
            if name == 'wrong-platform':
                content = elf(183)
                row['model_omp'] = asset(name + '-wrong', content, format='raw', size=len(content))
            if name == 'wrong-bun-platform':
                row['bun'] = asset(name + '-wrong', tar({'bun': elf(183)}), member='bun')
            if name == 'missing-helper':helper.unlink()
            if name == 'helper-link':
                helper.unlink(); helper.symlink_to(tools / HELPERS[0])
            if name == 'existing':
                destination.mkdir(); (destination / 'keep').write_text('untouched')
            if name == 'receipt-existing':receipt.write_text('untouched')
            if name == 'receipt-alias':
                (folder / 'alias').symlink_to(destination); receipt = folder / 'alias/receipt.json'
            if name == 'base-tag':base_image = 'python:latest'
            if name == 'base-injection':base_image = BASE + '\nRUN echo forbidden'
            if name == 'version':current['omp_version'] = '18.19.0'
            if name == 'archive-limit':
                row['codex'] = asset(name + '-large', b'x' * 512, member='codex')
            pin = folder / 'lock.json'; pin.write_text(json.dumps(current))
            arguments = ['model-image-context', '--runtime', runtime, '--platform', platform,
                '--base-image', base_image, '--destination', str(destination), '--receipt', str(receipt), '--lock', str(pin)]
            try:
                command = [sys.executable, str(wrapper if name in ('raw-over-general-limit', 'archive-limit')
                                              else tools / 'install_native_tools.py'), *arguments]
                completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
                document = json.loads(completed.stdout) if completed.stdout else {}
                if name in failures:
                    assert completed.returncode != 0 and document.get('error') == failures[name], completed.stdout + completed.stderr
                    if name == 'receipt-existing':assert receipt.read_text() == 'untouched'
                    else:assert not receipt.exists(), 'failure published receipt'
                    if name == 'existing':assert (destination / 'keep').read_text() == 'untouched'
                    else:assert not destination.exists(), 'partial context retained'
                else:
                    assert completed.returncode == 0, completed.stdout + completed.stderr
                    assert document == json.loads(receipt.read_bytes())
                    assert document['kind'] == 'native-model-image-context-receipt-v1'
                    assert document['status'] == 'prepared' and document['execution_verified'] is False
                    assert document['base_image'] == BASE and document['platform'] == platform
                    assert document['lock_sha256'] == sha(pin.read_bytes())
                    expected = {'bin/model', *HELPERS}
                    if runtime == 'codex':expected |= {'bin/bun', 'native_runtime_codex_exec.mjs', 'codex-package.json', 'codex-resources/bwrap'}
                    manifest = document['runtime_manifest']
                    assert set(manifest) == expected
                    executable = document['profile_fields']['executable']
                    assert executable == {'path': str(destination / 'runtime/bin/model'),
                                          'sha256': sha((destination / 'runtime/bin/model').read_bytes())}
                    for relative in expected:
                        path = destination / 'runtime' / relative
                        assert manifest[relative]['sha256'] == sha(path.read_bytes())
                        assert stat.S_IMODE(path.stat().st_mode) == (0o555 if (relative.startswith('bin/') or relative == 'codex-resources/bwrap') else 0o444)
                    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
                    assert all(stat.S_IMODE(path.stat().st_mode) == 0o755 for path in
                               (destination / 'runtime', destination / 'runtime/bin'))
                    if runtime == 'codex':assert stat.S_IMODE((destination / 'runtime/codex-resources').stat().st_mode) == 0o755
                    dockerfile = (destination / 'Dockerfile').read_text()
                    assert dockerfile.splitlines()[0] == 'FROM ' + BASE
                    assert 'COPY --chown=0:0 runtime/ /runtime/' in dockerfile
                    assert set(line.split()[0] for line in dockerfile.splitlines()) <= {'FROM', 'COPY', 'ENV', 'ENTRYPOINT', 'CMD', 'USER', 'WORKDIR'}
                    assert 'ENTRYPOINT []' in dockerfile and 'CMD ["/bin/true"]' in dockerfile
                    assert set(path.name for path in destination.iterdir()) == {'runtime', 'Dockerfile', '.dockerignore'}
                    assert '.model' not in set(path.name for path in destination.iterdir())
                    assert document['context_manifest_sha256'].startswith('sha256:')
                    for helper_name in expected - {'bin/model', 'bin/bun', 'codex-package.json', 'codex-resources/bwrap'}:
                        assert (destination / 'runtime' / helper_name).read_bytes() == (tools / helper_name).read_bytes()
                assert not any(folder.glob('.oslit-download-*')), 'temporary acquisition left behind'
                checks.append({'name': name, 'status': 'passed'})
            except Exception as error:
                checks.append({'name': name, 'status': 'failed', 'error': str(error)})
            finally:
                if helper.is_symlink():helper.unlink()
                helper.write_bytes(original_helper)
    finally:
        server.shutdown(); server.server_close()
    return {'status': 'passed' if all(row['status'] == 'passed' for row in checks) else 'failed',
            'classification': 'engineering_model_packaging_fixture', 'checks': checks,
            'acquisition': 'owned localhost synthetic ELF fixtures', 'provider_calls': 0,
            'docker_calls': 0, 'native_execution': 'not_run', 'fixture_request_count': len(requests),
            'source_sha256': sha((ROOT / 'tools/install_native_tools.py').read_bytes())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='model-image-install-check-') as root:
        result = run(Path(root).resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(result['status'] != 'passed')
