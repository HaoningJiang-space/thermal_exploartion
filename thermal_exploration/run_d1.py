"""D1: known-mechanism read probes at fixed K32, capacity and compute."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
from . import hb_trace
from .known_mechanisms import MECHANISMS,trace,validate,mechanism_audit
from .organization import load_exploration,lp_config,thermal_config,organization_cost
from .run_organization import check_commands
from .run_g4 import RAMULATOR_COMMIT,native_build,read_csv,validate_events,verify_upstream
from .trace_generator import write_trace
from .thermal import response
from .model import optimize,Fabric
from .run import revision


def run_case(exe,root,out,name,partial=False):
    case=out/(name+('_partial_row' if partial else ''));case.mkdir()
    settings=MECHANISMS[name];req=trace(name,partial)
    validator=lambda r:validate(r,settings['subarrays'])
    write_trace(req,case,validator)
    dram,config=hb_trace.ramulator_config(root,case,2,**settings)
    (case/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    with (case/'execution.log').open('w') as log:
        subprocess.run([str(exe),str(case/'config.json'),str(case/'requests.tsv'),str(case/'run'),'8192','2000','500','0'],stdout=log,stderr=log,check=True)
    driver=json.loads((case/'run-driver.json').read_text());events=read_csv(case/'run-events.csv')
    work=validate_events(req,events,driver,validator)
    commands=[]
    for ch in range(16):commands.extend(read_csv(case/f'transaction-commands.ch{ch}.csv'))
    commands.sort(key=lambda c:int(c['clock']))
    replay=check_commands(dram,req,events,commands);audit=mechanism_audit(commands)
    period=15600;start=period*2;end=(driver['ticks']//period-1)*period
    if end-start<5*period:raise ValueError('Not enough refresh periods')
    delivered=sum(start<=int(e['completed'])<end for e in events)*1024
    rate=delivered/((end-start)*.25)/1000
    resolved=dram.resolve()[1]
    if settings['subarrays']>1 and (resolved['nRAS']!=60 or not audit['overlapping_ACTs']):
        raise ValueError('Subarray overlap either shortened restoration or never overlapped')
    counts=replay['counts'].copy();counts['PREab_rows']=audit['PREab_rows']
    r=dict(name=case.name,mechanism=name,partial_row=partial,settings=settings,
        work=work,driver=driver,commands=replay,audit=audit,
        steady=dict(start_tick=start,end_tick=end,duration_ns=(end-start)*.25,useful_tb_s=rate),
        activity=dict(counts=counts,useful_bytes=work['read_bytes'],duration_ns=driver['ticks']*.25,
                      selector_events=audit['selector_events'] if settings['subarrays']>1 else 0),
        timing_ns={k:resolved['n'+k]*.5 for k in ('RCDRD','RAS','RP','RC')},
        resources=dict(physical_banks=256,subarrays_per_bank=settings['subarrays'],native_local_states=256*settings['subarrays'],
                       capacity_bytes=256*settings['subarrays']*(32768//settings['subarrays'])*4096,compute_tflops=128,hb_tb_s=32,K=32),
        scope='Known-mechanism surrogate. Subarray selection is implicit with0.5ns first-access overhead; not literal SALP/MASA or qualified AL-DRAM')
    (case/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    print(case.name,rate,r['timing_ns'],flush=True)
    return r


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ramulator-root',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--thermal-backend',choices=['scipy','hits'],default='scipy');a=ap.parse_args()
    root=Path(a.ramulator_root).resolve();out=Path(a.output).resolve()
    if out.exists():raise SystemExit('Preserve prior records')
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=RAMULATOR_COMMIT:raise ValueError('Wrong pin')
    verified=verify_upstream(root);out.mkdir(parents=True);sys.path[:0]=[str(root/'python'),str(root)]
    p=load_exploration();(out/'profile.json').write_text(json.dumps(p,indent=2)+'\n')
    (out/'provenance.json').write_text(json.dumps(dict(source_commit=revision(),ramulator_commit=RAMULATOR_COMMIT,
        source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        upstream_verification=verified,started_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
    exe=native_build(root,out)
    cases=[run_case(exe,root,out,name) for name in MECHANISMS]
    cases += [run_case(exe,root,out,name,True) for name in ('baseline','subarray_overlap_2')]
    h,g,thermal=response(4,thermal_config(p),a.thermal_backend);rows=[]
    for case in cases:
        for mode in ('timing_only','trace_driven'):
            cfg=lp_config(p,2,case['steady']['useful_tb_s'],energy_mode=mode,
                          command_activity=case['activity'] if mode=='trace_driven' else None)
            extra_area=.0015*121 if case['settings']['subarrays']>1 else 0.
            cfg['hardware']['logic_static_w']+=extra_area*.1/16
            for workload in cfg['workloads']:
                for tm in (0,3,2):
                    r=optimize(cfg,h,g,workload,cfg['tilings'][0],Fabric('local',0),tm,[1/16]*16,'free')
                    r.update(case=case['name'],energy_mode=mode,energy_contract=cfg['energy_contract'],
                             additional_control_area_mm2=extra_area,area_budget_mm2=121,
                             active_area_mm2=organization_cost(p,2)['active_area_mm2']+extra_area)
                    rows.append(r)
    (out/'summary.json').write_text(json.dumps(dict(cases=cases,results=rows,thermal_solver=thermal,
        scope='Fixed K32 known-mechanism probes; no new architecture, no device reliability claim'),indent=2)+'\n')
    print('D1 complete',len(cases),'command cases',len(rows),'LP points',flush=True)


if __name__=='__main__':main()
