"""Package the frozen P4-B grid and retained pre-execution launcher failure."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--native',type=Path,required=True);ap.add_argument('--qualification',type=Path,required=True);ap.add_argument('--phases',type=Path,required=True);ap.add_argument('--failed-log',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 launches=[json.loads((r/'launcher-manifest.json').read_text()) for r in (a.root,a.native)]
 if any(run['exit_code'] for launch in launches for run in launch['runs']):raise ValueError('Incomplete frozen execution')
 metadata=a.output/'launch-metadata';metadata.mkdir()
 for label,root in (('main',a.root),('native',a.native)):
  shutil.copy(root/'launcher-manifest.json',metadata/(label+'-launcher.json'))
  for suffix in ('.log','.exit'):
   path=root.parent/(root.name+'-launch'+suffix)
   if path.exists():shutil.copy(path,metadata/(label+'-launch'+suffix))
 groups={'p4-b-b8':[a.root/r['directory'] for r in launches[0]['runs'] if r['directory'].startswith('b8-')],
 'p4-b-b32-tp4':[a.root/r['directory'] for r in launches[0]['runs'] if r['directory'].startswith('b32-tp4-')],
 'p4-b-b32-tp16-fixed':[a.root/r['directory'] for r in launches[0]['runs'] if r['directory'].startswith('b32-tp16-') and r['directory'].endswith('fine_fixed')],
 'p4-b-b32-tp16-prefetch':[a.root/r['directory'] for r in launches[0]['runs'] if r['directory'].startswith('b32-tp16-') and r['directory'].endswith('fine_prefetch')],
 'p4-b-native-and-controls':[a.root/r['directory'] for r in launches[0]['runs'] if r['directory'].startswith('b32-tp16-') and r['directory'].endswith('macro')]+[a.native/r['directory'] for r in launches[1]['runs']]+[a.qualification,a.phases,metadata]}
 packager=Path(__file__).with_name('package_expert_raw.py');records=[]
 for name,sources in groups.items():
  directory=a.output/name;cmd=[sys.executable,str(packager),'--sources',*[str(p) for p in sources],'--output',str(directory),'--name',name]
  result=subprocess.run(cmd,capture_output=True,text=True,check=True);record=json.loads(result.stdout);record.update(directory=directory.name,source_directories=[p.name for p in sources]);records.append(record);print(json.dumps(record),flush=True)
 retired=a.output/'launcher-import-failure';retired.mkdir();shutil.copy(a.failed_log,retired/'failed-launch.log');(retired/'failure.json').write_text(json.dumps(dict(status='RETIRED_LAUNCHER_FAILURE_BEFORE_EXPERIMENT',exit_code=1,source='3e1557a',fix='c95c2d7',reason='Frozen source package absent from script import path',performance_points=0),indent=2)+'\n')
 name='p4-b-retired-launch';directory=a.output/name
 result=subprocess.run([sys.executable,str(packager),'--sources',str(retired),'--output',str(directory),'--name',name,'--retired'],capture_output=True,text=True,check=True);record=json.loads(result.stdout);record.update(directory=directory.name,source_directories=[retired.name]);records.append(record);print(json.dumps(record),flush=True)
 (a.output/'bundle-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':main()
