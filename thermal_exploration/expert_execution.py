"""Known row-blocked accumulation and physically owned expert execution.

Architecture exploration, not new hardware or an independently calibrated
Mono3D device. Unknown current domains remain explicit in the service model.
"""
from collections import Counter
from math import ceil
from .crossover_execution import CrossoverExecution,pipeline,RCD_NS
from .layer_execution import merge_spans


def slice_spans(parts,first,last,total):
    """Disjoint byte intervals; padding is neither dropped nor read twice."""
    size=sum(n for _,n in parts);lo=size*first//total;hi=size*last//total
    result=[];offset=0
    for tier,n in parts:
        take=max(0,min(hi,offset+n)-max(lo,offset))
        if take:result.append((tier,take))
        offset+=n
    return tuple(result)


class RowBlockedExecution(CrossoverExecution):
    """Software row blocking: one token accumulator + one output row cohort.

    No full expert output is formed before its row is weighted/accumulated.
    Gate/up state stays within the already reserved activation storage. All
    down weights are read once and every FP32 result store/read is charged.
    Row cohorts serialize conservatively; no oracle network or free overlap.
    """
    row_block=64
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.incremental_combine=True;self.row_ledger=[];self.combined_down=False

    def bounded_expert_cohorts(self,groups,batch):
        # Reuse the reserved gated-state allocation, never keep arbitrary
        # numbers of expert intermediates. Grouped GEMM remains permitted.
        result=[]
        available=self.expert_workspace_bytes-batch*self.c['hidden_size']*4
        gated=batch*8*ceil(self.c['shared_expert_intermediate_size']/16)
        for count,names in groups:
            maximum=min(available//(count*self.row_block*4),gated//(count*8*ceil(self.c['moe_intermediate_size']/16)))
            if maximum<1:raise ValueError('One row/gated expert cohort cannot fit')
            for offset in range(0,len(names),3*maximum):result.append((count,names[offset:offset+3*maximum]))
        return result

    def linear(self,names,batch,name):
        if not all(n.endswith('.down') and ('.expert' in n or '.shared.' in n) for n in names):
            return super().linear(names,batch,name)
        d=self.c['hidden_size'];global_batch=self.a['batch']
        parts=merge_spans([self.layout['tensors'][n] for n in names]);counts=Counter();useful=Counter()
        for n in names:
            owners=self.layout['tensors'][n]
            for tile in owners:counts[tile]+=batch;useful[tile]+=self.tensor_bytes[n]//len(owners)
        accumulator=global_batch*d*4
        for row in range(0,d,self.row_block):
            rows=min(self.row_block,d-row)
            live=max(accumulator+rows*4*count for count in counts.values())
            if live>self.expert_workspace_bytes:raise ValueError('One row block + accumulator exceed workspace')
            kernels={tile:pipeline(slice_spans(spans,row,row+rows,d),batch,self.profile,
                useful_bytes=useful[tile]*(row+rows)//d-useful[tile]*row//d) for tile,spans in parts.items()}
            self.phase(name+'_rows',max(k['ticks'] for k in kernels.values()),
                {str(t):k['activity'] for t,k in kernels.items()},'memory/storage')
            self.events[-1]['row_interval']=[row,row+rows]
            # Ordinary SRAM/vector units, no arithmetic in the network.
            activity={str(t):dict(vector=2*rows*count,
                sram_write=rows*4*(count+global_batch),
                sram_read=rows*4*(count+global_batch)) for t,count in counts.items()}
            duration=max(max(ceil(a['vector']/16),ceil(a['sram_read']/256)+ceil(a['sram_write']/128)) for a in activity.values())
            self.phase(name+'_row_weighted_accumulate',duration,activity,'vector/local state')
            self.events[-1].update(row_interval=[row,row+rows],live_expert_workspace_bytes=live)
            self.row_ledger.append(dict(stage=name,first_row=row,last_row=row+rows,
                live_bytes=live,workspace_bytes=self.expert_workspace_bytes,
                weight_bytes=sum(k['dram_bytes'] for k in kernels.values()),mac_flops=sum(k['mac_flops'] for k in kernels.values())))
        self.combined_down=True

    def accumulate_expert_partials(self,*args):
        if not self.combined_down:raise ValueError('Down output did not enter row accumulator')
        self.combined_down=False

    def token(self,*args,**kwargs):
        r=super().token(*args,**kwargs);r['row_block_ledger']=self.row_ledger
        r['scope']+='; known64-row expert accumulation, bounded gated-state cohorts'
        return r


def expert_graph(c,layout,layer,routes,profile,schedule='overlap',order='dynamic',isolation='none',down_partition='column',combine_scheme='fused'):
    """Conventional TP/EP, packed dispatch, paired SwiGLU and row reductions.

    A joint local kernel uses the existing finite streaming service model.
    It reserves its tile's MAC/DRAM/HB while running (conservative inter-expert
    serialization). In overlap mode SRAM reads are split128+128B/tick between
    MAC and packets; the ordinary128B write port remains serialized. This is
    not FlashMoE/HDA reproduction or a proof of globally optimal scheduling.
    """
    from dataclasses import replace
    from .decode_graph import Graph
    if schedule not in ('barrier','overlap') or order not in ('static','dynamic'):
        raise ValueError('Unknown conventional expert schedule')
    if down_partition not in ('row','column'):raise ValueError('Unknown frozen down layout')
    if combine_scheme not in ('fused','eager'):raise ValueError('Unknown known combine schedule')
    if not profile.area()['area_feasible']:raise ValueError('Paid area infeasible')
    b=len(routes);d=c['hidden_size'];h=c['moe_intermediate_size'];hs=c['shared_expert_intermediate_size']
    if any(len(r)!=c['num_experts_per_tok'] or len(set(r))!=len(r) or any(not 0<=e<c['num_experts'] for e in r) for r in routes):
        raise ValueError('Invalid captured expert selection')
    counts=Counter(e for row in routes for e in row);budget=profile.budget(b,d,hs)
    if not budget['feasible']:raise ValueError('Fixed SRAM budget infeasible')
    p=replace(profile,isolation=isolation if isolation!='none' else profile.isolation)
    g=Graph(256,True);g.meta['coupled_resources']={};jobs=[];ledger=[]
    experts=list(counts)
    if order=='static':experts.sort()
    else:experts.sort(key=lambda e:(-counts[e]/len(layout['tensors'][f'layer{layer}.expert{e}.up']),e))
    descriptors=[(f'layer{layer}.expert{e}',[t for t,row in enumerate(routes) if e in row],h,e) for e in experts]
    descriptors.append((f'layer{layer}.shared',list(range(b)),hs,'shared'))
    # The shared expert already needs every token on all16 tiles. Reuse this
    # one legal input distribution instead of resending it once per expert.
    common={t:[] for t in range(16)}
    for source in range(16):
        distributed=g.broadcast(source,list(range(16)),b*d*2//16,stage='dispatch')
        for tile in range(16):common[tile].append(distributed[tile])
    common_ready={t:g.join(deps,'resident_token_input') for t,deps in common.items()}
    dispatches=[]
    for prefix,tokens,width,expert in descriptors:
        owners=sorted(layout['tensors'][prefix+'.up']);count=len(tokens)
        dispatch={t:common_ready[t] for t in owners}
        dispatches.extend(dispatch.values())
        jobs.append(dict(prefix=prefix,tokens=tokens,count=count,width=width,expert=expert,owners=owners,dispatch=dispatch))
    barrier=g.join(dispatches,'dispatch_barrier') if schedule=='barrier' else None
    terminals=[];stage_done=[];token_rows={}
    accumulator_init={tile:g.add('sram_write',tile,b*d*4,resource=('write',tile),ticks=ceil(b*d*4/128),stage='token_accumulator_init') for tile in range(16)} if combine_scheme=='fused' else {}
    def kernel(tile,spans,count,useful,deps,stage,memory_deps=()):
        # Bounded known prefetch. Identity is already known at time zero;
        # arithmetic never precedes both input and actual prefix arrival.
        pre=[];lead=0;prefix=min(sum(n for _,n in spans),262144) if schedule=='overlap' else 0
        if prefix:
            left=prefix
            for tier,size in spans:
                for offset in range(0,min(size,left),65536):
                    n=min(65536,size-offset,left)
                    effective=0 if isolation=='uniform_fast_tier' else tier
                    rc=ceil((RCD_NS[effective]+27.5+4.77)/.25)
                    shared=profile.service_tb_s/16*1000*.25
                    rate=shared if isolation=='bank_cycle' else min(shared,16*4096/rc)
                    mem=g.add('dram',tile,n,memory_deps,resource=('dram',tile),ticks=0 if isolation in ('ideal_memory','native_only') else ceil(n/rate)+ceil((RCD_NS[effective]+4)/.25),stage='expert_prefetch',tier=tier)
                    hb_time=0 if isolation in ('ideal_memory','hb_only','hb_ingress_only') else n/(profile.hb_tb_s/16*1000*.25)
                    ingress=0 if isolation in ('ideal_memory','ingress_only','hb_ingress_only') else n/profile.fifo_ingress_bytes_tick
                    hb=g.add('hb',tile,n,(mem,),('hb',tile),ceil(max(hb_time,ingress)),'expert_prefetch',tier)
                    g.lease(mem,hb,('return',tile),n);pre.append((mem,hb,n));left-=n
                    lead+=g.nodes[mem].ticks+g.nodes[hb].ticks
                    if not left:break
                if not left:break
        r=pipeline(tuple(spans),count,p,lead=lead,collective_ports=schedule=='overlap',useful_bytes=useful)
        node=g.add('mac',tile,r['mac_flops'],list(deps)+[x[1] for x in pre],('mac',tile),r['ticks'],stage)
        g.meta['coupled_resources'][node]=[('dram',tile),('hb',tile)]+([('read',tile),('write',tile)] if schedule=='barrier' else [])
        for mem,hb,n in pre:g.lease(mem,node,('weight_fifo',tile),n)
        ledger.append(dict(node=node,tile=tile,stage=stage,prefetch_prefix_bytes=prefix,**r))
        return node
    # Each expert forms grouped GEMM with its actual effective token count.
    owner_last={}
    for job in jobs:
        prefix=job['prefix'];count=job['count'];owners=job['owners'];width=job['width']
        gate=[];silu={}
        for tile in owners:
            spans=merge_spans([layout['tensors'][prefix+'.gate'],layout['tensors'][prefix+'.up']])[tile]
            admission=sorted({owner_last[t] for t in owners if t in owner_last})
            deps=([barrier] if barrier is not None else [job['dispatch'][tile]])+admission+([accumulator_init[tile]] if combine_scheme=='fused' else [])
            node=kernel(tile,spans,count,4*d*width//len(owners),deps,'expert_gate_up',admission)
            gate.append(node)
            size=count*width//len(owners);write=g.add('sram_write',tile,size*8,(node,),('write',tile),ceil(size*8/128),'gated_state')
            read=g.add('sram_read',tile,size*8,(write,),('read',tile),ceil(size*8/(128 if schedule=='overlap' else 256)),'gated_state')
            v=g.add('vector',tile,size*6,(read,),('vector',tile),ceil(size*6/16),'silu_product')
            silu[tile]=g.add('sram_write',tile,size*2,(v,),('write',tile),ceil(size*2/128),'gated_state')
        prior={t:silu[t] for t in owners};all_ends=[];first_rows=[]
        row_down=down_partition=='row' and job['expert']!='shared'
        gathered={t:[] for t in owners};gather_starts=[]
        if row_down:
            # A STATIC alternative tensor layout with the same shard capacity.
            # Its output-row weights are packed locally from machine loading;
            # no runtime weight migration, replication or free layout switch.
            for source in owners:
                copied=g.broadcast(source,owners,count*width*2//len(owners),(silu[source],),'hidden_allgather')
                for tile in owners:gathered[tile].append(copied[tile])
            for tile in owners:
                prior[tile]=g.join(gathered[tile],'row_down_input_ready');gather_starts.append(prior[tile])
        for row in range(0,d,128):
            rows=min(128,d-row);root=row//(d//16);partials={}
            row_owners=[owners[row//(d//len(owners))]] if row_down else owners
            for tile in row_owners:
                local_row=row%(d//len(owners)) if row_down else row
                spans=slice_spans(layout['tensors'][prefix+'.down'][tile],local_row,local_row+rows,d//len(owners) if row_down else d)
                deps=[prior[tile]]
                if schedule=='barrier':deps+=gate
                k=kernel(tile,spans,count,2*rows*width//(1 if row_down else len(owners)),deps,'expert_down_rows',deps);first_rows.append(k)
                size=rows*count*4;write=g.add('sram_write',tile,size,(k,),('write',tile),ceil(size/128),'partial_store')
                read=g.add('sram_read',tile,size,(write,),('read',tile),ceil(size/(128 if schedule=='overlap' else 256)),'weighted_partial')
                weight=g.add('vector',tile,rows*count,(read,),('vector',tile),ceil(rows*count/16),'weighted_partial')
                partials[tile]=g.add('sram_write',tile,size,(weight,),('write',tile),ceil(size/128),'weighted_partial')
                prior[tile]=partials[tile]
            if combine_scheme=='fused':
                # Known linearity: weight/accumulate local expert partials,
                # then reduce ONCE per output row for the whole token batch.
                # This works with EP and TP; absent local experts contribute0.
                local=[]
                for tile,partial in partials.items():
                    read=g.add('sram_read',tile,rows*count*8,(partial,),('read',tile),ceil(rows*count*8/(128 if schedule=='overlap' else 256)),'local_token_accumulate')
                    add=g.add('vector',tile,rows*count,(read,),('vector',tile),ceil(rows*count/16),'local_token_accumulate')
                    end=g.add('sram_write',tile,rows*count*4,(add,),('write',tile),ceil(rows*count*4/128),'local_token_accumulate')
                    g.lease(partial,end,('output',tile),rows*count*4)
                    token_rows.setdefault((row,tile),[]).append(end);local.append(end)
                    prior[tile]=end
                all_ends.append(g.join(local,'expert_row_accumulated'))
                continue
            if row_down:
                source=row_owners[0]
                reduced=g.transfer(source,root,rows*count*4,(partials[source],),'combine')
            else:reduced=g.collective(root,partials,rows*count*4,'combine',preallocated_sources=True)
            # Packed expert outputs update exactly their token IDs. No dropping
            # duplicate tokens or substituting an ideal collective.
            read=g.add('sram_read',root,rows*count*8,(reduced,),('read',root),ceil(rows*count*8/(128 if schedule=='overlap' else 256)),'token_accumulate')
            add=g.add('vector',root,rows*count,(read,),('vector',root),ceil(rows*count/16),'token_accumulate')
            end=g.add('sram_write',root,rows*count*4,(add,),('write',root),ceil(rows*count*4/128),'token_accumulate')
            for tile,node in partials.items():g.lease(node,end,('output',tile),rows*count*4)
            # One output row buffer per owner; backpressure reaches producer.
            for tile in row_owners:prior[tile]=g.join((prior[tile],end),'row_release')
            all_ends.append(end)
        finished=g.join(all_ends,'expert_finished');job['terminal']=finished;terminals.append(finished)
        for tile in owners:owner_last[tile]=finished
        for tile in owners:
            # Registered gate/up state is bounded through its final down use.
            g.lease(gate[owners.index(tile)],finished,('workspace',tile),count*width*8//len(owners))
            if row_down:g.lease(gather_starts[owners.index(tile)],finished,('workspace',tile),count*width*2*(len(owners)-1)//len(owners))
        stage_done.append(finished)
    if schedule=='overlap':
        # MAC has half the read port, NoC/vector have the other half.
        for node in g.nodes:
            if node.kind=='sram_read':node.ticks=ceil(node.work/128)
    accumulator=b*d*4 if combine_scheme=='fused' else ceil(b*d*4/16)
    g.meta.update(fixed_sram_bytes=[budget['activation_reserved_bytes']+65536+accumulator]*16,
        private_sram_budget_bytes=budget['private_bytes'],buffer_caps={'workspace':budget['expert_workspace_bytes'],'output':65536})
    if combine_scheme=='fused':
        final=[];local_done=g.join(terminals,'all_local_token_accumulators_ready')
        for row in range(0,d,128):
            root=row//(d//16)
            producers={tile:g.join([accumulator_init[tile]]+token_rows.get((row,tile),[]),'all_local_expert_rows_ready') for tile in range(16)}
            # Drain local weighted partials before the collective borrows the
            # same finite output buffers. Early reduction arrivals otherwise
            # fill those buffers and block a local producer needed by the
            # reduction. This is an ordinary conservative schedule barrier;
            # it adds no storage, arithmetic or network traffic.
            # Keep one output-row cohort in the tree at a time. Concurrent
            # roots can hold each other's bounded reduction buffers while
            # waiting for sibling contributions; the eager baseline already
            # serializes these row cohorts. Pay this same finite discipline.
            admission=local_done if not final else final[-1]
            producers={tile:g.join((node,admission),'token_reduce_admitted') for tile,node in producers.items()}
            final.append(g.collective(root,producers,min(128,d-row)*b*4,'combine',preallocated_sources=True))
        g.output=[g.join(final,'moe_output_ready')]
    else:g.output=[g.join(terminals,'moe_output_ready')]
    expected=6*d*h*sum(counts.values())+6*d*hs*b
    if sum(g.nodes[x['node']].work for x in ledger)!=expected:raise ValueError('Expert MAC work changed')
    unique=(len(counts)*6*d*h+6*d*hs)
    if sum(r['dram_bytes'] for r in ledger)!=sum(sum(n for _,n in parts) for name,owners in layout['tensors'].items() if name in [j['prefix']+'.'+suffix for j in jobs for suffix in ('gate','up','down')] for parts in owners.values()):
        raise ValueError('Expert weight reads changed')
    return g,dict(jobs=[{k:v for k,v in j.items() if k not in ('dispatch',)} for j in jobs],kernel_ledger=ledger,
        mac_flops=expected,active_weight_bytes=unique,actual_dram_bytes=sum(r['dram_bytes'] for r in ledger),
        all_expert_model_weight_bytes=c['num_experts']*6*d*h+6*d*hs,budget=budget,
        token_expert_assignments=sum(counts.values()),counts=dict(counts),schedule=schedule,order=order,down_partition=down_partition,combine_scheme=combine_scheme,
        scope='Captured routing, conventional static physical ownership, finite packed collectives and row buffering; joint service kernel serializes local experts conservatively; not complete LLM tokens/s')
