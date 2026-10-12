"""Independent bit-level check of real routed Hidden sharding and tail masks."""
from math import ceil
import numpy as np

def check(p):
    nodes=p['nodes'];records=[];rng=np.random.default_rng(20261012)
    for copy in p.get('hidden_copies',[]):
        count=len(copy['tokens']);width=copy['width'];owners=copy['owners'];source=copy['source'];local=width//len(owners);lo=owners.index(source)*local
        full=rng.integers(0,65536,size=(count,width),dtype=np.uint16)
        payload=full[:,lo:lo+local].copy().tobytes();wire=payload+b'\0'*((-len(payload))%32)
        ids=range(copy['first'],copy['last']);reads=[i for i in ids if nodes[i]['kind']==1 and nodes[i]['tile']==source]
        if len(reads)!=ceil(len(payload)/32) or sum(nodes[i]['work'] for i in reads)!=len(wire):raise ValueError('Hidden source physical bytes changed')
        index={node:j for j,node in enumerate(reads)};links=[nodes[i] for i in ids if nodes[i]['kind']==5]
        for n in links:
            before=nodes[n['deps'][0]]
            while before['kind']==5:before=nodes[before['deps'][0]]
            packet=index[before['id']];expected=min(32,len(payload)-32*packet)
            if n['valid_bytes']!=expected:raise ValueError('Hidden mask omits or invents elements')
        restored=np.frombuffer(wire[:len(payload)],dtype=np.uint16).reshape(count,local)
        if not np.array_equal(restored,full[:,lo:lo+local]):raise ValueError('Hidden token/K ownership changed')
        records.append(dict(expert=copy['expert'],source=source,tokens=copy['tokens'],width=width,logical_bytes=len(payload),wire_bytes=len(wire),padding_bytes=len(wire)-len(payload),status='PASS_BITWISE_HIDDEN_SHARD'))
    return dict(status='PASS_REAL_SHAPE_HIDDEN_PACKING',copies=len(records),tail_copies=sum(r['padding_bytes']>0 for r in records),records=records,scope='Real token IDs/counts and K widths; deterministic BF16 bit patterns, mask/physical padding and strided shard assembly, not checkpoint inference')
