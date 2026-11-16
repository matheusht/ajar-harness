"""Small offline checks for selected knowledge identity and recommendation rules."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engagement_knowledge import KnowledgeLibrary


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='knowledge-contract-') as temporary:
        library = KnowledgeLibrary(Path(temporary) / 'library')
        source = library.retain(b'Original reference bytes', origin='https://example.test/a',
                                title='A', kind='reference')
        first = library.read(source['version'])
        assert first['status'] == 'available' and first['content'] == 'Original reference bytes'

        author = {'engagement_id': 'eng-a', 'worker_id': 'lead-a', 'session_id': 'ses-a'}
        package = library.publish_technique(b'check procedure v1', title='check',
                                             origin='engagement:eng-a', author=author,
                                             source_case='case-a', applicability='local source')
        version = package['version']
        rejected = False
        try:
            library.evaluate(version, evaluator=author, transfer_case='case-b', transfer=True,
                             counterexample=True, evidence_refs=['ev-a'],
                             applicability='local source', reason='independent checks')
        except (ValueError, PermissionError):
            rejected = True
        assert rejected, 'author evaluated their own technique'

        evaluator = {'engagement_id': 'eng-b', 'worker_id': 'reviewer-b', 'session_id': 'ses-b'}
        result = library.evaluate(version, evaluator=evaluator, transfer_case='case-b',
                                  transfer=True, counterexample=True, evidence_refs=['ev-b'],
                                  applicability='local source', reason='transfer and counterexample')
        assert result.get('status') == 'recommended', result

        revised = library.publish_technique(b'check procedure v2', title='check',
                                             origin='engagement:eng-c',
                                             author={'engagement_id': 'eng-c', 'worker_id': 'lead-c',
                                                     'session_id': 'ses-c'},
                                             source_case='case-c', applicability='local source')
        assert revised['version'] != version
        assert library.read(version)['content'] == 'check procedure v1'
        assert revised.get('status', 'experimental') == 'experimental'


if __name__ == '__main__':
    main()
