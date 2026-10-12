"""Actual RD-command/MAC-window overlap; admission lifetime is not service."""
import argparse
from bisect import bisect_right
import csv
import gzip
import json
from pathlib import Path


def read(path):
    with gzip.open(path,'rt') as f:
        return json.load(f)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();p=read(a.case/'program/program.json.gz')
    jobs={j['expert']:j for j in p['meta']['jobs']}
    if set(jobs)!={10,34} or any(jobs[e]['count']!=22 or jobs[e]['owners']!=[8,9,10,11] for e in jobs):
        raise ValueError('Frozen original Expert10/34 competition required')
    with gzip.open(a.case/'native/run-nodes.csv.gz','rt') as f:
        history={int(r['id']):{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)}
    kernels={r['node']:r for r in p['meta']['kernel_ledger']}
    intervals={t:[] for t in range(8,12)}
    for s in p['meta']['semantic_ledger']:
        if s['expert']!=10:continue
        for block in kernels[s['node']]['microtile_ledger']:
            h=history[block['node']]
            intervals[s['tile']].append((h['start'],h['finish'],block['node']))
    for values in intervals.values():values.sort()
    identities={r['node']:r for r in p['request_identity']}
    counts={t:dict(expert34_rd_commands=0,expert34_rd_during_expert10_mac=0) for t in range(8,12)}
    examples=[]
    for t,windows in intervals.items():
        starts=[r[0] for r in windows]
        with gzip.open(a.case/f'native/transaction-commands.ch{t}.csv.gz','rt') as f:
            for r in csv.DictReader(f):
                if r['command'] not in ('RD','RDA'):continue
                node=int(r['transaction_id']);identity=identities[node]
                if identity['expert']!=34:continue
                counts[t]['expert34_rd_commands']+=1
                tick=int(r['clock']);index=bisect_right(starts,tick)-1
                if index>=0 and windows[index][0]<=tick<windows[index][1]:
                    counts[t]['expert34_rd_during_expert10_mac']+=1
                    if len(examples)<12:
                        lo,hi,mac=windows[index]
                        examples.append(dict(tile=t,tick=tick,expert34_request=node,
                                             expert10_mac=mac,mac_start=lo,mac_finish=hi))
    counts32=sum(v['expert34_rd_commands'] for v in counts.values())
    overlap=sum(v['expert34_rd_during_expert10_mac'] for v in counts.values())
    result=dict(source='0d5b89b95cdb28c7823514d38f20ea3168395512',
                case=a.case.name,experts=[10,34],tokens_each=22,owners=[8,9,10,11],
                policy='Existing fine_prefetch; expert/MAC ordering retained',
                per_tile=counts,expert34_rd_commands=counts32,rd_overlap_commands=overlap,
                rd_overlap_fraction=overlap/counts32 if counts32 else None,examples=examples,
                boundary='RD issued inside actual MAC-service window. Not DRAM busy-time '
                         'inferred from acceptance/return, not RF or silicon qualification.')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
