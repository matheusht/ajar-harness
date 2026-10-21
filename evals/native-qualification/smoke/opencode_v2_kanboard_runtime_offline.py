#!/usr/bin/env python3
"""Offline Kanboard runtime check inside the pinned V2 researcher image."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid


HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import observer_case
IMAGE = 't02-kanboard-runtime:20261020a'
IMAGE_ID = 'sha256:31b7fa2b80f17bbddfeffd0577634257df40490f1b8d4c57f8507b40956cdf15'
SOURCE_ROOT = Path('/private/tmp/native-qualification-observer-20261019-final')
CONFIG = HERE / 'smoke/opencode_v2_observed_config.json'
PLUGIN = HERE / 'smoke/opencode_v2_request_observer'
DOCKERFILE = HERE / 'Dockerfile.opencode-kanboard-runtime'
CHECKS = HERE / 'T02-KANBOARD-RUNTIME-CHECKS.md'


def run(*args, input_text=None):
    return subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=30)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


PHP_CLIENT = '''$r=json_decode(stream_get_contents(STDIN),true);
$header="Content-Type: application/json\\r\\n";
if(isset($r['auth'])) $header.="Authorization: Basic ".$r['auth']."\\r\\n";
$context=stream_context_create(['http'=>['method'=>$r['method'],'header'=>$header,
  'content'=>isset($r['body'])?json_encode($r['body']):'', 'ignore_errors'=>true,'timeout'=>5]]);
$body=@file_get_contents('http://127.0.0.1:8081'.$r['path'],false,$context);
$line=$http_response_header[0]??'';
preg_match('/^HTTP\\/\\S+ (\\d+)/',$line,$match);
echo json_encode(['status'=>isset($match[1])?(int)$match[1]:0,'body'=>$body===false?'':$body]);'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('output directory must be new')
    output.mkdir(parents=True, mode=0o700)
    pins = {str(p.relative_to(HERE)): sha(p) for p in (Path(__file__).resolve(), CONFIG,
            PLUGIN/'server.js', PLUGIN/'package.json', DOCKERFILE, CHECKS, HERE/'observer_case.py')}
    report = {'classification': 'offline researcher-side Kanboard runtime prerequisite; no model/provider call',
              'status': 'running', 'image': IMAGE, 'expected_image_id': IMAGE_ID,
              'source_sha256': pins, 'checks': [], 'resources': [], 'cleanup': []}

    def save():
        (output/'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def check(name, passed):
        report['checks'].append({'check': name, 'status': 'pass' if passed else 'fail'})
        save()
        if not passed:
            raise RuntimeError(name)

    save()
    nonce = uuid.uuid4().hex
    label = 'io.lrh.t02-kanboard-runtime=' + nonce
    container = None
    observer = None
    active_stage = None
    try:
        image = run('docker', 'image', 'inspect', IMAGE)
        check('derived V2 image exact ID present', image.returncode == 0 and
              json.loads(image.stdout)[0]['Id'] == IMAGE_ID)
        archive = SOURCE_ROOT/'vulnerable.tar.gz'
        check('pinned vulnerable archive cached', archive.is_file() and
              sha(archive) == observer_case.PINS['vulnerable'][1])
        source = observer_case.prepare_source(SOURCE_ROOT, 'vulnerable', *observer_case.PINS['vulnerable'])
        report['application'] = {'commit': observer_case.PINS['vulnerable'][0],
                                 'archive_sha256': sha(archive),
                                 'source_files': sum(p.is_file() for p in source.rglob('*'))}
        with tempfile.TemporaryDirectory(prefix='t02-kanboard-app-') as temp:
            workspace = Path(temp).resolve()/'workspace'
            project = workspace/'project'
            shutil.copytree(source, project)
            for name in ('home', 'config/opencode', 'data', 'cache', 'state', 'tmp', 'telemetry'):
                (workspace/name).mkdir(parents=True, exist_ok=True)
            (workspace/'config/opencode/opencode.json').touch()
            check('clean answer-free vulnerable copy',
                  {str(p.relative_to(project)) for p in project.rglob('*') if p.is_file()} ==
                  {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()} and
                  not (project/'data/db.sqlite').exists() and
                  not any(p.name in ('observer-results.json', 'observer_case.py', 'BRIEF.md')
                          for p in project.rglob('*')))
            def start_pair(stage):
                nonlocal container, observer, active_stage
                active_stage = stage
                created = run('docker', 'container', 'create', '--name', f't02-kanboard-app-{nonce[:12]}-{stage}',
                              '--label', label, '--pull', 'never', '--platform', 'linux/arm64',
                              '--network', 'none', '--read-only', '--restart', 'no',
                              '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop', 'ALL',
                              '--security-opt', 'no-new-privileges=true', '--memory', '1g',
                              '--cpus', '1', '--pids-limit', '64',
                              '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                              '--mount', f'type=bind,src={workspace},dst=/workspace',
                              '--mount', f'type=bind,src={CONFIG},dst=/workspace/config/opencode/opencode.json,readonly',
                              '--mount', f'type=bind,src={PLUGIN},dst=/observer/opencode_v2_request_observer,readonly',
                              '--env', 'HOME=/workspace/home', '--env', 'XDG_CONFIG_HOME=/workspace/config',
                              '--env', 'XDG_DATA_HOME=/workspace/data', '--env', 'XDG_CACHE_HOME=/workspace/cache',
                              '--env', 'XDG_STATE_HOME=/workspace/state', '--env', 'TMPDIR=/workspace/tmp',
                              '--env', 'T02_OBSERVER_PATH=/workspace/telemetry/request-names.jsonl',
                              '--workdir', '/workspace/project', '--entrypoint', 'php', IMAGE,
                              '-S', '127.0.0.1:8081', '-t', '/workspace/project')
                check(stage + ': researcher application container created', created.returncode == 0)
                container = created.stdout.strip()
                report['resources'].append({'role': 'researcher_app', 'stage': stage, 'id': container})
                state = json.loads(run('docker', 'container', 'inspect', container).stdout)[0]
                check(stage + ': only owned workspace and read-only config/plugin mounted',
                      state['Image'] == IMAGE_ID and state['HostConfig']['NetworkMode'] == 'none' and
                      {x['Source'] for x in state['Mounts']} == {str(workspace), str(CONFIG), str(PLUGIN)} and
                      all(not x['RW'] for x in state['Mounts'] if x['Source'] != str(workspace)))
                check(stage + ': PHP app started in researcher container',
                      run('docker', 'container', 'start', container).returncode == 0)
                created = run('docker', 'container', 'create', '--name', f't02-kanboard-client-{nonce[:12]}-{stage}',
                              '--label', label, '--pull', 'never', '--network', 'container:' + container,
                              '--read-only', '--restart', 'no', '--cap-drop', 'ALL',
                              '--security-opt', 'no-new-privileges=true', '--memory', '256m',
                              '--cpus', '1', '--pids-limit', '32', '--tmpfs', '/tmp:rw,nosuid,nodev,size=32m',
                              '--entrypoint', 'sh', IMAGE, '-c', 'exec sleep 120')
                check(stage + ': mount-free host-owned client created', created.returncode == 0)
                observer = created.stdout.strip()
                report['resources'].append({'role': 'host_client', 'stage': stage, 'id': observer})
                client_state = json.loads(run('docker', 'container', 'inspect', observer).stdout)[0]
                check(stage + ': client shares only app network namespace',
                      client_state['HostConfig']['NetworkMode'] == 'container:' + container and
                      not client_state['Mounts'])
                check(stage + ': host-owned client started',
                      run('docker', 'container', 'start', observer).returncode == 0)

            def remove_pair(stage):
                nonlocal container, observer, active_stage
                for role, identifier in (('host_client', observer), ('researcher_app', container)):
                    if not identifier:
                        continue
                    removed = run('docker', 'container', 'rm', '--force', '--volumes', identifier)
                    absent = run('docker', 'container', 'inspect', identifier).returncode != 0
                    report['cleanup'].append({'role': role, 'stage': stage, 'id': identifier,
                                              'remove_exit': removed.returncode, 'absent': absent})
                    check(stage + ': ' + role + ' removed', removed.returncode == 0 and absent)
                container = observer = None
                active_stage = None

            def api(*argv):
                response = run('docker', 'container', 'exec', '-w', '/workspace/project',
                               container, 'opencode', 'api', '--standalone', *argv)
                if response.returncode:
                    raise RuntimeError('native API failed: ' + response.stderr[:160])
                return json.loads(response.stdout)

            def native_ids():
                rows, cursor, seen = [], None, set()
                for _ in range(20):
                    params = ['session.list', '--param', 'limit=100']
                    params += ['--param', 'cursor=' + cursor] if cursor else ['--param', 'order=asc']
                    response = api(*params)
                    page = response.get('items', response.get('data'))
                    if not isinstance(page, list):
                        raise RuntimeError('native session page absent')
                    rows += page
                    cursor = (response.get('cursor') or {}).get('next')
                    if not cursor:
                        break
                    if cursor in seen:
                        raise RuntimeError('native session cursor repeated')
                    seen.add(cursor)
                else:
                    raise RuntimeError('native session page limit')
                ids = [row['id'] for row in rows]
                if len(ids) != len(set(ids)):
                    raise RuntimeError('duplicate native session ID')
                return ids

            start_pair('first')
            linted = {}
            for name in ('index.php', 'jsonrpc.php', 'app/common.php', 'app/check_setup.php', 'vendor/autoload.php'):
                linted[name] = run('docker', 'container', 'exec', '-w', '/workspace/project',
                                   container, 'php', '-l', name).returncode
            report['researcher_php_lint'] = linted
            check('packaged release has vendor and key PHP files lint inside researcher image',
                  (project/'vendor/autoload.php').is_file() and all(code == 0 for code in linted.values()))
            version = run('docker', 'container', 'exec', container, 'opencode', '--version')
            loaded = api('config.get')
            document = next(x['info'] for x in loaded if x.get('type') == 'document')
            expected = json.loads(CONFIG.read_text())
            check('native V2 and pinned model/config/plugin load without inference',
                  version.returncode == 0 and version.stdout.strip() == 'opencode v2.0.32' and
                  document.get('model') == {'providerID': 'opencode', 'model': 'deepseek-v4.1-flash-free'} and
                  document.get('permissions') == expected['permissions'] and
                  document.get('policies') == expected['policies'] and
                  document.get('plugins') == expected['plugins'])
            check('native store begins with no sessions', native_ids() == [])
            created = api('session.create', '--data', '{"title":"T02 offline Kanboard workspace"}')
            session_id = created.get('data', {}).get('id')
            db_path = workspace/'data/opencode/opencode.db'
            report['native_session'] = {'id': session_id, 'store': '/workspace/data/opencode/opencode.db'}
            check('native session created in same persistent workspace without inference',
                  isinstance(session_id, str) and session_id.startswith('ses_') and
                  native_ids() == [session_id] and db_path.is_file() and
                  not (workspace/'telemetry/request-names.jsonl').exists())

            def request(method, path, body=None, username=None, password=None):
                payload = {'method': method, 'path': path}
                if body is not None:
                    payload['body'] = body
                if username is not None:
                    payload['auth'] = base64.b64encode(f'{username}:{password}'.encode()).decode()
                response = run('docker', 'container', 'exec', '-i', observer,
                               'php', '-r', PHP_CLIENT, input_text=json.dumps(payload))
                if response.returncode:
                    raise RuntimeError('host client failed: ' + response.stderr[:160])
                return json.loads(response.stdout)

            for _ in range(50):
                try:
                    ready = request('GET', '/robots.txt')
                    if ready['status'] == 200:
                        break
                except (RuntimeError, ValueError):
                    time.sleep(0.1)
            else:
                raise RuntimeError('host-owned client could not reach app readiness endpoint')
            report['host_readiness'] = {'http_status': ready['status'], 'body_sha256': hashlib.sha256(ready['body'].encode()).hexdigest()}
            admin_secret = observer_case.default_admin_password(project)
            alice_secret, bob_secret = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            methods = []

            def rpc(username, password, method, params):
                response = request('POST', '/jsonrpc.php', {'jsonrpc': '2.0', 'id': 1,
                                                            'method': method, 'params': params}, username, password)
                methods.append({'actor': username, 'method': method, 'http_status': response['status']})
                if not response['body'].strip():
                    report['last_rpc_failure'] = {'method': method, 'http_status': response['status'],
                                                  'empty_body': True}
                    raise RuntimeError('empty JSON-RPC response')
                value = json.loads(response['body'])
                value['_http_status'] = response['status']
                return value

            admin = lambda method, params: rpc('admin', admin_secret, method, params)
            alice = lambda method, params: rpc('alice', alice_secret, method, params)
            bob = lambda method, params: rpc('bob', bob_secret, method, params)
            alice_id = observer_case.result(admin('createUser', ['alice', alice_secret]), 'create alice')
            observer_case.result(admin('createUser', ['bob', bob_secret]), 'create bob')
            project_id = observer_case.result(admin('createProject', ['T02 Ordinary Project']), 'create project')
            observer_case.result(admin('addProjectUser', [project_id, alice_id, 'project-manager']), 'grant alice')
            own = observer_case.result(alice('getProjectById', [project_id]), 'authorized project')
            denied = observer_case.denial(bob('getProjectById', [project_id]), 'private project control')
            report['host_observation'] = {'route': 'host-owned client in app network namespace; loopback :8081',
                                          'requests': methods,
                                          'authorized_project': {'id': own['id'], 'name': own['name']},
                                          'private_project_control': denied,
                                          'db_created': (project/'data/db.sqlite').is_file(),
                                          'db_bytes': (project/'data/db.sqlite').stat().st_size if (project/'data/db.sqlite').is_file() else None}
            check('host observes ordinary application effect and private-project control',
                  own['id'] == project_id and own['name'] == 'T02 Ordinary Project' and
                  denied['code'] == 403 and report['host_observation']['db_created'])
            remove_pair('first')
            check('owned workspace and SQLite state retained after container replacement',
                  (project/'data/db.sqlite').is_file() and
                  (project/'data/db.sqlite').stat().st_size > 0 and db_path.is_file())
            start_pair('replacement')
            session = api('session.get', '--param', 'sessionID=' + session_id).get('data', {})
            report['native_session_after_replacement'] = {
                'ids': native_ids(), 'cost': session.get('cost'), 'parentID': session.get('parentID')}
            check('exact native session survives app/researcher replacement with zero cost',
                  report['native_session_after_replacement'] ==
                  {'ids': [session_id], 'cost': 0, 'parentID': None} and
                  not (workspace/'telemetry/request-names.jsonl').exists())
            for _ in range(50):
                try:
                    ready = request('GET', '/robots.txt')
                    if ready['status'] == 200:
                        break
                except (RuntimeError, ValueError):
                    time.sleep(0.1)
            else:
                raise RuntimeError('replacement app readiness failed')
            own_again = observer_case.result(alice('getProjectById', [project_id]), 'retained authorized project')
            denied_again = observer_case.denial(bob('getProjectById', [project_id]), 'retained private control')
            report['host_observation_after_replacement'] = {
                'authorized_project': {'id': own_again['id'], 'name': own_again['name']},
                'private_project_control': denied_again,
                'db_bytes': (project/'data/db.sqlite').stat().st_size}
            check('host observes retained ordinary effect and control in replacement',
                  own_again['id'] == project_id and own_again['name'] == 'T02 Ordinary Project' and
                  denied_again['code'] == 403)
            remove_pair('replacement')
            with sqlite3.connect('file:' + str(db_path) + '?mode=ro', uri=True) as db:
                quick_check = db.execute('PRAGMA quick_check').fetchone()[0]
                rows = db.execute('SELECT id,cost FROM session_v2 ORDER BY id').fetchall()
            report['stopped_native_store'] = {'quick_check': quick_check, 'sessions':
                                               [{'id': row[0], 'cost': row[1]} for row in rows]}
            check('host reads intact exact native session after clean stop',
                  quick_check == 'ok' and report['stopped_native_store']['sessions'] ==
                  [{'id': session_id, 'cost': 0.0}] and
                  (project/'data/db.sqlite').is_file())
            check('source and config pins unchanged', all(sha(HERE/name) == digest for name, digest in pins.items()) and
                  sha(archive) == report['application']['archive_sha256'])
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)[:240]}
        if container:
            logs = run('docker', 'container', 'logs', '--tail', '20', container)
            report['app_log_tail'] = (logs.stdout + logs.stderr)[-1000:]
    finally:
        if observer:
            removed = run('docker', 'container', 'rm', '--force', '--volumes', observer)
            absent = run('docker', 'container', 'inspect', observer).returncode != 0
            report['cleanup'].append({'role': 'host_client', 'stage': active_stage, 'id': observer,
                                      'remove_exit': removed.returncode, 'absent': absent})
        if container:
            removed = run('docker', 'container', 'rm', '--force', '--volumes', container)
            absent = run('docker', 'container', 'inspect', container).returncode != 0
            report['cleanup'].append({'role': 'researcher_app', 'stage': active_stage, 'id': container,
                                      'remove_exit': removed.returncode, 'absent': absent})
        report['host_port_published'] = False
        report['workspace_removed'] = 'workspace' in locals() and not workspace.parent.exists()
        report['status'] = ('offline_ordinary_app_pass' if not report.get('error') and
                            all(x['status'] == 'pass' for x in report['checks']) and
                            len(report['cleanup']) == len(report['resources']) and
                            all(x['absent'] for x in report['cleanup']) and not report['host_port_published'] and
                            report['workspace_removed'] else 'offline_ordinary_app_failed')
        save()
    print(output)
    return 0 if report['status'] == 'offline_ordinary_app_pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
