"""Archive all frozen complete-model results and explicit conditional evidence.

Figures show structural simulation, not measured inference. Macro critical
reasons are mutually exclusive chosen-stage labels, not additive oracle gains.
"""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--layers', required=True)
    ap.add_argument('--original', required=True)
    ap.add_argument('--thermal', required=True)
    ap.add_argument('--output', required=True)
    a=ap.parse_args()
    layers,original,thermal,out=map(Path,(a.layers,a.original,a.thermal,a.output))
    out.mkdir(parents=True,exist_ok=False)
    rows=read(layers/'summary.json');old=read(original/'summary.json')
    heat=read(thermal/'summary.json');convergence=read(thermal/'convergence.json')
    if len(rows)!=60 or len(heat)!=135:raise ValueError('Incomplete frozen experiment matrix')
    for r in rows:
        if r['status']!='PASS_ACCOUNTING' or r['steps']!=128:raise ValueError('Missing completed run')
        if sum(r['critical_macro_path_ticks'].values())!=round(r['time_us']/.00025):raise ValueError('Critical-stage partition does not close')
        if not r['admission']['capacity_feasible']:raise ValueError('Invalid resident admission')
    for filename in ('contract.json','admissions.json','derivation.json'):
        shutil.copyfile(layers/filename,out/filename)
    shutil.copyfile(thermal/'contract.json',out/'thermal-contract.json')
    write(out/'all-points.json',rows);write(out/'original-all-points.json',old)
    write(out/'thermal-all-points.json',heat);write(out/'convergence.json',convergence)
    keys=('scenario','baseline','oracle','routing','tensor_parts','tokens_s','time_us','steps','source_commit')
    with (out/'all-points.csv').open('w') as f:
        w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in rows)
    keys=('workload','baseline','tensor_parts','scenario','t0_tokens_s','t1_layer_sustainable_tokens_s','t2_spatial_steady_tokens_s','sustainable_tokens_s','energy_per_token_j','periodic_logic_peak_c','periodic_dram_peak_c','pace_factor','area_mm2')
    with (out/'thermal-all-points.csv').open('w') as f:
        w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in heat)
    scenarios=list(read(layers/'contract.json')['scenarios']);baselines=['B0_local','B1_dataflow','B2_stream_fusion','B3_3d_placement']
    def chosen(s,b='B3_3d_placement',oracle='none'):
        return next(r for r in rows if r['scenario']==s and r['baseline']==b and r['oracle']==oracle and r['tensor_parts']==16 and (r['routing']=='public_projected' or r['model']=='llama31_8b'))
    best={s:max((chosen(s,b) for b in baselines),key=lambda r:r['tokens_s']) for s in scenarios}
    reasons=['memory/storage','compute','communication/synchronization','vector/local state','KV update']
    fig,axes=plt.subplots(1,2,figsize=(12,4.5));x=np.arange(6);width=.19
    for i,b in enumerate(baselines):axes[0].bar(x+(i-1.5)*width,[chosen(s,b)['tokens_s'] for s in scenarios],width,label=b.split('_')[0])
    axes[0].set_xticks(x,scenarios,rotation=35,ha='right');axes[0].set_ylabel('Conditional full-model tokens/s');axes[0].legend(ncol=4)
    bottom=np.zeros(6)
    for reason in reasons:
        v=np.array([best[s]['critical_macro_path_ticks'].get(reason,0)/(best[s]['time_us']/.00025)*100 for s in scenarios])
        axes[1].bar(x,v,bottom=bottom,label=reason);bottom+=v
    axes[1].set_xticks(x,scenarios,rotation=35,ha='right');axes[1].set_ylim(0,100);axes[1].set_ylabel('Chosen macro critical path (%)');axes[1].legend(fontsize=8)
    fig.suptitle('Full structural Decode: known baselines and critical-stage attribution');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('architecture_bottlenecks.'+ext),dpi=180)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.3))
    capacities={'Useful MAC':('mac',128e12),'HB delivered':('hb',32e12),
                'SRAM reads':('sram_read',16e12),'SRAM writes':('sram_write',16*.512e12)}
    for i,(label,(kind,rate)) in enumerate(capacities.items()):
        vals=[100*best[s]['activity'].get(kind,0)/(best[s]['time_us']*1e-6*rate) for s in scenarios]
        ax.bar(x+(i-1.5)*.2,vals,.2,label=label)
    ax.set_xticks(x,scenarios,rotation=35,ha='right');ax.set_ylabel('Whole-run work / peak service (%)');ax.legend(ncol=4,fontsize=8)
    ax.set_title('Aggregate demand; not instantaneous occupancy or DRAM Row-hit measurement');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('physical_resource_demand.'+ext),dpi=180)
    plt.close(fig)
    # State windows are constructive bounds from the chosen sequential DAG,
    # not measured SRAM lease histories or minimal communication lower bounds.
    lifetimes=[];kernel_bounds=[]
    for s in scenarios:
        r=best[s];events=[]
        with gzip.open(layers/r['directory']/r['events_file'],'rt') as f:
            for line in f:
                e=json.loads(line)
                if e['step']>0:break
                events.append(e)
                for tile,w in e.get('tile_kernel_windows',{}).items():
                    kernel_bounds.append(dict(scenario=s,stage=e['stage'],tile=int(tile),response_bytes=w['max_response_bytes'],live_weight_bytes=w['max_live_weight_bytes']))
        for layer in range(32 if r['model']=='llama31_8b' else 24):
            prefix=f'layer{layer}.';group=[e for e in events if e['stage'].startswith(prefix)];by={e['stage'][len(prefix):]:e for e in group}
            for name,producer,consumer in [('Residual input','input_norm','residual'),('Normalized FFN input','ffn_input_distribution','residual'),('Projection partial','o_projection_result_state','o_reduce')]:
                p,c=by[producer],by[consumer]
                lifetimes.append(dict(scenario=s,layer=layer,state=name,from_tick=p['finish_tick'],through_tick=c['finish_tick'],chosen_live_window_us=(c['finish_tick']-p['finish_tick'])*.00025,
                    scope='Chosen DAG residency window; no claim of measured or irreducible minimum lifetime'))
    with (out/'state-windows.csv').open('w') as f:
        w=csv.DictWriter(f,tuple(lifetimes[0]));w.writeheader();w.writerows(lifetimes)
    write(out/'kernel-capacity-bounds.json',dict(maximum_response_bytes=max(r['response_bytes'] for r in kernel_bounds),maximum_live_weight_bytes=max(r['live_weight_bytes'] for r in kernel_bounds),
        response_limit_bytes=65536,private_storage_bytes=36*2**20//16,scope='Constructive finite kernel slot reservation maxima; first complete-model step of best known baseline; other steps accounting remains in raw traces'))
    fig,ax=plt.subplots(figsize=(9,4));states=['Residual input','Normalized FFN input','Projection partial']
    for i,state in enumerate(states):
        vals=[max(r['chosen_live_window_us'] for r in lifetimes if r['scenario']==s and r['state']==state) for s in scenarios]
        ax.plot(x,vals,'o-',label=state)
    ax.set_xticks(x,scenarios,rotation=35,ha='right');ax.set_ylabel('Chosen residency window (μs)');ax.legend(fontsize=8)
    ax.set_title('First Decode step: state kept through its final declared consumer');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('state_lifetimes.'+ext),dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for model,marker,color in [('llama31_8b','o','#237b83'),('qwen15_moe','s','#b17d32')]:
        for s in scenarios:
            r=best[s]
            if r['model']!=model:continue
            axes[0].scatter(r['batch'],r['initial_context'],s=170,marker=marker,color=color)
            offset=(5,10) if model=='llama31_8b' else (5,-14)
            axes[0].annotate(s.replace('llama_','L ').replace('qwen_','Q '),(r['batch'],r['initial_context']),xytext=offset,textcoords='offset points',fontsize=8)
    axes[0].set(xlabel='Decode batch',ylabel='Initial context',yscale='log',ylim=(1300,52000),xlim=(.6,9.1),title='Six admitted cases; no interpolation')
    labels=['DRAM read','SRAM R+W','NoC byte-hops']
    for i,label in enumerate(labels):
        vals=[(best[s]['activity'].get('dram',0) if i==0 else best[s]['activity'].get('sram_read',0)+best[s]['activity'].get('sram_write',0) if i==1 else best[s]['activity'].get('link',0))/best[s]['tokens']/2**20 for s in scenarios]
        axes[1].bar(x+(i-1)*.25,vals,.25,label=label)
    axes[1].set_xticks(x,scenarios,rotation=35,ha='right');axes[1].set_ylabel('MiB / generated token');axes[1].set_yscale('log');axes[1].legend(fontsize=8)
    fig.suptitle('Memory/storage includes delivery, finite copies and operand service');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('movement_and_map.'+ext),dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,4.7))
    oracles=['ideal_memory','infinite_noc','ideal_buffer','ideal_collective','direct_producer_stream']
    gains=[]
    for i,o in enumerate(oracles):
        v=[100*(chosen(s,oracle=o)['tokens_s']/chosen(s)['tokens_s']-1) for s in scenarios];gains.append(v)
        axes[0 if o=='ideal_memory' else 1].plot(x,v,'o-',label=o.replace('_',' '))
    for ax in axes[:2]:
        ax.axhline(0,color='black',lw=.7);ax.set_xticks(x,scenarios,rotation=35,ha='right');ax.set_ylabel('Matched B3 change (%)');ax.legend(fontsize=7)
    axes[0].set_title('Memory oracle removes DRAM and HB waits')
    axes[1].set_title('Other resource oracles (independent scale)')
    for i,(key,label) in enumerate([('t0_tokens_s','T0'),('t1_layer_sustainable_tokens_s','T1 layer steady'),('t2_spatial_steady_tokens_s','T2 spatial steady'),('sustainable_tokens_s','T2 periodic')]):
        v=[]
        for s in scenarios:
            h=next(h for h in heat if h['workload']==s and h['baseline']==best[s]['baseline'] and h['tensor_parts']==16 and h['scenario']=='cooling_weak')
            v.append(h[key])
        axes[2].bar(x+(i-1.5)*.2,v,.2,label=label)
    axes[2].set_xticks(x,scenarios,rotation=35,ha='right');axes[2].set_ylabel('Conditional tokens/s');axes[2].legend(fontsize=7)
    axes[2].set_title('Same baseline, weak cooling')
    fig.suptitle('Oracle effects overlap; none is a paid new architecture');fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('isolation_and_thermal.'+ext),dpi=180)
    plt.close(fig)
    # Spatial source fields and bounded periodic peaks for one fixed high-state case.
    h=next(h for h in heat if h['workload']=='qwen_b8_c2k' and h['baseline']=='B3_3d_placement' and h['tensor_parts']==16 and h['scenario']=='default')
    fig,axes=plt.subplots(1,2,figsize=(8,3.8))
    for i,layer in enumerate(('Logic','Equivalent DRAM')):
        im=axes[i].imshow(np.asarray(h['node_peak_upper_c'])[i*16:(i+1)*16].reshape(4,4),cmap='inferno',vmin=25,vmax=85)
        axes[i].set_title(layer+'\nPeriodic peak upper bound',fontsize=10);axes[i].set_xticks([]);axes[i].set_yticks([])
    fig.colorbar(im,ax=axes,shrink=.8,label='°C');fig.suptitle('Qwen B8/C2048; assumed equivalent-layer geometry')
    for ext in ('png','pdf'):fig.savefig(out/('spatial_temperature.'+ext),dpi=180,bbox_inches='tight')
    plt.close(fig)
    audit=dict(completed_runs=60,steps_per_run=128,total_model_steps=60*128,thermal_points=135,
        distinct_scenarios=6,all_capacity_feasible=True,all_macro_critical_paths_close=True,
        useful_mac_work='Independently verified each step by model_contract.expected_mac_flops',
        aggregate_dynamic_energy_closure='Verified by event_energy for every thermal input',
        fastest_known_t0={s:dict(baseline=best[s]['baseline'],tokens_s=best[s]['tokens_s']) for s in scenarios},
        matched_counterfactuals={o:dict(zip(scenarios,gains[i])) for i,o in enumerate(oracles)},
        evidence_scope='Structural full-model execution; conditional finite resources; no numerical model-weight execution or independent full-inference validation')
    write(out/'accounting-audit.json',audit)
    write(out/'artifact-digests.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()})
    print('Archived all60 cases,135 thermal points and fixed convergence controls')


if __name__=='__main__':main()
