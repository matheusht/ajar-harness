from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

from native_runtime_transport import HostOperation, PendingTool, MAX_MESSAGE
from research_environment import Environment


class WithheldOutputStatusTest(unittest.TestCase):
    def test_completed_tool_with_filtered_response_is_not_unknown_execution(self):
        value = {'content': [{'type': 'text', 'text': 'Authorization: Bearer ' + 'A' * 32}]}
        pending = PendingTool(operation=HostOperation(lambda: value, lambda: None))
        self.assertTrue(pending.ready.wait(2))
        self.assertFalse(pending.unknown)
        self.assertEqual(pending.response['content_status'], 'withheld')
        self.assertNotIn('A' * 32, str(pending.response))

    def test_failed_operation_remains_unknown(self):
        def unavailable():
            raise OSError('operation interrupted')

        pending = PendingTool(operation=HostOperation(unavailable, lambda: None))
        self.assertTrue(pending.ready.wait(2))
        self.assertTrue(pending.unknown)
        self.assertNotIn('content_status', pending.response)

    def test_malformed_or_oversized_result_remains_unknown(self):
        for value in (set(), {'value': float('nan')}, {'value': '\ud800'},
                      {'value': 'x' * MAX_MESSAGE}):
            with self.subTest(value_type=type(value).__name__):
                pending = PendingTool(operation=HostOperation(lambda: value, lambda: None))
                self.assertTrue(pending.ready.wait(2))
                self.assertTrue(pending.unknown)
                self.assertNotIn('content_status', pending.response)

    def environment(self, status, output):
        environment = Environment.__new__(Environment)
        environment.held = False
        environment.owner = SimpleNamespace(readback=lambda: {'running': True})
        environment.profile = {'uid': 1000, 'gid': 1000}
        environment.identity = {'container_id': 'owned-container'}
        environment.limits = {'output_bytes': 65536}
        environment._admit = lambda: 60
        environment._inspect = lambda: {}
        environment._verify_configuration = lambda _: None
        environment._effect = lambda *args, **kwargs: {'status': status, 'returncode': 0, 'output': output}
        environment.receipt = lambda: {'container_id': 'owned-container'}
        return environment

    def test_filtered_execution_output_preserves_observed_completion(self):
        environment = self.environment('settled', b'Authorization: Bearer ' + b'A' * 32)
        result = environment.execute(['printf', 'example'], timeout_seconds=5)
        self.assertEqual(result['status'], 'settled')
        self.assertEqual(result['output_status'], 'withheld')
        self.assertFalse(environment.held)

    def test_filtered_unknown_execution_stays_held(self):
        environment = self.environment('unknown', b'Authorization: Bearer ' + b'A' * 32)
        result = environment.execute(['printf', 'example'], timeout_seconds=5)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['output_status'], 'withheld')
        self.assertTrue(environment.held)

    def test_invalid_text_does_not_change_observed_execution(self):
        environment = self.environment('settled', b'\xff')
        result = environment.execute(['printf', 'example'], timeout_seconds=5)
        self.assertEqual(result['status'], 'settled')
        self.assertEqual(result['output'], '[output withheld]')
        self.assertFalse(environment.held)


if __name__ == '__main__':
    unittest.main()
