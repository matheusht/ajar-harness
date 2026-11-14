#!/usr/bin/env python3
"""Build and inspect one owned model image on an explicitly selected native Linux host.

The caller supplies an already installed digest-pinned base and a NEW directory.
Release acquisition uses the production installer. Native processes never start.
Keep the context/executable for runtime profile checks; cleanup removes only the
owned probe and built image. The three public functions support a later runtime
E2E within the same invocation, with cleanup deferred until that caller finishes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_contract import ContractError, safe_publication

BUILD_TIMEOUT = 300
LABEL = 'io.oslit.model-image-fixture'


@dataclass
class ImageFixture:
    runtime: str
    platform: str
    base_image: str
    endpoint: str
    directory: Path
    result: dict
    docker: str
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex)
    daemon_id: str = ''
    base_id: str = ''
    image_id: str = ''
    probe_id: str = ''
    context_receipt: dict = field(default_factory=dict)
    images_before: set = field(default_factory=set)
    containers_before: set = field(default_factory=set)
    build_started: bool = False
    uncertain: bool = False

    @property
    def tag(self):return 'oslit-model-check:' + self.nonce

    @property
    def probe_name(self):return 'oslit-model-probe-' + self.nonce


def check(result, name, condition):
    result.setdefault('checks', []).append({'name': name, 'passed': bool(condition)})
    if not condition:raise RuntimeError(name)


def call(fixture, *arguments, required=True, timeout=15, mutation=False):
    command = [fixture.docker, '--host', fixture.endpoint, *arguments]
    record = {'arguments': list(arguments)}
    fixture.result.setdefault('commands', []).append(record)
    try:
        response = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if mutation:fixture.uncertain = True
        record['status'] = 'timeout'
        raise RuntimeError('docker_command_timeout') from None
    record['returncode'] = response.returncode
    if mutation and response.returncode:fixture.uncertain = True
    if required and response.returncode:
        try:record['error'] = safe_publication(response.stderr[:2048]).decode('utf-8', 'replace')
        except ContractError:record['error'] = 'diagnostic_redacted'
        raise RuntimeError('docker_command_failed:' + arguments[0])
    return response


def inspect(fixture, kind, identity):
    response = call(fixture, kind, 'inspect', identity, required=False)
    if response.returncode:return None
    rows = json.loads(response.stdout)
    if len(rows) != 1:raise RuntimeError('docker_inspect_ambiguous')
    return rows[0]


def identities(fixture, kind):
    return set(call(fixture, kind, 'ls', '--all', '--quiet', '--no-trunc').stdout.decode().split())


def prepare_image(*, runtime, platform, base_image, endpoint, directory, result):
    """Acquire/build one image; reconcile partial creation before propagating failure."""
    fixture = ImageFixture(runtime, platform, base_image, endpoint, Path(directory).absolute(), result,
                           shutil.which('docker') or '')
    result['identity'] = {'nonce': fixture.nonce, 'tag': fixture.tag, 'probe_name': fixture.probe_name,
                          'directory': str(fixture.directory), 'endpoint': endpoint}
    try:
        native = {'x86_64': 'linux/amd64', 'aarch64': 'linux/arm64', 'arm64': 'linux/arm64'}
        check(result, 'native Linux host matches requested architecture',
              host_platform.system() == 'Linux' and native.get(host_platform.machine()) == platform)
        check(result, 'runtime and local Docker endpoint are explicit', runtime in ('codex', 'omp')
              and endpoint.startswith('unix:///') and bool(fixture.docker))
        check(result, 'base is a registry digest',
              re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}', base_image))
        check(result, 'artifact directory is new and canonical', not fixture.directory.exists()
              and not fixture.directory.is_symlink() and fixture.directory.parent.is_dir()
              and fixture.directory.parent.resolve() == fixture.directory.parent)
        fixture.daemon_id = call(fixture, 'info', '--format', '{{.ID}}').stdout.decode().strip()
        check(result, 'daemon reports an identity', bool(fixture.daemon_id))
        result['docker_version'] = json.loads(call(fixture, 'version', '--format', '{{json .}}').stdout)
        base = inspect(fixture, 'image', base_image)
        check(result, 'installed base has the exact digest and platform', base is not None
              and base_image in base.get('RepoDigests', [])
              and base['Os'] + '/' + base['Architecture'] == platform)
        check(result, 'base has no inherited build or runtime effects',
              not any(base['Config'].get(key) for key in ('OnBuild', 'Volumes', 'Healthcheck', 'ExposedPorts')))
        fixture.base_id = base['Id']
        result['identity'].update(daemon_id=fixture.daemon_id, base_id=fixture.base_id,
                                  base_image=base_image, platform=platform)
        fixture.images_before, fixture.containers_before = identities(fixture, 'image'), identities(fixture, 'container')
        fixture.directory.mkdir(mode=0o700)
        context, receipt = fixture.directory / 'context', fixture.directory / 'context-receipt.json'
        command = [sys.executable, str(ROOT / 'tools/install_native_tools.py'), 'model-image-context',
            '--runtime', runtime, '--platform', platform, '--base-image', base_image,
            '--destination', str(context), '--receipt', str(receipt)]
        installed = subprocess.run(command, capture_output=True, timeout=300)
        check(result, 'production context installer completed', installed.returncode == 0)
        fixture.context_receipt = json.loads(receipt.read_bytes())
        check(result, 'retained executable comes from the prepared receipt',
              fixture.context_receipt.get('kind') == 'native-model-image-context-receipt-v1'
              and fixture.context_receipt.get('runtime') == runtime
              and fixture.context_receipt.get('platform') == platform
              and fixture.context_receipt.get('base_image') == base_image
              and fixture.context_receipt['profile_fields']['executable']['path'] == str(context / 'runtime/bin/model'))
        result['installation'] = fixture.context_receipt
        fixture.build_started = True
        call(fixture, 'build', '--pull=false', '--network', 'none', '--platform', platform,
             '--tag', fixture.tag, '--label', LABEL + '=' + fixture.nonce,
             '--iidfile', str(fixture.directory / 'image-id'), str(context), timeout=BUILD_TIMEOUT, mutation=True)
        fixture.image_id = (fixture.directory / 'image-id').read_text().strip()
        image = inspect(fixture, 'image', fixture.tag)
        check(result, 'built image has exact fresh identity and ownership', image is not None
              and re.fullmatch(r'sha256:[0-9a-f]{64}', fixture.image_id)
              and image['Id'] == fixture.image_id and fixture.image_id not in fixture.images_before
              and image['Config'].get('Labels', {}).get(LABEL) == fixture.nonce)
        result['identity']['image_id'] = fixture.image_id
        check(result, 'built image matches requested platform', image['Os'] + '/' + image['Architecture'] == platform)
        config = image['Config']
        check(result, 'model image has inert defaults and no inherited execution surfaces',
              not config.get('Entrypoint') and config.get('Cmd') == ['/bin/true']
              and config.get('User') == '1000:1000' and config.get('WorkingDir') == '/work'
              and not any(config.get(key) for key in ('Volumes', 'Healthcheck', 'OnBuild', 'ExposedPorts')))
        return fixture
    except BaseException:
        cleanup_image(fixture, result)
        raise


class BoundedReader:
    def __init__(self, stream, remaining):self.stream, self.remaining = stream, remaining
    def read(self, size):
        value = self.stream.read(min(size, self.remaining + 1))
        self.remaining -= len(value)
        if self.remaining < 0:raise RuntimeError('runtime_archive_oversize')
        return value


def verify_image(fixture, result):
    """Read back bytes and ownership from a stopped, never-started owned probe."""
    response = call(fixture, 'container', 'create', '--name', fixture.probe_name,
        '--label', LABEL + '=' + fixture.nonce, '--network', 'none', '--read-only',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '1000:1000',
        '--memory', '268435456', '--memory-swap', '268435456', '--cpus', '1', '--pids-limit', '32',
        fixture.image_id, mutation=True)
    fixture.probe_id = response.stdout.decode().strip()
    probe = inspect(fixture, 'container', fixture.probe_id)
    check(result, 'probe identity is exact and never started', probe is not None
          and probe['Id'] == fixture.probe_id and fixture.probe_id not in fixture.containers_before
          and probe['Image'] == fixture.image_id and probe['Config'].get('Labels', {}).get(LABEL) == fixture.nonce
          and probe['State']['Status'] == 'created' and not probe['State']['Running'] and probe['State']['Pid'] == 0)
    result['identity']['probe_id'] = fixture.probe_id
    config = probe['HostConfig']
    check(result, 'probe has no mounts or network and bounded unprivileged configuration',
          not probe.get('Mounts') and not config.get('Binds') and not config.get('PortBindings')
          and not config.get('Privileged') and config['NetworkMode'] == 'none' and config['ReadonlyRootfs']
          and config['Memory'] == config['MemorySwap'] == 268435456
          and config['NanoCpus'] == 1000000000 and config['PidsLimit'] == 32
          and config.get('CapDrop') == ['ALL'] and 'no-new-privileges' in config.get('SecurityOpt', []))
    expected = fixture.context_receipt['runtime_manifest']
    seen, directories, observed = set(), set(), {}
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([fixture.docker, '--host', fixture.endpoint, 'cp', fixture.probe_id + ':/runtime', '-'],
                                   stdout=subprocess.PIPE, stderr=errors)
        timer = threading.Timer(60, process.kill); timer.start()
        try:
            bounded = BoundedReader(process.stdout, sum(row['size'] for row in expected.values()) + 1024 * 1024)
            with tarfile.open(fileobj=bounded, mode='r|*') as archive:
                for row in archive:
                    name = row.name.rstrip('/')
                    if row.isdir():
                        if name not in ('runtime', 'runtime/bin') or name in directories or (row.mode, row.uid, row.gid) != (0o755, 0, 0):
                            raise RuntimeError('runtime_directory_mismatch')
                        directories.add(name); continue
                    relative = name.removeprefix('runtime/')
                    if not name.startswith('runtime/') or not row.isfile() or relative not in expected or relative in seen:
                        raise RuntimeError('runtime_entry_mismatch')
                    wanted = expected[relative]
                    if (row.size, row.mode, row.uid, row.gid) != (wanted['size'], wanted['mode'], 0, 0):
                        raise RuntimeError('runtime_metadata_mismatch')
                    checksum = hashlib.sha256()
                    with archive.extractfile(row) as stream:
                        while chunk := stream.read(1024 * 1024):checksum.update(chunk)
                    actual = 'sha256:' + checksum.hexdigest()
                    if actual != wanted['sha256']:raise RuntimeError('runtime_content_mismatch')
                    seen.add(relative); observed[relative] = {**wanted, 'uid': row.uid, 'gid': row.gid}
            if process.wait(timeout=5) != 0:raise RuntimeError('runtime_readback_failed')
        finally:
            timer.cancel()
            if process.poll() is None:process.kill()
            process.wait()
            process.stdout.close()
    check(result, 'runtime files match complete manifest and root ownership', set(expected) == seen
          and directories == {'runtime', 'runtime/bin'})
    result['runtime_readback'] = observed
    after = inspect(fixture, 'container', fixture.probe_id)
    check(result, 'readback did not start the probe', after['State']['Status'] == 'created'
          and not after['State']['Running'] and after['State']['Pid'] == 0)
    return observed


def cleanup_image(fixture, result):
    """Preserve context and refuse removal when daemon/resource identity is uncertain."""
    cleanup = {'status': 'clean', 'removed': [], 'retained_directory': str(fixture.directory)}
    result['cleanup'] = cleanup
    if not fixture.build_started:return cleanup
    try:
        if call(fixture, 'info', '--format', '{{.ID}}').stdout.decode().strip() != fixture.daemon_id:
            raise RuntimeError('cleanup_daemon_mismatch')
        labeled = set(call(fixture, 'image', 'ls', '--all', '--quiet', '--no-trunc',
                           '--filter', 'label=' + LABEL + '=' + fixture.nonce).stdout.decode().split())
        found = {}
        for reference in {fixture.image_id, fixture.tag, *labeled} - {''}:
            candidate = inspect(fixture, 'image', reference)
            if candidate:found[candidate['Id']] = candidate
            elif reference in labeled:raise RuntimeError('cleanup_image_unreadable')
        if len(found) > 1:raise RuntimeError('cleanup_image_ambiguous')
        image = next(iter(found.values()), None)
        if image:
            if (image['Id'] in fixture.images_before or image['Config'].get('Labels', {}).get(LABEL) != fixture.nonce
                    or fixture.image_id and image['Id'] != fixture.image_id):
                raise RuntimeError('cleanup_image_mismatch')
            fixture.image_id = image['Id']; result['identity']['image_id'] = fixture.image_id
        found = {}
        for reference in {fixture.probe_id, fixture.probe_name} - {''}:
            candidate = inspect(fixture, 'container', reference)
            if candidate:found[candidate['Id']] = candidate
        if len(found) > 1:raise RuntimeError('cleanup_probe_ambiguous')
        probe = next(iter(found.values()), None)
        if probe:
            if (probe['Id'] in fixture.containers_before or probe['Config'].get('Labels', {}).get(LABEL) != fixture.nonce
                    or probe['Image'] != fixture.image_id or fixture.probe_id and probe['Id'] != fixture.probe_id
                    or probe['Name'].lstrip('/') != fixture.probe_name):
                raise RuntimeError('cleanup_probe_mismatch')
            fixture.probe_id = probe['Id']; result['identity']['probe_id'] = fixture.probe_id
            call(fixture, 'container', 'rm', fixture.probe_id, mutation=True)
            cleanup['removed'].append(fixture.probe_id)
        if image:
            call(fixture, 'image', 'rm', fixture.image_id, mutation=True)
            cleanup['removed'].append(fixture.image_id)
        images, containers = identities(fixture, 'image'), identities(fixture, 'container')
        if (fixture.image_id in images or fixture.probe_id in containers
                or not fixture.images_before <= images or not fixture.containers_before <= containers
                or fixture.base_id not in images):
            raise RuntimeError('cleanup_absence_or_preservation_unverified')
        if fixture.uncertain:raise RuntimeError('cleanup_request_completion_unknown')
    except Exception as error:
        cleanup.update(status='unresolved', error=str(error)); result['status'] = 'failed'
    return cleanup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('codex', 'omp'), required=True)
    parser.add_argument('--platform', choices=('linux/amd64', 'linux/arm64'), required=True)
    parser.add_argument('--base-image', required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'model-image-docker-e2e-v1', 'classification': 'actual_docker_model_packaging',
              'status': 'failed', 'checks': [], 'provider_calls': 0, 'native_execution': 'not_run'}
    fixture = None
    try:
        fixture = prepare_image(runtime=args.runtime, platform=args.platform, base_image=args.base_image,
                                endpoint=args.endpoint, directory=args.directory, result=result)
        verify_image(fixture, result)
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if fixture is not None:cleanup_image(fixture, result)
        result['source_sha256'] = 'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return result['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
