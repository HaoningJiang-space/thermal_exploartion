"""Frozen full-shape routed-projection validation; never smoke performance."""
import argparse,json,os,subprocess,sys,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--pin',required=True);ap.add_argument('--routes',type=Path,required=True);ap.add_argument('--ramulator-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args()
 source=a.source.resolve();routes=a.routes.resolve();output=a.output.resolve();pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 if not pin.startswith(a.pin) or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Clean frozen source required')
 digest=hashlib.sha256(routes.read_bytes()).hexdigest()
 if digest!='24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6':raise ValueError('Original capture required')
 sys.path.insert(0,str(source));from thermal_exploration.run_p4_fine import selection
 selected=selection(json.loads(routes.read_text()));jobs=[];env=dict(os.environ,PYTHONPATH=str(source),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 for role in ('cold','reused'):
  for backend in ('native','fluid'):
   label=f'gate-full-{role}-{backend}';cmd=[sys.executable,'-m','thermal_exploration.run_h2','--ramulator-root',str(a.ramulator_root.resolve()),'--shape','1408','2048',str(selected[role]['count']),'--cases','row_fifo32','column_fifo32']+(['--fluid-memory'] if backend=='fluid' else [])
   jobs.append((label,cmd))
 output.mkdir(parents=True,exist_ok=False)
 def run(job):
  label,cmd=job
  with (output/(label+'.log')).open('w') as log:status=subprocess.run(cmd+['--output',str(output/label)],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  (output/(label+'.exit')).write_text(str(status)+'\n');print(label,status,flush=True);return dict(directory=label,exit_code=status)
 with ThreadPoolExecutor(max_workers=a.workers) as pool:records=list(pool.map(run,jobs))
 (output/'launcher-manifest.json').write_text(json.dumps(dict(source=pin,routing_sha256=digest,selected_experts=selected,runs=records,scope='Real routed Gate/Up full projection dimensions and captured counts;16-way tensor contract; not fullMoE or TP4/TP16 fidelity'),indent=2)+'\n')
 if any(r['exit_code'] for r in records):raise SystemExit('Preserve all failures')
if __name__=='__main__':main()
