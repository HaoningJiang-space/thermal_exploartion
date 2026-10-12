"""Independent full-range check of the retained start-row-only shape pilot."""
import argparse,csv,gzip,json,sys
from pathlib import Path

def check(contract,tasks,vectors):
 rowbytes=contract['batch']*4;straddled=0;early=[];finals={tile:[t for t in tasks if t['tile']==tile and t['final']] for tile in range(16)}
 for v in vectors:
  lo=v['group']*contract['packet_bytes'];hi=lo+contract['packet_bytes'];tile=v['tile'];hits=[t for t in finals[tile] if t['m_start']*rowbytes<hi and (t['m_start']+t['m_count'])*rowbytes>lo]
  if len(hits)>1:straddled+=1
  if not hits:continue # Intermediate reduction-only node has no local MAC.
  ready=max(t['finish'] for t in hits)
  if v['start']<ready:early.append(dict(group=v['group'],tile=tile,packet_bytes=[lo,hi],producer_tasks=[t['id'] for t in hits],observed_start=v['start'],required_ready=ready,premature_ticks=ready-v['start']))
 return dict(straddled_packets=straddled,early_packet_count=len(early),early_packets=early)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--native-root',type=Path,required=True);ap.add_argument('--cycle-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();sys.path.insert(0,str(a.source.resolve()));from thermal_exploration.tensor_execution import build,CASES
 q=json.loads((a.cycle_root/'qualification.json').read_text());records=[]
 for rec in q['records']:
  if rec['role']!='shape_validation':continue
  directory=a.native_root/rec['run']/rec['case'];c=json.loads((directory/'contract.json').read_text());model=build(dict(CASES[rec['case']],fluid_memory=c['fluid_memory']),c['m'],c['n'],c['batch'])
  with (directory/'run-tasks.csv').open() as f:times=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
  tasks=[dict(t,**actual) for t,actual in zip(model['tasks'],times,strict=True)]
  with (directory/'run-vector.csv').open() as f:vec=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
  raw=json.loads(gzip.decompress((a.cycle_root/rec['event_file']).read_bytes()))['result']
  records.append(dict(run=rec['run'],case=rec['case'],shape=rec['shape'],native_reference=check(c,tasks,vec),python_predictor=check(c,raw['tasks'],raw['vectors'])))
 output=dict(status='RETIRED_START_ROW_ONLY_SHAPE_CONTRACT',retired_source=q['source'],records=records,scope='Whole eight-point shape pilot retired; actual early reads occur in cold row cases. Aligned column cases and oldM512 references are not asserted to have this bug. Timing/byte/trace agreement does not prove full packet readiness.')
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'retirement.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({k:v for k,v in output.items() if k!='records'}))
if __name__=='__main__':main()
