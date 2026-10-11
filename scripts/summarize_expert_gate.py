"""Compare fixed policies on matched captured cases; never choose per-case oracles."""
import json,argparse,re
from pathlib import Path
from collections import defaultdict
from math import exp,log

def gm(v):return exp(sum(map(log,v))/len(v))
def stats(rows):return dict(samples=len(rows),geomean_us=gm([r['time_us'] for r in rows]),mean_us=sum(r['time_us'] for r in rows)/len(rows))
def identity(r):return r['step'],r['layer']
def matched(a,b,work=True):
 a={identity(r):r for r in a};b={identity(r):r for r in b}
 if a.keys()!=b.keys():raise ValueError('Unmatched captured cases')
 if work and any(a[k]['mac_flops']!=b[k]['mac_flops'] or a[k]['actual_dram_bytes']!=b[k]['actual_dram_bytes'] for k in a):raise ValueError('Changed expert work/weight reads')
 return gm([a[k]['time_us']/b[k]['time_us'] for k in a])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results',required=True);a=ap.parse_args();out=Path(a.results);allpoints=json.loads((out/'all-points.json').read_text());points=[r for r in allpoints if r['status']=='PASS_ACCOUNTING']
 groups=defaultdict(list)
 for r in points:
  if r['experiment'].startswith('expert-p2'):groups[r['batch'],r['tp'],r['combine_scheme'],r['down_partition'],r['baseline'],r['schedule'],r['order']].append(r)
 best=[];fusion=[];layouts=[]
 for b in (8,32):
  for tp in ('1','4','16','hybrid'):
   for combine in ('eager','fused'):
    candidates=[(k,v) for k,v in groups.items() if k[:4]==(b,tp,combine,'column') and len(v)==20]
    key,rows=min(candidates,key=lambda kv:gm([r['time_us'] for r in kv[1]]))
    best.append(dict(batch=b,tp=tp,combine_scheme=combine,baseline=key[4],schedule=key[5],order=key[6],**stats(rows)))
    if combine=='fused':
     eager=groups[b,tp,'eager','column',*key[4:]]
     fusion.append(dict(batch=b,tp=tp,baseline=key[4],schedule=key[5],order=key[6],paired_speedup=matched(eager,rows),eager=stats(eager),fused=stats(rows),link_activity_ratio=gm([x['activity']['link']/y['activity']['link'] for x,y in zip(sorted(eager,key=identity),sorted(rows,key=identity))])))
   candidates=[(k,v) for k,v in groups.items() if k[:4]==(b,tp,'fused','row') and len(v)==6]
   key,row=min(candidates,key=lambda kv:gm([r['time_us'] for r in kv[1]]))
   column=[r for r in groups[b,tp,'fused','column',*key[4:]] if r['step'] in (0,127) and r['layer'] in (0,15,23)]
   layouts.append(dict(batch=b,tp=tp,baseline=key[4],schedule=key[5],order=key[6],paired_column_over_row=matched(column,row),column=stats(column),row=stats(row)))
 prompts=[];pg=defaultdict(list)
 for r in points:
  m=re.match(r'expert-promptfused-(topic_short|code_math)-(FP32|BF16)-',r['experiment'])
  if m and (r['schedule'],r['order']) in (('barrier','static'),('overlap','dynamic')):pg[m[1],m[2],r['tp'],r['down_partition'],r['schedule'],r['order']].append(r)
 for family in ('topic_short','code_math'):
  for tp in ('1','4','16','hybrid'):
   for partition in ('column','row'):
    for schedule,order in (('barrier','static'),('overlap','dynamic')):
     fp,bf=pg[family,'FP32',tp,partition,schedule,order],pg[family,'BF16',tp,partition,schedule,order]
     if len(fp)!=6 or len(bf)!=6:raise ValueError('Incomplete precision case grid')
     ratio=matched(fp,bf,work=False);bycase={identity(r):r for r in fp}
     prompts.append(dict(family=family,tp=tp,down_partition=partition,schedule=schedule,order=order,fp32=stats(fp),bf16=stats(bf),bf16_over_fp32_geomean=1/ratio,max_case_absolute_latency_change=max(abs(r['time_us']/bycase[identity(r)]['time_us']-1) for r in bf),same_mac_work=all(r['mac_flops']==bycase[identity(r)]['mac_flops'] for r in bf)))
 workspace=json.loads((out/'workspace-repair.json').read_text());p1=[]
 for base in ('B2_stream_fusion','B3_3d_placement'):
  r={x['label'].split(base+'-')[1]:x for x in workspace if x['baseline']==base};old,new,matched_rows=r['128-36-cohort'],r['152-18-rows'],r['128-36-rows']
  if new['activity']['mac']!=old['activity']['mac'] or new['activity']['dram']!=old['activity']['dram']:raise ValueError('Full-model P1 work changed')
  p1.append(dict(baseline=base,rows_152_over_cohort_128=new['tokens_s']/old['tokens_s'],rows_152_over_rows_128=new['tokens_s']/matched_rows['tokens_s'],row_workspace_high_bytes=new['live_workspace_high_bytes'],available_workspace_bytes=new['workspace_bytes']))
 routing=json.loads((out/'routing-records.json').read_text());intensity=[]
 for b in (8,32):
  rows=[r for r in routing if r['batch']==b];values=[8*b/(r['active_experts']+4) for r in rows]
  intensity.append(dict(batch=b,capture_cases=len(rows),mean_linear_flops_per_active_weight_byte=sum(values)/len(values),min=min(values),max=max(values),peak_compute_over_shared_memory_flops_per_byte=128/26.599,scope='Gate/up/down BF16 active weights, includes always-active shared expert of4x routed width; excludes activation/KV/vector traffic, physical padding and stage dependencies'))
 result=dict(scope='Fixed conventional policies on matched captured cases; conditional packet MoE subgraphs, not serving throughput, global schedule optimum or new hardware qualification',points=len(allpoints),pass_count=len(points),expected_cohort_failures=len(allpoints)-len(points),p1=p1,best_fixed_column_policies=best,paired_fusion=fusion,paired_down_layouts=layouts,paired_precision=prompts,captured_weight_reuse=intensity,research_go=True,hardware_go=False)
 (out/'decision-summary.json').write_text(json.dumps(result,indent=2)+'\n');print('Matched policy/byte/MAC comparisons PASS')
if __name__=='__main__':main()
