"""Small isolated checks for native helper identity, accounting and revocation."""
from __future__ import annotations

from contextlib import contextmanager
import sys
import time
import uuid

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from native_runtime_helpers import HelperSessions
from native_runtime_transport import RuntimeError


class FakeController:
    def __init__(self):
        self.data = {'scope': {'limits': {'max_workers': 3}},
                     'workers': {'parent-worker': {'generation': 1}}, 'helpers': {}}
        self.events = []

    def state(self):
        return self.data

    def record_helper(self, grant, helper_id, event, data):
        self.events.append((helper_id, event, data))
        row = self.data['helpers'].setdefault(helper_id, {'usage': {'input_tokens': 0}})
        row.update(data)
        if event == 'usage':
            row['usage'] = data['usage']


class FakeHelper:
    def __init__(self, helper_id):
        self.session_id = 'child-session-' + helper_id
        self.active = False
        self.usage = {'input_tokens': 10, 'output_tokens': 2, 'estimated_cost': None}
        self.stopped = False
        self.observations = 0

    def invoke(self, prompt, invocation_id):
        self.active = True
        return {'output': 'permitted helper result', 'invocation_id': invocation_id}

    def observe(self, timeout_seconds=0):
        self.observations += 1
        rows = [{'event': 'usage', 'usage': self.usage}]
        if self.observations >= 2:
            rows.append({'event': 'completed', 'status': 'completed'})
            self.active = False
        return rows

    def steer(self, message):
        return {'status': 'accepted'}

    def interrupt(self):
        self.stopped = True
        self.active = False

    close = interrupt


class FakeRuntime:
    session_id = 'parent-session'

    def __init__(self):
        self.children = {}

    def create_helper(self, helper_id):
        child = FakeHelper(helper_id)
        self.children[helper_id] = child
        return child


class FakeContext:
    worker = {'worker_id': 'parent-worker', 'generation': 1}
    grant = {'worker_id': 'parent-worker', 'generation': 1, 'effects': ['read']}
    principal = {'engagement_id': 'fixture', 'worker_id': 'parent-worker',
                 'session_id': 'parent-session', 'role': 'lead'}

    def authorize(self):
        return self.grant


class FakeBoundary:
    def __init__(self):
        self.context = FakeContext()
        self.controller = FakeController()
        self.runtime = FakeRuntime()

    @contextmanager
    def guard(self):
        yield

    def record_helper(self, grant, helper_id, event, data):
        self.controller.record_helper(grant, helper_id, event, data)

    def read_object(self, sha):
        return b'permitted helper result'


def main() -> None:
    boundary = FakeBoundary()
    sessions = HelperSessions(boundary)
    rows = []
    for _ in range(2):
        created = sessions.handle({'action': 'spawn', 'prompt': 'inspect authorized notes'})
        helper_id = created['helper_id']
        uuid.UUID(helper_id)
        row = sessions.handle({'action': 'read', 'helper_id': helper_id})
        assert row['worker_id'] == 'parent-worker'
        assert row['parent_session_id'] == 'parent-session'
        assert row.get('role') != 'reviewer'
        rows.append((helper_id, row))
    assert len({helper_id for helper_id, _ in rows}) == 2
    for helper_id, _ in rows:
        deadline = time.monotonic() + 1
        while 'usage' not in boundary.controller.data['helpers'][helper_id] and time.monotonic() < deadline:
            time.sleep(0.01)
        observed = [event for identity, event, _ in boundary.controller.events if identity == helper_id]
        assert observed.count('usage') == 1, observed
        usage = boundary.controller.data['helpers'][helper_id]['usage']
        assert usage == {'tokens': {'input': 10, 'output': 2}, 'cost': None}, usage

    forged = '00000000-0000-0000-0000-000000000001'
    try:
        sessions.handle({'action': 'read', 'helper_id': forged})
    except RuntimeError as error:
        assert error.code == 'native_helper_identity_invalid', error.code
    else:
        raise AssertionError('forged helper identity was accepted')

    sessions.close()
    assert all(child.stopped for child in boundary.runtime.children.values())


if __name__ == '__main__':
    main()
