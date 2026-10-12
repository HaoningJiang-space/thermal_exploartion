"""Same program, changed FIFO execution, potentially unchanged end latency."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from thermal_exploration.moe_fifo_audit import check_fifo


def digest(path):
    h=hashlib.sha256()
    with gzip.open(path,'rb') as f:
        while data:=f.read(2**20):h.update(data)
    return h.hexdigest()


def times(case):
    with gzip.open(case/'native/run-nodes.csv.gz','rt') as f:
        return {int(r['id']):{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retired',type=Path,required=True)
    ap.add_argument('--fixed',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();old_program=a.retired/'program/program.json.gz';new_program=a.fixed/'program/program.json.gz'
    ph=digest(old_program)
    if ph!=digest(new_program):raise ValueError('Pair changed work/dependency program')
    with gzip.open(old_program,'rt') as f:p=json.load(f)
    old,new=times(a.retired),times(a.fixed)
    if set(old)!=set(new):raise ValueError('Pair changed operation identity')
    changed=[i for i in old if old[i]!=new[i]]
    divergences=[(min(old[i][phase],new[i][phase]),phase,i)
                 for i in changed for phase in ('start','finish')
                 if old[i][phase]!=new[i][phase]]
    first_event=min(divergences) if divergences else None
    first=first_event[2] if first_event else None
    old_fifo=check_fifo(p,old)
    result=dict(case=a.fixed.name,semantic_program_sha256=ph,
                identical_program=True,changed_node_times=len(changed),
                first_changed_node=None if first is None else dict(id=first,
                    time=first_event[0],phase=first_event[1],
                    kind=p['nodes'][first]['kind'],stage=p['nodes'][first]['stage'],
                    retired=old[first],fixed=new[first]),
                retired_fifo=old_fifo,fixed_fifo=check_fifo(p,new),
                first_violation_consumer_kinds=({str(i):p['nodes'][i]['kind']
                    for side in ('head','bypass') for i in old_fifo['examples'][0][side]['consumers']}
                    if old_fifo['examples'] else {}),
                retired_finish_tick=max(x['finish'] for x in old.values()),
                fixed_finish_tick=max(x['finish'] for x in new.values()),
                native_request_history_equal=digest(a.retired/'native/run-requests.csv.gz')==digest(a.fixed/'native/run-requests.csv.gz'),
                interpretation='Equal end latency does not imply equal or legal execution. '
                'FIFO correction alone, identical abstract MAC program; not physical RF qualification.')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
