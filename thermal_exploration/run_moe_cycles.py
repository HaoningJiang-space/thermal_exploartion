"""Frozen real-route full MoE qualification; no smoke performance mode."""
import argparse,csv,gzip,hashlib,json,subprocess,sys,time,heapq,shutil
from pathlib import Path
from .model_contract import load_model,capacity
from .layer_execution import resident_layout
from .run_expert_gate import captured
from .moe_cycle_program import program,write_program
from .moe_cycle import execute
from .moe_cycle_audit import replay,rows
from .moe_numerical import compare
from .run_g4 import RAMULATOR_COMMIT,verify_upstream
from .multitier import config,TierLegality
from .run_organization import check_commands
from .hb_trace import address_vector

HEADERS={'nodes':['id','start','finish'],'ports':['tick','tile','read','write','vector','hb','fifo'],'leases':['tick','resource','tile','delta'],'router':['tick','tile','port','vc','delta','credit'],'requests':['id','accepted','depart','address'],'service':['tick','id','kind','amount']}

def compact(path):
    with path.open('rb') as f,gzip.open(str(path)+'.gz','wb',compresslevel=3) as out:shutil.copyfileobj(f,out)
    path.unlink()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--routes',required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--ramulator-root',type=Path,required=True);ap.add_argument('--exe',type=Path,required=True);ap.add_argument('--batch',type=int,choices=(8,32),required=True);ap.add_argument('--tp',type=int,choices=(4,16),required=True);ap.add_argument('--down',choices=('row','column'),required=True);ap.add_argument('--step',type=int,choices=(0,32,127),required=True);ap.add_argument('--layer',type=int,choices=(0,7,23),required=True);ap.add_argument('--scope',choices=('cold','reused','contending','moe'),required=True);a=ap.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('Frozen clean source required')
    r,digest=captured(a.routes)
    if digest!='24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6':raise ValueError('Original decompressed trace required')
    root=a.ramulator_root.resolve()
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=RAMULATOR_COMMIT:raise ValueError('Pinned Ramulator required')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sys.path[:0]=[str(root/'python'),str(root)];verify_upstream(root)
    c=load_model('qwen15_moe');routes=r['routes'][a.layer][a.step*32:a.step*32+a.batch];probs=r['route_probabilities'][a.layer][a.step*32:a.step*32+a.batch]
    selected=None if a.scope=='moe' else {'cold':[12],'reused':[10],'contending':[10,34]}[a.scope];shared=a.scope=='moe';grain='fine_prefetch' if a.scope=='contending' else 'fine_fixed'
    layout=resident_layout(c,capacity(c,a.batch,512),'B3_3d_placement',r['training_expected_activations'],a.tp)
    p=program(c,layout,a.layer,routes,a.down,grain,selected,shared);write_program(p,out/'program')
    (out/'provenance.json').write_text(json.dumps(dict(source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),routing_sha256=digest,params={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},ramulator=RAMULATOR_COMMIT,scope='Full true MoE shapes and real routing; shared builder, independent executors; no empirical fitting'),indent=2)+'\n')
    small=dict(c,hidden_size=512,moe_intermediate_size=256,shared_expert_intermediate_size=512)
    sl=resident_layout(small,capacity(small,a.batch,512),'B3_3d_placement',r['training_expected_activations'],a.tp)
    sp=program(small,sl,a.layer,routes,a.down,grain,selected,shared)
    numerical=[compare(small,routes,probs,sp['meta'],dtype,accumulation='fixed_k') for dtype in ('FP32','BF16')];(out/'numerical.json').write_text(json.dumps(numerical,indent=2)+'\n');del sp
    results=[]
    for backend in ('native','fluid'):
        case=out/backend;case.mkdir();dram,cfg=config(root,case,refresh=True);(case/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
        with (case/'execution.log').open('w') as log:subprocess.run([str(a.exe.resolve()),str(case/'config.json'),str(out/'program'),str(case/'run'),backend],stdout=log,stderr=log,check=True)
        z=json.loads((case/'run-driver.json').read_text());z.update(backend=backend,time_us=z['ticks']*.00025);z['replay']=replay(p,case/'run',z)
        rd={x['id']:x for x in rows(case/'run-requests.csv')};ids=sorted(rd);index={node:i for i,node in enumerate(ids)}
        req=[dict(id=i,addr_vec=address_vector(rd[node]['address'],2),source_tile=p['nodes'][node]['tile']) for i,node in enumerate(ids)]
        events=[dict(id=i,accepted=rd[node]['accepted'],completed=rd[node]['depart']) for i,node in enumerate(ids)]
        def commands(path):
            with path.open() as f:yield from csv.DictReader(f)
        merged=heapq.merge(*(commands(case/f'transaction-commands.ch{ch}.csv') for ch in range(16)),key=lambda x:int(x['clock']));tier=TierLegality()
        from tests.device_timings.harness import DeviceUnderTest
        level_names=DeviceUnderTest(dram).level_names
        def remapped():
            for row in merged:
                vec=[int(row[k]) for k in level_names];tier.issue(row['command'],vec,int(row['clock']))
                if row['command'] in ('RD','RDA'):row['transaction_id']=str(index[int(row['transaction_id'])])
                yield row
        z['commands']=check_commands(dram,req if backend=='native' else [],events if backend=='native' else [],remapped());z['scope']='Same semantic DAG and finite physical resources, independent execution frontends; tier timing surrogate, not silicon validation'
        (case/'result.json').write_text(json.dumps(z,indent=2)+'\n');results.append(z)
        for path in case.glob('*.csv'):compact(path)
        print(backend,z['time_us'],z['replay']['status'],flush=True)
    handles={};writers={}
    for name,header in HEADERS.items():
        handles[name]=gzip.open(out/('python-'+name+'.csv.gz'),'wt',compresslevel=3,newline='');writers[name]=csv.writer(handles[name]);writers[name].writerow(header)
    try:z=execute(p,lambda kind,row:writers[kind].writerow(row))
    finally:
        for f in handles.values():f.close()
    z['replay']=replay(p,out/'python',z);(out/'python-result.json').write_text(json.dumps(z,indent=2)+'\n')
    # Trace checks locate first divergence; raw evidence is not substituted
    # into predictions. Native memory timing may legitimately differ.
    diffs={}
    for name in HEADERS:
        first=None;count=0
        native=rows(out/'fluid'/('run-'+name+'.csv.gz'));candidate=rows(out/('python-'+name+'.csv.gz'))
        for i,(aa,bb) in enumerate(__import__('itertools').zip_longest(native,candidate)):
            count=i+1
            if aa!=bb:first=dict(row=i,reference=aa,prediction=bb);break
        diffs[name]=dict(equal=first is None,rows_compared=count,first_divergence=first)
    qualification=dict(source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),params={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},references=results,predictor=z,absolute_native_error=z['time_us']/results[0]['time_us']-1,absolute_target=.1,absolute_pass=abs(z['time_us']/results[0]['time_us']-1)<=.1,fluid_trace_comparison=diffs,full_moe=a.scope=='moe',shared_preserved=shared,selected_experts=selected)
    (out/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
    # Retain exact TSV, program and CSV bytes as gzip after interpreters finish.
    for path in (out/'program').iterdir():
        if path.suffix in ('.json','.tsv'):compact(path)
    print('Python',z['time_us'],'native_error',qualification['absolute_native_error'],'fluid_exact',all(x['equal'] for x in diffs.values()),flush=True)
if __name__=='__main__':main()
