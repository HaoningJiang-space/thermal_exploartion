"""Read-only phase diagnosis of failed component qualification; no fitting."""
import argparse,csv,gzip,json
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--native',type=Path,required=True);ap.add_argument('--qualification',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();q=json.loads((a.qualification/'qualification.json').read_text());records=[]
 for r in q['records']:
  directory=a.native/r['run']/r['case'];raw=json.loads(gzip.decompress((a.qualification/r['event_file']).read_bytes()));events={e['id']:e for e in raw['events']}
  def csvrows(name):
   with (directory/name).open() as f:return list(csv.DictReader(f))
  tasks=csvrows('run-tasks.csv');inputs=csvrows('run-inputs.csv');reads=csvrows('run-reads.csv');vec=csvrows('run-vector.csv');mac=[n for n in raw['nodes'] if n['kind']=='mac']
  if len(mac)!=len(tasks):raise ValueError('Task mapping mismatch')
  pairs=[dict(task=int(t['id']),tile=int(t['tile']),native_start=int(t['start']),native_finish=int(t['finish']),graph_start=events[n['id']]['start_tick'],graph_finish=events[n['id']]['finish_tick']) for t,n in zip(tasks,mac)]
  for p in pairs:p['start_delta_ticks']=p['graph_start']-p['native_start'];p['finish_delta_ticks']=p['graph_finish']-p['native_finish']
  def end(kind=None,stage=None):return max((e['finish_tick'] for e in events.values() if (kind is None or e['kind']==kind) and (stage is None or e['stage']==stage)),default=0)
  records.append(dict(run=r['run'],case=r['case'],shape=r['shape'],backend=r['backend'],relative_error=r['relative_error'],native_ticks=dict(input_last=max(int(t['last_tick']) for t in inputs),hb_last=max(int(t['hb_done']) for t in reads),mac_first=min(int(t['start']) for t in tasks),mac_last=max(int(t['finish']) for t in tasks),vector_last=max(int(t['finish']) for t in vec),output_last=r['detailed_us']/.00025),graph_ticks=dict(input_last=end(stage='input'),hb_last=end(kind='hb'),mac_first=min(events[n['id']]['start_tick'] for n in mac),mac_last=end(kind='mac'),vector_last=end(stage='tensor_reduce'),output_last=r['graph_us']/.00025),worst_start_task=max(pairs,key=lambda p:abs(p['start_delta_ticks'])),worst_finish_task=max(pairs,key=lambda p:abs(p['finish_delta_ticks'])),task_pairs=pairs))
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'phases.json').write_text(json.dumps(dict(scope='Observed phase endpoints overlap; not additive causes or counterfactual gains. Matched detailed task order, no empirical fit.',records=records),indent=2)+'\n')
 print(json.dumps([{k:v for k,v in r.items() if k!='task_pairs'} for r in records],indent=2))
if __name__=='__main__':main()
