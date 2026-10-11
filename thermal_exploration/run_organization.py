"""Mode B: command-grounded service rates plus fair steady thermal exploration."""
import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from . import hb_trace
from .organization import bounds,load_exploration,organization_cost,scenarios,solve,thermal_config,values
from .run import revision
from .run_g4 import RAMULATOR_COMMIT,native_build,read_csv,run_case,validate_events,verify_upstream
from .thermal import response
from .trace_generator import request,streaming,write_trace


def check_commands(dram,req,events,commands,logic_ticks_per_dram_tick=1,device_channels=16):
    from tests.device_timings.harness import DeviceUnderTest
    devices=[DeviceUnderTest(dram) for _ in range(device_channels)]
    issued=set();counts=Counter();ev={int(e["id"]):e for e in events}
    for c in commands:
        channel=int(c["Channel"]);dut=devices[channel];vec=[int(c[k]) for k in dut.level_names];vec[0]=0
        clock=int(c["clock"]);name=c["command"]
        if not dut.probe(name,vec,clock).ready:raise ValueError("Illegal assumed-device command")
        dut.issue(name,vec,clock);counts[name]+=1
        if name in ("RD","RDA"):
            rid=int(c["transaction_id"])
            if rid in issued or not 0<=rid<len(req):raise ValueError("Duplicate/invalid physical transaction")
            original=[int(c[k]) for k in dut.level_names]
            if req[rid]["addr_vec"]!=original or req[rid]["source_tile"]!=int(c["source"]):raise ValueError("Transaction tag/placement mismatch")
            if int(ev[rid]["accepted"])//logic_ticks_per_dram_tick>=clock or int(ev[rid]["completed"])//logic_ticks_per_dram_tick<=clock:raise ValueError("Noncausal command attribution")
            issued.add(rid)
    if issued!=set(range(len(req))):raise ValueError("Read requests not all attributed to physical commands")
    return dict(status="PASS",counts=dict(counts),commands=sum(counts.values()),logical_reads=len(issued),
                read_merging="Pinned controller does not merge reads; two identical-address reads issue separately",
                evidence_level="L1 software execution; assumed device parameters are not measured")


def command_case(exe,root,out,name,paths,hb,kind="streaming",refresh=True,ideal=False,long=False):
    case=out/name;case.mkdir()
    req=hb_trace.streaming_trace(paths,1048576 if long else 32768) if kind=="streaming" else hb_trace.gemv_trace(paths)
    validator=lambda r:hb_trace.validate(r,paths)
    write_trace(req,case,validator)
    dram,config=hb_trace.ramulator_config(root,case,paths,refresh,ideal)
    (case/"config.json").write_text(json.dumps(config,indent=2)+"\n")
    # 8 TFLOP/s/tile =2000 FLOP per 0.25ns tick; 512 inflight/tile,
    # 512KiB payload buffer/tile fits the same 2.25MiB private SRAM budget.
    with (case/"execution.log").open("w") as log:
        subprocess.run([str(exe),str(case/"config.json"),str(case/"requests.tsv"),str(case/"run"),"8192","2000",str(hb/16*1000*.25),"0","2"],stdout=log,stderr=log,check=True)
    driver=json.loads((case/"run-driver.json").read_text());events=read_csv(case/"run-events.csv")
    work=validate_events(req,events,driver,validator)
    commands=[]
    for ch in range(16):commands.extend(read_csv(case/f"transaction-commands.ch{ch}.csv"))
    commands.sort(key=lambda c:int(c["clock"]))
    validation=check_commands(dram,req,events,commands,2)
    # Freeze the steady window rule before looking at rates: discard first and
    # last4096 completed transactions; report full execution separately.
    ordered=sorted(int(e["completed"]) for e in events)
    start,end=ordered[4096],ordered[-4096]
    if long:
        period=15600  # 3900ns refresh interval /0.25ns per tick
        start=period*2;end=(driver["ticks"]//period-1)*period
        if end-start<period*5:raise ValueError("Steady interval must contain at least five refresh periods")
    count=sum(start<=int(e["completed"])<end for e in events)
    steady=Counter(c["command"] for c in commands if start<=2*int(c["clock"])<end)
    bytes_=count*hb_trace.TX;rate=bytes_/((end-start)*.25)/1000
    full_rate=work["read_bytes"]/(driver["ticks"]*.25)/1000
    if rate>hb*1.001:raise ValueError("Simulated delivery exceeds fixed HB budget")
    # A steady full-row combined ACT/PRE coefficient. Actual ACTs include row
    # reopenings caused by refresh. No coefficient is fitted to measured power.
    result=dict(name=name,paths=paths,hb_tb_s=hb,refresh_enabled=refresh,ideal_row_retention=ideal,
        trace_kind=kind,work=work,ticks=driver["ticks"],full_execution_tb_s=full_rate,
        long_multi_refresh_trace=long,
        steady_window=dict(start_tick=start,end_tick=end,requests=count,bytes=bytes_,duration_ns=(end-start)*.25,
                           useful_tb_s=rate,commands=dict(steady),ACT_per_useful_byte=steady["ACT"]/bytes_),
        warmup_ticks=start,drain_ticks=driver["ticks"]-end,command_validation=validation,
        scope="Simulated assumed internal port model; not standard HBM3 or Stratum calibration")
    if kind=="gemv" and (work["useful_flops"]!=2*4096**2 or work["read_bytes"]!=2*4096**2+8192):
        raise ValueError("4096-square GEMV workload incomplete")
    (case/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument("--ramulator-root",required=True);p.add_argument("--output",required=True)
    p.add_argument("--thermal-backend",choices=["scipy","hits"],default="scipy");args=p.parse_args()
    root=Path(args.ramulator_root).resolve();out=Path(args.output).resolve()
    if subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()!=RAMULATOR_COMMIT:
        raise SystemExit("Wrong upstream snapshot")
    upstream=verify_upstream(root)
    if out.exists():raise SystemExit("Choose a new directory")
    out.mkdir(parents=True);sys.path[:0]=[str(root/"python"),str(root)]
    (out/"provenance.json").write_text(json.dumps(dict(source_commit=revision(),
        source_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True).strip()),
        ramulator_commit=RAMULATOR_COMMIT,upstream_build_verification=upstream,python=sys.version,
        started_utc=datetime.now(timezone.utc).isoformat(),thermal_backend=args.thermal_backend),indent=2)+"\n")
    profile=load_exploration();(out/"profile.json").write_text(json.dumps(profile,indent=2)+"\n")
    exe=native_build(root,out)
    # Fix applicability before any organization comparisons; no address-based
    # inference is allowed for the two simultaneous identical-address reads.
    repeated=[request(0,0,0),request(1,0,1)]
    repeat=run_case(exe,out,"repeated_address",repeated,refresh=False)
    if repeat["command_validation"]["commands"]["RD"]!=2:raise ValueError("Unexpected read merge policy")
    # Controlled concurrency check: identical data and no refresh on either side.
    q64=run_case(exe,out,"queue64_no_refresh",streaming(),refresh=False)
    q1=run_case(exe,out,"queue1_no_refresh",streaming(),queue=1,refresh=False)
    if q1["command_validation"]["commands"].get("REFab",0) or q64["command_validation"]["commands"].get("REFab",0):
        raise ValueError("Refresh enabled in supposedly controlled pair")
    if q1["useful_bandwidth_gb_s"]>=q64["useful_bandwidth_gb_s"]:raise ValueError("Queue control did not constrain service")
    print("Applicability controls PASS",flush=True)
    cases=[]
    for hb in (32,16,8):
        for paths in ((1,2,4,8) if hb==32 else (1,2,4)):
            cases.append(command_case(exe,root,out,f"stream_p{paths}_HB{hb}",paths,hb,long=hb==32))
            print(cases[-1]["name"],cases[-1]["steady_window"]["useful_tb_s"],flush=True)
    for paths in (1,2,4,8):
        cases.append(command_case(exe,root,out,f"gemv_p{paths}_HB32",paths,32,"gemv"))
        print(cases[-1]["name"],cases[-1]["steady_window"]["useful_tb_s"],flush=True)
    # One physical relaxation: shorten row-retention constraint; preserve all
    # other timing/refresh/HB limitations and modeled activity energy.
    cases.append(command_case(exe,root,out,"ideal_row_retention_p2_HB32",2,32,ideal=True,long=True))
    lookup={(c["hb_tb_s"],c["paths"]):c for c in cases if c["trace_kind"]=="streaming" and not c["ideal_row_retention"]}
    rows=[];thermal_records=[];rejected=[]
    for name,scenario in scenarios(profile):
        h,gh,record=response(4,thermal_config(scenario),args.thermal_backend);thermal_records.append(dict(scenario=name,**record))
        for allocation in ("shared_area","fixed_compute"):
            for paths in (1,2,4,8):
                cost=organization_cost(scenario,paths,allocation)
                if not cost["area_feasible"]:
                    rejected.append(dict(scenario=name,paths=paths,reason="fixed area budget exceeded",**cost));continue
                observed=lookup[(32,paths)]["steady_window"]
                service=observed.copy();service["useful_tb_s"]=min(observed["useful_tb_s"],values(scenario)["hb_chip_tb_s"])
                for workload in ((0,1,2) if allocation=="shared_area" else (0,1)):
                    for mode in (0,3,2):
                        r=solve(scenario,paths,service["useful_tb_s"],h,gh,workload,mode,service["ACT_per_useful_byte"],allocation)
                        r.update(scenario=name,paths=paths,allocation=allocation,service_tb_s=service["useful_tb_s"],
                                 service_evidence="multi-refresh internal rate plus explicit buffered HB min bound",necessary_bounds=bounds(scenario,paths))
                        rows.append(r)
        print("Thermal/area analysis",name,flush=True)
    ideal=next(c for c in cases if c["ideal_row_retention"])["steady_window"]
    h,gh,_=response(4,thermal_config(profile),args.thermal_backend)
    oracle=[]
    for allocation in ("shared_area","fixed_compute"):
        for workload in ((0,1,2) if allocation=="shared_area" else (0,1)):
            for mode in (0,3,2):
                r=solve(profile,2,ideal["useful_tb_s"],h,gh,workload,mode,ideal["ACT_per_useful_byte"],allocation)
                r.update(scenario="default",paths=2,allocation=allocation,ideal_only=True,
                         scope="Same cost/energy assumptions; row retention alone relaxed")
                oracle.append(r)
    summary=dict(mode="Architecture Exploration",reference_reproduction_status="NOT_READY",command_cases=cases,
        applicability=dict(repeated_address="PASS; end-to-end ids",no_refresh_queue_control="PASS"),
        results=rows,rejected_organizations=rejected,ideal_row_retention=oracle,thermal_solver_records=thermal_records,
        experiment_scope="Finite, prespecified organizations and sensitivity controls; steady LP relaxations, not measured or RTL performance")
    (out/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(command_cases=len(cases),LP_results=len(rows),ideal_results=len(oracle),area_rejects=len(rejected))))


if __name__=="__main__":main()
