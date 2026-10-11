"""Audit completed frozen real-route runs before making compact public evidence."""
import argparse,json,hashlib,re
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np

LABEL=re.compile(r'^(.*)-tp(1|4|16|hybrid)-b(\d+)-l(\d+)-s(\d+)-(barrier|overlap)-(static|dynamic)-(.+)$')
SCHEDULERS=(('barrier','static'),('overlap','static'),('overlap','dynamic'))
ISOLATIONS=('none','bank_cycle','uniform_fast_tier','hb_only','ingress_only','mac_only','infinite_noc','ideal_memory')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def compact(r):
 out={k:v for k,v in r.items() if k not in ('kernel_service_windows','critical_path','prefetch_ledger','row_block_ledger')}
 if 'kernel_service_windows' in r:
  kernels=r['kernel_service_windows'];out['joint_kernel_activity']=dict(sum((Counter(k['activity']) for k in kernels),Counter()))
  out['joint_kernel_state_ticks']=dict(mac_occupied=sum(k['mac_busy_ticks'] for k in kernels),missing_weight=sum(k['missing_data_ticks'] for k in kernels))
  out['packet_dag_activity']=dict(r.get('packet_dag_activity',r['activity']))
  out['activity']=dict(r['activity'],dram=r['actual_dram_bytes'],hb=r['actual_dram_bytes'])
  if 'packet_dag_activity' not in r:out['activity']['sram_read']=r['activity'].get('sram_read',0)+out['joint_kernel_activity']['sram_read']
  out['packet_dag_per_tile_activity']=r['per_tile_activity']
  out['per_tile_activity']={tile:dict(activity) for tile,activity in r['per_tile_activity'].items()}
  for tile,activity in out['per_tile_activity'].items():
   local=[k for k in kernels if k['tile']==int(tile)]
   activity.update(dram=sum(k['dram_bytes'] for k in local),hb=sum(k['dram_bytes'] for k in local))
   activity['sram_read']=activity.get('sram_read',0)+sum(k['activity']['sram_read'] for k in local)
  if sum((Counter(v) for v in out['per_tile_activity'].values()),Counter())!=Counter(out['activity']):raise ValueError('Normalized per-tile activity does not close')
  out['critical_attribution_note']='Joint memory/MAC durations and busy windows are not additive loss counters; counterfactual gains overlap.'
  out['critical_kind_ticks']=dict(sum((Counter({e['kind']:e['finish_tick']-e['start_tick']}) for e in r['critical_path']),Counter()))
 out.setdefault('combine_scheme','eager' if 'kernel_service_windows' in r else None)
 out.setdefault('down_partition','column' if 'kernel_service_windows' in r else None)
 m=LABEL.match(r['label'])
 if m:out.update(baseline=m[1],tp=m[2],step=int(m[5]))
 return out

def audit(directory):
 summary=directory/'summary.json';rows=read(summary);provenance=read(directory/'provenance.json');params=provenance['params']
 exit_file=Path(str(directory)+'.exit')
 if not exit_file.exists() or exit_file.read_text().strip()!='0':raise ValueError('Missing successful process exit: '+directory.name)
 if provenance['dirty'] or not provenance['source_commit'].startswith(directory.name.split('-')[-1]):raise ValueError('Source pin mismatch: '+directory.name)
 if len({r['label'] for r in rows})!=len(rows):raise ValueError('Duplicate case label')
 if sha(params['routes'])!=provenance['routing_sha256']:raise ValueError('Routing digest mismatch')
 prior_path=directory/'prior-provenance.json'
 if prior_path.exists() and sha(params['prior_routes'])!=read(prior_path)['routing_sha256']:raise ValueError('Training prior digest mismatch')
 if params['mode']=='rows':expected=4
 elif params['mode']=='isolation':
  names=params.get('isolation_names') or ISOLATIONS;expected=len(names)
  if {r['isolation'] for r in rows}!=set(names):raise ValueError('Isolation grid incomplete')
 else:
  route_path=Path(params['routes'])
  if route_path.suffix=='.gz':
   import gzip
   route=json.loads(gzip.decompress(route_path.read_bytes()))
  else:route=read(route_path)
  steps=sorted(set((0,route['steps']-1))) if route['steps']<128 else params.get('sample_steps') or [0,32,64,96,127]
  layers=[0,15,23] if route['steps']<128 else params.get('sample_layers') or [0,7,15,23]
  wanted={(step,layer,schedule,order) for step in steps for layer in layers for schedule,order in SCHEDULERS}
  actual={(int(LABEL.match(r['label'])[5]),r['layer'],r['schedule'],r['order']) for r in rows}
  if wanted!=actual:raise ValueError('Layer/step/scheduler grid incomplete: '+directory.name)
  expected=len(wanted)
 if len(rows)!=expected:raise ValueError('Point count mismatch: '+directory.name)
 for row in rows:
  file=directory/(row['label']+'.json')
  if read(file)!=row:raise ValueError('Summary differs from raw point: '+file.name)
  if row['status']=='PASS_ACCOUNTING':
   if params['mode']=='rows' and row['completed_steps']!=params['steps']:raise ValueError('Partial full-model run')
   if 'kernel_service_windows' in row:
    kernels=row['kernel_service_windows']
    if sum(k['mac_flops'] for k in kernels)!=row['mac_flops'] or row['activity']['mac']!=row['mac_flops']:raise ValueError('MAC closure')
    if sum(k['dram_bytes'] for k in kernels)!=row['actual_dram_bytes']:raise ValueError('Weight read closure')
    if sum(row['critical_chain_ticks'].values())+row['critical_gap_ticks']!=row['ticks']:raise ValueError('Critical path closure')
   if row.get('event_file') and sha(directory/row['event_file'])!=row['event_sha256']:raise ValueError('Event digest mismatch')
  elif params['mode']!='rows' or row['profile']['sram_mib']!=18 or not row['label'].endswith('cohort'):
   raise ValueError('Unexpected failure requires investigation: '+row['label'])
 params={k:(Path(v).name if k in ('routes','prior_routes','output') and v else v) for k,v in params.items()}
 provenance=dict(provenance,params=params)
 layout=directory/'resident-layout.json'
 manifest=dict(directory=directory.name,summary_sha256=sha(summary),expected_points=expected,point_count=len(rows),pass_count=sum(r['status']=='PASS_ACCOUNTING' for r in rows),exit_code=0,provenance=provenance,audit='PASS: complete grid, clean source, route/point/event digests and work/causal closure')
 if layout.exists():manifest['frozen_layout_sha256']=sha(layout)
 if prior_path.exists():manifest['prior_provenance']=read(prior_path)
 return rows,manifest

def statistics(values):return dict(samples=len(values),mean_us=float(np.mean(values)),geomean_us=float(np.exp(np.mean(np.log(values)))),p95_us=float(np.quantile(values,.95)))
def dump(out,name,value):(out/name).write_text(json.dumps(value,indent=2)+'\n')
def executed_grids(points,manifests):
 for manifest in manifests:
  rows=[r for r in points if r['experiment']==manifest['directory']]
  if manifest['provenance']['params']['mode']=='rows':
   manifest['completed_decode_steps_by_profile']={r['label']:r['completed_steps'] for r in rows}
  else:
   manifest['executed_steps']=sorted({r['step'] for r in rows})
   manifest['executed_layers']=sorted({r['layer'] for r in rows})
  manifest['selection_note']='Actual execution derives from audited case files; legacy selected_steps/layers in raw provenance list CLI defaults even for supplements.'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sources',nargs='+',required=True);ap.add_argument('--output',required=True);ap.add_argument('--merge-from',type=Path);a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);points=[];manifests=[]
 if a.merge_from:
  points=read(a.merge_from/'all-points.json');manifests=read(a.merge_from/'run-manifest.json')
  if any(not m['audit'].startswith('PASS:') for m in manifests) or sum(m['point_count'] for m in manifests)!=len(points):raise ValueError('Invalid prior audited cache')
  dump(out,'merge-provenance.json',dict(prior_points_sha256=sha(a.merge_from/'all-points.json'),prior_manifest_sha256=sha(a.merge_from/'run-manifest.json'),scope='Previously completed full raw audit; cached compact points are retained without a fidelity change'))
 for directory in map(Path,a.sources):
  rows,manifest=audit(directory);manifests.append(manifest)
  for row in rows:
   p=compact(row);p.update(experiment=directory.name,point_sha256=sha(directory/(row['label']+'.json')));points.append(p)
 if len({(p['experiment'],p['label']) for p in points})!=len(points):raise ValueError('Duplicate merged point')
 executed_grids(points,manifests)
 (out/'all-points.json').write_text(json.dumps(points,separators=(',',':'))+'\n');dump(out,'run-manifest.json',manifests)
 aggregates=[];groups=defaultdict(list)
 for r in points:
  if r['experiment'].startswith('expert-p2') and r['status']=='PASS_ACCOUNTING':groups[r['batch'],r['tp'],r['baseline'],r['schedule'],r['order'],r['combine_scheme'],r['down_partition']].append(r)
 for (b,tp,baseline,sched,order,combine,partition),rows in sorted(groups.items(),key=str):
  aggregates.append(dict(batch=b,tp=tp,baseline=baseline,schedule=sched,order=order,combine_scheme=combine,down_partition=partition,case_ids=sorted([r['step'],r['layer']] for r in rows),**statistics([r['time_us'] for r in rows])))
 dump(out,'conventional-baselines.json',aggregates)
 isolates=[];pairs=defaultdict(dict)
 for r in points:
  if r['experiment'].startswith('expert-p3') and r['status']=='PASS_ACCOUNTING':
   p=pairs[r['batch'],r['tp'],r['combine_scheme'],r['down_partition'],r['schedule'],r['order']]
   if r['isolation'] in p:
    previous=p[r['isolation']]
    if any(previous[k]!=r[k] for k in ('ticks','mac_flops','actual_dram_bytes','activity','critical_chain_ticks','critical_gap_ticks')):raise ValueError('Supplemental baseline replay differs')
   p[r['isolation']]=r
 for (b,tp,combine,partition,schedule,order),p in sorted(pairs.items(),key=str):
  expected=set(ISOLATIONS)|({'native_only','hb_ingress_only'} if combine=='fused' else set())
  if set(p)!=expected:raise ValueError('Incomplete matched isolation group')
  base=p['none']
  if (schedule,order)==('barrier','static') and combine=='fused':
   originals=[r for r in points if r['experiment'].startswith('expert-p2') and r['status']=='PASS_ACCOUNTING' and r['batch']==b and r.get('tp')==tp and r['down_partition']==partition and r['combine_scheme']==combine and r.get('baseline')==base['baseline'] and r['layer']==0 and r['step']==0 and r['schedule']==schedule and r['order']==order]
   if len(originals)!=1 or any(originals[0][k]!=base[k] for k in ('ticks','activity','mac_flops','actual_dram_bytes','critical_chain_ticks','critical_gap_ticks')):raise ValueError('Strong P3 differs from matching P2 baseline')
  for iso,r in p.items():
   if r['actual_dram_bytes']!=base['actual_dram_bytes'] or r['mac_flops']!=base['mac_flops']:raise ValueError('Oracle changed work')
   isolates.append(dict(batch=b,tp=tp,combine_scheme=combine,down_partition=partition,schedule=schedule,order=order,isolation=iso,time_us=r['time_us'],speedup=base['time_us']/r['time_us'],dram_bytes=r['actual_dram_bytes'],mac_flops=r['mac_flops'],critical_chain_ticks=r['critical_chain_ticks'],critical_gap_ticks=r['critical_gap_ticks']))
 dump(out,'physical-isolation.json',isolates)
 print(json.dumps(dict(points=len(points),passes=sum(r['status']=='PASS_ACCOUNTING' for r in points),runs=len(manifests),audit='PASS')))
if __name__=='__main__':main()
