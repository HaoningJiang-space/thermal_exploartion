"""Observer replay. Checks physical histories, not two predictors agreeing."""
from collections import Counter,defaultdict
from math import ceil
import csv,gzip,heapq
from .moe_cycle_program import KINDS
from .moe_fifo_audit import check_fifo


def rows(path):
    path=str(path);op=gzip.open if path.endswith('.gz') else open
    with op(path,'rt',newline='') as f:
        for r in csv.DictReader(f):yield {k:int(v) for k,v in r.items()}

def replay(p,prefix,summary):
    def path(kind):
        from pathlib import Path
        a=Path(str(prefix)+'-'+kind+'.csv');return a if a.exists() else a.with_suffix('.csv.gz')
    nodes=p['nodes'];actual={r['id']:r for r in rows(path('nodes'))}
    if set(actual)!=set(range(len(nodes))):raise ValueError('Node identity not conserved')
    activity=Counter();context_intervals=defaultdict(list);mac_intervals=defaultdict(list);links=defaultdict(list)
    for n in nodes:
        r=actual[n['id']]
        if r['start']<max((actual[d]['finish'] for d in n['deps']),default=0) or r['finish']<r['start']:raise ValueError('Consumer before producer')
        if n['kind']==3 and not n['work'] and r['finish']!=r['start']:raise ValueError('Invented zero-operation vector delay')
        if n['kind']==4:
            if r['finish']-r['start']!=max(1,ceil(n['work']/2000),ceil(n['read']/256),ceil(n['fifo']/500)):raise ValueError('MAC arithmetic/operand floor changed')
            mac_intervals[n['tile']].append((r['start'],r['finish']));activity['mac']+=n['work']
        if n['master']>=0:
            if (r['start'],r['finish'])!=(actual[n['master']]['start'],actual[n['master']]['finish']):raise ValueError('Coissued slave timing changed')
        if n['kind']==5:
            if r['finish']-r['start']!=8 or n['work']!=32:raise ValueError('Changed physical flit flight')
            if not 0<n['valid_bytes']<=32:raise ValueError('Invalid logical flit byte mask')
            parent=nodes[n['deps'][0]]
            if parent['kind']==5 and n['valid_bytes']!=parent['valid_bytes']:raise ValueError('Forwarding changed payload mask')
            links[n['tile'],n['target']].append(r['start']);activity['link']+=32
    for ids in p['contexts']:
        tile=nodes[ids[0]]['tile'];a,b,c=[actual[i] for i in ids]
        if a['finish']>b['start'] or b['finish']>c['start']:raise ValueError('Illegal vector phase overlap')
        context_intervals[tile].append((a['start'],c['finish']))
    for families in (context_intervals,mac_intervals):
        for intervals in families.values():
            ordered=sorted(intervals)
            if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):raise ValueError('Extra vector or MAC context')
    for times in links.values():
        ordered=sorted(times)
        if any(b-a<4 for a,b in zip(ordered,ordered[1:])):raise ValueError('Link serialization exceeded')
    used=Counter();private=Counter();caps={int(k):v for k,v in p['caps'].items()};peaks=Counter();private_peak=0
    expected_leases=Counter()
    for l in p['leases']:
        expected_leases[(actual[l['first']]['start'],l['resource'],l['tile'],l['bytes'])]+=1
        expected_leases[(actual[l['last']]['finish'],l['resource'],l['tile'],-l['bytes'])]+=1
    observed=Counter()
    for r in rows(path('leases')):
        observed[(r['tick'],r['resource'],r['tile'],r['delta'])]+=1;used[r['resource']]+=r['delta'];private[r['tile']]+=r['delta'];peaks[r['resource']]=max(peaks[r['resource']],used[r['resource']]);private_peak=max(private_peak,private[r['tile']]+p['fixed'][r['tile']])
        if not 0<=used[r['resource']]<=caps[r['resource']] or private[r['tile']]+p['fixed'][r['tile']]>p['private_budget']:raise ValueError('Private lease/capacity exceeded')
    if any(used.values()) or observed!=expected_leases:raise ValueError('Lost private lease')
    expected_router=Counter()
    for i,r in enumerate(p['router']):
        expected_router[(actual[r['first']]['start'],*r['key'],1,i)]+=1
        expected_router[(max(actual[j]['start'] for j in r['users']),*r['key'],-1,i)]+=1
    observed=Counter();usage=Counter();router_peak=0
    for r in rows(path('router')):
        key=r['tile'],r['port'],r['vc'];usage[key]+=r['delta'];router_peak=max(router_peak,usage[key]);observed[(r['tick'],*key,r['delta'],r['credit'])]+=1
        if not 0<=usage[key]<=8:raise ValueError('Extra port/VC flit credit')
    if any(usage.values()) or observed!=expected_router:raise ValueError('Lost flit credit')
    fifo_check=check_fifo(p,actual)
    if fifo_check['status']!='PASS_FIFO_HEAD_ORDER':raise ValueError('Illegal FIFO head bypass or input service overrun')
    requests={r['id']:r for r in rows(path('requests'))};expected={r['node']:r for r in p['request_identity']}
    if set(requests)!=set(expected):raise ValueError('Request identity changed')
    for i,n in expected.items():
        r=requests[i]
        if r['address']!=n['address'] or r['accepted']!=actual[i]['start'] or r['depart']!=actual[i]['finish'] or not r['accepted']<r['depart']:raise ValueError('Native request identity/causality changed')
    expected_activity=Counter()
    for n in nodes:
        if n['kind'] in (1,2,3,6,7,8):expected_activity[KINDS[n['kind']]]+=n['work']
    service=iter(rows(path('service')));current=next(service,None);served=Counter()
    portrows=0;previous=(-1,15)
    for r in rows(path('ports')):
        if (r['tick'],r['tile'])!=((previous[0]+1,0) if previous[1]==15 else (previous[0],previous[1]+1)):raise ValueError('Missing or reordered port tick')
        previous=r['tick'],r['tile'];portrows+=1
        allocated=Counter()
        while current is not None and (current['tick'],nodes[current['id']]['tile'])<=(r['tick'],r['tile']):
            n=nodes[current['id']];t=actual[current['id']]
            if (current['tick'],n['tile'])!=(r['tick'],r['tile']) or current['kind']!=n['kind'] or not t['start']<=current['tick']<t['finish'] or current['amount']<0:raise ValueError('Noncausal per-node service')
            served[n['id']]+=current['amount'];allocated[n['kind']]+=current['amount'];current=next(service,None)
        if allocated[4]>2000:raise ValueError('Extra MAC arithmetic capacity')
        for key,cap,kind in (('read',256,'sram_read'),('write',128,'sram_write'),('vector',16,'vector'),('hb',500,'hb'),('fifo',500,'fifo_read')):
            if not 0<=r[key]<=cap:raise ValueError('Port service overrun')
            code={'sram_read':1,'sram_write':2,'vector':3,'hb':6,'fifo_read':8}[kind]
            if r[key]!=allocated[code]:raise ValueError('Port allocation not attributable to nodes')
            activity[kind]+=r[key]
    if current is not None or any(served[n['id']]!=n['work'] for n in nodes if n['kind'] in (1,2,3,4,6,8)):raise ValueError('Node finished without actual service')
    activity['dram']=1024*len(requests)
    if portrows!=summary['ticks']*16 or any(activity[k]!=v for k,v in expected_activity.items()) or dict(activity)!=summary['activity']:raise ValueError('Activity/port work not conserved')
    return dict(status='PASS_INDEPENDENT_FULL_PROGRAM_REPLAY',fifo_check=fifo_check,nodes=len(actual),requests=len(requests),port_rows=portrows,private_peak=private_peak,router_peak=router_peak,activity=dict(activity))
