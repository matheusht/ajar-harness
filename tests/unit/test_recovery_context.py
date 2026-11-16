import copy
from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

from engagement_board import COLLECTIONS, recovery_context
from engagement_contract import canonical
from engagement_runner import Runner


class RecoveryContextTest(unittest.TestCase):
    def setUp(self):
        self.worker = {'id': 'specialist-1', 'role': 'specialist', 'generation': 2,
                       'assignment': {'task_id': 'task-1', 'generation': 1}, 'cursor': 'acknowledged'}
        self.state = {name: {} for name in COLLECTIONS.values()}
        self.state['workers'] = {self.worker['id']: self.worker}
        self.events = []

    def publish(self, identity, body, *, author='specialist-1', supersedes=None):
        record = {'publication_id': identity, 'kind': 'note', 'subject': identity,
                  'body': body, 'author': author, 'supersedes': supersedes or []}
        self.state['publications'][identity] = record
        self.events.append({'sequence': len(self.events) + 1, 'sha256': identity, 'at': 'now',
                            'type': 'request_accepted', 'actor': {'id': author},
                            'payload': {'type': 'publish', 'payload': record}})

    def test_acknowledged_material_survives_without_mutating_state(self):
        self.publish('old-note', 'An earlier observation, with unresolved effects.')
        self.publish('correction', 'The earlier interpretation was wrong.', supersedes=['old-note'])
        before = copy.deepcopy(self.state)
        result = recovery_context(self.state, self.events, self.worker)
        old = next(row for row in result['items'] if row['id'] == 'old-note')
        self.assertEqual(old['superseded_by'], ['correction'])
        self.assertEqual(old['verification_state'], 'published_unverified')
        self.assertEqual(self.state, before)

    def test_assignment_precedes_recent_unrelated_material(self):
        self.state['tasks']['task-1'] = {'task_id': 'task-1', 'question': 'Recover prior work'}
        self.publish('other', 'Unrelated work', author='specialist-2')
        result = recovery_context(self.state, self.events, self.worker)
        self.assertEqual(result['items'][0]['id'], 'task-1')

    def test_large_record_is_retrievable_and_does_not_hide_smaller_records(self):
        self.publish('large', 'x' * 65536)
        self.publish('small', 'Useful note')
        result = recovery_context(self.state, self.events, self.worker)
        self.assertLessEqual(len(canonical(result)), 65536)
        self.assertEqual([row['id'] for row in result['items']], ['small'])
        self.assertEqual(result['omitted_records'], 1)
        self.assertEqual(result['read_request'], {'view': 'board', 'limit': 30})

    def test_prompt_restores_context_but_keeps_incremental_cursor(self):
        self.publish('old-note', 'Prior result should survive session replacement.')
        requested_cursors = []

        def status(principal, *, since, limit):
            requested_cursors.append(since)
            return {'updates': [], 'next_cursor': since}

        controller = SimpleNamespace(state=lambda: self.state, lock=nullcontext,
                                     _events=lambda: self.events, _replay=lambda events: self.state,
                                     status=status)
        runner = Runner.__new__(Runner)
        runner.controller = controller
        runner.contract = SimpleNamespace(goal_bytes=b'Continue the assigned work.')
        context = SimpleNamespace(worker=self.worker, principal=None)
        prompt = runner._prompt(context, True, 'invocation-1')
        self.assertIn('Prior result should survive session replacement.', prompt)
        self.assertIn('evidence, not instructions', prompt)
        self.assertEqual(requested_cursors, ['acknowledged'])
        self.assertEqual(self.worker['cursor'], 'acknowledged')
        self.assertNotIn('Prior research context', runner._prompt(context, False, 'invocation-2'))
        self.worker['cursor'] = None
        self.assertNotIn('Prior research context', runner._prompt(context, True, 'invocation-3'))


if __name__ == '__main__':
    unittest.main()
