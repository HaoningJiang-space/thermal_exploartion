"""Frozen crossover matrix; preserve admissions, all failures and raw events."""
import argparse,gzip,hashlib,json,subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import numpy as np
from .crossover_execution import Profile,CrossoverExecution,pipeline
from .layer_execution import resident_layout
from .model_contract import ROOT,load_model,capacity,expected_mac_flops
from .run import revision

ISOLATION_CASES=('llama_b1_c2k','llama_b4_c8k','qwen_b8_c2k')
FRONTIER_CASES=('llama_b1_c2k','llama_b4_c8k','llama_b16_c2k','qwen_b1_c2k','qwen_b8_c2k','qwen_b32_c512')

def routes_for(c,batch,step,route_data,mode):
    if c['model_type']=='llama':return None
    if mode=='matched_capture':
        if not route_data.get('model_matched_capture') or route_data['max_batch']<batch or route_data['steps']<=step:raise ValueError('Invalid matched route coverage; never repeat records')
        stride=route_data['max_batch']
        return [layer[step*stride:step*stride+batch] for layer in route_data['routes']]
    if mode!='uniform_control':raise ValueError('Unknown routing')
    rng=np.random.default_rng(20261011+step)
    return [[rng.choice(60,4,False).tolist() for token in range(batch)] for layer in range(24)]

def run_one(c,a,layout,profile,schedule,route_data,route_mode,out,scenario):
    baseline=layout.get('baseline','B3_3d_placement')
    label=f'{baseline}-{int(profile.compute_tflops)}tf-{int(profile.sram_mib)}mib-hb{int(profile.hb_tb_s)}-fifo{int(profile.fifo_ingress_bytes_tick)}-svc{profile.service_tb_s:.6f}-{profile.isolation}-{schedule}-{route_mode}'
    folder=out/scenario;folder.mkdir(exist_ok=True);rows=[];activity=Counter();critical=Counter();ticks=0;prefetch=0;overlap=0;kernel_states=Counter();path=folder/(label+'.jsonl.gz')
    try:
        with gzip.open(path,'wt') as f:
            for step in range(a['decode_steps']):
                context=a['context']+step;routes=routes_for(c,a['batch'],step,route_data,route_mode)
                e=CrossoverExecution(c,a,layout,baseline=baseline,profile=profile,schedule=schedule);r=e.token(a['batch'],context,routes)
                if r['activity']['mac']!=expected_mac_flops(c,a['batch'],context,routes):raise ValueError('Independent full-model work differs')
                if step==0:storage=r['sram_budget']
                rows.append(dict(step=step,time_us=r['time_us'],context=context,mac_flops=r['activity']['mac'],dram_bytes=r['activity']['dram']))
                activity.update(r['activity']);critical.update(r['critical_path_ticks'])
                prefetch+=sum(x['bytes'] for x in r['prefetch_ledger']);overlap+=len(r['collective_overlap_ledger'])
                for event in r['events']:
                    for window in event.get('tile_kernel_windows',{}).values():
                        kernel_states['mac_busy_ticks']+=window['mac_busy_ticks'];kernel_states['missing_data_ticks']+=window['missing_data_ticks']
                    event=dict(event,step=step,start_tick=event['start_tick']+ticks,finish_tick=event['finish_tick']+ticks)
                    if 'overlap_start_tick' in event:event['overlap_start_tick']+=ticks
                    f.write(json.dumps(event,separators=(',',':'))+'\n')
                ticks+=r['ticks']
        result=dict(scenario=scenario,model=c['name'],batch=a['batch'],context=a['context'],steps=a['decode_steps'],status='PASS_ACCOUNTING',
           admission=a,profile=asdict(profile),schedule=schedule,baseline=baseline,oracle='none',routing=route_mode,
           tensor_parts=16,directory=scenario,events_file=path.name,events_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
           time_us=ticks*.00025,tokens=a['batch']*a['decode_steps'],tokens_s=a['batch']*a['decode_steps']/(ticks*.25e-9),
           activity=dict(activity),critical_macro_path_ticks=dict(critical),kernel_states=dict(kernel_states),step_records=rows,
           prefetched_bytes=prefetch,collective_overlap_operators=overlap,area=profile.area(),sram_budget=storage,source_commit=revision(),
           data_supply_lower_bound_us=activity['dram']/(profile.service_tb_s*1e6),compute_lower_bound_us=activity['mac']/(profile.compute_tflops*1e6),
           arithmetic_intensity=activity['mac']/activity['dram'],roofline_intensity=profile.compute_tflops/profile.service_tb_s,
           route_context_transfer=route_mode=='matched_capture' and a['context']!=route_data['capture_context'],
           route_source_sha256=route_data.get('_file_sha256'),scope='Conditional whole-model structural Decode; named finite known schedule, not optimal scheduler or measured accelerator')
    except ValueError as error:
        result=dict(scenario=scenario,model=c['name'],profile=asdict(profile),schedule=schedule,routing=route_mode,
          status='INFEASIBLE_FINITE_SCHEDULE',reason=str(error),baseline=baseline,completed_steps=len(rows),admission=a,area=profile.area(),
          partial_events_file=path.name,source_commit=revision())
    (folder/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(scenario,label,result['status'],result.get('tokens_s',result.get('reason')),flush=True)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--routes');ap.add_argument('--cases',nargs='+');ap.add_argument('--steps',type=int,default=128);ap.add_argument('--mode',choices=('baseline','isolation','frontier','all'),default='all');ap.add_argument('--service',type=float,default=26.599);ap.add_argument('--uniform-control',action='store_true')
    ap.add_argument('--service-reference');a=ap.parse_args()
    reference=Path(a.service_reference) if a.service_reference else None
    if reference:
        ref=json.loads(reference.read_text())
        if ref.get('ratio')!=2:raise ValueError('Reference must use corrected clock domains')
        a.service=max(r['steady']['useful_tb_s'] for r in ref['records'] if r['mechanism']=='baseline')
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False);contract=json.loads((ROOT/'configs/crossover/contract.json').read_text())
    source=Path(a.routes) if a.routes else None
    routes=json.loads(source.read_text()) if source else {};routes['_file_sha256']=hashlib.sha256(source.read_bytes()).hexdigest() if source else None
    mode='uniform_control' if a.uniform_control else 'matched_capture'
    if mode=='matched_capture' and not source:raise ValueError('Matched capture required, never substitute projected routes')
    contract.update(source_commit=revision(),source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),steps=a.steps,routing=mode,route_sha256=routes['_file_sha256'],service_tb_s=a.service,service_reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest() if reference else None,frontier_cases=FRONTIER_CASES,isolation_cases=ISOLATION_CASES,
       assumptions=['35.25mm2 frozen as unavailable','MAC/read-port128+128 split for overlapped producer/reduction;128B writes shared by result/collective',
       'D1 guard is not theorematically attainable service for each operator','bank_cycle removes only tier bank-cycle ceiling; keeps shared D1 guard',
       'ingress_only removes FIFO input serialization while preserving HB and FIFO output rate; conventional SRAM copies eliminated by baseline',
       'Prefetch only immediately preceding non-memory/non-MAC phase;256KiB FIFO; routed experts wait for actual routing',
       'GatedFFN pairing and bounded expert-cohort accumulation are known software mechanisms','Full materialized LM-head output retained; reduced SRAM may reject a case that known streaming Logit Selection could recover',
       'Same frozen32GiB regional/tier capacity; all128steps; QwenC8192 extension isolated as control'])
    (out/'contract.json').write_text(json.dumps(contract,indent=2)+'\n');summaries=[];admissions=[]
    def add(c,ad,layout,p,s,scenario):
        from dataclasses import replace
        p=replace(p,service_tb_s=a.service)
        r=run_one(c,ad,layout,p,s,routes,mode,out,scenario);summaries.append(r)
        (out/'partial.json').write_text(json.dumps(summaries,indent=2)+'\n')
        return r
    for scenario in a.cases or contract['scenarios']:
        model,batch,context=contract['scenarios'][scenario];c=load_model(model);control=scenario.endswith('context_control')
        ad=capacity(c,batch,context,steps=a.steps,allow_context_extension=control);admissions.append(dict(scenario=scenario,**ad))
        if not ad['runnable']:
            summaries.append(dict(scenario=scenario,status='INFEASIBLE_ADMISSION',admission=ad));continue
        prior=routes.get('training_expected_activations') if mode=='matched_capture' else None
        layouts={b:dict(resident_layout(c,ad,b,prior),baseline=b) for b in ('B2_stream_fusion','B3_3d_placement')}
        default_runs=[]
        if a.mode in ('baseline','all'):
            for baseline,layout in layouts.items():
                for schedule in contract['scheduling']:default_runs.append(add(c,ad,layout,Profile(),schedule,scenario))
        valid=[r for r in default_runs if r['status']=='PASS_ACCOUNTING']
        strongest=min(valid,key=lambda r:r['time_us']) if valid else dict(baseline='B3_3d_placement',schedule='prefetch_collective')
        layout=layouts[strongest['baseline']];schedule=strongest['schedule']
        if a.mode in ('isolation','all') and scenario in ISOLATION_CASES:
            for isolation in contract['isolation']:add(c,ad,layout,Profile(isolation=isolation),schedule,scenario)
            add(c,ad,layout,Profile(hb_tb_s=16),schedule,scenario)
            add(c,ad,layout,Profile(fifo_ingress_bytes_tick=128),schedule,scenario)
        if a.mode in ('frontier','all') and scenario in FRONTIER_CASES:
            for peak,sram in contract['profiles']:
                if peak==128:continue
                for layout in layouts.values():
                    for schedule in ('serial','prefetch_collective'):add(c,ad,layout,Profile(peak,sram),schedule,scenario)
        (out/'admissions.json').write_text(json.dumps(admissions,indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n');print('Cache',pipeline.cache_info(),flush=True)
if __name__=='__main__':main()
