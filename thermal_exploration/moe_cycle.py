"""Independent Python interpreter of the full finite-resource MoE program."""
from collections import Counter,defaultdict,deque
from heapq import heappush,heappop
from math import ceil
from .crossover_execution import RCD_NS


def execute(p,emit=lambda kind,row:None,max_ticks=2_000_000,oracle='none',memory_backend=None):
    if oracle not in ('none','link_only','flight_only','infinite_noc'):raise ValueError('Unsupported diagnostic')
    nodes=p['nodes'];n=len(nodes);children=[[] for _ in nodes];remaining=[len(r['deps']) for r in nodes]
    for r in nodes:
        for d in r['deps']:children[d].append(r['id'])
    ready=[[set() for _ in range(16)] for _ in range(9)];joins=[];done=[-1]*n;start=[-1]*n;left=[r['work'] for r in nodes];events=[];state=[0]*n
    busy=[0]*p['resource_count'];used=Counter();private=[0]*16;leases=defaultdict(list);releases=defaultdict(list)
    for l in p['leases']:leases[l['first']].append(l);releases[l['last']].append(l)
    router_for=defaultdict(list);router_users=defaultdict(list);router_used=Counter();router_left=[len(r['users']) for r in p['router']];router_reserved=[False]*len(p['router'])
    router_fifo=defaultdict(deque);router_served={}
    for i,r in enumerate(p['router']):
        router_for[r['first']].append(i)
        for child in r['users']:router_users[child].append(i)
    contexts=p['contexts'];vector=[-1]*16;mac=[None]*16;memory_until=[0.]*16
    activity=Counter();high=Counter();private_high=[0]*16;router_high=Counter();wait=Counter();completed=0;clock=0
    caps={int(k):v for k,v in p['caps'].items()};slaves={int(k):v for k,v in p['slaves'].items()}
    def enqueue(i):
        if nodes[i]['master']>=0:return
        if nodes[i]['kind']==0:heappush(joins,i)
        else:ready[nodes[i]['kind']][nodes[i]['tile']].add(i)
    for r in nodes:
        if not r['deps']:enqueue(r['id'])
    def finish(i,time):
        nonlocal completed
        if state[i]==3:raise ValueError('Repeated completion')
        state[i]=3;done[i]=time;completed+=1;emit('nodes',[i,start[i],time])
        # Reserved space includes flight, but the FIFO order is established
        # only when the physical flit arrives (source read or incoming link).
        for ri in router_for[i]:
            if not router_reserved[ri]:raise ValueError('Arrival without reserved flit')
            router_fifo[tuple(p['router'][ri]['key'])].append(ri)
        if nodes[i]['kind']==4:activity['mac']+=nodes[i]['work']
        for l in releases[i]:
            k=l['resource'];used[k]-=l['bytes'];private[l['tile']]-=l['bytes'];emit('leases',[time,k,l['tile'],-l['bytes']])
            if used[k]<0:raise ValueError('Unbalanced lease')
        for child in children[i]:
            remaining[child]-=1
            if remaining[child]==0:enqueue(child)
    def admissible(i):
        needs=Counter();bytile=Counter()
        for l in leases[i]:needs[l['resource']]+=l['bytes'];bytile[l['tile']]+=l['bytes']
        if any(used[k]+v>caps[k] for k,v in needs.items()):wait['byte_credit']+=1;return False
        if any(private[t]+p['fixed'][t]+v>p['private_budget'] for t,v in bytile.items()):wait['private_credit']+=1;return False
        for r in router_for[i]:
            key=tuple(p['router'][r]['key'])
            if router_used[key]>=8:wait['router_credit']+=1;return False
        for ri in router_users[i]:
            key=tuple(p['router'][ri]['key']);q=router_fifo[key]
            if not q or q[0]!=ri:wait['router_head']+=1;return False
            served=router_served.get(key)
            if served and served[0]==clock and served[1]!=ri:wait['router_input_service']+=1;return False
        return True
    def begin(i):
        if state[i]:return
        r=nodes[i];state[i]=1;start[i]=clock;ready[r['kind']][r['tile']].discard(i)
        for l in leases[i]:
            k=l['resource'];used[k]+=l['bytes'];private[l['tile']]+=l['bytes'];high[k]=max(high[k],used[k]);private_high[l['tile']]=max(private_high[l['tile']],private[l['tile']]+p['fixed'][l['tile']]);emit('leases',[clock,k,l['tile'],l['bytes']])
        for ri in router_for[i]:
            key=tuple(p['router'][ri]['key']);router_used[key]+=1;router_high[key]=max(router_high[key],router_used[key]);router_reserved[ri]=True;emit('router',[clock,*key,1,ri])
        for ri in router_users[i]:
            if not router_reserved[ri]:raise ValueError('Consumer without router reservation')
            key=tuple(p['router'][ri]['key'])
            if not router_fifo[key] or router_fifo[key][0]!=ri:raise ValueError('Consumer bypassed FIFO head')
            router_served[key]=(clock,ri)
            router_left[ri]-=1
            if router_left[ri]==0:
                router_fifo[key].popleft();router_used[key]-=1;emit('router',[clock,*key,-1,ri])
    def schedule(i,time):state[i]=2;heappush(events,(time,i))
    for clock in range(max_ticks):
        while events and events[0][0]<=clock:
            time,i=heappop(events);r=nodes[i];finish(i,time)
            if r['kind']==4:
                for slave in slaves[i]:start[slave]=start[i];state[slave]=2;finish(slave,time)
                mac[r['tile']]=None
            if r['context']>=0 and r['phase']==2:vector[r['tile']]=-1
        deferred=[]
        while joins:
            i=heappop(joins)
            if not admissible(i):deferred.append(i);continue
            begin(i);finish(i,clock)
        for i in deferred:heappush(joins,i)
        if completed==n:break
        rb=[256]*16;wb=[128]*16;vb=[16]*16;hb=[500]*16;fifo=[0]*16
        for tile in range(16):
            if mac[tile] is None:
                for i in sorted(ready[4][tile]):
                    if not admissible(i):continue
                    r=nodes[i];begin(i);mac[tile]=dict(id=i,until=clock+r['ticks'],read=r['read'],fifo=r['fifo'],flops=r['work']);schedule(i,clock+r['ticks']);break
            a=mac[tile]
            if a:
                t=a['until']-clock;read=ceil(a['read']/t);fr=ceil(a['fifo']/t);fma=ceil(a['flops']/t);a['read']-=read;a['fifo']-=fr;a['flops']-=fma;rb[tile]-=read;fifo[tile]=fr;activity['sram_read']+=read;activity['fifo_read']+=fr
                if rb[tile]<0 or fr>500:raise ValueError('MAC invented a port')
                emit('service',[clock,a['id'],4,fma])
                for slave in slaves[a['id']]:emit('service',[clock,slave,nodes[slave]['kind'],read if nodes[slave]['kind']==1 else fr])
            if vector[tile]<0:
                candidates=[i for i in ready[1][tile] if nodes[i]['context']>=0 and nodes[i]['phase']==0]
                for i in sorted(candidates):
                    if admissible(i):vector[tile]=nodes[i]['context'];break
            cid=vector[tile]
            if cid>=0:
                for i in contexts[cid]:
                    if done[i]>=0:continue
                    if state[i]==2 or remaining[i]:break
                    if not state[i]:
                        if not admissible(i):break
                        begin(i)
                    if not left[i]:
                        finish(i,clock)
                        if nodes[i]['phase']==2:vector[tile]=-1
                        continue
                    kind=nodes[i]['kind'];budget=rb if kind==1 else wb if kind==2 else vb;take=min(left[i],budget[tile]);left[i]-=take;budget[tile]-=take;activity[('sram_read' if kind==1 else 'sram_write' if kind==2 else 'vector')]+=take
                    emit('service',[clock,i,kind,take])
                    if not left[i]:schedule(i,clock+1)
                    break
            # Drain sinks before source reads; all consumers share the residual
            # physical budget already used above by MAC/one vector context.
            for kind,budget in ((2,wb),(1,rb),(6,hb)):
                for i in sorted(ready[kind][tile]):
                    if nodes[i]['context']>=0:continue
                    if budget[tile]<=0:break
                    if not state[i]:
                        if not admissible(i):continue
                        begin(i);ready[kind][tile].add(i)
                    take=min(left[i],budget[tile]);left[i]-=take;budget[tile]-=take;activity['hb' if kind==6 else 'sram_write' if kind==2 else 'sram_read']+=take
                    emit('service',[clock,i,kind,take])
                    if not left[i]:ready[kind][tile].remove(i);schedule(i,clock+1)
            for i in sorted(ready[5][tile]):
                r=nodes[i];rid=r['resource']
                if busy[rid]>clock:wait['link_serial']+=1;continue
                if not admissible(i):continue
                begin(i);busy[rid]=clock+(0 if oracle in ('link_only','infinite_noc') else 4);schedule(i,clock+(0 if oracle in ('flight_only','infinite_noc') else 8));activity['link']+=32
            for i in sorted(ready[7][tile]):
                if not admissible(i):break
                if memory_backend is not None and not memory_backend.send(i,nodes[i]['address'],tile):wait['native_controller_reject']+=1;break
                if memory_backend is not None:
                    begin(i);state[i]=2;activity['dram']+=nodes[i]['work'];break
                r=nodes[i];begin(i);tier=r['tier'];rate=min(26.599/16*1000*.25,16*4096/ceil((RCD_NS[tier]+27.5+4.77)/.25));memory_until[tile]=max(clock,memory_until[tile])+r['work']/rate;depart=ceil(memory_until[tile])+ceil((RCD_NS[tier]+4)/.25);schedule(i,depart);activity['dram']+=r['work'];emit('requests',[i,clock,depart,r['address']]);break
            emit('ports',[clock,tile,256-rb[tile],128-wb[tile],16-vb[tile],500-hb[tile],fifo[tile]])
        if memory_backend is not None:
            for i,depart in memory_backend.tick(clock):
                if state[i]!=2 or start[i]<0:raise ValueError('Online memory completion identity')
                schedule(i,depart);emit('requests',[i,start[i],depart,nodes[i]['address']])
    else:raise ValueError('Finite MoE executor failed to drain')
    if any(used.values()) or any(router_used.values()) or any(router_fifo.values()):raise ValueError('Leases or router credits leaked')
    if any(start[r['id']]<max((done[d] for d in r['deps']),default=0) for r in nodes):raise ValueError('Premature consumer')
    if memory_backend is not None:memory_backend.close()
    return dict(ticks=clock,time_us=clock*.00025,activity=dict(activity),private_peak=max(private_high),router_peak=max(router_high.values(),default=0),wait=dict(wait),nodes=n,oracle=oracle,memory_backend='online_native' if memory_backend else 'tier_fluid',source='Independent Python full MoE cycle execution; memory model stated explicitly, no measured arrival input')
