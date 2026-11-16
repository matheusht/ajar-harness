"""Native helper sessions with one inherited engagement identity and authority.

This is transport lifecycle, not task planning. The parent chooses helper work.
"""
from __future__ import annotations

import threading
import time
import uuid

from engagement_contract import safe_publication
from native_runtime_transport import RuntimeError


def usage(runtime):
    observed = runtime.usage or {}
    names = {'input': 'input_tokens', 'output': 'output_tokens', 'cached_input': 'cached_input_tokens',
             'cache_write': 'cache_write_input_tokens', 'reasoning': 'reasoning_output_tokens', 'total': 'total_tokens'}
    return {'tokens': {key: observed[name] for key, name in names.items() if observed.get(name) is not None} or None,
            'cost': observed.get('estimated_cost')}


class HelperSessions:
    def __init__(self, boundary):
        self.boundary = boundary
        self.context, self.controller = boundary.context, boundary.controller
        self.parent_session = boundary.runtime.session_id
        boundary.runtime.helper_observer = lambda identity, receipt: self.controller.record_helper(
            self.context.grant, identity, 'owner', {'owner_receipt': receipt})
        self.jobs = {}
        self.lock = threading.RLock()
        self.closed = False

    def _owned(self, identity):
        row = self.controller.state()['helpers'].get(identity)
        grant = self.context.grant
        if (row is None or row.get('worker_id') != grant['worker_id'] or
                row.get('generation') != grant['generation'] or row.get('parent_session_id') != self.parent_session):
            raise RuntimeError('native_helper_identity_invalid')
        return row

    def handle(self, arguments):
        if not isinstance(arguments, dict) or set(arguments) - {'action', 'prompt', 'helper_id', 'message'}:
            raise RuntimeError('native_helper_request_invalid')
        self.context.authorize()
        action = arguments.get('action')
        if action == 'spawn':
            prompt = arguments.get('prompt')
            if not isinstance(prompt, str) or not prompt or len(prompt.encode()) > 65536:
                raise RuntimeError('native_helper_prompt_invalid')
            safe_publication(prompt.encode())
            with self.lock:
                if self.closed:
                    raise RuntimeError('native_helpers_stopped')
                identity = uuid.uuid4().hex
                self.controller.record_helper(self.context.grant, identity, 'intended', {
                    'worker_id': self.context.grant['worker_id'], 'generation': self.context.grant['generation'],
                    'parent_session_id': self.parent_session, 'status': 'starting'})
                job = {'handle': None, 'stop': threading.Event()}
                job['thread'] = threading.Thread(target=self._run, args=(identity, prompt, job), daemon=True)
                self.jobs[identity] = job
                job['thread'].start()
                return {'helper_id': identity, 'status': 'starting', 'identity': 'parent_owned'}
        identity = arguments.get('helper_id')
        row = self._owned(identity)
        job = self.jobs.get(identity)
        if action == 'read':
            result = dict(row)
            if row.get('output_sha256'):
                result['output'] = self.controller.read_object(row['output_sha256']).decode('utf-8')
            return result
        if action == 'stop':
            if job:
                job['stop'].set()
                if job['handle'] is not None:
                    job['handle'].interrupt()
            return {'helper_id': identity, 'stop_requested': True}
        if action == 'steer':
            message = arguments.get('message')
            if not isinstance(message, str) or not message or len(message.encode()) > 65536:
                raise RuntimeError('native_helper_message_invalid')
            if job is None or job['handle'] is None or not job['handle'].active:
                raise RuntimeError('native_helper_inactive')
            job['handle'].steer(message)
            return {'helper_id': identity, 'delivered': True}
        raise RuntimeError('native_helper_request_invalid')

    def _run(self, identity, prompt, job):
        handle, output, status, reason = None, '', 'failed', None
        prior_usage = None
        try:
            self.context.authorize()
            if job['stop'].is_set():
                status = 'stopped'
                return
            handle = self.boundary.runtime.create_helper(identity)
            job['handle'] = handle
            self.controller.record_helper(self.context.grant, identity, 'started', {'session_id': handle.session_id})
            handle.invoke('You are an internal helper acting under the parent\'s identity and permissions. '
                          'Your work is not independent review. Publish useful evidence through the shared tools.\n' + prompt, identity)
            while True:
                self.context.authorize()
                if job['stop'].is_set():
                    status = 'stopped'
                    handle.interrupt()
                    break
                events = handle.observe(timeout_seconds=.05)
                for event in events:
                    if event['event'] == 'text':
                        remaining = 65536 - len(output.encode())
                        output += event.get('text', '').encode()[:remaining].decode('utf-8', errors='ignore')
                    elif event['event'] == 'unknown':
                        raise RuntimeError('native_helper_outcome_unknown')
                    elif event['event'] == 'completed':
                        status = 'completed' if event['status'] == 'completed' else 'stopped' if event['status'] in ('aborted', 'interrupted') else 'failed'
                observed = usage(handle)
                if observed != prior_usage and observed != {'tokens': None, 'cost': None}:
                    self.controller.record_helper(self.context.grant, identity, 'usage', {'usage': observed})
                    prior_usage = observed
                if not handle.active:
                    break
                if not events:
                    time.sleep(.01)
        except Exception as error:
            reason = getattr(error, 'code', 'native_helper_unavailable')
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    status, reason = 'failed', 'native_helper_stop_unverified'
                observed = usage(handle)
                if observed != prior_usage and observed != {'tokens': None, 'cost': None}:
                    try:
                        self.controller.record_helper(self.context.grant, identity, 'usage', {'usage': observed})
                    except Exception:
                        status, reason = 'failed', 'native_helper_usage_unrecorded'
            try:
                safe_publication(output.encode())
            except ValueError:
                output = '[Helper output withheld by the shared credential scanner.]'
            try:
                self.controller.record_helper(self.context.grant, identity, 'finished',
                    {'status': status, 'output': output, 'reason': reason})
            finally:
                with self.lock:
                    self.jobs.pop(identity, None)

    def close(self):
        with self.lock:
            self.closed = True
            jobs = list(self.jobs.values())
        for job in jobs:
            job['stop'].set()
            if job['handle'] is not None:
                try:
                    job['handle'].interrupt()
                except Exception:
                    pass
        for job in jobs:
            if job['thread'] is not threading.current_thread():
                job['thread'].join(timeout=5)
