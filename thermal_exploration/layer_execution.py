"""Bounded streaming kernels and complete-layer Decode dependencies.

Architecture assumptions, not a reconstructed Stratum or numerical LLM.
The fast hierarchy preserves resident layout and each operator's work. It
does not model every Ramulator command or flit, nor claim SET/HDA reproduction.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from math import ceil
import numpy as np
from .decode_graph import Graph, execute
from .model_contract import tensors
from .horizontal import route

TICK_NS=.25
BASELINES=('B0_local','B1_dataflow','B2_stream_fusion','B3_3d_placement')
ORACLES=('none','ideal_memory','infinite_noc','ideal_buffer','ideal_collective','direct_producer_stream')


def resident_layout(c, admission, baseline, prior=None, tp=16):
    """Each physical channel/tier has256MiB; no globally pooled fast tier."""
    if tp not in (4,16):raise ValueError('Unsupported static TP/EP layout')
    rows=tensors(c); room=np.full((16,8),256*2**20,dtype=np.int64);layout={}
    def priority(t):
        if t['family']=='embedding':return 0.
        if t['family']=='routed':
            return float(prior[t['layer']][t['expert']]) if prior is not None else c['num_experts_per_tok']/c['num_experts']
        return 1.
    # Optimized layout uses only independent routing prefix frequencies.
    ordered=sorted(rows,key=lambda t:(-priority(t),t['name'])) if baseline=='B3_3d_placement' else rows
    for t in ordered:
        owners=list(range(16))
        if t['family']=='routed' and tp==4:
            group=(t['expert']+t['layer'])%4
            owners=list(range(group*4,group*4+4))
        remaining=ceil(t['bytes']/len(owners)/4096)*4096
        spans={}
        for tile in owners:
            need=remaining;parts=[]
            tier_order=range(8)
            if baseline!='B3_3d_placement':
                # Capacity-striped pages, not all weights magically in tier0.
                for tier in tier_order:
                    take=min(int(room[tile,tier]),ceil(remaining/8/4096)*4096,need)
                    if take:parts.append((tier,take));room[tile,tier]-=take;need-=take
            for tier in tier_order:
                take=min(int(room[tile,tier]),need)
                if take:parts.append((tier,take));room[tile,tier]-=take;need-=take
            if need:raise ValueError('Regional resident capacity exceeded')
            spans[tile]=parts
        layout[t['name']]=spans
    # All-layer KV, buffers and metadata must also fit each region/tier. KV is
    # capacity-striped through the REMAINING physical space, never free fast.
    extra=admission['all_layer_kv_bytes']+admission['dram_workspace_bytes']+admission['metadata_bytes']
    kv_spans={}
    for tile in range(16):
        need=ceil(extra/16/4096)*4096;parts=[]
        for tier in range(8):
            take=min(int(room[tile,tier]),need)
            if take:parts.append((tier,take));room[tile,tier]-=take;need-=take
        if need:raise ValueError('KV/workspace regional capacity exceeded')
        kv_spans[tile]=parts
    return dict(tensors=layout,kv=kv_spans,used_bytes=(256*2**20-room).tolist(),tp=tp,
        regional_tier_capacity_bytes=256*2**20,scope='Page-rounded frozen resident layout; input BF16 weights; KV capacity reserved through step128')


def merge_spans(items):
    result=defaultdict(Counter)
    for spans in items:
        for tile,parts in spans.items():
            for tier,size in parts:result[tile][tier]+=size
    return {tile:tuple(sorted(parts.items())) for tile,parts in result.items()}


@lru_cache(maxsize=8192)
def tile_pipeline(parts,batch,stream,oracle='none',chunk=32768,ports=1.,useful_bytes=None,packet_bytes=1024,keep_events=True):
    """Finite32KiB blocks,64KiB response and512/256KiB weight/FIFO credits.

    MAC operand/accumulator service overlaps MAC arithmetic, unlike old H3.
    Cache-copy bandwidth conservatively reserves MAC's worst write rate.
    A stream FIFO has its own explicitly costed HB ingress; no free SRAM ports.
    Returned-slot reservation is taken BEFORE memory issue and released at HB.
    """
    if chunk>65536 or min(batch,ports)<=0:raise ValueError('Invalid streaming contract')
    mem_free=hb_free=mac_free=0; slots=8 if stream else 16
    if oracle=='ideal_buffer':slots=2**20
    if packet_bytes not in (1024,4096,32768) or packet_bytes>chunk:raise ValueError('Invalid memory packet granularity')
    weights=defaultdict(int);returned=defaultdict(int);return_slots=2**20 if oracle=='ideal_buffer' else 65536//packet_bytes;events=[];index=0;packet_index=0
    total=sum(size for _,size in parts)
    useful=total if useful_bytes is None else useful_bytes
    processed=0
    for tier,size in parts:
        rc=ceil((2.29+20.59*tier/7+27.5+4.77)/TICK_NS)
        rate=min(26.599/16*1000*TICK_NS,16*4096/rc)
        latency=ceil((2.29+20.59*tier/7+4.)/TICK_NS)
        for offset in range(0,size,chunk):
            count=min(chunk,size-offset);weight_slot=index%slots
            if oracle=='ideal_memory':latency=0
            # A32x512 MAC microtile; partials remain registered on the known
            # stream/fusion path. Cache path reads/writes FP32 partial blocks.
            flops=((processed+count)*useful*batch)//total-(processed*useful*batch)//total
            processed+=count
            input_read=min(count,1024*batch)
            partial=0 if stream else 32*batch*4
            read_bytes=input_read+(0 if stream else count)+partial
            write_bytes=partial
            compute=max(1,ceil(flops/2000),ceil(read_bytes/(256*ports)),ceil(write_bytes/(128*ports)))
            reserved_write=write_bytes/compute
            write_rate=128*ports-reserved_write
            if write_rate<=0 and not stream:raise ValueError('No bandwidth remains for memory copies')
            cumulative=0
            for part_offset in range(0,count,packet_bytes):
                part=min(packet_bytes,count-part_offset);return_slot=packet_index%return_slots
                begin=max(mem_free,weights[weight_slot],returned[return_slot])
                duration=ceil((cumulative+part)/rate)-ceil(cumulative/rate);cumulative+=part
                if oracle=='ideal_memory':duration=0
                mem_free=begin+duration;available=mem_free+latency
                events.append(('dram',begin,available,part,tier))
                hb_begin=max(available,hb_free)
                # Fluid sub-tick serialization preserves500B/tick across
                # adjacent1024B returns; rounding EACH packet to3 ticks would
                # manufacture a21.85TB/s HB ceiling. MAC starts on whole ticks.
                hb_duration=part/500 if stream else max(part/500,part/write_rate)
                if oracle=='ideal_memory':hb_duration=0
                hb_end=hb_begin+hb_duration;hb_free=hb_end;returned[return_slot]=hb_end
                events.append(('hb',hb_begin,hb_end,part,tier))
                if not stream:events.append(('sram_write',hb_begin,hb_end,part,tier))
                packet_index+=1
            mac_begin=ceil(max(hb_end,mac_free));mac_end=mac_begin+compute;mac_free=mac_end
            events.append(('mac',mac_begin,mac_end,flops,tier))
            events.append(('sram_read',mac_begin,mac_end,read_bytes,tier))
            if write_bytes:events.append(('sram_write',mac_begin,mac_end,write_bytes,tier))
            weights[weight_slot]=mac_end;index+=1
    if sum(e[3] for e in events if e[0]=='dram')!=total or sum(e[3] for e in events if e[0]=='mac')!=useful*batch:
        raise ValueError('Streaming byte/FLOP conservation')
    activity=dict(Counter({kind:sum(e[3] for e in events if e[0]==kind) for kind in ('dram','hb','mac','sram_read','sram_write')}))
    return dict(ticks=mac_free,events=tuple(events) if keep_events else (),dram_bytes=total,mac_flops=useful*batch,activity=activity,
        dram_last_tick=max(e[2] for e in events if e[0]=='dram'),hb_last_tick=max(e[2] for e in events if e[0]=='hb'),
        memory_packet_bytes=packet_bytes,max_response_bytes=min(packet_index,return_slots)*packet_bytes,max_live_weight_bytes=min(index,slots)*chunk)


@lru_cache(maxsize=2048)
def collective(batch,width,kind,oracle='none'):
    """Known tree multicast/reduction on ordinary tiles, no network compute."""
    g=Graph(256,True)
    if kind=='broadcast':
        outputs=[]
        for source in range(16):
            x=g.broadcast(source,list(range(16)),ceil(batch*width*2/16),stage='broadcast')
            outputs.extend(x.values())
        g.output=outputs
    elif kind=='router':
        local={tile:g.join(()) for tile in range(16)}
        g.output=[g.collective(0,local,batch*width*4,'attention_reduce')]
    elif kind=='route_broadcast':
        g.output=list(g.broadcast(0,list(range(16)),batch*36,stage='broadcast').values())
    elif kind=='scalar':
        local={tile:g.join(()) for tile in range(16)}
        reduced=g.collective(0,local,batch*4,'attention_reduce')
        delivered=g.broadcast(0,list(range(16)),batch*4,(reduced,),'attention_reduce')
        g.output=list(delivered.values())
    else:
        roots=[];local={tile:g.join(()) for tile in range(16)}
        for root in range(16):roots.append(g.collective(root,local,ceil(batch*width*4/16),'attention_reduce'))
        g.output=roots
    mode='infinite_noc' if oracle=='infinite_noc' else 'ideal_collective' if oracle=='ideal_collective' else 'baseline'
    return execute(g,mode)


@lru_cache(maxsize=128)
def kv_gather(update,owner,oracle):
    g=Graph(256,True);g.output=[g.transfer(t,owner,ceil(update/16),(),stage='kv_update') for t in range(16)]
    return execute(g,'infinite_noc' if oracle=='infinite_noc' else 'baseline')


@lru_cache(maxsize=256)
def head_exchange(batch,hq,hkv,dim,context_mod,oracle,query=False):
    g=Graph(256,True);split=16//hkv;ends=[]
    for source in range(16):
        group=source//split
        if query:
            targets=list(range(group*split,(group+1)*split))
            size=batch*hq//16*dim*2
        else:
            targets=[group*split+context_mod%split]
            size=batch*hkv*dim*4//16
        for target in targets:ends.append(g.transfer(source,target,size,(),stage='query' if query else 'kv_update'))
    g.output=ends
    return execute(g,'infinite_noc' if oracle=='infinite_noc' else 'baseline')


@lru_cache(maxsize=128)
def attention_merge(batch,hq,hkv,dim,sequence_only,oracle):
    """Associative online-softmax(m,l,o) state merge, not a plain sum.

    A whole520B state arrives before its nonlinear merge. The link engine can
    split it into256B packets; max/exp/rescaling depend on all state fields.
    """
    g=Graph(256,True);outputs=[];split=16 if sequence_only else 16//hkv
    for token in range(batch):
        for head in range(hq):
            group=0 if sequence_only else head//(hq//hkv)
            leaves=list(range(group*split,(group+1)*split));root=head//(hq//16)
            edges={e for source in leaves for e in route(root,source)}
            children=defaultdict(list)
            for a,b in sorted(edges):children[a].append(b)
            def visit(node):
                arrivals=[g.join(())] if node in leaves else []
                for child in children[node]:
                    state=visit(child);arrival=g.transfer(child,node,(dim+2)*4,(state,),'attention_reduce')
                    arrivals.append(arrival)
                read=g.add('sram_read',node,len(arrivals)*(dim+2)*4,arrivals,('read',node),ceil(len(arrivals)*(dim+2)*4/256),'attention_reduce')
                for arrival in arrivals[1:]:g.lease(arrival,read,('output',node),(dim+2)*4)
                ops=max(0,len(arrivals)-1)*(3*dim+8)
                merge=g.add('vector',node,ops,(read,),('vector',node),ceil(ops/16),'attention_reduce')
                return g.add('sram_write',node,(dim+2)*4,(merge,),('write',node),ceil((dim+2)*4/128),'attention_reduce')
            merged=visit(root)
            normalized=g.add('vector',root,2*dim+1,(merged,),('vector',root),ceil((2*dim+1)/16),'attention_reduce')
            outputs.append(g.add('sram_write',root,dim*2,(normalized,),('write',root),ceil(dim*2/128),'attention_output'))
    g.output=outputs
    mode='infinite_noc' if oracle=='infinite_noc' else 'ideal_collective' if oracle=='ideal_collective' else 'baseline'
    return execute(g,mode)


class LayerExecution:
    def __init__(self,c,admission,layout,baseline,oracle='none'):
        self.c=c;self.a=admission;self.layout=layout;self.baseline=baseline;self.oracle=oracle
        self.events=[];self.clock=0;self.work=Counter();self.stage_times=Counter()
        self.tensor_rows=tensors(c)
        self.tensor_bytes={t['name']:t['bytes'] for t in self.tensor_rows}

    def kernel(self,*args,**kwargs):
        return tile_pipeline(*args,**kwargs)

    def phase(self,name,duration,activity,reason):
        if duration<0:raise ValueError('Negative phase')
        start=self.clock;self.clock+=duration
        self.events.append(dict(stage=name,start_tick=start,finish_tick=self.clock,activity=activity,critical_reason=reason))
        for tile,kinds in activity.items():self.work.update(kinds)
        self.stage_times[reason]+=duration

    def network(self,name,batch,width,kind):
        r=collective(batch,width,kind,self.oracle)
        self.phase(name,r['ticks'],r['per_tile_activity'],'communication/synchronization')

    def linear(self,names,batch,name):
        parts=merge_spans([self.layout['tensors'][n] for n in names]);stream=self.baseline in BASELINES[2:]
        useful=Counter()
        for name_ in names:
            owners=self.layout['tensors'][name_]
            for tile in owners:useful[tile]+=self.tensor_bytes[name_]//len(owners)
        results={tile:self.kernel(spans,batch,stream,self.oracle,useful_bytes=useful[tile],keep_events=False) for tile,spans in parts.items()}
        elapsed=max(r['ticks'] for r in results.values());activity={str(tile):r['activity'] for tile,r in results.items()}
        # Exact event windows are nested in the operator. A macro phase is
        # never interpreted as serial DRAM+HB+MAC times.
        mem=max(r['dram_last_tick'] for r in results.values())
        mac=sum(r['mac_flops'] for r in results.values())/32000
        reason='memory/storage' if mem>=mac else 'compute'
        self.phase(name,elapsed,activity,reason)
        self.events[-1]['tile_kernel_windows']={str(tile):dict(ticks=r['ticks'],dram_last_tick=r['dram_last_tick'],
            hb_last_tick=r['hb_last_tick'],max_response_bytes=r['max_response_bytes'],max_live_weight_bytes=r['max_live_weight_bytes']) for tile,r in results.items()}

        # Final tensor/partial state must actually exist before its next
        # consumer. Internal scratch spills do not substitute for this ledger.
        result_bytes=Counter()
        for n in names:
            last=n.split('.')[-1];owners=self.layout['tensors'][n]
            if n=='lm_head':width=self.c['vocab_size'];column=False
            elif last in ('q','o','down'):width=self.c['hidden_size'];column=last in ('o','down')
            elif last in ('k','v'):width=self.c['num_key_value_heads']*self.c['hidden_size']//self.c['num_attention_heads'];column=False
            elif last in ('router','shared_router'):width=self.c['num_experts'] if last=='router' else 1;column=True
            else:
                width=self.c['moe_intermediate_size'] if '.expert' in n else self.c['shared_expert_intermediate_size'] if '.shared.' in n else self.c['intermediate_size'];column=False
            for t in owners:result_bytes[t]+=batch*width*4 if column else ceil(batch*width*4/len(owners))
        duration=max(ceil(n/128) for n in result_bytes.values())
        if self.oracle=='direct_producer_stream':duration=0
        self.phase(name+'_result_state',duration,{str(t):dict(sram_write=n) for t,n in result_bytes.items()},'vector/local state')

    def vector(self,name,ops,bytes_,batch):
        physical_bytes=0 if self.oracle=='direct_producer_stream' and any(x in name for x in ('silu','residual')) else bytes_
        duration=max(ceil(ops/16/16),ceil(physical_bytes/16/256)+ceil(physical_bytes/16/128))
        activity={str(t):dict(vector=ceil(ops/16),sram_read=ceil(physical_bytes/16),sram_write=ceil(physical_bytes/16)) for t in range(16)}
        self.phase(name,duration,activity,'vector/local state')

    def layer(self,layer,batch,context,routes=None):
        c=self.c;d=c['hidden_size'];hq=c['num_attention_heads'];kv=c['num_key_value_heads'];hd=d//hq;p=f'layer{layer}.'
        small=sum(t['bytes'] for t in self.tensor_rows if t['layer']==layer and t['family'] in ('norm','bias'))
        self.phase(p+'norm_bias_weights',max(ceil(small/(26.599*1000*TICK_NS)),ceil(small/16/128)),
            {str(t):dict(dram=ceil(small/16),hb=ceil(small/16),sram_write=ceil(small/16)) for t in range(16)},'memory/storage')
        self.vector(p+'input_norm_partial_stats',batch*d*3,batch*d*2,batch)
        # RMS statistics use an ordinary scalar tree; traffic is small but its
        # synchronization latency is retained, not silently eliminated.
        self.network(p+'norm_statistics',batch,1,'scalar')
        self.vector(p+'input_norm',batch*d*3,batch*d*2,batch)
        self.network(p+'input_distribution',batch,d,'broadcast')
        self.linear([p+x for x in ('q','k','v')],batch,p+'qkv')
        self.vector(p+'rope',batch*(d+kv*hd)*6,batch*(d+kv*hd)*4,batch)
        sequence_only=self.baseline=='B0_local'
        if sequence_only:self.network(p+'query_distribution',batch,d,'broadcast')
        else:
            exchange=head_exchange(batch,hq,kv,hd,context,self.oracle,True)
            self.phase(p+'head_group_query_distribution',exchange['ticks'],exchange['per_tile_activity'],'communication/synchronization')
        update=batch*kv*hd*4
        # Sequence-striped KV: gather the newly projected K/V shards at the
        # position owner, rather than pretending every region owns this row.
        gathered=kv_gather(update,context%16,self.oracle) if sequence_only else head_exchange(batch,hq,kv,hd,context,self.oracle)
        self.phase(p+'kv_update_delivery',gathered['ticks'],gathered['per_tile_activity'],'communication/synchronization')
        writers=[context%16] if sequence_only else [group*(16//kv)+context%(16//kv) for group in range(kv)]
        local_update=update//len(writers)
        self.phase(p+'kv_update',ceil(local_update/128),{str(t):dict(sram_read=local_update,hb=local_update,dram_write=local_update) for t in writers},'KV update')
        # Complete GQA K/V read and QK/PV work; score matrices never reside in
        # DRAM. The full-model all-layer KV was checked before this call.
        bytes_=batch*(context+1)*kv*hd*4
        parts={};physical_per_tile={}
        useful_per_tile={}
        for tile in range(16):
            resident=self.layout['kv'][tile];total=sum(n for _,n in resident)
            seq_split=16 if sequence_only else 16//kv
            positions=(context+1+seq_split-1-tile%seq_split)//seq_split
            useful_per_tile[tile]=batch*positions*(kv if sequence_only else 1)*hd*4
            per_tile=ceil(useful_per_tile[tile]/4096)*4096;physical_per_tile[tile]=per_tile
            sizes=[(tier,ceil(per_tile*n/total/4096)*4096) for tier,n in resident]
            # Do not allow rounding to invent useful KV bytes/FLOPs.
            excess=sum(n for _,n in sizes)-per_tile
            if excess:sizes[-1]=(sizes[-1][0],sizes[-1][1]-excess)
            parts[tile]=tuple((t,n) for t,n in sizes if n)
        # Query-head reuse factor is hq/kv, separate from batch already in KV.
        r={t:self.kernel(s,hq//kv,self.baseline in BASELINES[2:],self.oracle,useful_bytes=useful_per_tile[t],keep_events=False) for t,s in parts.items()}
        duration=max(x['ticks'] for x in r.values());useful_flops=4*batch*(context+1)*hq*hd
        activity={str(t):dict(dram=physical_per_tile[t],hb=physical_per_tile[t],mac=useful_per_tile[t]*hq//kv,vector=5*batch*((context+1+seq_split-1-t%seq_split)//seq_split)*(hq if sequence_only else hq//kv),
            sram_read=x['activity']['sram_read'],sram_write=x['activity']['sram_write']) for t,x in r.items()}
        # Online softmax has its own16ops/tick tile engine; include its service
        # bound in the streaming phase, not an uncharged extra compute unit.
        vector_time=ceil(5*batch*(context+1)*hq/256)
        reason='vector/local state' if vector_time>duration else 'memory/storage'
        duration=max(duration,vector_time)
        self.phase(p+'split_kv_attention',duration,activity,reason)
        self.events[-1]['useful_kv_bytes']=bytes_;self.events[-1]['physical_kv_bytes']=sum(physical_per_tile.values())
        merged=attention_merge(batch,hq,kv,hd,sequence_only,self.oracle)
        self.phase(p+'attention_merge',merged['ticks'],merged['per_tile_activity'],'communication/synchronization')
        self.linear([p+'o'],batch,p+'o_projection')
        self.network(p+'o_reduce',batch,d,'reduction')
        self.vector(p+'residual_postnorm_partial',batch*d*4,batch*d*4,batch)
        self.network(p+'postnorm_statistics',batch,1,'scalar')
        self.vector(p+'postnorm_scale',batch*d*3,batch*d*2,batch)
        self.network(p+'ffn_input_distribution',batch,d,'broadcast')
        if c['model_type']=='llama':
            if self.baseline=='B0_local':
                self.linear([p+'gate',p+'up'],batch,p+'gate_up')
            else:
                self.linear([p+'gate',p+'up'],batch,p+'paired_gate_up')
            self.vector(p+'silu_multiply',batch*c['intermediate_size']*6,batch*c['intermediate_size']*6,batch)
            if self.baseline=='B0_local':self.network(p+'hidden_redistribution',batch,c['intermediate_size'],'broadcast')
            self.linear([p+'down'],batch,p+'paired_down')
        else:
            if routes is None or len(routes)!=batch or any(len(set(x))!=4 or any(not 0<=e<60 for e in x) for x in routes):
                raise ValueError('Invalid immutable token routing')
            self.linear([p+'router',p+'shared_router'],batch,p+'router')
            self.network(p+'router_scores',batch,61,'router')
            self.phase(p+'topk_shared_sigmoid',ceil(batch*(60*4+5)/16),{'0':dict(vector=batch*(60*4+5),sram_read=batch*61*4,sram_write=batch*36)},'vector/local state')
            self.network(p+'route_weights_distribution',batch,1,'route_broadcast')
            if not getattr(self,'resident_expert_input',False):
                self.network(p+'dispatch',batch,d,'broadcast')
            # Active expert matrices are read once per token microbatch. Every
            # unselected expert remains resident but is not falsely charged as
            # a per-step read. Shared MLP is always active, with3 projections.
            counts=Counter(e for row in routes for e in row)
            expert_groups=defaultdict(list)
            for e,count in sorted(counts.items()):expert_groups[count].extend(p+f'expert{e}.'+x for x in ('gate','up','down'))
            if getattr(self,'incremental_combine',False):self.initialize_combine(p,batch)
            # gate/up -> SiLU -> down dependencies are preserved per expert;
            # combine one count cohort's three stages, never one unconstrained
            # fused3-matrix multiply. Separate cohorts serialize conservatively.
            groups=list(expert_groups.items())
            if hasattr(self,'bounded_expert_cohorts'):groups=self.bounded_expert_cohorts(groups,batch)
            for count,names in groups:
                self.linear([n for n in names if not n.endswith('.down')],count,p+'routed_gate_up')
                self.vector(p+'routed_silu',count*(len(names)//3)*c['moe_intermediate_size']*6,count*(len(names)//3)*c['moe_intermediate_size']*6,batch)
                self.linear([n for n in names if n.endswith('.down')],count,p+'routed_down')
                if getattr(self,'incremental_combine',False):
                    self.accumulate_expert_partials(p,count,names,batch)
            self.linear([p+'shared.gate',p+'shared.up'],batch,p+'shared_gate_up')
            self.vector(p+'shared_silu',batch*c['shared_expert_intermediate_size']*6,batch*c['shared_expert_intermediate_size']*6,batch)
            self.linear([p+'shared.down'],batch,p+'shared_down')
            if getattr(self,'incremental_combine',False):
                self.accumulate_expert_partials(p,batch,[p+'shared.down'],batch)
            # Weight and add each tile's FP32 partial BEFORE the one final
            # collective. This multiplies vector work by TP width; no free
            # network-side weighting or reduction is being assumed.
            partial_counts=Counter({tile:batch for tile in range(16)})
            for expert,count in counts.items():
                for tile in self.layout['tensors'][p+f'expert{expert}.down']:partial_counts[tile]+=count
            activity={str(tile):dict(vector=d*(2*n-batch),sram_read=d*4*n,sram_write=d*4*batch) for tile,n in partial_counts.items()}
            if not getattr(self,'incremental_combine',False):
                if max(d*4*n for n in partial_counts.values())>getattr(self,'expert_workspace_bytes',1048576):raise ValueError('Expert partials exceed workspace; microbatch required')
                duration=max(max(ceil(v['vector']/16),ceil(v['sram_read']/256)+ceil(v['sram_write']/128)) for v in activity.values())
                self.phase(p+'local_weighted_partial_combine',duration,activity,'vector/local state')
        self.network(p+'output_reduce',batch,d,'reduction')
        self.vector(p+'residual',batch*d,batch*d*6,batch)

    def token(self,batch,context,routes=None):
        c=self.c;d=c['hidden_size']
        # Exactly the selected embedding rows, not the whole vocabulary.
        self.phase('embedding_lookup',ceil(batch*d*2/(26.599*1000*TICK_NS)),
            {str(t):dict(dram=ceil(batch*d*2/16),hb=ceil(batch*d*2/16)) for t in range(16)},'memory/storage')
        for layer in range(c['num_hidden_layers']):self.layer(layer,batch,context,None if routes is None else routes[layer])
        self.vector('final_norm_partial_stats',batch*d*3,batch*d*2,batch)
        self.network('final_norm_statistics',batch,1,'scalar')
        self.vector('final_norm',batch*d*3,batch*d*2,batch)
        self.network('lm_head_input_distribution',batch,d,'broadcast')
        self.linear(['lm_head'],batch,'lm_head')
        self.vector('logit_selection',batch*c['vocab_size']*2,batch*c['vocab_size']*4,batch)
        self.network('next_token_sampling',batch,16,'reduction')
        if sum(self.stage_times.values())!=self.clock:raise ValueError('Critical macro path does not close')
        return dict(ticks=self.clock,time_us=self.clock*.00025,activity=dict(self.work),events=self.events,
            critical_path_ticks=dict(self.stage_times),capacity=self.a,baseline=self.baseline,oracle=self.oracle,
            scope='Full-layer BF16 structural Decode, bounded streaming kernel + packet collectives; chosen hierarchical schedule, no numeric inference or globally optimal scheduling')
