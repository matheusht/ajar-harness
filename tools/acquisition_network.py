"""Classify lab requests once; acquisition records exact, unmodified transfers."""
from __future__ import annotations

import copy
import hashlib
from urllib.parse import unquote, urlsplit
import uuid

from engagement_contract import canonical, digest, safe_publication, ContractError
from engagement_network import NetworkDenied, _forward_headers
from target_accounts import origin, _route_origin


class LabRequestBinder:
    def __init__(self, scope, environment_id, authorize, observe, target_accounts=None):
        self.scope = copy.deepcopy(scope)
        self.environment_id, self.authorize, self.observe = environment_id, authorize, observe
        self.target_accounts = target_accounts
        self.providers = {_route_origin(row) for row in scope['network']['provider']}
        self.targets = {_route_origin(row) for row in scope['network']['target']}
        self.acquisition = {_route_origin(row) for row in scope['network']['acquisition']}
        self.allowed = any(row['profile_id'] == environment_id and 'acquisition' in row['capabilities']
                           for row in scope['environments'])

    def secrets(self):
        if self.target_accounts is None:
            return ()
        with self.target_accounts.lock:
            return tuple(self.target_accounts.secrets)

    def bind(self, method, url, headers, *, request_length):
        self.authorize()
        destination = origin(url)
        if destination in self.providers:
            raise NetworkDenied('acquisition_provider_origin')
        if destination in self.targets:
            if self.target_accounts is None:
                raise NetworkDenied('target_account_origin_not_granted')
            return self.target_accounts.bind(method, url, headers, request_length=request_length)
        if not self.allowed or destination not in self.acquisition:
            raise NetworkDenied('acquisition_not_granted')
        if method not in ('GET', 'HEAD') or type(request_length) is not int or request_length != 0:
            raise NetworkDenied('acquisition_request_invalid')
        try:
            safe_publication(url.encode(), known_secrets=self.secrets())
            safe_publication(unquote(url).encode(), known_secrets=self.secrets())
        except ContractError:
            raise NetworkDenied('acquisition_credentials_forbidden') from None
        normalized = {}
        for name, value in headers.items():
            key = name.lower()
            if key in normalized:
                raise NetworkDenied('acquisition_header_duplicate')
            if key in ('authorization', 'proxy-authorization', 'cookie', 'x-oslit-access', 'x-oslit-account', 'x-oslit-effect'):
                raise NetworkDenied('acquisition_credentials_forbidden')
            normalized[key] = value
        try:
            safe_publication(canonical(normalized), known_secrets=self.secrets())
        except ContractError:
            raise NetworkDenied('acquisition_credentials_forbidden') from None
        normalized['accept-encoding'] = 'identity'
        parsed = urlsplit(url)
        path = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
        display = destination + (parsed.path or '/')
        try:
            safe_publication(display.encode(), known_secrets=self.secrets())
            safe_publication(unquote(display).encode(), known_secrets=self.secrets())
        except ContractError:
            display = None
        metadata = {'kind': 'acquisition-network-observation-v1', 'phase': 'intent',
            'operation_id': uuid.uuid4().hex, 'origin': destination, 'method': method,
            'path_sha256': digest(path.encode()), 'display_url': display}
        try:
            self.observe(metadata)
        except Exception:
            raise NetworkDenied('acquisition_observation_unavailable') from None
        return _AcquisitionBinding(self, normalized, metadata)


class _AcquisitionBinding:
    def __init__(self, binder, headers, metadata):
        self.binder, self.headers, self.metadata = binder, headers, metadata
        self.response_headers, self.response_bytes = [], 0
        self.hasher, self.carry = hashlib.sha256(), b''
        self.complete, self.finished = False, False
        self.body_kind = 'absent'

    def accept_response(self, response):
        absent = self.metadata['method'] == 'HEAD' or response.status in (204, 304) or 100 <= response.status < 200
        self.body_kind = 'absent' if absent else 'range' if response.status == 206 else 'whole'
        raw = response.getheaders()
        list(_forward_headers(raw))
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise NetworkDenied('acquisition_response_encoding_unavailable')
        self.complete = absent
        self.response_headers = [(name, value) for name, value in raw if name.lower() != 'set-cookie']
        for name, value in self.response_headers:
            if any(secret in (name + ': ' + value).encode('latin-1') for secret in self.binder.secrets()):
                raise NetworkDenied('acquisition_secret_reflection')

    def filter_chunk(self, chunk, *, final=False):
        self.response_bytes += len(chunk)
        self.hasher.update(chunk)
        data = self.carry + chunk
        secrets = self.binder.secrets()
        if any(secret in data for secret in secrets):
            self.carry = b''
            raise NetworkDenied('acquisition_secret_reflection')
        keep = 0 if final else max((len(secret) - 1 for secret in secrets), default=0)
        split = max(0, len(data) - keep)
        self.carry = data[split:]
        if final:
            self.complete = True
        return data[:split]

    def finish(self, status, http_status, request_bytes):
        if self.finished:
            return
        self.finished = True
        self.headers.clear(); self.carry = b''
        complete = self.complete and status == 'settled'
        observation = dict(self.metadata, phase='result', status=status, http_status=http_status,
            request_bytes=request_bytes, response_bytes=self.response_bytes, body_complete=complete,
            body_kind=self.body_kind, response_sha256='sha256:' + self.hasher.hexdigest()
                if complete and self.body_kind != 'absent' else None)
        try:
            self.binder.observe(observation)
        except Exception:
            raise NetworkDenied('acquisition_observation_unavailable') from None
