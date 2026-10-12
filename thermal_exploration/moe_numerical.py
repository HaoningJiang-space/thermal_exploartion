"""Small numerical semantics check; never used as a performance workload.

Inputs/weights are deterministic small tensors, selected experts and routed
probabilities are captured. The candidate interprets the graph's shard/token
ledger; the reference uses full matrices separately for each routed token.
FP32 accumulators, BF16 gated-state stores in the BF16 case. Shared sigmoid
weights are deterministic test tensors: not checkpoint activation validation.
"""
from collections import defaultdict
import numpy as np


def bf16(x):
    x=np.asarray(x,dtype=np.float32)
    bits=x.view(np.uint32)
    return ((bits+np.uint32(0x7fff)+((bits>>16)&1))&np.uint32(0xffff0000)).view(np.float32)


def check_ledger(c,routes,meta):
    """Independent token/row/K coverage, weight slot and event binding audit."""
    expected={e:[t for t,row in enumerate(routes) if e in row] for e in set(e for row in routes for e in row)}
    if meta.get('selected_experts') is not None:expected={e:t for e,t in expected.items() if e in meta['selected_experts']}
    if meta.get('include_shared',True):expected['shared']=list(range(len(routes)))
    d=c['hidden_size'];actual=defaultdict(list)
    kernels={rec['node']:rec for rec in meta['kernel_ledger']}
    if meta.get('shared_gate_ledger'):
        cursor=0
        for rec in sorted(meta['shared_gate_ledger'],key=lambda r:r['input_interval']):
            lo,hi=rec['input_interval']
            if lo!=cursor or rec['tokens']!=list(range(len(routes))) or kernels[rec['node']]['mac_flops']!=2*(hi-lo)*len(routes):raise ValueError('Shared scalar semantic coverage changed')
            cursor=hi
        if cursor!=d:raise ValueError('Shared scalar input coverage incomplete')
    for rec in meta['semantic_ledger']:
        e=rec['expert'];width=c['shared_expert_intermediate_size'] if e=='shared' else c['moe_intermediate_size']
        if rec['tokens']!=expected[e] or len(set(rec['tokens']))!=len(rec['tokens']):raise ValueError('Numerical token binding changed')
        lo,hi=rec['intermediate']
        if not 0<=lo<hi<=width:raise ValueError('Numerical K shard changed')
        if rec['kind']=='gate_up':
            work=4*d*(hi-lo)*len(rec['tokens'])
            actual[e,'gate'].append((lo,hi))
        else:
            first,last=rec['rows']
            if not 0<=first<last<=d:raise ValueError('Numerical output row changed')
            slots=[None if e=='shared' else routes[t].index(e) for t in rec['tokens']]
            if rec['routing_slots']!=slots:raise ValueError('Numerical routing weight binding changed')
            if 'accumulate_node' not in rec:raise ValueError('Local accumulation event missing')
            work=2*(last-first)*(hi-lo)*len(rec['tokens'])
            for row in range(first,last):actual[e,row].append((lo,hi))
        if kernels[rec['node']]['mac_flops']!=work:raise ValueError('Numerical event work changed')
    for e in expected:
        width=c['shared_expert_intermediate_size'] if e=='shared' else c['moe_intermediate_size']
        for row in ['gate']+list(range(d)):
            cursor=0
            for first,last in sorted(actual[e,row]):
                if first!=cursor:raise ValueError('Numerical shard coverage missing or duplicated')
                cursor=last
            if cursor!=width:raise ValueError('Numerical shard coverage missing or duplicated')


def compare(c,routes,probabilities,meta,dtype='FP32',seed=20261011,accumulation='blas'):
    check_ledger(c,routes,meta)
    if dtype not in ('FP32','BF16'):raise ValueError('Unknown numerical precision')
    if accumulation not in ('blas','fixed_k'):raise ValueError('Unknown numerical accumulation contract')
    q=bf16 if dtype=='BF16' else lambda x:np.asarray(x,np.float32)
    rng=np.random.default_rng(seed);b=len(routes);d=c['hidden_size'];h=c['moe_intermediate_size'];hs=c['shared_expert_intermediate_size']
    x=q(rng.normal(0,.2,(b,d)));prob=q(probabilities)
    if prob.shape!=(b,c['num_experts_per_tok']):raise ValueError('Captured probability shape')
    weights={}
    for e in [j['expert'] for j in meta['jobs']]:
        width=hs if e=='shared' else h
        weights[e]=[q(rng.normal(0,.04,(width,d))),q(rng.normal(0,.04,(width,d))),q(rng.normal(0,.04,(d,width)))]
    shared_router=q(rng.normal(0,.04,(d,)))
    shared_scores=x@shared_router
    shared_prob=q(1/(1+np.exp(-shared_scores)))
    candidate_shared_prob=shared_prob
    if meta.get('shared_gate_ledger'):
        parts=[np.einsum('bk,k->b',x[:,r['input_interval'][0]:r['input_interval'][1]],shared_router[r['input_interval'][0]:r['input_interval'][1]],dtype=np.float32,optimize=False) for r in meta['shared_gate_ledger']]
        candidate_scores=np.sum(parts,axis=0,dtype=np.float32)
        np.testing.assert_allclose(candidate_scores,shared_scores,rtol=2e-4,atol=2e-6)
        candidate_shared_prob=q(1/(1+np.exp(-candidate_scores)))
    def gated(g,u):return q((g/(1+np.exp(-g)))*u)
    def linear(x,w):
        # Freeze FP32 contraction order across token GEMV and grouped GEMM.
        # BLAS remains the exact legacy default; no tolerance is relaxed.
        return np.einsum('bk,mk->bm',np.atleast_2d(x),w,dtype=np.float32,optimize=False) if accumulation=='fixed_k' else np.atleast_2d(x)@w.T
    reference=np.zeros((b,d),np.float32)
    for token,row in enumerate(routes):
        for slot,e in enumerate(row+['shared']):
            if e not in weights:continue
            wg,wu,wd=weights[e]
            hidden=gated(linear(x[token],wg)[0],linear(x[token],wu)[0]) if accumulation=='fixed_k' else gated(wg@x[token],wu@x[token])
            scale=shared_prob[token] if e=='shared' else prob[token,slot]
            reference[token]+=scale*(linear(hidden,wd)[0] if accumulation=='fixed_k' else wd@hidden)
    hidden={e:np.zeros((b,hs if e=='shared' else h),np.float32) for e in weights}
    for rec in meta['semantic_ledger']:
        if rec['kind']!='gate_up':continue
        e=rec['expert'];tokens=rec['tokens'];lo,hi=rec['intermediate'];wg,wu,_=weights[e]
        hidden[e][np.ix_(tokens,range(lo,hi))]=gated(linear(x[tokens],wg[lo:hi]),linear(x[tokens],wu[lo:hi]))
    local=np.zeros((16,b,d),np.float32)
    for rec in meta['semantic_ledger']:
        if rec['kind']!='down':continue
        e=rec['expert'];tokens=rec['tokens'];lo,hi=rec['intermediate'];first,last=rec['rows']
        partial=linear(hidden[e][tokens,lo:hi],weights[e][2][first:last,lo:hi])
        scales=candidate_shared_prob[tokens] if e=='shared' else np.array([prob[t,slot] for t,slot in zip(tokens,rec['routing_slots'])],np.float32)
        local[rec['tile']][np.ix_(tokens,range(first,last))]+=partial*scales[:,None]
    candidate=np.sum(local,axis=0,dtype=np.float32)
    np.testing.assert_allclose(candidate,reference,rtol=2e-4,atol=2e-6)
    return dict(status='PASS_NUMERICAL',dtype=dtype,seed=seed,accumulation=accumulation,shape=dict(batch=b,hidden=d,intermediate=h,shared=hs),
        max_absolute_error=float(np.max(np.abs(candidate-reference))),relative_l2_error=float(np.linalg.norm(candidate-reference)/max(np.linalg.norm(reference),1e-30)),
        tolerance=dict(rtol=2e-4,atol=2e-6),captured_routing_probabilities=True,
        scope='Deterministic small tensors; graph shard/token/weight-slot semantics, FP32 accumulation and BF16 storage; not checkpoint numerical inference or performance')
