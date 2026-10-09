import json,subprocess,time,pathlib,sys,hashlib,os,shutil
repo=pathlib.Path('/tmp/redteam-harness-board'); sys.path.insert(0,str(repo/'tools'))
from engagement_records import sha256_file
from engagement_state import initialize_engagement,_append_kernel_event,base_event,read_ledger
from task_board import post_notice
from task_notice import compile_hunter_notices
out=pathlib.Path('/tmp/redteam-pilots/communication-v2');out.mkdir(parents=True,exist_ok=True);empty=pathlib.Path('/tmp/redteam-pilots/empty')
protocol=json.loads((repo/'docs/experiments/communication-v2/protocol.json').read_text())
base=['codex','exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only','-C',str(empty),'-m','gpt-5.6-sol','-c','model_reasoning_effort="medium"','-c','features.shell_tool=false','-c','features.multi_agent=false','-c','features.memories=false','-c','features.apps=false','-c','features.plugins=false','-c','features.remote_plugin=false','-c','features.skip_host_skill_discovery=true','-c','features.skill_search=false','-c','features.hooks=false','-c','project_doc_max_bytes=0','-c','tools.view_image=false','-c','web_search="disabled"','-c','mcp_servers={} ','--json','-']
def call(id,prompt):
 d=out/id;d.mkdir(parents=True,exist_ok=True)
 if (d/'receipt.json').exists(): return json.loads((d/'receipt.json').read_text())
 (d/'prompt.txt').write_text(prompt);t=time.monotonic();p=subprocess.run(base,input=prompt,text=True,capture_output=True);elapsed=time.monotonic()-t;(d/'events.jsonl').write_text(p.stdout);(d/'stderr.txt').write_text(p.stderr);events=[]
 for line in p.stdout.splitlines():
  try:events.append(json.loads(line))
  except:pass
 msgs=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'];usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None);unexpected=[e for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') not in {'agent_message','error'}]
 rec={'id':id,'returncode':p.returncode,'elapsed_seconds':elapsed,'usage':usage,'output':msgs[-1] if msgs else None,'unexpected_items':unexpected,'runtime_messages':[e for e in events if e.get('item',{}).get('type')=='error'],'prompt_sha256':'sha256:'+hashlib.sha256(prompt.encode()).hexdigest()};(d/'receipt.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n');return rec
brief=(repo/'docs/experiments/communication-v1/inputs/brief.md').read_text()
finals={}
for case in protocol['cases']:
 cid=case['case_id']; paths=[repo/x['path'] for x in case['sources']]; initial=paths[:-1] if cid=='late' else paths; current=paths
 def sources(ps):return '\n\n'.join(f'FILE {p.name}:\n{p.read_text()}' for p in ps)
 serial_note=call(f'{cid}-serial-initial',f'{brief}\nCreate a short initial draft from these sources. Preserve unknowns and cite filenames. No tools.\n{sources(initial)}')['output'] or ''
 finals[(cid,'serial')]=call(f'{cid}-serial-final',f'{brief}\nCURRENT SOURCES:\n{sources(current)}\nINITIAL DRAFT:\n{serial_note}\nProduce the final attendee-facing note. Follow current revisions, cite filenames, and do not invent facts. No tools.')['output']
 for arm in ('direct','board'):
  notes=[]
  for ix,p in enumerate(initial[:2]):
   notes.append(call(f'{cid}-{arm}-worker-{ix+1}',f'{brief}\nYou are independent worker {ix+1}. Read only this assigned source and return one concise observation under 250 characters with filename and uncertainty. No tools.\nFILE {p.name}:\n{p.read_text()}')['output'] or '')
  if arm=='direct': packet='\n'.join(f'WORKER {i+1}: {n}' for i,n in enumerate(notes))
  else:
   eng=out/f'{cid}-board-ledger';eng.mkdir(exist_ok=True);scope=f'''# Scope - {cid} board pilot\n## Surfaces in scope\n- Local synthetic documents.\n## Benign safe-objective set\n- Document synthesis.\n## Escalation ceiling\n- Local only.\n## Impact-demo authorization\n- impact_demo_authorized: `no`\n- zone2_authorized_categories: `none`\n- zone2_escalation_ceiling: `none`\n- zone2_containment: `none`\n## Accounts / fixtures\n- None.\n## Independent reviewer identity\n- Reviewer allowed signers SHA256: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n## Authorization\n- Operator allowed signers SHA256: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n- Operator: operator-pilot\n- Date: 2026-09-22\n- Signed: [x]\n- Record kernel: `decision-0006-v2`\n''';(eng/'scope.md').write_text(scope);initialize_engagement(eng,'2026-09-22T18:00:00Z');_append_kernel_event(eng,base_event(event_id=f'event-task-{cid}',engagement_id=eng.name,recorded_at='2026-09-22T18:00:01Z',actor_role='orchestrator',actor_id='coordinator',event_type='observation.recorded',rationale='Define measured task.',payload={'entity_id':f'task-{cid}','entity_type':'task_definition','status':'recorded','task_id':f'task-{cid}','source_revision':'task-v1'},session_id='session-coordinator',operation_class='notebook'))
   for ix,(p,n) in enumerate(zip(initial[:2],notes),1):_append_kernel_event(eng,base_event(event_id=f'event-initial-{cid}-{ix}',engagement_id=eng.name,recorded_at=f'2026-09-22T18:00:0{ix+1}Z',actor_role='orchestrator',actor_id=f'worker-{ix}',event_type='observation.recorded',rationale=n or 'Empty worker observation retained.',payload={'entity_id':f'initial-{cid}-{ix}','entity_type':'independent_initial','status':'recorded','task_id':f'task-{cid}','source_revision':p.name},session_id=f'session-worker-{ix}',operation_class='notebook'))
   for ix,(p,n) in enumerate(zip(initial[:2],notes),1):post_notice(eng,{'notice_version':1,'notice_id':f'{cid}-notice-{ix}','task_id':f'task-{cid}','principal_id':f'worker-{ix}','source_event_ref':f'event-initial-{cid}-{ix}','source_revision':p.name,'observation':n[:250] or 'No observation produced.','applicability':f'Only task-{cid}.','uncertainty':'Primary source check remains required.','predecessor_event_ref':None},recorded_at=f'2026-09-22T18:00:0{ix+3}Z')
   compiled=compile_hunter_notices(read_ledger(eng,'event'),task_id=f'task-{cid}');(eng/'compiled-notices.json').write_text(json.dumps({'commitment':compiled['commitment'],'brief':compiled['brief']},indent=2,sort_keys=True)+'\n');packet='\n'.join(data.decode() for data in compiled['files'].values())
  finals[(cid,arm)]=call(f'{cid}-{arm}-final',f'{brief}\nCURRENT SOURCES:\n{sources(current)}\nRECEIVED {arm.upper()} PACKET (advisory; check primary sources):\n{packet}\nProduce final attendee-facing note. Follow current revisions, cite filenames, and do not invent facts. No tools.')['output']
call('grader-calibration','''Blind grader calibration. Correct: current revision and all required facts with citations. Wrong: stale revision or unsupported fact. Ambiguous: wording cannot establish required claim. Return only JSON confirming fields correctness, completeness, revision_correctness, unsupported_claims.''')
for case in protocol['cases']:
 cid=case['case_id'];ref=(repo/case['reference']['path']).read_text(); vals=[finals[(cid,a)] for a in protocol['arms']];order=[1,2,0]
 call(f'grader-{cid}',f'''Blindly grade outputs A/B/C. No arm labels. REFERENCE:\n{ref}\nOUTPUTS:\n{json.dumps({chr(65+i):vals[j] for i,j in enumerate(order)})}\nReturn only JSON mapping each output to correctness, completeness, revision_correctness, unsupported_claims, rationale.''')
(out/'run-summary.json').write_text(json.dumps({'protocol_commit':'bc5c5bb3beb7979fb3c71b7f21ab9c1bec85947c','candidate_assignments':9,'initial_note_calls':15,'final_calls':9,'calibration_calls':1,'grading_calls':3,'no_favorable_reruns':True},indent=2,sort_keys=True)+'\n')
