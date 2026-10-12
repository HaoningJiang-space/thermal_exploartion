"""H2-A tensor/physical-layout contract; no free dataflow or service cap."""
from collections import Counter, defaultdict
from math import ceil
from pathlib import Path
import json
from .hb_trace import encoded,address_vector
from .horizontal import route

CASES={
    f'{name}_blocked_{order}':dict(rows=rows,columns=16//rows,layout='blocked',order=order)
    for name,rows in (('row',16),('column',1),('2d',4)) for order in ('m','k')
}
CASES.update({
    'row_fifo_k':dict(rows=16,columns=1,layout='blocked',order='k',stream_fifo=True,weight_buffer=262144),
    'row_fifo_m':dict(rows=16,columns=1,layout='blocked',order='m',stream_fifo=True,weight_buffer=262144),
    'row_fifo32':dict(rows=16,columns=1,layout='blocked',order='k',reduction_packet=32,stream_fifo=True,weight_buffer=262144),
    'column_fifo32':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=32,stream_fifo=True,weight_buffer=262144),
    'column_fifo64':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64,stream_fifo=True,weight_buffer=262144),
    'column_fifo_barrier':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64,barrier=True,stream_fifo=True,weight_buffer=262144),
    'row_fifo_independent':dict(rows=16,columns=1,layout='blocked',order='k',stream_fifo=True,weight_buffer=262144,command_domains=2),
    'row_fifo_m_independent':dict(rows=16,columns=1,layout='blocked',order='m',stream_fifo=True,weight_buffer=262144,command_domains=2),
    'column_fifo_independent':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64,stream_fifo=True,weight_buffer=262144,command_domains=2),
    'row_local_first':dict(rows=16,columns=1,layout='blocked',order='k',local_first=True),
    '2d_local_first':dict(rows=4,columns=4,layout='blocked',order='k',local_first=True),
    'row_rowmajor_k':dict(rows=16,columns=1,layout='row_major',order='k'),
    'column_rowmajor_m':dict(rows=1,columns=16,layout='row_major',order='m'),
    '2d_rowmajor_k':dict(rows=4,columns=4,layout='row_major',order='k'),
    'column_padded_m':dict(rows=1,columns=16,layout='padded_row',order='m'),
    'column_barrier':dict(rows=1,columns=16,layout='blocked',order='m',barrier=True),
    'column_buffer8k':dict(rows=1,columns=16,layout='blocked',order='m',weight_buffer=8192),
    'column_reduce64':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64),
    'row_ideal_transport':dict(rows=16,columns=1,layout='blocked',order='k',ideal_noc=True),
    'column_ideal_transport':dict(rows=1,columns=16,layout='blocked',order='m',ideal_noc=True),
    'column_ideal_memory':dict(rows=1,columns=16,layout='blocked',order='m',ideal_memory=True),
    'column_ideal_buffer':dict(rows=1,columns=16,layout='blocked',order='m',ideal_buffer=True),
    'column64_ideal_transport':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64,ideal_noc=True),
    'column64_ideal_memory':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64,ideal_memory=True),
    'column64_ideal_buffer':dict(rows=1,columns=16,layout='blocked',order='m',reduction_packet=64,ideal_buffer=True),
})


def hardware(settings,m=1024,n=16384,batch=32):
    p,q=settings['rows'],settings['columns']
    if p*q!=16 or min(m,n,batch,p,q)<1 or m%16 or n%16 or (m//16*batch*4)%32:
        raise ValueError('Invalid tensor/hardware partition')
    ml,nl=m//p,n//q;mb,kb=min(32,ml),min(128,nl,n//16)
    # Actual MoE row shards can be88 rows (1408/16). Use the largest legal
    # block at the existing32-row maximum, rather than padding/inventing MACs.
    while ml%mb:mb-=1
    # Input groups must be wholly owned by their canonical source shard.
    # Pick an aligned divisor; never invent a128-element source block when
    # a source owns only88 elements (e.g. Qwen expert1408/16).
    while kb and (nl%kb or (n//16)%kb or (kb*batch*2)%32):kb-=1
    if not kb:raise ValueError('No canonically owned32B-aligned input block; padding unsupported')
    if ml%mb or nl%kb:raise ValueError('Nonintegral MAC blocks')
    packet=settings.get('reduction_packet',256)
    if packet not in (32,64,256) or (m//16*batch*4)%min(packet,m//16*batch*4):raise ValueError('Unaligned output')
    packet=min(packet,m//16*batch*4)
    static=[]
    for tile in range(16):
        col=tile%q;lo=col*nl;own=tile*(n//16)
        input_elements=nl if lo<=own and own+n//16<=lo+nl else nl+n//16
        static.append(input_elements*batch*2+ml*batch*4+m//16*batch*2+2560)
    weight=settings.get('weight_buffer',524288);response=min(65536,weight)
    ideal_buffer=settings.get('ideal_buffer',False)
    if ideal_buffer:weight=4*2**20;response=2*2**20
    peak=float(settings.get('compute_tflops',128));capacity=float(settings.get('sram_mib',36))
    if min(peak,capacity)<=0:raise ValueError('Invalid paid compute/storage profile')
    sram=16*2**20 if ideal_buffer else int(capacity*2**20/16)
    red=2**20 if ideal_buffer else 65536
    # Metadata, router FIFOs, fixed inputs/partials/output and all return
    # storage are charged separately. Unused private SRAM is not pooled.
    if max(static)+weight+response+red+65536>sram:
        raise ValueError('Private SRAM budget exceeded')
    return dict(m=m,n=n,batch=batch,row_parts=p,column_parts=q,m_block=mb,k_block=kb,
        mac_flops=2*m*n*batch,weight_bytes=m*n*2,input_bytes=n*batch*2,output_bytes=m*batch*2,
        reduction_adds=(q-1)*m*batch,output_casts=m*batch,partial_bytes_per_tile=ml*batch*4,
        static_sram_per_tile=static,sram_per_tile=sram,metadata_reserve=65536,
        weight_buffer=weight,response_buffer=response,reduce_buffer=red,prefetch_tasks=4096 if ideal_buffer else 32,
        packet_bytes=packet,flit_bytes=32,vc_depth_flits=8,virtual_channels=2,
        compute_tflops=peak,sram_mib=capacity,
        tick_ns=.25,dram_CK_ns=.5,dram_tick_ns=.25,logic_ticks_per_dram_tick=1,mac_flops_per_tick=peak*1000*.25/16,vector_ops_per_tick=16,
        sram_read_bytes_per_tick=256,sram_write_bytes_per_tick=128,
        hb_bytes_per_tile_tick=500,link_serial_ticks=4,link_latency_ticks=8,
        ideal_noc=settings.get('ideal_noc',False),barrier=settings.get('barrier',False),
        ideal_memory=settings.get('ideal_memory',False),ideal_buffer=ideal_buffer,
        stream_fifo=settings.get('stream_fifo',False),fifo_bytes_per_tick=500,
        command_domains_per_tile=settings.get('command_domains',1),
        fluid_memory=bool(settings.get('fluid_memory',False)),fluid_service_tb_s=float(settings.get('fluid_service_tb_s',26.599)),
        assumptions=['Fast-tier internal timing surrogate, not calibrated Mono3D',
          f'{peak:g}TF peak MAC service, operand/register reuse ideal within a MAC block',
          'Aggregate private-SRAM ports are assumed, explicitly arbitrated each tick',
          'Two virtual networks and router multicast common to all partitions',
          'Vector packet read/add/write are serial, transport and MAC may overlap',
          'Input starts canonically sharded in private SRAM; output same canonical shards',
          'No functional FP16 numerical inference claim, no thermal feedback'])


def trees(root,targets,reverse=False):
    edges={e for target in targets for e in route(root,target)}
    children=[[] for _ in range(16)];parent=[-1]*16
    for a,b in sorted(edges):children[a].append(b);parent[b]=a
    return children,parent


def build(settings,m=1024,n=16384,batch=32):
    c=hardware(settings,m,n,batch);p,q=c['row_parts'],c['column_parts'];ml,nl=m//p,n//q
    mb,kb=c['m_block'],c['k_block'];layout=settings['layout']
    if layout not in ('blocked','row_major','padded_row') or settings['order'] not in ('m','k'):
        raise ValueError('Unknown layout/loop')
    tasks=[];requests=[];request_by_key={};last={};coverage=Counter()
    coordinates=[(i,j) for i in range(ml//mb) for j in range(nl//kb)]
    if settings['order']=='k':coordinates.sort(key=lambda z:(z[1],z[0]))
    allocated=[0]*16
    for bi,bj in coordinates:
        for tile in range(16):
            rowpart,colpart=tile//q,tile%q;ridset=set();sequence_index=bj
            own_start=tile*(n//16)-colpart*nl
            rotation=own_start//kb if settings.get('local_first',False) and 0<=own_start<nl else 0
            actual_bj=(bj+rotation)%(nl//kb)
            for row in range(bi*mb,(bi+1)*mb):
                for column in range(actual_bj*kb,(actual_bj+1)*kb):
                    if layout=='blocked':offset=((bi*(nl//kb)+actual_bj)*mb*kb+(row-bi*mb)*kb+column-actual_bj*kb)*2
                    else:
                        stride=ceil(nl*2/4096)*4096 if layout=='padded_row' else nl*2
                        offset=row*stride+column*2
                    key=(tile,offset//1024);allocated[tile]=max(allocated[tile],offset+2)
                    if key not in request_by_key:
                        page=offset//4096;bank=(page^(page>>4))%16;physrow=page//16
                        addr=encoded(tile,bank,physrow,(offset%4096)//1024)
                        rid=len(requests);request_by_key[key]=rid
                        requests.append(dict(id=rid,tile=tile,address=addr,addr_vec=address_vector(addr,2),size=1024,refs=0))
                    rid=request_by_key[key];ridset.add(rid);coverage[rid]+=2
            tid=len(tasks);parent=last.get((tile,bi),-1)
            # K always increases within each output block, regardless of loop.
            if parent>=0 and (tasks[parent]['k_start']-colpart*nl+kb)%nl!=actual_bj*kb:raise ValueError('Broken partial-sum chain')
            for rid in ridset:requests[rid]['refs']+=1
            tasks.append(dict(id=tid,tile=tile,m_start=rowpart*ml+bi*mb,m_count=mb,k_start=colpart*nl+actual_bj*kb,k_count=kb,
                flops=2*mb*kb*batch,parent=parent,input_group=(colpart*nl+actual_bj*kb)//kb,
                final=int(sequence_index==nl//kb-1),requests=sorted(ridset)))
            last[tile,bi]=tid
    if sum(coverage.values())!=c['weight_bytes'] or any(not 0<x<=1024 for x in coverage.values()):
        raise ValueError('Every weight byte must be fetched/used exactly once across the contraction')
    if len({r['address'] for r in requests})!=len(requests):raise ValueError('Physical alias')
    groups=[]
    for g in range(n//kb):
        source=(g*kb)//(n//16);col=(g*kb)//nl;targets=[r*q+col for r in range(p)]
        children,parent=trees(source,targets)
        groups.append(dict(id=g,source=source,bytes=kb*batch*2,targets=targets,children=children,parent=parent))
    reductions=[]
    for gid,start in enumerate(range(0,m*batch*4,c['packet_bytes'])):
        row=start//(batch*4);root=row//(m//16);rpart=row//ml
        producers=[rpart*q+col for col in range(q)];children,parent=trees(root,producers)
        nodes=sorted(set(producers)|{root}|{a for a in range(16) if children[a]})
        reductions.append(dict(id=gid,root=root,bytes=c['packet_bytes'],row=row,producers=producers,
            children=children,parent=parent,nodes=nodes))
    c.update(tasks=len(tasks),requests=len(requests),dram_bytes=len(requests)*1024,
             allocated_weight_bytes=sum(ceil(x/4096)*4096 for x in allocated),layout=layout,order=settings['order'])
    if max(allocated)>2*2**30 or sum(t['flops'] for t in tasks)!=c['mac_flops']:
        raise ValueError('Capacity/work violation')
    return dict(contract=c,tasks=tasks,requests=requests,inputs=groups,reductions=reductions)


def write_contract(model,out):
    out=Path(out);c=model['contract'];(out/'contract.json').write_text(json.dumps(c,indent=2)+'\n')
    with (out/'resources.tsv').open('w') as f:
        keys=('m','n','batch','row_parts','column_parts','m_block','k_block','weight_buffer','response_buffer',
              'reduce_buffer','prefetch_tasks','packet_bytes','ideal_noc','barrier','ideal_memory')
        f.write(' '.join(str(int(c[k])) for k in keys)+'\n')
        f.write(' '.join(map(str,c['static_sram_per_tile']))+'\n')
        f.write(str(int(c.get('stream_fifo',False)))+' '+str(c.get('command_domains_per_tile',1))+'\n')
        f.write(f"{c['mac_flops_per_tick']} {c['sram_per_tile']} {int(c['fluid_memory'])} {c['fluid_service_tb_s']}\n")
    with (out/'tasks.tsv').open('w') as f:
        for t in model['tasks']:
            f.write(' '.join(map(str,[t[k] for k in ('id','tile','m_start','m_count','k_start','k_count','flops','parent','input_group','final')]+[len(t['requests'])]+t['requests']))+'\n')
    with (out/'requests.tsv').open('w') as f:
        for r in model['requests']:f.write(' '.join(map(str,[r['id'],r['tile'],r['address'],r['refs']]+r['addr_vec']))+'\n')
    for name in ('inputs','reductions'):
        with (out/(name+'.tsv')).open('w') as f:
            for g in model[name]:
                root=g['source'] if name=='inputs' else g['root'];participants=g['targets'] if name=='inputs' else g['producers']
                f.write(' '.join(map(str,[g['id'],root,g['bytes'],g.get('row',-1),sum(1<<t for t in participants)]+g['parent']))+'\n')
