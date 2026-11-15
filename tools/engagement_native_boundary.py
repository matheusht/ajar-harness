"""Host-owned native model, isolated tools, network gates, and evidence capture.

Worker requests cannot construct this boundary or select its controller principal.
The runtime owns model credentials; the environment owns uncredentialed tool effects.
"""
from __future__ import annotations

import base64
import copy
from contextlib import contextmanager
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

from engagement_contract import canonical, digest, read_bytes, read_json, source_manifest
from engagement_controller import ControllerError, instant, overlap
from engagement_lab_artifacts import select_effect as select_artifact_effect, execute_effect, cleanup_staging
from engagement_network import NetworkGate
from engagement_network_bridge import ProxyBridge
from research_environment import Environment
from native_runtime_transport import HostOperation, MAX_FRAME
from native_runtime_linux import LinuxModelOwner
from target_accounts import TargetAccountError, TargetAccountResolver
from acquisition_network import LabRequestBinder
from application_state import ApplicationOwner
from engagement_evidence import application_released
import native_runtime_codex as codex
import native_runtime_omp as omp


class BoundaryError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _credential_resolver():
    from native_credentials import HostCredentialResolver
    return HostCredentialResolver()


def _recover_owner(receipt, *, profile=None, maximum_lease_seconds=None):
    from native_runtime_owner import recover_runtime_owner
    if receipt.get('kind') == 'native-runtime-owner-v2':
        return recover_runtime_owner(receipt, profile=profile, maximum_lease_seconds=maximum_lease_seconds)
    return recover_runtime_owner(receipt)


def _inspect_bundle(profile, identity):
    return (codex if profile['kind'] == 'codex' else omp).inspect_tool_bundle(profile, identity)


def _guidance(contract):
    try:
        result = {name: contract.frozen_files[name] for name in ('methodology.md', 'protocol.md')}
        if any(type(content) is not bytes or not 0 < len(content) <= 1024 * 1024 for content in result.values()):
            raise ValueError()
        return result
    except (KeyError, AttributeError, ValueError):
        raise BoundaryError('native_engagement_guidance_unavailable') from None


def _origin(value):
    if isinstance(value, str):
        url = urlsplit(value)
        return url.scheme, url.hostname.lower(), url.port or (443 if url.scheme == 'https' else 80)
    return value['protocol'], value['host'], value['port']


def _routes(scope, resources):
    provider = {_origin(row) for row in scope['network']['provider']}
    target = {_origin(row) for row in scope['network']['target']}
    allowed_target = {_origin(row['identity']['base_url']) for row in scope['access']
        if row['id'] in resources and row['kind'] == 'application'}
    lab = {}
    for row in scope['network']['acquisition']:
        origin = _origin(row)
        if origin not in provider and (origin not in target or origin in allowed_target):
            lab[origin] = row
    for row in scope['network']['target']:
        origin = _origin(row)
        if origin in allowed_target and origin not in provider:
            lab[origin] = row
    return {'provider': copy.deepcopy(scope['network']['provider']),
            'lab': [copy.deepcopy(row) for row in lab.values()]}


def _result(value, *, error=False):
    return {'content': [{'type': 'text', 'text': canonical(value).decode()}], 'isError': error}


def _completed(value, *, error=False):
    response = _result(value, error=error)
    return HostOperation(lambda: response, lambda: None)


def _tool(name, description, properties, required):
    return {'name': name, 'description': description, 'inputSchema': {
        'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}


TOOLS = [
    _tool('engagement_status', 'Read your assignment, current authority and bounded shared evidence updates.',
        {'since': {'type': ['string', 'null']}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}, ['since', 'limit']),
    _tool('engagement_submit', 'Submit a typed request using your authenticated worker identity and the current revision.',
        {'request': {'type': 'object'}}, ['request']),
    _tool('engagement_read', 'Read a published evidence object or current ephemeral status view in byte ranges. Follow next_offset until null; default max_bytes is 65536.',
        {'sha256': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'},
         'offset': {'type': 'integer', 'minimum': 0},
         'max_bytes': {'type': 'integer', 'minimum': 1, 'maximum': 65536}}, ['sha256']),
    _tool('engagement_artifact', 'Freeze a file at a path relative to /work for publication; returns its publication path and digest.',
        {'path': {'type': 'string'}, 'max_bytes': {'type': 'integer', 'minimum': 1, 'maximum': 4194304}}, ['path', 'max_bytes']),
    _tool('engagement_capture', 'Run a pinned probe and candidate from paths relative to /work with a registered instrument in a separately reserved lab. Optional resources selects a nonempty subset of current authority. A fresh lab does not reset a remote application. seconds bounds the operation while short reservations renew. Returns protected execution, target request and output references.',
        {'instrument_id': {'type': 'string'}, 'candidate_path': {'type': 'string'}, 'probe_path': {'type': 'string'},
         'interpreter': {'type': ['string', 'null']}, 'arguments': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 64},
         'conditions': {'type': 'object'}, 'seconds': {'type': 'integer', 'minimum': 1},
         'resources': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'uniqueItems': True},
         'starting_state': {'type': 'object', 'additionalProperties': {'type': 'string'}, 'description': 'Optional map of every selected application access to its signed owned baseline. Recreates separate owned .invalid targets; omission makes no application clean-start claim.'},
         'artifact_effect_id': {'type': 'string', 'description': 'Optional signed owned-lab-state-v1 creation effect; separate from probe execution.'},
         'effect_id': {'type': 'string', 'description': 'Optional signed local effect for source/binary capture execution; later rungs require current evidence review. Application requests select their own effect.'},
         'patch_id': {'type': ['string', 'null']}, 'patch_arm': {'type': ['string', 'null']}},
        ['instrument_id', 'candidate_path', 'probe_path', 'interpreter', 'arguments', 'conditions', 'seconds', 'patch_id', 'patch_arm'])]


def _write(path, data, mode=0o600):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
    path.chmod(mode)


def _certificates(directory, hosts, *, lifetime_seconds):
    executable = shutil.which('openssl')
    if executable is None:
        raise BoundaryError('native_proxy_certificate_tool_unavailable')
    days = str(math.ceil(lifetime_seconds / 86400) + 1)
    hosts = sorted(set(hosts) | {'localhost'})
    san = []
    for host in hosts:
        try:
            ipaddress.ip_address(host)
            san.append('IP:' + host)
        except ValueError:
            if not re.fullmatch('[A-Za-z0-9.-]+', host):
                raise BoundaryError('native_proxy_certificate_host_invalid')
            san.append('DNS:' + host)
    ca, ca_key = directory / 'ca.pem', directory / 'ca.key'
    leaf, key, csr = directory / 'leaf.pem', directory / 'leaf.key', directory / 'leaf.csr'
    config = directory / 'certificate.cnf'
    _write(config, ('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ca\n'
        '[dn]\nCN=OSLit private worker authority\n[ca]\nbasicConstraints=critical,CA:TRUE\n'
        'keyUsage=critical,keyCertSign,cRLSign\n[leaf]\nbasicConstraints=critical,CA:FALSE\n'
        'keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n'
        'subjectAltName=' + ','.join(san) + '\n').encode())
    commands = [
        [executable, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', days,
         '-config', str(config), '-keyout', str(ca_key), '-out', str(ca)],
        [executable, 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-config', str(config),
         '-subj', '/CN=OSLit worker proxy',
         '-keyout', str(key), '-out', str(csr)],
        [executable, 'x509', '-req', '-sha256', '-days', days, '-in', str(csr), '-CA', str(ca),
         '-CAkey', str(ca_key), '-CAcreateserial', '-extfile', str(config), '-extensions', 'leaf', '-out', str(leaf)]]
    for command in commands:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=20, env={'PATH': '/usr/bin:/bin'})
        if result.returncode:
            raise BoundaryError('native_proxy_certificate_unavailable')
    for path in directory.iterdir():
        path.chmod(0o600)
    return ca, leaf, key


def _model_policy(provider_url, executor_url=None):
    ports = []
    for url in (provider_url, executor_url):
        if url is None:
            continue
        parsed = urlsplit(url)
        if parsed.hostname != '127.0.0.1' or not parsed.port:
            raise BoundaryError('native_host_endpoint_invalid')
        ports.append(parsed.port)
    policy = ('(version 1)(allow default)(deny network*)'
        '(allow network-bind (local ip "localhost:*"))'
        '(allow network-inbound (local ip "localhost:*"))')
    policy += ''.join(f'(allow network-outbound (remote ip "localhost:{port}"))' for port in sorted(set(ports)))
    return ['/usr/bin/sandbox-exec', '-p', policy]


def _clean_environment(proxy=None, *, omp_state=False):
    values = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'HOME': '/work', 'TMPDIR': '/tmp', 'LANG': 'C.UTF-8', **(proxy or {})}
    if omp_state:
        values['PI_CODING_AGENT_DIR'] = '/work/.omp'
    return ['/usr/bin/env', '-i', *[key + '=' + value for key, value in sorted(values.items())]]


class NativeBoundary:
    def __init__(self, context):
        self.context = context
        self.controller = context.controller
        self.scope = context.contract.scope
        self.runtime = self.native_owner = self.environment = self.proxy = None
        self.model_owner = self.model_proxy = None
        self.provider_gate = self.lab_gate = None
        self.owner_receipt = None
        self.execution_admitted = False
        self.artifact_effect = None
        self.status_read_view = None
        self.finished = None
        self.finish_lock = threading.Lock()
        self.capture_lock = threading.Lock()
        self.capture_cancel = None
        self.capture_done = None
        self.capture_application_active = False
        self.bootstrap = self.certificate = self.private_key = None
        self.credential_binding = None
        self.target_accounts = None
        self.network_operations = {}
        self.operations = {}
        self.operation_lock = threading.Lock()
        self.state_dir = self.socket_dir = None
        self.accesses = []
        self.routes = self.profile = None
        self.environment_id = self.environment_reference = self.environment_profile = None

    def _select_environment(self):
        kinds = {row['kind'] for row in self.accesses}
        for reference in self.scope['environments']:
            if not kinds <= set(reference['capabilities']):
                continue
            try:
                self._effect(reference['profile_id'], self.context.grant)
            except BoundaryError:
                continue
            profile = read_json(self.controller.root / 'contract/environments' / (reference['profile_id'] + '.json'), private=True)
            if profile['platform'] != self.context.contract.runtime_profiles[self.context.worker['profile_id']]['tool_bundle']['platform']:
                continue
            return reference['profile_id'], copy.deepcopy(reference), profile
        raise BoundaryError('native_environment_capability_unavailable')

    def _active(self):
        try:
            self.context.authorize()
            return True
        except Exception:
            return False

    def _effect(self, profile_id, grant):
        candidates = [row for row in self.scope['effects'] if profile_id in row['environment_ids']
            and set(grant['resources']) <= set(row['access_ids']) and not row['account_refs'] and row['kind'] == 'read'
            and row['rung'] in ('source_only', 'self')]
        if len(candidates) != 1:
            raise BoundaryError('native_effect_grant_unavailable')
        return candidates[0]['id']

    def _observe(self, observation):
        operation_id = observation['operation_id']
        with self.operation_lock:
            if observation['phase'] == 'intent' or operation_id not in self.operations:
                admitted = copy.deepcopy(self.context.grant)
                self.operations[operation_id] = admitted
            else:
                admitted = self.operations[operation_id]
        execution = observation['operation'] == 'execute' or (observation['operation'] == 'launch_stdio' and observation.get('role') == 'native_tools')
        return self.controller.record_environment_observation(admitted, self.environment_id, observation,
            effect_id=execute_effect(self.scope, admitted, self.environment_id) if self.artifact_effect and execution
                else self._effect(self.environment_id, admitted))

    def _environment_options(self):
        if self.environment_profile['ssh']:
            return {'known_hosts_file': self.controller.root / 'contract/environments' / (self.environment_id + '.known_hosts')}
        return {}

    def _application_connectors(self, resources, owners=None):
        managed = {row['access_id'] for row in self.scope.get('application_states', [])}
        result = {}
        for access in self.accesses:
            if access['id'] in resources and access['id'] in managed:
                scheme, host, port = _origin(access['identity']['base_url'])
                owner = (owners or {}).get(access['id'])
                result[f'{scheme}://{host}:{port}'] = owner.connect if owner is not None else None
        return result

    def _runtime_owner(self, receipt):
        self.controller.record_runtime_preparation_owner(self.context.grant, receipt)
        self.owner_receipt = copy.deepcopy(receipt)

    def _target_reference(self):
        value = os.environ.get('OSLIT_ACCOUNT_BINDINGS')
        if value is None:
            return None
        reference = Path(value)
        try:
            if not reference.is_absolute():
                raise ValueError()
            resolved = reference.resolve(strict=True)
        except (OSError, ValueError):
            raise BoundaryError('target_account_references_unavailable') from None
        protected = [self.controller.root, self.context.workspace]
        protected.extend(Path(value) for value in self.context.contract.inputs['access_files'].values())
        protected.extend(Path(profile['tool_bundle']['path']) for profile in self.context.contract.runtime_profiles.values())
        protected.extend(Path(worker['workspace']) for worker in self.controller.state()['workers'].values()
            if worker.get('workspace'))
        if any(overlap(resolved, path.resolve()) for path in protected):
            raise BoundaryError('target_account_references_exposed')
        return reference

    def _observe_network(self, observation):
        with self.controller.lock():
            operation_id = observation['operation_id']
            if observation['phase'] == 'intent':
                self._authorize_target()
                if self.environment is None or self.environment.identity is None:
                    raise BoundaryError('native_network_environment_unavailable')
                admitted = copy.deepcopy(self.context.grant)
                nonce = self.environment.receipt()['nonce']
            else:
                if operation_id not in self.network_operations:
                    raise BoundaryError('native_network_intent_missing')
                admitted, nonce = self.network_operations[operation_id]
            result = self.controller.record_network_observation(admitted, self.environment_id, nonce, observation)
            if observation['phase'] == 'intent':
                self.network_operations[operation_id] = (admitted, nonce)
            else:
                self.network_operations.pop(operation_id)
            return result

    def _authorize_target(self):
        with self.controller.lock():
            grant = self.context.authorize()
            if self.capture_application_active:
                raise BoundaryError('native_capture_target_busy')
            return grant

    def start(self):
        self.context.authorize()
        self.accesses = [copy.deepcopy(row) for row in self.scope['access'] if row['id'] in self.context.grant['resources']]
        self.routes = _routes(self.scope, self.context.grant['resources'])
        self.environment_id, self.environment_reference, self.environment_profile = self._select_environment()
        self.artifact_effect = select_artifact_effect(self.scope, self.context.grant, self.environment_id)
        if self.artifact_effect:
            execute_effect(self.scope, self.context.grant, self.environment_id)
        self.profile = copy.deepcopy(self.context.contract.runtime_profiles[self.context.worker['profile_id']])
        self.profile['config_file'] = str(self.controller.root / 'contract/runtimes' / (self.context.worker['profile_id'] + '.config'))
        self.profile['protocol']['schema_file'] = str(self.controller.root / 'contract/runtimes' / (self.context.worker['profile_id'] + '.schema'))
        if 'model_catalog' in self.profile:
            self.profile['model_catalog']['path'] = str(self.controller.root / 'contract/runtimes' / (self.context.worker['profile_id'] + '.models.yml'))
        if any(access['kind'] == 'application' for access in self.accesses):
            try:
                self.target_accounts = TargetAccountResolver(self._target_reference(), self.scope,
                    self._authorize_target, self._observe_network, environment_profile_id=self.environment_id)
            except TargetAccountError as error:
                raise BoundaryError(str(error)) from None
        bundle_id = 'native-runtime'
        bundle = _inspect_bundle(self.profile, bundle_id)
        guidance = _guidance(self.context.contract)
        workers = self.controller.root / 'workers'
        workers.mkdir(mode=0o700, exist_ok=True)
        self.state_dir = Path(tempfile.mkdtemp(prefix=self.context.worker['id'] + '-', dir=workers))
        self.socket_dir = Path(tempfile.mkdtemp(prefix='oslit-net-', dir='/tmp')).resolve()
        tls = self.state_dir / 'tls'; tls.mkdir(mode=0o700)
        ca, certificate, key = _certificates(tls, [row['host'] for rows in self.routes.values() for row in rows],
            lifetime_seconds=self.scope['limits']['hard']['worker_seconds'])
        bootstrap = self.state_dir / 'bootstrap'; bootstrap.mkdir(mode=0o700)
        _write(bootstrap / 'ca.pem', ca.read_bytes())
        _write(bootstrap / 'bridge.py', read_bytes(Path(__file__).with_name('engagement_network_bridge.py')))
        _write(bootstrap / 'goal.md', self.context.contract.goal_bytes)
        _write(bootstrap / 'scope.md', read_bytes(self.controller.root / 'contract/scope.md', private=True))
        for name, content in guidance.items():
            _write(bootstrap / name, content)
        self.bootstrap, self.certificate, self.private_key = bootstrap, certificate, key
        support = {'bootstrap': {'path': str(bootstrap), 'manifest_sha256': digest(canonical(source_manifest(bootstrap)))}}
        self.controller.register_support_inputs(self.context.grant, support)
        support[bundle_id] = bundle['support_input']
        maximum = self.environment_reference['limits']['output_bytes']
        self.provider_gate = NetworkGate(self.routes['provider'], self._active,
            maximum_bytes=max(maximum, 8 * 1024 * 1024), dispatch_guard=self.context.guard,
            request_observer=lambda observation: self.controller.record_provider_request(
                self.context.grant, observation))
        provider_url = None
        if 'model_host' in self.profile:
            self.provider_gate.serve(self.socket_dir / 'provider.sock', certificate=certificate, private_key=key)
        else:
            provider_address = self.provider_gate.serve_tcp(certificate=certificate, private_key=key)
            provider_url = f'http://127.0.0.1:{provider_address}'
        self.lab_gate = NetworkGate(self.routes['lab'], self._active, maximum_bytes=maximum,
            dispatch_guard=self.context.guard,
            request_binder=LabRequestBinder(self.scope, self.environment_id, self._authorize_target,
                self._observe_network, self.target_accounts).bind,
            target_connectors=self._application_connectors(self.context.grant['resources']))
        self.lab_gate.serve(self.socket_dir / 'lab.sock', certificate=certificate, private_key=key)
        self.controller.record_preparation_setup(self.context.grant)
        self.execution_admitted = True
        self.environment = Environment(self.environment_profile, self.environment_reference['limits'],
            self.context.authorize, self._observe, grant=self.context.grant,
            dispatch_guard=self.context.guard, lab_artifact=bool(self.artifact_effect),
            codex_tool_policy=(self.profile['kind'] == 'codex'
                and 'codex_tool_policy' in self.environment_profile), **self._environment_options())
        if self.artifact_effect:
            self.controller.record_lab_artifact_intent(self.context.grant, self.environment_id, self.artifact_effect,
                self.environment.allocation_identity())
        self.environment.prepare(self.accesses, self.context.contract.inputs['access_files'], support_inputs=support)
        if self.artifact_effect:
            self.controller.record_lab_artifact_ready(self.context.grant, self.environment_id, self.environment.artifact_state_readback())
        if 'model_host' in self.profile:
            self.model_owner = LinuxModelOwner(self.profile, self.context.assignment['profile_sha256'],
                self.context.grant, authorize=self.context.authorize, dispatch_guard=self.context.guard,
                observe_owner=self._runtime_owner, maximum_lease_seconds=self.scope['limits']['max_worker_lease_seconds'],
                support_directory=self.state_dir / 'model-input')
            self.model_owner.prepare(config_bytes=read_bytes(self.profile['config_file']), ca_bytes=ca.read_bytes())
        self.credential_binding = _credential_resolver()(self.profile)
        self.credential_binding.check()
        self.controller.record_native_admission(self.context.grant)
        self.proxy = ProxyBridge(lambda command: self.environment.launch_stdio(command, role='network_proxy'),
            _clean_environment() + ['python3', '-I', '-S', '/input/bootstrap/bridge.py', 'relay'],
            self.lab_gate, self._active, dispatch_guard=self.context.guard)
        tool_environment = self.proxy.environment('/input/bootstrap/ca.pem')
        if self.model_owner is not None:
            self.model_proxy = ProxyBridge(lambda command: self.model_owner.launch_support('provider_relay'), [],
                self.provider_gate, self._active, dispatch_guard=self.context.guard)
            model_environment = {key: value for key, value in self.model_proxy.environment(self.model_owner.paths.ca).items()
                                 if key.isupper()}
        else:
            model_environment = {'HTTP_PROXY': provider_url, 'HTTPS_PROXY': provider_url,
                'NO_PROXY': 'localhost,127.0.0.1,::1', 'SSL_CERT_FILE': str(ca),
                'CURL_CA_BUNDLE': str(ca), 'NODE_EXTRA_CA_CERTS': str(ca)}
        runtime_options = {'host_tools': TOOLS, 'host_call': self.host_call,
            'dispatch_guard': self.context.guard, 'protected_model': True,
            'profile_sha256': self.context.assignment['profile_sha256'],
            'credential_resolver': lambda profile: self.credential_binding, 'provider_environment': model_environment,
            'owner_observer': self._runtime_owner}
        if self.model_owner is not None:
            runtime_options['model_owner'] = self.model_owner
        if self.profile['kind'] == 'codex':
            self.native_owner = codex.NativeExecutor(launcher=lambda command: self.environment.launch_stdio(command, role='native_tools'),
                command=_clean_environment(tool_environment) + bundle['command'],
                environment_id=self.context.worker['id'] + '-' + str(self.context.worker['generation']),
                cwd='/work', dispatch_guard=self.context.guard, expected_platform=bundle['expected_platform'],
                expected_version=bundle['expected_version'], owner_observer=self._runtime_owner,
                profile_sha256=self.context.assignment['profile_sha256'],
                **({'model_owner': self.model_owner} if self.model_owner is not None else {}))
            runtime_options.update(native_executor=self.native_owner)
            if self.model_owner is None:
                runtime_options['command_prefix'] = _model_policy(provider_url, self.native_owner.url)
            self.runtime = codex.Runtime(self.profile, self.state_dir / 'model', self.context.workspace, **runtime_options)
        else:
            self.native_owner = omp.ToolOwner(bundle['sdk_dir'], self.context.workspace, self.state_dir / 'native-tools',
                sdk_pin=bundle['sdk_pin'], launcher=lambda command: self.environment.launch_stdio(command, role='native_tools'),
                command=_clean_environment(tool_environment, omp_state=True) + bundle['command'],
                target_platform=self.profile['tool_bundle']['platform'], expected_ready=bundle['expected_ready'],
                dispatch_guard=self.context.guard)
            runtime_options.update(host_tools=[*self.native_owner.catalog, *TOOLS])
            if self.model_owner is None:
                runtime_options['command_prefix'] = _model_policy(provider_url)
            self.runtime = omp.Runtime(self.profile, self.state_dir / 'model', self.context.workspace, **runtime_options)
        identity = self.runtime.fresh()
        self.owner_receipt = self.runtime.owner_receipt()
        return {'session_id': identity['session_id'], 'owner_receipt': self.owner_receipt}

    def renew(self, seconds):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            raise BoundaryError('native_renewal_invalid')
        self.context.authorize()
        if self.environment is None or self.finished is not None:
            raise BoundaryError('native_boundary_inactive')
        self.environment.grant = copy.deepcopy(self.context.grant)
        if self.model_owner is not None:
            self.model_owner.renew(self.context.grant, seconds)
        return self.environment.renew(seconds)

    def host_call(self, name, arguments):
        try:
            self.context.authorize()
            if name == 'engagement_status':
                return self._status(arguments)
            if name == 'engagement_submit':
                return _completed(self.context.submit(arguments['request']))
            if name == 'engagement_read':
                return self._read(arguments)
            if name == 'engagement_artifact':
                return HostOperation(lambda: self._artifact(arguments), self.environment.revoke)
            if name == 'engagement_capture':
                with self.context.guard():
                    return self._accept_capture(arguments)
            if self.profile['kind'] == 'omp' and self.native_owner is not None:
                return self.native_owner.host_call(name, arguments)
            raise BoundaryError('native_host_tool_unavailable')
        except (ControllerError, BoundaryError) as error:
            return _completed({'status': 'rejected', 'code': error.code}, error=True)

    def _status(self, arguments):
        self.status_read_view = None
        limit = arguments['limit']
        while True:
            page = self.controller.status(self.context.principal, since=arguments['since'], limit=limit)
            if len(canonical(_result(page))) <= MAX_FRAME // 2:
                return _completed(page)
            if limit > 1:
                limit = max(1, limit // 2)
                continue
            content = canonical(page)
            if len(content) > 4 * 1024 * 1024:
                raise BoundaryError('native_status_view_too_large')
            sha = digest(content)
            self.status_read_view = (sha, content)
            return _completed({'status': page['status'], 'revision': page['revision'],
                'ephemeral_read_view': {'sha256': sha, 'bytes': len(content),
                    'instruction': 'Read with engagement_read. The next engagement_status replaces this view; requery the same cursor if it expires.'},
                'since': arguments['since']})

    def _read(self, arguments):
        sha = arguments['sha256']
        if self.status_read_view is not None and sha == self.status_read_view[0]:
            content = self.status_read_view[1]
            source = 'ephemeral_status_view'
        else:
            if sha not in self.controller.state()['evidence_objects']:
                raise BoundaryError('native_evidence_object_unpublished')
            content = self.controller.read_object(sha)
            source = 'published_evidence'
        offset, size = arguments.get('offset', 0), arguments.get('max_bytes', 65536)
        if type(offset) is not int or not 0 <= offset <= len(content) or type(size) is not int or not 1 <= size <= 65536:
            raise BoundaryError('native_evidence_range_invalid')
        part = content[offset:offset + size]
        body = {'sha256': sha, 'source': source, 'offset': offset, 'bytes': len(part), 'total_bytes': len(content),
            'next_offset': offset + len(part) if offset + len(part) < len(content) else None}
        try:
            body.update(encoding='utf-8', content=part.decode('utf-8'))
        except UnicodeError:
            body.update(encoding='base64', content=base64.b64encode(part).decode())
        return _completed(body)

    def _artifact(self, arguments):
        observed = self.environment.read_artifact(arguments['path'], arguments['max_bytes'])
        content = observed['content']
        grant = self.operations[observed['operation_id']]
        self.controller.record_environment_output(grant, self.environment_id, observed['operation_id'], content)
        sha = self.controller.store_object(content)
        name = 'artifact-' + sha[7:]
        path = self.context.workspace / name
        if path.exists():
            if read_bytes(path, private=True, max_bytes=4 * 1024 * 1024) != content:
                raise BoundaryError('native_publication_path_conflict')
        else:
            _write(path, content)
        return _result({'path': name, 'sha256': sha, 'bytes': len(content), 'operation_id': observed['operation_id']})

    def _accept_capture(self, arguments):
        allowed = {None, 'python3', 'python', 'node', 'bash', 'sh', 'ruby', 'perl', 'php', 'lua', 'Rscript'}
        if arguments['interpreter'] not in allowed:
            raise BoundaryError('native_capture_interpreter_unsupported')
        if (not isinstance(arguments['arguments'], list) or len(arguments['arguments']) > 64 or
                any(not isinstance(value, str) or '\0' in value or len(value) > 8192 for value in arguments['arguments'])):
            raise BoundaryError('native_capture_arguments_invalid')
        seconds = arguments['seconds']
        if type(seconds) is not int or seconds <= 0:
            raise BoundaryError('native_capture_reservation_invalid')
        remaining = (instant(self.context.grant['lease_expires_at']) - self.controller.clock()).total_seconds()
        segment = min(seconds, self.scope['limits']['max_worker_lease_seconds'],
            self.environment_reference['limits']['lease_seconds'], math.floor(remaining))
        if segment < 1:
            raise BoundaryError('native_capture_parent_lease_short')
        state = self.controller.state()
        instrument = state['instruments'].get(arguments['instrument_id'])
        if instrument is None or instrument.get('superseded_by'):
            raise BoundaryError('native_capture_instrument_unavailable')
        resources = arguments.get('resources', self.context.grant['resources'])
        if (not isinstance(resources, list) or not resources or any(not isinstance(name, str) for name in resources)
                or len(resources) != len(set(resources)) or not set(resources) <= set(self.context.grant['resources'])):
            raise BoundaryError('native_capture_resources_invalid')
        applications = {row['id'] for row in self.accesses if row['id'] in resources and row['kind'] == 'application'}
        application = bool(applications)
        reset_profiles = {}
        if 'starting_state' in arguments:
            requested = arguments['starting_state']
            references = {row['access_id']: row for row in self.scope.get('application_states', [])}
            if (not applications or type(requested) is not dict or set(requested) != applications
                    or not applications <= set(references)):
                raise BoundaryError('native_capture_starting_state_invalid')
            for access_id, baseline in requested.items():
                reference = references[access_id]
                profile = read_json(self.controller.root / 'contract/applications' / (access_id + '.json'), private=True)
                if type(baseline) is not str or baseline != profile['baseline_id']:
                    raise BoundaryError('native_capture_starting_state_invalid')
                environment = next(row for row in self.scope['environments'] if row['profile_id'] == reference['environment_id'])
                reset_profiles[access_id] = (reference, profile, environment)
                segment = min(segment, environment['limits']['lease_seconds'])
        capture_grant = dict(self.context.grant, resources=resources)
        artifact_effect = select_artifact_effect(self.scope, capture_grant, self.environment_id, arguments.get('artifact_effect_id'))
        if 'effect_id' in arguments:
            effect = next((row for row in self.scope['effects'] if row['id'] == arguments['effect_id']), None)
            if (application or effect is None or effect['kind'] == 'artifact_create' or (artifact_effect and effect['kind'] != 'execute') or effect['account_refs']
                    or self.environment_id not in effect['environment_ids'] or not set(resources) <= set(effect['access_ids'])):
                raise BoundaryError('native_capture_effect_invalid')
            effect_id = effect['id']
        else:
            effect_id = execute_effect(self.scope, capture_grant, self.environment_id) if artifact_effect else self._effect(self.environment_id, capture_grant)
        if application and self.network_operations:
            raise BoundaryError('native_capture_target_busy')
        if (arguments['patch_id'] is None) != (arguments['patch_arm'] is None):
            raise BoundaryError('native_capture_patch_invalid')
        if arguments['patch_id'] is not None:
            patch = state['patches'].get(arguments['patch_id'])
            if patch is None or patch['source_access'] not in resources or arguments['patch_arm'] not in ('original', 'patched'):
                raise BoundaryError('native_capture_patch_invalid')
        if not self.capture_lock.acquire(blocking=False):
            raise BoundaryError('native_capture_already_active')
        try:
            grant = self.controller.prepare_capture_dispatch(self.context.grant, seconds=segment, resources=resources)
        except Exception:
            self.capture_lock.release()
            raise
        self.capture_application_active = application
        control = {'environment': None, 'application_owners': {}, 'reset_profiles': reset_profiles,
            'cancelled': threading.Event(), 'done': threading.Event(), 'effect_id': effect_id, 'artifact_effect': artifact_effect}
        def cancel():
            control['cancelled'].set()
            environment = control['environment']
            if environment is not None:
                environment.revoke()
            for owner in list(control['application_owners'].values()):
                owner.environment.revoke()
        self.capture_cancel, self.capture_done = cancel, control['done']
        return HostOperation(lambda: self._capture(arguments, instrument, grant, control), cancel)

    def _capture(self, arguments, instrument, grant, control):
        started = time.monotonic()
        environment = proxy = gate = directory = target_accounts = None
        cleanup = None
        artifact_nonce = None
        value = None
        failure = None
        executions, operations, network_operations = [], {}, {}
        owners = control['application_owners']
        application_cleanup = {}
        accesses = [row for row in self.accesses if row['id'] in grant['resources']]
        applications = {row['id'] for row in accesses if row['kind'] == 'application'}
        renewal_stopped, prepared = threading.Event(), threading.Event()
        renewal_failure = []
        deadline = started + arguments['seconds']
        def authorize():
            with self.controller.lock():
                self.controller.authorize_dispatch(grant)
                if control['cancelled'].is_set():
                    raise BoundaryError('native_capture_cancelled')
                return copy.deepcopy(grant)
        def active():
            try:
                authorize()
                return True
            except Exception:
                return False
        @contextmanager
        def guard():
            with self.controller.lock():
                authorize()
                yield
        def observe(observation):
            with self.controller.lock():
                operation_id = observation['operation_id']
                if observation['phase'] == 'intent' or operation_id not in operations:
                    operations[operation_id] = copy.deepcopy(grant)
                admitted = operations[operation_id]
                if observation['phase'] == 'intent' and observation['operation'] == 'execute':
                    executions.append(operation_id)
                return self.controller.record_environment_observation(admitted, self.environment_id, observation,
                    effect_id=control['effect_id'] if observation['operation'] == 'execute'
                    else self._effect(self.environment_id, admitted))
        def observe_network(observation):
            with self.controller.lock():
                operation_id = observation['operation_id']
                if observation['phase'] == 'intent':
                    admitted = authorize()
                    nonce = environment.receipt()['nonce']
                else:
                    admitted, nonce = network_operations[operation_id]
                owner = owners.get(observation.get('access_id'))
                target_nonce = owner.start_receipt['target_nonce'] if owner is not None else None
                result = self.controller.record_network_observation(admitted, self.environment_id, nonce, observation,
                    target_nonce=target_nonce)
                if observation['phase'] == 'intent':
                    network_operations[operation_id] = (admitted, nonce)
                else:
                    network_operations.pop(operation_id)
                return result
        def renew_capture():
            nonlocal grant
            renewal_window = grant['seconds']
            while not renewal_stopped.wait(.1):
                try:
                    with self.controller.lock():
                        authorize()
                        remaining = (instant(grant['lease_expires_at']) - self.controller.clock()).total_seconds()
                        if remaining > min(5, renewal_window / 2):
                            continue
                        available = deadline - time.monotonic()
                        if available <= 0:
                            raise BoundaryError('native_capture_deadline_expired')
                        parent = self.controller.state()['dispatches'][self.context.grant['dispatch_id']]
                        parent_remaining = (instant(parent['lease_expires_at']) - self.controller.clock()).total_seconds()
                        segment = min(math.ceil(available), self.scope['limits']['max_worker_lease_seconds'],
                            self.environment_reference['limits']['lease_seconds'], math.floor(parent_remaining))
                        if control['reset_profiles']:
                            segment = min(segment, *(row[2]['limits']['lease_seconds'] for row in control['reset_profiles'].values()))
                        if segment < 1:
                            raise BoundaryError('native_capture_parent_lease_short')
                        grant = self.controller.renew_dispatch(grant, seconds=segment)
                        renewal_window = segment
                        if environment is not None:
                            environment.grant = copy.deepcopy(grant)
                        for owner in list(owners.values()):
                            owner.environment.grant = copy.deepcopy(grant)
                    if prepared.is_set():
                        remaining = (instant(grant['lease_expires_at']) - self.controller.clock()).total_seconds()
                        environment.renew(min(remaining, self.environment_reference['limits']['lease_seconds']))
                    for access_id, owner in list(owners.items()):
                        if owner.start_receipt is not None:
                            remaining = (instant(grant['lease_expires_at']) - self.controller.clock()).total_seconds()
                            owner.renew(min(remaining, control['reset_profiles'][access_id][2]['limits']['lease_seconds']))
                except Exception as error:
                    renewal_failure.append(getattr(error, 'code', 'native_capture_renewal_unavailable'))
                    control['cancelled'].set()
                    if environment is not None:
                        try:
                            environment.revoke()
                        except Exception:
                            pass
                    return
        renewal = threading.Thread(target=renew_capture, daemon=True)
        renewal.start()
        try:
            authorize()
            environment = Environment(self.environment_profile, self.environment_reference['limits'], authorize,
                observe, grant=grant, dispatch_guard=guard, lab_artifact=bool(control['artifact_effect']), **self._environment_options())
            control['environment'] = environment
            if control['artifact_effect']:
                identity = environment.allocation_identity()
                self.controller.record_lab_artifact_intent(grant, self.environment_id, control['artifact_effect'], identity)
                artifact_nonce = identity['nonce']
            directory = Path(tempfile.mkdtemp(prefix='capture-', dir=self.state_dir))
            if artifact_nonce:
                paths = ['capture/instrument', 'capture/candidate', 'capture/probe']
                if arguments['patch_id'] is not None:
                    patch = self.controller.state()['patches'][arguments['patch_id']]
                    logical = json.loads(self.controller.read_object(patch[arguments['patch_arm'] + '_manifest_sha256']))
                    paths.extend('patch-source/' + name for name in logical)
                self.controller.record_artifact_staging(grant, artifact_nonce, directory, paths)
            capture = directory / 'capture'; capture.mkdir(mode=0o700)
            limit = min(4 * 1024 * 1024, self.environment_reference['limits']['output_bytes'])
            candidate = self.environment.read_artifact(arguments['candidate_path'], limit)
            probe = self.environment.read_artifact(arguments['probe_path'], limit)
            for observed in (candidate, probe):
                self.controller.record_environment_output(self.operations[observed['operation_id']],
                    self.environment_id, observed['operation_id'], observed['content'])
            instrument_bytes = self.controller.read_object(instrument['artifact_sha256'])
            _write(capture / 'instrument', instrument_bytes)
            _write(capture / 'candidate', candidate['content'])
            _write(capture / 'probe', probe['content'], mode=0o700)
            candidate_sha = self.controller.store_object(candidate['content'])
            probe_sha = self.controller.store_object(probe['content'])
            support = {'capture': {'path': str(capture), 'manifest_sha256': digest(canonical(source_manifest(capture)))},
                'bootstrap': {'path': str(self.bootstrap), 'manifest_sha256': digest(canonical(source_manifest(self.bootstrap)))}}
            if control['reset_profiles']:
                connector = directory / 'application-connector'; connector.mkdir(mode=0o700)
                _write(connector / 'bridge.py', read_bytes(self.bootstrap / 'bridge.py'))
                support['application-connector'] = {'path': str(connector), 'manifest_sha256': digest(canonical(source_manifest(connector)))}
            subjects = [row['identity']['base_url'] if row['kind'] == 'application' else '/input/' + row['id']
                for row in accesses]
            patch_manifest = None
            if arguments['patch_id'] is not None:
                patch = self.controller.state()['patches'][arguments['patch_id']]
                logical = json.loads(self.controller.read_object(patch[arguments['patch_arm'] + '_manifest_sha256']))
                source = directory / 'patch-source'; source.mkdir(mode=0o700)
                for name, row in logical.items():
                    path = source / name
                    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    content = self.controller.read_object(row['sha256'])
                    if len(content) != row['size']:
                        raise BoundaryError('native_capture_patch_changed')
                    _write(path, content, mode=row['mode'])
                if source_manifest(source) != logical:
                    raise BoundaryError('native_capture_patch_changed')
                support['patch-source'] = {'path': str(source), 'manifest_sha256': digest(canonical(logical))}
                patch_manifest = {name: dict(row, mode=0o555 if row['mode'] & 0o111 else 0o444) for name, row in logical.items()}
                subjects = ['/input/patch-source']
            with self.controller.lock():
                self.controller.register_support_inputs(grant, support)
            authorize()
            environment.prepare(accesses, self.context.contract.inputs['access_files'], support_inputs=support)
            if artifact_nonce:
                self.controller.record_lab_artifact_ready(grant, self.environment_id, environment.artifact_state_readback())
            prepared.set()
            for access_id, (reference, profile, target_environment) in control['reset_profiles'].items():
                profile_id = reference['environment_id']
                target_profile = read_json(self.controller.root / 'contract/environments' / (profile_id + '.json'), private=True)
                target_operations = {}
                def observe_target(observation, profile_id=profile_id, effect_id=reference['reset_effect_id'], operations=target_operations):
                    with self.controller.lock():
                        opid = observation['operation_id']
                        if observation['phase'] == 'intent' or opid not in operations:
                            operations[opid] = copy.deepcopy(grant)
                        return self.controller.record_environment_observation(operations[opid], profile_id,
                            observation, effect_id=effect_id)
                options = {'known_hosts_file': self.controller.root / 'contract/environments' / (profile_id + '.known_hosts')} if target_profile['ssh'] else {}
                owner = ApplicationOwner(profile, next(row for row in accesses if row['id'] == access_id),
                    target_profile, target_environment['limits'], authorize, observe_target,
                    grant=grant, dispatch_guard=guard, bootstrap={'application-connector': support['application-connector']}, **options)
                with self.controller.lock():
                    owners[access_id] = owner
                receipt = owner.reset(arguments['starting_state'][access_id])
                self.controller.record_application_start(grant, profile_id, receipt)
            if applications:
                target_accounts = TargetAccountResolver(self._target_reference(), self.scope,
                    authorize, observe_network, environment_profile_id=self.environment_id)
            routes = _routes(self.scope, grant['resources'])['lab']
            gate = NetworkGate(routes, active, maximum_bytes=self.environment_reference['limits']['output_bytes'],
                dispatch_guard=guard, request_binder=LabRequestBinder(self.scope, self.environment_id,
                    authorize, observe_network, target_accounts).bind,
                target_connectors=self._application_connectors(grant['resources'], owners))
            socket_path = self.socket_dir / ('capture-' + uuid.uuid4().hex[:12] + '.sock')
            gate.serve(socket_path, certificate=self.certificate, private_key=self.private_key)
            proxy = ProxyBridge(lambda command: environment.launch_stdio(command, role='network_proxy'),
                _clean_environment() + ['python3', '-I', '-S', '/input/bootstrap/bridge.py', 'relay'],
                gate, active, dispatch_guard=guard)
            command = _clean_environment(proxy.environment('/input/bootstrap/ca.pem'))
            if arguments['interpreter'] is not None:
                command.append(arguments['interpreter'])
            command.extend(['/input/capture/probe', '/input/capture/instrument', '/input/capture/candidate',
                *subjects, *arguments['arguments']])
            output = environment.execute(command, timeout_seconds=max(.01, deadline - time.monotonic()))
            if output['status'] != 'settled' or len(executions) != 1:
                raise BoundaryError('native_capture_execution_unknown')
            operation_id = executions[0]
            admitted = operations[operation_id]
            raw_output = output['output'].encode('utf-8')
            self.controller.record_environment_output(admitted, self.environment_id, operation_id, raw_output)
            self.controller.record_experiment_execution(admitted, self.environment_id, operation_id, {
                'instrument_id': arguments['instrument_id'], 'instrument_sha256': instrument['artifact_sha256'],
                'candidate_sha256': candidate_sha, 'probe_sha256': probe_sha, 'conditions': arguments['conditions'],
                'reset': instrument['reset'], 'clean_start': not applications or set(owners) == applications})
            if patch_manifest is not None:
                self.controller.record_patch_execution(admitted, self.environment_id, operation_id,
                    arguments['patch_id'], arguments['patch_arm'], patch_manifest)
            value = {'status': 'captured', 'dispatch_id': grant['dispatch_id'], 'operation_id': operation_id,
                'instrument_id': arguments['instrument_id'], 'candidate_sha256': candidate_sha, 'probe_sha256': probe_sha,
                'output_sha256': digest(raw_output), 'returncode': output['returncode'],
                'environment_nonce': output['identity']['nonce'], 'clean_start': not applications or set(owners) == applications,
                'limits': ['remote_application_reset_unverified'] if applications - set(owners) else [],
                'network_request_ids': sorted(name for name, row in self.controller.state()['network_operations'].items()
                    if row['grant']['dispatch_id'] == grant['dispatch_id'])}
        except Exception as error:
            failure = getattr(error, 'code', 'native_capture_unavailable')
        finally:
            renewal_stopped.set()
            renewal.join(timeout=5)
            if renewal.is_alive():
                failure = failure or 'native_capture_renewal_cleanup_unverified'
            elif renewal_failure:
                failure = failure or renewal_failure[0]
            for owned in (gate, proxy):
                if owned is not None:
                    try:
                        owned.close()
                    except Exception:
                        failure = failure or 'native_capture_transport_cleanup_unverified'
            if target_accounts is not None:
                target_accounts.close()
            for access_id, owner in owners.items():
                try:
                    readback = owner.cleanup()
                    self.controller.record_environment_cleanup(grant, control['reset_profiles'][access_id][0]['environment_id'], readback)
                    application_cleanup[access_id] = readback['status'] == 'clean'
                except Exception:
                    failure = failure or 'native_capture_application_cleanup_unresolved'
            if environment is not None:
                try:
                    cleanup = environment.cleanup()
                    self.controller.record_environment_cleanup(grant, self.environment_id, cleanup)
                except Exception:
                    failure = failure or 'native_capture_cleanup_unresolved'
            staging_clean = directory is None
            if directory is not None:
                try:
                    if artifact_nonce:
                        cleanup_staging(self.controller, grant, artifact_nonce)
                    else:
                        shutil.rmtree(directory)
                    staging_clean = not directory.exists() and not directory.is_symlink()
                except Exception:
                    failure = failure or 'native_capture_staging_cleanup_unverified'
            if artifact_nonce and cleanup is not None and cleanup.get('status') == 'clean' and staging_clean:
                try:
                    self.controller.record_lab_artifact_cleanup(grant, self.environment_id, cleanup)
                except Exception:
                    staging_clean = False
                    failure = failure or 'native_capture_artifact_cleanup_unverified'
            known = not renewal.is_alive() and cleanup is not None and cleanup.get('status') == 'clean' and staging_clean
            known = known and all(application_cleanup.get(name) for name in owners)
            if environment is None:
                try:
                    known = staging_clean and not renewal.is_alive() and not any(row['grant']['dispatch_id'] == grant['dispatch_id']
                        for row in self.controller.state()['environment_operations'].values())
                except Exception:
                    known = False
            try:
                with self.controller.lock():
                    state = self.controller.state()
                    retained = known and self._active() and not network_operations
                    resources = {name: ('reset' if environment is not None else 'unchanged') if known else 'unknown'
                        for name in grant['resources']}
                    resources.update({name: 'retained' if retained and not state['resource_holds'].get(name) else 'unknown'
                        for name in applications})
                    resources.update({name: 'reset' if known and application_cleanup.get(name) else 'unknown' for name in owners})
                    observation = {'status': 'settled' if known else 'unknown',
                        'worker_seconds': min(grant['seconds'], max(0, math.ceil(time.monotonic() - started))) if known else grant['seconds'],
                        'resources': resources, 'usage': {'tokens': None, 'cost': None},
                        'cleanup': 'verified' if known else 'unresolved'}
                    receipt = self.controller.store_receipt(grant, observation, adapter_id=grant['adapter_id'])
                    self.controller.adopt_receipt(grant['dispatch_id'], receipt, adapter_id=grant['adapter_id'])
            except Exception:
                failure = failure or 'native_capture_settlement_unresolved'
            with self.controller.lock():
                self.capture_application_active = False
                self.capture_cancel = None
            control['done'].set()
            self.capture_lock.release()
        if failure:
            return _result({'status': 'unavailable', 'code': failure, 'dispatch_id': grant['dispatch_id'],
                'evidence': value}, error=True)
        return _result(value)

    def finish(self):
        with self.finish_lock:
            if self.finished is not None:
                return copy.deepcopy(self.finished)
            self.controller.revoke_worker(self.context.worker['id'], self.context.worker['generation'], reason='native-boundary-finish')
            capture_closed = True
            if self.capture_cancel is not None:
                try:
                    self.capture_cancel()
                except Exception:
                    capture_closed = False
                if self.capture_done is not None and not self.capture_done.wait(5):
                    capture_closed = False
            transports_closed = True
            for gate in (self.provider_gate, self.lab_gate):
                if gate is not None:
                    try:
                        gate.close()
                    except Exception:
                        transports_closed = False
            if self.target_accounts is not None:
                try:
                    self.target_accounts.close()
                except Exception:
                    transports_closed = False
            runtime_readback = {'session_id': self.owner_receipt.get('session_id') if self.owner_receipt else None,
                'process_exited': False, 'child_absence': 'not_observed', 'capabilities_revoked': True}
            if self.runtime is not None:
                try:
                    runtime_readback.update(self.runtime.close())
                except Exception:
                    pass
            elif self.owner_receipt is not None and self.model_owner is None:
                try:
                    runtime_readback.update(_recover_owner(self.owner_receipt))
                except Exception:
                    pass
            if self.model_owner is not None:
                try:
                    runtime_readback.update(self.model_owner.revoke_and_verify(runtime_readback['session_id']))
                except Exception:
                    runtime_readback['child_absence'] = 'not_observed'
            if self.credential_binding is not None:
                try:
                    self.credential_binding.revoke()
                except Exception:
                    transports_closed = False
            if self.owner_receipt is not None:
                runtime_readback['owner_receipt_sha256'] = digest(canonical(self.owner_receipt))
            if self.native_owner is not None:
                try:
                    self.native_owner.close()
                except Exception:
                    runtime_readback['child_absence'] = 'not_observed'
            for proxy in (self.proxy, self.model_proxy):
                if proxy is not None:
                    try:
                        proxy.close()
                    except Exception:
                        pass
            environment_readback = cleanup = None
            if self.environment is not None:
                try:
                    environment_readback = self.environment.revoke()
                    cleanup = self.environment.cleanup()
                    if self.artifact_effect:
                        self.controller.record_environment_cleanup(self.context.grant, self.environment_id, cleanup)
                except Exception:
                    pass
            unused = (not self.execution_admitted and self.owner_receipt is None and self.runtime is None
                and self.native_owner is None and self.environment is None and self.proxy is None)
            pre_native = self.controller.preparation_without_native(self.context.grant)
            cleanup_state = self.controller.state()
            owned = (any(row['grant']['dispatch_id'] == self.context.grant['dispatch_id']
                for row in cleanup_state['environment_operations'].values())
                or any(row['dispatch_id'] == self.context.grant['dispatch_id'] for row in cleanup_state['lab_artifacts'].values()))
            if pre_native and owned and cleanup is not None and cleanup.get('status') == 'clean':
                try:
                    environment_readback = self.environment.revoke()
                except Exception:
                    environment_readback = None
            verified = (capture_closed and transports_closed and runtime_readback.get('process_exited') is True and
                runtime_readback.get('child_absence') == 'verified' and
                runtime_readback.get('capabilities_revoked') is True and self.owner_receipt is not None and
                cleanup is not None and cleanup.get('status') == 'clean' and
                environment_readback is not None and environment_readback.get('status') in ('stopped', 'absent'))
            verified = verified or (unused and capture_closed and transports_closed)
            verified = verified or (pre_native and capture_closed and transports_closed and
                (not owned or (cleanup is not None and cleanup.get('status') == 'clean'
                    and environment_readback is not None and environment_readback.get('status') in ('stopped', 'absent'))))
            if verified and self.state_dir is not None:
                verified = not any(row['state'] != 'clean' and row['dispatch_id'] != self.context.grant['dispatch_id']
                    and cleanup_state['dispatches'][row['dispatch_id']].get('parent_dispatch_id') == self.context.grant['dispatch_id']
                    for row in cleanup_state['lab_artifacts'].values())
            if verified:
                for directory in (self.socket_dir, self.state_dir):
                    if directory is not None:
                        try:
                            shutil.rmtree(directory)
                        except OSError:
                            verified = False
            if verified and self.artifact_effect and self.environment is not None:
                try:
                    self.controller.record_lab_artifact_cleanup(self.context.grant, self.environment_id, cleanup)
                except Exception:
                    verified = False
            self.finished = {'runtime': runtime_readback, 'environment': environment_readback,
                'execution_admitted': self.execution_admitted,
                'setup_only': pre_native,
                'setup_environments': [{'profile_id': self.environment_id, 'environment': environment_readback,
                    'cleanup': cleanup}] if pre_native and owned else [],
                'environment_cleanup': cleanup, 'cleanup': 'verified' if verified else 'unresolved',
                'resources': {row['id']: ('unchanged' if unused else 'reset') if verified and (unused or row['kind'] != 'application'
                    or application_released(self.controller.state(), self.context.grant['dispatch_id'], row['id']))
                    else 'unknown' for row in self.accesses}}
            return copy.deepcopy(self.finished)


def recover_boundary(context, dispatch):
    c = context.controller
    state = c.state()
    current = c.bind_grant(state, context.grant)
    if current.get('setup_receipt'):
        return {'status': 'settled'}
    worker = state['workers'][context.worker['id']]
    auxiliary = bool(dispatch.get('parent_dispatch_id'))
    pre_native = not auxiliary and c.preparation_without_native(context.grant)
    runtime_readback = None
    if not auxiliary:
        owner_sha = worker.get('runtime_owner_sha256')
        if not owner_sha and not pre_native:
            return {'status': 'unknown', 'code': 'native_owner_receipt_unavailable'}
        if owner_sha:
            owner = json.loads(c.read_object(owner_sha))
            if owner.get('session_id') != worker.get('session_id') or owner.get('profile_sha256') != context.assignment['profile_sha256']:
                return {'status': 'unknown', 'code': 'native_owner_identity_changed'}
        c.revoke_worker(worker['id'], worker['generation'], reason='native-boundary-recovery')
    try:
        if not auxiliary and not pre_native:
            options = {}
            if owner.get('kind') == 'native-runtime-owner-v2':
                options = {'profile': context.contract.runtime_profiles[context.grant['profile_id']],
                           'maximum_lease_seconds': context.contract.scope['limits']['max_worker_lease_seconds']}
            runtime_readback = _recover_owner(owner, **options)
            runtime_readback['owner_receipt_sha256'] = owner_sha
        nonces = {row['identity']['nonce'] for row in state['environment_operations'].values()
            if row['grant']['dispatch_id'] == context.grant['dispatch_id']}
        nonces.update(row['nonce'] for row in state['lab_artifacts'].values() if row['dispatch_id'] == context.grant['dispatch_id'])
        environments = [row for nonce, row in state['environments'].items() if nonce in nonces]
        if not environments and not pre_native:
            return {'status': 'unknown', 'code': 'native_environment_receipt_unavailable'}
        setup_readbacks = []
        for row in environments:
            profile_id = row['profile_id']
            profile = read_json(c.root / 'contract/environments' / (profile_id + '.json'), private=True)
            reference = next(r for r in context.contract.scope['environments'] if r['profile_id'] == profile_id)
            recorded = {operation['effect_id'] for operation in state['environment_operations'].values()
                if operation['identity']['nonce'] == row['identity']['nonce'] and operation['grant']['dispatch_id'] == context.grant['dispatch_id']}
            artifact = state['lab_artifacts'].get(row['identity']['nonce'])
            if artifact is not None and not recorded:
                recorded.add(artifact['effect_id'])
            effects = [r for r in context.contract.scope['effects'] if profile_id in r['environment_ids'] and r['id'] in recorded
                and {access['id'] for access in row['identity']['access']} <= set(r['access_ids']) and not r['account_refs']]
            if not effects:
                raise BoundaryError('native_effect_grant_unavailable')
            def observe(value, identity=profile_id, effect=effects[0]['id']):
                return c.record_environment_observation(context.grant, identity, value, effect_id=effect)
            options = {'known_hosts_file': c.root / 'contract/environments' / (profile_id + '.known_hosts')} if profile['ssh'] else {}
            environment = Environment(profile, reference['limits'], context.authorize, observe,
                grant=context.grant, dispatch_guard=context.guard, receipt=row['identity'], lab_artifact=artifact is not None, **options)
            stopped = environment.revoke()
            cleanup = environment.cleanup()
            if artifact is not None:
                c.record_environment_cleanup(context.grant, profile_id, cleanup)
                cleanup_staging(c, context.grant, row['identity']['nonce'])
                c.record_lab_artifact_cleanup(context.grant, profile_id, cleanup)
            if pre_native:
                stopped = environment.revoke()
                setup_readbacks.append({'profile_id': profile_id, 'environment': stopped, 'cleanup': cleanup})
                continue
            if not auxiliary:
                c.record_worker_stopped(context.grant, profile_id, {'runtime': runtime_readback, 'environment': stopped})
            c.record_environment_cleanup(context.grant, profile_id, cleanup)
        if pre_native:
            elapsed = min(context.grant['seconds'], max(0, math.ceil(
                (c.clock() - instant(current['setup_started_at'])).total_seconds())))
            c.settle_preparation(context.grant, setup_readbacks, worker_seconds=elapsed)
            return {'status': 'settled'}
        observation = {'status': 'settled', 'worker_seconds': context.grant['seconds'],
            'resources': {name: 'reset' if next(r for r in context.contract.scope['access'] if r['id'] == name)['kind'] != 'application'
                or application_released(c.state(), context.grant['dispatch_id'], name)
                else 'unknown' for name in context.grant['resources']}, 'usage': {'tokens': None, 'cost': None}, 'cleanup': 'verified'}
        receipt = c.store_receipt(context.grant, observation, adapter_id=context.grant['adapter_id'])
        c.adopt_receipt(context.grant['dispatch_id'], receipt, adapter_id=context.grant['adapter_id'])
        return {'status': 'settled'}
    except Exception as error:
        return {'status': 'unknown', 'code': getattr(error, 'code', 'native_recovery_unverified')}
