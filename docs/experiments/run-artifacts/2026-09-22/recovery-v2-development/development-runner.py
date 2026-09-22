import asyncio,json,pathlib,sys,hashlib
sdk=pathlib.Path('/tmp/redteam-recovery-sdk');sys.path.insert(0,str(sdk/'src'))
from agents import Agent,Runner,RunState,RunConfig,function_tool
from agents.testing import ScriptedModel
from openai.types.responses import ResponseFunctionToolCall,ResponseOutputMessage,ResponseOutputText
out=pathlib.Path('/tmp/redteam-pilots/recovery-v2');out.mkdir(parents=True,exist_ok=True)
def msg(text):return ResponseOutputMessage(id='m',type='message',role='assistant',content=[ResponseOutputText(text=text,type='output_text',annotations=[],logprobs=[])],status='completed')
def call(name,args,call_id):return ResponseFunctionToolCall(id='f',call_id=call_id,type='function_call',name=name,arguments=json.dumps(args))
def snap(c):
 def clean(x):
  if isinstance(x,(str,int,float,bool)) or x is None:return x
  if isinstance(x,list):return [clean(y) for y in x]
  if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
  if hasattr(x,'model_dump'):return clean(x.model_dump())
  return repr(x)
 return clean({'system_instructions':c.system_instructions,'input':c.input,'tools':[getattr(t,'name',repr(t)) for t in c.tools],'previous_response_id':c.previous_response_id,'conversation_id':c.conversation_id})
async def run_case(case):
 effects=[]
 @function_tool(needs_approval=True)
 def checkpoint(payload:str)->str:
  effects.append(payload);return 'receipt:'+payload
 scripts={
 'late-correction':[[call('checkpoint',{'payload':'binding-v2 correction supplied'},'c1')],[msg('Revised output uses binding-v2 and retains the predecessor as stale history.')]],
 'cooperative-pause':[[call('checkpoint',{'payload':'pause after bounded first phase'},'c1')],[msg('Resumed from approved checkpoint with unfinished work visible.')]],
 'lost-receipt':[[call('checkpoint',{'payload':'write attendee-note-v2'},'c1')],RuntimeError('simulated lost provider receipt after approved effect')],
 }
 model=ScriptedModel(scripts[case],emit_traces=False);agent=Agent(name=f'recovery-{case}',instructions='Use checkpoint once, then report recovery status without exactly-once claims.',model=model,tools=[checkpoint]);config=RunConfig(tracing_disabled=True)
 first=await Runner.run(agent,f'case={case}; preserve exact supplied arguments',run_config=config);state_json=first.to_state().to_json();state_text=json.dumps(state_json,sort_keys=True,separators=(',',':'));restored=await RunState.from_json(agent,state_json);intr=restored.get_interruptions()[0];restored.approve(intr)
 err=None;final=None
 try:
  resumed=await Runner.run(agent,restored,run_config=config);final=resumed.final_output
 except Exception as exc:err=type(exc).__name__+': '+str(exc)
 return {'case':case,'arm':'sdk','state_sha256':'sha256:'+hashlib.sha256(state_text.encode()).hexdigest(),'state_bytes':len(state_text.encode()),'interruption':{'name':intr.name,'arguments':getattr(intr,'arguments',None)},'model_calls':[snap(c) for c in model.calls],'effects':effects,'final_output':final,'error':err,'trace_export':False,'exactly_once_external_effects':'not_established'}
async def main():
 rows=[]
 for case in ('late-correction','cooperative-pause','lost-receipt'):
  rows.append({'case':case,'arm':'baseline','received_arguments':['workshop-v1'] if case!='late-correction' else ['workshop-v1','binding-v2'],'native_pause_restore':'unsupported','unfinished_work':['reconcile state'],'exactly_once_external_effects':'not_established'})
  rows.append(await run_case(case))
 (out/'results.json').write_text(json.dumps({'protocol_commit':'bc5c5bb3beb7979fb3c71b7f21ab9c1bec85947c','sdk_commit':'f1f35031d364f9f0d8e94dda0853c92abefdccff','assignments':rows},indent=2,sort_keys=True,default=str)+'\n')
asyncio.run(main())
