#!/usr/bin/env python3
"""Signed journal workflow for protected target-request attribution.

Python 3 and ssh-keygen; no external target/provider. Protected gate observations
are explicitly simulated. Run --output FILE; every scenario must pass.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).parent)]
from check_engagement_evidence_e2e import Case, fixture, require, refused
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller, Principal


def case(path):
    x = Case.__new__(Case)
    x.path, x.serial, x.workspaces = path, 0, {}
    x.inputs = fixture.make_fixture(path / 'input')
    scope = fixture.fixture_scope(x.inputs)
    scope['access'] = [{'id': name, 'kind': 'application',
        'identity': {'base_url': 'http://127.0.0.1:' + str(port), 'version': None},
        'account_refs': ['owner-a', 'owner-b'], 'permissions': ['read', 'write']}
        for name, port in [('app-main', 43199), ('app-other', 43200)]]
    scope['network']['target'] = [{'protocol': 'http', 'host': '127.0.0.1', 'port': port,
        'address_policy': {'public_only': False, 'cidrs': ['127.0.0.1/32']}} for port in (43199, 43200)]
    scope['effects'][0].update(access_ids=['app-main', 'app-other'], account_refs=['owner-a', 'owner-b'])
    scope['effects'].append(dict(scope['effects'][0], id='write-app', kind='write', cleanup_required=True))
    scope['effects'].append(dict(scope['effects'][0], id='read-anonymous', account_refs=[]))
    inputs = json.loads(x.inputs.read_text())
    inputs['access_files'] = {}
    fixture.write(x.inputs, canonical(inputs))
    fixture.resign_fixture(x.inputs, scope)
    x.contract = load_inputs(x.inputs)
    x.c = Controller.initialize(path / 'engagement', x.contract, evidence_class='engineering_simulation')
    x.lead = Principal('worker', 'lead-1', 1)
    x.start('lead-1')
    x.g = x.grant(resources=['app-main', 'app-other'])
    x.nonce = '4' * 32
    x.observe(x.g, 'environment-ready', x.nonce)
    return x


def observation(op='request-1', **changes):
    return dict({'kind': 'target-network-observation-v1', 'phase': 'intent',
        'operation_id': op, 'access_id': 'app-main', 'effect_id': 'read-source',
        'account_ref': 'owner-a', 'origin': 'http://127.0.0.1:43199', 'method': 'GET',
        'path_sha256': digest(b'/private')}, **changes)


def record(x, row, grant=None, nonce=None):
    return x.c.record_network_observation(grant or x.g, 'lab-main', nonce or x.nonce, row)


def result(row, **changes):
    return dict(row, phase='result', status=changes.get('status', 'settled'),
        http_status=200, request_bytes=0, response_bytes=7)


def attribution(x):
    for account in ('owner-a', 'owner-b', None):
        row = observation('request-' + (account or 'anonymous'), account_ref=account,
                          effect_id='read-source' if account else 'read-anonymous')
        record(x, row)
        record(x, row)
        record(x, result(row))
        record(x, result(row))
    state = Controller(x.c.root).state()
    require(len(state['network_operations']) == 3, 'account requests lost')
    require(all(len(row['receipts']) == 2 for row in state['network_operations'].values()), 'retry duplicated')
    x.c.export(x.path / 'export')
    exported = json.loads((x.path / 'export/result.json').read_text())
    require(len(exported['network_operations']) == 3, 'public attribution missing in export')


def scope_rejections(x):
    for change in ({'account_ref': 'outsider'}, {'access_id': 'app-other'},
                   {'origin': 'http://127.0.0.1:43200'}, {'effect_id': 'missing'}, {'method': 'POST'}):
        refused('network_effect_forbidden', lambda: record(x, observation(**change)))
    refused('network_environment_invalid', lambda: record(x, observation(), nonce='5' * 32))
    for change in ({'method': 'get'}, {'path_sha256': '/private?secret=x'}, {'headers': {}},
                   {'origin': 'http://127.0.0.1:43199/?token=x'}):
        refused('network_observation_invalid', lambda: record(x, observation(**change)))
    row = observation(method='POST', effect_id='write-app')
    record(x, row)
    record(x, result(row))
    require(len(x.c.state()['network_operations']) == 1, 'refused requests persisted')


def binding_and_revocation(x):
    row = observation()
    refused('network_intent_missing', lambda: record(x, result(row)))
    record(x, row)
    refused('network_operation_conflict', lambda: record(x, result(dict(row, account_ref='owner-b'))))
    refused('network_observation_invalid', lambda: record(x, dict(result(row), response_bytes=-1)))
    x.c.revoke_worker('lead-1', 1, reason='fixture')
    refused('worker_stale', lambda: record(x, observation('late-new')))
    record(x, result(row))
    require(x.c.state()['network_operations']['request-1']['result']['status'] == 'settled', 'late result lost')


def unknown_holds(x):
    row = observation()
    record(x, row)
    record(x, result(row, status='unknown'))
    x.settle(x.g)
    x.c.reconcile(x.g['dispatch_id'], {'app-main': 'unchanged', 'app-other': 'unchanged'}, adapter_id=x.g['adapter_id'])
    require(x.c.state()['resource_holds'] == {'app-main': [x.g['dispatch_id']]}, 'unknown attribution erased or broadened')
    record(x, result(row))
    require(not x.c.state()['resource_holds'], 'exact late result failed to release hold')
    require(len(x.c.state()['network_operations']['request-1']['receipts']) == 3, 'unknown overwritten')


def lost_result(x):
    record(x, observation())
    x.settle(x.g)
    require(x.c.state()['resource_holds'] == {'app-main': [x.g['dispatch_id']]}, 'missing result released target')


def anonymous_authority(x):
    refused('network_effect_forbidden', lambda: record(x, observation(account_ref=None)))


def cleaned_environment(x):
    row = observation()
    record(x, row)
    identity = x.c.state()['environments'][x.nonce]['identity']
    x.c.record_environment_cleanup(x.g, 'lab-main', {'status': 'clean', 'identity': identity,
                                                   'owned_workspace': 'container_removed'})
    refused('network_environment_invalid', lambda: record(x, observation('after-cleanup')))
    record(x, result(row))


def different_dispatch(x):
    x.settle(x.g)
    x.g = x.grant(resources=['app-main', 'app-other'])
    refused('network_environment_invalid', lambda: record(x, observation()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'classification': 'engineering_simulation', 'provider_calls': 0, 'scenarios': []}
    for check in (attribution, scope_rejections, binding_and_revocation, unknown_holds, lost_result,
                  anonymous_authority, cleaned_environment, different_dispatch):
        try:
            with tempfile.TemporaryDirectory(prefix='oslit-network-journal-') as folder:
                check(case(Path(folder).resolve()))
            report['scenarios'].append({'scenario': check.__name__, 'status': 'pass'})
        except Exception as error:
            report['scenarios'].append({'scenario': check.__name__, 'status': 'fail', 'error': str(error)})
    report['status'] = 'pass' if all(row['status'] == 'pass' for row in report['scenarios']) else 'fail'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
