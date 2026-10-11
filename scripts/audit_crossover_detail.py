"""Detailed supply evidence; windows/counters are not additive stall fractions."""
import argparse,csv,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
from thermal_exploration.crossover_execution import Profile,pipeline
from thermal_exploration.run import revision

def read(path):
 with path.open() as f:return list(csv.DictReader(f))
def audit(case,service):
 r=json.loads((case/'result.json').read_text());c=r['contract'];d=r['driver'];requests=read(case/'run-reads.csv');counts=Counter();row_counts=Counter()
 for channel in range(16*c.get('command_domains_per_tile',1)):
  for row in read(case/f'transaction-commands.ch{channel}.csv'):
   cmd=row.get('command',row.get('cmd'));counts[cmd]+=1
 latency=np.array([int(x['depart'])-int(x['accepted']) for x in requests])*.25
 ingress=np.array([int(x['hb_done'])-int(x['depart']) for x in requests])*.25
 # Same fast-tier/bytes/batch/port hardware, chosen packet hierarchy. It still
 # lacks command dependencies, flit arbitration and numerical output checks.
 proxy=pipeline(((0,c['dram_bytes']//16),),c['batch'],Profile(service_tb_s=service,fifo_ingress_bytes_tick=500 if c.get('stream_fifo') else 128))
 return dict(contract=c,time_us=r['time_us'],effective_tflops=r['effective_tflops'],useful_dram_tb_s=r['useful_dram_tb_s'],command_validation=r['command_validation'],command_counts=dict(counts),
    actual_ACT_per_useful_byte=counts.get('ACT',0)/c['weight_bytes'],
    average_useful_bytes_per_ACT=c['weight_bytes']/max(1,counts.get('ACT',0)),
    request_dram_latency_ns={'p50':float(np.median(latency)),'p95':float(np.quantile(latency,.95))},
    returned_to_fifo_or_sram_ns={'p50':float(np.median(ingress)),'p95':float(np.quantile(ingress,.95))},
    exclusive_mac_tile_tick_states=d['mac_states'],state_denominator=sum(d['mac_states'].values()),
    overlapping_backpressure_counters=d['backpressure'],byte_hops=r['byte_hops'],sram_activity=r['sram_activity'],stages_ns=r['stages_ns'],
    fast_kernel_only_time_us=proxy['ticks']*.00025,fast_kernel_scope='Fast-tier weight kernel only; excludes input distribution/final cast/collective. Cached case128B/tick is an ingress-cap sensitivity with streaming operands, NOT equal cached hardware.',
    detailed_fifo_vs_fast_kernel_gap=(r['time_us']/(proxy['ticks']*.00025)-1) if c.get('stream_fifo') and c['row_parts']==16 else None,
    hb_utilization=c['dram_bytes']/(r['time_us']*32e6),
    source_commit=revision(),service_tb_s=service,scope='Actual emitted commands and bounded native supply/port timing under assumed fast-tier surrogate. Timing windows overlap; ACT counts measured here, not inferred for full-model hierarchy.')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--runs',nargs='+',required=True);ap.add_argument('--output',required=True);ap.add_argument('--service',type=float,required=True);a=ap.parse_args();records=[]
 for run in map(Path,a.runs):
  for case in sorted(p for p in run.iterdir() if p.is_dir() and (p/'result.json').exists()):
   record=audit(case,a.service);record.update(experiment=run.name,case=case.name);records.append(record)
 Path(a.output).write_text(json.dumps(records,indent=2)+'\n');print('Detailed records',len(records))
if __name__=='__main__':main()
