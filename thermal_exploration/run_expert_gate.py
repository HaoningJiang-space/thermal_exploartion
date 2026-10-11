"""Focused P1–P3, fixed points and explicit fidelity boundaries; no DSE."""
import argparse,gzip,hashlib,json,subprocess,time
from collections import Counter,defaultdict
from dataclasses import asdict
from pathlib import Path
import numpy as np
from .crossover_execution import Profile,CrossoverExecution
from .expert_execution import RowBlockedExecution,expert_graph
from .decode_graph import execute
from .layer_execution import resident_layout
from .model_contract import load_model,capacity,expected_mac_flops
from .run_crossover import routes_for
from .run import revision

STEPS=(0,32,64,96,127);LAYERS=(0,7,15,23)
SCHEDULERS=(('barrier','static'),('overlap','static'),('overlap','dynamic'))
ISOLATIONS=('none','bank_cycle','uniform_fast_tier','hb_only','ingress_only','mac_only','infinite_noc','ideal_memory')

def write(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def captured(path):
 p=Path(path);raw=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes();r=json.loads(raw)
 if not r.get('model_matched_capture') or r['model']!='Qwen/Qwen1.5-MoE-A2.7B':raise ValueError('Original checkpoint routing required')
 return r,hashlib.sha256(p.read_bytes()).hexdigest()

def stats(r,out):
 records=[];distribution={};coactivation={};temporal={}
 for b in (1,8,16,32):
  if b>r['max_batch']:continue
  co=Counter();previous={};overlap=[];expert_counts=Counter();active=[]
  for step in range(r['steps']):
   for l,layer in enumerate(r['routes']):
    rows=layer[step*r['max_batch']:step*r['max_batch']+b];counts=Counter(e for row in rows for e in row);keys=set(counts)
    for e in keys:
     for f in keys:
      if e<f:co[e,f]+=1
    if l in previous:overlap.append(len(keys&previous[l])/len(keys|previous[l]))
    previous[l]=keys;active.append(len(keys));expert_counts.update(counts.values())
    records.append(dict(batch=b,step=step,layer=l,active_experts=len(keys),tokens_per_expert=dict(counts),maximum_tokens=max(counts.values()),assignments=sum(counts.values()),skew_max_over_mean=max(counts.values())/(b*4/len(keys))))
  distribution[b]=dict(active_expert_mean=float(np.mean(active)),active_expert_min=min(active),active_expert_max=max(active),effective_expert_batch_histogram=dict(expert_counts))
  temporal[b]=dict(adjacent_step_active_set_jaccard_mean=float(np.mean(overlap)),samples=len(overlap))
  coactivation[b]=[dict(experts=[e,f],joint_occurrences=n) for (e,f),n in co.most_common(30)]
 write(out/'routing-records.json',records);write(out/'routing-distributions.json',dict(distribution=distribution,temporal=temporal,coactivation=coactivation,scope='All captured steps/layers; controlled prompts; no production generalization'))

def rows(r,out,baseline,steps):
 c=load_model('qwen15_moe');a=capacity(c,32,512,steps=steps);layout=resident_layout(c,a,baseline,r['training_expected_activations']);summaries=[]
 for peak,sram,model in ((128,36,'cohort'),(128,36,'rows'),(152,18,'cohort'),(152,18,'rows')):
  p=Profile(peak,sram);label=f'{baseline}-{peak}-{sram}-{model}';events=out/(label+'.jsonl.gz');total=Counter();ticks=0;high=0;perstep=[];status='PASS_ACCOUNTING'
  try:
   with gzip.open(events,'wt') as f:
    for step in range(steps):
     routes=routes_for(c,32,step,r,'matched_capture');e=(RowBlockedExecution if model=='rows' else CrossoverExecution)(c,a,layout,baseline=baseline,profile=p,schedule='prefetch_collective');z=e.token(32,512+step,routes)
     if z['activity']['mac']!=expected_mac_flops(c,32,512+step,routes):raise ValueError('Full-model work changed')
     total.update(z['activity']);high=max(high,max((x.get('live_expert_workspace_bytes',0) for x in z['events']),default=0));perstep.append(dict(step=step,time_us=z['time_us'],dram=z['activity']['dram'],mac=z['activity']['mac']))
     for ev in z['events']:f.write(json.dumps(dict(ev,step=step,offset_tick=ticks),separators=(',',':'))+'\n')
     ticks+=z['ticks']
   reason=None
  except ValueError as error:status='INFEASIBLE_FINITE_SCHEDULE';reason=str(error)
  result=dict(label=label,baseline=baseline,profile=asdict(p),area=p.area(),status=status,reason=reason,completed_steps=len(perstep),time_us=ticks*.00025,tokens_s=32*len(perstep)/(ticks*.25e-9) if ticks else None,activity=dict(total),live_workspace_high_bytes=high,workspace_bytes=p.budget(32,2048,5632)['expert_workspace_bytes'],step_records=perstep,event_file=events.name,event_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),scope='Complete24-layer conditional Decode; old cohort and known row-block schedule, not new hardware')
  write(out/(label+'.json'),result);summaries.append(result);write(out/'summary.json',summaries);print(label,status,result['tokens_s'],flush=True)

def point(c,layout,layer,route,p,schedule,order,isolation,out,label,full=False,down_partition='column',combine_scheme='fused',dispatch_scheme='broadcast_all',reduction_scheme='drain_all'):
 started=time.time()
 try:
  g,meta=expert_graph(c,layout,layer,route,p,schedule,order,isolation,down_partition,combine_scheme,dispatch_scheme,reduction_scheme)
  z=execute(g,'infinite_noc' if isolation=='infinite_noc' else 'baseline')
  if z['activity']['mac']!=meta['mac_flops']:raise ValueError('Independent expert work mismatch')
  events={e['id']:e for e in z['events']};latencies=[]
  for job in meta['jobs']:
   end=events[job['terminal']]['finish_tick'];latencies.append(dict(expert=job['expert'],tokens=job['tokens'],owners=job['owners'],count=job['count'],finish_us=end*.00025))
  chain=Counter()
  for ev in z['critical_path']:chain[ev['stage']]+=(ev['finish_tick']-ev['start_tick'])
  maxgap=sum(ev['unattributed_gap_ticks'] for ev in z['critical_path'])
  if sum(chain.values())+maxgap!=z['ticks']:raise ValueError('Critical chain does not close')
  result={k:z[k] for k in ('time_us','ticks','activity','per_tile_activity','buffer_high','credit_stall_probes','validation','fidelity')}
  result['packet_dag_activity']=dict(result['activity'])
  result['activity']=dict(result['activity'],dram=meta['actual_dram_bytes'],hb=meta['actual_dram_bytes'])
  result['activity']['sram_read']=result['activity'].get('sram_read',0)+sum(x['activity']['sram_read'] for x in meta['kernel_ledger'])
  result['critical_attribution_note']='Gate/up and down-row MAC nodes are JOINT memory/MAC services, not pure compute durations; component oracles are nonadditive.'
  result.update(dispatch_scheme=dispatch_scheme,reduction_scheme=reduction_scheme,private_sram_high=z['private_sram_high'],credit_group_high=z['credit_group_high'])
  by_stage=defaultdict(Counter)
  for node in g.nodes:by_stage[node.stage][node.kind]+=node.work
  result['stage_activity']={k:dict(v) for k,v in by_stage.items()}
  if dispatch_scheme!='broadcast_all' or reduction_scheme!='drain_all':
   combine=[e for e in z['events'] if e['stage']=='combine']
   result['communication_audit']=dict(input_delivery=meta['input_delivery'],semantic_ledger=meta['semantic_ledger'],first_combine_us=min(e['start_tick'] for e in combine)*.00025,last_local_expert_us=max(x['finish_us'] for x in latencies),credit_groups=g.meta.get('credit_groups',{}),buffer_caps=g.meta['buffer_caps'])
  result.update(status='PASS_ACCOUNTING',critical_path=z['critical_path'],critical_chain_ticks=dict(chain),critical_gap_ticks=maxgap,expert_service_latency=latencies,tail_expert=max(latencies,key=lambda x:x['finish_us']),mac_flops=meta['mac_flops'],actual_dram_bytes=meta['actual_dram_bytes'],active_weight_bytes=meta['active_weight_bytes'],all_expert_model_weight_bytes=meta['all_expert_model_weight_bytes'],counts=meta['counts'],effective_s_mfu=meta['mac_flops']/(z['ticks']*.25e-9*p.compute_tflops*1e12),effective_s_mbu=meta['active_weight_bytes']/(z['ticks']*.25e-9*p.service_tb_s*1e12),actual_read_utilization=meta['actual_dram_bytes']/(z['ticks']*.25e-9*p.service_tb_s*1e12),kernel_service_windows=[{k:v for k,v in rec.items() if k not in ('byte_completion','mac_blocks')} for rec in meta['kernel_ledger']],scope=meta['scope'])
  if full:
   path=out/(label+'-events.json.gz')
   with gzip.open(path,'wt') as f:json.dump(dict(nodes=[dict(id=n.id,kind=n.kind,tile=n.tile,work=n.work,deps=n.deps,resource=n.resource,ticks=n.ticks,stage=n.stage,tier=n.tier,leases=n.leases) for n in g.nodes],meta=g.meta,events=z['events']),f,separators=(',',':'))
   result.update(event_file=path.name,event_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),full_events_retained=True)
  else:result['full_events_retained']=False
 except ValueError as error:result=dict(status='INFEASIBLE_FINITE_SCHEDULE',reason=str(error))
 result.update(label=label,layer=layer,batch=len(route),schedule=schedule,order=order,isolation=isolation,down_partition=down_partition,combine_scheme=combine_scheme,dispatch_scheme=dispatch_scheme,reduction_scheme=reduction_scheme,elapsed_host_s=time.time()-started)
 write(out/(label+'.json'),result);print(label,result['status'],result.get('time_us',result.get('reason')),flush=True)
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--routes',required=True);ap.add_argument('--prior-routes');ap.add_argument('--output',required=True);ap.add_argument('--mode',choices=('stats','rows','experts','isolation'),required=True);ap.add_argument('--baseline',choices=('B2_stream_fusion','B3_3d_placement'),default='B3_3d_placement');ap.add_argument('--tp',choices=('1','4','16','hybrid'),default='16');ap.add_argument('--batch',type=int,default=8);ap.add_argument('--steps',type=int,default=128)
 ap.add_argument('--down-partition',choices=('row','column'),default='column')
 ap.add_argument('--combine-scheme',choices=('fused','eager'),default='fused')
 ap.add_argument('--sample-steps',nargs='+',type=int);ap.add_argument('--sample-layers',nargs='+',type=int)
 ap.add_argument('--isolation-names',nargs='+',choices=ISOLATIONS+('native_only','hb_ingress_only'))
 ap.add_argument('--probe-schedule',choices=('barrier','overlap'),default='overlap')
 ap.add_argument('--probe-order',choices=('static','dynamic'),default='dynamic')
 a=ap.parse_args()
 r,sha=captured(a.routes);out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
 write(out/'provenance.json',dict(source_commit=revision(),dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),routing_sha256=sha,route_model=r['model'],dtype=r['execution_dtype'],params=vars(a),selected_steps=STEPS,selected_layers=LAYERS,scope='Fixed P0–P3; no RTL or thermal scan'))
 if a.mode=='stats':stats(r,out);return
 if a.mode=='rows':rows(r,out,a.baseline,a.steps);return
 prior=r.get('training_expected_activations')
 if a.prior_routes:
  pr,ph=captured(a.prior_routes);prior=pr['training_expected_activations'];write(out/'prior-provenance.json',dict(routing_sha256=ph,scope='Frozen separate training prefix, never evaluation routing'))
 c=load_model('qwen15_moe');ad=capacity(c,a.batch,r['capture_context']);tp=a.tp if a.tp=='hybrid' else int(a.tp);layout=resident_layout(c,ad,a.baseline,prior,tp)
 write(out/'resident-layout.json',layout);summaries=[]
 steps=[s for s in a.sample_steps or STEPS if s<r['steps']];layers=[l for l in a.sample_layers or LAYERS if l<len(r['routes'])]
 if r['steps']<128:steps=sorted(set((0,r['steps']-1)));layers=[0,15,23]
 if a.mode=='isolation':steps=[0];layers=[0]
 for step in steps:
  for l in layers:
   route=r['routes'][l][step*r['max_batch']:step*r['max_batch']+a.batch]
   for schedule,order in SCHEDULERS if a.mode=='experts' else ((a.probe_schedule,a.probe_order),):
    for iso in ('none',) if a.mode=='experts' else a.isolation_names or ISOLATIONS:
     label=f'{a.baseline}-tp{tp}-b{a.batch}-l{l}-s{step}-{schedule}-{order}-{iso}'
     summaries.append(point(c,layout,l,route,Profile(),schedule,order,iso,out,label,full=(a.mode=='isolation' or step==0 and l==0),down_partition=a.down_partition,combine_scheme=a.combine_scheme))
     write(out/'summary.json',summaries)
if __name__=='__main__':main()
