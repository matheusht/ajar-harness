"""Host-only target credentials selected by signed public account references."""
from __future__ import annotations

import copy
import hashlib
import http.cookiejar
from http.cookies import SimpleCookie
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit
from urllib.request import Request
import uuid

from engagement_contract import read_json
from engagement_network import NetworkDenied, _HOP_HEADERS, _forward_headers


class TargetAccountError(NetworkDenied):
    pass


def _deny(code):
    raise TargetAccountError(code)


def origin(value):
    if type(value) is not str:
        _deny('target_origin_invalid')
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            _deny('target_origin_invalid')
        host = '[' + parsed.hostname.lower() + ']' if ':' in parsed.hostname else parsed.hostname.lower()
        return parsed.scheme + '://' + host + ':' + str(parsed.port or (443 if parsed.scheme == 'https' else 80))
    except (TypeError, ValueError):
        _deny('target_origin_invalid')


def _route_origin(route):
    host = '[' + route['host'] + ']' if ':' in route['host'] else route['host']
    return origin(route['protocol'] + '://' + host + ':' + str(route['port']))


class TargetAccountResolver:
    def __init__(self, private_reference_file, scope, grant_authorize, observe_callback, *, environment_profile_id):
        self.scope = copy.deepcopy(scope)
        self.authorize = grant_authorize
        self.observe = observe_callback
        self.environment_id = environment_profile_id
        self.lock = threading.RLock()
        self.closed = False
        self.accounts = {}
        self.secrets = set()
        self.accesses = {row['id']: row for row in self.scope['access'] if row['kind'] == 'application'}
        self.origins = {key: origin(row['identity']['base_url']) for key, row in self.accesses.items()}
        self.providers = {_route_origin(row) for row in self.scope['network']['provider']}
        grant = self.authorize()
        required = {(key, account) for key, row in self.accesses.items() if key in grant['resources']
                    for account in row['account_refs']}
        if private_reference_file is None:
            document = {'kind': 'target-account-bindings-v1', 'bindings': []}
        else:
            try:
                document = read_json(Path(private_reference_file), private=True, max_bytes=256 * 1024)
            except Exception:
                _deny('target_account_references_unavailable')
        if (type(document) is not dict or set(document) != {'kind', 'bindings'} or
                document['kind'] != 'target-account-bindings-v1' or type(document['bindings']) is not list or
                len(document['bindings']) > 256):
            _deny('target_account_references_invalid')
        seen = set()
        for row in document['bindings']:
            if type(row) is not dict or set(row) != {'access_id', 'account_ref', 'origin', 'headers'}:
                _deny('target_account_binding_invalid')
            pair = row['access_id'], row['account_ref']
            if any(type(value) is not str for value in pair):
                _deny('target_account_binding_invalid')
            access = self.accesses.get(pair[0])
            if (pair in seen or access is None or pair[1] not in access['account_refs'] or
                    origin(row['origin']) != self.origins[pair[0]] or self.origins[pair[0]] in self.providers or
                    urlsplit(row['origin']).path not in ('', '/') or urlsplit(row['origin']).query):
                _deny('target_account_binding_invalid')
            seen.add(pair)
            configured = row['headers']
            if type(configured) is not dict or not 1 <= len(configured) <= 16:
                _deny('target_account_headers_invalid')
            references = {}
            for name, reference in configured.items():
                if (type(name) is not str or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or name.lower() in references or
                        name.lower() in _HOP_HEADERS | {'host', 'content-length', 'accept-encoding', 'expect',
                                                        'x-oslit-access', 'x-oslit-account', 'x-oslit-effect'} or
                        type(reference) is not str or not re.fullmatch(r'env_[A-Za-z_][A-Za-z0-9_]*', reference)):
                    _deny('target_account_headers_invalid')
                references[name.lower()] = reference[4:]
            if pair not in required:
                continue
            headers = {}
            jar = http.cookiejar.CookieJar()
            for name, variable in references.items():
                value = os.environ.get(variable)
                if (not value or len(value) > 8192 or any(ord(char) < 32 or ord(char) > 126 for char in value)):
                    _deny('target_account_credential_unavailable')
                self._remember([value])
                if name == 'authorization' and ' ' in value:
                    self._remember([value.split(' ', 1)[1].strip()])
                if name == 'cookie':
                    cookies = SimpleCookie()
                    try:
                        cookies.load(value)
                    except Exception:
                        _deny('target_account_cookie_invalid')
                    if not cookies:
                        _deny('target_account_cookie_invalid')
                    parsed = urlsplit(self.origins[pair[0]])
                    for cookie in cookies.values():
                        self._remember([cookie.value])
                        jar.set_cookie(http.cookiejar.Cookie(0, cookie.key, cookie.value, None, False,
                            parsed.hostname, False, False, '/', True, parsed.scheme == 'https', None, True,
                            None, None, {}, False))
                else:
                    headers[name] = value
            self.accounts[pair] = {'headers': headers, 'jar': jar, 'protected_headers': set(references)}
        if required - set(self.accounts):
            _deny('target_account_binding_unavailable')

    def _remember(self, values):
        additions = set()
        for value in values:
            if value:
                additions.add(value.encode('utf-8'))
                try:
                    additions.add(value.encode('latin-1'))
                except UnicodeEncodeError:
                    _deny('target_account_secret_encoding')
        combined = self.secrets | additions
        if len(combined) > 4096 or sum(map(len, combined)) > 1024 * 1024:
            _deny('target_account_secret_capacity')
        self.secrets = combined

    def bind(self, method, url, headers):
        with self.lock:
            if self.closed:
                _deny('target_account_binding_closed')
            grant = self.authorize()
            destination = origin(url)
            normalized = {}
            for name, value in headers.items():
                if name.lower() in normalized:
                    _deny('target_account_header_duplicate')
                normalized[name.lower()] = value
            access_id = normalized.pop('x-oslit-access', None)
            account_ref = normalized.pop('x-oslit-account', None)
            effect_id = normalized.pop('x-oslit-effect', None)
            matching = [key for key, value in self.origins.items() if value == destination]
            if destination in self.providers:
                _deny('target_account_provider_origin')
            if not matching:
                if access_id is not None or account_ref is not None or effect_id is not None:
                    _deny('target_account_origin_not_granted')
                return None
            if account_ref is not None and access_id is None:
                _deny('target_account_access_required')
            if access_id is None:
                available = [key for key in matching if key in grant['resources']]
                if len(available) != 1:
                    _deny('target_account_access_ambiguous')
                access_id = available[0]
            if access_id not in matching or access_id not in grant['resources']:
                _deny('target_account_access_not_granted')
            access = self.accesses[access_id]
            if account_ref is not None and account_ref not in access['account_refs']:
                _deny('target_account_not_granted')
            kind = 'read' if method in ('GET', 'HEAD', 'OPTIONS') else 'write'
            effects = [row for row in self.scope['effects'] if row['kind'] == kind and
                access_id in row['access_ids'] and self.environment_id in row['environment_ids'] and
                ((not row['account_refs']) if account_ref is None else account_ref in row['account_refs'])]
            if kind not in access['permissions'] or not effects:
                _deny('target_account_effect_not_granted')
            if effect_id is not None:
                effects = [row for row in effects if row['id'] == effect_id]
            if not effects:
                _deny('target_account_effect_not_granted')
            if len(effects) != 1:
                _deny('target_account_effect_ambiguous')
            protected = {'authorization', 'cookie'}
            for pair, account in self.accounts.items():
                if self.origins[pair[0]] == destination:
                    protected |= account['protected_headers']
            if protected & set(normalized):
                _deny('target_account_auth_override')
            account = None if account_ref is None else self.accounts.get((access_id, account_ref))
            if account_ref is not None and account is None:
                _deny('target_account_binding_unavailable')
            if account is not None:
                normalized.update(account['headers'])
                request = Request(url)
                account['jar'].add_cookie_header(request)
                if request.has_header('Cookie'):
                    normalized['cookie'] = request.get_header('Cookie')
                    self._remember([normalized['cookie']])
            normalized['accept-encoding'] = 'identity'
            parsed = urlsplit(url)
            path = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
            metadata = {'kind': 'target-network-observation-v1', 'operation_id': uuid.uuid4().hex,
                'access_id': access_id, 'account_ref': account_ref, 'effect_id': effects[0]['id'],
                'origin': destination, 'method': method, 'path_sha256': 'sha256:' + hashlib.sha256(path.encode()).hexdigest()}
            try:
                self.observe(dict(metadata, phase='intent'))
            except Exception:
                _deny('target_network_observation_unavailable')
            return _RequestBinding(self, url, normalized, account, metadata)

    def close(self):
        with self.lock:
            self.closed = True
            for account in self.accounts.values():
                account['headers'].clear()
                account['jar'].clear()
            self.accounts.clear()
            self.secrets.clear()


class _RequestBinding:
    def __init__(self, resolver, url, headers, account, metadata):
        self.resolver, self.url, self.headers = resolver, url, headers
        self.account, self.metadata = account, metadata
        self.response_headers = []
        self.carry = b''
        self.response_bytes = 0
        self.finished = False

    def accept_response(self, response):
        with self.resolver.lock:
            if self.resolver.closed:
                _deny('target_account_binding_closed')
            raw = response.getheaders()
            list(_forward_headers(raw))
            if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                _deny('target_account_response_encoding_unavailable')
            jar = http.cookiejar.CookieJar()
            if self.account is not None:
                for cookie in self.account['jar']:
                    jar.set_cookie(copy.deepcopy(cookie))
            jar.extract_cookies(response, Request(self.url))
            if len(jar) > 128:
                _deny('target_account_cookie_capacity')
            self.resolver._remember([cookie.value for cookie in jar])
            self.response_headers = [(key, value) for key, value in raw if key.lower() != 'set-cookie']
            for name, value in self.response_headers:
                encoded = (name + ': ' + value).encode('latin-1')
                if any(secret in encoded for secret in self.resolver.secrets):
                    _deny('target_account_secret_reflection')
            if self.account is not None:
                self.account['jar'] = jar

    def filter_chunk(self, chunk, *, final=False):
        with self.resolver.lock:
            if self.resolver.closed:
                _deny('target_account_binding_closed')
            self.response_bytes += len(chunk)
            data = self.carry + chunk
            if any(secret in data for secret in self.resolver.secrets):
                self.carry = b''
                _deny('target_account_secret_reflection')
            keep = 0 if final else max((len(secret) - 1 for secret in self.resolver.secrets), default=0)
            split = max(0, len(data) - keep)
            self.carry = data[split:]
            return data[:split]

    def finish(self, status, http_status, request_bytes):
        if self.finished:
            return
        self.finished = True
        self.headers.clear()
        self.carry = b''
        try:
            self.resolver.observe(dict(self.metadata, phase='result', status=status, http_status=http_status,
                request_bytes=request_bytes, response_bytes=self.response_bytes))
        except Exception:
            _deny('target_network_observation_unavailable')
