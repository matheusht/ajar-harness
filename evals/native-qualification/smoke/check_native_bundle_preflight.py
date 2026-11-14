#!/usr/bin/env python3
"""Offline, failure-first portable OMP bundle admission checks; no supplied code executes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))


def run(base):
    from engagement_contract import canonical, digest, source_manifest
    from native_runtime_omp import inspect_tool_bundle
    from native_runtime_transport import RuntimeError
    tree = base / 'bundle';tree.mkdir()
    files = {
        'bin/bun': b'\x7fELF\x02\x01\x01' + b'\x00' * 11 + b'\xb7\x00' + b'\x00' * 44,
        'native_runtime_omp_tools.mjs': (ROOT / 'tools/native_runtime_omp_tools.mjs').read_bytes(),
        'node_modules/@oh-my-pi/pi-coding-agent/package.json': json.dumps({
            'name': '@oh-my-pi/pi-coding-agent', 'version': '18.20.0', 'engines': {'bun': '>=1.4.4'}}).encode(),
        'node_modules/@oh-my-pi/pi-natives-linux-arm64/package.json': json.dumps({
            'name': '@oh-my-pi/pi-natives-linux-arm64', 'version': '18.20.0', 'main':'./pi_natives.linux-arm64.node'}).encode(),
        'node_modules/@oh-my-pi/pi-natives-linux-arm64/pi_natives.linux-arm64.node': b'fixture native addon',
        'node_modules/@oh-my-pi/pi-coding-agent/src/sdk.ts': b'// fixture entrypoint',
    }
    for name, data in files.items():
        path=tree / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data);path.chmod(0o500 if name == 'bin/bun' else 0o400)
    profile={'kind':'omp','version':'18.20.0','tool_bundle': {'path':str(tree),'manifest_sha256':'', 'platform':'linux/arm64','bun_version':'1.4.4'}}
    def pin(p):p['tool_bundle']['manifest_sha256']=digest(canonical(source_manifest(tree)))
    pin(profile)
    rows=[]
    def check(name, p, code=None):
        try:
            result=inspect_tool_bundle(p)
            assert code is None, name + ' was accepted'
            assert result['command'][0] == '/input/runtime-main/bin/bun'
            rows.append({'case':name,'status':'passed'})
        except RuntimeError as error:
            assert str(error)==code,(name,str(error),code)
            rows.append({'case':name,'status':'passed','refused':str(error)})
    check('valid_static_fixture',profile)
    changed=copy.deepcopy(profile);changed['tool_bundle']['bun_version']='1.4.0';check('unsupported_bun',changed,'native_bundle_bun_unsupported')
    changed=copy.deepcopy(profile);changed['tool_bundle']['platform']='linux/amd64';check('wrong_bun_arch',changed,'native_bundle_platform_mismatch')
    changed=copy.deepcopy(profile);changed['version']='18.19.0';check('wrong_sdk',changed,'native_bundle_sdk_mismatch')
    sidecar=tree / 'native_runtime_omp_tools.mjs';sidecar.chmod(0o600);sidecar.write_text('// changed');pin(profile)
    check('changed_sidecar',profile,'native_bundle_sidecar_mismatch')
    sidecar.write_bytes(files['native_runtime_omp_tools.mjs']);sidecar.chmod(0o400);pin(profile)
    (tree / 'bin/bun').chmod(0o400);pin(profile);check('nonexecutable_bun',profile,'native_bundle_bun_not_executable')
    (tree / 'bin/bun').chmod(0o500);pin(profile)
    (tree / 'node_modules/@oh-my-pi/pi-natives-linux-arm64/package.json').unlink();pin(profile)
    check('missing_platform_addon',profile,'native_bundle_platform_unavailable')
    return {'status':'passed','evidence':'offline_static_admission_only','cases':rows,'execution':'none'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory() as directory: result=run(Path(directory).resolve())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'cases':len(result['cases'])}))
