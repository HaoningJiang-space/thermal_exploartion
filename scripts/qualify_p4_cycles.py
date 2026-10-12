"""Independently replay finite service records and frozen component targets."""
import argparse,csv,gzip,hashlib,json,subprocess,sys
from pathlib import Path
from collections import Counter,defaultdict

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def audit(result,contract):
 activity=Counter();inputs={(r['group'],r['tile']):r['last_tick'] for r in result['inputs']};reads={r['id']:r for r in result['reads']};tasks={r['id']:r for r in result['tasks']};usage=Counter();peaks=Counter();private_peak=0
 caps={'weight':contract['weight_buffer'],'response':contract['response_buffer'],'reduce':contract['reduce_buffer']}
 for event in result['lease_events']:
  key=event['kind'],event['tile'];usage[key]+=event['delta'];peaks[key]=max(peaks[key],usage[key])
  if usage[key]<0 or usage[key]>caps[key[0]]:raise ValueError('Invalid component byte lease')
  tile=key[1];private=contract['static_sram_per_tile'][tile]+contract['metadata_reserve']+sum(usage[k,tile] for k in caps);private_peak=max(private_peak,private)
  if private>contract['sram_per_tile']:raise ValueError('Invented component private storage')
 if any(usage.values()):raise ValueError('Unreleased byte lease')
 usage=Counter();router_peak=0
 for event in result['queue_events']:
  key=event['tile'],event['port'],event['vc'];usage[key]+=event['delta'];router_peak=max(router_peak,usage[key])
  if not 0<=usage[key]<=8:raise ValueError('Invalid router credit')
 if any(usage.values()):raise ValueError('Unreleased router credit')
 refs=Counter()
 for task in tasks.values():
  if any(reads[r]['hb_done']>task['start'] for r in task['requests']) or inputs[task['input_group'],task['tile']]>task['start']:raise ValueError('Early component consumption')
  if task['parent']>=0 and tasks[task['parent']]['finish']>task['start']:raise ValueError('Early partial sum')
  refs.update(task['requests']);activity['mac']+=task['flops']
 for r in reads.values():
  if refs[r['id']]!=r['refs'] or r['remaining']!=0 or r['allocated'] or not (0<=r['accepted']<=r['depart']<=r['hb_first']<r['hb_done']<=r['last_use']):raise ValueError('Weight identity/lifetime mismatch')
 for name,key in (('sram_read','read_bytes'),('sram_write','write_bytes'),('vector','vector_ops'),('fifo_operand','fifo_operand_bytes'),('fifo_ingress','fifo_ingress_bytes')):
  for row in result['ports']:
   limit={'read_bytes':256,'write_bytes':128,'vector_ops':16,'fifo_operand_bytes':500,'fifo_ingress_bytes':500}[key]
   if not 0<=row[key]<=limit:raise ValueError('Component port overrun')
   activity[name]+=row[key]
 if activity!=Counter(result['activity']):raise ValueError('Port/work closure failed')
 for tile in range(16):
  for records in (result['tasks'],result['vectors']):
   intervals=sorted((r['start'],r['finish']) for r in records if r['tile']==tile)
   if any(a[1]>b[0] for a,b in zip(intervals,intervals[1:])):raise ValueError('Overlapping component context')
 links=defaultdict(list)
 for event in result['noc']:
  if event['finish']-event['start']!=8 or event['bytes']!=32:raise ValueError('Changed flit flight')
  links[event['source'],event['target']].append(event['start'])
 for times in links.values():
  if any(b-a<4 for a,b in zip(sorted(times),sorted(times)[1:])):raise ValueError('Link serialization overrun')
 if len(result['noc'])*32!=sum(result['byte_hops'].values()):raise ValueError('Lost flit work')
 return dict(status='PASS_INDEPENDENT_COMPONENT_REPLAY',private_peak_bytes=private_peak,router_queue_peak_flits=router_peak,tasks=len(tasks),reads=len(reads),port_rows=len(result['ports']),link_flits=len(result['noc']))

def equal_csv(path,rows,keys,kind=False):
 with path.open() as f:
  source=csv.DictReader(f)
  for i,(actual,expected) in enumerate(zip(source,rows,strict=True)):
   converted={k:(0 if actual[k]=='X' else 1) if kind and k=='kind' else int(actual[k]) for k in keys}
   if any(converted[k]!=expected[k] for k in keys):return dict(equal=False,first_row=i,actual=converted,expected={k:expected[k] for k in keys})
 return dict(equal=True,rows=len(rows))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--legacy-root',type=Path,required=True);ap.add_argument('--shape-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();source=a.source.resolve();sys.path.insert(0,str(source))
 if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Frozen source required')
 from thermal_exploration.tensor_cycle import execute_tensor
 from thermal_exploration.tensor_execution import build,CASES
 a.output.mkdir(parents=True,exist_ok=False);records=[]
 for role,root in (('legacy',a.legacy_root),('shape_validation',a.shape_root)):
  launch=read(root/'launcher-manifest.json')
  for run in launch['runs']:
   directory=root/run['directory']
   if run['exit_code'] or (root/(run['directory']+'.exit')).read_text().strip()!='0':raise ValueError('Incomplete reference')
   for native in read(directory/'summary.json'):
    c=native['contract'];settings=dict(CASES[native['name']],compute_tflops=c['compute_tflops'],sram_mib=c['sram_mib'],fluid_memory=c['fluid_memory'],fluid_service_tb_s=c['fluid_service_tb_s']);model=build(settings,c['m'],c['n'],c['batch']);result=execute_tensor(model)
    if result['activity']['mac']!=c['mac_flops'] or result['activity']['fifo_operand']!=c['dram_bytes'] or result['byte_hops']!=native['byte_hops']:raise ValueError('Reference work changed')
    for kind,key in (('sram_read','read_bytes'),('sram_write','write_bytes'),('vector','vector_ops'),('fifo_operand','fifo_operand_bytes'),('fifo_ingress','fifo_ingress_bytes')):
     if result['activity'][kind]!=native['sram_activity'][key]:raise ValueError('Reference SRAM work changed')
    replay=audit(result,c);trace={}
    if c['fluid_memory']:
     path=directory/native['name']
     grids=(('tasks',result['tasks'],('id','tile','start','finish')),('inputs',result['inputs'],('group','tile','bytes','last_tick')),('reads',result['reads'],('id','tile','accepted','depart','hb_first','hb_done','last_use','refs')),('vector',result['vectors'],('group','tile','start','finish')),('inject',result['injections'],('kind','group','flit','tile','tick')),('noc',result['noc'],('kind','group','flit','source','target','bytes','start','finish')),('ports',result['ports'],tuple(result['ports'][0])))
     for name,rows,keys in grids:trace[name]=equal_csv(path/('run-'+name+'.csv'),rows,keys,kind=name in ('inject','noc'))
    path=a.output/(role+'-'+run['directory']+'-'+native['name']+'-cycle.json.gz')
    with gzip.open(path,'wt') as f:json.dump(dict(contract=c,result=result),f,separators=(',',':'))
    error=result['time_us']/native['time_us']-1
    record=dict(role=role,run=run['directory'],case=native['name'],shape=[c['m'],c['n'],c['batch']],backend='fluid' if c['fluid_memory'] else 'native',reference_us=native['time_us'],cycle_us=result['time_us'],relative_error=error,absolute_target_met=abs(error)<=.1,source_reference=launch['source'],reference_summary_sha256=sha(directory/'summary.json'),event_file=path.name,event_sha256=sha(path),event_replay=replay,fluid_trace_comparison=trace)
    records.append(record);print(record['run'],record['case'],error,all(v['equal'] for v in trace.values()),flush=True)
 pairs=[];index={(r['role'],tuple(r['shape']),r['case'],r['backend']):r for r in records}
 for role in ('legacy','shape_validation'):
  shapes=sorted({tuple(r['shape']) for r in records if r['role']==role})
  names=('row_fifo_k','column_fifo64') if role=='legacy' else ('row_fifo32','column_fifo32')
  for shape in shapes:
   row,col=[index[role,shape,n,'native'] for n in names];ratio=row['reference_us']/col['reference_us'];predict=row['cycle_us']/col['cycle_us'];error=predict/ratio-1
   pairs.append(dict(role=role,shape=shape,native_ratio=ratio,cycle_ratio=predict,relative_prediction_error=error,relative_target_met=abs(error)<=.05,rank_agrees=(ratio<1)==(predict<1)))
 output=dict(source=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),records=records,pairs=pairs,absolute_target=.1,relative_target=.05,absolute_pass=sum(r['absolute_target_met'] for r in records),relative_pass=sum(r['relative_target_met'] for r in pairs),scope='Independent tensor execution frontend, shared contract/physical assumptions, fixed fluid memory; does not qualify fullMoE Graph timing or silicon',all_fluid_traces_exact=all(v['equal'] for r in records for v in r['fluid_trace_comparison'].values()))
 (a.output/'qualification.json').write_text(json.dumps(output,indent=2)+'\n')
 print(json.dumps({k:v for k,v in output.items() if k not in ('records','pairs')}),flush=True)
if __name__=='__main__':main()
