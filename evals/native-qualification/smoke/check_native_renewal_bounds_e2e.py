#!/usr/bin/env python3
"""Exercise native boundary renewal against a changing signed grant deadline."""
import argparse
from contextlib import contextmanager
from datetime import datetime as RealDatetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import research_environment
from engagement_native_boundary import NativeBoundary
from research_environment import Environment


def run():
    current = [RealDatetime(2026, 11, 16, tzinfo=timezone.utc)]
    class Clock(RealDatetime):
        @classmethod
        def now(cls, tz=None): return current[0]
    research_environment.datetime = Clock
    grant = {'lease_expires_at': (current[0] + timedelta(seconds=30)).isoformat()}
    authorized, owner_calls, checks = [True], [], []
    @contextmanager
    def guard():
        current[0] += timedelta(seconds=.25)
        yield
    class Owner:
        def __init__(self, name): self.name = name
        def renew(self, seconds):
            owner_calls.append((self.name, seconds, (RealDatetime.fromisoformat(grant['lease_expires_at']) - current[0]).total_seconds()))
            current[0] += timedelta(seconds=.5)
    def environment(name):
        env = Environment.__new__(Environment)
        env.retired = env.held = False; env.grant = grant; env.limits = {'lease_seconds': 30}
        env.authorize = lambda: authorized[0]; env.dispatch_guard = guard; env.lock = threading.RLock()
        env.owner = Owner(name); env._inspect = lambda: {}; env._verify_configuration = lambda _: None
        env._event = lambda *a, **k: None; env.receipt = lambda: {'kind': 'owned-fixture'}
        return env
    model, tool = environment('model'), environment('tool')
    boundary = NativeBoundary.__new__(NativeBoundary)
    boundary.scope = {'authority_policy': 'initial-scope-v1'}
    boundary.context = SimpleNamespace(authorize=lambda: authorized[0], grant=grant)
    boundary.environment, boundary.finished = tool, None
    class ModelOwner:
        def renew(self, grant_value, seconds=None):
            model.grant = grant_value
            return model.renew(seconds) if seconds is not None else model.renew()
    boundary.model_owner = ModelOwner()
    def check(name, action):
        try: action(); checks.append({'name': name, 'passed': True})
        except Exception as error: checks.append({'name': name, 'passed': False, 'error': getattr(error, 'code', type(error).__name__)})
    def bounded():
        boundary.renew()
        assert [row[0] for row in owner_calls] == ['model', 'tool']
        assert all(0 < seconds <= remaining for _, seconds, remaining in owner_calls)
        assert owner_calls[1][1] < owner_calls[0][1]
    check('each owner renewal uses its current admitted remaining grant', bounded)
    def refuse(seconds, code):
        try: tool.renew(seconds) if seconds is not None else tool.renew()
        except Exception as error:
            assert getattr(error, 'code', str(error)) == code; return
        raise AssertionError('renewal unexpectedly accepted')
    def excessive(): refuse(1000, 'environment_lease_exceeds_grant')
    check('explicit duration exceeding grant refused', excessive)
    def revoked():
        authorized[0] = False
        try: refuse(None, 'environment_grant_inactive')
        finally: authorized[0] = True
    check('revoked grant refused', revoked)
    def expired():
        current[0] = RealDatetime.fromisoformat(grant['lease_expires_at']) + timedelta(seconds=1)
        refuse(None, 'environment_grant_inactive')
    check('expired grant refused', expired)
    return checks


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); checks = run()
    result = {'kind': 'native-renewal-bounds-e2e-v1', 'classification': 'actual_boundary_and_environment_with_controlled_clock_and_owned_owners',
              'checks': checks, 'status': 'passed' if all(c['passed'] for c in checks) else 'failed',
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  (Path(__file__), ROOT / 'tools/engagement_native_boundary.py', ROOT / 'tools/research_environment.py')}}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': checks})); return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
