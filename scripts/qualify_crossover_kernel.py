"""Visible cross-fidelity disagreements; no latency fit or pass by averaging."""
import argparse,json
from pathlib import Path
from math import ceil
from thermal_exploration.crossover_execution import pipeline,Profile
from thermal_exploration.layer_execution import collective

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--runs',nargs='+',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();records=[]
 for directory in map(Path,a.runs):
  for r in json.loads((directory/'summary.json').read_text()):
   c=r['contract']
   if c['row_parts']!=16 or not c.get('stream_fifo') or c.get('command_domains_per_tile',1)!=1:continue
   b=c['batch'];m=c['m'];n=c['n'];network=collective(b,n,'broadcast');lead=network['ticks'];local=c['dram_bytes']//16
   kernel=pipeline(((0,local),),b,Profile(),lead=lead,useful_bytes=c['weight_bytes']//16)
   output=(m//16)*b;tail=ceil(output*4/128)+ceil(output*4/256)+ceil(output/16)+ceil(output*2/128)
   predicted=(lead+kernel['ticks']+tail)*.00025
   records.append(dict(experiment=directory.name,case=r['name'],shape=[m,n,b],native_us=r['time_us'],fast_us=predicted,relative_error=predicted/r['time_us']-1,target_met=abs(predicted/r['time_us']-1)<=.1,
    work_checks=dict(mac_flops=kernel['mac_flops']*16==c['mac_flops'],dram_bytes=kernel['dram_bytes']*16==c['dram_bytes'],input_byte_hops=network['activity']['link']==r['byte_hops'].get('X',0)),
    terms_us=dict(input_distribution=lead*.00025,finite_weight_mac_kernel=kernel['ticks']*.00025,result_cast_tail=tail*.00025),
    differences=['Fast model retains full input-distribution barrier; native consumes128/88-element groups as they arrive','Fast32KiB tiles/register-reused partials versus native32x128/88 MAC tasks with intermediate partial SRAM access','Physical bank/address order abstracted into measured service guard; same area/ports/capacity but not identical execution schedule'],
    verdict='Case-level characterization; no general absolute-latency qualification or empirical fit'))
 Path(a.output).write_text(json.dumps(records,indent=2)+'\n');print('Qualified checks',len(records),'target passes',sum(r['target_met'] for r in records))
if __name__=='__main__':main()
