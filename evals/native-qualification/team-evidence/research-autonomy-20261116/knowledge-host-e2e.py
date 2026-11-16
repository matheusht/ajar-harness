#!/usr/bin/env python3
"""Signed controller and host knowledge-tool flow with synthetic fetch/environment.

No native model, Docker, external network, or real security evidence is used.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'evals/native-qualification/smoke')]
import check_engagement_evidence_e2e as fixture
import engagement_knowledge_delivery as delivery
from engagement_contract import canonical, digest, source_manifest
from engagement_controller import Principal
from engagement_knowledge import KnowledgeLibrary
from engagement_native_boundary import NativeBoundary
from engagement_runner import WorkerContext


class Environment:
    limits = {'output_bytes': 1048576}
    def read_artifact(self, path, maximum):
        assert path == 'procedure.md' and maximum >= 64
        return {'content': b'Inspect the harmless input and compare a counterexample.\n'}


def main(output):
    result = {'kind': 'knowledge-host-engagement-e2e', 'status': 'failed',
              'classification': 'real_signed_controller_and_host_tool_with_simulated_fetch_and_environment',
              'native_runtime': False, 'docker_lab': False, 'checks': []}
    def check(name, condition):
        result['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)
    try:
        with tempfile.TemporaryDirectory(prefix='oslit-knowledge-') as directory:
            root = Path(directory).resolve(); shared = KnowledgeLibrary(root / 'shared', corpus_root=None)
            original_scope, original_make = fixture.fixture.fixture_scope, fixture.fixture.make_fixture
            def case(name, content):
                def make(path):
                    inputs = original_make(path)
                    document = json.loads(inputs.read_bytes())
                    fixture.fixture.write(Path(document['access_files']['source-main']) / 'main.py', content)
                    return inputs
                def scope(inputs):
                    value = original_scope(inputs); document = json.loads(inputs.read_bytes())
                    value['engagement_id'] = name; value['authority_policy'] = 'research-autonomy-v1'
                    value['reference_web'] = {'public_sources': True, 'max_bytes': 1048576, 'timeout_seconds': 10}
                    value['access'][0]['identity']['manifest_sha256'] = digest(canonical(source_manifest(Path(document['access_files']['source-main']))))
                    return value
                with patch.object(fixture.fixture, 'make_fixture', make), patch.object(fixture.fixture, 'fixture_scope', scope):
                    return fixture.Case(root / name, start=False)
            def start(case, worker, role='lead'):
                workspace = case.workspace(worker)
                grant = case.c.prepare_worker_dispatch(worker, 1, workspace, seconds=30,
                    resources=['source-main'], adapter_id='fixture-adapter')
                session = 'session-' + case.c.state()['engagement_id'] + '-' + worker
                case.c.record_worker_started(worker, 1, session, workspace, owner_receipt=case.owner(worker, session))
                runner = SimpleNamespace(controller=case.c, contract=case.contract, changed=threading.Event())
                context = WorkerContext(runner, case.c.state()['workers'][worker], grant, workspace)
                boundary = NativeBoundary(context); boundary.environment = Environment()
                boundary._knowledge_shared = shared
                boundary._knowledge_local = KnowledgeLibrary(case.c.root / 'knowledge', corpus_root=None)
                return boundary
            def tool(boundary, arguments):
                response = boundary.host_call('engagement_knowledge', arguments).wait()
                return response, json.loads(response['content'][0]['text'])
            def refused(boundary, arguments, expected):
                try:
                    response, value = tool(boundary, arguments)
                    return response.get('isError') and value.get('code') == expected
                except Exception as error:
                    return getattr(error, 'code', None) == expected
            first = case('case-a', b'print("case A")\n'); lead = start(first, 'lead-1')
            response, technique = tool(lead, {'action': 'publish', 'path': 'procedure.md',
                'title': 'Owned procedure', 'applicability': 'owned fixture', 'helpers': []})
            check('lead publishes experimental exact technique', not response.get('isError')
                  and technique.get('retention') == 'retained' and technique.get('technique_status') == 'experimental')
            version = technique['version']
            second = case('case-b', b'print("case B")\n'); second_lead = start(second, 'lead-1')
            response, selected = tool(second_lead, {'action': 'read', 'version': version,
                'materialize': False, '_delivery_id': 'fixture-read'})
            check('changed case selects same retained version', not response.get('isError') and selected['version'] == version)
            def reviewer(name, review):
                second.worker(name, 'reviewer', start=False)
                second.request('review_request', {'review_id': review, 'kind': 'technique',
                    'subject_id': version, 'reviewer_id': name})
                return start(second, name, 'reviewer'), Principal('worker', name, 1)
            def observation(actor, name):
                workspace = second.workspace(actor.id); (workspace / (name + '.txt')).write_text('Synthetic decision outcome.\n')
                second.request('publish', {'publication_id': name, 'kind': 'observation', 'subject': name,
                    'body': 'Synthetic independent decision outcome.', 'refs': [], 'supersedes': [],
                    'artifacts': [{'path': name + '.txt'}]}, actor)
            reviewer1, actor1 = reviewer('reviewer-1', 'technique-review-1')
            observation(actor1, 'transfer'); observation(actor1, 'counterexample')
            denied = refused(second_lead, {'action': 'evaluate', 'review_id': 'technique-review-1',
                'status': 'recommended', 'transfer_refs': ['transfer'], 'counterexample_refs': ['counterexample'],
                'applicability': 'owned fixture', 'reason': 'A lead cannot satisfy the reviewer assignment.'}, 'review_identity_invalid')
            check('lead cannot satisfy a fresh reviewer assignment', denied)
            denied = refused(reviewer1, {'action': 'evaluate', 'review_id': 'technique-review-1',
                'status': 'recommended', 'transfer_refs': ['invented'], 'counterexample_refs': ['counterexample'],
                'applicability': 'owned fixture', 'reason': 'Invented evidence must be rejected.'}, 'technique_evidence_missing')
            check('invented evidence cannot recommend a technique', denied)
            denied = refused(reviewer1, {'action': 'evaluate', 'review_id': 'technique-review-1',
                'status': 'recommended', 'transfer_refs': ['transfer'], 'counterexample_refs': ['transfer'],
                'applicability': 'owned fixture', 'reason': 'One observation cannot stand for both outcomes.'}, 'technique_counterexample_distinct_outcome_required')
            check('transfer and counterexample must be distinct', denied)
            response, evaluated = tool(reviewer1, {'action': 'evaluate', 'review_id': 'technique-review-1',
                'status': 'recommended', 'transfer_refs': ['transfer'], 'counterexample_refs': ['counterexample'],
                'applicability': 'owned fixture', 'reason': 'Changed case and counterexample are separately observed.'})
            check('independent changed-case and counterexample recommend exact version',
                  not response.get('isError') and evaluated.get('status') == 'recommended' and evaluated['version'] == version)
            reviewer2, actor2 = reviewer('reviewer-2', 'technique-review-2')
            observation(actor2, 'withdrawal')
            response, withdrawn = tool(reviewer2, {'action': 'evaluate', 'review_id': 'technique-review-2',
                'status': 'withdrawn', 'transfer_refs': [], 'counterexample_refs': ['withdrawal'],
                'applicability': 'owned fixture', 'reason': 'Synthetic contrary evidence withdraws the recommendation.'})
            check('fresh reviewer withdraws recommendation', not response.get('isError') and withdrawn.get('status') == 'withdrawn')
            response, current = tool(second_lead, {'action': 'read', 'version': version,
                'materialize': False, '_delivery_id': 'fixture-read-after-withdrawal'})
            check('withdrawal visible without rewriting original bytes', not response.get('isError')
                  and current.get('technique_status') == 'withdrawn'
                  and current.get('content') == 'Inspect the harmless input and compare a counterexample.\n')
            fetched = {'content': b'Owned fetched reference.\n', 'origin': 'https://reference.example/',
                       'requested_origin': 'https://reference.example/', 'content_type': 'text/plain'}
            with patch.object(delivery, 'fetch_reference', return_value=fetched), \
                 patch.object(shared, '_put', side_effect=OSError('fixture retention failure')), \
                 patch.object(second_lead._knowledge_local, '_put', side_effect=OSError('fixture retention failure')):
                response, gap = tool(second_lead, {'action': 'fetch', 'url': fetched['origin'],
                    'title': 'Owned reference', 'materialize': False, '_delivery_id': 'fixture-fetch-gap'})
            check('fetch content remains usable when retention fails', not response.get('isError')
                  and gap.get('content') == 'Owned fetched reference.\n' and gap.get('retention') == 'not_retained')
            records = second.c.state()['knowledge_deliveries']
            check('retention failure is recorded durably', any(row.get('version') == gap['version']
                  and row.get('retention') == 'not_retained' for row in records))
            destination = root / 'export'; exported = second.c.export(destination)
            projection = json.loads((destination / 'result.json').read_bytes())
            manifest = json.loads((destination / 'manifest.json').read_bytes())
            check('same engagement export preserves retention gap', exported['status'] == 'exported'
                  and any(row.get('version') == gap['version'] and row.get('retention') == 'not_retained'
                          for row in projection['knowledge_deliveries'])
                  and 'knowledge/files/' + digest(fetched['content'])[7:] not in manifest['files'])
            for script, extra in (('check_engagement_export.py', []),
                                  ('verify_engagement_export_references.py', []),
                                  ('verify_engagement_export_references.py', ['--check-result'])):
                checked = subprocess.run([sys.executable, str(ROOT / 'tools' / script), str(destination), *extra],
                                         capture_output=True, timeout=30)
                check('export check ' + script + ' ' + ' '.join(extra), checked.returncode == 0)
            result['status'] = 'passed'
    except Exception as error:
        import traceback
        result['error'] = getattr(error, 'code', type(error).__name__)
        result['error_frames'] = [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                                  for frame in traceback.extract_tb(error.__traceback__)[-6:]]
    result['source_sha256'] = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in
        (Path(__file__), ROOT / 'tools/engagement_knowledge_delivery.py', ROOT / 'tools/engagement_knowledge.py',
         ROOT / 'tools/engagement_controller.py', ROOT / 'tools/engagement_evidence.py')}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(canonical(result))
    print(json.dumps(result, sort_keys=True))
    return result['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
