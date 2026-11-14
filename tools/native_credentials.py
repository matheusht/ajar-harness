"""Private host credential binding. Secret values never become public adapter records."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from native_runtime_transport import RuntimeError

PROVIDER_ENV = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY',
                'opencode-go': 'OPENCODE_API_KEY', 'opencode-zen': 'OPENCODE_API_KEY'}


class CredentialBinding:
    __slots__ = ('_environment', '_tokens', '_reload', '_expires', '_revoked')

    def __init__(self, *, environment=None, tokens=None, reload=None, expires=None):
        self._environment = environment or {}
        self._tokens, self._reload, self._expires = tokens, reload, expires
        self._revoked = False

    def __repr__(self):return '<CredentialBinding private>'
    def __reduce__(self):raise TypeError('credential binding cannot be serialized')

    def check(self):
        if self._revoked:raise RuntimeError('native_credential_revoked')
        if self._expires is not None and self._expires <= time.time() + 30:
            raise RuntimeError('native_credential_expired')

    def environment(self):
        self.check()
        return dict(self._environment)

    def login(self):
        self.check()
        return {'type': 'chatgptAuthTokens', **self._tokens} if self._tokens else None

    def refresh(self, previous_account_id):
        if self._revoked:raise RuntimeError('native_credential_revoked')
        if self._reload is None or self._tokens is None:
            raise RuntimeError('native_credential_refresh_unavailable')
        account = self._tokens['chatgptAccountId']
        if previous_account_id not in (None, account):
            raise RuntimeError('native_credential_account_changed')
        tokens, expires = self._reload()
        if tokens['chatgptAccountId'] != account:
            raise RuntimeError('native_credential_account_changed')
        self._tokens, self._expires = tokens, expires
        return dict(tokens)

    def revoke(self):
        self._revoked = True
        self._environment.clear()
        self._tokens = self._reload = None


def _private_file(path):
    path = Path(path)
    try:
        info = path.lstat()
        if (not path.is_absolute() or path.resolve() != path or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 32 * 1024 * 1024):
            raise RuntimeError('native_credential_store_not_private')
        return path
    except OSError:
        raise RuntimeError('native_credential_unavailable') from None


def _secret(value):
    if not isinstance(value, str) or not value or len(value) > 32768 or any(c in value for c in '\r\n\x00'):
        raise RuntimeError('native_credential_unavailable')
    return value


class HostCredentialResolver:
    """Resolve explicit matching-provider references, without login or network refresh.

    Defaults read the existing native stores. Override paths only from trusted host
    configuration; worker messages cannot choose them. Expired native OAuth access
    requires the operator's existing native login flow to update its source store.
    """
    def __init__(self, *, environment=None, codex_auth_path=None, omp_db_path=None):
        self.environment = os.environ if environment is None else environment
        self.codex_auth_path = Path(codex_auth_path or Path.home() / '.codex/auth.json')
        self.omp_db_path = Path(omp_db_path or Path.home() / '.omp/agent/agent.db')

    def _codex_tokens(self):
        try:
            data = json.loads(_private_file(self.codex_auth_path).read_bytes())['tokens']
            access = _secret(data['access_token'])
            parts = access.split('.')
            if len(parts) != 3:raise ValueError()
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
            expires = claims['exp']
            if type(expires) is not int or expires <= time.time() + 30:
                raise RuntimeError('native_credential_expired')
            auth = claims.get('https://api.openai.com/auth', {})
            account = _secret(data.get('account_id') or auth.get('chatgpt_account_id'))
            if auth.get('chatgpt_account_id') not in (None, account):
                raise RuntimeError('native_credential_account_changed')
            plan = auth.get('chatgpt_plan_type')
            if plan is not None and (not isinstance(plan, str) or len(plan) > 64):raise ValueError()
            return {'accessToken': access, 'chatgptAccountId': account, 'chatgptPlanType': plan}, expires
        except (KeyError, TypeError, ValueError, OSError):
            raise RuntimeError('native_credential_unavailable') from None

    def __call__(self, profile):
        ref, provider, kind = (profile.get(k) for k in ('credential_ref', 'provider', 'kind'))
        if ref is None:return CredentialBinding()
        variable = PROVIDER_ENV.get(provider)
        if variable is None and kind == 'codex' and profile.get('config_file'):
            import re
            import tomllib
            from native_runtime_transport import pinned
            config = pinned(profile['config_file'], profile['config_sha256'], max_bytes=1048576)
            variable = tomllib.loads(config.read_text()).get('model_providers', {}).get(provider, {}).get('env_key')
            if variable is not None and not re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', str(variable)):
                raise RuntimeError('native_credential_provider_mismatch')
        if isinstance(ref, str) and ref.startswith('env_'):
            if variable is None or ref[4:] != variable:
                raise RuntimeError('native_credential_provider_mismatch')
            return CredentialBinding(environment={variable: _secret(self.environment.get(variable))})
        if ref == 'omp_default':
            if kind != 'omp' or variable is None:
                raise RuntimeError('native_credential_provider_mismatch')
            path = _private_file(self.omp_db_path)
            try:
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
                    rows = connection.execute('SELECT data FROM auth_credentials WHERE provider=? '
                        'AND credential_type=? AND disabled_cause IS NULL', (provider, 'api_key')).fetchall()
                if len(rows) != 1:raise RuntimeError('native_credential_unavailable')
                key = _secret(json.loads(rows[0][0])['key'])
            except (sqlite3.Error, ValueError, KeyError, TypeError):
                raise RuntimeError('native_credential_unavailable') from None
            return CredentialBinding(environment={variable: key})
        if ref == 'codex_default':
            if kind != 'codex' or provider != 'openai':
                raise RuntimeError('native_credential_provider_mismatch')
            tokens, expires = self._codex_tokens()
            return CredentialBinding(tokens=tokens, expires=expires, reload=self._codex_tokens)
        raise RuntimeError('native_credential_reference_unsupported')
