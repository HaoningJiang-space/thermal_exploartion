"""Component qualification: same tensor work, visible per-case failures."""
import argparse,gzip,hashlib,json,sys,subprocess
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 source=a.source.resolve();sys.path.insert(0,str(source))
 from thermal_exploration.tensor_execution import build,CASES
 from thermal_exploration.native_tensor_graph import compare_native
 if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Clean component builder source required')
 a.output.mkdir(parents=True,exist_ok=False);manifest=json.loads((a.root/'launcher-manifest.json').read_text());records=[]
 for run in manifest['runs']:
  directory=a.root/run['directory']
  if run['exit_code'] or (a.root/(run['directory']+'.exit')).read_text().strip()!='0':raise ValueError('Native run incomplete')
  for result in json.loads((directory/'summary.json').read_text()):
   c=result['contract'];settings=dict(CASES[result['name']],compute_tflops=c['compute_tflops'],sram_mib=c['sram_mib'],fluid_memory=c['fluid_memory'],fluid_service_tb_s=c['fluid_service_tb_s'])
   model=build(settings,c['m'],c['n'],c['batch']);rec=compare_native(model,result)
   path=a.output/(run['directory']+'-'+result['name']+'-graph.json.gz')
   with gzip.open(path,'wt') as f:json.dump({k:rec.pop(k) for k in ('events','nodes','meta')},f,separators=(',',':'))
   rec.update(run=run['directory'],case=result['name'],shape=[c['m'],c['n'],c['batch']],backend='fluid' if c['fluid_memory'] else 'native',event_file=path.name,event_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
   records.append(rec);print(rec['run'],rec['case'],rec['relative_error'],rec['absolute_target_met'],flush=True)
 index={(r['shape'][1],r['shape'][2],r['case'],r['backend']):r for r in records};pairs=[]
 for k in (1024,2048):
  for b in (1,22):
   native=[index[k,b,c,'native'] for c in ('row_fifo_k','column_fifo64')];fluid=[index[k,b,c,'fluid'] for c in ('row_fifo_k','column_fifo64')]
   ratio_native=native[0]['detailed_us']/native[1]['detailed_us'];ratio_graph=native[0]['graph_us']/native[1]['graph_us']
   error=ratio_graph/ratio_native-1
   pairs.append(dict(k=k,batch=b,native_row_over_column=ratio_native,graph_row_over_column=ratio_graph,relative_prediction_error=error,relative_target_met=abs(error)<=.05,rank_agrees=(ratio_native<1)==(ratio_graph<1),native_fluid_max_error=max(abs(f['detailed_us']/n['detailed_us']-1) for n,f in zip(native,fluid))))
 (a.output/'qualification.json').write_text(json.dumps(dict(source_commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),records=records,pairs=pairs,absolute_target=.1,relative_target=.05,absolute_pass=sum(r['absolute_target_met'] for r in records),relative_pass=sum(r['relative_target_met'] for r in pairs),scope='Same detailed tensor task/work; packet/flit and eager/spread service differences; fullMoE TP4/16 independent fidelity not established'),indent=2)+'\n')

if __name__=='__main__':main()
