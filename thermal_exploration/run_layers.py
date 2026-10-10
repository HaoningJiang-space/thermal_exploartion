"""Six frozen complete-model Decode scenarios,128 steps; no silent admission."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from .model_contract import SCENARIOS,ROOT,load_model,capacity,expected_mac_flops
from .layer_execution import BASELINES,ORACLES,LayerExecution,resident_layout,tile_pipeline
from .run import revision


def routes_for(c,batch,step,route_data,mode):
    if c['model_type']=='llama':return None
    if mode=='public_projected':
        # Each step has disjoint token records, fixed maximum batch8. Smaller
        # batches use a subset of the SAME128-token-step sequence.
        return [layer[step*8:step*8+batch] for layer in route_data['routes']]
    if mode!='uniform':raise ValueError('Unknown route source')
    rng=np.random.default_rng(20261010+step)
    return [[rng.choice(60,4,replace=False).tolist() for _ in range(batch)] for _ in range(c['num_hidden_layers'])]


def run_case(c,admission,baseline,oracle,route_data,mode,directory,tp=16):
    prior=route_data['training_expected_activations'] if mode=='public_projected' else None
    layout=resident_layout(c,admission,baseline,prior,tp)
    name=baseline+'-'+oracle+'-'+mode+('-tp4' if tp==4 else '')
    event_file=directory/(name+'.jsonl.gz');rows=[];total=Counter();critical=Counter();all_ticks=0
    with gzip.open(event_file,'wt') as f:
        for step in range(admission['decode_steps']):
            context=admission['context']+step
            routes=routes_for(c,admission['batch'],step,route_data,mode)
            e=LayerExecution(c,admission,layout,baseline,oracle);r=e.token(admission['batch'],context,routes)
            expected=expected_mac_flops(c,admission['batch'],context,routes)
            if r['activity']['mac']!=expected:raise ValueError('Independent full-model FLOP ledger disagrees')
            row=dict(step=step,context=context,time_us=r['time_us'],mac_flops=expected,activity=r['activity'],critical_path_ticks=r['critical_path_ticks'])
            rows.append(row);total.update(r['activity']);critical.update(r['critical_path_ticks'])
            for i,event in enumerate(r['events']):
                event=dict(event,id=step*10000+i,deps=[step*10000+i-1] if i else ([step*10000-10000+len(previous)-1] if step else []),step=step,
                    start_tick=event['start_tick']+all_ticks,finish_tick=event['finish_tick']+all_ticks,
                    data_ownership='canonical activation shards; paired gate/up/down; FP32 collective partials',
                    scope='Hierarchical stage event; tile_kernel_windows preserve intra-stage overlap; not per-command/flit tracing')
                f.write(json.dumps(event,separators=(',',':'))+'\n')
            previous=r['events'];all_ticks+=r['ticks']
    result=dict(model=c['name'],baseline=baseline,oracle=oracle,routing=mode,tensor_parts=tp,
        batch=admission['batch'],initial_context=admission['context'],steps=admission['decode_steps'],
        time_us=all_ticks*.00025,tokens=admission['batch']*admission['decode_steps'],
        tokens_s=admission['batch']*admission['decode_steps']/(all_ticks*.25e-9),
        activity=dict(total),critical_macro_path_ticks=dict(critical),step_records=rows,
        admission=admission,layout=layout,source_commit=revision(),events_file=event_file.name,
        events_sha256=hashlib.sha256(event_file.read_bytes()).hexdigest(),
        qualification='Conditional hierarchy: Column crossover passes; Row/2D old H3 fail10%; full Decode is not independently prediction-validated',
        baseline_scope='Named implemented mechanisms, NOT complete SET/SoMa/ATLAS/DeepStack/HDA algorithm reproductions',
        routing_scope='Qwen2 public trace projection, not Qwen1.5 captured inference' if mode=='public_projected' else 'Uniform seeded control',
        scope='Whole-model structural Decode latency; no model-weight execution, numerical accuracy, serving overhead or sampling correctness claim')
    (directory/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(c['name'],admission['batch'],admission['context'],name,result['tokens_s'],flush=True)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--allow-context-extension',action='store_true');ap.add_argument('--cases',nargs='+',choices=SCENARIOS,default=list(SCENARIOS));a=ap.parse_args()
    out=Path(a.output)
    if out.exists():raise ValueError('Never overwrite evidence')
    out.mkdir(parents=True);routes=json.loads((ROOT/'configs/routing/hda_qwen_projected.json').read_text());summaries=[];admissions=[]
    (out/'contract.json').write_text(json.dumps(dict(source_commit=revision(),source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        scenarios=SCENARIOS,steps=128,baselines=BASELINES,oracles=ORACLES,area_mm2=121,dram_bytes=32*2**30,sram_bytes=36*2**20,
        peak_tflops=128,hb_tb_s=32,noc_link_gb_s=32,temperature_limit_c=85,
        route_source={k:v for k,v in routes.items() if k not in ('routes','training_expected_activations')},
        assumptions=['D1 streaming guard26.599TB/s plus tier bank-cycle bounds','Independent256MiB physical tier/region capacities',
        'B2/B3 known bounded ingress FIFO and registered partials:0.8mm2/0.08W charged, same compute and36MiB',
        'Conservative operator/layer barriers; no claimed optimal SET/SoMa global schedule','No DRAM command traces in full-model hierarchy',
        'Complete causal layer/step order; no autoregressive speculation','Context-extension flag is an architectural assumption, not validated inference quality']),indent=2)+'\n')
    for scenario in a.cases:
        model,batch,context=SCENARIOS[scenario];c=load_model(model);admission=capacity(c,batch,context,allow_context_extension=a.allow_context_extension)
        admissions.append(dict(scenario=scenario,**admission));(out/'admissions.json').write_text(json.dumps(admissions,indent=2)+'\n')
        if not admission['runnable']:
            summaries.append(dict(scenario=scenario,status='INFEASIBLE',admission=admission));continue
        directory=out/scenario;directory.mkdir()
        mode='public_projected' if c['model_type']=='qwen2_moe' else 'uniform'
        runs=[(b,'none',mode,16) for b in BASELINES]+[('B3_3d_placement',o,mode,16) for o in ORACLES if o!='none']
        if c['model_type']=='qwen2_moe':runs.extend([('B3_3d_placement','none',mode,4),('B3_3d_placement','none','uniform',16)])
        for baseline,oracle,route_mode,tp in runs:
            r=run_case(c,admission,baseline,oracle,routes,route_mode,directory,tp)
            compact={k:v for k,v in r.items() if k not in ('step_records','layout')};compact.update(scenario=scenario,status='PASS_ACCOUNTING',directory=scenario)
            summaries.append(compact);(out/'partial.json').write_text(json.dumps(summaries,indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    print('Kernel cache',tile_pipeline.cache_info(),flush=True)


if __name__=='__main__':main()
