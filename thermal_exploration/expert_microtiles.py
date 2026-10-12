"""Finite32KiB service blocks, preserving the existing registered-reuse law.

No hardware added. MAC/operand/FIFO service can co-issue as in the native tensor
frontend, with exclusive read-port windows (an eager operand-service policy).
Memory return latency does not occupy the DRAM serialization resource.
"""
from collections import Counter
from math import ceil
from .crossover_execution import pipeline,RCD_NS


def microtile_kernel(g,tile,spans,batch,profile,useful,deps,stage,prefetch=False):
    total=sum(n for _,n in spans);processed=0;blocks=[];packets=[];ledger=[]
    memory_deps=() if prefetch else tuple(deps)
    for tier,size in spans:
        rc=ceil((RCD_NS[tier]+27.5+4.77)/.25)
        rate=min(profile.service_tb_s/16*1000*.25,16*4096/rc)
        latency=ceil((RCD_NS[tier]+4)/.25)
        for offset in range(0,size,32768):
            count=min(32768,size-offset);returns=[];first=None;cumulative=0
            recycle=blocks[-8] if len(blocks)>=8 else None
            for po in range(0,count,1024):
                n=min(1024,count-po);duration=ceil((cumulative+n)/rate)-ceil(cumulative/rate);cumulative+=n
                mem=g.add('dram',tile,n,list(memory_deps)+([recycle] if recycle is not None else []),('dram',tile),duration,stage,tier)
                arrival=g.add('join',tile,0,(mem,),('native_return_latency',mem),latency,stage,tier)
                hb=g.add('hb',tile,n,(arrival,),('hb',tile),max(n/(profile.hb_tb_s/16*1000*.25),n/profile.fifo_ingress_bytes_tick),stage,tier)
                g.lease(mem,hb,('return',tile),n);g.lease(mem,hb,('return_descriptor',tile),16)
                first=mem if first is None else first;returns.append(hb);packets.append(dict(dram=mem,arrival=arrival,hb=hb,bytes=n,tier=tier))
            flops=((processed+count)*useful*batch)//total-(processed*useful*batch)//total
            read=min(count,1024*batch);arithmetic=0 if profile.isolation=='mac_only' else ceil(flops/(profile.compute_tflops/128*2000))
            read_ticks=ceil(read/256);fifo_ticks=ceil(count/profile.fifo_bytes_tick)
            duration=max(1,arithmetic,read_ticks,fifo_ticks)
            ready=list(deps)+returns+blocks[-1:]
            node=g.add('mac',tile,flops,ready,('mac',tile),duration,stage,tier)
            operand=g.add('sram_read',tile,read,ready,('read',tile),read_ticks,stage+'_operand',tier)
            fifo=g.add('fifo_read',tile,count,ready,('fifo_consume',tile),fifo_ticks,stage+'_operand',tier)
            g.meta.setdefault('coissued_nodes',{})[node]=[operand,fifo]
            g.meta.setdefault('arithmetic_ticks',{})[node]=arithmetic
            g.lease(first,node,('weight_fifo',tile),count);g.lease(first,node,('weight_descriptor',tile),32)
            ledger.append(dict(node=node,first_memory=first,return_nodes=returns,bytes=count,flops=flops,operand_bytes=read,arithmetic_ticks=arithmetic,operand_ticks=read_ticks,fifo_ticks=fifo_ticks))
            blocks.append(node);processed+=count
    terminal=g.join(blocks,'local_kernel_complete')
    reference=pipeline(tuple(spans),batch,profile,useful_bytes=useful)
    if sum(r['flops'] for r in ledger)!=reference['mac_flops'] or sum(r['bytes'] for r in packets)!=reference['dram_bytes'] or sum(r['operand_bytes'] for r in ledger)!=reference['activity']['sram_read']:
        raise ValueError('Fine kernel changes work')
    g.meta['fluid_ticks']=True
    return terminal,dict(reference,node=terminal,tile=tile,stage=stage,prefetch_prefix_bytes=0,
        microtile_ledger=ledger,packet_ledger=packets,execution_grain='fine_prefetch' if prefetch else 'fine_fixed')
