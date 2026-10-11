"""Frozen P4-A real-route points; no synthetic performance workloads or DSE."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from .run_expert_gate import captured,write,point
from .model_contract import load_model,capacity
from .layer_execution import resident_layout
from .crossover_execution import Profile
from .expert_execution import expert_graph
from .moe_numerical import compare,check_ledger

CASES=((0,0),(32,7),(127,23)) # primary then two predeclared holdouts
DISPATCHES=('broadcast_all','destination_only','decoupled')
REDUCTIONS=('drain_all','row_ready','row_ready_128')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--routes',required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--batch',type=int,choices=(8,32),default=8);ap.add_argument('--tp',type=int,choices=(4,16),default=16)
    ap.add_argument('--down-partition',choices=('column','row'),default='row');ap.add_argument('--dispatch',choices=DISPATCHES,default='broadcast_all')
    ap.add_argument('--reduction',choices=REDUCTIONS,default='drain_all');ap.add_argument('--numerical-only',action='store_true')
    a=ap.parse_args();r,distribution_sha=captured(a.routes)
    raw=Path(a.routes).read_bytes()
    if Path(a.routes).suffix=='.gz':
        import gzip
        raw=gzip.decompress(raw)
    route_sha=hashlib.sha256(raw).hexdigest()
    if route_sha!='24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6':raise ValueError('Use frozen original Qwen capture')
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('Research points require clean frozen source')
    a.output.mkdir(parents=True,exist_ok=False);source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    params={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}
    write(a.output/'provenance.json',dict(source_commit=source,dirty=False,routing_sha256=route_sha,distribution_sha256=distribution_sha,checkpoint_revision=r['checkpoint_revision'],execution_dtype=r['execution_dtype'],cases=[dict(step=s,layer=l,role='primary' if i==0 else 'holdout') for i,(s,l) in enumerate(CASES)],params=params,scope='P4-A only; unchanged joint memory/MAC abstraction, frozen B3 placement and paid resources'))
    c=load_model('qwen15_moe');layout=resident_layout(c,capacity(c,a.batch,512),'B3_3d_placement',r['training_expected_activations'],a.tp)
    write(a.output/'resident-layout.json',layout);summaries=[]
    for step,layer in CASES:
        routes=r['routes'][layer][step*r['max_batch']:step*r['max_batch']+a.batch]
        probs=r['route_probabilities'][layer][step*r['max_batch']:step*r['max_batch']+a.batch]
        case_hash=hashlib.sha256(json.dumps(dict(routes=routes,probabilities=probs),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if a.numerical_only:
            small=dict(c,hidden_size=256,moe_intermediate_size=32,shared_expert_intermediate_size=128)
            # Only semantic validation uses small deterministic tensors.
            # Owners/tier placement are derived with the same frozen rule.
            small_layout=resident_layout(small,capacity(small,a.batch,512),'B3_3d_placement',r['training_expected_activations'],a.tp)
            g,meta=expert_graph(small,small_layout,layer,routes,Profile(),schedule='barrier',order='static',down_partition=a.down_partition,dispatch_scheme=a.dispatch,reduction_scheme=a.reduction)
            for dtype in ('FP32','BF16'):
                rec=compare(small,routes,probs,meta,dtype)
                rec.update(step=step,layer=layer,tp=a.tp,down_partition=a.down_partition,route_case_sha256=case_hash)
                summaries.append(rec);write(a.output/'summary.json',summaries)
            continue
        # Exact full model dimensions, actual tokens and frozen weight bytes.
        g,meta=expert_graph(c,layout,layer,routes,Profile(),schedule='barrier',order='static',down_partition=a.down_partition,dispatch_scheme=a.dispatch,reduction_scheme=a.reduction)
        check_ledger(c,routes,meta)
        del g,meta
        for isolation in ('none','infinite_noc'):
            label=f'b{a.batch}-tp{a.tp}-{a.down_partition}-s{step}-l{layer}-{a.dispatch}-{a.reduction}-{isolation}'
            rec=point(c,layout,layer,routes,Profile(),'barrier','static',isolation,a.output,label,full=True,down_partition=a.down_partition,dispatch_scheme=a.dispatch,reduction_scheme=a.reduction)
            rec.update(step=step,tp=a.tp,route_case_sha256=case_hash,role='primary' if step==0 else 'holdout')
            write(a.output/(label+'.json'),rec);summaries.append(rec);write(a.output/'summary.json',summaries)
            if rec['status']!='PASS_ACCOUNTING':raise ValueError('Preserve failed point; P4-A not qualified')

if __name__=='__main__':main()
