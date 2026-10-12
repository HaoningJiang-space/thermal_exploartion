"""Graph reconstruction of the detailed tensor contract, no latency fitting.

Same tasks, refs, input groups, writes, reduction casts. Packet vs32B-flit
transport and eager vs spread operand service remain explicit differences.
"""
from collections import Counter,defaultdict
from math import ceil
from .decode_graph import Graph,execute


def tensor_graph(model):
    c=model['contract'];g=Graph(c['packet_bytes'],True);g.meta.update(fluid_ticks=True,coissued_nodes={},detailed_waits=True)
    inputs={}
    for group in model['inputs']:
        targets=group['targets'];source=group['source']
        inputs[group['id']]=g.broadcast(source,targets,group['bytes'],stage='input') if any(t!=source for t in targets) else {source:g.join(())}
    delivered={};issued={};cumulative=Counter();rate=c['fluid_service_tb_s']*1000*.25/16
    for request in model['requests']:
        tile=request['tile'];n=request['size'];old=cumulative[tile];cumulative[tile]+=n
        mem=g.add('dram',tile,n,resource=('dram',tile),ticks=ceil(cumulative[tile]/rate)-ceil(old/rate),stage='memory')
        arrive=g.add('join',tile,0,(mem,),('native_return_latency',mem),26,'memory')
        hb=g.add('hb',tile,n,(arrive,),('hb',tile),n/500,'memory')
        g.lease(mem,hb,('return',tile),n);delivered[request['id']]=hb;issued[request['id']]=mem
    terminals={};uses=defaultdict(list)
    for task in model['tasks']:
        tile=task['tile'];read=task['k_count']*c['batch']*2+(task['m_count']*c['batch']*4 if task['parent']>=0 else 0)
        write=task['m_count']*c['batch']*4;weight=task['m_count']*task['k_count']*2
        deps=[delivered[r] for r in task['requests']]+[inputs[task['input_group']][tile]]+([terminals[task['parent']]] if task['parent']>=0 else [])
        duration=max(1,ceil(task['flops']/c['mac_flops_per_tick']),ceil(read/256),ceil(write/128),ceil(weight/500))
        mac=g.add('mac',tile,task['flops'],deps,('mac',tile),duration,'tensor_mac')
        rd=g.add('sram_read',tile,read,deps,('read',tile),ceil(read/256),'tensor_operand')
        wr=g.add('sram_write',tile,write,deps,('write',tile),ceil(write/128),'tensor_partial')
        fifo=g.add('fifo_read',tile,weight,deps,('fifo_consume',tile),ceil(weight/500),'tensor_operand')
        g.meta['coissued_nodes'][mac]=[rd,wr,fifo];terminals[task['id']]=mac
        for rid in task['requests']:uses[rid].append(mac)
    for request in model['requests']:
        last=g.join(uses[request['id']],'last_weight_reference')
        if len(uses[request['id']])!=request['refs']:raise ValueError('Tensor reference count')
        g.lease(issued[request['id']],last,('weight_fifo',request['tile']),request['size'])
    outputs=[]
    for reduction in model['reductions']:
        producers={}
        for tile in reduction['producers']:
            hits=[t for t in model['tasks'] if t['tile']==tile and t['final'] and t['m_start']<=reduction['row']<t['m_start']+t['m_count']]
            if len(hits)!=1:raise ValueError('Tensor output binding')
            producers[tile]=terminals[hits[0]['id']]
        outputs.append(g.collective(reduction['root'],producers,reduction['bytes'],'tensor_reduce',preallocated_sources=True,root_cast=True,native_leaves=True))
    g.output=outputs;g.meta.update(fixed_sram_bytes=[v+c['metadata_reserve'] for v in c['static_sram_per_tile']],private_sram_budget_bytes=c['sram_per_tile'],buffer_caps={'weight_fifo':c['weight_buffer'],'return':c['response_buffer'],'output':c['reduce_buffer']})
    return g


def compare_native(model,result):
    g=tensor_graph(model);z=execute(g)
    if z['activity']['mac']!=model['contract']['mac_flops'] or z['activity']['dram']!=model['contract']['dram_bytes']:raise ValueError('Tensor graph work mismatch')
    native=result['sram_activity']
    for kind,key in (('sram_read','read_bytes'),('sram_write','write_bytes'),('vector','vector_ops'),('fifo_read','fifo_operand_bytes')):
        if z['activity'].get(kind,0)!=native[key]:raise ValueError('Tensor SRAM/vector work mismatch: '+kind)
    if z['activity']['link']!=sum(result['byte_hops'].values()):raise ValueError('Tensor NoC work mismatch')
    error=z['time_us']/result['time_us']-1
    return dict(graph_us=z['time_us'],detailed_us=result['time_us'],relative_error=error,absolute_target_met=abs(error)<=.10,validation=z['validation'],byte_hops=z['activity']['link'],events=z['events'],nodes=[vars(n) for n in g.nodes],meta=g.meta,scope='Same tensor task/work; different packet/flit and eager/spread port scheduling; no full MoE qualification')
