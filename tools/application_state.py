"""Optional, host-owned application instances; the controller owns their journal."""
from __future__ import annotations

import copy
import re
import threading
from urllib.parse import urlsplit

from engagement_contract import canonical, digest, safe_publication
from engagement_network_bridge import SocketBridge
from research_environment import Environment


class ApplicationStateError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_profile(profile):
    code = 'application_state_profile_invalid'
    version = 2 if isinstance(profile, dict) and profile.get('kind') == 'owned-application-state-v2' else 1
    expected = {'kind', 'method', 'baseline_id', 'command', 'service_port'} | ({'state_volumes'} if version == 2 else set())
    if (type(profile) is not dict or set(profile) != expected
            or profile['kind'] != f'owned-application-state-v{version}'
            or profile['method'] != f'owned-container-recreate-v{version}'
            or type(profile['baseline_id']) is not str
            or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', profile['baseline_id'])
            or type(profile['service_port']) is not int or not 1 <= profile['service_port'] <= 65535
            or type(profile['command']) is not list or not 1 <= len(profile['command']) <= 256
            or any(type(value) is not str or not value or '\0' in value for value in profile['command'])
            or not profile['command'][0].startswith('/')):
        raise ApplicationStateError(code)
    if version == 2:
        from application_volumes import validate
        from research_environment import EnvironmentUnavailable
        try:
            validate(profile['state_volumes'])
        except EnvironmentUnavailable:
            raise ApplicationStateError(code) from None
    safe_publication(canonical(profile))
    return profile


def owned_origin(access, profile):
    try:
        url = urlsplit(access['identity']['base_url'])
        if (access['kind'] != 'application' or 'reset' not in access['permissions']
                or url.scheme != 'http' or not url.hostname or not url.hostname.endswith('.invalid')
                or url.username is not None or url.password is not None or url.path not in ('', '/')
                or url.query or url.fragment or (url.port or 80) != profile['service_port']
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.invalid', url.hostname)):
            raise ValueError()
        return f'http://{url.hostname}:{url.port or 80}'
    except (KeyError, TypeError, ValueError):
        raise ApplicationStateError('application_owned_origin_required') from None


class ApplicationOwner:
    def __init__(self, profile, access, environment_profile, limits, authorize, observe, *,
                 grant, dispatch_guard, bootstrap, known_hosts_file=None, lab_artifact=False, on_ready=None):
        self.profile = copy.deepcopy(validate_profile(profile))
        self.origin = owned_origin(access, self.profile)
        self.access_id = access['id']
        self.access = copy.deepcopy(access)
        self.authorize, self.guard = authorize, dispatch_guard
        self.bootstrap = copy.deepcopy(bootstrap)
        if bool(lab_artifact) != callable(on_ready):
            raise ApplicationStateError('application_artifact_observer_required')
        self.on_ready = on_ready
        self.environment = Environment(environment_profile, limits, authorize, observe, grant=grant,
            dispatch_guard=dispatch_guard, known_hosts_file=known_hosts_file,
            state_volumes=profile.get('state_volumes'), lab_artifact=lab_artifact)
        self.application = self.bridge = self.start_receipt = None
        self.started = False

    def reset(self, baseline_id):
        if baseline_id != self.profile['baseline_id']:
            raise ApplicationStateError('application_baseline_not_granted')
        if self.started:
            raise ApplicationStateError('application_generation_already_used')
        with self.guard():
            self.authorize()
            self.started = True
        self.environment.prepare([self.access], {}, support_inputs=self.bootstrap)
        if self.on_ready is not None:
            self.on_ready(self.environment.artifact_state_readback())
        self.application = self.environment.launch_stdio(self.profile['command'], role='application')
        # Output is never a readiness or reset assertion and must not block startup.
        def discard_output():
            try:
                while self.application.stdout.read(65536):
                    pass
            except (OSError, ValueError):
                pass
        threading.Thread(target=discard_output, daemon=True).start()
        self.bridge = SocketBridge(
            lambda command: self.environment.launch_stdio(command, role='application_connector'),
            ['python3', '-I', '-S', '/input/application-connector/bridge.py', 'connect', str(self.profile['service_port'])],
            self._active, dispatch_guard=self.guard, port=self.profile['service_port'])
        observed = self.environment.readback()
        if observed['status'] != 'running' or not self._active():
            raise ApplicationStateError('application_start_unobserved')
        identity = observed['identity']
        self.start_receipt = {'kind': 'application-start-v1', 'access_id': self.access_id,
            'baseline_id': self.profile['baseline_id'], 'profile_sha256': digest(canonical(self.profile)),
            'origin': self.origin, 'target_nonce': identity['nonce'], 'container_id': identity['container_id'],
            'daemon_id': identity['daemon_id'], 'environment_profile_sha256': identity['profile_sha256'], 'image_id': identity['image_id']}
        return copy.deepcopy(self.start_receipt)

    def _active(self):
        try:
            self.authorize()
            return self.application is not None and self.application.poll() is None
        except Exception:
            return False

    def connect(self, exact_origin):
        with self.guard():
            if exact_origin != self.origin or self.start_receipt is None or not self._active():
                raise ApplicationStateError('application_connection_not_granted')
            observed = self.environment.readback()
            if (observed['status'] != 'running'
                    or observed['identity']['nonce'] != self.start_receipt['target_nonce']
                    or observed['identity']['container_id'] != self.start_receipt['container_id']):
                raise ApplicationStateError('application_owner_changed')
            return self.bridge.connect()

    def renew(self, seconds=None):
        return self.environment.renew(seconds)

    def cleanup(self):
        connector_failure = None
        if self.bridge is not None:
            try:
                self.bridge.close()
            except Exception as error:
                connector_failure = error
        cleanup = self.environment.cleanup()
        if connector_failure is not None:
            error = ApplicationStateError('application_connector_cleanup_unresolved')
            error.cleanup_result = cleanup
            raise error from connector_failure
        return cleanup
