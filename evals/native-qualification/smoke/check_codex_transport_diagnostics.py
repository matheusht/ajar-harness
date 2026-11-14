#!/usr/bin/env python3
"""Exercise fail-closed pipe diagnostics without native runtimes or provider calls."""
import io
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
import native_runtime_codex as codex

SECRET = 'private-token-never-publish'


class TransportDiagnostics(unittest.TestCase):
    def owner(self):
        owner = codex.NativeExecutor.__new__(codex.NativeExecutor)
        owner.closed = False
        owner.failure = None
        owner.transport_diagnostic = None
        owner.diagnostic_lock = threading.Lock()
        owner.initialize_id = 1
        owner.expected_version = '0.166.0'
        owner.expected_platform = 'linux'
        owner.ready = None
        owner.guard = nullcontext
        owner.bridge = SimpleNamespace(stdin=io.BytesIO())
        return owner

    def check_failure(self, data, *, admit=False, phase='frame', guard=None, writer=None):
        owner = self.owner()
        if guard is not None:
            owner.guard = guard
        source = SimpleNamespace(stdout=io.BytesIO(data))
        destination = SimpleNamespace(stdin=io.BytesIO())
        with patch.object(codex, 'write_pipe', writer or (lambda stream, payload: stream.write(payload))):
            owner._copy(source, destination, admit)
        self.assertEqual(owner.failure, 'native_executor_transport_failed')
        self.assertEqual(owner.transport_diagnostic, {
            'direction': 'to_executor' if admit else 'from_executor',
            'phase': phase, 'outcome': 'exception'})
        self.assertTrue(owner.bridge.stdin.closed)
        with self.assertRaises(codex.RuntimeError):
            owner.check_authority()
        self.assertNotIn(SECRET, json.dumps(owner.transport_diagnostic))
        return owner

    def test_bad_json(self):
        self.check_failure((SECRET+'\n').encode())

    def test_bad_frame_shape(self):
        self.check_failure(json.dumps({'frame': {'secret': SECRET}}).encode()+b'\n', admit=True)

    def test_oversized_frame(self):
        self.check_failure(b'x' * (2 * 1048576 + 1))

    def test_identity(self):
        self.check_failure(json.dumps({'id': 1, 'result': {'environmentInfo': {
            'executorVersion': SECRET, 'platformOs': 'linux'}}}).encode()+b'\n', phase='identity')

    def test_admission(self):
        def reject():
            raise ValueError(SECRET)
        self.check_failure(b'{"frame":"{}"}\n', admit=True, phase='admission', guard=reject)

    def test_write(self):
        def reject(stream, payload):
            raise BrokenPipeError(SECRET)
        self.check_failure(b'{}\n', phase='write', writer=reject)

    def test_eof_retains_previous_diagnostic(self):
        owner = self.check_failure(b'bad\n')
        original = dict(owner.transport_diagnostic)
        owner._copy(SimpleNamespace(stdout=io.BytesIO()), SimpleNamespace(stdin=io.BytesIO()), True)
        self.assertEqual(owner.transport_diagnostic, original)
        self.assertEqual(owner.failure, 'native_executor_transport_failed')

    def test_secondary_exception_preserves_first_failure(self):
        owner = self.check_failure(b'bad\n')
        original = dict(owner.transport_diagnostic)
        with patch.object(codex, 'write_pipe', side_effect=BrokenPipeError(SECRET)):
            owner._copy(SimpleNamespace(stdout=io.BytesIO(b'{"frame":"{}"}\n')),
                        SimpleNamespace(stdin=io.BytesIO()), True)
        self.assertEqual(owner.transport_diagnostic, original)
        self.assertTrue(owner.bridge.stdin.closed)

    def test_eof(self):
        owner = self.owner()
        owner._copy(SimpleNamespace(stdout=io.BytesIO()), SimpleNamespace(stdin=io.BytesIO()), True)
        self.assertEqual(owner.failure, 'native_executor_transport_closed')
        self.assertEqual(owner.transport_diagnostic, {'direction': 'to_executor', 'phase': 'read', 'outcome': 'eof'})
        self.assertTrue(owner.bridge.stdin.closed)

    def test_closed_is_not_a_transport_failure(self):
        owner = self.owner()
        owner.closed = True
        owner._copy(SimpleNamespace(stdout=io.BytesIO()), SimpleNamespace(stdin=io.BytesIO()), True)
        self.assertIsNone(owner.failure)
        self.assertIsNone(owner.transport_diagnostic)


if __name__ == '__main__':
    unittest.main()
