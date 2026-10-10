"""Independent byte-arrival comparison and per-trace completion lower bound."""
import argparse,csv,hashlib,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    src=Path(a.input);s=json.loads((src/'summary.json').read_text());rows=[]
    for c in s['cases']:
        hashes=[hashlib.sha256() for _ in range(16)];count=0;last=0
        with (src/c['name']/'run-events.csv').open() as f:
            for e in csv.DictReader(f):
                # Within each tile, canonical problem-byte order is preserved
                # across task partition sizes. Request/task IDs can differ.
                hashes[int(e['tile'])].update((','.join(e[k] for k in ('phase','address','accepted','depart','delivered'))+'\n').encode())
                last=max(last,int(e['delivered']));count+=1
        d=c['driver']
        if count!=d['returned'] or last>d['ticks']:raise ValueError('Unconserved or noncausal stream')
        useful_ticks=d['useful_flops']/2000
        busy=d['tile_cycle_partition']['compute_busy']
        if useful_ticks>busy:raise ValueError('Useful MAC work exceeds occupied slots')
        lower=max(last,d['useful_flops']/32000)
        rows.append(dict(case=c['name'],requests=count,last_delivery_tick=last,finish_tick=d['ticks'],
            memory_schedule_sha256_per_tile=[h.hexdigest() for h in hashes],
            useful_MAC_utilization=d['useful_flops']/(d['ticks']*32000),
            consumer_occupied_fraction=busy/(d['ticks']*16),
            occupied_rounding_padding_fraction=(busy-useful_ticks)/(d['ticks']*16),
            fixed_arrival_completion_lower_bound_ticks=lower,
            fixed_arrival_consumer_speedup_upper_bound_pct=(d['ticks']/lower-1)*100))
        print(c['name'],'arrival bound',rows[-1]['fixed_arrival_consumer_speedup_upper_bound_pct'],flush=True)
    by={r['case']:r for r in rows};pairs=[]
    for x,y in [('mapped_prefetched','fine_streaming_probe'),('uniform_prefetched','uniform_fine_probe')]:
        pairs.append(dict(a=x,b=y,identical_memory_schedule=by[x]['memory_schedule_sha256_per_tile']==by[y]['memory_schedule_sha256_per_tile']))
    Path(a.output).write_text(json.dumps(dict(cases=rows,comparisons=pairs,
        scope='Strict consumer-only bound conditioned on this accepted/DRAM/HB arrival schedule; not a bound on architectures that change that schedule',
        occupancy='compute_busy records occupied consumer slots, including event quantization; useful MAC utilization is independently useful FLOP / fixed peak / runtime'),indent=2)+'\n')

if __name__=='__main__':main()
