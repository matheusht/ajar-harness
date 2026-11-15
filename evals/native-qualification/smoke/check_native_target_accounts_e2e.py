#!/usr/bin/env python3
"""NativeBoundary + signed journal + real owned HTTP account workflow.

No model, Docker daemon, SSH host or external target is contacted. Native runtime
and environment peers are explicit simulations; NetworkGate, account resolution,
HTTP sockets and controller records are real. Run --output FILE; expect pass.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import copy
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
import engagement_native_boundary as boundary
from engagement_contract import canonical, digest, load_inputs, source_manifest
from engagement_controller import Controller
from engagement_runner import WorkerContext, frozen_inputs
import check_engagement_native_boundary_e2e as native


def require(value, message):
    if not value:
        raise AssertionError(message)


@contextmanager
def receiver():
    seen, entered, release = [], threading.Event(), threading.Event()
    values = {name: 'fixture-' + uuid.uuid4().hex for name in ('a', 'b')}
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            headers = dict(self.headers)
            account = next((name for name, value in values.items()
                if self.headers.get('X-Fixture-Auth') == value), 'anonymous')
            seen.append({'account': account, 'selectors': any(name.lower().startswith('x-oslit-') for name in headers)})
            if self.path == '/wait':
                entered.set()
                release.wait(10)
            body = canonical({'account': account})
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield SimpleNamespace(url='http://127.0.0.1:' + str(server.server_port), values=values,
            seen=seen, entered=entered, release=release)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(2)


@contextmanager
def composed(path, target, *, reference_place='private', missing=False, combined=False,
             environment_class=native.SimulatedEnvironment, proxy_class=native.SimulatedProxy):
    fixture = native.fixture.fixture
    inputs = fixture.make_fixture(path / 'input')
    scope = fixture.fixture_scope(inputs)
    original_source = copy.deepcopy(scope['access'][0])
    source_path = Path(json.loads(inputs.read_text())['access_files']['source-main'])
    scope['access'] = ([original_source] if combined else []) + [{
        'id': 'app-main', 'kind': 'application',
        'identity': {'base_url': target.url, 'version': None},
        'account_refs': ['owner-a', 'owner-b'], 'permissions': ['read']}]
    scope['network']['target'] = [{'protocol': 'http', 'host': '127.0.0.1',
        'port': int(target.url.rsplit(':', 1)[1]),
        'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}}]
    resources = [row['id'] for row in scope['access']]
    template = scope['effects'][0]
    scope['effects'] = [dict(template, id='read-anonymous', access_ids=resources, account_refs=[]),
        dict(template, id='read-account', access_ids=['app-main'], account_refs=['owner-a', 'owner-b'])]
    data = json.loads(inputs.read_text())
    if not combined:
        data['access_files'] = {}
    fixture.write(inputs, canonical(data))
    binding = {'kind': 'target-account-bindings-v1', 'bindings': [
        {'access_id': 'app-main', 'account_ref': 'owner-' + name, 'origin': target.url,
            'headers': {'X-Fixture-Auth': 'env_OSLIT_FIXTURE_ACCOUNT_' + name.upper()}}
        for name in ('a', 'b')]}
    if reference_place == 'input':
        reference = source_path / 'private-references.json'
        fixture.write(reference, canonical(binding))
        scope['access'][0]['identity']['manifest_sha256'] = digest(canonical(source_manifest(source_path)))
    else:
        reference = path / 'private-references.json'
    fixture.resign_fixture(inputs, scope)
    contract = load_inputs(inputs)
    controller = Controller.initialize(path / 'engagement', contract, evidence_class='engineering_simulation')
    workspace = path / 'workspace'
    workspace.mkdir(mode=0o700)
    if reference_place == 'record':
        reference = controller.root / 'private-references.json'
    elif reference_place == 'workspace':
        reference = workspace / 'private-references.json'
    if reference_place != 'input':
        fixture.write(reference, canonical(binding))
    reference.chmod(0o600)
    grant = controller.prepare_worker_dispatch('lead-1', 1, workspace, seconds=20,
        resources=resources, adapter_id='fixture-native')
    runner = SimpleNamespace(controller=controller, contract=frozen_inputs(controller), changed=threading.Event())
    context = WorkerContext(runner, controller.state()['workers']['lead-1'], grant, workspace)
    def bundle(profile, identity):
        return {'support_input': {'path': profile['tool_bundle']['path'],
            'manifest_sha256': profile['tool_bundle']['manifest_sha256']},
            'command': ['/input/' + identity + '/bin/codex', 'exec-server', '--listen', 'stdio'],
            'expected_version': 'engineering-fixture', 'expected_platform': 'linux'}
    environment = {'OSLIT_ACCOUNT_BINDINGS': str(reference),
        'OSLIT_FIXTURE_ACCOUNT_A': target.values['a'], 'OSLIT_FIXTURE_ACCOUNT_B': target.values['b']}
    if missing:
        environment['OSLIT_FIXTURE_ACCOUNT_B'] = ''
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment))
        stack.enter_context(patch.object(boundary, 'Environment', environment_class))
        stack.enter_context(patch.object(boundary, 'ProxyBridge', proxy_class))
        stack.enter_context(patch.object(boundary, '_inspect_bundle', bundle))
        stack.enter_context(patch.object(boundary, '_credential_resolver', lambda: lambda profile: SimpleNamespace(check=lambda: None, revoke=lambda: None)))
        stack.enter_context(patch.object(boundary.codex, 'Runtime', native.SimulatedRuntime))
        stack.enter_context(patch.object(boundary.codex, 'NativeExecutor', native.SimulatedExecutor))
        native.SimulatedEnvironment.instances = []
        native.SimulatedEnvironment.cleanup_fails = False
        instance = boundary.NativeBoundary(context)
        try:
            yield SimpleNamespace(boundary=instance, controller=controller, context=context,
                root=path, target=target, reference=reference)
        finally:
            instance.finish()


def start(x):
    identity = x.boundary.start()
    x.controller.record_worker_started('lead-1', 1, identity['session_id'], x.context.workspace,
        owner_receipt=identity['owner_receipt'])


def account_workflow(path, target):
    with composed(path, target) as x:
        start(x)
        for name in ('a', 'b', None):
            headers = {'X-OSLit-Access': 'app-main'}
            if name:
                headers['X-OSLit-Account'] = 'owner-' + name
            response = x.boundary.lab_gate.fetch(target.url + '/who', headers=headers)
            require(json.loads(response['body'])['account'] == (name or 'anonymous'), 'wrong account reached target')
        require(not any(row['selectors'] for row in target.seen), 'public selectors reached target')
        operations = x.controller.state()['network_operations']
        require(len(operations) == 3, 'target requests were not recorded')
        require({row['intent']['account_ref'] for row in operations.values()} == {'owner-a', 'owner-b', None}, 'wrong account attribution')
        require(all(row['environment_nonce'] == x.boundary.environment.identity['nonce'] and
            row['grant'] == x.context.grant and row['result']['status'] == 'settled' for row in operations.values()),
            'request missing exact environment or grant')
        for filename in x.controller.root.rglob('*'):
            if filename.is_file():
                raw = filename.read_bytes()
                require(all(value.encode() not in raw for value in target.values.values()), 'secret entered controller record')
        require(x.boundary.provider_gate.request_binder is None, 'target resolver attached to provider gate')
        before = len(target.seen)
        try:
            x.boundary.lab_gate.fetch(target.url + '/who', headers={'X-OSLit-Access': 'app-main', 'X-OSLit-Account': 'outsider'})
        except Exception:
            pass
        else:
            raise AssertionError('unsigned account accepted')
        require(len(target.seen) == before, 'unsigned account reached target')
        binder = x.boundary.target_accounts.bind
        x.boundary.finish()
        try:
            binder('GET', target.url + '/who', {}, request_length=0)
        except Exception as error:
            require(getattr(error, 'code', str(error)) == 'target_account_binding_closed', 'private account binding remained usable')
        else:
            raise AssertionError('account binding survived finish')


def renewed_reply(path, target):
    with composed(path, target) as x:
        start(x)
        admitted = copy.deepcopy(x.context.grant)
        reply = []
        def fetch():
            try:
                reply.append(x.boundary.lab_gate.fetch(target.url + '/wait',
                    headers={'X-OSLit-Access': 'app-main', 'X-OSLit-Account': 'owner-a'}))
            except Exception as error:
                reply.append({'error': getattr(error, 'code', type(error).__name__)})
        worker = threading.Thread(target=fetch)
        worker.start()
        require(target.entered.wait(5), 'request never reached owned target')
        renew = x.controller.renew_dispatch
        def delayed_publish(*args, **kwargs):
            renewed = renew(*args, **kwargs)
            threading.Event().wait(.15)
            return renewed
        with patch.object(x.controller, 'renew_dispatch', delayed_publish):
            x.context.renew(30)
        require(x.context.grant != admitted, 'fixture failed to renew grant')
        target.release.set()
        worker.join(5)
        require(not worker.is_alive() and reply and 'error' not in reply[0], 'late response was not delivered')
        operation, = x.controller.state()['network_operations'].values()
        require(operation['grant'] == admitted and operation['result']['status'] == 'settled', 'renewal changed admitted request identity')


def revoked_reply(path, target):
    with composed(path, target) as x:
        start(x)
        admitted = copy.deepcopy(x.context.grant)
        reply = []
        def fetch():
            try:
                x.boundary.lab_gate.fetch(target.url + '/wait',
                    headers={'X-OSLit-Access': 'app-main', 'X-OSLit-Account': 'owner-a'})
                reply.append('delivered')
            except Exception:
                reply.append('revoked')
        worker = threading.Thread(target=fetch)
        worker.start()
        require(target.entered.wait(5), 'request never reached owned target')
        x.controller.revoke_worker('lead-1', 1, reason='fixture revoke')
        target.release.set()
        worker.join(5)
        require(not worker.is_alive() and reply == ['revoked'], 'revoked response was delivered')
        state = x.controller.state()
        operation, = state['network_operations'].values()
        require(operation['grant'] == admitted and operation['result']['status'] == 'unknown',
            'revoked request lost its unknown result or original grant')
        require(state['resource_holds'] == {'app-main': [admitted['dispatch_id']]},
            'uncertain target request was not held')


def bad_reference(path, target, place):
    with composed(path, target, reference_place=place, combined=place == 'input') as x:
        try:
            start(x)
        except Exception as error:
            require(getattr(error, 'code', None) == 'target_account_references_exposed', 'wrong reference isolation refusal')
        else:
            raise AssertionError('worker-visible credential reference accepted')
        require(not x.boundary.execution_admitted and not native.SimulatedEnvironment.instances, 'unsafe reference reached environment preparation')
        require(not target.seen, 'unsafe reference caused target contact')


def missing_credential(path, target):
    with composed(path, target, missing=True) as x:
        try:
            start(x)
        except Exception as error:
            require(getattr(error, 'code', None) == 'target_account_credential_unavailable', 'wrong missing credential refusal')
        else:
            raise AssertionError('missing credential accepted')
        require(not x.boundary.execution_admitted and not native.SimulatedEnvironment.instances, 'missing credential reached environment preparation')
        require(not target.seen, 'missing credential caused target contact')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = [('account-workflow', account_workflow), ('renewed-reply', renewed_reply), ('revoked-reply', revoked_reply),
        *[('reference-' + place, lambda path, target, place=place: bad_reference(path, target, place))
            for place in ('record', 'workspace', 'input')], ('missing-credential', missing_credential)]
    report = {'kind': 'native-target-accounts-e2e', 'classification': 'actual_owned_http_with_simulated_native_environment',
        'external_provider_calls': 0, 'external_target_calls': 0, 'docker_calls': 0, 'ssh_calls': 0, 'scenarios': []}
    for name, check in checks:
        try:
            with tempfile.TemporaryDirectory(prefix='native-target-account-') as folder, receiver() as target:
                check(Path(folder).resolve(), target)
            report['scenarios'].append({'scenario': name, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': name, 'status': 'fail', 'error': getattr(error, 'code', str(error))})
    report['status'] = 'pass' if all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    names = ['tools/engagement_native_boundary.py', 'tools/target_accounts.py', 'tools/engagement_network.py',
        'tools/engagement_evidence.py', 'tools/engagement_controller.py', 'tools/engagement_runner.py', str(Path(__file__).relative_to(ROOT))]
    report['source_sha256'] = {name: digest((ROOT / name).read_bytes()) for name in names if (ROOT / name).exists()}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
