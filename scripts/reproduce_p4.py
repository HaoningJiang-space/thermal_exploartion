"""Run the predeclared P4-A matrix in a clean pinned checkout, fresh outputs."""
import argparse,json,os,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--pin',required=True);ap.add_argument('--routes',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=2);ap.add_argument('--list-only',action='store_true');a=ap.parse_args()
 source=a.source.resolve();routes=a.routes.resolve();output=a.output.resolve()
 revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 if not revision.startswith(a.pin) or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Clean pinned source required')
 if a.workers<1:raise ValueError('Positive worker count required')
 jobs=[]
 for batch in (8,32):
  for tp in (4,16):
   for down in ('column','row'):
    base=[sys.executable,'-m','thermal_exploration.run_p4_communication','--routes',str(routes),'--batch',str(batch),'--tp',str(tp),'--down-partition',down]
    for dispatch in ('broadcast_all','destination_only','decoupled'):
     for reduction in ('drain_all','row_ready'):
      label=f'b{batch}-tp{tp}-{down}-{dispatch}-{reduction}'
      jobs.append((label,base+['--dispatch',dispatch,'--reduction',reduction]))
    jobs.append((f'numerical-b{batch}-tp{tp}-{down}',base+['--dispatch','destination_only','--reduction','row_ready','--numerical-only']))
 if a.list_only:
  print(json.dumps(dict(source=revision,jobs=len(jobs),performance_points=288,numerical_comparisons=48,commands=[cmd+['--output',str(output/label)] for label,cmd in jobs]),indent=2));return
 output.mkdir(parents=True,exist_ok=False)
 env=dict(os.environ,PYTHONPATH=str(source),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
 def run(job):
  label,cmd=job;path=output/label
  with (output/(label+'.log')).open('w') as log:status=subprocess.run(cmd+['--output',str(path)],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  (output/(label+'.exit')).write_text(str(status)+'\n')
  print(label,status,flush=True)
  return dict(directory=label,exit_code=status)
 with ThreadPoolExecutor(max_workers=a.workers) as pool:records=list(pool.map(run,jobs))
 (output/'launcher-manifest.json').write_text(json.dumps(dict(source=revision,runs=records),indent=2)+'\n')
 if any(rec['exit_code'] for rec in records):raise SystemExit('Preserve incomplete/failed runs for audit')

if __name__=='__main__':main()
