#!/usr/bin/env python3
"""Public Q02 admission regressions; disposable benign inputs only."""
import copy
import hashlib
import json
import io
import os
import runpy
import shutil
from contextlib import redirect_stdout
from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys
import tempfile

TOOL = Path(__file__).with_name('q02_compare.py')


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)


def main():
    checks = 0
    with tempfile.TemporaryDirectory(prefix='q02-admission-') as directory:
        root = Path(directory)
        source = root / 'source'
        for folder in (source, source / 'arm-a', source / 'arm-b'):
            folder.mkdir()
            (folder / '.record-kernel.lock').touch()
        for arm, ids in [('arm-a', ['one', 'two', 'three']), ('arm-b', ['one'])]:
            for package_id in ids:
                package = source / arm / 'findings' / package_id
                package.mkdir(parents=True)
                (package / 'finding.json').write_bytes(encoded({
                    'id': package_id, 'engagement': 'benign-fixture', 'owasp': 'LLM07',
                    'surface': 'synthetic', 'objective': 'benign fixture',
                    'scope_class': 'proxy_safe', 'severity': 'info', 'confidence': 'confirmed',
                    'attempt_id': 'synthetic-attempt', 'control_attempt_id': 'synthetic-control',
                    'oracle_verdict': {'signal': True, 'adjudication': True,
                                       'contamination_ruled_out': True},
                    'dedup_key': package_id, 'status': 'open'}))
        measurement_path, worksheet_path = root / 'measurement.json', root / 'worksheet.json'
        measured = run('measure', '--engagement', source, '--case-id', 'case-1',
                       '--run-id', 'run-1', '--worksheet', worksheet_path)
        assert measured.returncode == 0, measured.stderr
        measurement_path.write_text(measured.stdout)
        measurement = json.loads(measured.stdout)
        worksheet = json.loads(worksheet_path.read_bytes())
        binding = {'case_id': 'case-1', 'run_id': 'run-1', 'adjudicator': 'reviewer-1',
                   'measurement_sha256': digest(measurement_path.read_bytes()),
                   'source_sha256': measurement['source']['sha256']}
        assessment = {'schema_version': 1, **binding,
                      'compatibility': {'M1_unit': 'legacy_packages', 'M6_unit': 'root_cause_groups',
                                        'compatible': True, 'basis': 'Operator attestation for benign fixture'},
                      'packages': [{'arm': arm, 'package_id': package_id, 'eligible': True,
                                    'root_cause_group': 'shared'}
                                   for arm in ('arm_a', 'arm_b')
                                   for package_id in measurement[arm]['package_inventory']]}
        assessment_path = root / 'eligibility.json'
        worksheet.update({'schema_version': 1, **binding, 'blinding_held': True,
                          'run_record': {'ran_concurrently': True, 'cross_arm_read_occurred': False,
                                         'limit_truncated_an_arm': False},
                          'M6_overlap': {'both_arms': 1, 'arm_a_only': 0, 'arm_b_only': 0}})

        def invoke(m=None, w=None, a=None, expected='prompt_earns_its_keep', error=False,
                   raw_m=lambda data: data, raw_w=lambda data: data, raw_a=lambda data: data):
            nonlocal checks
            m = copy.deepcopy(measurement if m is None else m)
            w = copy.deepcopy(worksheet if w is None else w)
            a = copy.deepcopy(assessment if a is None else a)
            measurement_path.write_bytes(raw_m(encoded(m)))
            for record in (w, a):
                record['measurement_sha256'] = digest(measurement_path.read_bytes())
            assessment_path.write_bytes(raw_a(encoded(a)))
            if w.get('eligibility_ref') is None:
                w['eligibility_ref'] = {'path': str(assessment_path),
                                        'sha256': digest(assessment_path.read_bytes())}
            worksheet_path.write_bytes(raw_w(encoded(w)))
            result = run('verdict', '--measurements', measurement_path, '--worksheet', worksheet_path)
            checks += 1
            if error:
                assert result.returncode == 1 and 'VERDICT:' not in result.stdout and 'licenses:' not in result.stdout, result
                assert 'Traceback' not in result.stderr, result.stderr
            else:
                assert result.returncode == 0 and f'VERDICT: {expected}' in result.stdout, result
                assert 'licenses:' in result.stdout, result.stdout
                if expected == 'inconclusive':
                    assert 'no prompt conclusion' in result.stdout.lower(), result.stdout
            return result

        result = invoke()
        assert 'M1(A)=3, M1(B)=1' in result.stdout, result.stdout
        w = copy.deepcopy(worksheet); w['blinding_held'] = None
        invoke(w=w, expected='inconclusive')
        w['blinding_held'] = 'true'; invoke(w=w, error=True)
        for field in ('blinding_held',):
            for value in (False, None):
                w = copy.deepcopy(worksheet); w[field] = value
                invoke(w=w, expected='inconclusive')
            w = copy.deepcopy(worksheet); del w[field]
            invoke(w=w, expected='inconclusive')
        for field in ('ran_concurrently', 'cross_arm_read_occurred', 'limit_truncated_an_arm'):
            for value in (None,):
                w = copy.deepcopy(worksheet); w['run_record'][field] = value
                invoke(w=w, expected='inconclusive')
            for value in ('false', 0, []):
                w = copy.deepcopy(worksheet); w['run_record'][field] = value
                invoke(w=w, error=True)
        for field in ('cross_arm_read_occurred', 'limit_truncated_an_arm'):
            w = copy.deepcopy(worksheet); w['run_record'][field] = True
            assert 'preregistration guard tripped' in invoke(w=w, expected='inconclusive').stdout
        for value in (-1, 0.5, True, '1'):
            w = copy.deepcopy(worksheet); w['M6_overlap']['both_arms'] = value
            invoke(w=w, error=True)
        w = copy.deepcopy(worksheet); w['M6_overlap']['both_arms'] = 3
        invoke(w=w, error=True)
        for field in ('package_inventory', 'M1_findings', 'M2_candidates'):
            for value in ('one', ['one', 'one'], ['']):
                m = copy.deepcopy(measurement); m['arm_a'][field] = value
                invoke(m=m, error=True)
        for field in ('M5_attempts', 'M5_events', 'M5_subagents'):
            m = copy.deepcopy(measurement); m['arm_a'][field] = True
            invoke(m=m, error=True)
        for field in ('case_id', 'run_id', 'adjudicator'):
            w = copy.deepcopy(worksheet); w[field] = None
            invoke(w=w, expected='inconclusive')
            for value in ('', 7):
                w = copy.deepcopy(worksheet); w[field] = value
                invoke(w=w, error=True)
        for record_name in ('measurement', 'worksheet', 'eligibility'):
            for value in (2, None, '1'):
                record = copy.deepcopy({'measurement': measurement, 'worksheet': worksheet,
                                        'eligibility': assessment}[record_name])
                if value is None:
                    record.pop('schema_version')
                else:
                    record['schema_version'] = value
                invoke(**{{'measurement': 'm', 'worksheet': 'w', 'eligibility': 'a'}[record_name]: record},
                       expected='inconclusive', error=isinstance(value, str))
        a = copy.deepcopy(assessment); a['packages'].append(a['packages'][0].copy())
        invoke(a=a, error=True)
        a = copy.deepcopy(assessment); a['packages'][0]['root_cause_group'] = None
        invoke(a=a, expected='inconclusive')
        a = copy.deepcopy(assessment); a['packages'][0]['package_id'] = 'unknown'
        invoke(a=a, error=True)
        for field in ('arm', 'package_id'):
            a = copy.deepcopy(assessment); a['packages'][0].pop(field)
            invoke(a=a, expected='inconclusive')
        for field in ('schema_version',):
            w = copy.deepcopy(worksheet); w[field] = None
            invoke(w=w, error=True)
        w = copy.deepcopy(worksheet); w['run_record']['ran_concurrently'] = False
        invoke(w=w, expected='inconclusive')
        w['run_record']['sequence_order_if_sequential'] = 'arm_a_then_arm_b'
        invoke(w=w)
        for value in (False, None):
            a = copy.deepcopy(assessment); a['compatibility']['compatible'] = value
            invoke(a=a, expected='inconclusive')
        a = copy.deepcopy(assessment); a['compatibility']['M1_unit'] = 'root_cause_groups'
        invoke(a=a, expected='inconclusive')
        for field in ('source_sha256', 'case_id', 'run_id', 'adjudicator'):
            a = copy.deepcopy(assessment); a[field] = '0' * 64 if 'sha256' in field else 'different'
            invoke(a=a, error=True)
        w = copy.deepcopy(worksheet); w['eligibility_ref'] = {'path': str(root / 'missing'), 'sha256': 'a' * 64}
        invoke(w=w, expected='inconclusive')
        w['eligibility_ref']['path'] = str(assessment_path)
        invoke(w=w, error=True)
        for dimension in ('raw_m', 'raw_w', 'raw_a'):
            invoke(**{dimension: lambda data: b'{'}, error=True)
            invoke(**{dimension: lambda data: data.replace(b'{', b'{"schema_version":1,', 1)}, error=True)
        # Malformed input wins over a separate missing integrity answer.
        w = copy.deepcopy(worksheet); w['blinding_held'] = None; w['M6_overlap']['both_arms'] = -1
        invoke(w=w, error=True)
        w = copy.deepcopy(worksheet); w['M7_waste']['waste_class_a_avoided_that_b_hit'] = '  '
        invoke(w=w, error=True)
        w['M7_waste']['waste_class_a_avoided_that_b_hit'] = 'benign wasted review'
        invoke(w=w, expected='inconclusive')
        waste_source = root / 'waste-note.txt'; waste_source.write_text('Benign review evidence.\n')
        waste_record = {'schema_version': 1, **binding, 'assertion': 'benign wasted review',
                        'source_refs': [{'path': str(waste_source), 'sha256': digest(waste_source.read_bytes())}]}
        # invoke writes the canonical measurement; pin those exact bytes for this separate record.
        waste_record['measurement_sha256'] = digest(encoded(measurement))
        waste_path = root / 'waste.json'; waste_path.write_bytes(encoded(waste_record))
        w['waste_ref'] = {'path': str(waste_path), 'sha256': digest(waste_path.read_bytes())}
        invoke(w=w)
        waste_source.write_text('Changed review evidence.\n'); invoke(w=w, error=True)
        # A readable notes-only package and unreviewed revisions cannot enter M1.
        finding_path = source / 'arm-a' / 'findings' / 'one' / 'finding.json'
        original = finding_path.read_bytes()
        finding_path.write_bytes(original + b' '); invoke(error=True)
        finding_path.write_bytes(original)
        # Re-measure changed layouts so their inventory is honestly committed.
        for layout in ('notes', 'revision'):
            if layout == 'notes':
                finding_path.unlink(); (finding_path.parent / 'notes.md').write_text('Benign notes only.')
            else:
                finding_path.write_bytes(original)
                (finding_path.parent / 'revisions').mkdir()
                (finding_path.parent / 'revisions' / 'unreviewed.json').write_text('{}')
            result = run('measure', '--engagement', source, '--case-id', 'case-1', '--run-id', 'run-1')
            assert result.returncode == 0, result
            m = json.loads(result.stdout); w = copy.deepcopy(worksheet); a = copy.deepcopy(assessment)
            w['source_sha256'] = a['source_sha256'] = m['source']['sha256']
            invoke(m=m, w=w, a=a, expected='inconclusive')
            # Excluding that package preserves admission of the other supported packages.
            a['packages'][0]['eligible'] = False; a['packages'][0].pop('root_cause_group')
            invoke(m=m, w=w, a=a, expected='inconclusive')  # M1 gap 1 without cost evidence.
            if layout == 'notes':
                (finding_path.parent / 'notes.md').unlink()
            else:
                (finding_path.parent / 'revisions' / 'unreviewed.json').unlink()
                (finding_path.parent / 'revisions').rmdir()
        # Re-establish the complete bound control for publication-race regressions.
        invoke()
        module = runpy.run_path(str(TOOL), run_name='q02_admission_test')
        globals_ = module['cmd_verdict'].__globals__
        verdict_args = SimpleNamespace(measurements=str(measurement_path),
                                       worksheet=str(worksheet_path), prereg=module['PREREG'])

        def marker(folder):
            path = folder / 'legacy' / 'quarantine' / 'ledger-quarantined.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
            return path

        def blocked_call(command, args):
            nonlocal checks
            output = io.StringIO()
            try:
                with redirect_stdout(output):
                    command(args)
            except SystemExit:
                pass
            else:
                raise AssertionError('publication was not blocked')
            assert output.getvalue() == '', output.getvalue()
            checks += 1

        # Run the shared public helper too; loose dictionaries stay non-decisive.
        result = module['decide'](measurement, worksheet, 2)
        assert result[0] == 'inconclusive'
        checks += 1
        original_license = globals_['_license_text_for_verdict']
        for mutation in ('quarantine', 'source_bytes', 'assessment_bytes'):
            original_assessment = assessment_path.read_bytes()
            def before_publication(doc, verdict):
                if mutation == 'quarantine':
                    marker(source)
                elif mutation == 'source_bytes':
                    finding_path.write_bytes(original + b' ')
                else:
                    assessment_path.write_bytes(original_assessment + b' ')
                return original_license(doc, verdict)
            globals_['_license_text_for_verdict'] = before_publication
            try:
                blocked_call(module['cmd_verdict'], verdict_args)
            finally:
                globals_['_license_text_for_verdict'] = original_license
                if mutation == 'quarantine':
                    shutil.rmtree(source / 'legacy')
                finding_path.write_bytes(original)
                assessment_path.write_bytes(original_assessment)
        original_snapshot = globals_['_snapshot_bound_tree']
        for target in (source, source / 'arm-a'):
            aside = root / 'renamed-source'
            swapped = False
            def renamed(fd):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    target.rename(aside)
                    shutil.copytree(aside, target)
                return original_snapshot(fd)
            globals_['_snapshot_bound_tree'] = renamed
            try:
                blocked_call(module['cmd_verdict'], verdict_args)
            finally:
                globals_['_snapshot_bound_tree'] = original_snapshot
                shutil.rmtree(target); aside.rename(target)
        # Existing measurement boundary: no worksheet or stdout if a marker wins final admission.
        original_require = globals_['require_not_quarantined']
        source_identity = source.stat()
        root_checks = 0
        def final_marker(bound):
            nonlocal root_checks
            identity = os.fstat(int(Path(bound).name))
            if (identity.st_dev, identity.st_ino) == (source_identity.st_dev, source_identity.st_ino):
                root_checks += 1
                if root_checks == 2:
                    marker(source)
            return original_require(bound)
        globals_['require_not_quarantined'] = final_marker
        prevented_worksheet = root / 'prevented-worksheet.json'
        try:
            blocked_call(module['cmd_measure'], SimpleNamespace(engagement=str(source),
                         worksheet=str(prevented_worksheet), force=False))
            assert not prevented_worksheet.exists()
        finally:
            globals_['require_not_quarantined'] = original_require
            shutil.rmtree(source / 'legacy')
        # Missing source is incomplete; quarantined, symlinked or changed sources are input errors.
        aside = root / 'unavailable-source'; source.rename(aside)
        try:
            invoke(expected='inconclusive')
        finally:
            aside.rename(source)
        link = source / 'arm-a' / 'unsafe-link'; link.symlink_to(finding_path)
        try:
            invoke(error=True)
        finally:
            link.unlink()
        # An old loose input remains inspectable but never gets a fresh decisive license.
        old = {'arm_a': {'M1_findings': ['x', 'y', 'z']}, 'arm_b': {'M1_findings': []}}
        w = copy.deepcopy(worksheet); w.pop('source_sha256')
        w['M6_overlap'] = {'both_arms': 0, 'arm_a_only': 0, 'arm_b_only': 0}
        invoke(m=old, w=w, a={**assessment, 'packages': []}, expected='inconclusive')
    print(f'Q02 ADMISSION SELF-TEST: PASS ({checks} public controls)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
