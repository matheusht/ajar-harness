#!/usr/bin/env python3
"""Owned local HTTP requests through the target-account binding and network gate.

No provider, external target, Docker or SSH is contacted. Scope/grant inputs are
explicit engineering fixtures; the receiver, proxy, redirects and byte streams
are real. Controller journal integration is checked by its separate workflow.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import copy
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'kind': 'target-accounts-e2e-v1', 'classification': 'actual_local_http_with_scoped_grant_fixtures',
        'provider_calls': 0, 'external_target_calls': 0, 'checks': [],
        'unverified': ['controller journal integration', 'Docker isolation', 'SSH', 'actual target user identity']}

    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    servers, gates, resolvers = [], [], []
    previous = {}
    try:
        from target_accounts import TargetAccountResolver
        from engagement_network import NetworkGate
        secrets = {'alpha': 'fixture-alpha-' + uuid.uuid4().hex, 'beta': 'fixture-beta-' + uuid.uuid4().hex}
        cookies = {name: 'fixture-session-' + uuid.uuid4().hex for name in secrets}
        anonymous_cookie = 'fixture-anonymous-' + uuid.uuid4().hex
        latin_cookie = 'fixture-latin1-' + chr(255) + '-' + uuid.uuid4().hex
        cookie_round = [0]
        for name, secret in secrets.items():
            key = 'OSLIT_FIXTURE_' + name.upper()
            previous[key] = os.environ.get(key)
            os.environ[key] = 'Bearer ' + secret
        hits, observations = [], []
        response_started, release_response = threading.Event(), threading.Event()
        completed = threading.Condition()

        class Receiver(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.do_GET()

            def do_GET(self):
                auth = self.headers.get('Authorization')
                account = next((name for name, secret in secrets.items() if auth == 'Bearer ' + secret), None)
                if account is None:
                    account = next((name for name, value in cookies.items() if self.headers.get('Cookie') == 'session=' + value), None)
                hits.append({'port': self.server.server_port, 'path': self.path, 'account': account,
                    'cookie': self.headers.get('Cookie'), 'selectors': [self.headers.get('X-OSLit-Access'), self.headers.get('X-OSLit-Account')]})
                try:
                    if self.path == '/cross':
                        self.send_response(302); self.send_header('Location', second_url + '/identity')
                        self.send_header('Content-Length', '0'); self.end_headers(); return
                    if self.path == '/reflect-header-name':
                        self.send_response(200); self.send_header((auth or 'anonymous').split(' ', 1)[-1], 'harmless')
                        self.send_header('Content-Length', '0'); self.end_headers(); return
                    if self.path == '/reflect-header':
                        self.send_response(200); self.send_header('X-Reflection', auth or 'anonymous')
                        self.send_header('Content-Length', '0'); self.end_headers(); return
                    if self.path == '/latin-cookie-reflection':
                        body = latin_cookie.encode('latin-1')
                    elif self.path == '/anon-cookie-reflection':
                        body = anonymous_cookie.encode()
                    elif self.path == '/reflect-cookie':
                        body = (self.headers.get('Cookie') or 'anonymous').encode()
                    elif self.path in ('/reflect', '/split'):
                        body = (b'.' * 16380 if self.path == '/split' else b'') + (auth or 'anonymous').encode() + b' tail'
                    elif self.path == '/revoke':
                        self.send_response(200); self.send_header('Transfer-Encoding', 'chunked'); self.end_headers()
                        first = b'harmless first chunk' * 1024
                        self.wfile.write(f'{len(first):x}\r\n'.encode() + first + b'\r\n'); self.wfile.flush()
                        response_started.set(); release_response.wait(3)
                        self.wfile.write(b'4\r\nlate\r\n0\r\n\r\n'); return
                    else:
                        body = (account or 'anonymous').encode()
                    self.send_response(200)
                    if self.path == '/latin-cookie':
                        self.send_header('Set-Cookie', 'latin=' + latin_cookie + '; Path=/; HttpOnly')
                    if self.path == '/many-cookies':
                        cookie_round[0] += 1
                        for number in range(80):
                            self.send_header('Set-Cookie', f'cookie{cookie_round[0]}_{number}=fixture-value-{cookie_round[0]}-{number}; Path=/')
                    if self.path == '/anon-cookie-reflection':
                        self.send_header('Set-Cookie', 'session=' + anonymous_cookie + '; Path=/; HttpOnly')
                    if self.path == '/cookie' and account:
                        self.send_header('Set-Cookie', 'session=' + cookies[account] + '; Path=/; HttpOnly')
                    self.send_header('Content-Length', str(len(body))); self.end_headers()
                    if self.path == '/split':
                        self.wfile.write(body[:16384]); self.wfile.flush(); time.sleep(.03); self.wfile.write(body[16384:])
                    else:
                        self.wfile.write(body)
                except (OSError, ConnectionError):
                    pass

            def log_message(self, *_):
                pass

        for _ in range(3):
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
        first_url, second_url, provider_url = ['http://127.0.0.1:' + str(server.server_port) for server in servers]
        def route(server):
            return {'protocol': 'http', 'host': '127.0.0.1', 'port': server.server_port,
                'address_policy': {'public_only': False, 'cidrs': ['127.0.0.0/8']}}
        accesses = [{'id': name, 'kind': 'application', 'identity': {'base_url': url + '/', 'version': None},
            'account_refs': ['alpha', 'beta'] if name == 'app-main' else ['alpha'], 'permissions': ['read', 'write']}
            for name, url in [('app-main', first_url), ('app-other', second_url)]]
        effects = [{'id': 'read-' + access['id'], 'kind': 'read', 'access_ids': [access['id']],
            'environment_ids': ['lab-main'], 'account_refs': [], 'rung': 'self', 'artifact_classes': [], 'cleanup_required': False}
            for access in accesses]
        for access in accesses:
            for account in access['account_refs']:
                effects.append(dict(effects[0], id='read-' + access['id'] + '-' + account,
                    access_ids=[access['id']], account_refs=[account]))
        effects.append(dict(effects[0], id='write-alpha', kind='write', account_refs=['alpha'], cleanup_required=True))
        scope = {'access': accesses, 'effects': effects,
            'network': {'target': [route(server) for server in servers[:2]], 'provider': [route(servers[2])], 'acquisition': []}}
        grant = {'resources': ['app-main', 'app-other'], 'worker_id': 'worker-1', 'generation': 1, 'dispatch_id': 'dispatch-1'}
        active = [True]
        def authorize():
            if not active[0]:
                raise ValueError('fixture-authority-revoked')
            return copy.deepcopy(grant)
        def observe(value):
            with completed:
                observations.append(copy.deepcopy(value))
                completed.notify_all()
        def selected(account, access='app-main'):
            return {'X-OSLit-Access': access, 'X-OSLit-Account': account}
        with tempfile.TemporaryDirectory(prefix='oslit-accounts-') as temporary:
            folder = Path(temporary).resolve()
            config = folder / 'account-references.json'
            config_doc = {'kind': 'target-account-bindings-v1', 'bindings': [
                {'access_id': access['id'], 'account_ref': account, 'origin': access['identity']['base_url'].rstrip('/'),
                 'headers': {'Authorization': 'env_OSLIT_FIXTURE_' + account.upper()}}
                for access in accesses for account in access['account_refs']]}
            config.write_text(json.dumps(config_doc)); config.chmod(0o600)
            resolver = TargetAccountResolver(config, scope, authorize, observe, environment_profile_id='lab-main')
            resolvers.append(resolver)
            gate = NetworkGate([route(server) for server in servers], lambda: active[0],
                dispatch_guard=lambda: nullcontext(), request_binder=resolver.bind)
            gates.append(gate)
            port = gate.serve_tcp()
            def request(path, headers=None, method='GET', base=first_url):
                before = len(observations)
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    connection.request(method, base + path, body=b'' if method != 'GET' else None, headers=headers or {})
                    response = connection.getresponse(); response_headers = response.getheaders()
                    try:
                        body = response.read()
                    except http.client.IncompleteRead as error:
                        body = error.partial
                    return response.status, response_headers, body
                finally:
                    connection.close()
                    with completed:
                        operations = {row['operation_id'] for row in observations[before:] if row['phase'] == 'intent'}
                        if operations and not completed.wait_for(lambda: operations <= {row['operation_id']
                                for row in observations[before:] if row['phase'] == 'result'}, timeout=3):
                            raise AssertionError('request result observation missing')
            for account in ('alpha', 'beta'):
                status, headers, body = request('/identity', selected(account))
                check('selected-' + account, status == 200 and body == account.encode())
            status, _, body = request('/identity')
            check('anonymous-has-no-default-account', status == 200 and body == b'anonymous' and hits[-1]['cookie'] is None)
            check('selector-headers-never-reach-target', all(row['selectors'] == [None, None] for row in hits))
            for name, headers, method, base in [
                ('wrong-account', selected('outside'), 'GET', first_url),
                ('wrong-access', selected('alpha', 'outside'), 'GET', first_url),
                ('wrong-origin', selected('alpha'), 'GET', second_url),
                ('provider-origin', selected('alpha'), 'GET', provider_url),
                ('auth-override', dict(selected('alpha'), Authorization='asserted-user'), 'GET', first_url),
                ('anonymous-cookie-override', {'Cookie': 'asserted=session'}, 'GET', first_url),
                ('account-without-access', {'X-OSLit-Account': 'alpha'}, 'GET', first_url),
                ('write-without-effect', selected('beta'), 'POST', first_url)]:
                before = len(hits); status, _, _ = request('/identity', headers, method, base)
                check(name + '-before-effect', status == 403 and len(hits) == before)
            status, _, body = request('/identity', selected('alpha'), 'POST')
            check('signed-write-account', status == 200 and body == b'alpha' and observations[-1]['effect_id'] == 'write-alpha')
            grant['resources'] = ['app-other']; before = len(hits)
            status, _, _ = request('/identity', selected('alpha'))
            check('current-resource-grant-required', status == 403 and len(hits) == before)
            grant['resources'] = ['app-main', 'app-other']
            for account in ('alpha', 'beta'):
                status, headers, _ = request('/cookie', selected(account))
                check('private-cookie-response-' + account, status == 200 and not any(key.lower() == 'set-cookie' for key, _ in headers))
                request('/identity', selected(account))
                check('account-cookie-rotation-' + account, hits[-1]['cookie'] == 'session=' + cookies[account])
            request('/identity', selected('alpha', 'app-other'), base=second_url)
            check('same-account-other-origin-cookie-isolation', hits[-1]['cookie'] is None)
            cross = gate.fetch(first_url + '/cross', headers=selected('alpha'))
            check('cross-origin-redirect-has-no-account', cross['body'] == b'anonymous' and hits[-1]['port'] == servers[1].server_port and hits[-1]['cookie'] is None)
            for path in ('/reflect', '/split', '/reflect-cookie', '/reflect-header', '/reflect-header-name'):
                before = len(observations); status, headers, body = request(path, selected('alpha'))
                exposed = json.dumps(headers).encode() + body
                check(path[1:] + '-secret-withheld', all(value.encode() not in exposed for value in [*secrets.values(), *cookies.values()]))
                events = observations[before:]
                check(path[1:] + '-outcome-unknown', len(events) == 2 and events[-1]['status'] == 'unknown')
            before = len(observations)
            status, headers, body = request('/anon-cookie-reflection')
            check('anonymous-issued-cookie-withheld', anonymous_cookie.encode() not in body and
                not any(key.lower() == 'set-cookie' for key, _ in headers) and observations[-1]['status'] == 'unknown')
            status, headers, _ = request('/latin-cookie', selected('alpha'))
            check('latin1-issued-cookie-stays-private', status == 200 and not any(key.lower() == 'set-cookie' for key, _ in headers))
            status, headers, body = request('/latin-cookie-reflection', selected('alpha'))
            check('latin1-cookie-reflection-withheld', latin_cookie.encode('latin-1') not in body and observations[-1]['status'] == 'unknown')
            request('/many-cookies', selected('alpha'))
            accepted_count = len(resolver.accounts[('app-main', 'alpha')]['jar'])
            check('bounded-cookie-update-accepted', 80 <= accepted_count <= 128)
            for attempt in range(2):
                status, _, _ = request('/many-cookies', selected('alpha'))
                check('rejected-cookie-update-is-atomic-' + str(attempt), status == 403 and
                    len(resolver.accounts[('app-main', 'alpha')]['jar']) == accepted_count and observations[-1]['status'] == 'unknown')
            before = len(observations); request('/identity?private=query-value', selected('beta'))
            intent, outcome = observations[before:]
            check('exact-request-provenance', intent['access_id'] == 'app-main' and intent['account_ref'] == 'beta' and
                intent['effect_id'] == 'read-app-main-beta' and intent['origin'] == first_url and intent['method'] == 'GET' and
                intent['path_sha256'] == 'sha256:' + hashlib.sha256(b'/identity?private=query-value').hexdigest() and
                outcome['operation_id'] == intent['operation_id'] and outcome['status'] == 'settled' and outcome['http_status'] == 200 and
                outcome['response_bytes'] == 4)
            check('query-never-recorded', 'query-value' not in json.dumps(observations))
            check('secrets-never-in-observations', all(value not in json.dumps(observations) for value in [*secrets.values(), *cookies.values()]))
            failing = TargetAccountResolver(config, scope, authorize,
                lambda value: (_ for _ in ()).throw(ValueError('fixture-observer-unavailable')), environment_profile_id='lab-main')
            resolvers.append(failing)
            failed_gate = NetworkGate([route(servers[0])], lambda: active[0], dispatch_guard=lambda: nullcontext(), request_binder=failing.bind)
            gates.append(failed_gate); before = len(hits)
            try:
                failed_gate.fetch(first_url + '/identity', headers=selected('alpha')); refused = False
            except Exception:
                refused = True
            check('observer-failure-before-connect', refused and len(hits) == before)
            seeded = copy.deepcopy(config_doc)
            seed_key = 'OSLIT_FIXTURE_SEED_COOKIE'
            previous[seed_key] = os.environ.get(seed_key)
            os.environ[seed_key] = 'session=' + cookies['alpha']
            seeded['bindings'][0]['headers'] = {'Cookie': 'env_' + seed_key}
            seed_path = folder / 'cookie-references.json'; seed_path.write_text(json.dumps(seeded)); seed_path.chmod(0o600)
            cookie_resolver = TargetAccountResolver(seed_path, scope, authorize, observe, environment_profile_id='lab-main')
            resolvers.append(cookie_resolver)
            cookie_gate = NetworkGate([route(servers[0])], lambda: active[0], dispatch_guard=lambda: nullcontext(), request_binder=cookie_resolver.bind)
            gates.append(cookie_gate)
            seeded_result = cookie_gate.fetch(first_url + '/identity', headers=selected('alpha'))
            check('existing-cookie-reference-authenticates', seeded_result['body'] == b'alpha' and hits[-1]['cookie'] == 'session=' + cookies['alpha'])
            invalid = copy.deepcopy(config_doc); invalid['bindings'][0]['origin'] = provider_url
            bad = folder / 'bad-references.json'; bad.write_text(json.dumps(invalid)); bad.chmod(0o600)
            try:
                TargetAccountResolver(bad, scope, authorize, observe, environment_profile_id='lab-main'); refused = False
            except Exception:
                refused = True
            check('binding-cannot-expand-origin', refused)
            invalid = copy.deepcopy(config_doc); invalid['bindings'][0]['headers'] = {'Upgrade': 'env_OSLIT_FIXTURE_ALPHA'}
            bad.write_text(json.dumps(invalid))
            try:
                TargetAccountResolver(bad, scope, authorize, observe, environment_profile_id='lab-main'); refused = False
            except Exception:
                refused = True
            check('binding-cannot-inject-hop-header', refused)
            config.chmod(0o644)
            try:
                TargetAccountResolver(config, scope, authorize, observe, environment_profile_id='lab-main'); refused = False
            except Exception:
                refused = True
            check('private-reference-file-required', refused)
            config.chmod(0o600)
            missing = os.environ.pop('OSLIT_FIXTURE_BETA')
            try:
                try:
                    TargetAccountResolver(config, scope, authorize, observe, environment_profile_id='lab-main'); refused = False
                except Exception:
                    refused = True
                check('missing-credential-refused', refused)
            finally:
                os.environ['OSLIT_FIXTURE_BETA'] = missing
            before = len(observations)
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            connection.request('GET', first_url + '/revoke', headers=selected('alpha'))
            response = connection.getresponse()
            check('stream-started-before-revocation', response_started.wait(2) and response.read(64))
            active[0] = False; release_response.set()
            try:
                response.read()
            except (OSError, http.client.HTTPException):
                pass
            connection.close()
            for _ in range(100):
                if observations[before:] and observations[-1].get('phase') == 'result':
                    break
                time.sleep(.01)
            check('revocation-preserves-unknown-outcome', observations[-1].get('phase') == 'result' and observations[-1].get('status') == 'unknown')
            resolver.close(); resolver.close()
            check('close-is-idempotent', True)
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        for gate in gates:
            gate.close()
        for resolver in resolvers:
            resolver.close()
        for server in servers:
            server.shutdown(); server.server_close()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    result['passed'] = bool(result['checks']) and all(row['passed'] for row in result['checks']) and 'error' not in result
    result['source_sha256'] = {str(path.relative_to(ROOT)): 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [ROOT / 'tools/target_accounts.py', ROOT / 'tools/engagement_network.py', Path(__file__).resolve()] if path.is_file()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
