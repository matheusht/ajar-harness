#!/usr/bin/env python3
"""Failure-first E2E checks for the exact OMP model-discovery fixture route."""
from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import ssl
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_linux_model_native_e2e as native_e2e

# This fixture test is also runnable on hosts that bind only 127.0.0.1.
native_e2e.PROVIDER_HOST = '127.0.0.1'
PROVIDER_HOST = native_e2e.PROVIDER_HOST
Provider = native_e2e.Provider


def request(provider, context, path, authorization=None):
    connection = http.client.HTTPSConnection(PROVIDER_HOST, provider.server.server_port,
                                             context=context, timeout=5)
    headers = {'Authorization': authorization} if authorization is not None else {}
    connection.request('GET', path, headers=headers)
    response = connection.getresponse()
    status, body = response.status, response.read()
    connection.close()
    return status, body


def trust_context(ca):
    context = ssl.create_default_context(cafile=str(ca))
    # The local certificate fixture omits Authority Key Identifier. Keep normal
    # chain and hostname verification while allowing this legacy test CA shape.
    if hasattr(ssl, 'VERIFY_X509_STRICT'):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    secret = 'synthetic-discovery-key'
    result = {'kind': 'provider-discovery-fixture-e2e-v1',
        'classification': 'actual_local_owned_tls_provider', 'checks': [], 'failures': []}

    def check(name, condition, detail):
        result['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            result['failures'].append(name)

    with tempfile.TemporaryDirectory(prefix='provider-discovery-fixture-') as directory:
        provider = Provider(Path(directory) / 'tls', 'omp', secret)
        context = trust_context(provider.ca)
        try:
            status, body = request(provider, context, '/v1/models', 'Bearer ' + secret)
            try:
                document = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                document = None
            expected = {'object': 'list', 'data': [{'id': 'fixture-model', 'object': 'model',
                'created': 0, 'owned_by': 'fixture'}]}
            check('OMP authenticated model discovery returns the fixed fixture model list',
                status == 200 and document == expected and getattr(provider, 'discovery_requests', 0) == 1,
                {'status': status, 'body_matches_fixed_list': document == expected,
                 'discovery_requests': getattr(provider, 'discovery_requests', 0)})

            denied = [
                ('unknown path', '/v1/other', 'Bearer ' + secret),
                ('query string', '/v1/models?x=1', 'Bearer ' + secret),
                ('missing authorization', '/v1/models', None),
                ('wrong authorization', '/v1/models', 'Bearer wrong'),
            ]
            for label, path, authorization in denied:
                before = provider.escapes
                status, _body = request(provider, context, path, authorization)
                check(f'{label} discovery request is denied and counted as an escape',
                    status == 403 and provider.escapes == before + 1,
                    {'status': status, 'escape_delta': provider.escapes - before})

            codex = Provider(Path(directory) / 'codex-tls', 'codex', secret)
            codex_context = trust_context(codex.ca)
            status, _body = request(codex, codex_context, '/v1/models', 'Bearer ' + secret)
            check('Codex model discovery remains denied', status == 403 and codex.escapes == 1,
                  {'status': status, 'escapes': codex.escapes})
            check('discovery does not count as a provider POST', not provider.requests and not codex.requests,
                  {'omp_post_count': len(provider.requests), 'codex_post_count': len(codex.requests)})
        finally:
            provider.close()
            if 'codex' in locals():
                codex.close()

    result['status'] = 'passed' if not result['failures'] else 'failed'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']),
                      'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
