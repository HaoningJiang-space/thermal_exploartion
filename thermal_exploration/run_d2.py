"""Finite multi-tier execution discrimination; no new hardware/DSE/thermal loop."""
import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import heapq
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from .multitier import CASES,contract,request_identity,config,TierLegality,tier_timings
from .run_g4 import RAMULATOR_COMMIT,verify_upstream
from .run import revision


def native_build(root,out):
    source=Path(__file__).resolve().parents[1]/'native/multitier_task_driver.cpp'
    exe=out/'task-driver'
    cmd=['g++','-std=c++20','-O2','-I'+str(root/'src'),'-I'+str(root/'ext/fmt/include'),
         '-I'+str(root/'ext/yaml-cpp/include'),str(source),'-L'+str(root),'-lramulator','-Wl,-rpath,'+str(root),'-o',str(exe)]
    with (out/'build.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=log,check=True)
    return exe


def validate(case,dram,settings,rows):
    """Streaming validators avoid retaining millions of Python request dicts."""
    from tests.device_timings.harness import DeviceUnderTest
    c=contract(settings['task_bytes'],rows);d=json.loads((case/'run-driver.json').read_text())
    if any(d[k]!=c['requests'] for k in ('accepted','returned')) or d['completed_tasks']!=c['tasks']:
        raise ValueError('Lost/duplicated work')
    if d['useful_bytes']!=c['total_bytes'] or d['useful_flops']!=c['useful_flops']:raise ValueError('Problem changed')
    if d['buffer_high_water_bytes']>settings['buffer_bytes'] or settings['buffer_bytes']>524288:raise ValueError('SRAM contract exceeded')
    if sum(d['tile_cycle_partition'].values())!=d['ticks']*16:raise ValueError('Stalls are not a partition')
    tasks=np.zeros(c['tasks'],dtype=[(x,'i8') for x in ('start','finish','parent','first_return','last_return','phase','previous')])
    frontier=Counter();f=0;kv_finish=0
    with (case/'run-tasks.csv').open() as stream:
        for i,t in enumerate(csv.DictReader(stream)):
            if int(t['id'])!=i or int(t['tile'])!=i%16 or int(t['first'])!=i*(settings['task_bytes']//1024):raise ValueError('Task attribution')
            if int(t['count'])!=settings['task_bytes']//1024:raise ValueError('Input join changed')
            phase=int(i>=c['kv_tasks']);parent=int(t['parent'])
            block=(i-(c['kv_tasks'] if phase else 0))//16
            expected_parent=i-16 if phase and settings['task_bytes']<16384 and block%(16384//settings['task_bytes']) else -1
            if parent!=expected_parent or int(t['phase'])!=phase:raise ValueError('Partial reduction dependency')
            for key in tasks.dtype.names:tasks[i][key]=int(t[key])
            a,b=int(t['start']),int(t['finish'])
            if a<int(t['last_return']) or b<a or (parent>=0 and a<tasks[parent]['finish']):raise ValueError('Consume before data/partial')
            if not phase:kv_finish=max(kv_finish,b)
            f+=int(t['flops']);frontier[t['cause']]+=1
    if i+1!=c['tasks'] or f!=c['useful_flops'] or kv_finish!=d['kv_barrier_tick']:raise ValueError('Task count/barrier/work')
    if np.any(tasks['start'][c['kv_tasks']:]<kv_finish):raise ValueError('Weights computed before input activation')
    # Per-tile execution is serial even when ready-task order differs.
    for i,t in enumerate(tasks):
        prev=t['previous']
        if prev>=0 and (prev%16!=i%16 or t['start']<tasks[prev]['finish']):raise ValueError('Concurrent compute on one tile')
    devices=[DeviceUnderTest(dram) for _ in range(16)];extra=TierLegality(settings['uniform'])
    column=np.full(c['requests'],-1,dtype='i8');counts=Counter();tier_columns=Counter();tier_acts=Counter()
    def read_commands(path):
        with path.open() as stream:
            for row in csv.DictReader(stream):yield row
    streams=[read_commands(case/f'transaction-commands.ch{ch}.csv') for ch in range(16)]
    for command in heapq.merge(*streams,key=lambda x:int(x['clock'])):
        ch=int(command['Channel']);dut=devices[ch];vec=[int(command[k]) for k in dut.level_names]
        clk=int(command['clock']);name=command['command'];local=vec.copy();local[0]=0
        if not dut.probe(name,local,clk).ready:raise ValueError('Base command illegal')
        dut.issue(name,local,clk);extra.issue(name,vec,clk);counts[name]+=1
        if name=='ACT':tier_acts[vec[5]//4096]+=1
        if name in ('RD','RDA'):
            rid=int(command['transaction_id'])
            if not 0<=rid<c['requests'] or column[rid]>=0:raise ValueError('Duplicate/unattributed column')
            expected=request_identity(rid,settings['task_bytes'],settings['mapping'],rows)
            if vec!=expected['vec'] or int(command['source'])!=expected['tile']:raise ValueError('Command address/source differs')
            column[rid]=clk;tier_columns[expected['tier']]+=1
    if np.any(column<0):raise ValueError('Request without physical command')
    actual_min=np.full(c['tasks'],np.iinfo(np.int64).max,dtype='i8');actual_max=np.zeros(c['tasks'],dtype='i8')
    latencies=Counter();tier_requests=Counter();frontier_bytes=0
    with (case/'run-events.csv').open() as stream:
        for rid,e in enumerate(csv.DictReader(stream)):
            if int(e['id'])!=rid:raise ValueError('Duplicate/missing return')
            r=request_identity(rid,settings['task_bytes'],settings['mapping'],rows)
            if any(int(e[key])!=r[key] for key in ('task','tile','phase','address','tier')):raise ValueError('Returned wrong data')
            a,b,u=int(e['accepted']),int(e['delivered']),int(e['consumed']);depart=int(e['depart']);t=r['task']
            if not 0<=a<column[rid]<depart<=b<=tasks[t]['start']<=u or u!=tasks[t]['finish']:raise ValueError('Request not causal')
            actual_min[t]=min(actual_min[t],b);actual_max[t]=max(actual_max[t],b)
            tier_requests[r['tier']]+=1;latencies[r['tier']]+=b-a
    if rid+1!=c['requests'] or not np.array_equal(actual_min,tasks['first_return']) or not np.array_equal(actual_max,tasks['last_return']):
        raise ValueError('Task join not equal to all returned inputs')
    if counts.get('RD',0)+counts.get('RDA',0)!=c['requests']:raise ValueError('Byte conservation')
    # This is a consumer-frontier metric, not a full resource-causal global
    # critical path. Each data-dominated task contributes one last1024B packet.
    frontier_bytes=frontier['critical_input_return']*1024
    result=dict(settings=settings,workload=c,driver=d,validation='PASS: base state/timing, tier deadlines, request ids, task joins, dependencies, compute serialization and SRAM',
        commands=dict(counts),tier_ACT_counts=dict(tier_acts),tier_read_counts=dict(tier_columns),
        mean_delivery_latency_ns_by_tier={k:latencies[k]/tier_requests[k]*.25 for k in tier_requests},
        full_workload_tb_s=c['total_bytes']/(d['ticks']*.25)/1000,
        effective_tflops=c['useful_flops']/(d['ticks']*.25)/1000,
        hb_utilization=c['total_bytes']/(d['ticks']*.25)/1000/32,
        consumer_frontier_bytes=frontier_bytes,task_start_causes=dict(frontier),
        critical_path_scope='Last packet of data-dominated task joins; excludes controller-resource causal chains, so not exact global critical-path data movement',
        timing=tier_timings(settings['uniform']),scope='T0 assumed tier-aware internal model. Known prefetch/partial-sum streaming, not new hardware or physical device calibration')
    (case/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ramulator-root',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--smoke',action='store_true');ap.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES));a=ap.parse_args()
    root=Path(a.ramulator_root).resolve();out=Path(a.output).resolve()
    if out.exists():raise ValueError('Do not overwrite evidence')
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=RAMULATOR_COMMIT:raise ValueError('Wrong upstream pin')
    verified=verify_upstream(root);out.mkdir(parents=True);sys.path[:0]=[str(root/'python'),str(root)]
    (out/'provenance.json').write_text(json.dumps(dict(source_commit=revision(),ramulator_commit=RAMULATOR_COMMIT,
        source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),upstream=verified,
        started=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
    exe=native_build(root,out);results=[];rows=6 if a.smoke else 6144
    for name in a.cases:
        case=out/name;case.mkdir();settings=CASES[name];dram,cfg=config(root,case,settings['uniform'])
        (case/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
        with (case/'execution.log').open('w') as log:
            subprocess.run([str(exe),str(case/'config.json'),str(case/'run'),str(settings['task_bytes']),settings['mapping'],
                str(settings['ordered']),str(settings['buffer_bytes']),str(rows)],stdout=log,stderr=log,check=True)
        result=validate(case,dram,settings,rows);results.append(dict(name=name,**result))
        print(name,result['full_workload_tb_s'],result['effective_tflops'],flush=True)
    (out/'summary.json').write_text(json.dumps(dict(cases=results,smoke=a.smoke,thermal_feedback='Not enabled: first discriminate execution loss at T0'),indent=2)+'\n')

if __name__=='__main__':main()
