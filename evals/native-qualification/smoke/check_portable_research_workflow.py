#!/usr/bin/env python3
"""Public portable-workspace workflow; native/provider boundaries are substituted."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import native_research as runner

RELAY = ROOT / ('experiments/native-network-preflight/tcp-relay-host-override/'
                'cloud-linux-amd64-20261020a/tcp-relay-linux-amd64')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(*args):
    stream = io.StringIO()
    with patch.object(sys, 'argv', ['native_research.py', *args]), redirect_stdout(stream):
        code = runner.main()
    return code, json.loads(stream.getvalue())


def main():
    os.umask(0o077)
    output = Path(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--output' else None
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'pass': bool(condition)})
        if not condition:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory(prefix='portable-research-check-') as raw:
        base = Path(raw).resolve()
        source = base / 'source'
        source.mkdir()
        (source / 'hello.php').write_text('<?php echo "hello";\n')
        brief, scope = base / 'brief.md', base / 'scope.md'
        brief.write_text('Inspect the owned hello fixture; save evidence and unfinished work.\n')
        scope.write_text('PRIVATE_SCOPE_SENTINEL; no live authorization.\n')
        relay, ca, key = base / 'relay', base / 'ca.pem', base / 'ca.key'
        shutil.copy2(RELAY, relay)
        relay.chmod(0o700)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                        '-days', '1', '-subj', '/CN=portable research fixture',
                        '-keyout', str(key), '-out', str(ca)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.unlink()
        command, root = base / 'target-command.json', base / 'run'
        command.write_text(json.dumps(['php', '-S', '0.0.0.0:8080']))
        code, prepared = cli('prepare', '--run-root', str(root), '--source', str(source),
                             '--brief', str(brief), '--scope-file', str(scope),
                             '--scope-sha256', sha(scope), '--relay', str(relay),
                             '--relay-sha256', sha(relay), '--runtime-ca', str(ca),
                             '--runtime-ca-sha256', sha(ca), '--target-command', str(command),
                             '--target-port', '8080', '--image-id', 'sha256:' + '1' * 64,
                             '--target-image-id', 'sha256:' + '2' * 64,
                             '--platform', 'linux/amd64', '--duration-seconds', '300')
        check('public prepare succeeds without live services', code == 0)
        plan_path = root / 'plan.json'
        plan = json.loads(plan_path.read_text())
        host = root / 'controls/research'
        notebook = root / 'researcher/RESEARCH.md'
        check('prepare pins workflow and seeds ordinary notebook',
              notebook.is_file() and host.joinpath('WORKFLOW.md').is_file()
              and plan.get('research_workflow_sha256') == sha(host / 'WORKFLOW.md'))
        check('frozen brief matches and source remains pristine',
              sha(host / 'BRIEF.md') == sha(brief)
              and list((root / 'researcher/project').iterdir()) == [root / 'researcher/project/hello.php'])

        notebook.write_text('# Research\nHypothesis H1 contradicted by result R1; H2 unfinished.\n'
                            'Unknown effect E1 must be reconciled before retry.\n')
        script = root / 'researcher/project/experiment.py'
        script.write_text('print("synthetic experiment; not executed")\n')
        result_file = root / 'researcher/project/result.txt'
        result_file.write_text('R1: synthetic contrary evidence; no target called.\n')
        originals = {path: path.read_bytes() for path in (notebook, script, result_file)}
        budget = {'run_identity': {'manifest_sha256': 'a' * 64, 'nonce': 'owned-fixture',
                                  'ids': [], 'created_monotonic': 100.0, 'deadline_monotonic': 400.0},
                  'hard_limits': {'max_connections': 16, 'max_bytes': 8000,
                                  'duration_seconds': 300},
                  'used_tunnels': 5, 'charged_tunnel_bytes': 2000, 'active': True,
                  'provider_deadline_unix': 1010.0,
                  'provider_request_count': None, 'monetary_spend': None}
        calls, commands, sessions = [], [], []

        def native_api(run_root, role, *parts):
            calls.append((role, parts))
            if parts[0] == 'session.create':
                session = 'ses_fresh' + str(len(sessions) + 1)
                sessions.append(session)
                return {'data': {'id': session}}
            if parts[0] == 'session.get':
                return {'data': {'id': parts[-1].split('=', 1)[1]}}
            return {'items': []}

        def native_exec(run_root, role, argv, timeout_seconds, **kwargs):
            commands.append((role, argv))
            if argv[0] == 'api':
                return subprocess.CompletedProcess(argv, 0,
                    json.dumps({'data': {'id': argv[-1].split('=', 1)[1],
                                         'cost': 0, 'tokens': {}}}).encode(), b'')
            session = argv[argv.index('--session') + 1]
            payload = {'type': 'text', 'sessionID': session,
                       'part': {'type': 'text', 'text': 'Synthetic native response only.'}}
            return subprocess.CompletedProcess(argv, 0, (json.dumps(payload) + '\n').encode(), b'')

        with patch.object(runner, 'native_api', side_effect=native_api), \
             patch.object(runner, '_native_exec', side_effect=native_exec), \
             patch.object(runner, 'run_active', return_value=True), \
             patch.object(runner, 'allowance_snapshot', side_effect=lambda _: deepcopy(budget)), \
             patch.object(runner.time, 'monotonic', return_value=150.0), \
             patch.object(runner.time, 'time', return_value=1000.0):
            code, initial = cli('research', '--run-root', str(root))
            check('initial research loads portable instructions in its actual prompt',
                  code == 0 and initial.get('continuity') == 'fresh_research'
                  and commands[0][0] == 'researcher'
                  and all(name in commands[0][1][-1]
                          for name in ('/research/WORKFLOW.md', '/workspace/RESEARCH.md')))
            prompt_file = base / 'next.md'
            prompt_file.write_text('Continue H2 from saved evidence.\n')
            code, first_resume = cli('resume', '--run-root', str(root), '--session', initial['session_id'],
                                     '--prompt-file', str(prompt_file))
            check('native resume keeps original research session',
                  code == 0 and first_resume['session_id'] == initial['session_id']
                  and first_resume.get('continuity') == 'native_history')
            calls.clear()
            before_reconstruction = len(commands)
            code, receipt = cli('reconstruct', '--run-root', str(root))
            check('reconstruction creates fresh session on existing resume producer',
                  code == 0 and receipt.get('continuity') == 'fresh_context_from_workspace'
                  and calls == [('resume', ('session.create', '--data', '{"title":"workspace reconstruction"}'))]
                  and commands[before_reconstruction][0] == 'resume'
                  and receipt['session_id'] != initial['session_id'])
            prompt = commands[before_reconstruction][1][-1]
            check('actual prompt loads portable inputs and hash binds it',
                  all(name in prompt for name in ('/research/WORKFLOW.md', '/research/BRIEF.md',
                                                   '/research/RUN.json', '/workspace/RESEARCH.md'))
                  and receipt['prompt_sha256'] == hashlib.sha256(prompt.encode()).hexdigest())
            snapshot = json.loads((host / 'RUN.json').read_text())
            archive = root / 'controls/research-snapshots' / (receipt['dispatch_id'] + '.json')
            check('snapshot preserves spent budget and is independently archived',
                  snapshot['allowance']['used_connections'] == 5
                  and snapshot['allowance']['remaining_connections'] == 11
                  and snapshot['allowance']['used_bytes'] == 2000
                  and snapshot['allowance']['remaining_bytes'] == 6000
                  and snapshot['allowance']['remaining_seconds'] == 10.0
                  and snapshot['allowance']['provider_request_count'] is None
                  and snapshot['allowance']['monetary_spend'] is None
                  and archive.read_bytes() == (host / 'RUN.json').read_bytes()
                  and receipt['research_snapshot_sha256'] == sha(archive))
            check('snapshot excludes private scope and review content',
                  'PRIVATE_SCOPE_SENTINEL' not in (host / 'RUN.json').read_text()
                  and snapshot['review'] is None and snapshot['cleanup'] is None)
            check('existing notes/scripts/results survive reconstruction',
                  all(path.read_bytes() == data for path, data in originals.items()))
            calls.clear()
            code, resumed = cli('resume', '--run-root', str(root), '--session', receipt['session_id'],
                                 '--prompt-file', str(prompt_file))
            check('ordinary resume retains session and shared consumption',
                  code == 0 and resumed['session_id'] == receipt['session_id']
                  and resumed['continuity'] == 'native_history'
                  and calls[0][1][0] == 'session.get'
                  and json.loads((host / 'RUN.json').read_text())['allowance']['used_connections'] == 5)

            def rejects(name, expected):
                calls.clear()
                before = len(commands)
                code, rejected = cli('reconstruct', '--run-root', str(root))
                check(name, code == 2 and rejected.get('code') == expected
                      and calls == [] and len(commands) == before)

            notebook.unlink()
            code, without_notebook = cli('resume', '--run-root', str(root),
                                         '--session', receipt['session_id'],
                                         '--prompt-file', str(prompt_file))
            check('missing advisory notebook does not block native resume',
                  code == 0 and without_notebook['session_id'] == receipt['session_id']
                  and without_notebook['continuity'] == 'native_history'
                  and not notebook.exists()
                  and all(path.read_bytes() == originals[path] for path in (script, result_file)))
            calls.clear()
            code, without_notebook = cli('reconstruct', '--run-root', str(root))
            check('missing advisory notebook does not block or reset reconstruction',
                  code == 0 and without_notebook['continuity'] == 'fresh_context_from_workspace'
                  and without_notebook['session_id'] != receipt['session_id']
                  and calls == [('resume', ('session.create', '--data', '{"title":"workspace reconstruction"}'))]
                  and not notebook.exists()
                  and json.loads((host / 'RUN.json').read_text())['allowance']['used_connections'] == 5
                  and all(path.read_bytes() == originals[path] for path in (script, result_file)))
            notebook.write_bytes(originals[notebook])
            workflow = (host / 'WORKFLOW.md').read_bytes()
            (host / 'WORKFLOW.md').write_text('changed workflow\n')
            rejects('changed workflow rejects before any native call', 'research_workflow_changed')
            (host / 'WORKFLOW.md').write_bytes(workflow)
            pending = root / 'controls/dispatch' / ('f' * 32 + '.json')
            pending.write_text(json.dumps({'dispatch_id': 'f' * 32, 'status': 'unknown_effect'}))
            rejects('unknown effect rejects before any native call', 'prior_dispatch_unknown_effect')
            pending.unlink()
            budget['active'] = False
            rejects('inactive allowance rejects before any native call', 'research_allowance_inactive')
            budget['active'] = True
            budget['used_tunnels'] = 16
            rejects('exhausted allowance rejects before any native call', 'research_allowance_exhausted')
            budget['used_tunnels'] = 5
            budget['provider_deadline_unix'] = 990.0
            rejects('expired provider lease rejects despite native time remaining', 'research_allowance_exhausted')
            del budget['provider_deadline_unix']
            rejects('missing provider expiry rejects before native calls', 'research_allowance_unavailable')
            budget['provider_deadline_unix'] = 'invalid'
            rejects('invalid provider expiry rejects before native calls', 'research_allowance_unavailable')
            budget['provider_deadline_unix'] = 1010.0
            with patch.object(runner, 'allowance_snapshot', side_effect=runner.NativeResearchError('unavailable')):
                rejects('missing allowance rejects before any native call', 'research_allowance_unavailable')
            old = dict(plan)
            del old['research_workflow_sha256']
            plan_path.write_text(json.dumps(old))
            rejects('old plan is explicitly native-history-only', 'portable_research_requires_new_prepare')
            plan_path.write_text(json.dumps(plan))

        # Inspect actual public launch builder's mount calls with Docker/network
        # operations substituted. No container or target is started.
        mounts = {}
        def create(run_root, nonce, rows, role, image, platform, network, ip,
                   mount_list, env, command, **kwargs):
            mounts[role] = mount_list
            return role
        def inspect(kind, identifier):
            if kind == 'network':
                return {'Name': identifier}
            return {'NetworkSettings': {'Networks': {
                name: {'IPAddress': '172.20.0.2'}
                for name in ('external', 'research', 'reviewer-1', 'reviewer-2')}}}
        with patch.object(runner, '_network', side_effect=lambda root, nonce, rows, role, **kw:
                          (role, '172.20.0.2', '172.20.0.3')), \
             patch.object(runner, '_create', side_effect=create), \
             patch.object(runner, '_docker'), patch.object(runner, '_inspect', side_effect=inspect):
            runner._preseal(root, plan, 'fixture', [], 8888, 'synthetic')
        check('read-only research mount reaches only researcher and resume',
              all(any('dst=/research,readonly' in mount for mount in mounts[role])
                  for role in ('researcher', 'resume'))
              and all(not any('dst=/research' in mount for mount in mounts[role])
                      for role in ('reviewer-1', 'reviewer-2')))
        store = root / 'researcher/data/opencode'
        store.mkdir()
        (store / 'opencode.db').write_bytes(b'SQLite format 3\x00')
        observed = runner._filesystem_snapshot(root, plan)
        check('stopped byte collection includes ordinary notebook without contents',
              observed['research_notebook']['sha256'] == sha(notebook)
              and 'H1' not in json.dumps(observed))
        notebook.unlink()
        observed = runner._filesystem_snapshot(root, plan)
        check('missing advisory notebook does not invalidate protected stopped bytes',
              observed['status'] == 'complete' and observed['native_store']['status'] == 'present'
              and observed['research_notebook'] == {'present': False})
        notebook.symlink_to(script)
        unsafe_rejected = False
        try:
            runner._filesystem_snapshot(root, plan)
        except runner.NativeResearchError as error:
            unsafe_rejected = str(error) == 'absolute_regular_file_required'
        check('snapshot never hashes an unsafe advisory notebook path', unsafe_rejected)
        notebook.unlink()
        notebook.write_bytes(originals[notebook])
        with notebook.open('wb') as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        oversized_rejected = False
        with patch.object(runner, '_sha', wraps=runner._sha) as hashed:
            try:
                runner._filesystem_snapshot(root, plan)
            except runner.NativeResearchError as error:
                oversized_rejected = str(error) == 'research_notebook_oversize'
            check('oversized notebook rejects before hashing its bytes',
                  oversized_rejected and not any(call.args == (notebook,) for call in hashed.call_args_list))

    result = {'status': 'pass', 'checks': checks, 'provider_calls': 0, 'target_calls': 0,
              'native_dispatch': 'substituted; no adaptive behavior qualification'}
    if output:
        output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(f'PASS: {len(checks)} portable workspace checks; provider_calls=0 target_calls=0')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
