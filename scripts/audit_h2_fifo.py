"""Independent flit FIFO/credit replay from emitted H2 traces."""
import argparse
from collections import defaultdict,deque
import csv
import json
from pathlib import Path


def port(node,source):
    if source==node:return 4
    if source==node-1 and node%4:return 0
    if source==node+1 and node%4!=3:return 1
    if source==node-4:return 2
    if source==node+4:return 3
    raise ValueError('Nonneighbor')


def replay(events,depth=8):
    data=defaultdict(deque);incoming=defaultdict(int);maximum=0
    for tick,phase,node,selector,op,payload in sorted(events,key=lambda e:e[:4]):
        key=payload[0]
        if op=='inject':data[key].append(payload[1])
        elif op=='arrival':
            if incoming[key]<=0:raise ValueError('Arrival without reserved credit')
            incoming[key]-=1;data[key].append(payload[1])
        elif op=='pop':
            if not data[key] or data[key].popleft()!=payload[1]:raise ValueError('FIFO order/availability violation')
            for target in payload[2]:incoming[target]+=1
        elif op=='end':
            if sum(len(v)+incoming[k] for k,v in data.items() if k[0]==node)!=payload[1]:
                raise ValueError('Recorded router occupancy disagrees with replay')
        for k in (key,*(payload[2] if op=='pop' else ())):
            total=len(data[k])+incoming[k]
            if total>depth or total<0:raise ValueError('Router credit overflow')
            maximum=max(maximum,total)
    if any(data.values()) or any(incoming.values()):raise ValueError('Undrained flits')
    return maximum


def audit(case):
    c=json.loads((case/'contract.json').read_text())
    if c['ideal_noc']:return dict(status='NOT_APPLICABLE: transport bypass oracle')
    def read(path):
        with path.open() as f:
            for row in csv.DictReader(f):yield {k:v if k=='kind' else int(v) for k,v in row.items()}
    trees={}
    for kind,name in (('X','inputs'),('R','reductions')):
        for line in (case/(name+'.tsv')).read_text().splitlines():
            v=list(map(int,line.split()));trees[kind,v[0]]=(v[1],v[5:])
    events=[];pops={};links=0
    for r in read(case/'run-inject.csv'):
        vc=int(r['kind']=='R');key=(r['tile'],4,vc)
        root,_=trees[r['kind'],r['group']]
        flit=(r['kind'],r['group'],r['flit'],root if vc==0 else r['tile'])
        events.append((r['tick'],1,r['tile'],0,'inject',(key,flit)))
    for r in read(case/'run-noc.csv'):
        links+=1;vc=int(r['kind']=='R');root,parent=trees[r['kind'],r['group']]
        source,target=r['source'],r['target'];flit=(r['kind'],r['group'],r['flit'],root if not vc else source)
        key=(source,4 if vc or source==root else port(source,parent[source]),vc)
        dest=(target,port(target,source),vc)
        phase=2 if vc else 0;selector=0 if vc else (key[1]*2-r['start']%10)%10
        popkey=(r['start'],phase,source,selector,key,flit)
        pops.setdefault(popkey,[]).append(dest)
        events.append((r['finish'],-1,target,0,'arrival',(dest,flit)))
    for r in read(case/'run-sink.csv'):
        vc=int(r['kind']=='R');root,parent=trees[r['kind'],r['group']];tile=r['tile']
        if not vc and any(p==tile for p in parent):continue # Atomic fork also ejects locally.
        key=(tile,port(tile,r['child'] if vc else parent[tile]),vc)
        selector=(key[1]*2+vc-r['tick']%10)%10
        flit=(r['kind'],r['group'],r['flit'],r['child'])
        popkey=(r['tick'],0,tile,selector,key,flit)
        if popkey in pops:raise ValueError('Double FIFO pop')
        pops[popkey]=[]
    for (tick,phase,node,selector,key,flit),targets in pops.items():
        events.append((tick,phase,node,selector,'pop',(key,flit,targets)))
    for r in read(case/'run-ports.csv'):
        events.append((r['tick'],3,r['tile'],0,'end',((r['tile'],4,0),r['router_flits'])))
    maximum=replay(events)
    return dict(status='PASS',maximum_input_fifo_reserved_flits=maximum,depth=8,link_flits=links,
        scope='Independent exact FIFO ordering and queued/inflight credit reconstruction including same-tick router phases')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runs',nargs='+',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    records={}
    for run in map(Path,a.runs):
        for case in sorted(p for p in run.iterdir() if p.is_dir() and (p/'result.json').exists()):
            key=run.name+'/'+case.name
            records[key]=audit(case);print(key,records[key]['status'],flush=True)
    Path(a.output).write_text(json.dumps(records,indent=2)+'\n')


if __name__=='__main__':main()
