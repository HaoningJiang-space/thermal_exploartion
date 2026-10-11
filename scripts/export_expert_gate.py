"""Compact public evidence; all detailed points stay in the raw manifest."""
import argparse,json,hashlib
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np

def compact(r):
 out={k:v for k,v in r.items() if k not in ('kernel_service_windows','critical_path','prefetch_ledger','row_block_ledger')}
 if 'kernel_service_windows' in r:
  kernels=r['kernel_service_windows'];out['joint_kernel_activity']=dict(sum((Counter(k['activity']) for k in kernels),Counter()))
  out['joint_kernel_state_ticks']=dict(mac_occupied=sum(k['mac_busy_ticks'] for k in kernels),missing_weight=sum(k['missing_data_ticks'] for k in kernels))
  out['packet_dag_activity']=dict(r.get('packet_dag_activity',r['activity']))
  out['activity']=dict(r['activity'],dram=r['actual_dram_bytes'],hb=r['actual_dram_bytes'])
  if 'packet_dag_activity' not in r:out['activity']['sram_read']=r['activity'].get('sram_read',0)+out['joint_kernel_activity']['sram_read']
  out['critical_attribution_note']='Joint memory/MAC node durations are not pure compute stalls; windows and counterfactual gains are nonadditive.'
 out.setdefault('combine_scheme','eager' if 'kernel_service_windows' in r else None)
 out.setdefault('down_partition','column' if 'kernel_service_windows' in r else None)
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sources',nargs='+',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);points=[];manifests=[]
 for directory in map(Path,a.sources):
  summary=directory/'summary.json'
  if not summary.exists():raise ValueError('Missing completed summary '+directory.name)
  rows=json.loads(summary.read_text())
  for row in rows:
   file=directory/(row['label']+'.json');p=compact(row);p.update(experiment=directory.name,point_sha256=hashlib.sha256(file.read_bytes()).hexdigest());points.append(p)
  provenance=json.loads((directory/'provenance.json').read_text());provenance['params']={k:(Path(v).name if k in ('routes','prior_routes','output') and v else v) for k,v in provenance['params'].items()}
  manifests.append(dict(directory=directory.name,summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest(),point_count=len(rows),pass_count=sum(r['status']=='PASS_ACCOUNTING' for r in rows),provenance=provenance))
 (out/'all-points.json').write_text(json.dumps(points,separators=(',',':'))+'\n');(out/'run-manifest.json').write_text(json.dumps(manifests,indent=2)+'\n')
 main=[r for r in points if r['experiment'].startswith('expert-p2') and r['status']=='PASS_ACCOUNTING'];aggregates=[]
 groups=defaultdict(list)
 for r in main:
  tp=r['label'].split('-tp')[1].split('-')[0];baseline=r['label'].split('-tp')[0]
  groups[r['batch'],tp,baseline,r['schedule'],r['order'],r['combine_scheme'],r['down_partition']].append(r['time_us'])
 for (b,tp,baseline,sched,order,combine,partition),values in sorted(groups.items(),key=str):
  aggregates.append(dict(batch=b,tp=tp,baseline=baseline,schedule=sched,order=order,combine_scheme=combine,down_partition=partition,samples=len(values),mean_us=float(np.mean(values)),geomean_us=float(np.exp(np.mean(np.log(values)))),p95_us=float(np.quantile(values,.95))))
 (out/'conventional-baselines.json').write_text(json.dumps(aggregates,indent=2)+'\n')
 isolates=[];pairs=defaultdict(dict)
 for r in points:
  if r['experiment'].startswith('expert-p3') and r['status']=='PASS_ACCOUNTING':pairs[r['batch'],r['label'].split('-tp')[1].split('-')[0],r['combine_scheme'],r['down_partition']][r['isolation']]=r
 for (b,tp,combine,partition),p in pairs.items():
  base=p['none']
  for iso,r in p.items():isolates.append(dict(batch=b,tp=tp,combine_scheme=combine,down_partition=partition,isolation=iso,time_us=r['time_us'],speedup=base['time_us']/r['time_us'],dram_bytes=r['actual_dram_bytes'],mac_flops=r['mac_flops'],critical_chain_ticks=r['critical_chain_ticks'],critical_gap_ticks=r['critical_gap_ticks']))
 (out/'physical-isolation.json').write_text(json.dumps(isolates,indent=2)+'\n');print('points',len(points),'pass',sum(r['status']=='PASS_ACCOUNTING' for r in points))
if __name__=='__main__':main()
