#!/usr/bin/env python3
"""Public provider-free #204 checked-setup transition scenario.

This regenerates a harmless synthetic #202 v2 package with local Docker. It
does not execute a native model or target service. See SETUP-TO-RESEARCH-E2E.md.
"""

import argparse
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / 'tools/native_research.py'
BUILDER_SCENARIO = ROOT / 'evals/native-qualification/smoke/check_native_setup_builder_e2e.py'
sys.path.insert(0, str(ROOT / 'tools'))
import native_continuation as continuation
import native_research as runner


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(*args, timeout=90):
    result = subprocess.run([sys.executable, str(NATIVE), *args], cwd=ROOT,
                            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                            capture_output=True, text=True, timeout=timeout, check=False)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        payload = {'code': 'non_json_cli_output', 'stderr': result.stderr[:1000]}
    return result.returncode, payload


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-root', type=Path)
    args = parser.parse_args()
    if args.keep_root:
        if not args.keep_root.is_absolute() or args.keep_root.exists():
            parser.error('--keep-root must be a new absolute directory')
        args.keep_root.mkdir(mode=0o700)
    checks = []

    def check(name, passed, observed):
        checks.append({'name': name, 'passed': bool(passed), 'observed': observed})

    context = (nullcontext(str(args.keep_root)) if args.keep_root else
               tempfile.TemporaryDirectory(prefix='native-setup-to-research-e2e-'))
    with context as raw:
        base = Path(raw).resolve()
        builder_output = base / 'builder-e2e.json'
        builder_root = base / 'builder-fixture'
        built = subprocess.run([sys.executable, str(BUILDER_SCENARIO),
                                '--output', str(builder_output), '--keep-root', str(builder_root)],
                               cwd=ROOT, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                               capture_output=True, text=True, timeout=180, check=False)
        builder_evidence = json.loads(builder_output.read_text()) if builder_output.exists() else {}
        check('fresh v2 checked setup fixture is available',
              built.returncode == 0 and builder_evidence.get('passed') is True,
              {'exit': built.returncode, 'builder_checks': len(builder_evidence.get('checks', []))})
        if built.returncode:
            raise RuntimeError('builder fixture failed: ' + built.stderr[:1000])
        setup_root = Path(builder_evidence['fixture_roots']['v2'])
        setup_controls = setup_root / 'controls'
        setup_plan = json.loads((setup_root / 'plan.json').read_text())
        checked = json.loads((setup_controls / 'setup-checked/receipt.json').read_text())
        research_scope = base / 'research-scope.md'
        research_scope.write_text('# Synthetic research scope\n\n'
                                  '- Synthetic fixture: unsigned; no live authority.\n'
                                  '- Surfaces: owned harmless source copy.\n'
                                  '- Benign objective: assess a concrete unsafe effect with a control.\n'
                                  '- Effect ceiling: offline source checks on owned copies.\n'
                                  '- Cleanup: stop and remove all owned research resources.\n')
        research = base / 'research'
        limits = ('--max-connections', '2', '--max-bytes', '1048576',
                  '--duration-seconds', '120')
        prepare = ('prepare-checked', '--run-root', str(research),
                   '--checked-setup-root', str(setup_root),
                   '--scope-file', str(research_scope), '--scope-sha256', sha(research_scope),
                   *limits)

        def rejected(name, arguments, expected_code=None):
            code, result = cli(*arguments)
            check(name, code == 2 and not Path(arguments[arguments.index('--run-root') + 1]).exists()
                  and (expected_code is None or result.get('code') == expected_code),
                  {'exit': code, 'code': result.get('code')})

        missing = setup_controls / 'setup-checked/receipt.json'
        missing.rename(missing.with_name('receipt-held.json'))
        rejected('missing checked receipt refuses before research root',
                 prepare)
        missing.with_name('receipt-held.json').rename(missing)
        source_file = setup_root / 'original/main.txt'
        source_bytes = source_file.read_bytes()
        source_file.write_text('changed source\n')
        rejected('changed frozen source refuses before research root', prepare)
        source_file.write_bytes(source_bytes)
        source_mode = stat.S_IMODE(source_file.stat().st_mode)
        source_file.chmod(source_mode ^ stat.S_IXUSR)
        rejected('changed source mode refuses before research root', prepare)
        source_file.chmod(source_mode)
        output_file = setup_controls / 'setup-checked/output/out/result.txt'
        output_bytes = output_file.read_bytes()
        output_file.write_text('changed output\n')
        rejected('changed checked output refuses before research root', prepare)
        output_file.write_bytes(output_bytes)
        dependency_file = setup_controls / 'setup-checked/dependencies/payload/data.txt'
        dependency_bytes = dependency_file.read_bytes()
        dependency_file.write_text('changed dependency\n')
        rejected('changed offline dependency refuses before research root', prepare)
        dependency_file.write_bytes(dependency_bytes)
        dependency_mode = stat.S_IMODE(dependency_file.stat().st_mode)
        dependency_file.chmod(dependency_mode ^ stat.S_IXUSR)
        rejected('changed offline dependency mode refuses before research root', prepare)
        dependency_file.chmod(dependency_mode)
        wrong_scope = list(prepare)
        wrong_scope[wrong_scope.index('--scope-file') + 1] = str(setup_controls / 'scope.md')
        wrong_scope[wrong_scope.index('--scope-sha256') + 1] = sha(setup_controls / 'scope.md')
        rejected('setup-only scope cannot become research scope', wrong_scope)
        edited_setup_scope = base / 'setup-scope-byte-edited.md'
        edited_setup_scope.write_bytes((setup_controls / 'scope.md').read_bytes() + b'\n')
        edited_scope = list(prepare)
        edited_scope[edited_scope.index('--scope-file') + 1] = str(edited_setup_scope)
        edited_scope[edited_scope.index('--scope-sha256') + 1] = sha(edited_setup_scope)
        rejected('byte-edited setup-only scope cannot become research scope',
                 edited_scope, 'separate_research_scope_required')
        spaced_setup_scope = base / 'setup-scope-spaced-fence.md'
        spaced_setup_scope.write_bytes((setup_controls / 'scope.md').read_bytes().replace(
            b'```native-setup-scope-v1', b'``` native-setup-scope-v1'))
        spaced_scope = list(prepare)
        spaced_scope[spaced_scope.index('--run-root') + 1] = str(base / 'spaced-scope-research')
        spaced_scope[spaced_scope.index('--scope-file') + 1] = str(spaced_setup_scope)
        spaced_scope[spaced_scope.index('--scope-sha256') + 1] = sha(spaced_setup_scope)
        rejected('space-edited setup-only scope cannot become research scope',
                 spaced_scope, 'separate_research_scope_required')
        wrong_hash = list(prepare)
        wrong_hash[wrong_hash.index('--scope-sha256') + 1] = '0' * 64
        rejected('changed research scope pin refuses preparation', wrong_hash)
        nested_root = setup_root / 'controls/setup-checked/nested-research'
        nested = list(prepare)
        nested[nested.index('--run-root') + 1] = str(nested_root)
        rejected('research root inside checked package refuses before copy', nested,
                 'checked_setup_run_root_overlap')
        partial_root = base / 'partial-research'
        (partial_root / 'controls/checked-setup').mkdir(parents=True)
        (partial_root / 'controls/checked-setup/incomplete').write_text('interrupted copy\n')
        partial = list(prepare)
        partial[partial.index('--run-root') + 1] = str(partial_root)
        partial_code, partial_result = cli(*partial)
        check('interrupted preparation root cannot be resealed',
              partial_code == 2 and not (partial_root / 'plan.json').exists(),
              {'exit': partial_code, 'code': partial_result.get('code')})
        code, prepared = cli(*prepare)
        check('public checked preparation seals research plan',
              code == 0 and prepared.get('status') == 'prepared_provider_free' and research.is_dir(),
              {'exit': code, 'status': prepared.get('status'),
               'plan_sha256': prepared.get('plan_sha256')})
        if code:
            raise RuntimeError('checked research preparation failed: ' + str(prepared))
        plan = json.loads((research / 'plan.json').read_text())
        package = plan.get('checked_setup', {})
        recipe = json.loads((setup_controls / 'setup-output/recipe.json').read_text())
        check('plan derives runtime build and target image from checked setup',
              plan.get('source_only', {}).get('runtime') == recipe['runtime']
              and plan['source_only']['build_command'] == recipe['build_command']
              and plan['target_image_id'] == checked['image_id']
              and plan['platform'] == checked['platform']
              and plan['source_manifest_sha256'] == checked['source_manifest_sha256']
              and package['source_mode_sha256'] == checked['source_mode_sha256']
              and package['cumulative_setup_used'] == checked['cumulative_setup_used']
              and plan['brief_sha256'] == checked['goal_sha256']
              and plan['source_effect_envelope']['readonly_host_mount']
              == '/deps:offline_dependencies'
              and plan['limits'] == {'max_connections': 2, 'max_bytes': 1048576,
                                     'duration_seconds': 120},
              {'source_manifest_sha256': plan.get('source_manifest_sha256'),
               'target_image_id': plan.get('target_image_id')})
        allowance = {'active': True, 'hard_limits': plan['limits'],
                     'run_identity': {'nonce': 'synthetic'}, 'used_tunnels': 0,
                     'charged_tunnel_bytes': 0}
        with patch.object(runner, '_approval_active'), \
             patch.object(runner, 'run_active', return_value=True), \
             patch.object(runner, '_unresolved_dispatches', return_value=[]), \
             patch.object(runner, 'allowance_snapshot', return_value=allowance), \
             patch.object(runner, '_source_executor_envelope'), \
             patch.object(runner, '_load_review_module', return_value=SimpleNamespace(
                 _sessions=lambda *args: [])):
            source_gate = continuation._source_preflight(
                research, {'plan_sha256': sha(research / 'plan.json')}, 'a' * 64)
            check('checked effect envelope admits agent source action',
                  source_gate['status'] == 'authorized',
                  {'status': source_gate['status']})
            review_gate = continuation._review_preflight(research, {})
            review_status = review_gate[3]
            check('checked effect envelope admits agent fresh review',
                  review_status in ('reviewer-1', 'reviewer-2'),
                  {'status': review_status})
        controls = research / 'controls'
        initial = controls / 'research/checked-setup/INITIAL_THREAT_MODEL.md'
        trace = controls / 'research/checked-setup/SETUP_TRACE.json'
        check('read-only research inputs retain original threat and trace',
              initial.is_file() and trace.is_file()
              and sha(initial) == package.get('initial_threat_model_sha256')
              and sha(trace) == package.get('setup_trace_sha256'),
              {'threat_sha256': sha(initial) if initial.exists() else None,
               'trace_sha256': sha(trace) if trace.exists() else None})
        replay = base / 'mounted-replay'
        shutil.copytree(research / 'target', replay)
        mounted = subprocess.run([
            'docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--pids-limit', '64', '--user', f'{os.getuid()}:{os.getgid()}',
            '--mount', f'type=bind,src={replay},dst=/target',
            '--mount', f'type=bind,src={controls / "source-modules"},dst=/deps,readonly',
            '--workdir', '/target', plan['target_image_id'], 'sh', '-c',
            'if (echo denied > /deps/data.txt) 2>/dev/null; then exit 41; fi; '
            'sha256sum /deps/data.txt; sh build.sh; sha256sum out/result.txt'],
            capture_output=True, text=True, timeout=30, check=False)
        readback = [line.split()[0] for line in mounted.stdout.splitlines()]
        check('offline Docker reads pinned /deps and builds disposable source copy',
              mounted.returncode == 0
              and readback == [checked['dependencies']['data.txt']['sha256'],
                               checked['outputs']['out/result.txt']['sha256']]
              and sha(controls / 'source-modules/data.txt')
              == checked['dependencies']['data.txt']['sha256'],
              {'exit': mounted.returncode, 'readback_sha256': readback})
        approval = base / 'research-approval-invalid.json'
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = lambda value: value.strftime('%Y-%m-%dT%H:%M:%SZ')
        approval.write_text(json.dumps({
            'kind': 'native-research-live-approval-v1', 'plan_sha256': '0' * 64,
            'scope_sha256': plan['scope_sha256'], 'provider_route': plan['provider_route'],
            'provider_authority': plan['provider_authority'], 'model': plan['model'],
            'image_id': plan['image_id'], 'target_image_id': plan['target_image_id'],
            'limits': plan['limits'], 'approved_by': 'synthetic-operator',
            'approved_at': stamp(now), 'expires_at': stamp(now + timedelta(hours=1))},
            sort_keys=True) + '\n')
        wrong_code, wrong_approval = cli('start', '--run-root', str(research),
                                         '--approval', str(approval))
        check('research plan approval mismatch refuses before Docker',
              wrong_code == 2 and wrong_approval.get('code') == 'live_approval_mismatch'
              and not (controls / 'resources.json').exists(),
              {'exit': wrong_code, 'code': wrong_approval.get('code')})
        held_setup_root = setup_root.with_name(setup_root.name + '-held')
        setup_root.rename(held_setup_root)
        isolated_code, isolated = cli('start', '--run-root', str(research),
                                       '--approval', str(approval))
        check('sealed research plan rechecks without original setup root',
              isolated_code == 2 and isolated.get('code') == 'live_approval_mismatch'
              and not (controls / 'resources.json').exists(),
              {'exit': isolated_code, 'code': isolated.get('code')})
        held_setup_root.rename(setup_root)
        archived_threat = controls / 'checked-setup/THREAT_MODEL.md'
        threat_bytes = archived_threat.read_bytes()
        archived_threat.write_text('swapped\n')
        swap_code, swapped = cli('start', '--run-root', str(research), '--approval', str(approval))
        check('swapped archived threat refuses before Docker',
              swap_code == 2 and not (controls / 'resources.json').exists(),
              {'exit': swap_code, 'code': swapped.get('code')})
        archived_threat.write_bytes(threat_bytes)
        plan_file = research / 'plan.json'
        original_plan_bytes = plan_file.read_bytes()
        missing_envelope = dict(plan)
        missing_envelope.pop('source_effect_envelope')
        plan_file.write_text(json.dumps(missing_envelope, sort_keys=True) + '\n')
        envelope_code, envelope_result = cli('start', '--run-root', str(research),
                                              '--approval', str(approval))
        check('missing checked effect envelope refuses before Docker',
              envelope_code == 2
              and envelope_result.get('code') == 'source_effect_envelope_changed'
              and not (controls / 'resources.json').exists(),
              {'exit': envelope_code, 'code': envelope_result.get('code')})
        plan_file.write_bytes(original_plan_bytes)
        archived_output = controls / 'checked-setup/package/output/out/result.txt'
        output_mode = stat.S_IMODE(archived_output.stat().st_mode)
        archived_output.chmod(output_mode ^ stat.S_IXUSR)
        output_code, output_changed = cli('start', '--run-root', str(research),
                                           '--approval', str(approval))
        check('swapped archived output mode refuses before Docker',
              output_code == 2 and not (controls / 'resources.json').exists(),
              {'exit': output_code, 'code': output_changed.get('code')})
        archived_output.chmod(output_mode)
        research_source = research / 'original/main.txt'
        research_source_mode = stat.S_IMODE(research_source.stat().st_mode)
        research_source.chmod(research_source_mode ^ stat.S_IXUSR)
        source_mode_code, source_mode_result = cli('start', '--run-root', str(research),
                                                   '--approval', str(approval))
        check('changed research source mode refuses before Docker',
              source_mode_code == 2 and not (controls / 'resources.json').exists(),
              {'exit': source_mode_code, 'code': source_mode_result.get('code')})
        research_source.chmod(research_source_mode)
        target_script = research / 'target/build.sh'
        target_script_mode = stat.S_IMODE(target_script.stat().st_mode)
        target_script.chmod(target_script_mode ^ stat.S_IXUSR)
        target_mode_code, target_mode_result = cli('start', '--run-root', str(research),
                                                   '--approval', str(approval))
        check('changed pristine target script mode refuses before Docker',
              target_mode_code == 2
              and target_mode_result.get('code') == 'checked_setup_pristine_source_mode_changed'
              and not (controls / 'resources.json').exists(),
              {'exit': target_mode_code, 'code': target_mode_result.get('code')})
        target_script.chmod(target_script_mode)
        active_dependency = controls / 'source-modules/data.txt'
        active_dependency_mode = stat.S_IMODE(active_dependency.stat().st_mode)
        active_dependency.chmod(active_dependency_mode ^ stat.S_IXUSR)
        active_dependency_code, active_dependency_result = cli(
            'start', '--run-root', str(research), '--approval', str(approval))
        check('changed active dependency mode refuses before Docker',
              active_dependency_code == 2 and not (controls / 'resources.json').exists(),
              {'exit': active_dependency_code, 'code': active_dependency_result.get('code')})
        active_dependency.chmod(active_dependency_mode)
        approved = base / 'research-approval-valid.json'
        valid_approval = json.loads(approval.read_text())
        valid_approval['plan_sha256'] = sha(research / 'plan.json')
        approved.write_text(json.dumps(valid_approval, sort_keys=True) + '\n')
        image_code, image_gate = cli('start', '--run-root', str(research),
                                     '--approval', str(approved))
        check('valid plan approval reaches pinned agent image gate',
              image_code == 2 and image_gate.get('code') == 'opencode_image_environment_mismatch'
              and not (controls / 'resources.json').exists(),
              {'exit': image_code, 'code': image_gate.get('code')})
        again_code, again = cli(*prepare)
        check('interrupted transition cannot reseal same research root',
              again_code == 2 and sha(research / 'plan.json') == prepared.get('plan_sha256'),
              {'exit': again_code, 'code': again.get('code')})
        before = sha(initial)
        notebook = research / 'researcher/RESEARCH.md'
        with notebook.open('a') as stream:
            stream.write('\n## Later correction\nThe setup threat model needs revision after source review.\n')
        check('later correction leaves original threat model pinned',
              sha(initial) == before and 'Later correction' in notebook.read_text(),
              {'initial_threat_model_sha256': before})
        runtime_file = base / 'runtime.json'
        runtime_file.write_text(json.dumps(recipe['runtime']) + '\n')
        command_file = base / 'command.json'
        command_file.write_text(json.dumps(recipe['build_command']) + '\n')
        ordinary_root = base / 'ordinary-source-only'
        ordinary_code, ordinary = cli(
            'prepare', '--source-only', '--run-root', str(ordinary_root),
            '--source', str(setup_root / 'original'), '--brief', str(setup_controls / 'BRIEF.md'),
            '--scope-file', str(research_scope), '--scope-sha256', sha(research_scope),
            '--relay', str(setup_controls / 'relay'), '--relay-sha256', setup_plan['relay_sha256'],
            '--runtime-ca', str(setup_controls / 'runtime-ca.pem'),
            '--runtime-ca-sha256', setup_plan['runtime_ca_sha256'],
            '--image-id', setup_plan['image_id'], '--target-image-id', checked['image_id'],
            '--platform', checked['platform'], '--source-runtime', str(runtime_file),
            '--build-command', str(command_file),
            '--module-cache', str(setup_controls / 'setup-checked/dependencies/payload'),
            *limits)
        ordinary_plan = json.loads((ordinary_root / 'plan.json').read_text()) if ordinary_root.exists() else {}
        check('ordinary source-only preparation remains available',
              ordinary_code == 0 and 'source_only' in ordinary_plan
              and 'checked_setup' not in ordinary_plan
              and ordinary_plan.get('source_effect_envelope', {}).get('readonly_host_mount')
              == '/modules:offline_dependencies',
              {'exit': ordinary_code, 'code': ordinary.get('code')})
        inputs = {'builder_scenario_sha256': sha(BUILDER_SCENARIO),
                  'builder_evidence_sha256': sha(builder_output),
                  'checked_receipt_sha256': sha(setup_controls / 'setup-checked/receipt.json'),
                  'research_scope_sha256': sha(research_scope),
                  'research_plan_sha256': sha(research / 'plan.json'),
                  'scenario_sha256': sha(Path(__file__))}
        fixture_roots = ({'setup': str(setup_root), 'research': str(research),
                          'ordinary': str(ordinary_root)} if args.keep_root else None)
    result = {'kind': 'native-setup-to-research-synthetic-e2e-v1', 'checks': checks,
              'passed': all(row['passed'] for row in checks), 'inputs': inputs,
              'fixture_roots': fixture_roots,
              'provider_or_model_executed': False, 'target_service_executed': False,
              'classification': 'synthetic setup/provenance and provider-free research preparation',
              'limits': 'No live native research turn, provider qualification, pause/resume, or actual target.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'result': str(args.output)}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
