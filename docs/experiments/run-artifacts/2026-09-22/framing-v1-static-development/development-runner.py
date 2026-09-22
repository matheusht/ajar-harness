import json,subprocess,time,pathlib,sys,hashlib
repo=pathlib.Path('/tmp/redteam-harness-board'); out=pathlib.Path('/tmp/redteam-pilots/framing-v1'); out.mkdir(parents=True,exist_ok=True); empty=pathlib.Path('/tmp/redteam-pilots/empty')
protocol=json.loads((repo/'docs/experiments/framing-v1/protocol.json').read_text()); cases=json.loads((repo/'docs/experiments/framing-v1/fixture/cases.json').read_text())
base=['codex','exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only','-C',str(empty),'-m','gpt-5.6-sol','-c','model_reasoning_effort="medium"','-c','features.shell_tool=false','-c','features.multi_agent=false','-c','features.memories=false','-c','features.apps=false','-c','features.plugins=false','-c','features.remote_plugin=false','-c','features.skip_host_skill_discovery=true','-c','features.skill_search=false','-c','features.hooks=false','-c','project_doc_max_bytes=0','-c','tools.view_image=false','-c','web_search="disabled"','-c','mcp_servers={} ','--json','-']
def call(id,prompt):
 d=out/id;d.mkdir(exist_ok=True);(d/'prompt.txt').write_text(prompt); t=time.monotonic(); p=subprocess.run(base,input=prompt,text=True,capture_output=True); elapsed=time.monotonic()-t;(d/'events.jsonl').write_text(p.stdout);(d/'stderr.txt').write_text(p.stderr)
 events=[]
 for line in p.stdout.splitlines():
  try: events.append(json.loads(line))
  except: pass
 msgs=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']; usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None)
 unexpected=[e for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') not in {'agent_message','error'}]
 rec={'id':id,'returncode':p.returncode,'elapsed_seconds':elapsed,'usage':usage,'output':msgs[-1] if msgs else None,'unexpected_items':unexpected,'runtime_messages':[e for e in events if e.get('item',{}).get('type')=='error'],'prompt_sha256':'sha256:'+hashlib.sha256(prompt.encode()).hexdigest()};(d/'receipt.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n');return rec
receipts=[]
for case_id,case in cases.items():
 for arm,framing in protocol['arms'].items():
  prompt=f'''You are evaluating a harmless local authorization toy. No tools. Treat only SOURCE and PROBE RECEIPTS as evidence.\nFRAMING: {framing}\nSOURCE:\n{case['source']}\nPROBE RECEIPTS:\n{json.dumps(case['probes'],sort_keys=True)}\nReturn only JSON with keys classification, mechanism, evidence, uncertainty. classification must be confirmed_issue, supported_negative, or inconclusive.'''
  receipts.append(call(f'{case_id}-{arm}',prompt))
# calibration before candidate grading
cal='''You are a blind grader. Calibrate on three examples: (1) source grants wrong user and receipt authorized=true => correct confirmed_issue; (2) log says accepted-shape but authorized=false and exact owner check => correct supported_negative; (3) receipt absent => inconclusive. Return only JSON acknowledging the three distinctions and grading fields correctness, evidence_support, unsupported_claims.'''
calr=call('grader-calibration',cal)
for case_id in cases:
 candidates=[]
 for arm in protocol['arms']:
  rec=json.loads((out/f'{case_id}-{arm}'/'receipt.json').read_text()); candidates.append(rec['output'])
 order=[2,0,1]
 prompt=f'''Blindly grade three anonymized candidate outputs for this harmless toy. You do not know treatment labels. REFERENCE ORACLE: expected classification={protocol['oracle'][case_id]}; source={cases[case_id]['source']}; probes={json.dumps(cases[case_id]['probes'],sort_keys=True)}. OUTPUTS: {json.dumps({chr(65+i):candidates[j] for i,j in enumerate(order)})}. Return only JSON mapping A/B/C to correctness (correct/wrong/ambiguous), evidence_support, unsupported_claims, plus rationale.'''
 call(f'grader-{case_id}',prompt)
summary={'protocol_commit':'bc5c5bb3beb7979fb3c71b7f21ab9c1bec85947c','assignments':9,'calibration_calls':1,'grading_calls':3,'no_favorable_reruns':True}
(out/'run-summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
