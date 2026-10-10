"""Append bounded cost/interface controls without repeating unchanged commands."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from .organization import bounds,load_exploration,organization_cost,scenarios,solve,thermal_config,values
from .run import revision
from .thermal import response


def main():
    a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--output',required=True)
    a.add_argument('--thermal-backend',choices=['hits','scipy'],default='scipy');args=a.parse_args()
    src=Path(args.input);out=Path(args.output)
    if out.exists():raise SystemExit('Preserve previous outputs')
    profile=load_exploration()
    if json.loads((src/'profile.json').read_text())!=profile:
        raise ValueError('Cannot reuse commands with a changed baseline contract')
    s=json.loads((src/'summary.json').read_text());old_scenarios={r['scenario'] for r in s['results']}
    lookup={r['paths']:r['steady_window'] for r in s['command_cases']
            if r['trace_kind']=='streaming' and not r['ideal_row_retention'] and r['hb_tb_s']==32}
    for name,q in scenarios(profile):
        if name in old_scenarios:continue
        h,g,record=response(4,thermal_config(q),args.thermal_backend)
        s['thermal_solver_records'].append(dict(scenario=name,**record))
        for allocation in ('shared_area','fixed_compute'):
            for paths in (1,2,4,8):
                cost=organization_cost(q,paths,allocation)
                if not cost['area_feasible']:
                    s['rejected_organizations'].append(dict(scenario=name,paths=paths,reason='fixed area budget exceeded',**cost));continue
                service=min(lookup[paths]['useful_tb_s'],values(q)['hb_chip_tb_s'])
                for workload in ((0,1,2) if allocation=='shared_area' else (0,1)):
                    for mode in (0,3,2):
                        r=solve(q,paths,service,h,g,workload,mode,allocation=allocation)
                        r.update(scenario=name,paths=paths,allocation=allocation,service_tb_s=service,
                                 service_evidence='Reused unchanged multi-refresh command evidence',necessary_bounds=bounds(q,paths))
                        s['results'].append(r)
        print('Additional bounded control',name,flush=True)
    out.mkdir(parents=True)
    for name,data in [('profile.json',profile),('summary.json',s)]:
        (out/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    provenance=json.loads((src/'provenance.json').read_text())
    provenance['extension']=dict(source_commit=revision(),utc=datetime.now(timezone.utc).isoformat(),
        unchanged_command_source_commit=provenance['source_commit'],
        controls=['periphery_area_low','periphery_area_high','bond_resistance_low','bond_resistance_high','uniform_cooling','cooling_gradient_high'],
        scope='No default, command, area-function or power-function change; added labeled one-at-a-time controls')
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')


if __name__=='__main__':main()
