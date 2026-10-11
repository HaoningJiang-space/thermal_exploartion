"""Absolute AND speedup fidelity; shared frontend is not independent validation."""
import argparse,json
from collections import defaultdict
from pathlib import Path
from math import ceil
from thermal_exploration.crossover_execution import pipeline,Profile
from thermal_exploration.layer_execution import collective

def qualify(records):
 groups=defaultdict(dict)
 for r in records:
  c=r['contract'];key=(c['m'],c['n'],c['batch'],r['name']);groups[key][c['compute_tflops'],c.get('fluid_memory',False)]=r
 absolute=[];relative=[];legacy=[]
 for key,points in sorted(groups.items()):
  for peak in (128,152):
   n=points[peak,False];f=points[peak,True];c=n['contract'];checks={k:n['contract'][k]==f['contract'][k] for k in ('mac_flops','weight_bytes','dram_bytes','m_block','k_block','sram_per_tile','mac_flops_per_tick')}
   checks.update(byte_hops=n['byte_hops']==f['byte_hops'],sram_activity=n['sram_activity']==f['sram_activity'])
   if not all(checks.values()):raise ValueError('Unmatched cross-fidelity contract')
   error=f['time_us']/n['time_us']-1
   absolute.append(dict(shape=list(key[:3]),case=key[3],peak=peak,native_us=n['time_us'],matched_fluid_us=f['time_us'],relative_error=error,target_met=abs(error)<=.1,work_and_port_checks=checks))
   if c['row_parts']==16:
    b=c['batch'];m=c['m'];width=c['n'];input_=collective(b,width,'broadcast');lead=input_['ticks']
    proxy=pipeline(((0,c['dram_bytes']//16),),b,Profile(peak,c['sram_mib']),lead=lead,useful_bytes=c['weight_bytes']//16)
    output=m//16*b;tail=ceil(output*4/128)+ceil(output*4/256)+ceil(output/16)+ceil(output*2/128)
    old=(lead+proxy['ticks']+tail)*.00025
    legacy.append(dict(shape=list(key[:3]),case=key[3],peak=peak,legacy_us=old,native_us=n['time_us'],relative_error=old/n['time_us']-1,scope='Old whole-input barrier/32KiB kernel, retained mismatch control'))
  ns=points[128,False]['time_us']/points[152,False]['time_us'];fs=points[128,True]['time_us']/points[152,True]['time_us']
  entry=dict(shape=list(key[:3]),case=key[3],native_speedup=ns,matched_fluid_speedup=fs,relative_speedup_error=fs/ns-1,target_met=abs(fs/ns-1)<=.05)
  ls=[x for x in legacy if x['shape']==list(key[:3]) and x['case']==key[3]]
  if len(ls)==2:
   old={x['peak']:x for x in ls};speed=old[128]['legacy_us']/old[152]['legacy_us'];entry.update(legacy_speedup=speed,legacy_relative_speedup_error=speed/ns-1,legacy_target_met=abs(speed/ns-1)<=.05)
  relative.append(entry)
 return dict(absolute=absolute,speedup=relative,legacy_mismatch_control=legacy,
   targets=dict(absolute=.1,relative_speedup=.05),
   scope='Selected fast-tier tensors only; common flit/compute frontend isolates DRAM abstraction. Not independent frontend validation; not a certification of complete H3 or original12.92%/7.06% gains.')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();r=qualify(json.loads(Path(a.input).read_text()));Path(a.output).write_text(json.dumps(r,indent=2)+'\n')
 print('absolute',sum(x['target_met'] for x in r['absolute']),len(r['absolute']),'speedups',sum(x['target_met'] for x in r['speedup']),len(r['speedup']))
if __name__=='__main__':main()
