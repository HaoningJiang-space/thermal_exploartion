"""Full MoE finite-flit program, preserving the conventional semantic DAG.

A program is work/dependencies/ownership, never a table of measured durations.
Both independent interpreters share this builder, not execution state.
"""
from collections import Counter,defaultdict
from pathlib import Path
from math import ceil
import json
from .decode_graph import Graph
from .horizontal import route
from .expert_execution import expert_graph
from .crossover_execution import Profile
from .hb_trace import encoded,address_vector
from .moe_numerical import check_ledger

KINDS=('join','sram_read','sram_write','vector','mac','link','hb','dram','fifo_read')

class FlitGraph(Graph):
    def __init__(self):
        super().__init__(64,True);self.packet_bytes=32
    def network_link(self,source,target,size,deps,stage):
        if size!=32:raise ValueError('Every transport operation must be one32B flit')
        node=self.add('link',source,size,deps,('link',source,target),8,stage)
        return node,node
    def broadcast(self,source,targets,bytes_,deps=(),stage='input'):
        if bytes_%32:raise ValueError('No free network padding')
        children=defaultdict(list)
        for a,b in sorted({e for t in targets for e in route(source,t)}):children[a].append(b)
        output=defaultdict(list)
        for offset in range(0,bytes_,32):
            read=self.add('sram_read',source,32,deps,('read',source),1,stage)
            def visit(node,before):
                if node in targets and node!=source:
                    write=self.add('sram_write',node,32,(before,),('write',node),1,stage)
                    output[node].append(write)
                for target in children[node]:
                    link,_=self.network_link(node,target,32,(before,),stage);visit(target,link)
            visit(source,read)
        result={t:self.join(output[t],stage) for t in targets if t!=source}
        if source in targets:result[source]=self.join(deps,stage)
        return result


def program(c,layout,layer,routes,down='row',grain='fine_fixed',selected=None,shared=True):
    g,meta=expert_graph(c,layout,layer,routes,Profile(),schedule='barrier',order='static',down_partition=down,reduction_scheme='row_ready_128',execution_grain=grain,graph_factory=FlitGraph,selected_experts=selected,include_shared=shared,shared_gate_execution=shared)
    check_ledger(c,routes,meta)
    meta['scope']='Conditional MoE FFN work/dependency contract with paid shared scalar gate; cycle timing qualification evaluated separately; not checkpoint/silicon/full LLM tokens per second'
    children=[[] for _ in g.nodes]
    for n in g.nodes:
        for d in n.deps:children[d].append(n.id)
    # One context holds each vector's read/ops/write sequence. The phases
    # share actual SRAM budgets, not distinct free ports or contexts.
    contexts=[];context_for={};context_phase={}
    for n in g.nodes:
        if n.kind!='vector':continue
        if len(n.deps)!=1:raise ValueError('Unrecognised vector input contract')
        before=g.nodes[n.deps[0]];after=[g.nodes[i] for i in children[n.id]]
        if before.kind!='sram_read' or len(children[before.id])!=1 or len(after)!=1 or after[0].kind!='sram_write':raise ValueError('Vector needs explicit exclusive read/ops/write context')
        ids=[before.id,n.id,after[0].id];cid=len(contexts);contexts.append(ids)
        for phase,i in enumerate(ids):context_for[i]=cid;context_phase[i]=phase
    # Recover every persistent tensor's physical pages in the frozen resident
    # layout, including unused experts/layers. No active-only compact remap.
    active_names={j['prefix']+'.'+suffix for j in meta['jobs'] for suffix in ('gate','up','down')}
    if meta['shared_gate_ledger']:active_names.add(f'layer{layer}.shared_router')
    alloc=defaultdict(int);pages={}
    for name,owners in layout['tensors'].items():
        for tile,spans in owners.items():
            parts=[]
            for tier,size in spans:
                lo=alloc[tile,tier];alloc[tile,tier]+=size
                if name not in active_names:continue
                for offset in range(lo,lo+size,1024):
                    page=offset//4096;bank=page%16;row=tier*4096+page//16;col=offset%4096//1024
                    if row//4096!=tier:raise ValueError('Physical tier capacity exceeded')
                    parts.append((tier,encoded(tile,bank,row,col)))
            if name in active_names:pages[name,tile]=parts
    kernels={r['node']:r for r in meta['kernel_ledger']};pools={};cursor=Counter();addresses={};request_identity=[]
    for semantic in meta['semantic_ledger']:
        e=semantic['expert'];prefix=f'layer{layer}.'+('shared' if e=='shared' else f'expert{e}');tile=semantic['tile'];kind=semantic['kind'];key=prefix,tile,kind
        if key not in pools:
            names=[prefix+'.gate',prefix+'.up'] if kind=='gate_up' else [prefix+'.down']
            pools[key]=sorted([a for name in names for a in pages[name,tile]],key=lambda a:a[0])
        rec=kernels[semantic['node']]
        for packet in rec['packet_ledger']:
            if packet['bytes']!=1024:raise ValueError('Partial DRAM transaction needs explicit byte mask')
            tier,address=pools[key][cursor[key]];cursor[key]+=1
            if tier!=packet['tier']:raise ValueError('Frozen tier order changed')
            addresses[packet['dram']]=address;request_identity.append(dict(node=packet['dram'],address=address,tile=tile,tier=tier,expert=e,projection=kind))
    for semantic in meta['shared_gate_ledger']:
        rec=kernels[semantic['node']];tile=semantic['tile'];pool=pages[semantic['tensor'],tile]
        if len(pool)!=len(rec['packet_ledger']):raise ValueError('Shared scalar physical coverage changed')
        for (tier,address),packet in zip(pool,rec['packet_ledger'],strict=True):
            if tier!=packet['tier']:raise ValueError('Shared scalar tier changed')
            addresses[packet['dram']]=address;request_identity.append(dict(node=packet['dram'],address=address,tile=tile,tier=tier,expert='shared_gate',projection='shared_router'))
    if len(set(addresses.values()))!=len(addresses) or sum(1024 for _ in addresses)!=meta['actual_dram_bytes']:raise ValueError('Lost, duplicated or aliased weights')
    if any(cursor[k]!=len(v) for k,v in pools.items()):raise ValueError('Incomplete persistent weight coverage')
    resources={};caps={};nodes=[];slaves={};master={}
    for rec in meta['kernel_ledger']:
        for block in rec['microtile_ledger']:
            ids=g.meta['coissued_nodes'][block['node']];slaves[block['node']]=ids
            for i in ids:master[i]=block['node']
    def resource(key):
        if key not in resources:resources[key]=len(resources)
        return resources[key]
    leases=[]
    defaults={'weight_fifo':262144,'return':65536,'receive':65536,'transmit':65536,'workspace':meta['budget']['expert_workspace_bytes'],'output':65536,'local_output':16384,'reduce_output':49152,'weight_descriptor':256,'return_descriptor':1024}
    for n in g.nodes:
        if n.kind=='join' and str(n.resource[0])=='native_return_latency':ticks=0
        else:ticks=ceil(n.ticks)
        rid=resource(tuple(n.resource));read=fifo=0
        if n.kind=='mac':
            read=sum(g.nodes[i].work for i in slaves[n.id] if g.nodes[i].kind=='sram_read');fifo=sum(g.nodes[i].work for i in slaves[n.id] if g.nodes[i].kind=='fifo_read')
            ticks=max(1,ceil(n.work/2000),ceil(read/256),ceil(fifo/500))
        vc=int(n.stage in ('combine','shared_gate_reduce'));target=n.resource[2] if n.kind=='link' else -1
        nodes.append(dict(id=n.id,kind=KINDS.index(n.kind),tile=n.tile,work=n.work,deps=list(n.deps),ticks=ticks,resource=rid,tier=n.tier,address=addresses.get(n.id,-1),context=context_for.get(n.id,-1),phase=context_phase.get(n.id,-1),master=master.get(n.id,-1),read=read,fifo=fifo,target=target,vc=vc,stage=n.stage))
        for key,amount,last in n.leases:
            if key[0].startswith('router'):continue # Actual port/VC flit credits below.
            cap=defaults.get(key[0])
            if cap is None:raise ValueError('Unknown private credit class')
            credit=resource(tuple(key));caps[credit]=cap;leases.append(dict(first=n.id,last=last,resource=credit,tile=key[1],bytes=amount,kind=key[0]))
    # Injection and physical input-port credits are distinct from long-lived
    # output/private SRAM leases. A flit retains its slot until all immediate
    # consumers start, covering flight, queuing and SRAM backpressure.
    router=[]
    for n in nodes:
        if n['kind']!=5:continue
        target=n['target'];source=n['tile'];port=0 if source==target-1 else 1 if source==target+1 else 2 if source==target-4 else 3
        consumers=children[n['id']]
        if not consumers:raise ValueError('Unconsumed physical flit')
        router.append(dict(first=n['id'],users=consumers,key=[target,port,n['vc']]))
    for n in nodes:
        links=[i for i in children[n['id']] if nodes[i]['kind']==5]
        if n['kind']==1 and links:router.append(dict(first=n['id'],users=links,key=[n['tile'],4,nodes[links[0]]['vc']]))
    result=dict(nodes=nodes,leases=leases,router=router,contexts=contexts,slaves=slaves,output=g.output,caps={str(k):v for k,v in caps.items()},resource_count=len(resources),fixed=g.meta['fixed_sram_bytes'],private_budget=g.meta['private_sram_budget_bytes'],meta=meta,contract=dict(tick_ns=.25,flit_bytes=32,vc_depth=8,vc_count=2,link_serial=4,flight=8,read=256,write=128,vector=16,hb=500,fifo=500,mac=2000,weight=262144,response=65536,one_vector_context=True,order='static',grain=grain,down=down,layer=layer,batch=len(routes),routing=routes,scope='Shared semantic builder, independent cycle executors; full MoE subgraph, not checkpoint numeric or silicon certification'))
    result['request_identity']=request_identity
    return result


def write_program(p,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    (out/'program.json').write_text(json.dumps(p,separators=(',',':'))+'\n')
    with (out/'nodes.tsv').open('w') as f:
        for n in p['nodes']:
            keys=('id','kind','tile','work','ticks','resource','tier','address','context','phase','master','read','fifo','target','vc')
            f.write(' '.join(map(str,[n[k] for k in keys]+[len(n['deps'])]+n['deps']))+'\n')
    for name,keys in (('leases',('first','last','resource','tile','bytes')),):
        (out/(name+'.tsv')).write_text(''.join(' '.join(str(r[k]) for k in keys)+'\n' for r in p[name]))
    (out/'router.tsv').write_text(''.join(' '.join(map(str,[r['first']]+r['key']+[len(r['users'])]+r['users']))+'\n' for r in p['router']))
    (out/'contexts.tsv').write_text(''.join(' '.join(map(str,ids))+'\n' for ids in p['contexts']))
    (out/'resources.tsv').write_text(str(p['resource_count'])+' '+str(p['private_budget'])+'\n'+' '.join(map(str,p['fixed']))+'\n'+''.join(f'{k} {v}\n' for k,v in p['caps'].items()))
