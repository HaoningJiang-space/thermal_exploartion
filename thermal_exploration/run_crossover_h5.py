"""Default cooling audit of selected fixed-area crossover organizations only."""
import argparse,json
from pathlib import Path
from .crossover_execution import Profile,MAC_AREA,STORAGE_AREA
from .run_layers_h5 import event_energy
from .run_h5 import evaluate
from .organization import load_exploration
from .run import revision

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',nargs='+',required=True);ap.add_argument('--output',required=True);ap.add_argument('--backend',choices=('scipy','hits'),default='scipy');a=ap.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False);records=[]
 selected=[]
 for name in a.inputs:
  directory=Path(name)
  for r in json.loads((directory/'summary.json').read_text()):
   if r.get('status')!='PASS_ACCOUNTING' or r['profile']['isolation']!='none' or r['profile']['hb_tb_s']!=32 or r['profile']['fifo_ingress_bytes_tick']!=500:continue
   if r['scenario'] not in ('llama_b1_c2k','llama_b16_c2k','qwen_b8_c2k','qwen_b32_c512'):continue
   key=(r['scenario'],r['profile']['compute_tflops'],r['routing'])
   previous=next((x for x in selected if x[0]==key),None)
   if previous and previous[2]['time_us']<=r['time_us']:continue
   if previous:selected.remove(previous)
   selected.append((key,directory,r))
 for key,directory,r in selected:
  p=Profile(**r['profile']);physical=dict(p.area(),sram_bytes=int(p.sram_mib*2**20),variable_area_static_delta_w=.02*(p.area()['mac_area_mm2']+p.area()['storage_area_mm2']-MAC_AREA-STORAGE_AREA))
  energy,ledger=event_energy(directory,r,128)
  mapped=dict(workload=r['scenario'],variant='known_fifo_baseline',ticks=round(r['time_us']/.00025),time_us=r['time_us'],meta=dict(tokens=r['tokens']))
  result=evaluate(mapped,energy,ledger,load_exploration(),.3,backend=a.backend,bins=128,pacing_mode='idle_bins',physical_contract=physical)
  result.update(profile=r['profile'],schedule=r['schedule'],routing=r['routing'],physical_contract=physical,source_commit=revision(),execution_source_commit=r['source_commit'],events_sha256=r['events_sha256'],source_file=r['events_file'],
    scope='Conditional default-cooling event-window thermal evaluation; FIFO dual-port costs assumed; static variable-area density0.02W/mm2; unknown temperature feedback disabled')
  records.append(result);print(key,result['periodic_logic_peak_c'],result['sustainable_tokens_s'],flush=True)
  (out/'partial.json').write_text(json.dumps(records,indent=2)+'\n')
 (out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':main()
