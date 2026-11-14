#!/usr/bin/env python3
"""Public v2 evidence workflows; protected observations are engineering simulations.

Run: python3 evals/native-qualification/smoke/check_engagement_evidence_e2e.py
     --output /tmp/engagement-evidence.json
Requires Python 3 and ssh-keygen. No model, target, container, or remote is used.
Expected: every scenario passes; temporary keys/workspaces are removed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from engagement_contract import canonical, digest, load_inputs
from engagement_controller import Controller, ControllerError, Principal

spec = importlib.util.spec_from_file_location('evidence_fixture', Path(__file__).with_name('check_engagement_contract_e2e.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def require(condition, text):
    if not condition:
        raise AssertionError(text)


def refused(code, call):
    try:
        call()
    except ControllerError as error:
        require(error.code == code, f'{error.code} != {code}')
    else:
        raise AssertionError('accepted forbidden operation: ' + code)


class Case:
    def __init__(self, path, *, start=True, patch=False, broad=False):
        self.path = path
        self.inputs = fixture.make_fixture(path / 'input')
        scope = fixture.fixture_scope(self.inputs)
        scope['limits']['hard']['invocations'] = 100
        scope['limits']['max_workers'] = 10
        scope['patch_required'] = patch
        scope['goal_mode'] = 'broad' if broad else 'bounded'
        fixture.resign_fixture(self.inputs, scope)
        self.contract = load_inputs(self.inputs)
        self.c = Controller.initialize(path / 'engagement', self.contract, evidence_class='engineering_simulation')
        self.lead = Principal('worker', 'lead-1', 1)
        self.serial = 0
        self.workspaces = {}
        if start:
            self.start('lead-1')

    def workspace(self, worker):
        if worker not in self.workspaces:
            path = self.path / ('workspace-' + worker)
            path.mkdir(mode=0o700)
            self.workspaces[worker] = path
        return self.workspaces[worker]

    def owner(self, worker, session=None):
        return {'kind': 'native-runtime-owner-v1', 'runtime': 'codex',
            'session_id': session or 'session-' + worker,
            'profile_sha256': self.contract.scope['runtime_assignments'][0]['profile_sha256'],
            'boundary': 'darwin-no-fork-v1',
            'process': {'pid': 34567, 'pgid': 34567, 'uid': 501,
                        'started_seconds': 1, 'started_microseconds': 2}}

    def start(self, worker, session=None):
        self.c.record_worker_started(worker, 1, session or 'session-' + worker,
            self.workspace(worker), owner_receipt=self.owner(worker, session))

    def request(self, kind, data, actor=None):
        self.serial += 1
        return self.c.submit(actor or self.lead, {'request_id': f'req-{self.serial}',
            'expected_revision': self.c.state()['revision'], 'type': kind, 'payload': data})

    def worker(self, name, role='specialist', start=True):
        self.request('worker_request', {'worker_id': name, 'role': role,
            'profile_id': 'runtime-main', 'question': 'Inspect harmless evidence.'})
        if start:
            self.start(name)
        return Principal('worker', name, 1)

    def task(self, name, resources=None):
        self.request('task_create', {'task_id': name, 'question': 'Inspect fixture.', 'priority': 1,
            'resources': resources or [], 'prerequisites': [], 'evidence_refs': []})

    def grant(self, actor=None, resources=None):
        actor = actor or self.lead
        return self.c.prepare_dispatch(actor.id, actor.generation, seconds=30,
            resources=resources or [], adapter_id='fixture-adapter')

    def settle(self, grant, unknown=False):
        observation = {'status': 'unknown' if unknown else 'settled', 'worker_seconds': 1,
            'resources': {r: 'unknown' if unknown else 'unchanged' for r in grant['resources']},
            'usage': {'tokens': {'input': 2, 'output': 3}, 'cost': None}, 'cleanup': 'pending'}
        receipt = self.c.store_receipt(grant, observation, adapter_id=grant['adapter_id'])
        self.c.adopt_receipt(grant['dispatch_id'], receipt, adapter_id=grant['adapter_id'])

    def publication(self, name):
        self.request('publish', {'publication_id': name, 'kind': 'observation', 'subject': name,
            'body': 'Harmless observed evidence.', 'refs': [], 'supersedes': [], 'artifacts': []})

    def instrument(self, name='instrument-1', reset='clean-copy', supersedes=None):
        artifact = self.c.store_object(b'print("harmless measurement")\n')
        self.request('instrument_register', {'instrument_id': name, 'artifact_sha256': artifact,
            'metric': 'fixture-signal', 'reset': reset, 'conditions': {'fixture': 'one'},
            'supersedes': supersedes or []})

    def observe(self, grant, op, nonce, output=b'fixture-signal\n', support_inputs=None):
        profile = self.contract.environment_profiles['lab-main']
        profile_sha = digest(json.dumps(profile, sort_keys=True, separators=(',', ':')).encode())
        access = copy.deepcopy(self.contract.scope['access'][0])
        identity = {'kind': 'research-environment-receipt-v2', 'nonce': nonce,
            'container_id': 'a' * 64, 'container_name': 'oslit-' + nonce,
            'stage_container_id': None, 'stage_container_name': 'oslit-' + nonce + '-stage',
            'prepared_image_id': None, 'prepared_image_name': 'oslit-input-' + nonce + ':latest',
            'unsettled': [], 'daemon_id': 'fixture-daemon', 'image_id': profile['image_id'],
            'profile_sha256': profile_sha, 'support_inputs': support_inputs or [],
            'access': [{k: access[k] for k in ('id', 'kind', 'identity')}]}
        common = {'kind': 'environment-observation-v2', 'operation': 'execute',
            'operation_id': op, 'identity': identity}
        self.c.record_environment_observation(grant, 'lab-main', dict(common,
            phase='intent', request_sha256=digest(b'fixture command')), effect_id='read-source')
        self.c.record_environment_observation(grant, 'lab-main', dict(common,
            phase='result', status='settled', returncode=0, output_sha256=digest(output)),
            effect_id='read-source')
        self.c.record_environment_output(grant, 'lab-main', op, output)
        return identity

    def experiment(self, name, actor=None, purpose='effect', explains=None,
                   nonce='1' * 32, instrument='instrument-1', score=1, patch_info=None):
        actor = actor or self.lead
        grant = self.grant(actor, ['source-main'])
        identity = self.observe(grant, 'op-' + name, nonce)
        self.settle(grant)
        if patch_info is not None:
            patch_id, arm, manifest = patch_info
            self.c.record_patch_execution(grant, 'lab-main', 'op-' + name, patch_id, arm, manifest)
        candidate = self.c.store_object(b'fixture candidate')
        probe = self.c.store_object(b'fixture probe')
        measured = self.c.state()['instruments'][instrument]
        self.c.record_experiment_execution(grant, 'lab-main', 'op-' + name, {
            'instrument_id': instrument, 'instrument_sha256': measured['artifact_sha256'],
            'candidate_sha256': candidate, 'probe_sha256': probe, 'conditions': {'fixture': 'one'},
            'reset': measured['reset'], 'clean_start': True})
        self.request('experiment_record', {'experiment_id': name, 'instrument_id': instrument,
            'candidate_sha256': candidate, 'probe_sha256': probe, 'operation_id': 'op-' + name,
            'purpose': purpose, 'conditions': {'fixture': 'one'}, 'score': score,
            'resources': ['source-main'], 'explains': explains, 'supersedes': []}, actor)
        return grant, identity

    def claim(self, replay=None):
        self.request('claim_propose', {'claim_id': 'claim-1', 'text': 'A harmless fixture effect.',
            'effect': 'effect', 'control': 'control', 'replay': replay,
            'contrary': ['contrary'], 'resources': ['source-main'], 'supersedes': []})

    def packet(self, kind, subject, reviewer='reviewer-1'):
        actor = self.worker(reviewer, 'reviewer', start=False)
        result = self.request('review_request', {'review_id': 'review-' + subject,
            'kind': kind, 'subject_id': subject, 'reviewer_id': reviewer})
        self.start(reviewer)
        return actor, result['result']['payload']['packet_sha256']

    def review(self, subject, actor, packet, disposition='accept', evidence=None, contrary=None):
        return self.request('review_result', {'review_id': 'review-' + subject,
            'packet_sha256': packet, 'disposition': disposition,
            'checks': {k: True for k in ('measurement', 'permissions', 'causal_control', 'clean_replay', 'completeness')},
            'evidence_refs': evidence or [], 'contrary_refs': contrary or [],
            'reason': 'The frozen fixture evidence supports this bounded decision.'}, actor)


def bootstrap(x):
    workspace = x.workspace('lead-1')
    grant = x.c.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
        resources=['source-main'], adapter_id='fixture-adapter')
    require(x.c.state()['workers']['lead-1']['status'] == 'preparing', 'preparation state missing')
    require(x.c.prepare_worker_dispatch('lead-1', 1, workspace, seconds=30,
        resources=['source-main'], adapter_id='fixture-adapter') == grant, 'retry changed grant')
    refused('worker_stale', lambda: x.request('claim', {}))
    require(x.c.authorize_dispatch(grant), 'host bootstrap grant rejected')
    x.start('lead-1')
    require(x.c.authorize_dispatch(grant), 'started bootstrap grant rejected')
    refused('session_dispatch_pending', lambda: x.c.record_worker_session('lead-1', 1, 'new-context', reason='process_loss'))
    x.settle(grant)
    x.c.record_worker_session('lead-1', 1, 'new-context', reason='process_loss')
    require(x.c.state()['workers']['lead-1']['session_id'] == 'new-context', 'session not recorded')
    specialist = x.worker('specialist-1', start=False)
    x.task('setup', ['source-main'])
    x.request('task_assign', {'task_id': 'setup', 'worker_id': specialist.id})
    specialist_grant = x.c.prepare_worker_dispatch(specialist.id, 1, x.workspace(specialist.id),
        seconds=30, resources=['source-main'], adapter_id='fixture-adapter')
    require(specialist_grant['assignment']['task_id'] == 'setup', 'pending assignment lost')
    x.c.revoke_worker(specialist.id, 1, reason='fixture-stop')
    refused('worker_stale', lambda: x.c.authorize_dispatch(specialist_grant))


def overlap_bundle(x):
    bundle = Path(x.contract.runtime_profiles['runtime-main']['tool_bundle']['path'])
    refused('engagement_root_overlap', lambda: Controller.initialize(bundle / 'controller', x.contract))
    require(not (bundle / 'controller').exists(), 'prohibited directory was created')
    x.worker('bundle-worker', start=False)
    refused('worker_workspace_overlap', lambda: x.c.record_worker_started('bundle-worker', 1,
        'bad-session', bundle))
    refused('worker_workspace_overlap', lambda: x.c.prepare_worker_dispatch('bundle-worker', 1,
        bundle, seconds=30, resources=[], adapter_id='fixture-adapter'))


def large_contract(x):
    inputs = json.loads(x.inputs.read_bytes())
    profile_path = Path(inputs['runtime_profiles']['runtime-main'])
    profile = json.loads(profile_path.read_bytes())
    config_path = Path(profile['config_file'])
    config_path.write_bytes(canonical({'fixture': 'x' * (1024 * 1024 + 100)}))
    profile['config_sha256'] = digest(config_path.read_bytes())
    profile_path.write_bytes(canonical(profile))
    scope = fixture.fixture_scope(x.inputs)
    scope['runtime_assignments'][0]['profile_sha256'] = digest(profile_path.read_bytes())
    fixture.resign_fixture(x.inputs, scope)
    contract = load_inputs(x.inputs)
    c = Controller.initialize(x.path / 'large-engagement', contract, evidence_class='engineering_simulation')
    require(c.state()['revision'] == 1, 'large frozen config cannot replay')
    c.export(x.path / 'large-export')


def evidence(x):
    x.publication('contrary')
    x.instrument()
    x.experiment('effect')
    x.experiment('control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'fixture_switch'})
    x.claim()
    require(x.c.state()['claims']['claim-1']['state'] == 'supported', 'effect-only confirmation')
    actor, packet = x.packet('claim', 'claim-1')
    refused('review_evidence_incomplete', lambda: x.review('claim-1', actor, packet, contrary=['contrary']))
    x.experiment('replay', actor, purpose='replay', explains={'experiment_id': 'effect', 'variable': None}, nonce='2' * 32)
    refused('review_contrary_missing', lambda: x.review('claim-1', actor, packet, evidence=['replay']))
    x.review('claim-1', actor, packet, evidence=['replay'], contrary=['contrary'])
    require(x.c.state()['claims']['claim-1']['state'] == 'independently_confirmed', 'complete fresh review not accepted')
    x.publication('unrelated')
    require(x.c.state()['claims']['claim-1']['state'] == 'independently_confirmed', 'unrelated publication invalidated claim')
    x.instrument('instrument-2', reset='new-reset', supersedes=['instrument-1'])
    require(x.c.state()['claims']['claim-1']['state'] == 'needs_review', 'material scorer supersession ignored')
    exported = x.path / 'evidence-export'
    x.c.export(exported)
    result = json.loads((exported / 'result.json').read_bytes())
    require(result['claims']['claim-1']['state'] == 'needs_review', 'export lost claim state')


def forged_and_comparison(x):
    x.instrument()
    x.experiment('effect')
    bad = copy.deepcopy(x.c.state()['experiments']['effect'])
    data = {k: bad[k] for k in ('instrument_id', 'candidate_sha256', 'probe_sha256', 'purpose', 'conditions', 'score', 'resources', 'explains', 'supersedes')}
    data.update(experiment_id='forged', operation_id='fake-op')
    refused('environment_observation_missing', lambda: x.request('experiment_record', data))
    x.instrument('instrument-2', reset='different')
    x.experiment('different', instrument='instrument-2')
    refused('experiment_not_comparable', lambda: x.request('experiment_compare',
        {'comparison_id': 'comparison-1', 'experiments': ['effect', 'different']}))
    fresh = x.worker('not-fresh', 'reviewer')
    x.publication('contrary')
    x.experiment('control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'fixture_switch'})
    x.claim()
    refused('reviewer_not_fresh', lambda: x.request('review_request', {'review_id': 'review-bad',
        'kind': 'claim', 'subject_id': 'claim-1', 'reviewer_id': fresh.id}))


def obligations(x):
    x.publication('contrary')
    x.request('strategy_challenge', {'obligation_id': 'challenge-1', 'kind': 'contradiction',
        'refs': ['contrary'], 'resources': ['source-main'], 'reason': 'The prior premise conflicts with this observation.'})
    first = x.grant()
    x.c.record_obligation_delivery('challenge-1', 'lead-1', 1, dispatch_id=first['dispatch_id'])
    x.settle(first)
    x.c.record_decision_checkpoint(first)
    x.c.record_decision_checkpoint(first)
    require(x.c.state()['obligations']['challenge-1']['opportunities'] == 1, 'duplicate checkpoint counted')
    second = x.grant()
    x.c.record_obligation_delivery('challenge-1', 'lead-1', 1, dispatch_id=second['dispatch_id'])
    refused('checkpoint_unsettled', lambda: x.c.record_decision_checkpoint(second))
    x.settle(second)
    x.c.record_decision_checkpoint(second)
    require(x.c.state()['replacement_required'], 'two nonresponses did not require replacement')
    refused('worker_not_stopped', lambda: x.c.replace_lead('lead-1', 1))
    x.c.revoke_worker('lead-1', 1, reason='unanswered-obligations')
    refused('worker_stale', lambda: x.request('claim', {}))
    refused('worker_not_stopped', lambda: x.c.replace_lead('lead-1', 1))
    require(x.c.state()['obligations']['challenge-1']['state'] == 'pending', 'replacement erased obligation')


def rebuttal(x):
    x.publication('contrary')
    x.request('strategy_challenge', {'obligation_id': 'challenge-1', 'kind': 'strong_lead_dismissal',
        'refs': ['contrary'], 'resources': ['source-main'], 'reason': 'Dismissal lacks a discriminating observation.'})
    x.request('review_response', {'obligation_id': 'challenge-1', 'action': 'rebuttal',
        'refs': ['contrary'], 'reason': 'The observed state may reflect the documented reset boundary.'})
    state = x.c.state()
    require(state['obligations']['challenge-1']['state'] == 'disputed', 'rebuttal silently ignored or accepted')
    require(not state['replacement_required'], 'substantive response counted as nonresponse')
    refused('direction_held', lambda: x.grant(resources=['source-main']))


def closure(x):
    x.task('unresolved', ['source-main'])
    refused('closure_incomplete', lambda: x.request('closure_request', {'closure_id': 'done',
        'outcome': 'goal_met', 'claim_ids': [], 'remaining': [], 'reason': 'A first claim alone is insufficient.'}))
    x.request('closure_request', {'closure_id': 'bounded-negative', 'outcome': 'covered_dry',
        'claim_ids': [], 'remaining': ['unresolved'], 'reason': 'Only the harmless fixture condition was inspected.'})
    actor, packet = x.packet('closure', 'bounded-negative')
    x.review('bounded-negative', actor, packet, disposition='reopen')
    state = x.c.state()
    require(state['closures']['bounded-negative']['state'] == 'reopened', 'rejected closure lost reopen state')
    require(any(o['kind'] == 'reopen' for o in state['obligations'].values()), 'reopen obligation missing')
    refused('closure_not_reviewed', lambda: x.c.finalize_closure('bounded-negative'))


def ownership_cleanup(x):
    owner = x.owner('lead-1')
    bad = dict(owner, profile_sha256='sha256:' + '0' * 64)
    refused('runtime_owner_invalid', lambda: x.c.record_worker_started('lead-1', 1,
        'session-lead-1', x.workspace('lead-1'), owner_receipt=bad))
    x.start('lead-1')
    state = x.c.state()
    sha = state['workers']['lead-1']['runtime_owner_sha256']
    require(json.loads(x.c.read_object(sha)) == owner, 'owner receipt not frozen')
    grant = x.grant(resources=['source-main'])
    identity = x.observe(grant, 'observed-stop', '3' * 32)
    x.settle(grant)
    x.c.revoke_worker('lead-1', 1, reason='fixture-stop')
    runtime = {'session_id': 'session-lead-1', 'owner_receipt_sha256': sha,
        'process_exited': True, 'child_absence': 'not_observed', 'capabilities_revoked': True}
    readback = {'environment': {'status': 'stopped', 'running': False, 'identity': identity}, 'runtime': runtime}
    refused('worker_stop_unverified', lambda: x.c.record_worker_stopped(grant, 'lab-main', readback))
    runtime['child_absence'] = 'verified'
    bad = copy.deepcopy(readback)
    bad['environment']['identity']['daemon_id'] = 'different-daemon'
    refused('environment_identity_changed', lambda: x.c.record_worker_stopped(grant, 'lab-main', bad))
    x.c.record_worker_stopped(grant, 'lab-main', readback)
    require(x.c.state()['workers']['lead-1']['status'] == 'stopped', 'stop proof not recorded')
    x.c.record_environment_cleanup(grant, 'lab-main', {'status': 'clean', 'identity': identity,
        'owned_workspace': 'container_removed'})
    require(x.c.state()['cleanup'] == 'verified', 'cleanup proof not recorded')
    x.c.export(x.path / 'owner-export')
    require((x.path / 'owner-export/objects' / sha[7:]).is_file(), 'export omitted owner receipt')


def patch(x):
    x.publication('contrary')
    x.instrument()
    x.experiment('effect')
    x.experiment('control', purpose='control', explains={'experiment_id': 'effect', 'variable': 'fixture_switch'})
    x.claim()
    bad_diff = x.c.store_object(b'diff --git a/x b/x\nnew file mode 120000\n--- /dev/null\n+++ b/x\n@@ -0,0 +1 @@\n+/etc/passwd\n')
    refused('patch_diff_unsafe', lambda: x.request('patch_propose', {'patch_id': 'bad',
        'claim_id': 'claim-1', 'source_access': 'source-main', 'diff_sha256': bad_diff, 'supersedes': []}))
    diff = x.c.store_object(b'--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print("harmless fixture ready")\n+print("harmless patched fixture ready")\n')
    x.request('patch_propose', {'patch_id': 'patch-1', 'claim_id': 'claim-1',
        'source_access': 'source-main', 'diff_sha256': diff, 'supersedes': []})
    material = x.c.state()['patches']['patch-1']
    original = json.loads(x.c.read_object(material['original_manifest_sha256']))
    patched = json.loads(x.c.read_object(material['patched_manifest_sha256']))
    require(original != patched, 'patch did not change pinned bytes')
    actor, packet = x.packet('patch', 'patch-1')
    refused('patch_checks_incomplete', lambda: x.review('patch-1', actor, packet))
    pairs = []
    for index, purpose in enumerate(('effect', 'control', 'normal_function', 'variant')):
        for arm, manifest in (('original', original), ('patched', patched)):
            name = purpose + '-' + arm
            x.experiment(name, actor, purpose=purpose, nonce=f'{index * 2 + (1 if arm == "original" else 2) + 20:032x}',
                patch_info=('patch-1', arm, manifest))
            pairs.append(name)
    x.review('patch-1', actor, packet, evidence=pairs)
    require(x.c.state()['patches']['patch-1']['state'] == 'accepted', 'complete patch review not accepted')
    x.c.export(x.path / 'patch-export')
    require((x.path / 'patch-export/objects' / material['patched_manifest_sha256'][7:]).is_file(),
        'patch manifest not exported')
    x.instrument('instrument-updated', reset='new-reset', supersedes=['instrument-1'])
    require(x.c.state()['patches']['patch-1']['state'] == 'needs_review', 'accepted patch survived changed measurement')


def unbound_execution(x):
    x.instrument()
    grant = x.grant(resources=['source-main'])
    x.observe(grant, 'unbound', '4' * 32)
    x.settle(grant)
    candidate = x.c.store_object(b'fixture candidate')
    probe = x.c.store_object(b'fixture probe')
    refused('experiment_execution_unbound', lambda: x.request('experiment_record', {
        'experiment_id': 'unbound', 'instrument_id': 'instrument-1', 'candidate_sha256': candidate,
        'probe_sha256': probe, 'operation_id': 'unbound', 'purpose': 'effect',
        'conditions': {'fixture': 'one'}, 'score': 1, 'resources': ['source-main'],
        'explains': None, 'supersedes': []}))


def late_delivery(x):
    x.publication('contrary')
    x.request('strategy_challenge', {'obligation_id': 'late', 'kind': 'contradiction',
        'refs': ['contrary'], 'resources': [], 'reason': 'A real delivery must precede a completed decision.'})
    grant = x.grant()
    x.settle(grant)
    refused('obligation_not_delivered', lambda: x.c.record_decision_checkpoint(grant))
    refused('delivery_after_completion', lambda: x.c.record_obligation_delivery('late', 'lead-1', 1,
        dispatch_id=grant['dispatch_id']))


def complete_closure(x):
    lead_grant = x.grant(resources=['source-main'])
    lead_identity = x.observe(lead_grant, 'lead-close', '5' * 32)
    x.settle(lead_grant)
    x.request('closure_request', {'closure_id': 'honest-negative', 'outcome': 'covered_dry',
        'claim_ids': [], 'remaining': [], 'reason': 'Only the harmless fixture condition was inspected.'})
    actor, packet = x.packet('closure', 'honest-negative')
    reviewer_grant = x.grant(actor, ['source-main'])
    reviewer_identity = x.observe(reviewer_grant, 'reviewer-close', '6' * 32)
    x.settle(reviewer_grant)
    x.review('honest-negative', actor, packet)
    for grant, env_identity in ((lead_grant, lead_identity), (reviewer_grant, reviewer_identity)):
        worker = x.c.state()['workers'][grant['worker_id']]
        x.c.revoke_worker(worker['id'], worker['generation'], reason='reviewed-closeout')
        x.c.record_worker_stopped(grant, 'lab-main', {'environment': {'status': 'stopped',
            'running': False, 'identity': env_identity}, 'runtime': {'session_id': worker['session_id'],
            'owner_receipt_sha256': worker['runtime_owner_sha256'], 'process_exited': True,
            'child_absence': 'verified', 'capabilities_revoked': True}})
        x.c.record_environment_cleanup(grant, 'lab-main', {'status': 'clean', 'identity': env_identity,
            'owned_workspace': 'container_removed'})
    x.c.finalize_closure('honest-negative')
    require(x.c.state()['status'] == 'closed', 'reviewed negative did not close after stop and cleanup')
    refused('engagement_stopped', lambda: x.c.prepare_dispatch('lead-1', 1, seconds=5,
        resources=[], adapter_id='fixture-adapter'))
    x.c.export(x.path / 'closed-export')
    require(json.loads((x.path / 'closed-export/result.json').read_bytes())['status'] == 'closed', 'closed export lost ending')


def stale_closure(x):
    x.request('closure_request', {'closure_id': 'old-negative', 'outcome': 'covered_dry',
        'claim_ids': [], 'remaining': [], 'reason': 'Only the prior fixture state was inspected.'})
    actor, packet = x.packet('closure', 'old-negative')
    x.task('new-material-work')
    refused('review_stale', lambda: x.review('old-negative', actor, packet))


def registered_support(x):
    from engagement_contract import source_manifest
    grant = x.grant(resources=['source-main'])
    path = x.path / 'bootstrap'
    path.mkdir(mode=0o700)
    (path / 'method.md').write_text('Inspect the harmless fixture under signed authority.\n')
    manifest = source_manifest(path)
    sha = digest(canonical(manifest))
    x.c.register_support_inputs(grant, {'bootstrap': {'path': str(path), 'manifest_sha256': sha}})
    x.observe(grant, 'bootstrap-observed', '7' * 32, support_inputs=[{'id': 'bootstrap', 'manifest_sha256': sha}])
    require(sha in x.c.state()['evidence_objects'], 'registered manifest was not frozen')
    refused('support_registration_late', lambda: x.c.register_support_inputs(grant,
        {'later': {'path': str(path), 'manifest_sha256': sha}}))


def object_bound(x):
    refused('object_size_limit', lambda: x.c.store_object(b'x' * (4 * 1024 * 1024 + 1)))
    require(x.c.state()['status'] == 'active', 'oversize object corrupted journal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', default='all')
    args = parser.parse_args()
    scenarios = {'bootstrap': (bootstrap, {'start': False}), 'bundle-overlap': (overlap_bundle, {}),
        'large-contract': (large_contract, {}), 'evidence': (evidence, {}),
        'forged-comparison': (forged_and_comparison, {}), 'obligations': (obligations, {}),
        'rebuttal': (rebuttal, {}), 'closure': (closure, {'broad': True}),
        'ownership-cleanup': (ownership_cleanup, {'start': False}), 'patch': (patch, {'patch': True}), 'unbound-execution': (unbound_execution, {}), 'late-delivery': (late_delivery, {}),
        'complete-closure': (complete_closure, {}), 'stale-closure': (stale_closure, {}), 'registered-support': (registered_support, {}), 'object-bound': (object_bound, {})}
    report = {'kind': 'engagement-evidence-e2e-v2', 'classification': 'engineering_simulation',
        'provider_calls': 0, 'research_acceptance': 'not_run', 'scenarios': [],
        'source_sha256': {name: digest((ROOT / name).read_bytes()) for name in
            ('tools/engagement_controller.py', 'tools/engagement_evidence.py', 'evals/native-qualification/smoke/check_engagement_evidence_e2e.py')}}
    for name, (function, options) in scenarios.items():
        if args.scenario not in ('all', name):
            continue
        with tempfile.TemporaryDirectory(prefix='oslit-evidence-') as tmp:
            try:
                case = Case(Path(tmp).resolve(), **options)
                function(case)
                report['scenarios'].append({'id': name, 'status': 'passed'})
            except Exception as error:
                report['scenarios'].append({'id': name, 'status': 'failed',
                    'error': type(error).__name__ + ': ' + str(error)})
    report['passed'] = bool(report['scenarios']) and all(r['status'] == 'passed' for r in report['scenarios'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report))
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
