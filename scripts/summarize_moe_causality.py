"""Export completed real-route frontend evidence without architecture certification."""
import argparse
import json
from pathlib import Path


def completed(root):
    records=[]
    for case in sorted(root.iterdir()):
        if not case.is_dir() or not (case/'program').is_dir():continue
        status=Path(str(case)+'.exit')
        if not status.exists() or status.read_text().strip()!='0':
            raise ValueError('Evidence process did not complete: '+case.name)
        q=json.loads((case/'qualification.json').read_text())
        params={k:q['params'][k] for k in ('batch','tp','down','step','layer','scope')}
        native=q['references'][0];fluid=q['references'][1]
        numerical=json.loads((case/'numerical.json').read_text())
        physical=q.get('physical_contract_audit')
        records.append(dict(case=case.name,source=q['source'],params=params,
            native_time_us=native['time_us'],fluid_time_us=fluid['time_us'],
            python_native_time_us=q['native_predictor']['time_us'],
            python_fluid_time_us=q['predictor']['time_us'],
            frontend_absolute_error=q['qualified_absolute_native_error'],
            fluid_absolute_error=q['absolute_native_error'],
            native_traces=q['native_trace_comparison'],fluid_traces=q['fluid_trace_comparison'],
            native_replay=native['replay'],fluid_replay=fluid['replay'],
            python_native_replay=q['native_predictor']['replay'],python_fluid_replay=q['predictor']['replay'],
            native_commands=native['commands'],python_native_commands=q['native_predictor']['commands'],
            numerical=numerical,
            transport=json.loads((case/'transport-numerical.json').read_text()),
            physical_contract_status=physical['status'] if physical else 'RETIRED_NO_PHYSICAL_QUALIFICATION',
            retained_output_requirement_bytes_per_tile=physical['retained_output_requirement_bytes_per_tile'] if physical else None,
            architecture_g3_g4_qualified=False))
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experts',type=Path,required=True)
    p.add_argument('--full',type=Path,required=True)
    p.add_argument('--retired-control',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();records=completed(a.experts)+completed(a.full);retired=completed(a.retired_control)
    if len(records)!=5 or len(retired)!=1:raise ValueError('Frozen five corrected and one retired comparison required')
    if any(not all(z['equal'] for z in r[k].values()) for r in records for k in ('native_traces','fluid_traces')):
        raise ValueError('Frontend trace mismatch: export first divergence before summarizing')
    fixed=next(r for r in records if r['params']['scope']=='moe' and r['params']['batch']==32)
    old=retired[0]
    summary=dict(status='FRONTEND_REGRESSIONS_COMPLETE_ARCHITECTURE_G3_G4_NOT_ESTABLISHED',
        corrected_cases=records,retired_fifo_control=retired,
        pairing=dict(case=fixed['case'],retired_native_us=old['native_time_us'],
            fixed_native_us=fixed['native_time_us'],native_end_time_equal=old['native_time_us']==fixed['native_time_us'],
            retired_fluid_us=old['fluid_time_us'],fixed_fluid_us=fixed['fluid_time_us']),
        targets=dict(frontend_absolute=.1,architecture_relative=.05),
        matrix_ranking_qualification_executed=False,
        architecture_g3_g4_qualified=False,hardware_go=False,
        boundary='Same high-level builder and abstract registered MAC law; independent frontends, '
                 'shared online native DRAM model; no finite Matrix RF or M/K proof. '
                 'Real routing/full dimensions, small numeric tensors are semantic controls only.')
    a.output.write_text(json.dumps(summary,indent=2)+'\n')
