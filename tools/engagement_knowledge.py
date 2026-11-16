"""Host-owned immutable references and experimental techniques.

Authority, actor identity and evaluation evidence are checked by the engagement
controller. This file owns bytes and their derived catalog, not research policy.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import unquote_plus, unquote_to_bytes, urljoin, urlsplit

from engagement_contract import ContractError, canonical, digest, read_bytes, safe_publication
from engagement_controller import ControllerError, publish_file, private_directory

MAX_BYTES = 64 * 1024 * 1024
MAX_READ = 64 * 1024
MAX_METADATA = 32 * 1024
DEFAULT_ROOT = Path.home() / '.oslit' / 'knowledge'
DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / 'skills/oracles/references'
CORPUS_FILES = ('CONTENTS.md', 'ghsa-fix-diff-corpus.md',
                'rejected-disputed-cve-corpus.md', 'project-zero-zdi-chain-corpus.md')
SHA = re.compile(r'sha256:[0-9a-f]{64}\Z')


def _safe(content, *, known_secrets=()):
    if type(content) is not bytes or len(content) > MAX_BYTES:
        raise ValueError('reference_size_limit')
    # Scanner windows overlap so a credential spanning a window is still inspected.
    overlap = max(4096, max((len(value) - 1 for value in known_secrets), default=0))
    for offset in range(0, max(1, len(content)), 4 * 1024 * 1024):
        safe_publication(content[max(0, offset - overlap):offset + 4 * 1024 * 1024], known_secrets=known_secrets)
    return content


def _identity(value):
    if (not isinstance(value, dict) or set(value) != {'engagement_id', 'worker_id', 'session_id'}
            or any(not isinstance(item, str) or not 1 <= len(item) <= 1024 for item in value.values())):
        raise ValueError('technique_identity_invalid')
    safe_publication(canonical(value))
    return dict(value)


def _record(content, origin, title, kind, extraction, metadata, helpers=None):
    if (not isinstance(origin, str) or not 1 <= len(origin) <= 8192
            or not isinstance(title, str) or not 1 <= len(title) <= 512
            or kind not in ('reference', 'technique')):
        raise ValueError('reference_metadata_invalid')
    _safe(content)
    if extraction is not None:
        _safe(extraction)
    helper_records = {}
    if helpers is not None and (not isinstance(helpers, dict) or len(helpers) > 32):
        raise ValueError('technique_helpers_invalid')
    if not isinstance(metadata or {}, dict) or len(canonical(metadata or {})) > MAX_METADATA:
        raise ValueError('reference_metadata_invalid')
    for name, raw in (helpers or {}).items():
        if not isinstance(name, str) or not 1 <= len(name) <= 256:
            raise ValueError('technique_helper_path_invalid')
        path = Path(name)
        if (path.is_absolute() or not path.parts or '..' in path.parts or path.parts[0] == '__knowledge__'
                or str(path) != name or name in ('.', 'SKILL.md')):
            raise ValueError('technique_helper_path_invalid')
        _safe(raw)
        helper_records[name] = {'sha256': digest(raw), 'size': len(raw)}
    document = {'kind': kind, 'origin': origin, 'title': title, 'sha256': digest(content),
                'size': len(content), 'extraction_sha256': digest(extraction) if extraction is not None else None,
                'metadata': metadata or {}, 'helpers': helper_records}
    safe_publication(canonical(document))
    return dict(document, version=digest(canonical(document)))


def evaluation_view(current):
    evaluations = current['evaluations']
    return {'evaluations': evaluations[-10:], 'evaluations_total': len(evaluations),
            'evaluations_truncated': len(evaluations) > 10,
            'evaluation_history': {'file_pattern': '__knowledge__/evaluation-{index}.json',
                                   'first_index': 1, 'total': len(evaluations)}}


class KnowledgeLibrary:
    def __init__(self, root=DEFAULT_ROOT, corpus_root=DEFAULT_CORPUS):
        self.root = Path(root).absolute()
        self.corpus_root = Path(corpus_root).absolute() if corpus_root is not None else None
        self._unsaved = {}
        self._unsaved_helpers = {}
        self._gaps = []

    @contextmanager
    def _lock(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        private_directory(self.root)
        descriptor = os.open(self.root / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            for name in ('files', 'versions', 'evaluations'):
                directory = self.root / name
                directory.mkdir(mode=0o700, exist_ok=True)
                private_directory(directory)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _put(self, path, content):
        if path.exists():
            if read_bytes(path, private=True, max_bytes=MAX_BYTES) != content:
                raise ValueError('reference_corrupt')
        else:
            publish_file(path, content)

    def retain(self, content, *, origin, title, kind='reference', extraction=None, metadata=None, helpers=None):
        record = _record(content, origin, title, kind, extraction, metadata, helpers)
        try:
            with self._lock():
                self._put(self.root / 'files' / record['sha256'][7:], content)
                if extraction is not None:
                    self._put(self.root / 'files' / record['extraction_sha256'][7:], extraction)
                for name, raw in (helpers or {}).items():
                    self._put(self.root / 'files' / record['helpers'][name]['sha256'][7:], raw)
                self._put(self.root / 'versions' / (record['version'][7:] + '.json'), canonical(record))
        except (OSError, ControllerError):
            record = dict(record, retention='not_retained', retention_error='reference_storage_unavailable')
            self._unsaved[record['version']] = (record, content, extraction)
            self._unsaved_helpers[record['version']] = dict(helpers or {})
            self._gaps.append(record)
            return record
        return dict(record, retention='retained', status='experimental' if kind == 'technique' else 'reference')

    def _catalog(self):
        records, failures = {}, []
        available = False
        try:
            if self.root.is_dir():
                private_directory(self.root)
                available = True
                for path in sorted((self.root / 'versions').glob('*.json')):
                    try:
                        row = json.loads(read_bytes(path, private=True))
                        if not isinstance(row, dict) or set(row) != {'kind', 'origin', 'title', 'sha256', 'size', 'extraction_sha256', 'metadata', 'helpers', 'version'}:
                            raise ValueError('reference_corrupt')
                        version = row.pop('version')
                        if digest(canonical(row)) != version or path.stem != version[7:]:
                            raise ValueError('reference_corrupt')
                        row['version'] = version
                        records[version] = dict(row, retention='retained')
                    except (OSError, ValueError, KeyError) as error:
                        failures.append({'source': path.name, 'reason': str(error)})
            elif self.root.exists():
                failures.append({'source': 'library', 'reason': 'library_unavailable'})
        except (OSError, ValueError):
            failures.append({'source': 'library', 'reason': 'library_unavailable'})
        if self.corpus_root is not None:
            for name in CORPUS_FILES:
                try:
                    content = read_bytes(self.corpus_root / name, max_bytes=MAX_BYTES)
                    row = _record(content, 'repository:skills/oracles/references/' + name, name,
                                  'reference', None, {'historical': True, 'primary_sources_retained': False})
                    available = True
                    records.setdefault(row['version'], dict(row, retention='not_retained',
                                                            _corpus_path=str(self.corpus_root / name)))
                except (OSError, ValueError) as error:
                    failures.append({'source': name, 'reason': str(error)})
        for version, (record, _, _) in self._unsaved.items():
            records.setdefault(version, record)
        return records, failures, available or bool(records)

    def _blob(self, sha):
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError('reference_identity_invalid')
        content = read_bytes(self.root / 'files' / sha[7:], private=True, max_bytes=MAX_BYTES)
        if digest(content) != sha:
            raise ValueError('reference_corrupt')
        return _safe(content)

    def _selected(self, version):
        if not isinstance(version, str) or not SHA.fullmatch(version):
            raise ValueError('reference_identity_invalid')
        records, _, _ = self._catalog()
        if version not in records:
            raise ValueError('reference_unavailable')
        row = records[version]
        if '_corpus_path' in row:
            content = read_bytes(Path(row['_corpus_path']), max_bytes=MAX_BYTES)
            if digest(content) != row['sha256']:
                raise ValueError('reference_changed')
            return row, _safe(content), None
        if row['retention'] == 'not_retained':
            return self._unsaved[version]
        return row, self._blob(row['sha256']), self._blob(row['extraction_sha256']) if row['extraction_sha256'] else None

    def status(self, version):
        row, _, _ = self._selected(version)
        status = 'experimental' if row['kind'] == 'technique' else 'reference'
        evaluations = []
        for sequence, path in enumerate(sorted((self.root / 'evaluations' / version[7:]).glob('*.json')), 1):
            event = json.loads(read_bytes(path, private=True))
            if (not isinstance(event, dict) or not path.name.startswith(f'{sequence:012d}-') or event.get('version') != version
                    or digest(canonical(event)) != 'sha256:' + path.stem.split('-', 1)[1]):
                raise ValueError('technique_evaluation_corrupt')
            evaluations.append(event)
            status = event['status']
        return {'status': status, 'evaluations': evaluations,
                'reason': evaluations[-1]['reason'] if evaluations else None,
                'applicability': evaluations[-1]['applicability'] if evaluations else row['metadata'].get('applicability', '')}

    def read(self, version, *, offset=0, limit=MAX_READ, file=None):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_READ:
            raise ValueError('reference_read_bounds_invalid')
        try:
            row, original, extraction = self._selected(version)
            if row['retention'] != 'retained':
                row = self.retain(original, origin=row['origin'], title=row['title'], kind=row['kind'],
                                  extraction=extraction, metadata=row['metadata'],
                                  helpers=self._unsaved_helpers.get(version))
            selected = extraction if extraction is not None else original
            current = self.status(version)
            representation = 'extraction' if extraction is not None else 'original'
            if file is not None:
                history = re.fullmatch(r'__knowledge__/evaluation-([1-9][0-9]*)\.json', file)
                if history:
                    index = int(history[1]) - 1
                    if index >= len(current['evaluations']):
                        raise ValueError('technique_evaluation_unavailable')
                    selected = canonical(current['evaluations'][index])
                    representation = 'evaluation'
                elif file not in row['helpers']:
                    raise ValueError('technique_helper_unavailable')
                else:
                    selected = (self._unsaved_helpers[version][file] if row['retention'] != 'retained'
                                else self._blob(row['helpers'][file]['sha256']))
                    representation = 'helper'
            try:
                text = selected.decode('utf-8')
            except UnicodeError:
                return {**row, 'status': 'unavailable', 'reason': 'text_extraction_required', 'content': None}
            # Offsets are characters; the complete original bytes retain their separate digest.
            end = min(len(text), offset + limit)
            return {**row, 'status': 'available', 'technique_status': current['status'],
                    **evaluation_view(current), 'status_reason': current['reason'],
                    'applicability': current['applicability'], 'content': text[offset:end],
                    'offset': offset, 'next_offset': end if end < len(text) else None,
                    'complete': end >= len(text), 'representation': representation,
                    'file': file, 'selected_sha256': digest(selected),
                    'extraction_complete': row['metadata'].get('extraction_complete') if extraction is not None else True}
        except (OSError, ValueError) as error:
            if isinstance(error, ContractError) and error.code == 'publication_secret':
                raise
            return {'status': 'unavailable', 'version': version, 'reason': str(error), 'content': None}

    def search(self, query, limit=20):
        if not isinstance(query, str) or len(query) > 4096 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('reference_query_invalid')
        records, failures, available = self._catalog()
        matches = []
        words = query.casefold().split()
        for version, row in records.items():
            try:
                _, original, extraction = self._selected(version)
                text = (extraction if extraction is not None else original).decode('utf-8')
                haystack = (row['title'] + '\n' + text).casefold()
                if not all(word in haystack for word in words):
                    continue
                position = min((text.casefold().find(word) for word in words if word in text.casefold()), default=0)
                current = self.status(version)
                matches.append({**{k: v for k, v in row.items() if not k.startswith('_')},
                                'status': current['status'], 'status_reason': current['reason'],
                                'applicability': current['applicability'],
                                'snippet': text[max(0, position - 160):position + 640],
                                'compatibility': 'not_assessed'})
            except (OSError, ValueError) as error:
                failures.append({'version': version, 'reason': str(error)})
        selected, size = [], 0
        for match in matches[:limit]:
            amount = len(canonical(match))
            if size + amount > 384 * 1024:
                break
            selected.append(match)
            size += amount
        return {'status': 'partial' if available and failures else 'available' if available else 'unavailable',
                'matches': selected, 'truncated': len(matches) > len(selected), 'matches_total': len(matches),
                'failures': failures[:100], 'failures_total': len(failures), 'failures_truncated': len(failures) > 100}

    def publish_technique(self, content, *, title, origin, author, source_case, applicability='', helpers=None):
        if (not isinstance(source_case, str) or not 1 <= len(source_case) <= 8192
                or not isinstance(applicability, str) or len(applicability) > 8192):
            raise ValueError('technique_case_invalid')
        return self.retain(content, origin=origin, title=title, kind='technique',
                           metadata={'author': _identity(author), 'source_case': source_case, 'applicability': applicability},
                           helpers=helpers)

    def evaluate(self, version, *, evaluator, transfer_case, transfer, counterexample,
                 evidence_refs, applicability, reason, status=None):
        row, _, _ = self._selected(version)
        evaluator = _identity(evaluator)
        if row['kind'] != 'technique' or row['retention'] != 'retained':
            raise ValueError('technique_retained_version_required')
        for helper in row['helpers'].values():
            self._blob(helper['sha256'])
        author = row['metadata']['author']
        if (evaluator['session_id'] == author['session_id'] or
                (evaluator['engagement_id'], evaluator['worker_id']) == (author['engagement_id'], author['worker_id'])):
            raise ValueError('technique_independent_evaluator_required')
        if (not isinstance(transfer_case, str) or not 1 <= len(transfer_case) <= 8192
                or type(transfer) is not bool or type(counterexample) is not bool
                or not isinstance(evidence_refs, list) or not 1 <= len(evidence_refs) <= 128
                or any(not isinstance(ref, str) or not 1 <= len(ref) <= 512 for ref in evidence_refs)
                or not isinstance(reason, str) or not 1 <= len(reason) <= 8192
                or not isinstance(applicability, str) or len(applicability) > 8192):
            raise ValueError('technique_evaluation_invalid')
        status = status or ('recommended' if transfer and counterexample else 'experimental')
        if status not in ('recommended', 'experimental', 'narrowed', 'withdrawn'):
            raise ValueError('technique_status_invalid')
        if status in ('recommended', 'narrowed') and (not transfer or not counterexample or not applicability):
            raise ValueError('technique_checks_incomplete')
        if status in ('recommended', 'narrowed') and transfer_case == row['metadata']['source_case']:
            raise ValueError('technique_transfer_case_unchanged')
        prior = self.status(version)
        event = {'version': version, 'evaluator': evaluator, 'transfer_case': transfer_case,
                 'transfer': transfer, 'counterexample': counterexample, 'evidence_refs': evidence_refs,
                 'applicability': applicability, 'reason': reason, 'status': status}
        if event in prior['evaluations']:
            return event
        declared = row['metadata'].get('applicability', '')
        if status == 'recommended' and declared and applicability != declared and prior['status'] == 'experimental':
            raise ValueError('technique_changed_claim_requires_new_version')
        if (status == 'recommended' and prior['status'] in ('recommended', 'narrowed')
                and applicability != prior['applicability']):
            raise ValueError('technique_changed_claim_requires_new_version')
        if status == 'narrowed' and (prior['status'] not in ('recommended', 'narrowed') or applicability == prior['applicability']):
            raise ValueError('technique_narrowing_required')
        raw = safe_publication(canonical(event))
        if len(raw) > MAX_METADATA:
            raise ValueError('technique_evaluation_metadata_limit')
        with self._lock():
            directory = self.root / 'evaluations' / version[7:]
            directory.mkdir(mode=0o700, exist_ok=True)
            private_directory(directory)
            if not any(path.name.endswith(digest(raw)[7:] + '.json') for path in directory.glob('*.json')):
                sequence = len(list(directory.glob('*.json'))) + 1
                publish_file(directory / f'{sequence:012d}-{digest(raw)[7:]}.json', raw)
        return event

    def export(self, output):
        output = Path(output).absolute()
        if output.exists() or output.is_symlink():
            raise ValueError('knowledge_export_exists')
        output.mkdir(mode=0o700, parents=True)
        files, gaps = {}, list(self._gaps)
        records, failures, _ = self._catalog()
        for version, row in records.items():
            if row['retention'] != 'retained':
                continue
            try:
                _, content, extraction = self._selected(version)
                selected = {'files/' + row['sha256'][7:]: content,
                            'versions/' + version[7:] + '.json': canonical({k: v for k, v in row.items() if k != 'retention'})}
                if extraction is not None:
                    selected['files/' + row['extraction_sha256'][7:]] = extraction
                for helper in row['helpers'].values():
                    selected['files/' + helper['sha256'][7:]] = self._blob(helper['sha256'])
                self.status(version)
                for path in sorted((self.root / 'evaluations' / version[7:]).glob('*.json')):
                    selected['evaluations/' + version[7:] + '/' + path.name] = read_bytes(path, private=True)
                for name, raw in selected.items():
                    if name in files:
                        continue
                    destination = output / name
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    publish_file(destination, raw)
                    files[name] = digest(raw)
            except (OSError, ValueError) as error:
                gaps.append({'version': version, 'retention': 'unavailable', 'reason': str(error)})
        manifest = {'kind': 'knowledge-archive-v1', 'files': files, 'retention_gaps': gaps,
                    'catalog_failures': failures}
        publish_file(output / 'manifest.json', canonical(manifest))
        return manifest


def fetch_reference(url, *, grant, authorize, dispatch_guard, forbidden_origins=(), known_secrets=()):
    """Credential-free public GET under the caller's signed reference-web grant."""
    from engagement_network import NetworkGate, NetworkDenied
    if (not isinstance(grant, dict) or grant.get('public_sources') is not True
            or type(grant.get('max_bytes')) is not int or not 1 <= grant['max_bytes'] <= MAX_BYTES
            or type(grant.get('timeout_seconds')) not in (int, float) or not 0 < grant['timeout_seconds'] <= 300):
        raise ValueError('reference_web_grant_invalid')
    def safe_url(target):
        if not isinstance(target, str) or not 1 <= len(target) <= 8192:
            raise ValueError('reference_url_invalid')
        for view in (target.encode('utf-8'), unquote_to_bytes(target), unquote_plus(target).encode('utf-8')):
            _safe(view, known_secrets=known_secrets)

    safe_url(url)
    deadline = time.monotonic() + grant['timeout_seconds']

    class PublicReferences(NetworkGate):
        def _destination(self, target):
            safe_url(target)
            parsed = urlsplit(target)
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            host = parsed.hostname
            rendered_host = f'[{host}]' if host and ':' in host else host
            origin = f'{parsed.scheme}://{rendered_host}:{port}'
            if origin in forbidden_origins:
                raise NetworkDenied('reference_target_or_provider_forbidden')
            self.routes = [{'protocol': parsed.scheme, 'host': host, 'port': port,
                            'address_policy': {'public_only': True, 'cidrs': []}}]
            return super()._destination(target)

    gate = PublicReferences([], lambda: time.monotonic() < deadline and authorize() is True,
                            maximum_bytes=grant['max_bytes'], dispatch_guard=dispatch_guard)
    requested = url
    try:
        for attempt in range(6):
            with gate._exchange(url, 'GET', {}, (), 0) as (response, _, _, _, binding):
                length, no_body = gate._response_shape(response, 'GET')
                payload = b''.join(gate._payload(response, length, no_body, limit=grant['max_bytes'], binding=binding))
                location = response.getheader('Location')
                if response.status in (301, 302, 303, 307, 308) and location:
                    if attempt == 5:
                        raise NetworkDenied('network_redirect_limit')
                    url = urljoin(url, location)
                    continue
                if not 200 <= response.status < 300:
                    raise ValueError('reference_source_unavailable')
                _safe(payload, known_secrets=known_secrets)
                content_type = response.getheader('Content-Type', 'application/octet-stream')
                _safe(content_type.encode('utf-8'), known_secrets=known_secrets)
                if len(content_type) > 1024:
                    raise ValueError('reference_content_type_invalid')
                return {'content': payload, 'origin': url, 'requested_origin': requested,
                        'content_type': content_type,
                        'sha256': digest(payload)}
    finally:
        gate.close()
