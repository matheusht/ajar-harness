"""Authenticated active knowledge delivery through the existing native boundary."""
from __future__ import annotations

import base64
from engagement_contract import canonical, digest, research_autonomy
from engagement_controller import fail
from engagement_knowledge import KnowledgeLibrary, MAX_BYTES, MAX_READ, _safe, evaluation_view, fetch_reference
from target_accounts import _route_origin


def source_case(accesses):
    """Case identity excludes resource aliases and ephemeral runtime identities."""
    rows = [{'kind': row['kind'], 'identity': row['identity']} for row in accesses]
    return digest(canonical(sorted(rows, key=lambda row: canonical(row))))


def _actor(state, worker):
    return {'engagement_id': state['engagement_id'], 'worker_id': worker['id'], 'session_id': worker['session_id']}


def _known_secrets(boundary):
    resolver = getattr(boundary, 'target_accounts', None)
    if resolver is None:
        return ()
    with resolver.lock:
        return tuple(resolver.secrets)


def _libraries(boundary):
    if not hasattr(boundary, '_knowledge_shared'):
        boundary._knowledge_shared = KnowledgeLibrary()
        boundary._knowledge_local = KnowledgeLibrary(boundary.controller.root / 'knowledge', corpus_root=None)
    return boundary._knowledge_shared, boundary._knowledge_local


def _reference_record(boundary, record):
    _safe(canonical(record), known_secrets=_known_secrets(boundary))
    try:
        boundary.controller.record_knowledge(boundary.context.grant, record)
    except OSError:
        if record.get('kind') != 'reference' or record.get('action') not in ('selected', 'delivery'):
            raise
        return False
    return True


def _journal_gap(record):
    record.update(journal_retention='not_retained',
        journal_limitation='This delivery record may not survive interruption; a later fetch is a new observation.')
    record['materialization'] = {'status': 'skipped', 'reason': 'knowledge_journal_unavailable'}
    return record


def _bounded_response(record):
    from engagement_native_boundary import _result
    from native_runtime_transport import MAX_FRAME

    # Match the native wrapper and reserve its normal transport-envelope headroom.
    while len(canonical(_result(record))) > MAX_FRAME // 2:
        record['response_truncated'] = True
        if record.get('evaluations'):
            record['evaluations'] = record['evaluations'][1:]
            record['evaluations_truncated'] = True
        elif record.get('matches'):
            record['matches'] = record['matches'][:-1]
            record['truncated'] = True
        elif isinstance(record.get('content'), str) and len(record['content']) > 1:
            record['content'] = record['content'][:len(record['content']) // 2]
            record.update(next_offset=record.get('offset', 0) + len(record['content']), complete=False)
        elif record.get('failures'):
            record['failures'] = record['failures'][:-1]
            record['failures_truncated'] = True
        else:
            return {key: record[key] for key in ('status', 'version', 'retention') if key in record} | {
                'response_truncated': True, 'response_status': 'metadata_unavailable'}
    return record


def _pin(source, destination, version):
    row, content, extraction = source._selected(version)
    helpers = {name: source._blob(item['sha256']) for name, item in row['helpers'].items()} if row['retention'] == 'retained' else source._unsaved_helpers.get(version, {})
    record = destination.retain(content, origin=row['origin'], title=row['title'], kind=row['kind'],
                                extraction=extraction, metadata=row['metadata'], helpers=helpers)
    current = source.status(version)
    if record['retention'] == 'retained' and current['evaluations']:
        try:
            with destination._lock():
                directory = destination.root / 'evaluations' / version[7:]
                directory.mkdir(mode=0o700, exist_ok=True)
                for index, event in enumerate(current['evaluations'], 1):
                    raw = canonical(event)
                    destination._put(directory / f'{index:012d}-{digest(raw)[7:]}.json', raw)
        except OSError:
            record['evaluation_retention'] = 'not_retained'
    if record['retention'] == 'retained' and record.get('evaluation_retention') != 'not_retained':
        current = destination.status(version)
    return dict(record, technique_status=current['status'], status_reason=current['reason'])


# Runs inside the existing owned environment. A complete digest is the readback.
_STAGE = '''import base64,hashlib,os,pathlib,stat,sys
p=pathlib.Path(sys.argv[1]); offset=int(sys.argv[2]); expected=sys.argv[3]; final=sys.argv[4]=='1'
root=pathlib.Path('/work')
if not p.is_absolute() or '..' in p.parts or root not in p.parents: raise ValueError('knowledge_path_invalid')
for parent in reversed(p.parents):
    if parent==root or root in parent.parents:
        if parent.is_symlink(): raise ValueError('knowledge_symlink')
        parent.mkdir(mode=0o700,exist_ok=True)
if p.is_symlink(): raise ValueError('knowledge_symlink')
if p.exists():
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as src: actual='sha256:'+hashlib.file_digest(src,'sha256').hexdigest()
    if actual!=expected: raise ValueError('knowledge_existing_file_changed')
    print(actual); sys.exit(0)
part=p.with_name(p.name+'.pending')
flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW
fd=os.open(part,flags,0o600)
try:
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise ValueError('knowledge_pending_file_invalid')
    if offset==0: os.ftruncate(fd,0)
    os.lseek(fd,offset,0)
    for encoded in sys.argv[5:]:
        raw=base64.b64decode(encoded,validate=True)
        with os.fdopen(os.dup(fd),'wb',closefd=True) as out: out.write(raw); out.flush()
    os.fsync(fd)
finally: os.close(fd)
if final:
    fd=os.open(part,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as src: actual='sha256:'+hashlib.file_digest(src,'sha256').hexdigest()
    if actual!=expected: raise ValueError('knowledge_digest_mismatch')
    os.replace(part,p)
    print(actual)
else: print('partial')
'''


def _materialize(boundary, library, version):
    row, content, extraction = library._selected(version)
    base = 'knowledge/' + version[7:]
    files = {'SKILL.md' if row['kind'] == 'technique' else 'reference.bin': content}
    if extraction is not None:
        files['extracted.txt'] = extraction
    for name, helper in row['helpers'].items():
        files[name] = (library._blob(helper['sha256']) if row['retention'] == 'retained'
                       else library._unsaved_helpers[version][name])
    paths = {}
    for name, raw in files.items():
        _safe(raw, known_secrets=_known_secrets(boundary))
        path = '/work/' + base + '/' + name
        # Bound argv and each argument below Linux's per-argument limit.
        for offset in range(0, max(1, len(raw)), 512 * 1024):
            chunk = raw[offset:offset + 512 * 1024]
            arguments = [base64.b64encode(chunk[i:i + 48 * 1024]).decode('ascii')
                         for i in range(0, len(chunk), 48 * 1024)]
            final = offset + len(chunk) >= len(raw)
            observed = boundary.environment.execute(['python3', '-I', '-S', '-c', _STAGE, path,
                str(offset), digest(raw), '1' if final else '0', *arguments], timeout_seconds=30)
            if observed['status'] != 'settled' or observed.get('returncode') != 0:
                return {'status': 'incomplete', 'paths': paths, 'reason': 'knowledge_materialization_failed'}
            if final and observed.get('output', '').strip() != digest(raw):
                return {'status': 'incomplete', 'paths': paths, 'reason': 'knowledge_materialization_unverified'}
        paths[name] = path
    return {'status': 'materialized', 'paths': paths}


def prepare_evaluation(c, state, worker, arguments):
    """Resolve fresh reviewer, exact subject, actual evidence and changed case."""
    review = state['reviews'].get(arguments.get('review_id'))
    if (review is None or review['kind'] != 'technique' or review['status'] != 'pending'
            or review['reviewer_id'] != worker['id'] or worker['role'] != 'reviewer'):
        fail('review_identity_invalid')
    version = review['subject_id']
    technique = state['techniques'][version]
    author = technique['metadata']['author']
    actor = _actor(state, worker)
    if (actor['session_id'] == author['session_id'] or
            (actor['engagement_id'], actor['worker_id']) == (author['engagement_id'], author['worker_id'])):
        fail('technique_independent_evaluator_required')
    events = c._events()
    requested = next((event['sequence'] for event in events if event['type'] == 'request_accepted'
        and event['payload']['type'] == 'review_request'
        and event['payload']['payload']['review_id'] == arguments['review_id']), None)
    if requested is None:
        fail('review_identity_invalid')
    status = arguments.get('status', 'recommended')
    if status not in ('recommended', 'experimental', 'narrowed', 'withdrawn'):
        fail('technique_status_invalid')
    groups, cases, evidence_kinds = {}, {}, {}
    for name in ('transfer_refs', 'counterexample_refs'):
        refs = arguments.get(name, [])
        if not isinstance(refs, list) or len(refs) > 64 or any(not isinstance(ref, str) for ref in refs):
            fail('technique_evidence_invalid')
        if status in ('recommended', 'narrowed') and not refs:
            fail('technique_checks_incomplete')
        groups[name] = refs
        for ref in refs:
            if ref in state['experiments']:
                row = state['experiments'][ref]
                if (row['session_id'] == author['session_id'] or
                        (state['engagement_id'], row['worker_id']) == (author['engagement_id'], author['worker_id'])):
                    fail('technique_independent_evidence_required')
                for key in ('receipt_sha256', 'execution_receipt_sha256', 'output_sha256'):
                    c.read_object(row[key])
                cases[ref] = source_case(row['input_identity'])
                evidence_kinds[ref] = 'protected_experiment'
            elif ref in state['publications']:
                row = state['publications'][ref]
                event = next((event for event in events if event['type'] == 'request_accepted'
                    and event['payload']['type'] == 'publish'
                    and event['payload']['payload']['publication_id'] == ref), None)
                if (row['author'] != worker['id'] or row['kind'] != 'observation' or not row['artifacts']
                        or event is None or event['sequence'] <= requested
                        or event['actor']['generation'] != worker['generation']):
                    fail('technique_decision_outcome_invalid')
                for artifact in row['artifacts']:
                    c.read_object(artifact['sha256'])
                case_inputs = [row for row in state['scope']['access'] if row['id'] in review['resources']]
                if not case_inputs:
                    fail('technique_case_unbound')
                cases[ref] = source_case(case_inputs)
                evidence_kinds[ref] = 'decision_outcome'
            else:
                fail('technique_evidence_missing')
    if not cases:
        fail('technique_evidence_missing')
    changed = [cases[ref] for ref in groups['transfer_refs'] if cases[ref] != technique['metadata']['source_case']]
    if status in ('recommended', 'narrowed'):
        if not changed:
            fail('technique_transfer_case_unchanged')
        if set(groups['transfer_refs']) == set(groups['counterexample_refs']):
            fail('technique_counterexample_distinct_outcome_required')
        if technique['helpers'] and any(not any(evidence_kinds[ref] == 'protected_experiment' for ref in refs)
                                        for refs in groups.values()):
            fail('technique_helper_execution_required')
    refs = list(dict.fromkeys(groups['transfer_refs'] + groups['counterexample_refs']))
    evidence = [state['engagement_id'] + ':' + ref for ref in refs]
    return version, {'evaluator': actor, 'transfer_case': changed[0] if changed else next(iter(cases.values())),
        'transfer': bool(groups['transfer_refs']) and status in ('recommended', 'narrowed'),
        'counterexample': bool(groups['counterexample_refs']) and status in ('recommended', 'narrowed'),
        'evidence_refs': evidence, 'applicability': arguments.get('applicability', ''),
        'reason': arguments.get('reason', ''), 'status': status}


def _read(boundary, shared, local, version, arguments, *, call_id=None):
    try:
        local._selected(version)
    except (OSError, ValueError) as error:
        if not isinstance(error, OSError) and str(error) not in ('reference_unavailable', 'file_unavailable'):
            raise
        try:
            _pin(shared, local, version)
        except ValueError as error:
            if str(error) != 'reference_unavailable':
                raise
            return shared.read(version, offset=arguments.get('offset', 0), limit=arguments.get('limit', MAX_READ), file=arguments.get('file'))
    record = local.read(version, offset=arguments.get('offset', 0), limit=arguments.get('limit', MAX_READ), file=arguments.get('file'))
    # Current recommendation may change, but selected source bytes never do.
    try:
        current = shared.status(version)
        if current['evaluations']:
            pinned = _pin(shared, local, version)
            if pinned.get('evaluation_retention') == 'not_retained':
                record['evaluation_retention'] = 'not_retained'
            else:
                current = local.status(version)
            record.update(technique_status=current['status'], status_reason=current['reason'],
                          applicability=current['applicability'], **evaluation_view(current))
    except (OSError, ValueError) as error:
        if not isinstance(error, OSError) and str(error) not in ('reference_unavailable', 'file_unavailable'):
            raise
        record['recommendation_refresh'] = 'unavailable'
    selected = {key: value for key, value in record.items() if key not in ('content', 'evaluations')}
    selected.update(action='selected', call_id=call_id)
    _safe(canonical(record), known_secrets=_known_secrets(boundary))
    if not _reference_record(boundary, selected):
        return _journal_gap(record)
    binary = record.get('reason') == 'text_extraction_required'
    if record['status'] != 'available' and not binary:
        return record
    if arguments.get('materialize', True):
        delivery = _materialize(boundary, local, version)
        record['materialization'] = delivery
        if binary and delivery['status'] == 'materialized':
            record.update(status='available', text_status='unavailable', reason='text_extraction_required')
    else:
        delivery = {'status': 'text_only'}
    record = _bounded_response(record)
    delivered = {key: value for key, value in record.items() if key not in ('content', 'evaluations')}
    delivered.update(kind=selected.get('kind'), action='delivery', call_id=call_id, materialization=delivery)
    if not _reference_record(boundary, delivered):
        _journal_gap(record)
        record['materialization'] = delivery
    return record


def handle(boundary, arguments):
    return _bounded_response(_handle(boundary, arguments))


def _handle(boundary, arguments):
    """Boundary calls this after authenticating the host tool request."""
    c, context = boundary.controller, boundary.context
    context.authorize()
    _safe(canonical(arguments), known_secrets=_known_secrets(boundary))
    state = c.state()
    if not research_autonomy(state['scope']):
        fail('knowledge_policy_required')
    worker = c._worker(state, context.principal)
    shared, local = _libraries(boundary)
    action = arguments.get('action')
    if action == 'search':
        result = shared.search(arguments.get('query', ''), limit=arguments.get('limit', 20))
        _safe(canonical(result), known_secrets=_known_secrets(boundary))
        return result
    if action == 'read':
        return _read(boundary, shared, local, arguments['version'], arguments)
    if action == 'fetch':
        call_id = arguments.get('_delivery_id')
        if not isinstance(call_id, str) or not call_id:
            fail('knowledge_call_identity_required')
        request_sha256 = digest(canonical({key: value for key, value in arguments.items() if key != '_delivery_id'}))
        prior = next((row for row in state.get('knowledge_deliveries', [])
                      if row.get('call_id') == call_id and row.get('action') == 'selected'), None)
        if prior:
            if prior.get('request_sha256') != request_sha256:
                fail('knowledge_request_conflict')
            try:
                local._selected(prior['version'])
            except (OSError, ValueError):
                return {'status': 'unavailable', 'reason': 'selected_reference_not_retained',
                        'version': prior['version'], 'retention': 'not_retained'}
            return _read(boundary, shared, local, prior['version'], arguments, call_id=call_id)
        grant = state['scope'].get('reference_web')
        if grant is None:
            fail('reference_web_not_granted')
        known_secrets = _known_secrets(boundary)
        fetched = fetch_reference(arguments['url'], grant=grant, known_secrets=known_secrets,
            authorize=lambda: bool(context.authorize()), dispatch_guard=context.guard,
            forbidden_origins={_route_origin(row) for group in ('target', 'provider') for row in state['scope']['network'][group]})
        _safe(fetched['content'], known_secrets=known_secrets)
        record = shared.retain(fetched['content'], origin=fetched['origin'], title=arguments.get('title') or fetched['origin'][:512],
            metadata={'content_type': fetched['content_type'], 'requested_origin': fetched['requested_origin']})
        pinned = _pin(shared, local, record['version'])
        if not _reference_record(boundary, dict(pinned, action='selected', call_id=call_id, request_sha256=request_sha256)):
            readable = local.read(record['version'], offset=arguments.get('offset', 0), limit=arguments.get('limit', MAX_READ), file=arguments.get('file'))
            return _journal_gap(readable)
        return _read(boundary, shared, local, record['version'], arguments, call_id=call_id)
    if action == 'publish':
        paths = arguments.get('helpers', [])
        if (not isinstance(paths, list) or len(paths) > 32 or any(not isinstance(path, str) or not 1 <= len(path) <= 256 for path in paths)
                or len(set(paths)) != len(paths)):
            fail('technique_helpers_invalid')
        content = boundary.environment.read_artifact(arguments['path'], min(MAX_BYTES, boundary.environment.limits['output_bytes'], 16 * 1024 * 1024))['content']
        _safe(content, known_secrets=_known_secrets(boundary))
        helpers = {}
        for path in paths:
            helpers[path] = boundary.environment.read_artifact(path, min(MAX_BYTES, boundary.environment.limits['output_bytes'], 16 * 1024 * 1024))['content']
            _safe(helpers[path], known_secrets=_known_secrets(boundary))
        inputs = [row for row in state['scope']['access'] if row['id'] in context.grant['resources']]
        if not inputs:
            fail('technique_case_unbound')
        record = shared.publish_technique(content, title=arguments['title'], origin='engagement:' + state['engagement_id'],
            author=_actor(state, worker), source_case=source_case(inputs), applicability=arguments.get('applicability', ''), helpers=helpers)
        pinned = _pin(shared, local, record['version'])
        c.record_knowledge(context.grant, dict(pinned, action='published'))
        return pinned
    if action == 'evaluate':
        with context.guard():
            state = c.state()
            worker = c._worker(state, context.principal)
            version, evaluation = prepare_evaluation(c, state, worker, arguments)
            # Recovery can evaluate a locally retained package after shared storage loss.
            _pin(local, shared, version)
            event = shared.evaluate(version, **evaluation)
            pinned = _pin(shared, local, version)
            if pinned['retention'] != 'retained' or pinned.get('evaluation_retention') == 'not_retained':
                fail('technique_evaluation_retention_required')
            c.record_technique_evaluation(context.grant, arguments['review_id'], event)
            return event
    fail('knowledge_action_invalid')


def export_files(c, state):
    """Export journal-selected local files; never enumerate the shared library."""
    from engagement_contract import read_bytes
    library = KnowledgeLibrary(c.root / 'knowledge', corpus_root=None)
    files = {}
    deliveries = state.get('knowledge_deliveries', [])
    gaps = [row for row in deliveries if row.get('retention') == 'not_retained'
            or row.get('evaluation_retention') == 'not_retained']
    versions = {row['version'] for row in deliveries if row.get('version')}
    versions.update(state.get('techniques', {}))
    for version in sorted(versions):
        try:
            row, content, extraction = library._selected(version)
            selected = {'knowledge/files/' + row['sha256'][7:]: content,
                'knowledge/versions/' + version[7:] + '.json': canonical({key: value for key, value in row.items() if key != 'retention'})}
            if extraction is not None:
                selected['knowledge/files/' + row['extraction_sha256'][7:]] = extraction
            for helper in row['helpers'].values():
                selected['knowledge/files/' + helper['sha256'][7:]] = library._blob(helper['sha256'])
            library.status(version)
            for path in sorted((library.root / 'evaluations' / version[7:]).glob('*.json')):
                selected['knowledge/evaluations/' + version[7:] + '/' + path.name] = read_bytes(path, private=True)
            files.update(selected)
        except (OSError, ValueError) as error:
            gaps.append({'version': version, 'retention': 'unavailable', 'reason': str(error)})
    if versions or deliveries:
        files['knowledge/manifest.json'] = canonical({'kind': 'engagement-knowledge-archive-v1',
            'files': {name: digest(content) for name, content in files.items()},
            'retention_gaps': gaps, 'deliveries': deliveries})
    return files
