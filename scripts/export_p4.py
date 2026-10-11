"""Independent immutable-event replay and matched P4-A evidence export."""
import argparse,gzip,hashlib,json
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from export_expert_gate import compact

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')

def replay(path,point):
 raw=json.loads(gzip.decompress(path.read_bytes()));nodes=raw['nodes'];events={e['id']:e for e in raw['events']};meta=raw['meta']
 if len(events)!=len(nodes) or set(events)!=set(range(len(nodes))):raise ValueError('Incomplete event graph')
 resources=defaultdict(list);credits=defaultdict(list);private=defaultdict(list)
 for node in nodes:
  ev=events[node['id']];start=ev['start_tick'];end=ev['finish_tick']
  if start<0 or end<start or any(events[d]['finish_tick']>start for d in node['deps']):raise ValueError('Noncausal event')
  if any(ev[k]!=node[k] for k in ('kind','tile','work','stage')):raise ValueError('Event semantic mismatch')
  if end>start:
   for resource in [node['resource']]+meta.get('coupled_resources',{}).get(str(node['id']),[]):resources[tuple(resource)].append((start,end))
  for key,amount,last in node['leases']:
   until=events[last]['finish_tick']
   if last<node['id'] or until<start:raise ValueError('Invalid lease lifetime')
   if until==start:continue # zero-duration reservation has no open interval
   key=tuple(key)
   credits[key]+=[(start,1,amount),(until,0,-amount)]
   private[key[1]]+=[(start,1,amount),(until,0,-amount)]
 for ranges in resources.values():
  ordered=sorted(ranges)
  if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping physical resource')
 def peak(changes):
  used=high=0
  for _,_,change in sorted(changes):
   used+=change
   if used<0:raise ValueError('Lease accounting underflow')
   high=max(high,used)
  if used:raise ValueError('Unreleased credit')
  return high
 caps={'weight':524288,'weight_fifo':262144,'return':65536,'receive':65536,'workspace':1048576,'router0':4096,'router1':4096,'router2':4096,'router3':4096,'transmit':65536,'output':262144}
 caps.update(meta.get('buffer_caps',{}))
 for key,changes in credits.items():
  high=peak(changes)
  if high>caps[key[0]] or high>point['buffer_high'][str(key)]:raise ValueError('Credit peak replay mismatch')
 max_output=0
 for name,group in meta.get('credit_groups',{}).items():
  if sum(caps[k] for k in group['members'])>group['capacity']:raise ValueError('Storage invented by partition')
  for tile in range(16):
   high=peak(sum((credits[(member,tile)] for member in group['members']),[]));max_output=max(max_output,high)
   if high>group['capacity'] or high>point['credit_group_high'][str((name,tile))]:raise ValueError('Physical output storage exceeded')
 private_high=max((peak(changes)+meta['fixed_sram_bytes'][tile] for tile,changes in private.items()),default=0)
 if private_high>meta['private_sram_budget_bytes']:raise ValueError('Private SRAM exceeded')
 activity=Counter()
 for ev in events.values():activity[ev['kind']]+=ev['work']
 if activity!=Counter(point['packet_dag_activity']):raise ValueError('Packet activity replay mismatch')
 if sum(point['critical_chain_ticks'].values())+point['critical_gap_ticks']!=point['ticks']:raise ValueError('Critical chain not closed')
 combine=[e for e in events.values() if e['stage']=='combine']
 return dict(nodes=len(nodes),resources=len(resources),private_peak_bytes=private_high,output_partition_peak_bytes=max_output,first_combine_us=min(e['start_tick'] for e in combine)*.00025,last_combine_us=max(e['finish_tick'] for e in combine)*.00025,last_local_expert_us=max(e['finish_us'] for e in point['expert_service_latency']),status='PASS_INDEPENDENT_EVENT_REPLAY')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--cohort-root',type=Path);ap.add_argument('--old-points',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 pool=ProcessPoolExecutor(max_workers=a.workers);pending=[]
 roots=[a.root]+([a.cohort_root] if a.cohort_root else []);runs=[];sources={}
 for root in roots:
  launch=read(root/'launcher-manifest.json');sources[root.name]=launch['source']
  runs.extend((root,launch['source'],run) for run in launch['runs'])
 points=[];numerical=[];manifest=[];old=read(a.old_points);replays=[]
 for root,source,run in runs:
  directory=root/run['directory'];prov=read(directory/'provenance.json');summary=read(directory/'summary.json');params=prov['params']
  if run['exit_code']!=0 or (root/(run['directory']+'.exit')).read_text().strip()!='0':raise ValueError('Failed process')
  if prov['dirty'] or prov['source_commit']!=source:raise ValueError('Source pin mismatch')
  source_route=Path(params['routes']);raw=source_route.read_bytes()
  if source_route.suffix=='.gz':raw=gzip.decompress(raw)
  if hashlib.sha256(raw).hexdigest()!=prov['routing_sha256']:raise ValueError('Routing hash mismatch')
  if len(summary)!=6:raise ValueError('Incomplete run')
  wanted={(s,l,x) for s,l in ((0,0),(32,7),(127,23)) for x in (('FP32','BF16') if params['numerical_only'] else ('none','infinite_noc'))}
  actual={(r['step'],r['layer'],r['dtype'] if params['numerical_only'] else r['isolation']) for r in summary}
  if wanted!=actual:raise ValueError('Frozen case grid mismatch')
  for rec in summary:
   if params['numerical_only']:
    if rec['status']!='PASS_NUMERICAL':raise ValueError('Numerical mismatch')
    numerical.append(rec);continue
   path=directory/(rec['label']+'.json')
   if read(path)!=rec or rec['status']!='PASS_ACCOUNTING':raise ValueError('Point/summary mismatch')
   if sha(directory/rec['event_file'])!=rec['event_sha256']:raise ValueError('Event digest mismatch')
   if sum(k['mac_flops'] for k in rec['kernel_service_windows'])!=rec['mac_flops'] or rec['activity']['mac']!=rec['mac_flops']:raise ValueError('MAC changed')
   if sum(k['dram_bytes'] for k in rec['kernel_service_windows'])!=rec['actual_dram_bytes']:raise ValueError('Native reads changed')
   future=pool.submit(replay,directory/rec['event_file'],rec)
   row=compact(rec);row.update(experiment=run['directory'],point_sha256=sha(path));pending.append((row,future))
   detail=row.pop('communication_audit',None)
   if detail:
    row['communication_audit_summary']={k:v for k,v in detail.items() if k not in ('input_delivery','semantic_ledger')}
    for k in ('input_delivery','semantic_ledger'):row['communication_audit_summary'][k+'_sha256']=hashlib.sha256(json.dumps(detail[k],sort_keys=True,separators=(',',':')).encode()).hexdigest()
   points.append(row)
   if rec['dispatch_scheme']=='broadcast_all' and rec['reduction_scheme']=='drain_all':
    matches=[r for r in old if r.get('batch')==rec['batch'] and str(r.get('tp'))==str(rec['tp']) and r.get('step')==rec['step'] and r.get('layer')==rec['layer'] and r.get('down_partition')==rec['down_partition'] and r.get('combine_scheme')=='fused' and r.get('schedule')=='barrier' and r.get('order')=='static' and r.get('isolation')==rec['isolation'] and r.get('baseline')=='B3_3d_placement']
    if matches:
     fields=('ticks','activity','mac_flops','actual_dram_bytes','critical_chain_ticks','critical_gap_ticks')
     if any(any(r.get(k)!=row.get(k) for k in fields) for r in matches):raise ValueError('26d1b02 replay changed: '+rec['label'])
     replays.append(dict(label=rec['label'],prior_experiments=[r['experiment'] for r in matches],status='EXACT_26D1B02_REPLAY',fields=fields))
  safe={k:dict(v,**{name:Path(value).name for name,value in v.items() if name in ('routes','output')}) if k=='params' else v for k,v in prov.items()}
  manifest.append(dict(directory=run['directory'],exit_code=0,provenance=safe,points=len(summary),summary_sha256=sha(directory/'summary.json'),layout_sha256=sha(directory/'resident-layout.json')))
 for row,future in pending:row['event_replay']=future.result()
 pool.shutdown()
 if len(points)!=(336 if a.cohort_root else 288) or len(numerical)!=48 or len(manifest)!=(64 if a.cohort_root else 56):raise ValueError('Full matrix incomplete')
 index={(r['batch'],r['tp'],r['down_partition'],r['step'],r['layer'],r['dispatch_scheme'],r['reduction_scheme'],r['isolation']):r for r in points}
 paired=[]
 for r in points:
  if r['isolation']!='none':continue
  key=(r['batch'],r['tp'],r['down_partition'],r['step'],r['layer']);base=index[key+('broadcast_all','drain_all','none')];oracle=index[key+(r['dispatch_scheme'],r['reduction_scheme'],'infinite_noc')]
  if any(r[k]!=base[k] for k in ('mac_flops','actual_dram_bytes','route_case_sha256')):raise ValueError('Matched workload changed')
  if r['activity']!=oracle['activity']:raise ValueError('Oracle changes work')
  if r['dispatch_scheme']=='destination_only' and sum(r['stage_activity'].get('dispatch',{}).get(k,0) for k in ('link',))!=base['stage_activity']['dispatch']['link']:raise ValueError('Shared input disappeared')
  paired.append(dict(batch=r['batch'],tp=r['tp'],down_partition=r['down_partition'],step=r['step'],layer=r['layer'],role=r['role'],dispatch=r['dispatch_scheme'],reduction=r['reduction_scheme'],time_us=r['time_us'],legacy_us=base['time_us'],latency_reduction_pct=100*(1-r['time_us']/base['time_us']),speedup=base['time_us']/r['time_us'],infinite_noc_us=oracle['time_us'],noc_speedup_pct=100*(r['time_us']/oracle['time_us']-1),noc_latency_reduction_pct=100*(1-oracle['time_us']/r['time_us']),dispatch_byte_hops=sum(r['stage_activity'].get(stage,{}).get('link',0) for stage in ('dispatch','shared_dispatch','routed_dispatch')),combine_byte_hops=r['stage_activity']['combine']['link']))
 fixed=[]
 strategies=[(dispatch,reduction) for dispatch in ('broadcast_all','destination_only','decoupled') for reduction in ('drain_all','row_ready')]+([('broadcast_all','row_ready_128')] if a.cohort_root else [])
 for dispatch,reduction in strategies:
   rec=dict(dispatch=dispatch,reduction=reduction)
   for role in ('primary','holdout'):
    rows=[r for r in paired if r['dispatch']==dispatch and r['reduction']==reduction and r['role']==role]
    rec[role]=dict(points=len(rows),geomean_speedup=float(np.exp(np.mean(np.log([r['speedup'] for r in rows])))),latency_reduction_range_pct=[min(r['latency_reduction_pct'] for r in rows),max(r['latency_reduction_pct'] for r in rows)])
   fixed.append(rec)
 winner=max(fixed,key=lambda r:r['primary']['geomean_speedup'])
 dump(a.output/'all-points.json',points);dump(a.output/'numerical.json',numerical);dump(a.output/'run-manifest.json',manifest);dump(a.output/'paired-comparisons.json',paired)
 dump(a.output/'audit.json',dict(status='PASS',source_commits=sources,performance_points=len(points),numerical_comparisons=len(numerical),runs=len(manifest),exact_legacy_replays=replays,all_event_replays=True,max_numerical_absolute_error=max(r['max_absolute_error'] for r in numerical),max_numerical_relative_l2_error=max(r['relative_l2_error'] for r in numerical),fixed_strategies=fixed,primary_selected_fixed_strategy=winner,selection_scope='one policy selected across all eight primary workloads, evaluated unchanged on16 holdouts; no per-point hardware/placement choice;128-row cohort is a separately frozen post-negative-result control'))
 print(json.dumps(dict(status='PASS',points=len(points),numerical=len(numerical),runs=len(manifest),exact_replays=len(replays),selected=winner)),flush=True)

if __name__=='__main__':main()
