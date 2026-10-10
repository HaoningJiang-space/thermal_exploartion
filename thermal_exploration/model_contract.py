"""Structural BF16 contracts, independent of performance/thermal assumptions."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    'llama_b1_c2k': ('llama31_8b', 1, 2048),
    'llama_b1_c32k': ('llama31_8b', 1, 32768),
    'llama_b4_c8k': ('llama31_8b', 4, 8192),
    'qwen_b1_c2k': ('qwen15_moe', 1, 2048),
    'qwen_b2_c8k': ('qwen15_moe', 2, 8192),
    'qwen_b8_c2k': ('qwen15_moe', 8, 2048),
}


def load_model(name):
    c = json.loads((ROOT/'configs/models'/f'{name}.json').read_text())
    if c['dtype_bytes'] != 2 or c['hidden_size'] % c['num_attention_heads']:
        raise ValueError('Invalid BF16/head contract')
    return c


def tensors(c):
    """All resident parameter tensors, including untied vocabulary and biases.

    Qwen shared width5632 is ONE shared MLP, equivalent in width to4 routed
    experts of1408. Counting four5632-wide MLPs would quadruple it incorrectly.
    """
    d = c['hidden_size']; v = c['vocab_size']
    kv = c['num_key_value_heads']*d//c['num_attention_heads']
    result = [dict(name='embedding', elements=v*d, family='embedding', layer=-1)]
    if not c['tie_word_embeddings']:
        result.append(dict(name='lm_head', elements=v*d, family='linear', layer=-1))
    result.append(dict(name='final_norm', elements=d, family='norm', layer=-1))
    for layer in range(c['num_hidden_layers']):
        def add(name, size, family='linear', expert=-1):
            result.append(dict(name=f'layer{layer}.{name}', elements=size, family=family, layer=layer, expert=expert))
        for name, out in [('q', d), ('k', kv), ('v', kv), ('o', d)]:
            add(name, d*out)
            if c['model_type']=='qwen2_moe' and name!='o':
                add(name+'.bias', out, 'bias')
        add('input_norm', d, 'norm'); add('post_norm', d, 'norm')
        if c['model_type']=='llama':
            for name in ('gate', 'up', 'down'):
                add(name, d*c['intermediate_size'])
        else:
            add('router', d*c['num_experts'], 'router')
            add('shared_router', d, 'router')
            for name in ('gate', 'up', 'down'):
                add('shared.'+name, d*c['shared_expert_intermediate_size'], 'shared')
            for expert in range(c['num_experts']):
                for name in ('gate', 'up', 'down'):
                    add(f'expert{expert}.'+name, d*c['moe_intermediate_size'], 'routed', expert)
    for t in result:
        t['bytes'] = t['elements']*c['dtype_bytes']
    return result


def capacity(c, batch, context, steps=128, dram_bytes=32*2**30, allow_context_extension=False):
    if min(batch, context, steps) < 1:
        raise ValueError('Nonpositive Decode workload')
    rows = tensors(c)
    weights = sum(t['bytes'] for t in rows)
    head_dim = c['hidden_size']//c['num_attention_heads']
    kv_per_position = 2*c['num_hidden_layers']*c['num_key_value_heads']*head_dim*c['dtype_bytes']*batch
    # Reserve page-rounded KV for the largest (after-step128) context. Bounded
    # IO/logit workspace is in DRAM in addition to the fixed36MiB private SRAM.
    kv = ((kv_per_position*(context+steps)+4095)//4096)*4096
    tensor_padding = sum((-t['bytes']) % 4096 for t in rows)
    workspace = 64*2**20
    metadata = ((len(rows)*64 + c['num_hidden_layers']*batch*16 + 4095)//4096)*4096
    total = weights+tensor_padding+kv+workspace+metadata
    context_valid = context+steps <= c['max_position_embeddings']
    return dict(model=c['name'], batch=batch, context=context, decode_steps=steps,
        parameter_elements=sum(t['elements'] for t in rows), resident_weights_bytes=weights,
        tensor_padding_bytes=tensor_padding, all_layer_kv_bytes=kv,
        kv_bytes_per_added_position=kv_per_position, dram_workspace_bytes=workspace,
        metadata_bytes=metadata, total_resident_bytes=total, dram_capacity_bytes=dram_bytes,
        dram_headroom_bytes=dram_bytes-total, capacity_feasible=total<=dram_bytes,
        published_context_valid=context_valid, context_extension_assumed=not context_valid and allow_context_extension,
        runnable=total<=dram_bytes and (context_valid or allow_context_extension),
        private_sram_bytes=36*2**20, precision='BF16',
        scope='Resident BF16 weights, all-layer K/V through128 Decode steps; no offload or quantization')


def route_replay(source, output, steps=128, max_batch=8):
    """Import public HDA Qwen2 routing WITHOUT pretending it is Qwen1.5 data.

    Select first24 layers, retain first60 expert IDs, take the first4 surviving
    choices. This explicit projection is a routing sensitivity, not captured
    Qwen1.5 inference. Original traces have64 experts, top8 and28 layers.
    """
    raw = Path(source).read_bytes(); data = json.loads(raw)
    training_records=256
    need = training_records+steps*max_batch
    result = []; training_counts=[]
    for layer in range(24):
        original = data[str(layer)]
        if len(original)<need:
            raise ValueError('Insufficient public route records; never silently repeat')
        layer_routes = []; counts=Counter()
        for j,row in enumerate(original[:need]):
            if len(row)!=8 or len(set(row))!=8 or any(not 0<=x<64 for x in row):
                raise ValueError('Invalid source route contract')
            projected = [int(x) for x in row if x<60][:4]
            if len(projected)!=4:
                raise ValueError('Projection loses too many selected experts')
            if j<training_records:counts.update(projected)
            else:layer_routes.append(projected)
        result.append(layer_routes)
        training_counts.append([counts[e]/training_records for e in range(60)])
    report = dict(source_repo='https://github.com/PKU-SEC-Lab/HDA-MoE-TCAD26',
        source_commit='56ea3725b2c621d4aea248f16345c34f5e06b8ed',
        source_file='expert_trace/qwen/experts_reasoning_qwen.json', source_sha256=hashlib.sha256(raw).hexdigest(),
        source_shape=dict(layers=28, experts=64, topk=8),
        projection='first24 layers; drop IDs60–63; retain first4 surviving selections; contiguous records; no modulo remap',
        training_records=training_records,training_expected_activations=training_counts,
        scope='Public Qwen2 trace projected as an explicitly assumed Qwen1.5-shaped route sensitivity; NOT a Qwen1.5 model capture',
        model_matched_capture=False, steps=steps, max_batch=max_batch, routes=result)
    Path(output).write_text(json.dumps(report, separators=(',', ':'))+'\n')
    return report


def expected_mac_flops(c,batch,context,routes=None):
    """Independent mathematical work ledger, not obtained from event counts."""
    total=0
    counts=[Counter(e for row in layer for e in row) for layer in routes] if routes is not None else None
    for t in tensors(c):
        if t['family'] in ('linear','shared','router'):
            total+=2*t['elements']*batch
        elif t['family']=='routed':
            if counts is None:raise ValueError('MoE work requires immutable routing')
            total+=2*t['elements']*counts[t['layer']][t['expert']]
    total+=4*batch*(context+1)*c['num_attention_heads']*(c['hidden_size']//c['num_attention_heads'])*c['num_hidden_layers']
    return total
