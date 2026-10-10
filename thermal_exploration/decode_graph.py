"""H3 finite-resource packet DAG screening, explicitly below H2 fidelity.

Memory uses a tier row-cycle service abstraction, not a new command simulator.
All compute stays on logic. Traces are shape/probability generated, not model
captures. This module cannot establish calibrated token/s or hardware novelty.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import heapq
from math import ceil
import numpy as np
from .horizontal import route


@dataclass
class Node:
    id: int
    kind: str
    tile: int
    work: int
    deps: tuple
    resource: tuple
    ticks: int
    stage: str
    tier: int = -1
    leases: list = field(default_factory=list)


class Graph:
    def __init__(self):
        self.nodes=[];self.meta={};self.output=[]

    def add(self,kind,tile,work,deps=(),resource=None,ticks=0,stage='',tier=-1):
        id=len(self.nodes)
        if any(d>=id or d<0 for d in deps):raise ValueError('Noncausal graph')
        if work<0 or ticks<0:raise ValueError('Negative service')
        resource=resource or (kind,tile)
        self.nodes.append(Node(id,kind,tile,work,tuple(sorted(set(deps))),resource,ticks,stage,tier))
        return id

    def join(self,deps,stage='join'):
        return self.add('join',0,0,deps,('join',len(self.nodes)),0,stage)

    def lease(self,first,last,key,bytes_):
        if last<first or bytes_<0:raise ValueError('Invalid buffer lifetime')
        self.nodes[first].leases.append((key,bytes_,last))

    def memory_compute(self,tile,bytes_,flops,deps=(),parent=None,tier=0,vec_ops=0,stage='weight',stream=False,memory_deps=()):
        # One chunk must fit the 64KiB return/FIFO credit. Half full-row reads
        # still pay an ACT in the service abstraction, no timing oracle here.
        if not 0<bytes_<=65536:raise ValueError('Memory chunk exceeds return capacity')
        rc=ceil((2.29+(22.88-2.29)*tier/7+27.5+4.77)/.25)
        # Fixed bank/ACT-domain/column resources. D1's observed 26.599TB/s
        # is a guard on the fastest streaming service, not a device calibration.
        service=min(26.599/16*1000*.25,16*4096/rc)
        pieces=[];ready=list(deps)
        # Independently returned32KiB packets can overlap stages; a64KiB
        # compute block does not force an artificial single-flight return.
        for offset in range(0,bytes_,32768):
            size=min(32768,bytes_-offset)
            mem=self.add('dram',tile,size,memory_deps,('dram',tile),max(1,ceil(size/service)),'memory',tier)
            hb=self.add('hb',tile,size,(mem,),ticks=ceil(size/500),stage='memory',tier=tier)
            write=hb if stream else self.add('sram_write',tile,size,(hb,),('write',tile),ceil(size/128),'memory',tier)
            pieces.append((mem,write,size));ready.append(write)
        if parent is not None:ready.append(parent)
        read_bytes=0 if stream else bytes_
        # Input/partial accesses remain charged even on the known FIFO path.
        read_bytes+=2048
        read=self.add('sram_read',tile,read_bytes,ready,('read',tile),ceil(read_bytes/256),stage,tier)
        mac=self.add('mac',tile,flops,(read,),('mac',tile),max(1,ceil(flops/2000)),stage,tier)
        end=mac
        if vec_ops:end=self.add('vector',tile,vec_ops,(mac,),('vector',tile),ceil(vec_ops/16),stage,tier)
        end=self.add('sram_write',tile,2048,(end,),('write',tile),16,stage,tier)
        for mem,write,size in pieces:
            self.lease(mem,write,('return',tile),size)
            self.lease(mem,mac if stream else read,('weight_fifo' if stream else 'weight',tile),size)
        return end

    def transfer(self,source,target,bytes_,deps,stage='communication'):
        if source==target:return self.join(deps,stage)
        packets=[]
        for offset in range(0,bytes_,4096):
            size=min(4096,bytes_-offset)
            first=self.add('sram_read',source,size,deps,('read',source),ceil(size/256),stage)
            end=first;links=[]
            for a,b in route(source,target):
                link=self.add('link',a,size,(end,),('link',a,b),ceil(size/8)+8,stage)
                links.append((link,b));end=link
            end=self.add('sram_write',target,size,(end,),('write',target),ceil(size/128),stage)
            self.lease(first,links[0][0],('transmit',source),size)
            for index,(link,node) in enumerate(links):
                previous=self.nodes[link].resource[1]
                direction=0 if previous==node-1 else 1 if previous==node+1 else 2 if previous==node-4 else 3
                self.lease(link,links[index+1][0] if index+1<len(links) else end,('router'+str(direction),node),size)
            self.lease(first,end,('receive',target),size);packets.append(end)
        return self.join(packets,stage)

    def broadcast(self,source,targets,bytes_,deps=(),stage='input'):
        """Known XY multicast: one shared prefix, not16 duplicate unicasts."""
        edges={e for target in targets for e in route(source,target)}
        children=defaultdict(list)
        for a,b in sorted(edges):children[a].append(b)
        output=defaultdict(list)
        for offset in range(0,bytes_,4096):
            size=min(4096,bytes_-offset)
            read=self.add('sram_read',source,size,deps,('read',source),ceil(size/256),stage)
            def visit(node,before):
                local=[]
                if node in targets and node!=source:
                    write=self.add('sram_write',node,size,(before,),('write',node),ceil(size/128),stage)
                    self.lease(read,write,('receive',node),size);output[node].append(write);local.append(write)
                for target in children[node]:
                    link=self.add('link',node,size,(before,),('link',node,target),ceil(size/8)+8,stage)
                    local.append(link);last=visit(target,link)
                    direction=0 if node==target-1 else 1 if node==target+1 else 2 if node==target-4 else 3
                    self.lease(link,last,('router'+str(direction),target),size)
                return self.join(local or (before,),stage)
            rootlast=visit(source,read);self.lease(read,rootlast,('transmit',source),size)
        result={t:self.join(output[t],stage) for t in targets if t!=source}
        if source in targets:result[source]=self.join(deps,stage)
        return result

    def collective(self,root,producers,bytes_,stage='ffn_reduce'):
        """FP32 tree partials, ordinary tile vectors and same SRAM/links."""
        edges={e for source in producers for e in route(root,source)};children=defaultdict(list)
        for a,b in sorted(edges):children[a].append(b)
        outputs=[]
        for offset in range(0,bytes_,4096):
            size=min(4096,bytes_-offset)
            def visit(node):
                contributions=[];incoming=[]
                if node in producers:contributions.append(producers[node])
                for child in children[node]:
                    partial=visit(child)
                    read=self.add('sram_read',child,size,(partial,),('read',child),ceil(size/256),stage)
                    self.lease(partial,read,('output',child),size)
                    link=self.add('link',child,size,(read,),('link',child,node),ceil(size/8)+8,stage)
                    write=self.add('sram_write',node,size,(link,),('write',node),ceil(size/128),stage)
                    self.lease(read,link,('transmit',child),size);self.lease(link,write,('receive',node),size)
                    contributions.append(write);incoming.append(link)
                read=self.add('sram_read',node,size*len(contributions),contributions,('read',node),ceil(size*len(contributions)/256),stage)
                for link in incoming:self.lease(link,read,('output',node),size)
                ops=(len(contributions)-1)*size//4
                vector=self.add('vector',node,ops,(read,),('vector',node),ceil(ops/16),stage)
                return self.add('sram_write',node,size,(vector,),('write',node),ceil(size/128),stage)
            outputs.append(visit(root))
        return self.join(outputs,stage)


def execute(g,mode='baseline',sram_scale=1.,link_scale=1.,energy_scale=1.):
    """Events serialize shared resources and reserve finite bytes until use.

    The selected parent chain includes dependencies, resource predecessors and
    credit releases. Link packets use store-and-forward, not H2 flit routers.
    """
    valid={'baseline','ideal_memory','infinite_noc','ideal_buffer','direct_stream','ideal_collective','known_fusion'}
    if mode not in valid:raise ValueError(mode)
    n=len(g.nodes);children=[[] for _ in range(n)];remaining=[]
    for node in g.nodes:
        remaining.append(len(node.deps))
        for dep in node.deps:children[dep].append(node.id)
    queues=defaultdict(list);events=[];busy={};used=Counter();private_used=Counter();high=Counter();owners=defaultdict(set)
    release=defaultdict(list);last_release={};done=np.full(n,-1,dtype=np.int64);start=done.copy();parents=[None]*n
    wait=Counter();last_resource={};clock=0;completed=0;activity=Counter();per_tile=defaultdict(Counter)
    caps={'weight':524288,'weight_fifo':262144,'return':65536,'receive':65536,'workspace':1048576,
          'router0':4096,'router1':4096,'router2':4096,'router3':4096,'transmit':65536,'output':262144}
    def cap(key):return 2**50 if mode=='ideal_buffer' else caps[key[0]]
    priority={'join':0,'sram_write':1,'sram_read':2,'vector':3,'mac':4,'link':5,'hb':6,'dram':7}
    def enqueue(i):heapq.heappush(queues[g.nodes[i].resource],(priority[g.nodes[i].kind],i))
    for node in g.nodes:
        if not node.deps:enqueue(node.id)
    resource_order=sorted(queues,key=str)
    records=[]
    while completed<n:
        while events and events[0][0]<=clock:
            time,i=heapq.heappop(events);done[i]=time;completed+=1
            for key,amount,owner in release.pop(i,[]):
                used[key]-=amount;private_used[key[1]]-=amount;owners[key].remove(owner);last_release[key]=(i,time)
            for child in children[i]:
                remaining[child]-=1
                if remaining[child]==0:enqueue(child)
        progress=True
        while progress:
            progress=False
            # A fixed drain-first policy is common to every counterfactual.
            for key in sorted(queues,key=lambda k:(priority[g.nodes[queues[k][0][1]].kind] if queues[k] else 99,str(k))):
                if not queues[key] or busy.get(key,0)>clock:continue
                _,i=queues[key][0];node=g.nodes[i]
                if any(used[k]+a>cap(k) for k,a,_ in node.leases):
                    wait[node.kind+'_credit']+=1;continue
                heapq.heappop(queues[key]);start[i]=clock;progress=True
                candidates=[(int(done[j]),j,'dependency') for j in node.deps]
                if key in last_resource:candidates.append((busy[key],last_resource[key],'resource'))
                for k,_,_ in node.leases:
                    if k in last_release:candidates.append((last_release[k][1],last_release[k][0],'buffer_credit'))
                candidates=[x for x in candidates if x[0]<=clock]
                latest=max(candidates,default=(0,-1,'origin'))
                parents[i]=latest
                duration=node.ticks
                if node.kind in ('sram_read','sram_write'):duration=max(1,ceil(duration/sram_scale))
                if node.kind=='link':duration=max(1,ceil(duration/link_scale))
                if mode=='ideal_memory' and node.kind in ('dram','hb'):duration=0
                if mode=='infinite_noc' and node.kind=='link':duration=0
                if mode=='ideal_collective' and node.stage in ('combine','attention_reduce','ffn_reduce') and node.kind=='link':duration=0
                if mode in ('direct_stream','known_fusion') and node.stage in ('up','down','expert_up','expert_down','attention_local'):
                    # Existing fused kernels/registered accumulators avoid a
                    # forced2KiB spill/reload on each local block. Dependencies
                    # and finite operand FIFO remain unchanged. Activity stays
                    # in the ledger: this is a timing-only isolation experiment.
                    if node.kind=='sram_write':duration=0
                    if node.kind=='sram_read':duration=max(0,duration-ceil(2048/256/sram_scale))
                # Direct streaming is a separate graph with a bounded FIFO;
                # it is not implemented by secretly dropping compute work.
                finish=clock+duration;busy[key]=finish;last_resource[key]=i
                for k,a,last in node.leases:
                    used[k]+=a;private_used[k[1]]+=a;high[k]=max(high[k],used[k]);owners[k].add(i);release[last].append((k,a,i))
                if mode!='ideal_buffer' and max(private_used.values(),default=0)+262144>2359296:
                    raise ValueError('Combined private SRAM budget exceeded')
                heapq.heappush(events,(finish,i))
                activity[node.kind]+=node.work;per_tile[node.tile][node.kind]+=node.work
                if duration==0:break
            if events and events[0][0]<=clock:break
        if events:clock=events[0][0]
        elif completed<n:raise ValueError('Deadlock: finite credits/dependencies cannot progress')
    if np.any(done<start) or any(done[d]>start[node.id] for node in g.nodes for d in node.deps) or any(used.values()):
        raise ValueError('Noncausal execution or unreleased buffer')
    # Independent per-resource overlap replay, also applied to zero-time oracles.
    intervals=defaultdict(list)
    for node in g.nodes:intervals[node.resource].append((int(start[node.id]),int(done[node.id]),node.id))
    for values in intervals.values():
        ordered=sorted(values)
        if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):raise ValueError('Shared resource overcommitted')
    end=max(g.output,key=lambda i:done[i]);path=[];seen=set();frontier=end
    while frontier>=0:
        if frontier in seen:raise ValueError('Critical parent cycle')
        seen.add(frontier);node=g.nodes[frontier];before,parent,cause=parents[frontier]
        # The parent selection describes this scheduler, not all schedules.
        path.append(dict(id=frontier,kind=node.kind,stage=node.stage,tile=node.tile,start_tick=int(start[frontier]),
            finish_tick=int(done[frontier]),cause=cause,unattributed_gap_ticks=int(start[frontier]-before)))
        frontier=parent
    for node in g.nodes:
        before,parent,cause=parents[node.id]
        records.append(dict(id=node.id,kind=node.kind,stage=node.stage,tile=node.tile,tier=node.tier,work=node.work,
            start_tick=int(start[node.id]),finish_tick=int(done[node.id]),parent=parent,cause=cause))
    return dict(mode=mode,ticks=int(done[end]),time_us=float(done[end])*.00025,activity=dict(activity),
        per_tile_activity={str(k):dict(v) for k,v in per_tile.items()},buffer_high={str(k):v for k,v in high.items()},
        credit_stall_probes=dict(wait),critical_path=list(reversed(path)),events=records,
        critical_path_scope='Resource/dependency/credit chain for the fixed packet scheduler; not an optimal-schedule lower bound',
        validation='PASS: dependency joins, resource nonoverlap, finite buffer lifetimes and work conservation',
        fidelity='Packet DAG; tier row-cycle service bounds, not Ramulator commands; no numerical LLM outputs')


def ffn(batch=1,stream=False):
    g=Graph();d,h=1024,4096;hidden=[]
    shared=[g.broadcast(source,list(range(16)),d//16*batch*2,(),'input') for source in range(16)]
    # Megatron paired output/input split; no intermediate all-gather.
    for tile in range(16):
        inputs=[mapping[tile] for mapping in shared]
        prev=None
        for _ in range(8):prev=g.memory_compute(tile,65536,65536*batch,inputs,prev,stage='up',stream=stream)
        act=g.add('vector',tile,h//16*batch*5,(prev,),('vector',tile),ceil(h//16*batch*5/16),'gelu');hidden.append(act)
    down=[]
    for tile in range(16):
        prev=None
        for _ in range(8):prev=g.memory_compute(tile,65536,65536*batch,(hidden[tile],),prev,stage='down',stream=stream)
        down.append(prev)
    outputs=[]
    for root in range(16):
        outputs.append(g.collective(root,dict(enumerate(down)),d//16*batch*4,'ffn_reduce'))
    g.output=outputs;g.meta=dict(family='FFN',batch=batch,d=d,h=h,weight_bytes=16*2*8*65536,
        mac_flops=4*d*h*batch,baseline='Megatron paired output/input split; shard-local GELU',tokens=batch)
    return g


def attention(batch=1,context=8192,stream=False):
    g=Graph();hq,hkv,dim=32,8,128;pieces=[]
    kv_bytes=batch*context*hkv*dim*4
    # Fixed resident layout puts the first4GiB in fast tier; excess is evenly
    # capacity-striped over seven slower tiers. No free per-token migration.
    fast_fraction=min(1.,4*2**30/kv_bytes)
    for tile in range(16):
        roots=tile//2;last=None
        for b in range(batch):
            for chunk in range(context//256):
                ordinal=(b*(context//256)+chunk)*16+tile
                total=batch*(context//256)*16
                fraction=(ordinal+.5)/total
                tier=0 if fraction<fast_fraction else min(7,1+int((fraction-fast_fraction)/max(1e-9,1-fast_fraction)*7))
                # 256 sequence positions: K+V=128KiB per KV head. Each tile
                # gets half:128 positions/64KiB; four query heads reuse it.
                last=g.memory_compute(tile,65536,4*4*128*dim,(),last,tier,
                    5*4*128+4*(dim+2),'attention_local',stream)
        pieces.append(last)
    outputs=[]
    for group in range(8):
        root=group*2;bytes_=batch*4*(dim+2)*4
        arrival=g.transfer(root+1,root,bytes_,(pieces[root+1],),'attention_reduce')
        ops=batch*4*(dim*3+6)
        merge=g.add('vector',root,ops,(pieces[root],arrival),('vector',root),ceil(ops/16),'attention_reduce')
        # Canonical output owners split the four query heads across two tiles.
        for owner in (root,root+1):
            delivery=g.transfer(root,owner,batch*2*dim*2,(merge,),'output')
            # A following local projection consumes the actual returned shard.
            outputs.append(g.add('mac',owner,2*batch*2*dim*128,(delivery,),('mac',owner),ceil(2*batch*2*dim*128/2000),'next_operator'))
    g.output=outputs;g.meta=dict(family='Attention',batch=batch,context=context,query_heads=hq,kv_heads=hkv,head_dim=dim,
        weight_bytes=kv_bytes,mac_flops=4*batch*context*hq*dim+2*batch*4096*128,
        baseline='Online softmax plus split-KV; merge max/logsumexp/output, no score-matrix materialization',tokens=batch,
        resident_kv_bytes=kv_bytes,fast_capacity_bytes=4*2**30)
    return g


def moe(batch=32,skew=1.2,seed=20261010,stream=False,tensor_parts=4):
    g=Graph();experts=80;d,h=2048,8192;topk=2
    if tensor_parts not in (1,4,16):raise ValueError('Unknown EP/TP combination')
    rng=np.random.default_rng(seed);prob=np.arange(1,experts+1,dtype=float)**(-skew);prob/=prob.sum()
    routing=[rng.choice(experts,topk,replace=False,p=prob).tolist() for _ in range(batch)]
    counts=Counter(e for selected in routing for e in selected);expert_finish={};physical_weight_bytes=0;groups=[]
    resident=experts*4*d*h;slots=4*2**30//(4*d*h)
    # Known expected popularity, not the future sampled route, determines
    # static fast-tier placement and an offline load-balanced expert assignment.
    clusters=16//tensor_parts;loads=[0.]*clusters;owner={};resident_count=[0]*clusters
    for e in range(experts):
        cluster=min((c for c in range(clusters) if resident_count[c]<experts//clusters),key=lambda t:(loads[t],t))
        owner[e]=list(range(cluster*tensor_parts,(cluster+1)*tensor_parts));loads[cluster]+=prob[e];resident_count[cluster]+=1
    # Fast capacity is256MiB in EACH physical channel region, not a freely
    # pooled4GiB. Static placement must respect local tier capacities.
    expert_tiers={};tier_count=[0]*clusters
    for e in range(experts):
        cluster=owner[e][0]//tensor_parts;local_rank=tier_count[cluster];tier_count[cluster]+=1
        local_fast=slots//clusters
        expert_tiers[e]=0 if local_rank<local_fast else min(7,1+(local_rank-local_fast)//max(1,local_fast))
    dispatched=[g.broadcast(t%16,sorted({tile for e in es for tile in owner[e]}),d*2,(),'dispatch') for t,es in enumerate(routing)]
    for e,count in sorted(counts.items(),key=lambda z:(-prob[z[0]],z[0])):
        tier=expert_tiers[e]
        tokens=[t for t,es in enumerate(routing) if e in es]
        # Known token batching keeps private intermediate SRAM finite. Weight
        # re-reads for additional microbatches are charged, not free reuse.
        for begin in range(0,count,16):
            selected=tokens[begin:begin+16];local_count=len(selected)
            partials={}
            for tile in owner[e]:
                dispatch=[dispatched[t][tile] for t in selected]
                entry=g.join((),'expert_workspace');prev=None
                for layer in range(2):
                    for chunk in range(512//tensor_parts):
                        prev=g.memory_compute(tile,65536,65536*local_count,(*dispatch,entry),prev,tier,
                            h//tensor_parts*local_count*5 if layer==0 and chunk==512//tensor_parts-1 else 0,'expert_up' if layer==0 else 'expert_down',stream,(entry,))
                g.lease(entry,prev,('workspace',tile),local_count*(d*2+h//tensor_parts*4+d*4))
                partials[tile]=prev;groups.append((prev,tile,selected))
            physical_weight_bytes+=4*d*h
            for token in selected:expert_finish[token,e]=partials
    outputs=[]
    for token,es in enumerate(routing):
        root=token%16
        arrivals=[g.collective(root,expert_finish[token,e],d*4,'combine') for e in es]
        merge=g.add('vector',root,d*3,arrivals,('vector',root),ceil(d*3/16),'combine')
        outputs.append(g.add('mac',root,2*d*128,(merge,),('mac',root),ceil(2*d*128/2000),'next_operator'))
    for finish,tile,selected in groups:
        retired=g.join([outputs[token] for token in selected],'output_retirement')
        g.lease(finish,retired,('output',tile),len(selected)*d*4)
    active_bytes=len(counts)*4*d*h
    g.output=outputs;g.meta=dict(family='MoE',batch=batch,experts=experts,d=d,h=h,topk=topk,seed=seed,skew=skew,
        routing=routing,expert_counts=dict(counts),expert_owners=owner,expert_tiers=expert_tiers,tensor_parts=tensor_parts,
        weight_bytes=physical_weight_bytes,unique_active_weight_bytes=active_bytes,
        resident_weight_bytes=resident,fast_capacity_bytes=4*2**30,mac_flops=4*d*h*batch*topk+2*d*128*batch,
        tokens=batch,baseline='Static popularity placement/load-balanced ownership; expert weight reuse, asynchronous dispatch and expert-granular combine',
        routing_evidence='Assumed weighted-without-replacement probability trace, not an observed model route')
    return g
