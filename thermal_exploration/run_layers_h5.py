"""Conditional spatial/periodic audit of complete-layer event workloads."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from .organization import load_exploration
from .run_h5 import COEFFICIENTS,SCENARIOS,evaluate
from .run import revision


def event_energy(directory,r,bins=128,logic_memory_share=.48):
    if not 0<=logic_memory_share<=1:raise ValueError('Invalid physical heat partition')
    file=directory/r['directory']/r['events_file']
    if hashlib.sha256(file.read_bytes()).hexdigest()!=r['events_sha256']:raise ValueError('Corrupt event trace')
    ticks=round(r['time_us']/.00025);energy=np.zeros((bins,32));ledger={};stream=r['baseline'] in ('B2_stream_fusion','B3_3d_placement')
    def deposit(a,b,tile,joules):
        if not joules:return
        lo=min(bins-1,int(a*bins/ticks));hi=min(bins-1,int(max(a,b-1)*bins/ticks))
        if a==b:energy[lo,tile]+=joules;return
        for bin_ in range(lo,hi+1):
            overlap=max(0,min(b,(bin_+1)*ticks/bins)-max(a,bin_*ticks/bins))
            energy[bin_,tile]+=joules*overlap/(b-a)
    totals={}
    with gzip.open(file,'rt') as f:
        for line in f:
            event=json.loads(line);a,b=event['start_tick'],event['finish_tick']
            for tile,kinds in event['activity'].items():
                tile=int(tile);window=event.get('tile_kernel_windows',{}).get(str(tile),{})
                for kind,work in kinds.items():
                    totals[kind]=totals.get(kind,0)+work
                    finish=min(b,a+window.get('ticks',b-a))
                    if kind in ('dram','dram_write'):
                        # Aggregate full-row energy scale, NOT a calibrated
                        # ACT/PRE/RD/WR model. Interface/peripheral already in it.
                        joules=work*3.432e-12
                        deposit(a,finish,tile,joules*logic_memory_share);deposit(a,finish,tile+16,joules*(1-logic_memory_share))
                        ledger['memory_access_j']=ledger.get('memory_access_j',0)+joules
                        if stream:
                            extra=work*COEFFICIENTS['fifo_and_steering_pj_byte']*1e-12
                            deposit(a,finish,tile,extra);ledger['fifo_steering_j']=ledger.get('fifo_steering_j',0)+extra
                        continue
                    coeff=dict(mac=COEFFICIENTS['mac_pj_flop'],vector=COEFFICIENTS['vector_pj_op'],link=COEFFICIENTS['noc_pj_byte_hop'],sram_read=COEFFICIENTS['sram_pj_byte'],sram_write=COEFFICIENTS['sram_pj_byte']).get(kind,0)
                    # HB is included in the memory aggregate, no second charge.
                    joules=work*coeff*1e-12;deposit(a,finish,tile,joules)
                    ledger[kind+'_j']=ledger.get(kind+'_j',0)+joules
    if totals!=r['activity']:raise ValueError('Event activity does not close to full128-step workload')
    if not np.isclose(energy.sum(),sum(ledger.values()),rtol=1e-9,atol=1e-12):raise ValueError('Event energy closure failed')
    return energy,ledger


def audit_record(directory,r,bins=128,grid=4,scale=1.,cooling=.3,backend='scipy',share=.48):
    energy,ledger=event_energy(directory,r,bins,share)
    # Reuse the established RC implementation and area/background contract.
    # No timing-only oracle is evaluated as a paid implementation.
    mapped=dict(workload=r['scenario'],variant='known_fifo_baseline' if r['baseline'] in ('B2_stream_fusion','B3_3d_placement') else 'sram_baseline',
                ticks=round(r['time_us']/.00025),time_us=r['time_us'],meta=dict(tokens=r['tokens']))
    result=evaluate(mapped,energy,ledger,load_exploration(),cooling,scale,backend,bins,grid,pacing_mode='idle_bins')
    result['cold_128_step_burst_sampled_peak_c']=result.pop('cold_token_sampled_peak_c')
    result.update(baseline=r['baseline'],routing=r['routing'],tensor_parts=r['tensor_parts'],logic_memory_share=share,
        scope='Full structural128-step Decode event workload, conditional periodicRC feasibility; not device-calibrated inference throughput',
        t0_tokens_s=r['tokens_s'],event_power_resolution='Per-tile activity distributed over measured fast-kernel/packet stage windows; not per-command switching power',
        context_extension_assumed=r['admission']['context_extension_assumed'])
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--layers',required=True);ap.add_argument('--output',required=True);ap.add_argument('--thermal-backend',choices=('hits','scipy'),default='scipy');a=ap.parse_args()
    directory=Path(a.layers);out=Path(a.output)
    if out.exists():raise ValueError('Never overwrite thermal evidence')
    out.mkdir(parents=True);summaries=json.loads((directory/'summary.json').read_text());records=[]
    (out/'contract.json').write_text(json.dumps(dict(source_commit=revision(),backend=a.thermal_backend,
        area_mm2=121,dram_bytes=32*2**30,sram_bytes=36*2**20,temperature_limit_c=85,
        coefficients=COEFFICIENTS,scenarios=SCENARIOS,
        assumptions=['Memory3.432pJ/B aggregate includesHB; no independent command energy calibration',
        'Equivalent30um DRAM thermal layer; tier thermal depths unresolved','Memory logic heat fraction.48; bounded.3/.7 controls',
        'Active rates fixed; idle bins inserted for duty-cycle pacing; checkpoint/geometry assumptions remain uncalibrated',
        'Unknown refresh/leakage temperature feedback disabled','128/256 energy-bin and4/8 spatial convergence checks are numerical, not device validation']),indent=2)+'\n')
    selected=[]
    for r in summaries:
        if r.get('status')!='PASS_ACCOUNTING' or r['oracle']!='none' :continue
        if r['model']=='qwen15_moe' and r['routing']!='public_projected':continue
        if r['baseline'] not in ('B0_local','B1_dataflow','B2_stream_fusion','B3_3d_placement'):continue
        selected.append(r)
        for name,(scale,cooling) in SCENARIOS.items():
            record=audit_record(directory,r,scale=scale,cooling=cooling,backend=a.thermal_backend);record['scenario']=name;records.append(record)
            print(r['scenario'],r['baseline'],name,record['sustainable_tokens_s'],record['periodic_logic_peak_c'],flush=True)
        (out/'partial.json').write_text(json.dumps(records,indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
    # Preselected capacity/high-state corner, not cherry-picked best gain.
    candidates=[r for r in selected if r['scenario']=='qwen_b8_c2k' and r['baseline']=='B3_3d_placement']
    convergence=[]
    for r in candidates:
        for bins,grid in [(128,4),(256,4),(128,8)]:
            x=audit_record(directory,r,bins=bins,grid=grid,backend=a.thermal_backend);convergence.append(x)
        for share in (.3,.7):
            x=audit_record(directory,r,share=share,backend=a.thermal_backend);x['sensitivity']='memory_heat_assignment';convergence.append(x)
    (out/'convergence.json').write_text(json.dumps(convergence,indent=2)+'\n')


if __name__=='__main__':main()
