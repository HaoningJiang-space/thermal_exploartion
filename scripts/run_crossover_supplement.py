"""Preselected network/memory capacity probes, matched to completed baselines."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from thermal_exploration.run_crossover import run_one
from thermal_exploration.crossover_execution import Profile
from thermal_exploration.layer_execution import resident_layout
from thermal_exploration.model_contract import load_model
from thermal_exploration.run import revision

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--baselines',nargs='+',required=True);ap.add_argument('--routes',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False);routes_path=Path(a.routes);routes=json.loads(routes_path.read_text());routes['_file_sha256']=hashlib.sha256(routes_path.read_bytes()).hexdigest();records=[]
 for directory in map(Path,a.baselines):
  data=json.loads((directory/'summary.json').read_text())
  selected=[r for r in data if r.get('status')=='PASS_ACCOUNTING' and r['profile']['compute_tflops']==128 and r['profile']['isolation']=='none' and r['profile']['hb_tb_s']==32 and r['profile']['fifo_ingress_bytes_tick']==500]
  for scenario in sorted({r['scenario'] for r in selected}):
   if scenario not in ('llama_b1_c2k','llama_b4_c8k','qwen_b8_c2k'):continue
   ref=min((r for r in selected if r['scenario']==scenario),key=lambda r:r['time_us']);c=load_model(ref['model']);prior=routes['training_expected_activations'] if c['model_type']!='llama' else None
   layout=dict(resident_layout(c,ref['admission'],ref['baseline'],prior),baseline=ref['baseline'])
   for isolation in ('infinite_noc','ideal_memory'):
    result=run_one(c,ref['admission'],layout,Profile(isolation=isolation),ref['schedule'],routes,ref['routing'],out,scenario)
    result.update(reference_events_sha256=ref['events_sha256'],reference_time_us=ref['time_us'],reference_source_commit=ref['source_commit']);records.append(result)
    (out/'partial.json').write_text(json.dumps(records,indent=2)+'\n')
 (out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
 (out/'contract.json').write_text(json.dumps(dict(source_commit=revision(),source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),scope='Matched strongest tested schedule/layout; remove ONLY specified resource capacity. Ideal Memory and NoC are oracles, no paid architecture.'),indent=2)+'\n')
if __name__=='__main__':main()
