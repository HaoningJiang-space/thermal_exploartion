"""Independent finite-flit interpreter of the existing H2 tensor contract.

This is a component qualification frontend, not a replacement for the MoE
Graph executor. Same tasks/ownership/ports/credits and arbitration as the
frozen C++ reference; memory is the pre-existing fluid service abstraction.
No recorded arrival times or empirical latency factors are inputs.
"""
from collections import Counter,deque
from heapq import heappush,heappop
from math import ceil


class Arrival:
    __slots__=('time','node','port','vc','data')
    def __init__(self,time,node,port,vc,data):
        self.time,self.node,self.port,self.vc,self.data=time,node,port,vc,data
    def __lt__(self,other):return self.time<other.time


def execute_tensor(model,max_ticks=2_000_000,record=True):
    c=model['contract'];tasks=model['tasks'];requests=model['requests'];inputs=model['inputs'];reductions=model['reductions']
    if not c['stream_fifo'] or c['ideal_noc'] or c['ideal_memory'] or c['ideal_buffer'] or c['barrier']:
        raise ValueError('Qualification requires the finite streaming contract')
    if c['flit_bytes']!=32 or c['vc_depth_flits']!=8 or c['virtual_channels']!=2:
        raise ValueError('Changed finite flit contract')
    fixed_rates={'sram_read_bytes_per_tick':256,'sram_write_bytes_per_tick':128,'vector_ops_per_tick':16,'hb_bytes_per_tile_tick':500,'fifo_bytes_per_tick':500,'link_serial_ticks':4,'link_latency_ticks':8}
    if any(c[k]!=v for k,v in fixed_rates.items()):raise ValueError('Unsupported physical rate change')
    local=[[] for _ in range(16)]
    for t in tasks:local[t['tile']].append(t['id'])
    read_state=[dict(remaining=r['refs'],allocated=False,accepted=-1,depart=-1,hb_first=-1,hb_done=-1,last_use=-1,transferred=0) for r in requests]
    task_state=[dict(done=False,start=-1,finish=-1) for _ in tasks]
    xreceived=[[0]*16 for _ in inputs];xseen=[[set() for _ in range(16)] for _ in inputs];xlast=[[-1]*16 for _ in inputs]
    xp=[set() for _ in range(16)];op=[set() for _ in range(16)];vr=[set() for _ in range(16)];input_next=[0]*len(inputs)
    for g in inputs:
        root=g['source'];gid=g['id']
        if root in g['targets']:xreceived[gid][root]=g['bytes'];xseen[gid][root]=set(range(g['bytes']//32));xlast[gid][root]=0
        if g['children'][root]:xp[root].add(gid)
    red=[[dict(local=False,slot=False,queued=False,complete=False,next_flit=0,finish=-1,start=-1,read=0,ops=0,write=0,reserved=0,received=[0]*16,seen={}) for _ in range(16)] for _ in reductions]
    fifo=[[[deque() for _ in range(2)] for _ in range(5)] for _ in range(16)];incoming=[[[0]*2 for _ in range(5)] for _ in range(16)];link_until=[[0]*16 for _ in range(16)];arrivals=[]
    mac=[None]*16;vec=[None]*16;admitted=[set() for _ in range(16)];unsent=[set() for _ in range(16)];admit_index=[0]*16
    hb=[deque() for _ in range(16)];wused=[0]*16;rused=[0]*16;redused=[0]*16;fluid_until=[0.]*16;fluid_returns=[]
    whigh=[0]*16;rhigh=[0]*16;redhigh=[0]*16;activity=Counter();bytehops=Counter();counters=Counter();mac_done=roots_done=returned=accepted=0
    port_records=[];noc_records=[];inject_records=[];vector_records=[];queue_records=[];lease_records=[];last_vector=0;clock=0
    def queue_change(tile,port,vc,delta):
        if record:queue_records.append(dict(tick=clock,tile=tile,port=port,vc=vc,delta=delta))
    def lease_change(tile,kind,delta):
        if record:lease_records.append(dict(tick=clock,tile=tile,kind=kind,delta=delta))
    def port_for(node,source):
        if source==node:return 4
        if source==node-1 and node%4:return 0
        if source==node+1 and node%4!=3:return 1
        if source==node-4:return 2
        if source==node+4:return 3
        raise ValueError('Nonlocal physical link')
    def reserve(gid,tile):
        a=red[gid][tile];g=reductions[gid]
        if a['slot'] or not g['children'][tile]:return True
        need=(len(g['children'][tile])+1)*g['bytes']
        if redused[tile]+need>c['reduce_buffer']:return False
        a['slot']=True;a['reserved']=need;redused[tile]+=need;lease_change(tile,'reduce',need);redhigh[tile]=max(redhigh[tile],redused[tile]);return True
    def ready(gid,tile):
        g=reductions[gid];a=red[gid][tile]
        belongs=tile==g['root'] or tile in g['producers'] or bool(g['children'][tile])
        return belongs and not a['queued'] and not a['complete'] and (tile not in g['producers'] or a['local']) and all(a['received'][child]==g['bytes'] for child in g['children'][tile])
    def deliver(f,tile):
        kind,gid,index,child=f
        if kind==0:
            g=inputs[gid]
            if tile not in g['targets'] or index in xseen[gid][tile]:raise ValueError('Repeated/unneeded input')
            xseen[gid][tile].add(index);xreceived[gid][tile]+=32;xlast[gid][tile]=clock
        else:
            g=reductions[gid];a=red[gid][tile]
            if g['parent'][child]!=tile or not a['slot']:raise ValueError('Unreserved reduction return')
            seen=a['seen'].setdefault(child,set())
            if index in seen:raise ValueError('Repeated partial flit')
            seen.add(index);a['received'][child]+=32
            if ready(gid,tile):vr[tile].add(gid)
    def release_output(gid,tile):
        nonlocal roots_done
        a=red[gid][tile]
        if tile==reductions[gid]['root']:
            roots_done+=1
            if a['slot']:redused[tile]-=a['reserved'];lease_change(tile,'reduce',-a['reserved']);a['slot']=False
        else:op[tile].add(gid)
    def send(f,node,target,vc):
        port=port_for(target,node);incoming[target][port][vc]+=1;link_until[node][target]=clock+4
        queue_change(target,port,vc,1)
        heappush(arrivals,Arrival(clock+8,target,port,vc,f));bytehops['X' if f[0]==0 else 'R']+=32
        if record:noc_records.append(dict(kind=f[0],group=f[1],flit=f[2],source=node,target=target,bytes=32,start=clock,finish=clock+8))
    for clock in range(max_ticks):
        while fluid_returns and fluid_returns[0][0]<=clock:
            time,rid=heappop(fluid_returns);r=read_state[rid]
            if r['depart']>=0 or r['accepted']<0:raise ValueError('Memory response identity')
            r['depart']=time;hb[requests[rid]['tile']].append(rid);returned+=1
        while arrivals and arrivals[0].time<=clock:
            f=heappop(arrivals)
            if incoming[f.node][f.port][f.vc]<=0:raise ValueError('Unreserved router FIFO')
            incoming[f.node][f.port][f.vc]-=1;fifo[f.node][f.port][f.vc].append(f.data)
        for tile in range(16):
            a=mac[tile]
            if a is None or a['until']>clock:continue
            if a['read'] or a['write'] or a['fifo']:raise ValueError('Premature MAC completion')
            tid=a['id'];t=tasks[tid];task_state[tid].update(done=True,finish=clock);mac_done+=1;activity['mac']+=t['flops']
            for rid in t['requests']:
                r=read_state[rid];r['remaining']-=1
                if r['hb_done']<0 or r['remaining']<0:raise ValueError('Premature/repeated weight use')
                r['last_use']=clock
                if not r['remaining']:wused[tile]-=1024;lease_change(tile,'weight',-1024);r['allocated']=False
            admitted[tile].remove(tid);mac[tile]=None
            if t['final']:
                for g in reductions:
                    if not (t['m_start']<=g['row']<t['m_start']+t['m_count'] and tile in g['producers']):continue
                    gid=g['id'];a=red[gid][tile]
                    if a['local']:raise ValueError('Duplicate output block')
                    a['local']=True
                    if not g['children'][tile] and tile!=g['root']:a.update(complete=True,finish=clock);release_output(gid,tile)
                    elif ready(gid,tile):vr[tile].add(gid)
        if mac_done==len(tasks) and roots_done==len(reductions):break
        rb=[256]*16;wb=[128]*16;vb=[16]*16;fifo_read=[0]*16
        for tile in range(16):
            while admit_index[tile]<len(local[tile]) and len(admitted[tile])<c['prefetch_tasks']:
                tid=local[tile][admit_index[tile]];t=tasks[tid];missing=sum(1024 for rid in t['requests'] if not read_state[rid]['allocated'])
                if wused[tile]+missing>c['weight_buffer']:break
                for rid in t['requests']:
                    r=read_state[rid]
                    if r['allocated']:continue
                    if r['remaining']<=0 or r['accepted']>=0:raise ValueError('Released weight reread')
                    r['allocated']=True;wused[tile]+=1024;lease_change(tile,'weight',1024);unsent[tile].add(rid)
                admitted[tile].add(tid);admit_index[tile]+=1
            whigh[tile]=max(whigh[tile],wused[tile])
            if mac[tile] is None:
                for tid in sorted(admitted[tile]):
                    t=tasks[tid]
                    if t['parent']>=0 and not task_state[t['parent']]['done']:continue
                    if xreceived[t['input_group']][tile]!=inputs[t['input_group']]['bytes'] or any(read_state[rid]['hb_done']<0 for rid in t['requests']):continue
                    read=t['k_count']*c['batch']*2+(t['m_count']*c['batch']*4 if t['parent']>=0 else 0);write=t['m_count']*c['batch']*4;weight=t['m_count']*t['k_count']*2
                    duration=max(1,ceil(t['flops']/c['mac_flops_per_tick']),ceil(read/256),ceil(write/128),ceil(weight/500))
                    task_state[tid]['start']=clock;mac[tile]=dict(id=tid,until=clock+duration,read=read,write=write,fifo=weight);break
            a=mac[tile]
            if a is not None:
                left=a['until']-clock;read=ceil(a['read']/left);write=ceil(a['write']/left);fr=ceil(a['fifo']/left)
                rb[tile]-=read;wb[tile]-=write;a['read']-=read;a['write']-=write;a['fifo']-=fr;fifo_read[tile]=fr
                if min(rb[tile],wb[tile])<0 or fr>500:raise ValueError('MAC port overrun')
                activity.update(sram_read=read,sram_write=write,fifo_operand=fr);counters['mac_occupied']+=1
            if vec[tile] is None:
                for gid in sorted(vr[tile]):
                    if not reserve(gid,tile):continue
                    a=red[gid][tile];g=reductions[gid];count=len(g['children'][tile])+int(tile in g['producers'])
                    if count<1:raise ValueError('Missing contribution')
                    a.update(start=clock,queued=True,read=count*g['bytes'],ops=(count-1)*g['bytes']//4+(g['bytes']//4 if tile==g['root'] else 0),write=g['bytes']//2 if tile==g['root'] else g['bytes']);vec[tile]=gid;vr[tile].remove(gid);break
            if vec[tile] is not None:
                gid=vec[tile];a=red[gid][tile];g=reductions[gid]
                if a['read']:x=min(rb[tile],a['read']);a['read']-=x;rb[tile]-=x;activity['sram_read']+=x
                elif a['ops']:x=min(vb[tile],a['ops']);a['ops']-=x;vb[tile]-=x;activity['vector']+=x
                elif a['write']:x=min(wb[tile],a['write']);a['write']-=x;wb[tile]-=x;activity['sram_write']+=x
                if not a['read'] and not a['ops'] and not a['write']:
                    a.update(complete=True,finish=clock+1);last_vector=clock+1;release_output(gid,tile);vec[tile]=None
                    if record:vector_records.append(dict(group=gid,tile=tile,start=a['start'],finish=a['finish']))
        for node in range(16):
            for attempt in range(10):
                selector=(clock+attempt)%10;port,vc=divmod(selector,2);q=fifo[node][port][vc]
                if port==4 and vc==1 or not q:continue
                f=q[0];kind,gid,index,child=f
                targets=inputs[gid]['children'][node] if kind==0 else []
                need_write=kind==1 or node in inputs[gid]['targets'] and index not in xseen[gid][node]
                if need_write and wb[node]<32:counters['noc_sram_backpressure']+=1;continue
                if any(link_until[node][target]>clock or len(fifo[target][port_for(target,node)][vc])+incoming[target][port_for(target,node)][vc]>=8 for target in targets):counters['noc_link_or_fifo_backpressure']+=1;continue
                if need_write:wb[node]-=32;activity['sram_write']+=32;deliver(f,node)
                for target in targets:send(f,node,target,vc)
                q.popleft();queue_change(node,port,vc,-1)
        for tile in range(16):
            for attempt in range(8):
                if rb[tile]<32:break
                sent=False
                if xp[tile]:
                    gid=min(xp[tile]);g=inputs[gid];q=fifo[tile][4][0]
                    if len(q)+incoming[tile][4][0]<8:
                        f=(0,gid,input_next[gid],tile);rb[tile]-=32;activity['sram_read']+=32;q.append(f);queue_change(tile,4,0,1)
                        if record:inject_records.append(dict(kind=0,group=gid,flit=input_next[gid],tile=tile,tick=clock))
                        input_next[gid]+=1
                        if input_next[gid]==g['bytes']//32:xp[tile].remove(gid)
                        sent=True
                if not sent and op[tile]:
                    for gid in sorted(op[tile]):
                        a=red[gid][tile];g=reductions[gid];parent=g['parent'][tile]
                        if a['finish']>clock or parent<0 or not reserve(gid,parent):continue
                        q=fifo[tile][4][1]
                        if len(q)+incoming[tile][4][1]>=8:break
                        f=(1,gid,a['next_flit'],tile);rb[tile]-=32;activity['sram_read']+=32;q.append(f);queue_change(tile,4,1,1)
                        if record:inject_records.append(dict(kind=1,group=gid,flit=a['next_flit'],tile=tile,tick=clock))
                        a['next_flit']+=1
                        if a['next_flit']==g['bytes']//32:
                            op[tile].remove(gid)
                            if a['slot']:redused[tile]-=a['reserved'];lease_change(tile,'reduce',-a['reserved']);a['slot']=False
                        sent=True;break
                if not sent:break
        for tile in range(16):
            q=fifo[tile][4][1]
            if not q:continue
            f=q[0];target=reductions[f[1]]['parent'][tile];port=port_for(target,tile)
            if link_until[tile][target]<=clock and len(fifo[target][port][1])+incoming[target][port][1]<8:send(f,tile,target,1);q.popleft();queue_change(tile,4,1,-1)
        for tile in range(16):
            bandwidth=500
            while bandwidth and hb[tile]:
                rid=hb[tile][0];r=read_state[rid]
                if r['depart']>clock:break
                transfer=min(bandwidth,1024-r['transferred'])
                if r['hb_first']<0:r['hb_first']=clock
                r['transferred']+=transfer;bandwidth-=transfer;activity['fifo_ingress']+=transfer
                if r['transferred']==1024:r['hb_done']=clock+1;rused[tile]-=1024;lease_change(tile,'response',-1024);hb[tile].popleft()
            if unsent[tile] and rused[tile]+1024<=c['response_buffer']:
                rid=min(unsent[tile]);r=read_state[rid];r['accepted']=clock;accepted+=1;rused[tile]+=1024;lease_change(tile,'response',1024);unsent[tile].remove(rid);rhigh[tile]=max(rhigh[tile],rused[tile])
                fluid_until[tile]=max(fluid_until[tile],float(clock))+1024/(c['fluid_service_tb_s']*1000*.25/16);heappush(fluid_returns,(ceil(fluid_until[tile])+26,rid))
            elif unsent[tile]:counters['response_credit_stall']+=1
            queued=0
            for port in range(5):
                for vc in range(2):
                    used=len(fifo[tile][port][vc])+incoming[tile][port][vc]
                    if used>8:raise ValueError('Router credit overrun')
                    queued+=used
            if min(rb[tile],wb[tile],vb[tile],wused[tile],rused[tile],redused[tile])<0 or wused[tile]>c['weight_buffer'] or rused[tile]>c['response_buffer'] or redused[tile]>c['reduce_buffer'] or c['static_sram_per_tile'][tile]+c['metadata_reserve']+wused[tile]+rused[tile]+redused[tile]>c['sram_per_tile']:raise ValueError('Physical resource overrun')
            if record:port_records.append(dict(tick=clock,tile=tile,read_bytes=256-rb[tile],write_bytes=128-wb[tile],vector_ops=16-vb[tile],weight_used=wused[tile],response_used=rused[tile],reduce_used=redused[tile],router_flits=queued,fifo_ingress_bytes=500-bandwidth,fifo_operand_bytes=fifo_read[tile]))
    else:raise ValueError('Incomplete finite execution')
    clock=max(clock,last_vector)
    if mac_done!=len(tasks) or roots_done!=len(reductions) or accepted!=len(requests) or returned!=accepted or activity['mac']!=c['mac_flops'] or activity['fifo_operand']!=c['dram_bytes'] or any(wused+rused+redused):raise ValueError('Incomplete work or unreleased lease')
    return dict(ticks=clock,time_us=clock*.00025,activity=dict(activity),byte_hops=dict(bytehops),counters=dict(counters),weight_high=max(whigh),response_high=max(rhigh),reduce_high=max(redhigh),tasks=[dict(t,**task_state[t['id']]) for t in tasks],reads=[dict(r,**read_state[r['id']]) for r in requests],inputs=[dict(group=g['id'],tile=t,bytes=g['bytes'],last_tick=xlast[g['id']][t]) for g in inputs for t in g['targets']],ports=port_records,noc=noc_records,injections=inject_records,vectors=vector_records,queue_events=queue_records,lease_events=lease_records,validation='PASS_FINITE_COMPONENT',scope='Independent Python interpreter, same tensor contract and reference arbitration; fixed fluid memory surrogate; not full MoE or independent silicon validation')
