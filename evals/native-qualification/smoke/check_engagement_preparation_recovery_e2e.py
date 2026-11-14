#!/usr/bin/env python3
"""Failure-first startup recovery scenarios; simulated peers, real journal and runner."""
from __future__ import annotations
import argparse, copy, json, os, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'evals/native-qualification/smoke')]
import check_engagement_native_boundary_e2e as fixture
from engagement_contract import canonical, digest
from engagement_controller import Controller
from engagement_runner import Runner, WorkerContext, frozen_inputs


def require(value, message):
    if not value: raise AssertionError(message)


def scenario(root, name):
    boundary, case, context, stack = fixture.simulated_boundary(root)
    instance = boundary.NativeBoundary(context)
    original = fixture.SimulatedEnvironment.prepare
    events = []
    def interrupted(environment, *args, **kwargs):
        dispatch = case.c.state()['dispatches'][context.grant['dispatch_id']]
        events.append(dispatch.get('setup_started_at') is not None)
        if name != 'before-environment': original(environment, *args, **kwargs)
        if name == 'proxy-admission': return
        raise boundary.BoundaryError('fixture_environment_setup_interrupted')
    with stack:
        if name == 'proxy-admission':
            def proxy_started(*args, **kwargs):
                require(case.c.state()['dispatches'][context.grant['dispatch_id']].get('native_admitted') is True,
                        'native admission marker missing before proxy construction')
                raise boundary.BoundaryError('fixture_environment_setup_interrupted')
            stack.enter_context(patch.object(boundary, 'ProxyBridge', proxy_started))
        if name in ('missing-marker', 'late-marker'):
            stack.enter_context(patch.object(case.c, 'record_preparation_setup', lambda grant: None, create=True))
        with patch.object(fixture.SimulatedEnvironment, 'prepare', interrupted):
            try: instance.start()
            except boundary.BoundaryError as error:
                require(error.code == 'fixture_environment_setup_interrupted', 'wrong setup refusal')
            else: raise AssertionError('injected setup failure did not stop startup')
        require(not fixture.SimulatedRuntime.instances and instance.owner_receipt is None,
                'native runtime started before setup failure')
        if name == 'late-marker':
            try: Controller.record_preparation_setup(case.c, context.grant)
            except Exception: pass
            else: raise AssertionError('late setup phase was registered after environment effects')
        if name == 'native-admitted':
            # The admission record is a durable hold even if no owner was captured.
            case.c.record_native_admission(context.grant)
        if name == 'identity-evolution':
            cleanup = fixture.SimulatedEnvironment.cleanup
            def complete_identity(environment):
                environment.identity = dict(environment.identity, prepared_image_id='sha256:' + 'c' * 64)
                operation = {'kind': 'environment-observation-v2', 'operation': 'remove_input_image',
                    'operation_id': 'resolved-input-image', 'identity': environment.receipt()}
                environment.observe(dict(operation, phase='intent'))
                environment.observe(dict(operation, phase='result', status='settled'))
                return cleanup(environment)
            stack.enter_context(patch.object(fixture.SimulatedEnvironment, 'cleanup', complete_identity))
        if name == 'unresolved-cleanup': fixture.SimulatedEnvironment.cleanup_fails = True
        if name == 'in-process':
            finished = instance.finish()
            require(finished['cleanup'] == 'verified', 'owned pre-native cleanup remained unresolved')
            settled = Runner._settle(context.runner, context, instance, time.monotonic() - 2.1)
            require(settled, 'runner did not settle owned setup failure')
            require(case.c.state()['usage']['worker_seconds'] == 3, 'setup elapsed charge was lost')
        else:
            # Drop all in-memory native boundary state, reopen journal and recover.
            for gate in (instance.provider_gate, instance.lab_gate):
                if gate is not None: gate.close()
            case.c.revoke_worker('lead-1', 1, reason='fixture-process-loss')
            reopened = Controller(case.c.root)
            context.runner.controller = reopened
            context.runner.contract = frozen_inputs(reopened)
            state = reopened.state()
            if name == 'identity-changed':
                cleanup = fixture.SimulatedEnvironment.cleanup
                def wrong(environment):
                    result = cleanup(environment)
                    result['identity'] = dict(result['identity'], container_id='b' * 64)
                    return result
                stack.enter_context(patch.object(fixture.SimulatedEnvironment, 'cleanup', wrong))
            result = boundary.recover_boundary(context, state['dispatches'][context.grant['dispatch_id']])
            expected = name not in ('unresolved-cleanup', 'identity-changed', 'native-admitted', 'proxy-admission', 'missing-marker', 'late-marker')
            require((result['status'] == 'settled') == expected, 'recovery acceptance mismatch: ' + str(result))
        state = context.controller.state(); dispatch = state['dispatches'][context.grant['dispatch_id']]
        if name in ('unresolved-cleanup', 'identity-changed', 'native-admitted', 'proxy-admission', 'missing-marker', 'late-marker'):
            require(state['resource_holds'] and state['usage']['invocations'] == 1
                    and dispatch['status'] in ('pending', 'unknown'), 'uncertain startup was refunded or released')
        else:
            require(events == [True], 'durable setup marker was not recorded before Environment.prepare')
            require(dispatch['status'] == 'settled' and state['workers']['lead-1']['status'] == 'stopped'
                    and state['cleanup'] == 'verified' and not state['resource_holds']
                    and state['usage']['invocations'] == 0 and state['usage']['reserved_worker_seconds'] == 0,
                    'verified setup cleanup did not release exactly its reservation')
            before = copy.deepcopy(state['usage'])
            repeat = boundary.recover_boundary(context, dispatch)
            require(repeat['status'] == 'settled' and context.controller.state()['usage'] == before,
                    'recovery charged or refunded a second time')
        # These are only local host fixture artifacts; no unproved external owner is removed.
        for directory in (instance.socket_dir, instance.state_dir):
            if directory is not None and directory.exists():
                import shutil
                shutil.rmtree(directory)
        return {'status': dispatch['status'], 'cleanup': state['cleanup'], 'usage': state['usage'],
                'native_runtime_starts': len(fixture.SimulatedRuntime.instances)}


def registration(root):
    boundary, case, context, stack = fixture.simulated_boundary(root)
    with stack:
        case.c.record_preparation_setup(context.grant)
        revision = case.c.state()['revision']
        case.c.record_preparation_setup(context.grant)
        require(case.c.state()['revision'] == revision, 'duplicate phase rewrote journal')
        wrong = dict(context.grant, generation=2)
        for grant in (wrong, dict(context.grant, dispatch_id='other-dispatch')):
            try: case.c.record_native_admission(grant)
            except Exception: pass
            else: raise AssertionError('foreign authority changed startup phase')
        case.c.record_native_admission(context.grant)
        revision = case.c.state()['revision']
        case.c.record_native_admission(context.grant)
        require(case.c.state()['revision'] == revision, 'duplicate admission rewrote journal')
        try: case.c.record_preparation_setup(context.grant)
        except Exception: pass
        else: raise AssertionError('native admission was reversed to no-native setup')
        return {'monotonic_phase': True, 'foreign_authority_refused': True}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); os.umask(0o077); checks=[]
    with tempfile.TemporaryDirectory(prefix='preparation-recovery-') as folder:
        for name in ('in-process', 'reopened', 'identity-evolution', 'before-environment', 'unresolved-cleanup', 'identity-changed', 'native-admitted', 'proxy-admission', 'missing-marker', 'late-marker', 'registration'):
            root=Path(folder).resolve()/name;root.mkdir(mode=0o700)
            try: checks.append({'scenario':name,'status':'passed','result':registration(root) if name == 'registration' else scenario(root,name)})
            except Exception as error: checks.append({'scenario':name,'status':'failed','error':str(error)})
    result={'classification':'engineering_simulation_real_journal_runner_boundary', 'status':'passed' if all(r['status']=='passed' for r in checks) else 'failed', 'checks':checks,
        'provider_calls':0,'docker_calls':0,'ssh_calls':0,
        'source_sha256':{name:digest((ROOT/name).read_bytes()) for name in ('tools/engagement_native_boundary.py','tools/engagement_controller.py','tools/engagement_runner.py','tools/engagement_evidence.py',str(Path(__file__).relative_to(ROOT)))},
        'unverified':['Docker/SSH cleanup','live provider behavior','native process containment','research acceptance']}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
