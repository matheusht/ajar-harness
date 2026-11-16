#!/usr/bin/env python3
"""Failure-first private credential resolution with fake source stores only.

Covers missing/mismatched refs, disabled/ambiguous OMP rows, expired Codex access,
account changes on reload, no repr/pickle disclosure, no persisted copy, and
revoked bindings. Real tokens and provider calls are deliberately absent.
"""
import argparse
import base64
import json
from pathlib import Path
import pickle
import sqlite3
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))


def run(base):
    from native_credentials import HostCredentialResolver
    from native_runtime_transport import RuntimeError
    auth=base/'auth.json';db=base/'agent.db'
    claims={'exp':int(time.time())+3600,'https://api.openai.com/auth':{'chatgpt_account_id':'fixture-account','chatgpt_plan_type':'plus'}}
    def token():return 'fake.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.fake'
    def save_auth():auth.write_text(json.dumps({'tokens':{'access_token':token(),'account_id':'fixture-account'}}));auth.chmod(0o600)
    save_auth()
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE auth_credentials(provider TEXT,credential_type TEXT,data TEXT,disabled_cause TEXT)')
        conn.execute('INSERT INTO auth_credentials VALUES(?,?,?,NULL)',('opencode-go','api_key',json.dumps({'key':'fake-omp-private-key'})))
        conn.execute('INSERT INTO auth_credentials VALUES(?,?,?,NULL)',('mistral','api_key',json.dumps({'key':'fake-mistral-key'})))
    db.chmod(0o600)
    resolver=HostCredentialResolver(environment={'OPENAI_API_KEY':'fake-env-private-key'},codex_auth_path=auth,omp_db_path=db)
    rows=[]
    def profile(kind,ref,provider):return {'kind':kind,'credential_ref':ref,'provider':provider}
    def refuse(name,p,code):
        try:resolver(p);raise AssertionError(name+' admitted')
        except RuntimeError as error:assert str(error)==code,(name,str(error));rows.append({'case':name,'refused':code})
    refuse('wrong_provider',profile('omp','env_OPENAI_API_KEY','anthropic'),'native_credential_provider_mismatch')
    refuse('unknown_ref',profile('omp','other','openai'),'native_credential_reference_unsupported')
    refuse('missing_env',profile('omp','env_ANTHROPIC_API_KEY','anthropic'),'native_credential_unavailable')
    env=resolver(profile('codex','env_OPENAI_API_KEY','openai'));assert env.environment()=={'OPENAI_API_KEY':'fake-env-private-key'}
    omp=resolver(profile('omp','omp_default','opencode-go'));assert omp.environment()=={'OPENCODE_API_KEY':'fake-omp-private-key'}
    mistral=resolver(profile('omp','omp_default','mistral'));assert mistral.environment()=={'MISTRAL_API_KEY':'fake-mistral-key'}
    refuse('mistral_wrong_provider',profile('omp','env_MISTRAL_API_KEY','openai'),'native_credential_provider_mismatch')
    with sqlite3.connect(db) as conn:conn.execute('INSERT INTO auth_credentials VALUES(?,?,?,NULL)',('mistral','api_key',json.dumps({'key':'second-fake-key'})))
    refuse('ambiguous_mistral',profile('omp','omp_default','mistral'),'native_credential_unavailable')
    with sqlite3.connect(db) as conn:conn.execute("UPDATE auth_credentials SET disabled_cause='disabled' WHERE provider='mistral'")
    refuse('disabled_mistral',profile('omp','omp_default','mistral'),'native_credential_unavailable')
    codex=resolver(profile('codex','codex_default','openai'));assert codex.login()['chatgptAccountId']=='fixture-account'
    assert all('fake-' not in repr(x) and 'accessToken' not in repr(x) for x in (env,omp,codex))
    try:pickle.dumps(codex);raise AssertionError('credential binding serialized')
    except TypeError:pass
    codex.refresh('fixture-account')
    try:codex.refresh('different-account');raise AssertionError('cross-account refresh admitted')
    except RuntimeError as error:assert str(error)=='native_credential_account_changed'
    claims['exp']=int(time.time())-1;save_auth()
    refuse('expired_token',profile('codex','codex_default','openai'),'native_credential_expired')
    with sqlite3.connect(db) as conn:conn.execute("UPDATE auth_credentials SET disabled_cause='operator-disabled'")
    refuse('disabled_omp',profile('omp','omp_default','opencode-go'),'native_credential_unavailable')
    env.revoke()
    try:env.environment();raise AssertionError('revoked binding reused')
    except RuntimeError as error:assert str(error)=='native_credential_revoked'
    assert sorted(p.name for p in base.iterdir())==['agent.db','auth.json'],'resolver persisted extra files'
    return {'status':'passed','evidence':'fake_private_source_stores_only','checks':rows,
            'positive_routes':['matching_env','matching_omp_api_key','codex_external_tokens','account_bound_reload'],
            'no_serialization':True,'no_persisted_copy':True,'external_provider_calls':0}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-credentials-') as d:result=run(Path(d).resolve())
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status']}))
