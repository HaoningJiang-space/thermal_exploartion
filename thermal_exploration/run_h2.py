"""H2-A causal tensor execution and independent event replay."""
import argparse
from collections import Counter, defaultdict
from math import ceil
import csv
from datetime import datetime, timezone
import heapq
import json
from pathlib import Path
import subprocess
import sys

from . import hb_trace
from .run import revision
from .run_g4 import RAMULATOR_COMMIT, verify_upstream
from .run_organization import check_commands
from .tensor_execution import CASES, build, write_contract, reduction_tasks


def rows(path):
    with Path(path).open() as f:
        for r in csv.DictReader(f):
            yield {k: (v if k == 'kind' else int(v)) for k, v in r.items()}


def native_build(root, out):
    source = Path(__file__).resolve().parents[1] / 'native/tensor_execution_driver.cpp'
    exe = out / 'tensor-driver'
    cmd = ['g++', '-std=c++20', '-O2', '-I'+str(root/'src'),
           '-I'+str(root/'ext/fmt/include'), '-I'+str(root/'ext/yaml-cpp/include'),
           str(source), '-L'+str(root), '-lramulator', '-Wl,-rpath,'+str(root), '-o', str(exe)]
    with (out/'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=log, check=True)
    return exe


def validate(case, model, dram):
    """Replay IDs, dependencies, traffic and aggregate service independently."""
    c = model['contract']; d = json.loads((case/'run-driver.json').read_text())
    rd = list(rows(case/'run-reads.csv')); tasks = list(rows(case/'run-tasks.csv'))
    if len(rd) != c['requests'] or len(tasks) != c['tasks']:
        raise ValueError('Lost or duplicated requests/tasks')
    uses = defaultdict(list)
    for expected, actual in zip(model['tasks'], tasks):
        if any(actual[k] != expected[k] for k in ('id','tile','m_start','k_start','parent','flops','final')):
            raise ValueError('Task identity/work changed')
        read=(0 if c.get('stream_fifo') else expected['m_count']*expected['k_count']*2)+expected['k_count']*c['batch']*2+(expected['m_count']*c['batch']*4 if expected['parent']>=0 else 0)
        write=expected['m_count']*c['batch']*4
        fifo=(expected['m_count']*expected['k_count']*2+499)//500 if c.get('stream_fifo') else 0
        if actual['finish']-actual['start'] != max(1,ceil(expected['flops']/c['mac_flops_per_tick']),(read+255)//256,(write+127)//128,fifo):
            raise ValueError('MAC service time')
        for rid in expected['requests']: uses[rid].append(actual)
    for expected, actual in zip(model['requests'], rd):
        if any(actual[k] != expected[k] for k in ('id','tile','address','refs')):
            raise ValueError('Request identity changed')
        if not 0 <= actual['accepted'] < actual['depart'] <= actual['hb_first'] < actual['hb_done']:
            raise ValueError('Noncausal DRAM/HB return')
        if len(uses[actual['id']]) != actual['refs'] or actual['last_use'] != max(t['finish'] for t in uses[actual['id']]):
            raise ValueError('Wrong weight lifetime/refcount')
    request_records = [dict(r, source_tile=r['tile']) for r in model['requests']]
    independent=c.get('command_domains_per_tile',1)==2
    if independent:
        for r in request_records:r['addr_vec']=hb_trace.command_domain_vector(r['addr_vec'])
    # DeviceUnderTest replays DRAM-cycle commands. Request traces remain in
    # logic ticks; convert only this validator view, preserving original IDs.
    events = [dict(r,completed=r['depart']) for r in rd]
    channels=32 if independent else 16
    # Command names are strings, unlike the numerical event traces above.
    def commands(path):
        with path.open() as f: yield from csv.DictReader(f)
    merged = heapq.merge(*(commands(case/f'transaction-commands.ch{ch}.csv') for ch in range(channels)),key=lambda x:int(x['clock']))
    if c['ideal_memory'] or c.get('fluid_memory'):
        command_validation=check_commands(dram, [], [], merged)
        command_validation['scope']='No command execution for synthetic memory backend; shared transport/compute semantics only, not independent device validation'
    else:command_validation = check_commands(dram, request_records, events, merged,c['logic_ticks_per_dram_tick'],channels)
    input_events = {(r['group'],r['tile']):r for r in rows(case/'run-inputs.csv')}
    for e, t in zip(model['tasks'],tasks):
        ready = input_events[e['input_group'],e['tile']]['last_tick']
        ready = max(ready, *(rd[r]['hb_done'] for r in e['requests']))
        if e['parent'] >= 0: ready = max(ready,tasks[e['parent']]['finish'])
        if t['start'] < ready: raise ValueError('MAC consumed missing operand')
    for tile in range(16):
        ordered=sorted((t for t in tasks if t['tile']==tile),key=lambda t:t['start'])
        if any(a['finish']>b['start'] for a,b in zip(ordered,ordered[1:])):
            raise ValueError('Overlapping MAC tasks')
    injections = {(r['kind'],r['group'],r['flit'],r['tile']):r['tick'] for r in rows(case/'run-inject.csv')}
    sinks = {(r['kind'],r['group'],r['flit'],r['child'],r['tile']):r['tick'] for r in rows(case/'run-sink.csv')}
    links = {}; previous = {}; byte_hops=Counter(); hot=Counter()
    for r in rows(case/'run-noc.csv'):
        key=(r['kind'],r['group'],r['flit'],r['source'],r['target'])
        if key in links or r['bytes'] != 32: raise ValueError('Repeated/invalid flit')
        if abs(r['source']//4-r['target']//4)+abs(r['source']%4-r['target']%4)!=1:
            raise ValueError('Nonphysical mesh hop')
        edge=(r['source'],r['target'])
        if not c['ideal_noc'] and (r['start']<previous.get(edge,-4)+4 or r['finish']!=r['start']+8):
            raise ValueError('Link serialization/latency exceeded')
        if c['ideal_noc'] and r['finish']!=r['start']:raise ValueError('Ideal transport definition')
        previous[edge]=r['start']; links[key]=r
        byte_hops[r['kind']]+=32; hot[edge]+=32
    expected_links=set(); expected_inject=set(); expected_sink=set()
    for g in model['inputs']:
        for i in range(g['bytes']//32):
            if g['children'][g['source']]:expected_inject.add(('X',g['id'],i,g['source']))
            for a in range(16):
                for b in g['children'][a]:
                    key=('X',g['id'],i,a,b);expected_links.add(key);r=links[key]
                    before=injections['X',g['id'],i,a] if a==g['source'] else links['X',g['id'],i,g['parent'][a],a]['finish']
                    if r['start']<before:raise ValueError('Forward before arrival')
            for tile in g['targets']:
                if tile==g['source']:continue
                key=('X',g['id'],i,g['source'],tile);expected_sink.add(key)
                if sinks[key]<links['X',g['id'],i,g['parent'][tile],tile]['finish']:
                    raise ValueError('Input received before transport')
        for tile in g['targets']:
            e=input_events[g['id'],tile]
            last=0 if tile==g['source'] else max(sinks['X',g['id'],i,g['source'],tile] for i in range(g['bytes']//32))
            if e['bytes']!=g['bytes'] or e['last_tick']!=last:raise ValueError('Input join incomplete')
    jobs=list(rows(case/'run-vector.csv')); jobmap={(j['group'],j['tile']):j for j in jobs}
    expected_jobs=set(); totals=Counter()
    local_ready={}
    for g in model['reductions']:
        for tile in g['producers']:
            hits=reduction_tasks(model,g,tile)
            local_ready[g['id'],tile]=max(tasks[i]['finish'] for i in hits)
        for tile in g['nodes']:
            count=len(g['children'][tile])+int(tile in g['producers'])
            if g['children'][tile] or tile==g['root']:
                expected_jobs.add((g['id'],tile));j=jobmap[g['id'],tile]
                ready=local_ready.get((g['id'],tile),0)
                for child in g['children'][tile]:
                    ready=max(ready,*(sinks['R',g['id'],i,child,tile] for i in range(g['bytes']//32)))
                if j['start']<ready or j['finish']<=j['start']:raise ValueError('Reduction before partial arrival')
                expected=(count*g['bytes'],(count-1)*g['bytes']//4+(g['bytes']//4 if tile==g['root'] else 0),g['bytes']//2 if tile==g['root'] else g['bytes'])
                if tuple(j[k] for k in ('read_bytes','ops','write_bytes'))!=expected:raise ValueError('Reduction changed work')
                for k in ('read_bytes','ops','write_bytes'):totals[k]+=j[k]
                done=j['finish']
            else:done=local_ready[g['id'],tile]
            if tile!=g['root']:
                parent=g['parent'][tile]
                for i in range(g['bytes']//32):
                    expected_inject.add(('R',g['id'],i,tile));expected_sink.add(('R',g['id'],i,tile,parent))
                    key=('R',g['id'],i,tile,parent);expected_links.add(key)
                    if injections['R',g['id'],i,tile]<done or links[key]['start']<injections['R',g['id'],i,tile] or sinks['R',g['id'],i,tile,parent]<links[key]['finish']:
                        raise ValueError('Noncausal partial-result transport')
    if set(jobmap)!=expected_jobs or len(jobs)!=len(jobmap) or set(links)!=expected_links or set(injections)!=expected_inject or set(sinks)!=expected_sink:
        raise ValueError('Traffic/result conservation failed')
    for tile in range(16):
        ordered=sorted((j for j in jobs if j['tile']==tile),key=lambda j:j['start'])
        if any(a['finish']>b['start'] for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping vector jobs')
    service=Counter(); port_count=0
    for r in rows(case/'run-ports.csv'):
        port_count+=1
        if not 0<=r['read_bytes']<=256 or not 0<=r['write_bytes']<=128 or not 0<=r['vector_ops']<=16:
            raise ValueError('SRAM/vector service exceeded')
        if not 0<=r['weight_used']<=c['weight_buffer'] or not 0<=r['response_used']<=c['response_buffer'] or not 0<=r['reduce_used']<=c['reduce_buffer'] or not 0<=r['router_flits']<=80:
            raise ValueError('Buffer contract exceeded')
        if c['static_sram_per_tile'][r['tile']]+65536+r['weight_used']+r['response_used']+r['reduce_used']>c['sram_per_tile']:
            raise ValueError('Private SRAM exceeded')
        for k in ('read_bytes','write_bytes','vector_ops'):service[k]+=r[k]
        for k in ('fifo_ingress_bytes','fifo_operand_bytes'):
            if not 0<=r.get(k,0)<=500:raise ValueError('FIFO port exceeded')
            service[k]+=r.get(k,0)
    mac_read=sum((0 if c.get('stream_fifo') else e['m_count']*e['k_count']*2)+e['k_count']*c['batch']*2+(e['m_count']*c['batch']*4 if e['parent']>=0 else 0) for e in model['tasks'])
    mac_write=sum(e['m_count']*c['batch']*4 for e in model['tasks'])
    copies=0 if c.get('stream_fifo') else c['dram_bytes']
    if c.get('stream_fifo') and (service['fifo_ingress_bytes']!=c['dram_bytes'] or service['fifo_operand_bytes']!=c['weight_bytes']):
        raise ValueError('FIFO supply/consumption ledger does not close')
    if service['read_bytes']!=mac_read+totals['read_bytes']+len(injections)*32 or service['write_bytes']!=mac_write+totals['write_bytes']+len(sinks)*32+copies or service['vector_ops']!=c['reduction_adds']+c['output_casts']:
        raise ValueError('SRAM/vector aggregate accounting does not close')
    if sum(d['mac_states'].values())!=port_count or d['mac_flops']!=c['mac_flops'] or d['dram_bytes']!=c['dram_bytes']:
        raise ValueError('Activity/work accounting does not close')
    if port_count!=d['ticks']*16:raise ValueError('Missing resource ticks')
    duration=d['ticks']*.25
    if c['mac_flops']/duration/1000>c['compute_tflops']+.00001:raise ValueError('Compute upper bound violated')
    # Stage windows overlap; these values must not be added as a breakdown.
    result=dict(contract=c,driver=d,validation=('PASS: shared transport/input/task/port accounting; synthetic memory emits no request commands' if c.get('fluid_memory') else 'PASS: command legality/transaction identity, operand joins, MAC/vector serialization, physical link serialization, traffic and port accounting'),
        command_validation=command_validation,time_us=duration/1000,effective_tflops=c['mac_flops']/duration/1000,
        useful_dram_tb_s=c['weight_bytes']/duration/1000,physical_dram_tb_s=c['dram_bytes']/duration/1000,
        mac_utilization=c['mac_flops']/duration/1000/c['compute_tflops'],byte_hops=dict(byte_hops),max_directed_link_bytes=max(hot.values(),default=0),
        sram_activity=dict(service),stages_ns=dict(DRAM=max(r['depart'] for r in rd)-min(r['accepted'] for r in rd),
            HB=max(r['hb_done'] for r in rd)-min(r['hb_first'] for r in rd),
            NoC=(max(r['finish'] for r in links.values())-min(r['start'] for r in links.values()))*.25 if links else 0,
            MAC=(d['last_mac']-d['first_mac'])*.25,Reduction=(d['last_vector']-d['first_vector'])*.25),
        scope='Mode B T0 causal architecture model; assumed ports/timing, not measured HB device or numerical inference')
    result['stages_ns']['DRAM']*=.25;result['stages_ns']['HB']*=.25
    (case/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ramulator-root',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--shape',nargs=3,type=int,metavar=('M','N','BATCH'));ap.add_argument('--smoke',action='store_true');ap.add_argument('--cases',nargs='+',choices=CASES,default=[name for name in CASES if name not in ('row_fifo32','column_fifo32')])
    ap.add_argument('--compute-tflops',type=float,default=128);ap.add_argument('--sram-mib',type=float,default=36)
    ap.add_argument('--fluid-memory',action='store_true');ap.add_argument('--fluid-service',type=float,default=26.599);a=ap.parse_args()
    root=Path(a.ramulator_root).resolve();out=Path(a.output).resolve()
    if out.exists():raise ValueError('Never overwrite experimental evidence')
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=RAMULATOR_COMMIT:raise ValueError('Wrong Ramulator snapshot')
    verified=verify_upstream(root);out.mkdir(parents=True);sys.path[:0]=[str(root/'python'),str(root)]
    (out/'provenance.json').write_text(json.dumps(dict(source_commit=revision(),source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        ramulator_commit=RAMULATOR_COMMIT,upstream=verified,started=datetime.now(timezone.utc).isoformat(),smoke=a.smoke),indent=2)+'\n')
    exe=native_build(root,out);results=[]
    for name in a.cases:
        case=out/name;case.mkdir();settings=dict(CASES[name],compute_tflops=a.compute_tflops,sram_mib=a.sram_mib,fluid_memory=a.fluid_memory,fluid_service_tb_s=a.fluid_service)
        model=build(settings,*(a.shape or ((64,1024,8) if a.smoke else (1024,16384,32))))
        write_contract(model,case);dram,cfg=hb_trace.ramulator_config(root,case,2,refresh=True,independent_commands=model['contract']['command_domains_per_tile']==2)
        from .clock_contract import ClockContract
        (case/'clock-contract.json').write_text(json.dumps(ClockContract().validate_device(dram),indent=2)+'\n')
        (case/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
        with (case/'execution.log').open('w') as log:subprocess.run([str(exe),str(case/'config.json'),str(case),str(case/'run')],stdout=log,stderr=log,check=True)
        result=validate(case,model,dram);results.append(dict(name=name,**result))
        print(name,result['time_us'],result['effective_tflops'],flush=True)
    (out/'summary.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':main()
