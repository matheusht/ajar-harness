#!/usr/bin/env python3
"""Failure-first Linux model-owner composition; no Docker or provider is contacted."""
from __future__ import annotations
import argparse
import copy
from contextlib import nullcontext
import importlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
import check_engagement_contract_e2e as fixture
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller


def require(value, message):
    if not value: raise AssertionError(message)


def refused(call, code=None):
    try: call()
    except Exception as error:
        observed = getattr(error, 'code', str(error))
        require(code is None or observed == code, 'wrong refusal: ' + str(observed))
        return observed
    raise AssertionError('forbidden operation accepted')


def model_host(binary):
    return {'kind': 'linux-docker-model-v1', 'docker_binary': str(binary),
        'docker_endpoint': 'unix:///fixture/docker.sock', 'daemon_id': 'fixture-model-daemon',
        'image_id': 'sha256:' + '2' * 64, 'platform': 'linux/amd64', 'uid': 1000, 'gid': 1000,
        'limits': {'memory_bytes': 1073741824, 'cpu_count': 1, 'pids': 64, 'workspace_bytes': 67108864}}


def signed(root, *, catalog=False):
    inputs = fixture.make_fixture(root / 'inputs')
    definitions = json.loads(inputs.read_bytes())
    path = Path(definitions['runtime_profiles']['runtime-main'])
    profile = json.loads(path.read_bytes())
    profile['model_host'] = model_host(Path(profile['executable']['path']))
    if catalog:
        profile['kind'] = 'omp'; profile['protocol']['mode'] = 'stdio-jsonl'
        profile['tool_bundle']['bun_version'] = '1.4.4'
        models = root / 'models.yml'
        fixture.write(models, canonical({'providers': {'openai': {'baseUrl': 'http://127.0.0.1:1/v1'}}}))
        profile['model_catalog'] = {'path': str(models), 'sha256': digest(models.read_bytes())}
    fixture.write(path, canonical(profile))
    scope = fixture.fixture_scope(inputs)
    scope['runtime_assignments'][0]['profile_sha256'] = digest(path.read_bytes())
    fixture.resign_fixture(inputs, scope)
    return inputs, profile


def profile_contract(root):
    inputs, profile = signed(root)
    verified = load_inputs(inputs)
    require(verified.runtime_profiles['runtime-main'] == profile, 'model profile was not frozen')
    from engagement_contract import validate_runtime_profile
    variants = []
    for key, value in (('kind', 'other'), ('docker_endpoint', 'tcp://127.0.0.1:2375'),
                       ('daemon_id', None), ('image_id', 'latest'), ('uid', 0), ('gid', 0),
                       ('platform', 'darwin/arm64'), ('docker_binary', 'docker')):
        changed = copy.deepcopy(profile); changed['model_host'][key] = value; variants.append(changed)
    for key, value in (('memory_bytes', 0), ('cpu_count', float('inf')), ('pids', True),
                       ('workspace_bytes', -1), ('state_bytes', 1024)):
        changed = copy.deepcopy(profile); changed['model_host']['limits'][key] = value; variants.append(changed)
    changed = copy.deepcopy(profile); changed['model_host']['mounts'] = []; variants.append(changed)
    for changed in variants: refused(lambda changed=changed: validate_runtime_profile(changed))
    definitions = json.loads(inputs.read_bytes())
    path = Path(definitions['runtime_profiles']['runtime-main'])
    changed = copy.deepcopy(profile); changed['model_host']['image_id'] = 'sha256:' + '3' * 64
    fixture.write(path, canonical(changed))
    refused(lambda: load_inputs(inputs), 'digest_mismatch')
    legacy = copy.deepcopy(profile); del legacy['model_host']
    validate_runtime_profile(legacy)
    return {'invalid_profiles_refused': len(variants), 'signed_drift_refused': True, 'legacy_shape_preserved': True}


def catalog_contract(root):
    from engagement_contract import validate_runtime_profile
    from engagement_runner import frozen_inputs
    inputs, profile = signed(root, catalog=True)
    verified = load_inputs(inputs)
    name = 'runtimes/runtime-main.models.yml'
    expected = Path(profile['model_catalog']['path']).read_bytes()
    require(verified.frozen_files[name] == expected, 'catalog was not frozen')
    controller = Controller.initialize(root / 'engagement', verified, evidence_class='engineering_simulation')
    reopened = frozen_inputs(Controller(controller.root))
    require(Path(reopened.runtime_profiles['runtime-main']['model_catalog']['path']).read_bytes() == expected,
            'reopened catalog does not use journal-owned bytes')
    for replacement in ({'path': 'models.yml', 'sha256': profile['model_catalog']['sha256']},
                        {'path': profile['model_catalog']['path'], 'sha256': 'latest'},
                        dict(profile['model_catalog'], extra=True)):
        changed = copy.deepcopy(profile); changed['model_catalog'] = replacement
        refused(lambda: validate_runtime_profile(changed))
    changed = copy.deepcopy(profile); changed['kind'] = 'codex'; changed['protocol']['mode'] = 'stdio-jsonrpc'
    del changed['tool_bundle']['bun_version']
    refused(lambda: validate_runtime_profile(changed))
    fixture.write(Path(profile['model_catalog']['path']), b'changed\n')
    refused(lambda: load_inputs(inputs), 'digest_mismatch')
    require(Path(reopened.runtime_profiles['runtime-main']['model_catalog']['path']).read_bytes() == expected,
            'original catalog mutation reached frozen owner')
    fixture.write(Path(profile['model_catalog']['path']), b'{"providers":{"openai":{"apiKey":"fixture-secret"}}}\n')
    definitions = json.loads(inputs.read_bytes()); profile_path = Path(definitions['runtime_profiles']['runtime-main'])
    profile['model_catalog']['sha256'] = digest(Path(profile['model_catalog']['path']).read_bytes())
    fixture.write(profile_path, canonical(profile)); scope = fixture.fixture_scope(inputs)
    scope['runtime_assignments'][0]['profile_sha256'] = digest(profile_path.read_bytes()); fixture.resign_fixture(inputs, scope)
    refused(lambda: load_inputs(inputs), 'publication_secret')
    return {'signed_and_frozen': True, 'reopened_frozen_path': True, 'tamper_refused': True,
            'literal_secret_refused': True, 'codex_catalog_refused': True}


def native_catalog(root):
    import check_native_runtime_adapters as wire
    from native_runtime_omp import Runtime
    root.mkdir(mode=0o700)
    peer = root / 'peer'; peer.write_text(wire.PEER.replace('KIND', repr('omp'))); peer.chmod(0o700)
    profile = wire.profile(root, 'omp', peer)
    catalog = root / 'models.yml'; catalog.write_text('{"providers":{}}\n'); catalog.chmod(0o600)
    profile['model_catalog'] = {'path': str(catalog), 'sha256': digest(catalog.read_bytes())}
    state = root / 'state'
    runtime = Runtime(profile, state, root, dispatch_guard=nullcontext)
    try:
        first = runtime.fresh()
        require(runtime.resume(first['session_id'])['session_id'] == first['session_id'], 'native catalog session lost')
        require((state / 'models.yml').read_bytes() == catalog.read_bytes(), 'native catalog was not staged')
    finally: runtime.close()
    (state / 'models.yml').chmod(0o600); (state / 'models.yml').write_text('foreign\n')
    refused(lambda: Runtime(profile, state, root, dispatch_guard=nullcontext), 'runtime_state_config_changed')
    (state / 'models.yml').unlink(); (state / 'models.yml').symlink_to(catalog)
    refused(lambda: Runtime(profile, state, root, dispatch_guard=nullcontext), 'runtime_state_config_changed')
    return {'real_protocol_subprocess': True, 'native_state_catalog_pinned': True, 'mutated_or_symlink_state_refused': True}


def receipt_for(module, profile, grant, scope_sha, *, ready=False):
    environment = module.environment_profile(profile)
    nonce = 'a' * 32
    identity = {'kind': 'research-environment-receipt-v2', 'nonce': nonce,
        'container_id': 'b' * 64 if ready else None, 'container_name': 'oslit-' + nonce,
        'stage_container_id': 'c' * 64 if ready else None, 'stage_container_name': 'oslit-' + nonce + '-stage',
        'prepared_image_id': 'sha256:' + 'd' * 64 if ready else None,
        'prepared_image_name': 'oslit-input-' + nonce + ':latest', 'unsettled': [],
        'daemon_id': environment['daemon_id'], 'image_id': environment['image_id'],
        'profile_sha256': module.environment_digest(environment), 'access': [],
        'support_inputs': [{'id': 'model', 'manifest_sha256': 'sha256:' + '9' * 64}] if ready else []}
    return {'kind': 'native-runtime-owner-v2', 'runtime': profile['kind'], 'session_id': None,
        'profile_sha256': digest(canonical(profile)), 'boundary': 'linux-docker-model-v1', 'owner': {
            'phase': 'running' if ready else 'intended', 'dispatch_id': grant['dispatch_id'],
            'worker_id': grant['worker_id'], 'generation': grant['generation'], 'scope_sha256': scope_sha,
            'environment': identity, 'configuration_sha256': module.configuration_digest(profile, 60),
            'host': {'id_sha256': 'sha256:' + 'e' * 64, 'boot_id': '00000000-0000-0000-0000-000000000001'},
            'init': {'host_pid': 12345, 'start_ticks': 99, 'pid_namespace_inode': 300} if ready else None,
            'cgroup': {'relative_path': '/system.slice/docker-' + 'b' * 64 + '.scope',
                       'device': 25, 'inode': 301} if ready else None}}


def ledger(root):
    import native_runtime_linux as module
    inputs, profile = signed(root)
    contract = load_inputs(inputs)
    c = Controller.initialize(root / 'engagement', contract, evidence_class='engineering_simulation')
    workspace = root / 'workspace'; workspace.mkdir(mode=0o700)
    grant = c.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
        resources=['source-main'], adapter_id='fixture-adapter')
    scope_sha = digest(contract.frozen_files['scope.md'])
    first = receipt_for(module, profile, grant, scope_sha)
    c.record_runtime_preparation_owner(grant, first)
    require(not c.preparation_without_native(grant), 'model intent became no-native refund proof')
    legacy = {'kind': 'native-runtime-owner-v1', 'runtime': profile['kind'], 'session_id': None,
        'profile_sha256': first['profile_sha256'], 'boundary': 'darwin-no-fork-v1',
        'process': {'pid': 34567, 'pgid': 34567, 'uid': 501, 'started_seconds': 1, 'started_microseconds': 2}}
    refused(lambda: c.record_runtime_preparation_owner(grant, legacy))
    mutated = []
    for key, value in (('dispatch_id', 'foreign'), ('worker_id', 'foreign'), ('generation', 2),
                       ('scope_sha256', 'sha256:' + 'f' * 64)):
        changed = copy.deepcopy(first); changed['owner'][key] = value; mutated.append(changed)
    for key, value in (('nonce', 'f' * 32), ('daemon_id', 'other-daemon'), ('access', [{'id': 'source-main'}])):
        changed = copy.deepcopy(first); changed['owner']['environment'][key] = value; mutated.append(changed)
    for changed in mutated: refused(lambda changed=changed: c.record_runtime_preparation_owner(grant, changed))
    ready = receipt_for(module, profile, grant, scope_sha, ready=True)
    c.record_runtime_preparation_owner(grant, ready)
    refused(lambda: c.record_runtime_preparation_owner(grant, first))
    changed = copy.deepcopy(ready); changed['owner']['cgroup']['inode'] += 1
    refused(lambda: c.record_runtime_preparation_owner(grant, changed))
    changed = copy.deepcopy(ready); changed['owner']['environment']['unsettled'] = ['create']
    refused(lambda: c.record_runtime_preparation_owner(grant, changed))
    ready['session_id'] = 'linux-fixture-session'
    c.record_runtime_preparation_owner(grant, ready)
    c.record_worker_started('lead-1', 1, ready['session_id'], workspace, owner_receipt=ready)
    revision = c.state()['revision']
    c.record_runtime_preparation_owner(grant, ready)
    require(c.state()['revision'] == revision, 'active exact owner duplicated history')
    changed = copy.deepcopy(ready); changed['owner']['host']['boot_id'] = '00000000-0000-0000-0000-000000000002'
    refused(lambda: c.record_runtime_preparation_owner(grant, changed))
    reopened = Controller(c.root)
    require(reopened.state()['workers']['lead-1']['runtime_owner_sha256'] == digest(canonical(ready)), 'owner lost on reopen')
    return {'foreign_or_mutated_owner_refusals': len(mutated) + 4, 'durable_before_native': True,
            'active_idempotent': True, 'reopened_receipt': True}


def bootstrap(root, *, catalog=False):
    import native_runtime_bootstrap as module
    root.mkdir(mode=0o700)
    model = root / 'model'; state = root / 'state'; config = root / 'config.json'
    canary = 'fixture-private-model-canary'
    model.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
        'x=sys.stdin.readline();print(json.dumps({"native":x.strip(),"credential_present":os.environ.get("OPENAI_API_KEY")=="' + canary + '","argc":len(sys.argv)}),flush=True)\n')
    model.chmod(0o700); config.write_text('{}\n')
    models = root / 'models.yml'; models.write_text('{"providers":{}}\n')
    frame = {'kind': 'native-model-bootstrap-v1', 'runtime': 'omp', 'argv': [str(model), '--mode', 'rpc'],
        'environment': {'PATH': '/usr/bin:/bin', 'HOME': str(state), 'PI_CODING_AGENT_DIR': str(state), 'TMPDIR': '/tmp'},
        'credentials': {'OPENAI_API_KEY': canary}, 'executable_sha256': digest(model.read_bytes()),
        'config_sha256': digest(config.read_bytes())}
    if catalog: frame['model_catalog_sha256'] = digest(models.read_bytes())
    program = 'import sys;sys.path.insert(0,sys.argv[1]);import native_runtime_bootstrap as b;b.MODEL=sys.argv[2];b.STATE=sys.argv[3];b.WORKSPACE=sys.argv[4];b.CONFIGS={"omp":sys.argv[5],"codex":sys.argv[5]};b.MODEL_CATALOG=sys.argv[6];b.main()'
    def invoke(value, *, wire=None):
        encoded = json.dumps(value).encode()
        payload = struct.pack('!I', len(encoded)) + encoded + b'native-message\n' if wire is None else wire
        return subprocess.run([sys.executable, '-c', program, str(ROOT / 'tools'), str(model), str(state), str(root), str(config), str(models)],
            input=payload, capture_output=True, timeout=5, env={'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'})
    result = invoke(frame)
    require(result.returncode == 0, 'bootstrap failed normal private launch')
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    require(lines[0] == {'native_model_bootstrap': 'ready'} and lines[1] == {
        'native': 'native-message', 'credential_present': True, 'argc': 3}, 'bootstrap consumed native frame or lost private key')
    require(canary.encode() not in result.stdout + result.stderr, 'bootstrap printed credential')
    require(all(canary.encode() not in p.read_bytes() for p in state.rglob('*') if p.is_file()), 'credential persisted in model state')
    if catalog:
        require((state / 'models.yml').read_bytes() == models.read_bytes(), 'catalog not copied to native OMP state')
        changed = copy.deepcopy(frame); changed['model_catalog_sha256'] = 'sha256:' + '0' * 64
        require(invoke(changed).returncode != 0, 'changed catalog pin accepted')
        (state / 'models.yml').chmod(0o600); (state / 'models.yml').write_text('foreign\n')
        require(invoke(frame).returncode != 0, 'changed native state catalog accepted')
        (state / 'models.yml').unlink()
        (state / 'models.yml').symlink_to(models)
        require(invoke(frame).returncode != 0, 'symlink native catalog accepted')
        (state / 'models.yml').unlink()
    failures = []
    for name, modify in (
        ('executable-pin', lambda x: x.update(executable_sha256='sha256:' + '0' * 64)),
        ('config-pin', lambda x: x.update(config_sha256='sha256:' + '0' * 64)),
        ('loader-env', lambda x: x['credentials'].update(LD_PRELOAD='/tmp/foreign.so')),
        ('public-key-collision', lambda x: x['credentials'].update(HOME='/tmp/foreign')),
        ('wrong-executable', lambda x: x['argv'].__setitem__(0, '/bin/sh')),
        ('unknown-field', lambda x: x.update(extra='forbidden'))):
        changed = copy.deepcopy(frame); modify(changed)
        bad = invoke(changed)
        require(bad.returncode != 0 and canary.encode() not in bad.stdout + bad.stderr, name + ' admitted or leaked')
        failures.append(name)
    for name, wire in (('oversized', struct.pack('!I', module.MAX_BOOTSTRAP + 1)), ('truncated', b'\x00\x00'),
                       ('malformed', struct.pack('!I', 4) + b'{bad')):
        bad = invoke(frame, wire=wire)
        require(bad.returncode != 0 and canary.encode() not in bad.stdout + bad.stderr, name + ' admitted or leaked')
        failures.append(name)
    return {'private_pipe_only': True, 'following_native_frame_preserved': True, 'refused': failures}


def adapter(root, kind):
    import check_native_runtime_adapters as wire
    from native_credentials import CredentialBinding
    module = importlib.import_module('native_runtime_' + kind)
    root.mkdir(mode=0o700)
    peer = root / 'peer'; peer.write_text(wire.PEER.replace('KIND', repr(kind))); peer.chmod(0o700)
    profile = wire.profile(root, kind, peer); profile['model_host'] = model_host(peer)
    seen = []
    class Owner:
        boundary = 'linux-docker-model-v1'
        profile_sha256 = digest(canonical(profile))
        paths = SimpleNamespace(executable='/runtime/bin/model', state='/work/.model', workspace='/work',
            config='/input/model/config.toml' if kind == 'codex' else '/input/model/config.json', ca='/input/model/ca.pem')
        def check_authority(self): pass
        def launch_model(self, command, public_environment, binding):
            require(command[0] == self.paths.executable, 'adapter used host executable in container')
            require(public_environment['HOME'] == self.paths.state, 'host home leaked into container')
            require('OPENAI_API_KEY' not in public_environment, 'credential crossed public environment')
            seen.append((list(command), dict(public_environment)))
            return subprocess.Popen([str(peer)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env={'PATH': os.environ['PATH']}, start_new_session=True)
        def receipt(self, session_id=None):
            return {'kind': 'native-runtime-owner-v2', 'runtime': kind, 'session_id': session_id,
                'profile_sha256': self.profile_sha256, 'boundary': self.boundary, 'owner': {'fixture': True}}
        def revoke_and_verify(self, session_id=None):
            return {'process_exited': True, 'child_absence': 'verified', 'capabilities_revoked': True,
                'session_id': session_id, 'boundary': self.boundary}
    owner = Owner()
    runtime = module.Runtime(profile, root / 'state', root, dispatch_guard=nullcontext,
        protected_model=True, profile_sha256=owner.profile_sha256, model_owner=owner,
        credential_resolver=lambda profile: CredentialBinding())
    try:
        first = runtime.fresh()
        require(runtime.resume(first['session_id'])['session_id'] == first['session_id'], 'live session lost')
        require(runtime.capabilities()['child_inventory'] == 'contained_descendants', 'Linux claimed no-fork')
        runtime.invoke('ordinary', 'linux-invocation')
        observed = []
        for _ in range(20):
            observed.extend(runtime.observe(.1))
            if not runtime.active: break
        require(any(row['event'] == 'completed' for row in observed), 'native completion lost')
        if kind == 'omp':
            command = seen[0][0]
            require(command[command.index('--cwd') + 1] == '/work' and
                command[command.index('--config') + 1] == '/input/model/config.json', 'OMP container paths changed')
        else: require(seen[0][1]['CODEX_HOME'] == '/work/.model', 'Codex container home changed')
        require(runtime.owner_receipt()['session_id'] == first['session_id'], 'owner lost native session')
    finally: closed = runtime.close()
    require(closed['child_absence'] == 'verified', 'container owner cleanup unused')
    return {'real_protocol_subprocess': True, 'container_identity_simulated': True, 'fresh_resume_completed': True}



def owned_lifecycle(root, *, host_permission_denied=False, catalog=False):
    import native_runtime_linux as module
    root.mkdir(mode=0o700)
    inputs, profile = signed(root, catalog=catalog)
    active = [True]
    records, effects = [], []
    grant = {'dispatch_id': 'dispatch-fixture', 'worker_id': 'lead-1', 'generation': 1,
        'scope_sha256': 'sha256:' + 'f' * 64, 'seconds_remaining': 30}
    facts = {'id_sha256': 'sha256:' + 'e' * 64, 'boot_id': '00000000-0000-0000-0000-000000000001'}
    os_identity = {'init': {'host_pid': 12345, 'start_ticks': 99, 'pid_namespace_inode': 300},
        'cgroup': {'relative_path': '/system.slice/docker-' + 'b' * 64 + '.scope', 'device': 25, 'inode': 301}}
    modes = {'wrong_file': False, 'absent_unverified': False, 'cleanup_fails': False}
    class Environment:
        def __init__(self, environment, limits, authorize, observe, **options):
            self.profile, self.limits, self.authorize, self.observe = environment, limits, authorize, observe
            self.grant = options.get('grant'); self.running = False
            self.identity = copy.deepcopy(options.get('receipt')) or receipt_for(module, profile,
                grant, grant['scope_sha256'])['owner']['environment']
        def receipt(self): return copy.deepcopy(self.identity)
        def prepare(self, accesses, access_files, *, support_inputs):
            require(records and records[0]['owner']['phase'] == 'intended', 'effect preceded durable intent')
            require(accesses == [] and access_files == {} and set(support_inputs) == {'model'}, 'target input entered model owner')
            if catalog:
                require((Path(support_inputs['model']['path']) / 'models.yml').read_bytes() ==
                        Path(profile['model_catalog']['path']).read_bytes(), 'model catalog was not staged privately')
            self.identity['support_inputs'] = [{'id': 'model', 'manifest_sha256': support_inputs['model']['manifest_sha256']}]
            self.identity['unsettled'] = ['create_stage']
            self.observe({'identity': self.receipt(), 'phase': 'intent', 'operation': 'create_stage'})
            effects.append('create')
            self.identity.update(container_id='b' * 64, stage_container_id='c' * 64,
                prepared_image_id='sha256:' + 'd' * 64, unsettled=[])
            self.running = True
            self.observe({'identity': self.receipt(), 'phase': 'result', 'operation': 'start', 'status': 'settled'})
            return {'status': 'ready'}
        def _run(self, args, **options):
            if args[:2] == ['container', 'exec']:
                require(args[2:7] == ['--user', '0:0', '--workdir', '/', self.identity['container_id']], 'namespace query is not exact/root-only')
                return {'status': 'settled', 'returncode': 0, 'output': json.dumps({'uid': 0,
                    'pid1_start_ticks': 99, 'pid_namespace_inode': 300, 'self_pid_namespace_inode': 300}).encode()}
            return {'status': 'settled', 'returncode': 0, 'output': json.dumps({'ID': self.profile['daemon_id'],
                'CgroupVersion': '2', 'SecurityOptions': ['name=seccomp,profile=builtin']}).encode()}
        def _inspect(self, **options):
            return {'Id': self.identity['container_id'], 'State': {'Pid': 12345, 'Running': self.running},
                'Config': {'Env': [], 'Healthcheck': {'Test': ['NONE']}, 'Volumes': None},
                'HostConfig': {'PidMode': '', 'IpcMode': 'private', 'CgroupnsMode': 'private',
                    'CgroupParent': '', 'UsernsMode': '', 'Devices': [], 'DeviceRequests': [],
                    'DeviceCgroupRules': [], 'SecurityOpt': ['no-new-privileges=true'],
                    'CapAdd': [], 'ExtraHosts': [], 'Links': [], 'VolumesFrom': [], 'Binds': [],
                    'PortBindings': {}, 'Privileged': False}, 'Mounts': []}
        def _verify_configuration(self, info): pass
        def execute(self, argv, *, timeout_seconds):
            paths = {'/runtime/bin/model': Path(profile['executable']['path']),
                '/runtime/native_runtime_bootstrap.py': ROOT / 'tools/native_runtime_bootstrap.py',
                '/runtime/engagement_network_bridge.py': ROOT / 'tools/engagement_network_bridge.py',
                '/runtime/native_runtime_codex_exec.mjs': ROOT / 'tools/native_runtime_codex_exec.mjs'}
            values = {name: {'sha256': digest(path.read_bytes()), 'mode': 0o555 if name.endswith('/model') else 0o444,
                'uid': 0, 'gid': 0} for name, path in paths.items()}
            values['/runtime/bin/bun'] = {'sha256': 'sha256:' + '6' * 64, 'mode': 0o555, 'uid': 0, 'gid': 0}
            if catalog:
                del values['/runtime/bin/bun']; del values['/runtime/native_runtime_codex_exec.mjs']
            if modes['wrong_file']: values['/runtime/bin/model']['sha256'] = 'sha256:' + '0' * 64
            return {'status': 'settled', 'returncode': 0, 'output': json.dumps(values)}
        def launch_stdio(self, *args, **options): raise AssertionError('unexpected model process dispatch')
        def renew(self, seconds): effects.append('renew'); return {'status': 'renewal_sent'}
        def revoke(self): self.running = False; effects.append('revoke'); return {'status': 'stopped', 'identity': self.receipt()}
        def cleanup(self):
            if modes['cleanup_fails']: raise RuntimeError('fixture-cleanup-fails')
            self.running = False; effects.append('clean'); return {'status': 'clean', 'identity': self.receipt(), 'owned_workspace': 'container_removed'}
    def authorize():
        require(active[0], 'fixture-grant-revoked')
        return grant
    def absence(receipt):
        if modes['absent_unverified']: raise RuntimeError('native_model_descendants_unknown')
        return True
    def running(info, *, namespace_inode=None):
        if host_permission_denied and namespace_inode != 300:
            raise PermissionError('fixture-root-guardian-namespace-unreadable')
        return copy.deepcopy(os_identity)
    with patch.object(module, 'Environment', Environment), patch.object(module, 'host_identity', lambda: facts), \
         patch.object(module, 'running_identity', running), \
         patch.object(module, 'process_start_ticks', lambda pid: 99, create=True), \
         patch.object(module, 'verify_absence', absence):
        owner = module.LinuxModelOwner(profile, digest(canonical(profile)), grant, authorize=authorize,
            dispatch_guard=nullcontext, observe_owner=lambda value: records.append(copy.deepcopy(value)),
            maximum_lease_seconds=60, support_directory=root / 'support')
        owner.prepare(config_bytes=Path(profile['config_file']).read_bytes(), ca_bytes=b'fixture-public-ca\n')
        require(owner.receipt()['owner']['phase'] == 'running', 'namespace observation was not committed')
        require(all(not r['owner']['environment']['access'] for r in records), 'model entered target evidence')
        owner.renew(grant, 10)
        active[0] = False
        refused(lambda: owner.launch_support('provider_relay'))
        stopped = owner.revoke_and_verify()
        require(stopped['child_absence'] == 'verified' and stopped['process_exited'], 'exact owner did not settle')
        require(owner.revoke_and_verify() == stopped, 'cleanup readback not idempotent')
        active[0] = True; modes['wrong_file'] = True
        failed = module.LinuxModelOwner(profile, digest(canonical(profile)), grant, authorize=authorize,
            dispatch_guard=nullcontext, observe_owner=lambda value: None, maximum_lease_seconds=60,
            support_directory=root / 'bad-support')
        refused(lambda: failed.prepare(config_bytes=Path(profile['config_file']).read_bytes(), ca_bytes=b'fixture-public-ca\n'),
            'native_model_image_files_changed')
        failed.revoke_and_verify()
        modes['wrong_file'] = False; modes['absent_unverified'] = True
        held = module.LinuxModelOwner(profile, digest(canonical(profile)), grant, authorize=authorize,
            dispatch_guard=nullcontext, observe_owner=lambda value: None, maximum_lease_seconds=60,
            support_directory=root / 'held-support')
        held.prepare(config_bytes=Path(profile['config_file']).read_bytes(), ca_bytes=b'fixture-public-ca\n')
        refused(held.revoke_and_verify)
    return {'namespace_and_docker_simulated': True, 'intent_before_effect': True,
        'model_inputs_separate': True, 'file_drift_prevents_launch': True, 'unverified_absence_held': True}



def composed_boundary(root, *, recovery=None):
    import check_engagement_native_boundary_e2e as fixtures
    import engagement_native_boundary as boundary
    import native_runtime_linux as linux
    from native_credentials import CredentialBinding
    from engagement_runner import WorkerContext, frozen_inputs
    from contextlib import ExitStack
    import threading
    inputs, profile = signed(root)
    contract = load_inputs(inputs)
    c = Controller.initialize(root / 'engagement', contract, evidence_class='engineering_simulation')
    workspace = root / 'workspace'; workspace.mkdir(mode=0o700)
    grant = c.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
        resources=['source-main'], adapter_id='fixture-adapter')
    runner = SimpleNamespace(controller=c, contract=frozen_inputs(c), changed=threading.Event())
    context = WorkerContext(runner, c.state()['workers']['lead-1'], grant, workspace)
    created, resolutions, proxies = [], [], []
    class Owner:
        def __init__(self, configured, profile_sha256, grant, **options):
            self.profile = configured; self.profile_sha256 = profile_sha256; self.grant = grant
            self.options = options; self.ready = False; self.renewals = []; self.failed_cleanup = False
            self.current = receipt_for(linux, configured, grant, grant['scope_sha256'])
            self.current['profile_sha256'] = profile_sha256
            self.paths = SimpleNamespace(executable='/runtime/bin/model', state='/work/.model',
                workspace='/work', config='/input/model/config.toml', ca='/input/model/ca.pem')
            created.append(self)
        def prepare(self, *, config_bytes, ca_bytes):
            require(config_bytes == Path(self.profile['config_file']).read_bytes() and b'PRIVATE KEY' not in ca_bytes,
                    'model support contains private or changed data')
            require(len(fixtures.SimulatedEnvironment.instances) == 1, 'lab was not separately prepared')
            self.options['observe_owner'](self.current)
            self.current = receipt_for(linux, self.profile, self.grant, self.grant['scope_sha256'], ready=True)
            self.current['profile_sha256'] = self.profile_sha256
            self.options['observe_owner'](self.current); self.ready = True
        def launch_support(self, role): raise AssertionError('simulated proxy must not launch real model')
        def receipt(self, session_id=None):
            if session_id is not None: self.current['session_id'] = session_id
            return copy.deepcopy(self.current)
        def renew(self, grant, seconds): self.grant = grant; self.renewals.append(seconds)
        def revoke_and_verify(self, session_id=None):
            if self.failed_cleanup: raise RuntimeError('fixture-model-cleanup-unresolved')
            return {'session_id': session_id or self.current['session_id'], 'process_exited': True,
                'child_absence': 'verified', 'capabilities_revoked': True, 'boundary': 'linux-docker-model-v1'}
    class Runtime(fixtures.SimulatedRuntime):
        def fresh(self):
            result = super().fresh(); self.options['owner_observer'](self.owner_receipt()); return result
        def owner_receipt(self): return self.options['model_owner'].receipt(self.session_id)
        def close(self): return self.options['model_owner'].revoke_and_verify(self.session_id)
    class Proxy(fixtures.SimulatedProxy):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs); proxies.append(self)
    def resolve():
        def value(configured):
            require(created and created[0].ready, 'credential resolution preceded model image verification')
            resolutions.append(True); return CredentialBinding()
        return value
    def bundle(configured, identity):
        return {'support_input': {'path': configured['tool_bundle']['path'],
            'manifest_sha256': configured['tool_bundle']['manifest_sha256']},
            'command': ['/input/' + identity + '/bin/codex', 'exec-server', '--listen', 'stdio'],
            'expected_version': 'engineering-fixture', 'expected_platform': 'linux'}
    with ExitStack() as stack:
        stack.enter_context(patch.object(boundary, 'Environment', fixtures.SimulatedEnvironment))
        stack.enter_context(patch.object(boundary, 'LinuxModelOwner', Owner, create=True))
        stack.enter_context(patch.object(boundary, 'ProxyBridge', Proxy))
        stack.enter_context(patch.object(boundary, '_inspect_bundle', bundle))
        stack.enter_context(patch.object(boundary, '_credential_resolver', resolve))
        stack.enter_context(patch.object(boundary.codex, 'Runtime', Runtime))
        stack.enter_context(patch.object(boundary.codex, 'NativeExecutor', fixtures.SimulatedExecutor))
        stack.enter_context(patch.object(boundary.NetworkGate, 'serve_tcp', lambda *a, **k: (_ for _ in ()).throw(
            AssertionError('Linux provider gate exposed host TCP'))))
        fixtures.SimulatedEnvironment.instances = []; fixtures.SimulatedEnvironment.cleanup_fails = False
        instance = boundary.NativeBoundary(context)
        try:
            identity = instance.start()
            c.record_worker_started('lead-1', 1, identity['session_id'], workspace, owner_receipt=identity['owner_receipt'])
            require(len(created) == 1 and len(proxies) == 2 and len(resolutions) == 1, 'boundary composition duplicated or omitted owner/gates')
            require(instance.runtime.options.get('command_prefix', ()) == (), 'Linux got Darwin argv prefix')
            require(instance.native_owner.options['model_owner'] is created[0], 'Codex bridge escaped model owner')
            require({row['identity']['nonce'] for row in c.state()['environments'].values()} ==
                    {fixtures.SimulatedEnvironment.instances[0].identity['nonce']}, 'model owner became research evidence')
            instance.renew(10)
            require(created[0].renewals == [10] and fixtures.SimulatedEnvironment.instances[0].renewals == [10],
                    'renewal omitted one owner')
            if recovery is None:
                created[0].failed_cleanup = True
                result = instance.finish()
                require(result['cleanup'] == 'unresolved' and result['resources']['source-main'] == 'unknown',
                        'model cleanup failure released resource')
            else:
                for gate in (instance.provider_gate, instance.lab_gate): gate.close()
                c.revoke_worker('lead-1', 1, reason='fixture-process-loss')
                runner.controller = Controller(c.root); runner.contract = frozen_inputs(runner.controller)
                captured = []
                def recover(receipt, configured, *, maximum_lease_seconds):
                    require(receipt == identity['owner_receipt'] and configured == runner.contract.runtime_profiles['runtime-main'] and maximum_lease_seconds == 60,
                            'recovery lost signed model or exact owner')
                    captured.append(True)
                    if recovery == 'held': raise RuntimeError('fixture-model-readback-unavailable')
                    return created[0].revoke_and_verify(receipt['session_id'])
                with patch.object(linux, 'recover_runtime_owner', recover):
                    state = runner.controller.state()
                    result = boundary.recover_boundary(context, state['dispatches'][grant['dispatch_id']])
                    require((result['status'] == 'settled') == (recovery == 'settled'), 'reopened model recovery mismatch: ' + str(result))
                    state = runner.controller.state()
                    require(state['usage']['invocations'] == 1 and len(resolutions) == 1,
                            'model recovery refunded invocation or resolved another credential')
                    require(bool(state['resource_holds']) == (recovery == 'held'), 'recovery resource hold mismatch')
                    if recovery == 'settled':
                        before = copy.deepcopy(state['usage'])
                        repeated = boundary.recover_boundary(context, state['dispatches'][grant['dispatch_id']])
                        require(repeated['status'] == 'settled' and runner.controller.state()['usage'] == before,
                                'repeat model recovery charged twice')
                require(captured, 'Linux recovery dispatcher was bypassed')
        finally:
            for gate in (instance.provider_gate, instance.lab_gate):
                if gate: gate.close()
            import shutil
            for path in (instance.state_dir, instance.socket_dir):
                if path and path.exists(): shutil.rmtree(path)
    return {'signed_controller': True, 'native_and_container_simulated': True,
        'image_check_before_credential_resolution': True, 'separate_stdio_provider_gate': True,
        'both_owners_renewed': True, 'model_cleanup_failure_held': recovery is None, 'reopened_recovery': recovery}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); os.umask(0o077); checks = []
    with tempfile.TemporaryDirectory(prefix='linux-model-host-') as temporary:
        base = Path(temporary).resolve()
        for name, scenario in [('signed-profile', profile_contract), ('durable-owner-ledger', ledger),
                               ('signed-model-catalog', catalog_contract), ('native-catalog-staging', native_catalog),
                               ('private-bootstrap', bootstrap), ('owned-lifecycle', owned_lifecycle),
                               ('catalog-bootstrap', lambda p: bootstrap(p, catalog=True)),
                               ('catalog-staging', lambda p: owned_lifecycle(p, catalog=True)),
                               ('nonroot-namespace-readback', lambda p: owned_lifecycle(p, host_permission_denied=True)), ('composed-boundary', composed_boundary),
                               ('reopened-linux-recovery', lambda p: composed_boundary(p, recovery='settled')),
                               ('reopened-linux-hold', lambda p: composed_boundary(p, recovery='held')), ('codex-container-paths', lambda p: adapter(p, 'codex')),
                               ('omp-container-paths', lambda p: adapter(p, 'omp'))]:
            try: details = scenario(base / name); checks.append({'name': name, 'passed': True, 'details': details})
            except Exception as error: checks.append({'name': name, 'passed': False, 'error': type(error).__name__,
                'code': str(error)[:256]})
    result = {'kind': 'linux-model-host-contained-e2e-v1', 'classification': 'signed_controller_and_controlled_subprocesses',
        'status': 'passed' if all(x['passed'] for x in checks) else 'failed', 'checks': checks,
        'docker_calls': 0, 'provider_calls': 0, 'target_calls': 0,
        'unverified': ['real_linux_container_isolation', 'actual_native_model_startup', 'provider_inference', 'hosted_recovery']}
    args.output.write_text(json.dumps(result, indent=2) + '\n'); print(json.dumps(result))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
