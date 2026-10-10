"""Same-tensor crossover for the existing H3 packet-DAG abstraction.

Do not calibrate away disagreement. This intentionally retains H3 serialized
SRAM phases so qualification exposes that difference from H2's concurrent
operand/accumulator ports. Packet size and budgets are recorded explicitly.
"""
from collections import Counter
from math import ceil
from .decode_graph import Graph, execute
from .tensor_execution import build, CASES


def graph(case,refined=False):
    model = build(CASES[case]); c = model['contract']; g = Graph(256,True) if refined else Graph()
    inputs = {}
    for x in model['inputs']:
        arrivals = g.broadcast(x['source'], x['targets'], x['bytes'], stage='input')
        for tile, node in arrivals.items(): inputs[x['id'], tile] = node
    tasks = {}
    for task in model['tasks']:
        tile = task['tile']; size = len(task['requests'])*1024
        deps = (inputs[task['input_group'], tile],)
        parent = tasks.get(task['parent'])
        tasks[task['id']] = g.memory_compute(tile, size, task['flops'], deps, parent, stage='tensor')
    for red in model['reductions']:
        row = red['row']; producers = {}
        for tile in red['producers']:
            relevant = [t for t in model['tasks'] if t['tile']==tile and t['final'] and t['m_start']<=row<t['m_start']+t['m_count']]
            if len(relevant)!=1: raise ValueError('Unmatched final partial')
            producers[tile] = tasks[relevant[0]['id']]
        end = g.collective(red['root'], producers, red['bytes'], 'tensor_reduce')
        cast = g.add('vector',red['root'],red['bytes']//4,(end,),ticks=ceil(red['bytes']/4/16),stage='cast')
        stored=g.add('sram_write',red['root'],red['bytes']//2,(cast,),('write',red['root']),ceil(red['bytes']/2/128),'output_cast_store')
        g.output.append(stored)
    g.meta = dict(contract=c, buffer_caps={'weight':c['weight_buffer'],'return':c['response_buffer'],'output':c['reduce_buffer']},
        fixed_sram_bytes=[n+65536+16384-2560 for n in c['static_sram_per_tile']],private_sram_budget_bytes=c['sram_per_tile'],
        output_ownership='canonical equal output shards, as H2',
        weight_bytes=c['dram_bytes'], mac_flops=c['mac_flops'],
        difference=f'H3:up-to32KiB memory-service abstraction,{g.packet_bytes}B packets,decoupled_flight={g.decoupled_link_latency},serialized SRAM/MAC phases; H2:actual1024B requests,32B flits,overlapping MAC ports')
    return g


def compare(case, detail,refined=False):
    g = graph(case,refined); r = execute(g)
    activity = r['activity']; c = g.meta['contract']
    if sum(n.work for n in g.nodes if n.stage=='output_cast_store')!=c['output_bytes']:raise ValueError('Missing BF16 output stores')
    if activity['dram']!=c['dram_bytes'] or activity['mac']!=c['mac_flops']:
        raise ValueError('Cross-fidelity workload mismatch')
    for node in g.nodes:
        if node.kind=='mac' and node.work==0: raise ValueError('Empty useful task')
    expected_link_bytes = detail.get('byte_hops',detail.get('noc_byte_hops'))
    if expected_link_bytes is None:raise ValueError('H2 detail has no NoC byte-hop ledger')
    actual_link_bytes = activity.get('link',0)
    error = r['time_us']/detail['time_us']-1
    windows = {}
    for kind in ('dram','hb','link','sram_read','sram_write','mac','vector'):
        events = [e for e in r['events'] if e['kind']==kind]
        windows[kind] = (max(e['finish_tick'] for e in events)-min(e['start_tick'] for e in events))*.00025 if events else 0
    return dict(case=case,refined_packet_model=refined,contract=c, h2_time_us=detail['time_us'], h3_time_us=r['time_us'],
        latency_relative_error=error, ten_percent_latency_target_met=abs(error)<=.1,
        same_weight_bytes=True, same_mac_flops=True, same_noc_byte_hops=actual_link_bytes==expected_link_bytes,
        h2_noc_byte_hops=expected_link_bytes,h3_noc_byte_hops=actual_link_bytes,
        h3_stage_windows_us=windows, h3_sram_credit_probes=r['credit_stall_probes'],
        h3_buffer_high=r['buffer_high'], h3_sram_activity={k:activity.get(k,0) for k in ('sram_read','sram_write')}, h2_sram_activity=detail['sram_activity'],
        same_total_private_capacity=True,persistent_input_partial_output_charged=True,identical_router_fidelity=False, output_ownership=g.meta['output_ownership'],
        abstraction_difference=g.meta['difference'], critical_path=r['critical_path'],
        scope='Qualification experiment; no fitting, no claim that finite staging granularity is identical')


def main():
    import argparse,json
    from pathlib import Path
    from .run import revision
    ap=argparse.ArgumentParser();ap.add_argument('--h2',required=True);ap.add_argument('--output',required=True);ap.add_argument('--legacy-packets',action='store_true');a=ap.parse_args()
    out=Path(a.output)
    if out.exists():raise ValueError('Never overwrite qualification evidence')
    detailed={r['name']:r for r in json.loads(Path(a.h2).read_text()) if r['status']=='PASS'}
    rows=[compare(name,detailed[name],not a.legacy_packets) for name in ('row_blocked_k','column_blocked_m','2d_blocked_k')]
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(dict(source_commit=revision(),records=rows,scope='Matched frozen tensors only; no fitting'),indent=2)+'\n')
    for r in rows:print(r['case'],r['latency_relative_error'],r['ten_percent_latency_target_met'])


if __name__=='__main__':main()
