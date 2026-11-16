from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

from engagement_controller import ControllerError
from engagement_runner import Runner
from native_runtime_transport import RuntimeError


class SessionReconstructionTest(unittest.TestCase):
    def setUp(self):
        self.worker = {'id': 'worker-1', 'role': 'specialist', 'generation': 2, 'status': 'stopped'}
        self.state = {'status': 'active', 'workers': {'worker-1': self.worker}, 'replacement_required': False}
        self.resume = Mock()
        self.runner = Runner.__new__(Runner)
        self.runner.controller = SimpleNamespace(state=lambda: self.state, resume_worker=self.resume)
        self.runner.failures = {'worker-1': 'native_session_dispatch_limit_reconstruct_required'}
        self.runner.jobs = {}

    def test_reconstruction_uses_existing_authority_and_settlement_gate(self):
        self.runner._reconstruct_exhausted_sessions()
        self.resume.assert_called_once_with('worker-1', 2, reason='controller_resume')
        self.assertNotIn('worker-1', self.runner.failures)

    def test_resume_denial_is_not_retried(self):
        for code in ('authority_expired', 'worker_resume_unsettled', 'engagement_stopped'):
            with self.subTest(code=code):
                self.setUp()
                self.resume.side_effect = ControllerError(code)
                self.runner._reconstruct_exhausted_sessions()
                self.runner._reconstruct_exhausted_sessions()
                self.resume.assert_called_once()
                self.assertEqual(self.runner.failures['worker-1'], code)

    def test_lead_replacement_takes_priority_over_session_reconstruction(self):
        self.worker['role'] = 'lead'
        self.state['replacement_required'] = True
        self.assertFalse(self.runner._reconstruct_exhausted_sessions())
        self.resume.assert_not_called()

    def test_other_runtime_failures_are_not_retried(self):
        for code in ('native_tool_call_limit', 'native_tool_concurrency_limit',
                     'native_host_tool_denied', 'native_dispatch_unknown',
                     'worker_cleanup_unresolved', 'native_worker_unavailable'):
            with self.subTest(code=code):
                self.runner.failures['worker-1'] = code
                self.runner._reconstruct_exhausted_sessions()
        self.resume.assert_not_called()

    def test_running_jobs_and_nonactive_engagements_are_not_resumed(self):
        self.runner.jobs['worker-1', 2] = SimpleNamespace(is_alive=lambda: True)
        self.runner._reconstruct_exhausted_sessions()
        self.runner.jobs.clear()
        self.state['status'] = 'stopped'
        self.runner._reconstruct_exhausted_sessions()
        self.state['status'] = 'active'
        self.worker['status'] = 'revoked'
        self.runner._reconstruct_exhausted_sessions()
        self.resume.assert_not_called()

    def test_rejected_invocation_does_not_recharge_previous_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            self.state['scope'] = {'limits': {'max_worker_lease_seconds': 60},
                                   'environments': [{'limits': {'lease_seconds': 60}}]}
            controller = self.runner.controller
            controller.root = Path(directory) / 'engagement'
            controller.prepare_worker_dispatch = Mock(return_value={})
            controller.record_worker_started = Mock()
            controller.begin_invocation = Mock(return_value='not-dispatched')
            controller.record_invocation_observed = Mock()
            runtime = SimpleNamespace(usage={'total_tokens': 500, 'estimated_cost': 1},
                invoke=Mock(side_effect=RuntimeError('native_session_dispatch_limit_reconstruct_required')))
            boundary = SimpleNamespace(runtime=runtime, start=lambda: {'session_id': 'session', 'owner_receipt': {}})
            self.runner.factory = lambda context: boundary
            self.runner._resources = lambda state, worker: []
            self.runner._prompt = lambda *args: 'Continue.'
            self.runner._settle = Mock(return_value=True)
            self.runner.mutex = threading.Lock()
            self.runner.changed = threading.Event()
            self.runner.failed_generations = set()
            context = SimpleNamespace(grant={}, authorize=lambda: None)
            with patch('engagement_runner.WorkerContext', return_value=context):
                self.runner._work(self.worker)
            controller.record_invocation_observed.assert_called_once_with({}, 'not-dispatched',
                {'status': 'local_only', 'usage': {'tokens': {'total': 0}, 'cost': 0}})
            self.runner._settle.assert_called_once()


if __name__ == '__main__':
    unittest.main()
