#!/usr/bin/env python3
"""Protected application capture through actual owned HTTP, relay and probe.

Run --output FILE; expect pass. Python 3, ssh-keygen and OpenSSL are required.
Native model and container peers are simulated. No provider, external target,
Docker daemon or SSH host is contacted; this is not containment qualification.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from engagement_contract import digest
from engagement_network_bridge import ProxyBridge
import check_native_target_accounts_e2e as accounts
from check_native_target_accounts_e2e import require
from check_engagement_native_boundary_e2e import SimulatedEnvironment


class LocalProbeEnvironment(SimulatedEnvironment):
    """Run only the owned relay/probe; keep container ownership explicitly fake."""
    processes = []

    def mapped(self, value):
        if value.startswith('/input/'):
            parts = value.split('/')
            root = self.staged[parts[2]]['path'] if parts[2] in self.staged else self.access_files[parts[2]]
            return str(Path(root).joinpath(*parts[3:]))
        return value

    def launch_stdio(self, argv, *, role='native_tools'):
        require(role == 'network_proxy', 'test attempted native model/tool execution')
        process = subprocess.Popen([self.mapped(value) for value in argv],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        self.processes.append(process)
        return process


PROBE = b'''import http.client,json,os,sys,urllib.parse
target=next((value for value in sys.argv[3:] if value.startswith("http")),sys.argv[3])
if target.startswith("http"):
    proxy=urllib.parse.urlsplit(os.environ["HTTP_PROXY"])
    for account in (value for value in sys.argv[3:] if value in ("owner-a","owner-b","wait")):
        connection=http.client.HTTPConnection(proxy.hostname,proxy.port,timeout=6)
        path="/wait" if account=="wait" else "/who"
        account="owner-a" if account=="wait" else account
        connection.request("GET",target+path,headers={"X-OSLit-Access":"app-main","X-OSLit-Account":account})
        response=connection.getresponse()
        if response.status!=200: raise RuntimeError("request refused")
        print(response.read().decode().strip())
        connection.close()
else:
    import pathlib
    print("source_files",len(list(pathlib.Path(target).rglob("*"))))
'''


@contextmanager
def case(path, target, *, combined=False):
    LocalProbeEnvironment.processes = []
    with accounts.composed(path, target, combined=combined,
            environment_class=LocalProbeEnvironment, proxy_class=ProxyBridge) as x:
        accounts.start(x)
        x.serial = 0
        instrument = x.controller.store_object(b'fixture account observation\n')
        submit(x, 'instrument_register', {'instrument_id': 'instrument-1', 'artifact_sha256': instrument,
            'metric': 'account-label', 'reset': 'remote-state-not-reset', 'conditions': {}, 'supersedes': []})
        LocalProbeEnvironment.native_files = {'candidate.txt': b'harmless account probe', 'probe.py': PROBE}
        try:
            yield x
        finally:
            target.release.set()
    require(all(process.poll() is not None for process in LocalProbeEnvironment.processes), 'owned relay survived cleanup')


def submit(x, kind, payload):
    x.serial += 1
    return x.context.submit({'request_id': 'capture-test-' + str(x.serial),
        'expected_revision': x.controller.state()['revision'], 'type': kind, 'payload': payload})


def accept(x, *, resources=None, names=('owner-a', 'owner-b')):
    arguments = {'instrument_id': 'instrument-1', 'candidate_path': 'candidate.txt', 'probe_path': 'probe.py',
        'interpreter': 'python3', 'arguments': list(names), 'conditions': {}, 'seconds': 10,
        'patch_id': None, 'patch_arm': None}
    if resources is not None:
        arguments['resources'] = resources
    with x.context.guard():
        return x.boundary.host_call('engagement_capture', arguments)


def value(response):
    return json.loads(response['content'][0]['text'])


def captured(x, *, resources=None, names=('owner-a', 'owner-b')):
    result = accept(x, resources=resources, names=names).wait()
    require(not result.get('isError'), 'capture refused: ' + str(value(result)))
    return value(result)


def application(path, target):
    with case(path, target) as x:
        result = captured(x)
        state = x.controller.state()
        dispatch = state['dispatches'][result['dispatch_id']]
        require(dispatch['status'] == 'settled' and dispatch['observation']['resources'] == {'app-main': 'retained'},
            'application ownership was reset, lost or left unsettled')
        require(not state['resource_holds'] and state['workers']['lead-1']['status'] == 'active', 'capture stopped parent ownership')
        require(result['clean_start'] is False and result['limits'] == ['remote_application_reset_unverified'],
            'fresh local lab claimed remote application reset')
        require([row['account'] for row in target.seen] == ['a', 'b'] and not any(row['selectors'] for row in target.seen),
            'actual captured requests lost account binding or forwarded selectors')
        requests = result['network_request_ids']
        require(len(requests) == 2 and all(state['network_operations'][name]['grant']['dispatch_id'] == result['dispatch_id']
            and state['network_operations'][name]['environment_nonce'] == result['environment_nonce'] for name in requests),
            'request evidence not bound to auxiliary environment')
        submit(x, 'experiment_record', {'experiment_id': 'experiment-1', 'instrument_id': 'instrument-1',
            'candidate_sha256': result['candidate_sha256'], 'probe_sha256': result['probe_sha256'],
            'operation_id': result['operation_id'], 'conditions': {}, 'resources': ['app-main'],
            'purpose': 'exploration', 'score': None, 'explains': None, 'supersedes': []})
        experiment = x.controller.state()['experiments']['experiment-1']
        require(experiment['network_operations'] == requests and {row['account_ref'] for row in experiment['target_bindings']} == {'owner-a', 'owner-b'},
            'experiment did not derive actual protected request provenance')
        require(captured(x, names=('owner-a',))['dispatch_id'] != result['dispatch_id'], 'retained ownership prevented subsequent capture')
        for root in (x.controller.root, x.context.workspace):
            for file in root.rglob('*'):
                if file.is_file():
                    content = file.read_bytes()
                    require(not any(secret.encode() in content for secret in target.values.values()), 'credential persisted in published/staged data')


def combined_source(path, target):
    with case(path, target, combined=True) as x:
        result = captured(x, resources=['source-main'], names=())
        dispatch = x.controller.state()['dispatches'][result['dispatch_id']]
        require(dispatch['resources'] == ['source-main'] and result['clean_start'] is True,
            'source-only subset inherited application reset limitation')
        require(result['network_request_ids'] == [] and target.seen == [], 'source-only capture contacted target')
        combined = captured(x, resources=['app-main', 'source-main'], names=('owner-a',))
        require(combined['clean_start'] is False, 'combined capture claimed remote reset')


def invalid_resources(path, target):
    with case(path, target) as x:
        before = len(x.controller.state()['dispatches'])
        for resources in ([], ['outside'], ['app-main', 'app-main'], 'app-main'):
            response = accept(x, resources=resources).wait()
            require(response.get('isError') and value(response)['code'] == 'native_capture_resources_invalid',
                'invalid resource selection was not rejected')
            require(len(x.controller.state()['dispatches']) == before, 'invalid selection reserved work')


def parent_busy(path, target):
    with case(path, target) as x:
        reply = []
        def fetch():
            reply.append(x.boundary.lab_gate.fetch(target.url + '/wait', headers={
                'X-OSLit-Access': 'app-main', 'X-OSLit-Account': 'owner-a'}))
        worker = threading.Thread(target=fetch)
        worker.start()
        require(target.entered.wait(5), 'main request did not enter target')
        before = len(x.controller.state()['dispatches'])
        response = accept(x).wait()
        target.release.set(); worker.join(5)
        require(response.get('isError') and value(response)['code'] == 'native_capture_target_busy', 'capture overlapped parent target request')
        require(len(x.controller.state()['dispatches']) == before and reply, 'busy refusal reserved work or broke parent request')


def capture_busy(path, target, *, revoke=False):
    with case(path, target) as x:
        operation = accept(x, names=('wait',))
        reply = []
        worker = threading.Thread(target=lambda: reply.append(operation.wait()))
        worker.start()
        require(target.entered.wait(5), 'capture request did not enter target')
        before = len(target.seen)
        try:
            x.boundary.lab_gate.fetch(target.url + '/who', headers={'X-OSLit-Access': 'app-main', 'X-OSLit-Account': 'owner-a'})
        except Exception:
            pass
        else:
            raise AssertionError('parent request overlapped application capture')
        require(len(target.seen) == before, 'parent request reached target during capture')
        if revoke:
            x.controller.revoke_worker('lead-1', 1, reason='capture fixture revoke')
        target.release.set(); worker.join(10)
        require(not worker.is_alive() and reply, 'capture did not settle after response/revoke')
        state = x.controller.state()
        auxiliary, = [row for row in state['dispatches'].values() if row.get('parent_dispatch_id')]
        require(auxiliary['status'] == 'settled', 'capture left a pending reservation')
        if revoke:
            require(reply[0].get('isError'), 'revoked capture reported successful execution')
            request, = state['network_operations'].values()
            require(request['result']['status'] == 'unknown' and request['grant']['dispatch_id'] == auxiliary['dispatch_id'],
                'revoked request lost unknown effect provenance')
            require(auxiliary['observation']['resources'] == {'app-main': 'unknown'} and 'app-main' in state['resource_holds'],
                'revoked target uncertainty was released')
        else:
            require(not reply[0].get('isError'), 'capture failed after main request refusal')
            x.boundary.lab_gate.fetch(target.url + '/who', headers={'X-OSLit-Access': 'app-main', 'X-OSLit-Account': 'owner-a'})
            require(len(target.seen) == before + 1, 'parent gate stayed closed after capture')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', default='all')
    args = parser.parse_args()
    checks = {'application': application, 'combined-source': combined_source, 'invalid-resources': invalid_resources,
        'parent-busy': parent_busy, 'capture-busy': capture_busy,
        'revoked-capture': lambda path, target: capture_busy(path, target, revoke=True)}
    report = {'classification': 'actual_owned_http_relay_probe_with_simulated_native_environment',
        'provider_calls': 0, 'external_target_calls': 0, 'docker_calls': 0, 'ssh_calls': 0, 'scenarios': []}
    for name, check in checks.items():
        if args.scenario not in ('all', name):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='app-capture-') as folder, accounts.receiver() as target:
                check(Path(folder).resolve(), target)
            report['scenarios'].append({'scenario': name, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': name, 'status': 'fail', 'error': getattr(error, 'code', str(error))})
    report['status'] = 'pass' if report['scenarios'] and all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    names = ['tools/engagement_native_boundary.py', 'tools/engagement_network_bridge.py', 'tools/engagement_network.py',
        'tools/target_accounts.py', 'tools/engagement_controller.py', 'tools/engagement_evidence.py', str(Path(__file__).relative_to(ROOT)),
        'evals/native-qualification/smoke/check_native_target_accounts_e2e.py']
    report['source_sha256'] = {name: digest((ROOT / name).read_bytes()) for name in names}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
