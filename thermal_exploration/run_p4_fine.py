"""Focused P4-B, original routing and exact macro controls, no DSE."""
import argparse,gzip,hashlib,json,subprocess
from pathlib import Path
from collections import Counter,defaultdict
from .run_expert_gate import captured,point,write
from .model_contract import load_model,capacity
from .layer_execution import resident_layout
from .crossover_execution import Profile
from .expert_execution import expert_graph
from .moe_numerical import check_ledger,compare
from .decode_graph import execute

def selection(r):
 routes=r['routes'][0][:32];counts=Counter(e for row in routes for e in row)
 cold=min(e for e,n in counts.items() if n==1);hot=min(e for e,n in counts.items() if n==max(counts.values()))
 other=min(e for e,n in counts.items() if e!=hot and n==counts[hot] and e%4==hot%4)
 return {name:dict(expert=e,tokens=[t for t,row in enumerate(routes) if e in row],count=counts[e]) for name,e in (('cold',cold),('reused',hot),('contending',other))}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--routes',required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--batch',type=int,choices=(8,32),required=True);ap.add_argument('--tp',type=int,choices=(4,16),required=True);ap.add_argument('--down',choices=('row','column'),required=True);ap.add_argument('--grain',choices=('macro','fine_fixed','fine_prefetch'),required=True);a=ap.parse_args()
 r,sha=captured(a.routes)
 if sha!='24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6':raise ValueError('Frozen decompressed real trace required')
 if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('Clean source required')
 a.output.mkdir(exist_ok=False,parents=True);c=load_model('qwen15_moe');layout=resident_layout(c,capacity(c,a.batch,512),'B3_3d_placement',r['training_expected_activations'],a.tp)
 write(a.output/'provenance.json',dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),source_dirty=False,routing_sha256=sha,params={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},selected_case=dict(layer=0,step=0),selected_experts=selection(r)))
 write(a.output/'resident-layout.json',layout);routes=r['routes'][0][:a.batch];probs=r['route_probabilities'][0][:a.batch]
 g,meta=expert_graph(c,layout,0,routes,Profile(),schedule='barrier',order='static',down_partition=a.down,reduction_scheme='row_ready_128',execution_grain=a.grain);check_ledger(c,routes,meta);del g,meta
 small=dict(c,hidden_size=256,moe_intermediate_size=32,shared_expert_intermediate_size=128);sl=resident_layout(small,capacity(small,a.batch,512),'B3_3d_placement',r['training_expected_activations'],a.tp)
 _,sm=expert_graph(small,sl,0,routes,Profile(),schedule='barrier',order='static',down_partition=a.down,reduction_scheme='row_ready_128',execution_grain=a.grain)
 write(a.output/'numerical.json',[compare(small,routes,probs,sm,dtype) for dtype in ('FP32','BF16')])
 probes=[('none','baseline')]
 if a.tp==16 and a.down=='row':probes += [('none','link_only'),('none','flight_only'),('none','infinite_noc'),('mac_only','baseline')]
 rows=[]
 for isolation,noc in probes:
  label=f'b{a.batch}-tp{a.tp}-{a.down}-{a.grain}-{isolation}-{noc}'
  rec=point(c,layout,0,routes,Profile(),'barrier','static',isolation,a.output,label,full=True,down_partition=a.down,reduction_scheme='row_ready_128',execution_grain=a.grain,noc_mode=noc)
  if rec['status']!='PASS_ACCOUNTING':raise ValueError('Keep failure, stop qualification')
  rec.update(tp=a.tp,step=0);write(a.output/(label+'.json'),rec);rows.append(rec);write(a.output/'summary.json',rows)

if __name__=='__main__':main()
