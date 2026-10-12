"""Frozen real-route P4-B and independently audited native components."""
import argparse,json,subprocess,sys,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--pin',required=True);ap.add_argument('--routes',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=2);ap.add_argument('--native-components',action='store_true');ap.add_argument('--ramulator-root',type=Path);a=ap.parse_args()
 source=a.source.resolve();routes=a.routes.resolve();output=a.output.resolve();pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 if not pin.startswith(a.pin) or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Clean frozen source required')
 env=dict(os.environ,PYTHONPATH=str(source),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1');jobs=[]
 if a.native_components:
  if not a.ramulator_root:raise ValueError('Pinned Ramulator required')
  sys.path.insert(0,str(source))
  from thermal_exploration.run_p4_fine import selection
  r=json.loads(routes.read_text());sel=selection(r)
  for role in ('cold','reused'):
   for k in (1024,2048):
    for backend in ('native','fluid'):
     label=f'{role}-k{k}-{backend}'
     cmd=[sys.executable,'-m','thermal_exploration.run_h2','--ramulator-root',str(a.ramulator_root.resolve()),'--shape','512',str(k),str(sel[role]['count']),'--cases','row_fifo_k','column_fifo64']+(['--fluid-memory'] if backend=='fluid' else [])
     jobs.append((label,cmd))
 else:
  for b in (8,32):
   for tp in (4,16):
    for down in ('row','column'):
     for grain in ('macro','fine_fixed','fine_prefetch'):
      label=f'b{b}-tp{tp}-{down}-{grain}';jobs.append((label,[sys.executable,'-m','thermal_exploration.run_p4_fine','--routes',str(routes),'--batch',str(b),'--tp',str(tp),'--down',down,'--grain',grain]))
 output.mkdir(parents=True,exist_ok=False)
 def run(job):
  label,cmd=job;path=output/label
  with (output/(label+'.log')).open('w') as log:status=subprocess.run(cmd+['--output',str(path)],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  (output/(label+'.exit')).write_text(str(status)+'\n');print(label,status,flush=True)
  return dict(directory=label,exit_code=status)
 with ThreadPoolExecutor(max_workers=a.workers) as pool:records=list(pool.map(run,jobs))
 (output/'launcher-manifest.json').write_text(json.dumps(dict(source=pin,native_components=a.native_components,routing_sha256=__import__('hashlib').sha256(routes.read_bytes()).hexdigest(),runs=records),indent=2)+'\n')
 if any(r['exit_code'] for r in records):raise SystemExit('Preserve failures')

if __name__=='__main__':main()
