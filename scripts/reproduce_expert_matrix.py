"""Reproduce frozen real-route matrices in clean source worktrees and fresh outputs."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
PINS={'p0':'83b1655','rows':'b468306','eager':'3dad8cd','fused':'15ad39e','prompt_eager':'5380b5d','prompt_fused':'15ad39e','probes':'4648f3c','strong_probes':'7890865'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--matrix',choices=PINS,required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--routes',type=Path,required=True);ap.add_argument('--precision-root',type=Path);ap.add_argument('--ramulator-root',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=1);ap.add_argument('--list-only',action='store_true');a=ap.parse_args()
 source=a.source.resolve();output=a.output.resolve();routes=a.routes.resolve();pin=PINS[a.matrix]
 rev=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 if not rev.startswith(pin) or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Use a clean frozen '+pin+' source worktree')
 if not routes.is_file():raise ValueError('Captured route file required')
 if a.workers<1:raise ValueError('Positive worker count required')
 jobs=[]
 def add(label,args,module='thermal_exploration.run_expert_gate'):
  jobs.append((output/(label+'-'+pin),[sys.executable,'-m',module,*args]))
 if a.matrix=='p0':
  if not a.ramulator_root:raise ValueError('Pinned Ramulator root required')
  shapes={'down2':([2048,1408,2],['column_fifo64','row_fifo_k']),'down8':([2048,1408,8],['column_fifo64','row_fifo_k']),'down16':([2048,1408,16],['column_fifo64','row_fifo_k']),'qkv4':([6144,4096,4],['row_fifo_k','row_fifo_m']),'qkv16':([6144,4096,16],['row_fifo_k'])}
  for name,(shape,cases) in shapes.items():
   for peak,sram in ((128,36),(152,18)):
    for backend in ('native','fluid'):
     args=['--ramulator-root',str(a.ramulator_root.resolve()),'--shape',*map(str,shape),'--cases',*cases,'--compute-tflops',str(peak),'--sram-mib',str(sram)]+(['--fluid-memory'] if backend=='fluid' else [])
     add(f'expert-p0-{name}-{peak}-{backend}',args,'thermal_exploration.run_h2')
 elif a.matrix=='rows':
  for base in ('B2_stream_fusion','B3_3d_placement'):add('expert-p1-'+base,['--routes',str(routes),'--mode','rows','--steps','128','--baseline',base])
 elif a.matrix.startswith('prompt'):
  if not a.precision_root:raise ValueError('Published paired captures required')
  fused=a.matrix=='prompt_fused'
  for family in ('topic_short','code_math'):
   for dtype in ('FP32','BF16'):
    route=a.precision_root.resolve()/(family+'-'+dtype+'.json')
    if not route.exists():route=Path(str(route)+'.gz')
    if not route.is_file():raise ValueError('Missing paired capture')
    for tp in ('1','4','16','hybrid'):
     for partition in ('column','row') if fused else ('column',):
      args=['--routes',str(route),'--prior-routes',str(routes),'--mode','experts','--tp',tp,'--batch','4']+(['--combine-scheme','fused','--down-partition',partition] if fused else [])
      add(f'expert-prompt{"fused" if fused else ""}-{family}-{dtype}-{partition}-tp{tp}',args)
 else:
  for batch in (8,32):
   for tp in ('1','4','16','hybrid'):
    base=['--routes',str(routes),'--batch',str(batch),'--tp',tp]
    if a.matrix in ('probes','strong_probes'):
     for partition in ('column','row'):
      names=['none','native_only','hb_ingress_only'] if a.matrix=='probes' else ['none','bank_cycle','uniform_fast_tier','native_only','hb_only','ingress_only','hb_ingress_only','mac_only','infinite_noc','ideal_memory']
      extra=[] if a.matrix=='probes' else ['--probe-schedule','barrier','--probe-order','static']
      add(f'expert-p3{"native" if a.matrix=="probes" else "strong"}-b{batch}-tp{tp}-{partition}',base+['--mode','isolation','--down-partition',partition,'--isolation-names',*names,*extra])
     continue
    fused=a.matrix=='fused';common=base+(['--combine-scheme','fused'] if fused else [])
    for placement in ('B2_stream_fusion','B3_3d_placement'):add(f'expert-p2{"fused" if fused else ""}-b{batch}-tp{tp}-{placement}',common+['--mode','experts','--baseline',placement])
    if fused:add(f'expert-p2row-b{batch}-tp{tp}',common+['--mode','experts','--down-partition','row','--sample-steps','0','127','--sample-layers','0','15','23'])
    for partition in ('column','row') if fused else ('column',):add(f'expert-p3{"fused" if fused else ""}-{partition}-b{batch}-tp{tp}',common+['--mode','isolation']+(['--down-partition',partition] if fused else []))
 if a.list_only:
  print(json.dumps(dict(source=rev,matrix=a.matrix,jobs=len(jobs),commands=[cmd+['--output',str(path)] for path,cmd in jobs]),indent=2));return
 if output.exists():raise ValueError('Output root must be fresh')
 output.mkdir(parents=True);env=dict(os.environ,PYTHONPATH=str(source))
 def run(job):
  path,cmd=job;cmd=cmd+['--output',str(path)]
  with Path(str(path)+'.log').open('w') as log:status=subprocess.run(cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  Path(str(path)+'.exit').write_text(str(status)+'\n')
  return dict(directory=path.name,exit_code=status)
 with ThreadPoolExecutor(max_workers=a.workers) as pool:results=list(pool.map(run,jobs))
 (output/'launcher-manifest.json').write_text(json.dumps(dict(source=rev,matrix=a.matrix,runs=results),indent=2)+'\n')
 if any(r['exit_code'] for r in results):raise SystemExit('Execution failed; preserve logs and incomplete records')
 print(json.dumps(dict(matrix=a.matrix,completed_runs=len(results),source=rev)))
if __name__=='__main__':main()
