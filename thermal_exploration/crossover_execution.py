"""Fixed-area resource crossover and finite known scheduling adaptations.

No new memory organization. Array-cycle probes retain the shared D1 service
ceiling. Prefetch never starts arithmetic before input readiness or uses future
router decisions. Blocked output collectives share fixed SRAM port budgets.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,asdict
from functools import lru_cache
from math import ceil
from .layer_execution import LayerExecution,merge_spans,TICK_NS
from .decode_graph import Graph,execute

MAC_AREA=13.9468928+5.0185472  # Tensor core AND its matrix RF scale together.
STORAGE_AREA=5.3103232+6.6176  # Psum SRAM + shared storage; row-swap RF fixed.
RESERVED=35.25
RCD_NS=(2.29,3.92,5.99,8.50,11.44,14.82,18.63,22.88)

@dataclass(frozen=True)
class Profile:
    compute_tflops:float=128
    sram_mib:float=36
    hb_tb_s:float=32
    isolation:str='none'
    fifo_bytes_tick:float=500
    fifo_ingress_bytes_tick:float=500
    service_tb_s:float=26.599
    def area(self,storage_fixed_fraction=.2):
        if not 0<=storage_fixed_fraction<=1:raise ValueError('Invalid storage peripheral fraction')
        storage=STORAGE_AREA*(storage_fixed_fraction+(1-storage_fixed_fraction)*self.sram_mib/36)
        variable=MAC_AREA*self.compute_tflops/128+storage
        fixed=85.75-MAC_AREA-STORAGE_AREA
        active=fixed+variable
        return dict(active_area_mm2=active,fixed_area_mm2=fixed,mac_area_mm2=MAC_AREA*self.compute_tflops/128,
          storage_area_mm2=storage,reserved_unidentified_area_mm2=RESERVED,
          fixed_row_swap_rf_mm2=4.8726592,storage_fixed_fraction=storage_fixed_fraction,
          total_committed_mm2=active+RESERVED,area_feasible=active+RESERVED<=121+1e-8,
          scaling='MAC+matrixRF scale together; row-swap RF fixed;20% buffer-area periphery fixed,80% capacity-scaled; clocks/ports fixed; unassigned area unavailable')
    def budget(self,batch,d,hidden):
        # Dedicated ingress FIFO remains PAID area(.8mm2) and allocated storage.
        # Worst simultaneous activation/gated state, partials and packet buffers.
        sram=int(self.sram_mib*2**20/16)
        activation=batch*(2*d+8*ceil(hidden/16))+batch*36+32768
        fixed=262144+65536+activation+65536*2+4096*4
        workspace=sram-fixed
        return dict(private_bytes=sram,weight_fifo_bytes=262144,response_bytes=65536,
          activation_reserved_bytes=activation,network_reserved_bytes=147456,
          fixed_bytes=fixed,expert_workspace_bytes=workspace,feasible=workspace>=batch*d*4)


@lru_cache(maxsize=4096)
def pipeline(parts,batch,profile=Profile(),lead=0,collective_ports=False,useful_bytes=None):
    """D1-guarded fluid delivery,1024B returns, finite32KiB streaming blocks.

    Arithmetic and operand reads overlap. When collective overlap is enabled,
    MAC has128B/tick of the existing256B read port; collective has the other
    half. All128B/tick writes go to the collective/result engine. No extra port.
    """
    if min(profile.compute_tflops,profile.hb_tb_s,profile.fifo_bytes_tick,profile.fifo_ingress_bytes_tick)<=0 or lead<0:raise ValueError('Invalid resource profile')
    if profile.isolation not in ('none','bank_cycle','uniform_fast_tier','hb_only','ingress_only','mac_only','ideal_memory'):raise ValueError('Unknown isolation')
    mem_free=hb_free=-lead;mac_free=0;weights=defaultdict(lambda:-lead);returns=defaultdict(lambda:-lead)
    chunk=32768;packet=1024;slots=8;return_slots=64;index=packet_index=processed=0
    total=sum(n for _,n in parts);useful=total if useful_bytes is None else useful_bytes
    activity=Counter({k:0 for k in ('dram','hb','mac','sram_read','sram_write')});ends=[];blocks=[];mac_busy=wait=0;memory_start=None;prefetched=0
    read_rate=128 if collective_ports else 256
    for tier,size in parts:
        effective=0 if profile.isolation=='uniform_fast_tier' else tier
        rc=ceil((RCD_NS[effective]+27.5+4.77)/TICK_NS)
        shared=profile.service_tb_s/16*1000*TICK_NS
        rate=shared if profile.isolation=='bank_cycle' else min(shared,16*4096/rc)
        latency=ceil((RCD_NS[effective]+4)/TICK_NS)
        for offset in range(0,size,chunk):
            count=min(chunk,size-offset);slot=index%slots
            flops=((processed+count)*useful*batch)//total-(processed*useful*batch)//total
            read=min(count,1024*batch)
            mac_rate=profile.compute_tflops/128*2000
            arithmetic=0 if profile.isolation=='mac_only' else ceil(flops/mac_rate)
            compute=max(1,arithmetic,ceil(read/read_rate),ceil(count/profile.fifo_bytes_tick))
            cumulative=0
            for po in range(0,count,packet):
                n=min(packet,count-po);rs=packet_index%return_slots
                start=max(mem_free,weights[slot],returns[rs]);memory_start=start if memory_start is None else min(start,memory_start)
                duration=ceil((cumulative+n)/rate)-ceil(cumulative/rate);cumulative+=n
                if profile.isolation=='ideal_memory':duration=0
                mem_free=start+duration;arrival=mem_free+(0 if profile.isolation=='ideal_memory' else latency)
                hb_start=max(arrival,hb_free)
                hb_duration=0 if profile.isolation in ('hb_only','ideal_memory') else n/(profile.hb_tb_s/16*1000*TICK_NS)
                ingress=0 if profile.isolation in ('ingress_only','ideal_memory') else n/profile.fifo_ingress_bytes_tick
                hb_duration=max(hb_duration,ingress)
                # Streaming uses the already paid dedicated ingress FIFO; the
                # ordinary SRAM-copy limit is independently probed below.
                hb_free=hb_start+hb_duration;returns[rs]=hb_free
                if hb_free<=0:prefetched+=n
                activity.update(dram=n,hb=n);packet_index+=1
            begin=ceil(max(0,hb_free,mac_free));finish=begin+compute
            wait+=begin-mac_free;mac_busy+=compute;mac_free=finish
            processed+=count;ends.append((processed,finish));blocks.append((begin,finish,read,flops))
            weights[slot]=finish;activity.update(mac=flops,sram_read=read);index+=1
    if processed!=total or activity['mac']!=useful*batch:raise ValueError('Kernel conservation')
    if prefetched>262144:raise ValueError('Prefetch exceeds FIFO lease')
    return dict(ticks=mac_free,activity=dict(activity),dram_bytes=total,mac_flops=useful*batch,
      dram_last_tick=mem_free+latency,hb_last_tick=hb_free,memory_start_tick=memory_start,
      prefetched_bytes=prefetched,mac_busy_ticks=mac_busy,missing_data_ticks=wait,
      byte_completion=tuple(ends),mac_blocks=tuple(blocks),max_response_bytes=min(packet_index,64)*1024,max_live_weight_bytes=min(index,8)*32768)


def split_result(c,names,layout,batch):
    sizes=Counter()
    for n in names:
        last=n.split('.')[-1];owners=layout['tensors'][n]
        if n=='lm_head':width=c['vocab_size'];column=False
        elif last in ('q','o','down'):width=c['hidden_size'];column=last in ('o','down')
        elif last in ('k','v'):width=c['num_key_value_heads']*c['hidden_size']//c['num_attention_heads'];column=False
        elif last in ('router','shared_router'):width=c['num_experts'] if last=='router' else 1;column=True
        else:width=c['moe_intermediate_size'] if '.expert' in n else c['shared_expert_intermediate_size'] if '.shared.' in n else c['intermediate_size'];column=False
        for tile in owners:sizes[tile]+=batch*width*4 if column else ceil(batch*width*4/len(owners))
    return sizes

@lru_cache(maxsize=512)
def output_collective(results,batch,width,private,activation,oracle='none'):
    """Known64-row blocked packing; partials become ready after ALL local K.

    Packing a column-sharded matrix by output64-row groups is a software layout
    choice. At each output group the last32KiB MAC block must finish. Whole
    tensor partial storage is reserved even though groups can be released early.
    """
    g=Graph(256,True);states={tile:(total,ends) for tile,total,ends in results}
    count=len(states);outputs=[]
    for row in range(0,width,64):
        size=min(64,width-row);producers={}
        for tile,(total,ends) in states.items():
            target=ceil(total*(row+size)/width)
            ready=next(time for consumed,time in ends if consumed>=target)
            marker=g.add('join',tile,0,resource=('producer_ready',len(g.nodes)),ticks=ready,stage='output_ready')
            write=g.add('sram_write',tile,size*batch*4,(marker,),('write',tile),ceil(size*batch*4/128),'result_state')
            producers[tile]=write
        root=min(15,row//ceil(width/16))
        outputs.append(g.collective(root,producers,size*batch*4,'blocked_reduce',preallocated_sources=True))
    # MAC consumes at most128B/tick; packets use the other128B/tick.
    for node in g.nodes:
        if node.kind=='sram_read':node.ticks=ceil(node.work/128)
    g.output=outputs
    fixed=262144+65536+activation+width*batch*4
    g.meta=dict(fixed_sram_bytes=[fixed]*16,private_sram_budget_bytes=private)
    mode='infinite_noc' if oracle=='infinite_noc' else 'baseline'
    r=execute(g,mode)
    return {k:r[k] for k in ('ticks','activity','per_tile_activity','buffer_high','credit_stall_probes','validation')}


@lru_cache(maxsize=128)
def stream_logits(results,batch,vocab):
    """Known blocked logit selection, with independently bounded pending bytes.

    MAC gets128B/tick of the existing read port. Result writes, selection reads
    and selection work share ordinary ports/vector units. The producer is NOT
    retimed optimistically: reject if pending results exceed two64-row blocks.
    """
    g=Graph(256,True);pending=[];ends=[]
    local=vocab//16
    for tile,total,completions in results:
        for row in range(0,local,64):
            count=min(64,local-row);size=count*batch*4
            target=ceil(total*(row+count)/local)
            ready=next(t for bytes_,t in completions if bytes_>=target)
            marker=g.add('join',tile,0,resource=('logits_ready',len(g.nodes)),ticks=ready,stage='logit_ready')
            write=g.add('sram_write',tile,size,(marker,),('write',tile),ceil(size/128),'logit_store')
            read=g.add('sram_read',tile,size,(write,),('read',tile),ceil(size/128),'logit_scan')
            scan=g.add('vector',tile,count*batch*2,(read,),('vector',tile),ceil(count*batch*2/16),'logit_argmax')
            end=g.add('sram_write',tile,size,(scan,),('write',tile),ceil(size/128),'logit_scan_state')
            # Charge the old temporary write volume conservatively; bounded
            # max/index state would actually require fewer writes.
            pending.append((tile,ready,end,size));ends.append(end)
    g.output=ends;r=execute(g);events={e['id']:e for e in r['events']};high=Counter()
    for tile in range(16):
        changes=Counter()
        for t,ready,end,size in pending:
            if t==tile:changes[ready]+=size;changes[events[end]['finish_tick']]-=size
        live=0
        for tick,delta in sorted(changes.items()):live+=delta;high[tile]=max(high[tile],live)
        if live or high[tile]>2*64*batch*4:raise ValueError('Logit producer outruns bounded selection; retiming required')
    return dict(ticks=r['ticks'],activity=r['per_tile_activity'],maximum_pending_bytes_per_tile=dict(high),scope='Known greedy vocabulary scan; two64-row buffers; conservative unchanged temporary write ledger; no new hardware')


@lru_cache(maxsize=128)
def greedy_selection(batch):
    # Each vocabulary shard contributes(max_logit,index), not a floating sum.
    from .horizontal import route
    g=Graph(256,True);children=defaultdict(list)
    for a,b in sorted({edge for tile in range(16) for edge in route(0,tile)}):children[a].append(b)
    def visit(tile):
        contributions=[g.join(())]
        for child in children[tile]:
            state=visit(child);contributions.append(g.transfer(child,tile,batch*8,(state,),'greedy_argmax'))
        read=g.add('sram_read',tile,len(contributions)*batch*8,contributions,('read',tile),ceil(len(contributions)*batch*8/256),'greedy_argmax')
        work=(len(contributions)-1)*batch*3
        merge=g.add('vector',tile,work,(read,),('vector',tile),ceil(work/16),'greedy_argmax')
        return g.add('sram_write',tile,batch*8,(merge,),('write',tile),ceil(batch*8/128),'greedy_argmax')
    result=visit(0);g.output=list(g.broadcast(0,list(range(16)),batch*4,(result,),'selected_token_id').values())
    r=execute(g);return dict(ticks=r['ticks'],activity=r['per_tile_activity'],semantics='Associative max/index with lowest-index ties, then generated ID broadcast')


class CrossoverExecution(LayerExecution):
    def __init__(self,c,admission,layout,baseline='B3_3d_placement',profile=Profile(),schedule='serial'):
        super().__init__(c,admission,layout,baseline,'none')
        if schedule not in ('serial','finite_prefetch','blocked_collective','prefetch_collective'):raise ValueError('Unknown schedule')
        if not profile.area()['area_feasible']:raise ValueError('Committed area exceeds121mm2')
        self.profile=profile;self.schedule=schedule;self.pending=None;self.route_ready=0
        hidden=c.get('intermediate_size',c.get('shared_expert_intermediate_size',0))
        self.budget=profile.budget(admission['batch'],c['hidden_size'],hidden)
        if not self.budget['feasible']:raise ValueError('Fixed SRAM allocations do not fit')
        self.expert_workspace_bytes=self.budget['expert_workspace_bytes']
        self.resident_expert_input=True
        self.incremental_combine=schedule!='serial'
        self.prefetch_ledger=[];self.overlap_ledger=[]
    def kernel(self,parts,batch,stream,oracle='none',useful_bytes=None,**kwargs):
        return pipeline(parts,batch,self.profile,useful_bytes=useful_bytes)
    def phase(self,name,duration,activity,reason):
        if name=='embedding_lookup' or name.endswith('norm_bias_weights'):
            bytes_=sum(v.get('dram',0) for v in activity.values())
            duration=max(duration,ceil(bytes_/(self.profile.service_tb_s*1000*TICK_NS)))
        super().phase(name,duration,activity,reason)
        if name.endswith('route_weights_distribution'):self.route_ready=self.clock
    def linear(self,names,batch,name):
        parts=merge_spans([self.layout['tensors'][n] for n in names]);useful=Counter()
        for n in names:
            for tile in self.layout['tensors'][n]:useful[tile]+=self.tensor_bytes[n]//len(self.layout['tensors'][n])
        # Only immediately preceding non-DRAM, non-MAC phase. FIFO ingress is
        # separate and paid. Expert identity must already have been computed.
        lead=0
        if self.schedule in ('finite_prefetch','prefetch_collective') and self.events:
            previous=self.events[-1]
            if not any(v.get('dram',0) or v.get('mac',0) or v.get('hb',0) for v in previous['activity'].values()):
                start=previous['start_tick']
                if any('.expert' in n for n in names):start=max(start,self.route_ready)
                lead=max(0,self.clock-start)
        overlap=self.schedule in ('blocked_collective','prefetch_collective') and len(names)==1 and names[0].split('.')[-1] in ('o','down') and '.expert' not in names[0] and '.shared.' not in names[0]
        logit_stream=names==['lm_head']
        results={tile:pipeline(spans,batch,self.profile,lead,overlap or logit_stream,useful[tile]) for tile,spans in parts.items()}
        start=self.clock;elapsed=max(r['ticks'] for r in results.values());activity={str(t):r['activity'] for t,r in results.items()}
        mem=max(r['dram_last_tick'] for r in results.values());mac=sum(r['mac_flops'] for r in results.values())/(self.profile.compute_tflops/128*32000)
        self.phase(name,elapsed,activity,'memory/storage' if mem>=mac else 'compute')
        self.events[-1]['tile_kernel_windows']={str(t):{k:r[k] for k in ('ticks','dram_last_tick','hb_last_tick','memory_start_tick','max_response_bytes','max_live_weight_bytes','prefetched_bytes','mac_busy_ticks','missing_data_ticks')} for t,r in results.items()}
        self.prefetch_ledger.append(dict(stage=name,start_tick=start,lead_ticks=lead,identity_ready_tick=self.route_ready if any('.expert' in n for n in names) else 0,bytes=sum(r['prefetched_bytes'] for r in results.values()),private_fifo_bytes=262144))
        sizes=split_result(self.c,names,self.layout,batch)
        if logit_stream:
            descriptors=tuple((t,r['dram_bytes'],r['byte_completion']) for t,r in sorted(results.items()))
            selected=stream_logits(descriptors,batch,self.c['vocab_size'])
            if max(selected['maximum_pending_bytes_per_tile'].values())>self.expert_workspace_bytes:raise ValueError('Logit block storage exceeds workspace')
            self.phase('lm_head_streaming_selection',max(0,start+selected['ticks']-self.clock),selected['activity'],'vector/local state')
            self.events[-1].update(overlap_start_tick=start,maximum_logit_pending_bytes=selected['maximum_pending_bytes_per_tile'])
            self.logit_streamed=True
            return
        if max(sizes.values())>self.expert_workspace_bytes:raise ValueError('Result partial workspace exceeds finite allocation')
        if overlap:
            self.pending=dict(start=start,name=name,batch=batch,width=self.c['hidden_size'],results=tuple((t,r['dram_bytes'],r['byte_completion']) for t,r in sorted(results.items())),sizes=sizes)
        else:
            self.phase(name+'_result_state',max(ceil(n/128) for n in sizes.values()),{str(t):dict(sram_write=n) for t,n in sizes.items()},'vector/local state')
    def network(self,name,batch,width,kind):
        if name=='next_token_sampling':
            r=greedy_selection(batch);self.phase(name,r['ticks'],r['activity'],'communication/synchronization')
            self.events[-1]['semantics']=r['semantics'];return
        if self.pending and kind=='reduction':
            p=self.pending;self.pending=None
            if batch!=p['batch'] or width!=p['width']:raise ValueError('Collective producer mismatch')
            r=output_collective(p['results'],batch,width,self.budget['private_bytes'],self.budget['activation_reserved_bytes'])
            end=p['start']+r['ticks'];tail=max(0,end-self.clock)
            self.phase(name,tail,r['per_tile_activity'],'communication/synchronization')
            self.events[-1]['overlap_start_tick']=p['start'];self.events[-1]['collective_buffer_high']=r['buffer_high']
            self.overlap_ledger.append(dict(stage=name,producer_start=p['start'],producer_finish=self.events[-2]['finish_tick'],collective_end=end,tail_ticks=tail,read_port_partition=[128,128],write_port_bytes_tick=128))
        else:
            if self.pending:raise ValueError('Pending producer lost dependency')
            super().network(name,batch,width,kind)
    def vector(self,name,ops,bytes_,batch):
        if name=='logit_selection' and getattr(self,'logit_streamed',False):return
        super().vector(name,ops,bytes_,batch)
    def initialize_combine(self,p,batch):
        size=self.c['hidden_size']*batch*4
        self.phase(p+'initialize_token_accumulator',ceil(size/128),{str(t):dict(sram_write=size) for t in range(16)},'vector/local state')
    def bounded_expert_cohorts(self,groups,batch):
        if not self.incremental_combine:return groups
        result=[];d=self.c['hidden_size']
        available=self.expert_workspace_bytes-batch*d*4
        for count,names in groups:
            maximum=available//(count*d*4)
            if maximum<1:raise ValueError('One expert + accumulator do not fit')
            for offset in range(0,len(names),3*maximum):result.append((count,names[offset:offset+3*maximum]))
        return result
    def accumulate_expert_partials(self,p,count,names,batch):
        # Known incremental accumulation: explicitly costs scratch reads/writes,
        # retaining one token accumulator plus one cohort. No network arithmetic.
        d=self.c['hidden_size'];partials=Counter()
        for n in names:
            if n.endswith('.down'):
                for tile in self.layout['tensors'][n]:partials[tile]+=count
        activity={str(t):dict(vector=2*d*n,sram_read=d*4*(n+batch),sram_write=d*4*batch) for t,n in partials.items()}
        peak=max(d*4*(n+batch) for n in partials.values())
        if peak>self.expert_workspace_bytes:raise ValueError('Cohort + running accumulator exceed finite workspace')
        duration=max(max(ceil(v['vector']/16),ceil(v['sram_read']/256)+ceil(v['sram_write']/128)) for v in activity.values())
        self.phase(p+'incremental_weighted_combine',duration,activity,'vector/local state')
        self.events[-1]['live_expert_workspace_bytes']=peak
    def token(self,*args,**kwargs):
        r=super().token(*args,**kwargs)
        r.update(profile=asdict(self.profile),area=self.profile.area(),sram_budget=self.budget,schedule=self.schedule,prefetch_ledger=self.prefetch_ledger,collective_overlap_ledger=self.overlap_ledger)
        return r
