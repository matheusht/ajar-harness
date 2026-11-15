#!/usr/bin/env python3
"""Signed capture/reset/replay workflow with actual owned HTTP and private relays.

Python 3, OpenSSL and ssh-keygen; no provider, Docker daemon, SSH host or external
target. Container and native peers are explicitly simulated. Run --output FILE.
Expected: valid reset captures baseline from a distinct owner; absent authority,
changed profile, stale/late start evidence and uncertain cleanup cannot be clean.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
import check_engagement_contract_e2e as fixture
import check_engagement_native_boundary_e2e as native
from check_application_owner_e2e import COUNTER
from check_native_application_capture_e2e import LocalProbeEnvironment, submit, value
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller
from engagement_controller import GRANT_KEYS
from engagement_runner import WorkerContext, frozen_inputs
from engagement_network_bridge import ProxyBridge


def require(condition, message):
    if not condition: raise AssertionError(message)


def configured(path, *, combined=False, applications=1, reset_capability=True, state_volumes=None):
    inputs = fixture.make_fixture(path / 'input')
    document = json.loads(inputs.read_text()); scope = fixture.fixture_scope(inputs)
    counter = path / 'counter.py'; fixture.write(counter, COUNTER.encode())
    scope['access'] = scope['access'] if combined else []
    scope['network']['target'] = []
    environment = copy.deepcopy(scope['environments'][0]); environment['profile_id'] = 'target-main'
    environment['capabilities'] = ['application']
    target_profile = json.loads(Path(document['environment_profiles']['lab-main']).read_text())
    target_profile['image_id'] = 'sha256:' + '3' * 64
    target_file = path / 'target-environment.json'; fixture.write(target_file, canonical(target_profile))
    environment['profile_sha256'] = digest(target_file.read_bytes())
    scope['environments'].append(environment)
    template = scope['effects'][0]
    scope['effects'] = [dict(template, id='read-app', access_ids=[])]
    scope['application_states'] = []
    document['application_profiles'] = {}
    ports = set(); first = None
    for index in range(applications):
        while True:
            bound = socket.socket(); bound.bind(('127.0.0.1', 0)); port = bound.getsockname()[1]; bound.close()
            if port not in ports: break
        ports.add(port)
        identity = 'app-main' if index == 0 else 'app-other'
        host = 'counter.invalid' if index == 0 else 'counter-other.invalid'
        url = f'http://{host}:{port}'
        scope['access'].append({'id': identity, 'kind': 'application',
            'identity': {'base_url': url + '/', 'version': 'counter-v1'}, 'account_refs': [], 'permissions': ['read', 'reset']})
        scope['network']['target'].append({'protocol': 'http', 'host': host, 'port': port,
            'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}})
        effect_id = 'reset-app' if index == 0 else 'reset-other'
        scope['effects'].append(dict(template, id=effect_id, kind='reset', access_ids=[identity],
            environment_ids=['target-main'], cleanup_required=True))
        command = [sys.executable, str(counter), str(port)]
        if state_volumes is not None:
            command.append(state_volumes[0]['path'])
        profile = {'kind': 'owned-application-state-v1', 'method': 'owned-container-recreate-v1',
            'baseline_id': 'counter-zero', 'command': command, 'service_port': port}
        if state_volumes is not None:
            counter.write_text('''import http.server,pathlib,sys
path=pathlib.Path(sys.argv[2]);path.mkdir(parents=True,exist_ok=True);value_file=path/'value'
if not value_file.exists():value_file.write_text('0')
class Counter(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  value=int(value_file.read_text()) if value_file.exists() else 0
  if self.path=='/increment':value+=1;value_file.write_text(str(value))
  data=str(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
http.server.HTTPServer(('127.0.0.1',int(sys.argv[1])),Counter).serve_forever()
''')
            profile.update(kind='owned-application-state-v2', method='owned-container-recreate-v2',
                state_volumes=copy.deepcopy(state_volumes))
        filename = path / (identity + '.json'); fixture.write(filename, canonical(profile))
        scope['application_states'].append({'access_id': identity, 'profile_sha256': digest(filename.read_bytes()),
            'environment_id': 'target-main', 'reset_effect_id': effect_id})
        document['application_profiles'][identity] = str(filename)
        if first is None: first = profile, filename
    scope['effects'][0]['access_ids'] = [row['id'] for row in scope['access']]
    scope['limits']['hard']['invocations'] = 100
    scope['limits']['max_workers'] = 10
    scope['limits']['hard']['worker_seconds'] = 10000
    if not combined: document['access_files'] = {}
    document['environment_profiles']['target-main'] = str(target_file)
    if not reset_capability:
        scope.pop('application_states'); document.pop('application_profiles')
        scope['effects'] = [row for row in scope['effects'] if row['kind'] != 'reset']
    fixture.write(inputs, canonical(document)); fixture.resign_fixture(inputs, scope)
    return inputs, scope, *first


class TargetEnvironment(native.SimulatedEnvironment):
    processes = []
    cleanup_fails = False

    def __init__(self, profile, limits, authorize, observe, **options):
        prior = next((row for row in self.instances if isinstance(row, TargetEnvironment)
            and options.get('receipt') is not None and row.identity is not None
            and row.identity['nonce'] == options['receipt']['nonce']), None)
        def stamped(event):
            event = copy.deepcopy(event)
            event['identity']['container_id'] = digest(event['identity']['nonce'].encode())[7:]
            return observe(event)
        super().__init__(profile, limits, authorize, stamped, **options)
        self.owned_processes = prior.owned_processes if prior else []

    def receipt(self):
        identity = super().receipt()
        if identity: identity['container_id'] = digest(identity['nonce'].encode())[7:]
        return identity

    def readback(self):
        return {**super().readback(), 'identity': self.receipt()}

    def launch_stdio(self, argv, *, role='native_tools'):
        require(role in ('application', 'application_connector'), 'untrusted target role')
        self.authorize()
        operation = uuid.uuid4().hex
        common = {'kind': 'environment-observation-v2', 'operation': 'launch_stdio',
            'operation_id': operation, 'identity': self.receipt(), 'role': role}
        self.observe(dict(common, phase='intent', request_sha256=digest(canonical(argv))))
        mapped = []
        for item in argv:
            if item.startswith('/input/'):
                _, _, name, *parts = item.split('/')
                item = str(Path(self.staged[name]['path']).joinpath(*parts))
            mapped.append(item)
        process = subprocess.Popen(mapped, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True)
        self.owned_processes.append(process); self.__class__.processes.append(process)
        self.observe(dict(common, phase='result', status='dispatched', native_acknowledgment='caller_required'))
        return process

    def cleanup(self):
        if self.cleanup_fails: raise ValueError('fixture-target-cleanup-unobserved')
        for process in self.owned_processes:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
        return {**super().cleanup(), 'identity': self.receipt()}


PROBE = b'''import http.client,os,urllib.parse,sys
proxy=urllib.parse.urlsplit(os.environ['HTTP_PROXY'])
for target in (value for value in sys.argv[3:] if value.startswith('http://')):
    for path in ('/','/' if 'control' in sys.argv[4:] else '/increment','/'):
        conn=http.client.HTTPConnection(proxy.hostname,proxy.port,timeout=5)
        conn.request('GET',target.rstrip('/')+path)
        response=conn.getresponse()
        if response.status!=200:raise RuntimeError('target refused '+str(response.status))
        print(response.read().decode());conn.close()
'''


class FreshRuntime(native.SimulatedRuntime):
    def fresh(self):
        self.session_id = 'simulated-session-' + uuid.uuid4().hex
        return {'session_id': self.session_id}


@contextmanager
def composed(path, **options):
    import engagement_native_boundary as boundary
    import application_state
    inputs, scope, profile, filename = configured(path, **options)
    controller = Controller.initialize(path / 'engagement', load_inputs(inputs), evidence_class='engineering_simulation')
    workspace = path / 'workspace'; workspace.mkdir(mode=0o700)
    grant = controller.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
        resources=[row['id'] for row in scope['access']], adapter_id='fixture-native')
    runner = SimpleNamespace(controller=controller, contract=frozen_inputs(controller), changed=threading.Event())
    context = WorkerContext(runner, controller.state()['workers']['lead-1'], grant, workspace)
    def bundle(profile, identity):
        return {'support_input': {'path': profile['tool_bundle']['path'], 'manifest_sha256': profile['tool_bundle']['manifest_sha256']},
            'command': ['/input/' + identity + '/bin/codex', 'exec-server', '--listen', 'stdio'],
            'expected_version': 'engineering-fixture', 'expected_platform': 'linux'}
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {}, clear=False))
        os.environ.pop('OSLIT_ACCOUNT_BINDINGS', None)
        stack.enter_context(patch.object(boundary, 'Environment', LocalProbeEnvironment))
        stack.enter_context(patch.object(application_state, 'Environment', TargetEnvironment))
        stack.enter_context(patch.object(boundary, 'ProxyBridge', ProxyBridge))
        stack.enter_context(patch.object(boundary, '_inspect_bundle', bundle))
        stack.enter_context(patch.object(boundary, '_credential_resolver', lambda: lambda profile: SimpleNamespace(check=lambda: None, revoke=lambda: None)))
        stack.enter_context(patch.object(boundary.codex, 'Runtime', FreshRuntime))
        stack.enter_context(patch.object(boundary.codex, 'NativeExecutor', native.SimulatedExecutor))
        native.SimulatedEnvironment.instances = []; LocalProbeEnvironment.processes = []; TargetEnvironment.processes = []
        native.SimulatedEnvironment.cleanup_fails = TargetEnvironment.cleanup_fails = False
        instance = boundary.NativeBoundary(context)
        try:
            started = instance.start()
            controller.record_worker_started('lead-1', 1, started['session_id'], workspace, owner_receipt=started['owner_receipt'])
            x = SimpleNamespace(boundary=instance, controller=controller, context=context, serial=0,
                inputs=inputs, scope=scope, profile=profile, filename=filename)
            artifact = controller.store_object(b'counter instrument\n')
            submit(x, 'instrument_register', {'instrument_id': 'instrument-1', 'artifact_sha256': artifact,
                'metric': 'counter-value', 'reset': 'owned-counter-zero', 'conditions': {}, 'supersedes': []})
            LocalProbeEnvironment.native_files = {'candidate.txt': b'counter candidate', 'probe.py': PROBE}
            yield x
        finally:
            TargetEnvironment.cleanup_fails = False
            for env in native.SimulatedEnvironment.instances:
                if isinstance(env, TargetEnvironment): env.cleanup()
            instance.finish()


def capture(x, **extra):
    arguments = {'instrument_id': 'instrument-1', 'candidate_path': 'candidate.txt', 'probe_path': 'probe.py',
        'interpreter': 'python3', 'arguments': [], 'conditions': {}, 'seconds': 20,
        'patch_id': None, 'patch_arm': None, **extra}
    with x.context.guard(): operation = x.boundary.host_call('engagement_capture', arguments)
    return operation.wait()


def record(x, captured, name, *, purpose='exploration', explains=None):
    submit(x, 'experiment_record', {'experiment_id': name, 'instrument_id': 'instrument-1',
        'candidate_sha256': captured['candidate_sha256'], 'probe_sha256': captured['probe_sha256'],
        'operation_id': captured['operation_id'], 'conditions': {},
        'resources': x.controller.state()['dispatches'][captured['dispatch_id']]['resources'],
        'purpose': purpose, 'score': None, 'explains': explains, 'supersedes': []})
    return x.controller.state()['experiments'][name]


def proof(x, captured):
    state = x.controller.state(); operation = state['environment_operations'][captured['operation_id']]
    return {'scope_sha256': state['scope_sha256'], 'dispatch_id': captured['dispatch_id'],
        'operation_id': captured['operation_id'], 'session_id': operation['session_id'],
        'client_environment_nonce': captured['environment_nonce'], 'clean_start': captured['clean_start'],
        'output_utf8': x.controller.read_object(captured['output_sha256']).decode(),
        'target_starts': [state['application_starts'][nonce] for nonce in operation.get('application_start_nonces', [])],
        'target_cleanup': {nonce: state['environments'][nonce].get('cleanup') for nonce in operation.get('application_start_nonces', [])},
        'requests': {name: state['network_operations'][name] for name in captured['network_request_ids']}}


def contract_cases(path):
    inputs, scope, profile, filename = configured(path)
    verified = load_inputs(inputs)
    require(verified.frozen_files['applications/app-main.json'] == filename.read_bytes(), 'application profile not frozen')
    original = filename.read_bytes()
    fixture.write(filename, canonical({**profile, 'baseline_id': 'changed'}))
    try: load_inputs(inputs)
    except Exception as error: require(getattr(error, 'code', None) == 'digest_mismatch', 'wrong profile-pin refusal')
    else: raise AssertionError('changed profile accepted')
    fixture.write(filename, original)
    for mutate in (
        lambda value: value['access'][0]['permissions'].remove('reset'),
        lambda value: value['application_states'][0].update(reset_effect_id='read-app'),
        lambda value: value['application_states'][0].update(environment_id='lab-main'),
        lambda value: value['access'][0]['identity'].update(base_url='http://production.example:80/')):
        changed = copy.deepcopy(scope); mutate(changed); fixture.resign_fixture(inputs, changed)
        try: load_inputs(inputs)
        except Exception: pass
        else: raise AssertionError('invalid signed reset relationship accepted')
    aliased = copy.deepcopy(scope)
    aliased['access'].append(dict(copy.deepcopy(scope['access'][0]), id='app-alias', permissions=['read']))
    aliased['effects'][0]['access_ids'].append('app-alias')
    fixture.resign_fixture(inputs, aliased)
    try: load_inputs(inputs)
    except Exception: pass
    else: raise AssertionError('same origin names distinct owned application identities')
    return {'frozen_application_profile_sha256': digest(verified.frozen_files['applications/app-main.json']),
        'negative_cases': ['changed_profile', 'missing_reset_permission', 'wrong_effect', 'wrong_environment', 'public_origin', 'duplicate_origin']}


def workflow(path):
    with composed(path) as x:
        status = value(x.boundary.host_call('engagement_status', {'since': None, 'limit': 100}).wait())
        require(status.get('application_baselines') == {'app-main': 'counter-zero'},
            'worker cannot discover its signed baseline through the native status tool')
        before = len(x.controller.state()['dispatches'])
        for starting in ({}, {'app-main': 'wrong'}, {'outside': 'counter-zero'}):
            response = capture(x, starting_state=starting)
            require(response.get('isError'), 'invalid starting state accepted')
            require(len(x.controller.state()['dispatches']) == before, 'invalid reset reserved work')
        first = capture(x, starting_state={'app-main': 'counter-zero'})
        require(not first.get('isError'), 'valid reset capture failed: ' + str(value(first)))
        first = value(first)
        require(first['clean_start'] is True and first['limits'] == [], 'reset capture not eligible')
        require(x.controller.read_object(first['output_sha256']) == b'0\n1\n1\n', 'probe did not reach fresh owned target')
        effect = record(x, first, 'first')
        second = capture(x, starting_state={'app-main': 'counter-zero'})
        require(not second.get('isError'), 'second reset capture failed: ' + str(value(second)))
        second = value(second); replay = record(x, second, 'second')
        require(x.controller.read_object(second['output_sha256']) == b'0\n1\n1\n', 'target was not recreated')
        require(effect['application_state'] == replay['application_state'], 'stable baseline changed')
        require(effect['application_generations']['app-main'] != replay['application_generations']['app-main'], 'generation reused')
        state = x.controller.state()
        require(not state['resource_holds'], 'clean target left hold')
        require(all(row.get('target_nonce') in state['application_starts'] for row in state['network_operations'].values()),
            'actual requests lack protected target identity')
        starts = list(state['application_starts'].values())
        require(all(row['operation_id'] for row in starts), 'start receipt was not consumed exactly once')
        require(all(state['environments'][nonce].get('cleanup') == 'verified' for nonce in state['application_starts']),
            'target cleanup not journaled')
        current = state['environment_operations'][second['operation_id']]
        late = dict(starts[0]['receipt'], target_nonce=starts[1]['receipt']['target_nonce'])
        try: x.controller.record_application_start(current['grant'], 'target-main', late)
        except Exception: pass
        else: raise AssertionError('late/reused reset receipt accepted')
        require(all(p.poll() is not None for p in TargetEnvironment.processes), 'target or connector process survived')
        return {'captures': [proof(x, first), proof(x, second)], 'resource_holds': state['resource_holds']}


def failed_cleanup(path):
    with composed(path) as x:
        TargetEnvironment.cleanup_fails = True
        result = capture(x, starting_state={'app-main': 'counter-zero'})
        require(result.get('isError'), 'unobserved cleanup reported success')
        state = x.controller.state()
        require(state['resource_holds'].get('app-main') and state['cleanup'] != 'verified', 'target uncertainty not held')
        require(any(row['status'] == 'unknown' for row in state['dispatches'].values()), 'reservation silently settled')
        return {'resource_holds': state['resource_holds'], 'cleanup': state['cleanup'],
            'dispatch_states': {name: row['status'] for name, row in state['dispatches'].items()}}


def recovery(path):
    import engagement_native_boundary as boundary
    with composed(path) as x:
        TargetEnvironment.cleanup_fails = True
        result = capture(x, starting_state={'app-main': 'counter-zero'})
        require(result.get('isError'), 'unobserved cleanup reported success')
        state = x.controller.state()
        dispatch, = [row for row in state['dispatches'].values() if row.get('parent_dispatch_id')]
        grant = {key: dispatch[key] for key in GRANT_KEYS}
        context = WorkerContext(x.context.runner, state['workers']['lead-1'], grant, x.context.workspace)
        before = (len(state['dispatches']), len(state['environment_operations']), len(state['network_operations']))
        TargetEnvironment.cleanup_fails = False
        def recovered_environment(profile, *args, **kwargs):
            cls = TargetEnvironment if profile['image_id'] == 'sha256:' + '3' * 64 else LocalProbeEnvironment
            return cls(profile, *args, **kwargs)
        with patch.object(boundary, 'Environment', recovered_environment):
            recovered = boundary.recover_boundary(context, dispatch)
        require(recovered['status'] == 'settled', 'recovery did not settle: ' + str(recovered))
        state = x.controller.state()
        require(not state['resource_holds'], 'owned target cleanup did not release held application')
        require(before == (len(state['dispatches']), len(state['environment_operations']), len(state['network_operations'])),
            'recovery blindly relaunched target or probe')
        require(all(process.poll() is not None for process in TargetEnvironment.processes), 'target process survived recovery')
        return {'recovery': recovered, 'counts_before_and_after': before, 'resource_holds': state['resource_holds'],
            'target_cleanup': {nonce: state['environments'][nonce].get('cleanup') for nonce in state['application_starts']}}


def fresh_replay(path):
    import engagement_native_boundary as boundary
    from engagement_evidence import related
    with composed(path) as x:
        first = value(capture(x, starting_state={'app-main': 'counter-zero'}))
        effect = record(x, first, 'effect', purpose='effect')
        control = value(capture(x, starting_state={'app-main': 'counter-zero'}, arguments=['control']))
        require(x.controller.read_object(control['output_sha256']) == b'0\n0\n0\n', 'control incremented counter')
        record(x, control, 'control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'increment-request'})
        submit(x, 'publish', {'publication_id': 'contrary', 'kind': 'observation', 'subject': 'bounded counter fixture',
            'body': 'Controlled plumbing fixture; not a security finding.', 'refs': [], 'supersedes': [], 'artifacts': []})
        submit(x, 'claim_propose', {'claim_id': 'claim-1', 'text': 'Counter increments only when requested.',
            'effect': 'effect', 'control': 'control', 'replay': None, 'contrary': ['contrary'], 'resources': ['app-main'], 'supersedes': []})
        submit(x, 'worker_request', {'worker_id': 'reviewer-1', 'role': 'reviewer', 'profile_id': 'runtime-main',
            'question': 'Independently repeat the owned counter.'})
        submit(x, 'review_request', {'review_id': 'review-1', 'kind': 'claim', 'subject_id': 'claim-1', 'reviewer_id': 'reviewer-1'})
        stopped = x.boundary.finish()
        require(stopped['resources']['app-main'] in ('reset', 'unchanged'), 'clean owned target blocked independent reviewer')
        x.controller.record_worker_stopped(x.context.grant, 'lab-main', {'runtime': stopped['runtime'], 'environment': stopped['environment']})
        x.controller.record_environment_cleanup(x.context.grant, 'lab-main', stopped['environment_cleanup'])
        receipt = x.controller.store_receipt(x.context.grant, {'status': 'settled', 'worker_seconds': 1,
            'resources': stopped['resources'], 'usage': {'tokens': None, 'cost': None}, 'cleanup': 'verified'}, adapter_id='fixture-native')
        x.controller.adopt_receipt(x.context.grant['dispatch_id'], receipt, adapter_id='fixture-native')
        workspace = path / 'reviewer-workspace'; workspace.mkdir(mode=0o700)
        grant = x.controller.prepare_worker_dispatch('reviewer-1', 1, workspace, seconds=30,
            resources=['app-main'], adapter_id='fixture-native')
        context = WorkerContext(x.context.runner, x.controller.state()['workers']['reviewer-1'], grant, workspace)
        instance = boundary.NativeBoundary(context)
        try:
            started = instance.start()
            x.controller.record_worker_started('reviewer-1', 1, started['session_id'], workspace, owner_receipt=started['owner_receipt'])
            y = SimpleNamespace(controller=x.controller, context=context, boundary=instance, serial=1000)
            captured = value(capture(y, starting_state={'app-main': 'counter-zero'}))
            replay = record(y, captured, 'replay', purpose='replay', explains={'experiment_id': 'effect', 'variable': None})
            require(x.controller.read_object(captured['output_sha256']) == b'0\n1\n1\n', 'reviewer did not observe fresh effect')
            require(related(effect, replay, 'replay', independent=True), 'fresh baseline-equivalent replay not eligible')
            same_generation = copy.deepcopy(replay); same_generation['application_generations'] = effect['application_generations']
            require(not related(effect, same_generation, 'replay', independent=True), 'same target counted as independent replay')
            changed_baseline = copy.deepcopy(replay); changed_baseline['application_state']['app-main']['baseline_id'] = 'other'
            require(not related(effect, changed_baseline, 'replay', independent=True), 'different baseline counted as comparable')
            return {'effect': proof(x, first), 'control_output': x.controller.read_object(control['output_sha256']).decode(),
                'replay': proof(y, captured), 'independent_replay_eligible': True, 'claim_confirmation': 'not_requested'}
        finally:
            instance.finish()


def combined_multiple(path):
    with composed(path, combined=True, applications=2) as x:
        before = len(x.controller.state()['dispatches'])
        require(capture(x, starting_state={'app-main': 'counter-zero'}).get('isError'), 'partial application reset map accepted')
        require(len(x.controller.state()['dispatches']) == before, 'partial map reserved work')
        result = capture(x, starting_state={'app-main': 'counter-zero', 'app-other': 'counter-zero'})
        require(not result.get('isError'), 'combined capture failed: ' + str(value(result)))
        captured = value(result); experiment = record(x, captured, 'combined')
        require(captured['clean_start'] and x.controller.read_object(captured['output_sha256']) == b'0\n1\n1\n0\n1\n1\n',
            'combined capture did not reset both actual targets')
        require(set(experiment['application_state']) == {'app-main', 'app-other'}
            and len({row['target_nonce'] for row in experiment['application_generations'].values()}) == 2,
            'combined targets lost independent identity')
        source = capture(x, resources=['source-main'])
        require(not source.get('isError') and value(source)['clean_start'] and not value(source)['network_request_ids'],
            'source-only subset inherited an application requirement')
        return {'combined': proof(x, captured), 'source_subset': proof(x, value(source))}


def missing_authority(path):
    with composed(path, reset_capability=False) as x:
        before = len(x.controller.state()['dispatches'])
        result = capture(x, starting_state={'app-main': 'counter-zero'})
        require(result.get('isError') and len(x.controller.state()['dispatches']) == before,
            'reset permission alone activated unsigned ownership')
        require(not TargetEnvironment.processes, 'unsigned owner started a target')
        return {'dispatches_before_and_after': before, 'target_processes': len(TargetEnvironment.processes), 'refusal': value(result)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', choices=('contract', 'workflow', 'cleanup', 'recovery', 'replay', 'combined', 'authority', 'all'), default='all')
    args = parser.parse_args(); result = {'kind': 'application-reset-capture-e2e-v1',
        'classification': 'actual_http_probe_private_relays_signed_journal_with_simulated_container_and_native_peers',
        'checks': [], 'unverified': ['Docker isolation', 'SSH transport', 'live provider', 'fresh-target research']}
    try:
        with tempfile.TemporaryDirectory(prefix='application-reset-e2e-') as name:
            root = Path(name).resolve()
            for label, function in (('contract', contract_cases), ('workflow', workflow), ('cleanup', failed_cleanup),
                                    ('recovery', recovery), ('replay', fresh_replay),
                                    ('combined', combined_multiple), ('authority', missing_authority)):
                if args.scenario not in ('all', label): continue
                directory = root / label; directory.mkdir()
                observed = function(directory)
                result['checks'].append({'name': label, 'passed': True, 'observed': observed})
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'; result['error'] = type(error).__name__ + ': ' + str(error)
    result['command'] = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    result['source_sha256'] = {name: 'sha256:' + hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        'tools/application_state.py', 'tools/engagement_contract.py', 'tools/engagement_controller.py',
        'tools/engagement_evidence.py', 'tools/engagement_native_boundary.py', 'tools/engagement_network.py',
        'tools/engagement_network_bridge.py', 'tools/research_environment.py', 'tools/target_accounts.py',
        'evals/native-qualification/smoke/check_application_reset_e2e.py')}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
