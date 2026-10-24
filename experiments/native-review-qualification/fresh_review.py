"""Freeze observer-selected evidence and invoke one fresh native reviewer.

The caller owns the presealed reviewer, protected observer and shared allowance.
This module performs no target, provider, container, filing or external action by itself.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat


ROLES = ('claim', 'conditions', 'source', 'raw', 'contrary', 'unfinished')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
IDENTIFIER = re.compile(r'ses_[A-Za-z0-9]{1,64}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
DECISIONS = {'raise', 'narrow', 'reject', 'retain', 'reopen', 'unfinished'}
OUTCOME_KEYS = {'input_id', 'decision', 'checked_link', 'valid_base',
                'missing_transitions', 'contrary', 'lead_dispositions', 'limits', 'next_check'}
LEAD_KEYS = {'basis_examined', 'uncertain_condition', 'next_check', 'decision'}
SENSITIVE = re.compile(
    r'(?i)(?:/Users/|/private/tmp/|file://|'
    r'\b(?:authorization|proxy-authorization|set-cookie|cookie)\s*[:=]|'
    r'\b(?:bearer|basic)\s+[A-Za-z0-9+/._=-]+|'
    r'\b(?:password|api[_-]?key|access[_-]?token|secret)\s*[:=]|'
    r'\blocal_[0-9a-f]{32}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
    r'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|'
    r'[?&](?:X-Amz-Signature|X-Goog-Signature|sig(?:nature)?|token|'
    r'access[_-]?token|api[_-]?key)=)')


def validate_public_bytes(data):
    """Conservative packet/output gate; the observer still owns full redaction."""
    if not isinstance(data, bytes) or not 0 < len(data) <= 4 * 1024 * 1024:
        raise ValueError('review_public_bytes_invalid')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('review_public_bytes_encoding') from None
    if SENSITIVE.search(text):
        raise ValueError('review_public_bytes_sensitive')
    return data


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_manifest_key')
        result[key] = value
    return result


def _selection(observer_root, selection_path, selected_sha256, public_bytes):
    root, manifest = Path(observer_root), Path(selection_path)
    if (root.is_symlink() or not root.is_dir() or manifest.is_symlink()
            or not manifest.is_file() or not SHA256.fullmatch(selected_sha256)):
        raise ValueError('observer_selection_invalid')
    raw = manifest.read_bytes()
    if _sha(raw) != selected_sha256:
        raise ValueError('observer_selection_changed')
    selected = json.loads(raw, object_pairs_hook=_unique_pairs)
    if (not isinstance(selected, dict)
            or set(selected) != {'claim_id', 'claim_version', 'source_manifest_sha256',
                                 'source_paths', 'roles', 'files'}
            or not isinstance(selected['source_manifest_sha256'], str)
            or not SHA256.fullmatch(selected['source_manifest_sha256'])):
        raise ValueError('observer_selection_shape')
    if any(not isinstance(selected[key], str) or not 1 <= len(selected[key]) <= 128
           or any(ord(char) < 32 for char in selected[key])
           for key in ('claim_id', 'claim_version')):
        raise ValueError('claim_identity_invalid')
    roles, expected = selected['roles'], selected['files']
    if (not isinstance(roles, dict) or set(roles) != set(ROLES)
            or not isinstance(expected, dict) or not expected):
        raise ValueError('observer_roles_invalid')
    names = []
    for role in ROLES:
        values = roles[role]
        if not isinstance(values, list) or not values or any(
                not isinstance(name, str) or not NAME.fullmatch(name) for name in values):
            raise ValueError('observer_role_files_invalid')
        names.extend(values)
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise ValueError('observer_file_roles_mismatch')
    source_paths = selected['source_paths']
    if (not isinstance(source_paths, dict) or set(source_paths) != set(roles['source'])
            or any(not isinstance(path, str) or not path or path.startswith('/')
                   or '\\' in path or any(part in ('', '.', '..') for part in path.split('/'))
                   for path in source_paths.values())
            or len(source_paths) != len(set(source_paths.values()))):
        raise ValueError('observer_source_paths_invalid')
    if (any(not NAME.fullmatch(name) or name in {'REQUEST.json', 'PROMPT.txt'}
            or not isinstance(digest, str) or not SHA256.fullmatch(digest)
            for name, digest in expected.items())
            or {item.name for item in root.iterdir()} != set(expected)):
        raise ValueError('observer_inventory_invalid')
    files = {}
    for name, digest in expected.items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('observer_file_invalid')
        data = path.read_bytes()
        if _sha(data) != digest or public_bytes(data) != data:
            raise ValueError('observer_file_changed_or_unsafe')
        files[name] = data
    return selected, files


def _prompt(request):
    return (f"Review exact input {request['input_id']} in this fresh context.\n"
        "Read /handoff/REQUEST.json and every listed file with your own native tools; verify their SHA256.\n"
        "REQUEST.json maps the relevant flat source subset to original relative paths in "
        "source_paths. The pinned full original source is read-only at /workspace/original; "
        "inspect additional paths there when needed. "
        "Read these roles without skipping failed or contrary observations: "
        + ', '.join(role + '=' + ','.join(request['roles'][role]) for role in ROLES) + '.\n'
        "Read /workspace/project/target.json for your presealed clean original reviewer target. "
        "Check a material causal link there with an executable native tool action under the "
        "original authorized conditions. Record command, output, effect, and a control. Do not "
        "edit original source to create proof, or use the researcher's mutable target, a host "
        "replay, candidate edit, or role label as "
        "original target proof.\n"
        "Examine each proposed strong-lead dismissal against its concrete basis and uncertain "
        "trust condition. Preserve supported partial bases, missing transitions, contrary results "
        "and useful next checks. A stop or missing check leaves the lead unfinished.\n"
        "Return one JSON object only, with input_id, decision (raise/narrow/reject/retain/reopen/"
        "unfinished), checked_link, valid_base, missing_transitions, contrary, lead_dispositions, "
        "limits, and next_check. Each lead disposition must name its basis_examined, "
        "uncertain_condition, next_check and decision. Do not claim filing, escalation or external "
        "action authority. Report any help, missing tools or unavailable cost.\n")


def prepare_packet(observer_root, selection_path, selected_sha256, packet_dir, *, public_bytes):
    """Copy one independent observer selection into the already sealed /handoff root."""
    selected, files = _selection(observer_root, selection_path, selected_sha256, public_bytes)
    packet = Path(packet_dir)
    if packet.is_symlink() or not packet.is_dir() or list(packet.iterdir()):
        raise ValueError('handoff_root_not_empty_or_fixed')
    identity = (packet.stat().st_dev, packet.stat().st_ino)
    roles = selected['roles']
    source = {selected['source_paths'][name]: selected['files'][name] for name in roles['source']}
    conditions = {name: selected['files'][name] for name in roles['conditions']}
    evidence = {name: selected['files'][name] for role in ('claim', 'raw', 'contrary', 'unfinished')
                for name in roles[role]}
    input_id = _sha(_json(selected))
    request = {'version': 1, 'claim_id': selected['claim_id'],
               'claim_version': selected['claim_version'], 'input_id': input_id,
               'selection_sha256': selected_sha256,
               'source_manifest_sha256': selected['source_manifest_sha256'],
               'roles': roles, 'files': selected['files'], 'source_paths': selected['source_paths'],
               'source_revision': _sha(_json({'source': source, 'conditions': conditions})),
               'evidence_revision': _sha(_json(evidence)),
               'previous_review': None, 'review_status': 'not_run',
               'authority': 'internal review only; no filing, escalation or external action'}
    files = dict(files, **{'REQUEST.json': _json(request), 'PROMPT.txt': _prompt(request).encode()})
    if any(public_bytes(data) != data for data in files.values()):
        raise ValueError('review_packet_unsafe')
    pin = {'dev': identity[0], 'ino': identity[1], 'input_id': input_id,
           'files': {name: _sha(data) for name, data in files.items()}}
    for name, data in files.items():
        fd = os.open(packet / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        (packet / name).chmod(0o444)
    packet.chmod(0o555)
    if not verify_packet(packet, pin):
        raise RuntimeError('review_packet_changed_during_freeze')
    return pin


def verify_packet(packet_dir, pin):
    packet = Path(packet_dir)
    try:
        info = packet.stat()
        if (packet.is_symlink() or (info.st_dev, info.st_ino) != (pin['dev'], pin['ino'])
                or info.st_mode & 0o222 or {item.name for item in packet.iterdir()} != set(pin['files'])):
            return False
        return all(NAME.fullmatch(name) and path.is_file() and not path.is_symlink()
                   and stat.S_ISREG(path.stat().st_mode) and not path.stat().st_mode & 0o222
                   and _sha(path.read_bytes()) == digest
                   for name, digest in pin['files'].items() for path in (packet / name,))
    except (OSError, KeyError, TypeError, ValueError):
        return False


def _pages(run_root, reviewer_role, native_api, endpoint, extra=()):
    rows, cursor, seen = [], None, set()
    for _ in range(20):
        args = [endpoint, '--param', 'limit=100', *extra]
        args += ['--param', 'cursor=' + cursor] if cursor else ['--param', 'order=asc']
        reply = native_api(run_root, reviewer_role, *args)
        items = reply.get('items', reply.get('data'))
        if not isinstance(items, list):
            raise RuntimeError('native_review_page_invalid')
        rows.extend(items)
        next_cursor = (reply.get('cursor') or {}).get('next')
        if not next_cursor:
            return rows
        if not isinstance(next_cursor, str) or next_cursor in seen:
            raise RuntimeError('native_review_cursor_invalid')
        seen.add(next_cursor)
        cursor = next_cursor
    raise RuntimeError('native_review_page_limit')


def _sessions(run_root, reviewer_role, native_api):
    sessions = _pages(run_root, reviewer_role, native_api, 'session.list')
    ids = [item.get('id') for item in sessions if isinstance(item, dict)]
    if len(ids) != len(sessions) or len(ids) != len(set(ids)) or any(
            not isinstance(sid, str) or not IDENTIFIER.fullmatch(sid) for sid in ids):
        raise RuntimeError('native_review_session_list_invalid')
    return ids


def _allowance(snapshot):
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get('run_identity'), dict)
            or not isinstance(snapshot.get('hard_limits'), dict)
            or any(not isinstance(snapshot.get(key), int) or snapshot[key] < 0
                   for key in ('used_tunnels', 'charged_tunnel_bytes'))):
        raise RuntimeError('review_allowance_unavailable')
    return {'run_identity': snapshot['run_identity'], 'hard_limits': snapshot['hard_limits'],
            'used_tunnels': snapshot['used_tunnels'],
            'charged_tunnel_bytes': snapshot['charged_tunnel_bytes'],
            'provider_request_count': snapshot.get('provider_request_count'),
            'monetary_spend': snapshot.get('monetary_spend'), 'active': snapshot.get('active') is True}


def _same_allowance(before, after):
    return (before['run_identity'] == after['run_identity']
            and before['hard_limits'] == after['hard_limits']
            and before['used_tunnels'] <= after['used_tunnels']
            and before['charged_tunnel_bytes'] <= after['charged_tunnel_bytes'])


def _room(snapshot):
    limits = snapshot['hard_limits']
    return (type(limits.get('max_connections')) is int
            and type(limits.get('max_bytes')) is int
            and snapshot['used_tunnels'] < limits['max_connections']
            and snapshot['charged_tunnel_bytes'] < limits['max_bytes'])


def _usage(run_root, reviewer_role, native_api):
    rows = []
    for sid in _sessions(run_root, reviewer_role, native_api):
        data = native_api(run_root, reviewer_role, 'session.get', '--param', 'sessionID=' + sid).get('data')
        if not isinstance(data, dict) or data.get('id') != sid:
            raise RuntimeError('native_review_usage_invalid')
        messages = _pages(run_root, reviewer_role, native_api, 'session.message.list',
                          ('--param', 'sessionID=' + sid))
        assistant = [(item.get('info', item) if isinstance(item, dict) else {}) for item in messages]
        assistant = [item for item in assistant if item.get('type') == 'assistant']
        rows.append({'id': sid, 'parentID': data.get('parentID'), 'cost': data.get('cost'),
                     'tokens': data.get('tokens'), 'assistant_messages': len(assistant),
                     'assistant_errors': sum(bool(item.get('error')) for item in assistant)})
    return rows


def project_review_material(run_root, packet_dir, pin, invocation, reviewer_stdout, *, public_bytes):
    """Keep bounded reviewer evidence while transient native stdout still exists."""
    held = lambda reason: {'kind': 'native-review-material-v1', 'status': 'held',
                           'reason': reason, 'input_id': pin['input_id']}
    native = invocation.get('native')
    if (not verify_packet(packet_dir, pin)
            or invocation.get('status') != 'native_turn_observed_unassessed'
            or not isinstance(native, dict) or not isinstance(reviewer_stdout, str)
            or not callable(public_bytes)):
        return held('review_material_input_unavailable')
    raw = reviewer_stdout.encode()
    if (not 0 < len(raw) <= 16 * 1024 * 1024
            or _sha(raw) != native.get('stdout_sha256')
            or not isinstance(native.get('dispatch_id'), str)
            or not re.fullmatch(r'[0-9a-f]{32}', native['dispatch_id'])
            or not isinstance(native.get('native_trace_sha256'), str)
            or not SHA256.fullmatch(native['native_trace_sha256'])
            or invocation.get('session_id') != native.get('session_id')
            or invocation.get('reviewer_role') != native.get('role')):
        return held('review_material_native_binding_invalid')
    try:
        request = json.loads((Path(packet_dir) / 'REQUEST.json').read_bytes(),
                             object_pairs_hook=_unique_pairs)
        if (request.get('input_id') != pin['input_id']
                or request.get('source_manifest_sha256') !=
                    native.get('review_target_source_sha256')):
            return held('review_material_packet_binding_invalid')
        session = invocation['session_id']
        required = {'REQUEST.json', *request['files']}
        reads, hashes, texts, actions, text_hashes = set(), set(), [], [], {}
        text_bytes = 0
        lines = reviewer_stdout.splitlines()
        if len(lines) > 10000:
            return held('review_material_event_limit')
        def reject_nonfinite(value):
            raise ValueError('nonfinite_number')
        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError('nonfinite_number')
            return number
        for number, line in enumerate(lines, 1):
            event = json.loads(line, object_pairs_hook=_unique_pairs,
                               parse_constant=reject_nonfinite, parse_float=finite_float)
            if not isinstance(event, dict) or event.get('sessionID') != session:
                continue
            part = event.get('part')
            if not isinstance(part, dict):
                continue
            if part.get('type') == 'text' and isinstance(part.get('text'), str):
                texts.append(part['text'])
                text_hashes[number] = _sha(part['text'].encode())
                text_bytes += len(part['text'].encode())
                if text_bytes > 128 * 1024:
                    return held('review_material_conclusion_limit')
                continue
            if part.get('type') != 'tool' or not isinstance(part.get('state'), dict):
                continue
            state = part['state']
            if state.get('status') != 'completed' or state.get('error'):
                continue
            tool_input, tool_output = state.get('input'), state.get('output')
            if (part.get('tool') == 'read' and isinstance(tool_input, dict)
                    and isinstance(tool_output, str) and tool_output):
                path = tool_input.get('filePath', tool_input.get('path'))
                if isinstance(path, str) and path.startswith('/handoff/'):
                    name = path[len('/handoff/'):]
                    if name in required:
                        reads.add(name)
            if (part.get('tool') != 'shell' or not isinstance(tool_input, dict)
                    or not isinstance(tool_input.get('command'), str)
                    or not tool_input['command'] or not isinstance(tool_output, str)
                    or not tool_output):
                continue
            command = tool_input['command']
            try:
                words = shlex.split(command)
            except ValueError:
                words = []
            if words in (['sha256sum', '/handoff/*'],
                         ['sha256sum', *('/handoff/' + name for name in sorted(required))]):
                expected = {pin['files'][name] + '  /handoff/' + name for name in required}
                rows = tool_output.splitlines()
                if set(rows) == expected and len(rows) == len(expected):
                    hashes = required
            actions.append({'line': number,
                            'command_sha256': _sha(command.encode()),
                            'input_sha256': _sha(json.dumps(tool_input, sort_keys=True,
                                                             default=str).encode()),
                            'output_sha256': _sha(json.dumps(tool_output, sort_keys=True,
                                                              default=str).encode())})
            if len(actions) > 100:
                return held('review_material_action_limit')
        if (not texts or not actions or reads != required and hashes != required):
            return held('review_material_check_unavailable')
        outcome = json.loads(''.join(texts), object_pairs_hook=_unique_pairs,
                             parse_constant=reject_nonfinite, parse_float=finite_float)
        def bounded_text(value):
            return isinstance(value, str) and bool(value.strip()) and len(value.encode()) <= 2048
        def bounded_list(value):
            return (isinstance(value, list) and len(value) <= 32
                    and all(bounded_text(item) for item in value))
        if (not isinstance(outcome, dict) or set(outcome) != OUTCOME_KEYS
                or outcome.get('input_id') != pin['input_id']
                or outcome.get('decision') not in DECISIONS
                or not bounded_text(outcome.get('checked_link'))
                or not bounded_text(outcome.get('next_check'))
                or any(not bounded_list(outcome.get(key)) for key in
                       ('valid_base', 'missing_transitions', 'contrary',
                        'limits'))
                or not isinstance(outcome.get('lead_dispositions'), list)
                or len(outcome['lead_dispositions']) > 32
                or any(not isinstance(lead, dict) or set(lead) != LEAD_KEYS
                       or any(not bounded_text(lead.get(key)) for key in LEAD_KEYS)
                       for lead in outcome['lead_dispositions'])):
            return held('review_material_conclusion_invalid')
        root = Path(run_root)
        trace_path = root / 'controls/dispatch' / (native['dispatch_id'] + '.trace.json')
        for directory in (root, root / 'controls', trace_path.parent):
            info = directory.stat(follow_symlinks=False)
            if (directory.is_symlink() or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.getuid() or info.st_mode & 0o077):
                return held('review_material_trace_untrusted')
        info = trace_path.stat(follow_symlinks=False)
        if (trace_path.is_symlink() or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid() or info.st_mode & 0o077
                or not 0 < info.st_size <= 16 * 1024 * 1024):
            return held('review_material_trace_untrusted')
        trace_bytes = trace_path.read_bytes()
        if len(trace_bytes) != info.st_size or _sha(trace_bytes) != native['native_trace_sha256']:
            return held('review_material_trace_changed')
        trace = json.loads(trace_bytes, object_pairs_hook=_unique_pairs,
                           parse_constant=reject_nonfinite, parse_float=finite_float)
        rows = trace.get('events') if isinstance(trace, dict) else None
        if (not isinstance(trace, dict)
                or trace.get('kind') != 'protected-native-event-trace-v1'
                or trace.get('session_id') != session
                or trace.get('stdout_sha256') != native['stdout_sha256']
                or not isinstance(rows, list) or len(rows) != len(lines)
                or any(not isinstance(row, dict) or row.get('line') != index
                       for index, row in enumerate(rows, 1))):
            return held('review_material_trace_changed')
        if (any(rows[number - 1].get('part_type') != 'text'
                or rows[number - 1].get('session_matches') is not True
                or rows[number - 1].get('text_sha256') != digest
                for number, digest in text_hashes.items())
                or any(rows[action['line'] - 1].get('part_type') != 'tool'
                       or rows[action['line'] - 1].get('tool') != 'shell'
                       or rows[action['line'] - 1].get('status') != 'completed'
                       or rows[action['line'] - 1].get('session_matches') is not True
                       or rows[action['line'] - 1].get('input_sha256') != action['input_sha256']
                       or rows[action['line'] - 1].get('output_sha256') != action['output_sha256']
                       for action in actions)):
            return held('review_material_trace_action_changed')
        value = {'kind': 'native-review-material-v1', 'status': 'captured',
                 'input_id': pin['input_id'], 'packet_pin': pin,
                 'packet_request_sha256': pin['files']['REQUEST.json'],
                 'source_revision': request['source_revision'],
                 'evidence_revision': request['evidence_revision'],
                 'dispatch_id': native['dispatch_id'], 'session_id': session,
                 'stdout_sha256': native['stdout_sha256'],
                 'native_trace_sha256': native['native_trace_sha256'],
                 'outcome': outcome, 'outcome_sha256': _sha(_json(outcome)),
                 'shell_actions': actions}
        if (public_bytes(_json(value)) != _json(value)
                or len(_json(value)) > 1024 * 1024):
            return held('review_material_unsafe_or_oversize')
        return value
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, RuntimeError,
            RecursionError, OverflowError):
        return held('review_material_unavailable')


def invoke_fresh_review(run_root, packet_dir, pin, reviewer_role, *, native_api, invoke_native,
                        allowance_snapshot, run_active, public_bytes,
                        independent_check=None):
    """Launch one new OpenCode reviewer session in the runner's sealed reviewer."""
    run_root, packet = Path(run_root), Path(packet_dir)
    if reviewer_role not in ('reviewer-1', 'reviewer-2'):
        raise RuntimeError('fresh_reviewer_role_invalid')
    if (packet.resolve() != (run_root / 'handoff' / reviewer_role).resolve()
            or not callable(public_bytes) or not verify_packet(packet, pin)):
        raise RuntimeError('review_packet_not_sealed_in_run')
    plan_path = run_root / 'plan.json'
    if plan_path.is_symlink() or not plan_path.is_file():
        raise RuntimeError('review_source_plan_unavailable')
    plan = json.loads(plan_path.read_bytes(), object_pairs_hook=_unique_pairs)
    if not isinstance(plan, dict):
        raise RuntimeError('review_clean_source_mismatch')
    request = json.loads((packet / 'REQUEST.json').read_bytes(), object_pairs_hook=_unique_pairs)
    packet_source = {request['source_paths'][name]: request['files'][name]
                     for name in request['roles']['source']}
    source_inventory = plan.get('source_sha256')
    if (plan.get('source_manifest_sha256') !=
            request['source_manifest_sha256'] or not isinstance(source_inventory, dict)
            or _sha(json.dumps(source_inventory, sort_keys=True).encode()) !=
                request['source_manifest_sha256']
            or any(source_inventory.get(path) != digest for path, digest in packet_source.items())):
        raise RuntimeError('review_clean_source_mismatch')
    first = _allowance(allowance_snapshot(run_root))
    if not first['active'] or not run_active(run_root) or not _room(first):
        raise RuntimeError('shared_run_closed_before_review')
    if _sessions(run_root, reviewer_role, native_api):
        raise RuntimeError('reviewer_store_not_fresh')
    created = native_api(run_root, reviewer_role, 'session.create', '--data',
                         '{"title":"fresh claim review"}')
    session = (created.get('data') or {}).get('id')
    if not isinstance(session, str) or not IDENTIFIER.fullmatch(session):
        raise RuntimeError('fresh_reviewer_session_invalid')
    if _pages(run_root, reviewer_role, native_api, 'session.message.list',
              ('--param', 'sessionID=' + session)):
        raise RuntimeError('fresh_reviewer_messages_not_empty')
    before = _allowance(allowance_snapshot(run_root))
    if (not _same_allowance(first, before) or not before['active'] or not run_active(run_root)
            or not _room(before)
            or not verify_packet(packet, pin)):
        raise RuntimeError('review_pre_dispatch_binding_changed')
    native = invoke_native(run_root, reviewer_role, session, (packet / 'PROMPT.txt').read_text(),
                           include_raw=True)
    raw = native.get('_raw_stdout')
    native = {key: native.get(key) for key in ('status', 'dispatch_id', 'role', 'session_id',
              'stdout_sha256', 'stderr_sha256', 'native_trace_sha256', 'event_types', 'tool_names', 'pool_before',
              'pool_after', 'review_target_id', 'review_target_source_sha256')}
    try:
        after = _allowance(allowance_snapshot(run_root))
        active_after = after['active'] and run_active(run_root)
    except (RuntimeError, OSError, ValueError, TypeError):
        after, active_after = None, False
    stable = (active_after and _same_allowance(before, after) and verify_packet(packet, pin)
              and native['review_target_source_sha256'] == request['source_manifest_sha256'])
    try:
        usage = _usage(run_root, reviewer_role, native_api) if active_after else None
    except (RuntimeError, OSError, ValueError, TypeError):
        usage = None
    receipt = {'status': ('native_turn_observed_unassessed'
                          if native.get('status') == 'acknowledged' and stable and usage is not None
                          and native.get('role') == reviewer_role
                          and native.get('session_id') == session
                          and isinstance(native.get('review_target_id'), str)
                          and native['review_target_id'] else 'unfinished'),
               'input_id': pin['input_id'], 'packet_request_sha256': pin['files']['REQUEST.json'],
               'session_id': session, 'reviewer_role': reviewer_role, 'native': native,
               'allowance_before': before, 'allowance_after': after,
               'same_original_allowance': stable,
               'session_usage': usage}
    receipt['assessment'] = assess_review(packet, pin, receipt, raw, independent_check,
                                          public_bytes=public_bytes)
    receipt['material'] = project_review_material(run_root, packet, pin, receipt, raw,
                                                  public_bytes=public_bytes)
    return receipt


def assess_review(packet_dir, pin, invocation, reviewer_stdout, independent_check, *,
                  public_bytes=None):
    """Return an internal candidate only when native work and host control agree."""
    unfinished = {'status': 'unfinished', 'decision': None, 'input_id': pin['input_id']}
    if (not verify_packet(packet_dir, pin)
            or invocation.get('status') != 'native_turn_observed_unassessed'
            or not callable(public_bytes)
            or not isinstance(reviewer_stdout, str)
            or _sha(reviewer_stdout.encode()) != invocation.get('native', {}).get('stdout_sha256')):
        return unfinished
    if not callable(independent_check):
        return unfinished
    request = json.loads((Path(packet_dir) / 'REQUEST.json').read_text())
    session = invocation['session_id']
    tools, texts = [], []
    for line_number, line in enumerate(reviewer_stdout.splitlines(), 1):
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            return unfinished
        if not isinstance(event, dict) or event.get('sessionID') != session:
            continue
        part = event.get('part')
        if not isinstance(part, dict):
            continue
        if part.get('type') == 'text' and isinstance(part.get('text'), str):
            texts.append(part['text'])
        elif part.get('type') == 'tool' and isinstance(part.get('state'), dict):
            state = part['state']
            if state.get('status') == 'completed' and not state.get('error'):
                tools.append({'line': line_number, 'tool': part.get('tool'),
                              'input': state.get('input'), 'output': state.get('output')})
    if not texts or not tools:
        return unfinished
    required = {'REQUEST.json', *request['files']}
    read_files = {name for item in tools if item['tool'] == 'read'
                  and isinstance(item['input'], dict) and isinstance(item['output'], str)
                  and item['output'] for name in required
                  if item['input'].get('filePath', item['input'].get('path')) == '/handoff/' + name}
    hashed_files = set()
    for item in tools:
        if item['tool'] != 'shell' or not isinstance(item['input'], dict):
            continue
        command = item['input'].get('command')
        if not isinstance(command, str) or not isinstance(item['output'], str):
            continue
        try:
            words = shlex.split(command)
        except ValueError:
            continue
        if words not in (['sha256sum', '/handoff/*'],
                         ['sha256sum', *('/handoff/' + name for name in sorted(required))]):
            continue
        lines = item['output'].splitlines()
        expected_lines = {pin['files'][name] + '  /handoff/' + name for name in required}
        if set(lines) == expected_lines and len(lines) == len(expected_lines):
            hashed_files = required
            break
    if read_files != required and hashed_files != required:
        return unfinished
    try:
        outcome = json.loads(''.join(texts))
    except (ValueError, RecursionError):
        return unfinished
    if (not isinstance(outcome, dict) or outcome.get('input_id') != pin['input_id']
            or outcome.get('decision') not in DECISIONS
            or not isinstance(outcome.get('checked_link'), str) or not outcome['checked_link'].strip()
            or any(not isinstance(outcome.get(key), list) for key in
                   ('valid_base', 'missing_transitions', 'contrary', 'lead_dispositions', 'limits'))
            or not isinstance(outcome.get('next_check'), str)):
        return unfinished
    if any(not isinstance(lead, dict) or any(
            not isinstance(lead.get(key), str) or not lead[key].strip()
            for key in ('basis_examined', 'uncertain_condition', 'next_check', 'decision'))
            for lead in outcome['lead_dispositions']):
        return unfinished
    try:
        checked = independent_check(tools, request, invocation)
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError):
        return unfinished
    if (not isinstance(checked, dict) or checked.get('status') != 'observed'
            or checked.get('observer_origin') != 'host_protected'
            or checked.get('native_action_reached_clean_target') is not True
            or checked.get('source_stable_after') is not True
            or checked.get('review_target_id') != invocation['native'].get('review_target_id')
            or checked.get('source_revision') != request['source_revision']
            or checked.get('evidence_revision') != request['evidence_revision']
            or checked.get('review_target_source_sha256') !=
                request['source_manifest_sha256']
            or not SHA256.fullmatch(str(checked.get('review_target_source_sha256', '')))
            or not isinstance(checked.get('effect'), dict) or not checked['effect']
            or not isinstance(checked.get('control'), dict) or not checked['control']):
        return unfinished
    selected = [item for item in tools if item['line'] == checked.get('tool_line')
                and item['tool'] == 'shell' and isinstance(item['input'], dict)
                and isinstance(item['input'].get('command'), str)
                and isinstance(item['output'], str) and item['output']]
    if not selected or _sha(selected[0]['input']['command'].encode()) != checked.get('command_sha256'):
        return unfinished
    try:
        outcome_bytes, checked_bytes = _json(outcome), _json(checked)
        effect_bytes, control_bytes = _json(checked['effect']), _json(checked['control'])
        if (public_bytes(outcome_bytes) != outcome_bytes
                or public_bytes(checked_bytes) != checked_bytes):
            return unfinished
    except (ValueError, TypeError, RuntimeError, RecursionError, OverflowError):
        return unfinished
    return {'status': 'candidate_for_operator_review', 'decision': outcome['decision'],
            'input_id': pin['input_id'], 'session_id': session,
            'conclusion_sha256': _sha(outcome_bytes), 'material_tool_line': selected[0]['line'],
            'effect_sha256': _sha(effect_bytes),
            'control_sha256': _sha(control_bytes),
            'outcome': outcome, 'independent_check': checked,
            'filing_or_escalation_authorized': False}
