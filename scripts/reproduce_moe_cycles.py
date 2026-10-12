"""Frozen G3-A/B then full-MoE G3-C/G4, real capture only."""
import argparse,hashlib,json,os,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--pin',required=True);ap.add_argument('--routes',type=Path,required=True);ap.add_argument('--ramulator-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--stage',choices=('experts','training','holdout'),required=True);ap.add_argument('--workers',type=int,default=4);a=ap.parse_args()
 source=a.source.resolve();out=a.output.resolve();root=a.ramulator_root.resolve();routes=a.routes.resolve();pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 if not pin.startswith(a.pin) or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Clean frozen source required')
 digest=hashlib.sha256(routes.read_bytes()).hexdigest()
 if digest!='24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6':raise ValueError('Original capture required')
 out.mkdir(parents=True,exist_ok=False);exe=out/'moe-driver';cmd=['g++','-std=c++20','-O2','-I'+str(root/'src'),'-I'+str(root/'ext/fmt/include'),'-I'+str(root/'ext/yaml-cpp/include'),str(source/'native/moe_execution_driver.cpp'),'-L'+str(root),'-lramulator','-Wl,-rpath,'+str(root),'-o',str(exe)]
 bridge=out/'memory-bridge'
 with (out/'build.log').open('w') as log:
  subprocess.run(cmd,stdout=log,stderr=log,check=True)
  bridge_cmd=list(cmd);bridge_cmd[bridge_cmd.index(str(source/'native/moe_execution_driver.cpp'))]=str(source/'native/moe_memory_bridge.cpp');bridge_cmd[-1]=str(bridge);subprocess.run(bridge_cmd,stdout=log,stderr=log,check=True)
 (out/'compiler-version.log').write_text(subprocess.check_output(['g++','--version'],text=True))
 env=dict(os.environ,PYTHONPATH=str(source),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1');jobs=[]
 if a.stage=='experts':cases=[(0,0,32,4,'column',scope) for scope in ('cold','reused','contending')]
 else:
  cohorts=[(0,0)] if a.stage=='training' else [(32,7),(127,23)]
  cases=[(step,layer,b,tp,down,'moe') for step,layer in cohorts for b in (8,32) for tp in (4,16) for down in ('row','column')]
 for step,layer,b,tp,down,scope in cases:
  label=f's{step}-l{layer}-b{b}-tp{tp}-{down}-{scope}'
  args=[sys.executable,'-m','thermal_exploration.run_moe_cycles','--routes',str(routes),'--batch',str(b),'--tp',str(tp),'--down',down,'--step',str(step),'--layer',str(layer),'--scope',scope,'--ramulator-root',str(root),'--exe',str(exe),'--bridge',str(bridge)]
  jobs.append((label,args))
 (out/'frozen-plan.json').write_text(json.dumps(dict(source=pin,stage=a.stage,cases=cases,routing_sha256=digest,targets=dict(absolute=.1,relative=.05),independent_blind_prompts=False),indent=2)+'\n')
 def run(job):
  label,cmd=job
  with (out/(label+'.log')).open('w') as log:status=subprocess.run(cmd+['--output',str(out/label)],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  (out/(label+'.exit')).write_text(str(status)+'\n');print(label,status,flush=True);return dict(directory=label,exit_code=status)
 with ThreadPoolExecutor(max_workers=a.workers) as pool:records=list(pool.map(run,jobs))
 (out/'launcher-manifest.json').write_text(json.dumps(dict(source=pin,routing_sha256=digest,stage=a.stage,runs=records),indent=2)+'\n')
 if any(r['exit_code'] for r in records):raise SystemExit('Qualification failed; preserve evidence')
if __name__=='__main__':main()
