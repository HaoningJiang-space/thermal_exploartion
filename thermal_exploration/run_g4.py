"""Minimal command validation, isolated from uncalibrated Stratum prediction."""
import argparse
from collections import Counter,defaultdict
import csv
from datetime import datetime,timezone
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

from .run import revision
from .trace_generator import (gemv,row_conflict,streaming,validate_trace,
                             verify_gemv_consumption,write_trace)

RAMULATOR_COMMIT="c6c7a5de0cef35935d6fad7369e6271406798865"


def generated_cpp_tokens(source):
    """Ignore only comments, whitespace and include ordering in codegen output."""
    includes=sorted(re.findall(r'^#include\s+([^\n]+)',source,re.M))
    source=re.sub(r'^#include[^\n]*','',source,flags=re.M)
    pattern=r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|::|->|==|!=|<=|>=|&&|\|\||[^\s]'
    tokens=[t for t in re.findall(pattern,source) if not t.startswith(('//','/*'))]
    return includes,tokens


def verify_upstream(root):
    changed=subprocess.check_output(["git","-C",str(root),"diff","HEAD","--name-only"],text=True).splitlines()
    accepted=[]
    for name in changed:
        if not name.startswith("src/ramulator/dram/impl/") or not name.endswith(".cpp"):
            raise ValueError("Unexpected upstream source change")
        original=subprocess.check_output(["git","-C",str(root),"show","HEAD:"+name],text=True)
        generated=(root/name).read_text()
        if "AUTO-GENERATED" not in original[:500] or generated_cpp_tokens(original)!=generated_cpp_tokens(generated):
            raise ValueError("Upstream codegen changed executable tokens")
        accepted.append(dict(path=name,head_sha256=hashlib.sha256(original.encode()).hexdigest(),
                             build_sha256=hashlib.sha256(generated.encode()).hexdigest()))
    return dict(codegen_format_changes=accepted,
                policy="Only generated C++ with identical tokens and include set; no timing/organization/command changes")


def read_csv(path):
    with Path(path).open() as f:return list(csv.DictReader(f))


def native_build(root,out):
    source=Path(__file__).resolve().parents[1]/"native/ramulator_trace_driver.cpp"
    exe=out/"trace-driver"
    command=["g++","-std=c++20","-O2","-I"+str(root/"src"),
             "-I"+str(root/"ext/fmt/include"),"-I"+str(root/"ext/yaml-cpp/include"),
             str(source),"-L"+str(root),"-lramulator","-Wl,-rpath,"+str(root),"-o",str(exe)]
    with (out/"build.log").open("w") as log:subprocess.run(command,stdout=log,stderr=log,check=True)
    return exe


def device_and_config(case,refresh=True):
    import ramulator
    dram=ramulator.dram.HBM3(org_preset="HBM3_16Gb_8hi",timing_preset="HBM3_6400Mbps")
    controller=ramulator.controller.HBM34(
        dram=dram,scheduler=ramulator.scheduler.FRFCFSRowHit(),
        refresh_manager=ramulator.refresh_manager.AllBank() if refresh else ramulator.refresh_manager.NoRefresh(),
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
        read_buffer_size=128,write_buffer_size=64,
        controller_plugins=[ramulator.controller_plugin.CmdTraceRecorder(path=str(case/"commands.csv"))])
    memory=ramulator.memory_system.GenericDRAM(clock_ratio=1,
        channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper(),controllers=[controller])
    config={"frontend":{"impl":"TraceConsumer","clock_ratio":1},"memory_system":memory.to_config()}
    config["memory_system"]["controllers"][0]["controller_plugins"].append(
        {"impl":"TransactionTrace","path":str(case/"transaction-commands.csv")})
    return dram,config


def validate_events(req,events,driver,validator=validate_trace):
    counts=validator(req)
    if len(events)!=len(req) or {int(e["id"]) for e in events}!=set(range(len(req))):
        raise ValueError("Lost/duplicate request completion")
    by_id={int(e["id"]):e for e in events}
    for r in req:
        e=by_id[r["id"]]
        for field,key in (("address","address"),("size","size"),("source","source_tile"),("useful_flops","useful_flops")):
            if int(e[field])!=r[key]:raise ValueError("Returned request attribution mismatch")
        a=int(e["accepted"]);c=int(e["completed"]);u=int(e["consumed"])
        if not r["timestamp"]<=a<c<=u:raise ValueError("Noncausal request lifetime")
        if any(int(by_id[d]["consumed"])>a for d in r["dependency"]):raise ValueError("Dependency released too early")
    if not all(driver[k]==counts["request_count"] for k in ("accepted","returned","consumed")):
        raise ValueError("Transaction count not conserved")
    if driver["useful_bytes"]!=counts["read_bytes"] or driver["useful_flops"]!=counts["useful_flops"]:
        raise ValueError("Work/byte count not conserved")
    if sum(driver["frontend_cycle_states"].values())!=driver["ticks"]:
        raise ValueError("Frontend cycle observations not a partition")
    return counts


def command_replay(dram,req,events,commands,ticks,transaction_commands=None):
    # Independent DRAM state instance, same upstream model. This catches illegal
    # issued traces; it is not validation against an independent physical model.
    from tests.device_timings.harness import DeviceUnderTest
    dut=DeviceUnderTest(dram)
    if transaction_commands is not None:
        if len(transaction_commands)!=len(commands):raise ValueError("Transaction and physical command traces differ")
        for a,b in zip(commands,transaction_commands):
            if any(a[k]!=b[k] for k in ("clock","command","source",*dut.level_names)):
                raise ValueError("Transaction tag is attached to the wrong physical command")
            a["transaction_id"]=int(b["transaction_id"])
    by_clk=defaultdict(list)
    for command in commands:by_clk[int(command["clock"])].append(command)
    accepted=defaultdict(list);completed=defaultdict(list);ev={int(e["id"]):e for e in events}
    for e in events:
        accepted[int(e["accepted"])+1].append(int(e["id"]))
        completed[int(e["completed"])].append(int(e["id"]))
    pending=set();issued=set();counts=Counter();observations=Counter()
    open_rows={};open_ticks=0;last_act={};command_matches=[]
    for clk in range(1,ticks+1):
        pending.update(accepted[clk])
        if pending:
            rid=min(pending,key=lambda i:(int(ev[i]["accepted"]),i));vec=req[rid]["addr_vec"]
            if rid in issued:state="column_burst_or_return"
            else:
                p=dut.probe("RD",vec,clk)
                if p.preq=="ACT":state="closed_bank_needs_ACT"
                elif p.preq in ("PREpb","PREab"):state="row_conflict_needs_PRE"
                elif not p.ready:
                    since=clk-last_act.get(tuple(vec[:5]),-10**9)
                    state="ACT_to_RD_timing" if since<dut.timings["nRCDRD"] else "column_or_other_timing"
                else:state="ready_waiting_controller"
        else:state="no_outstanding_read"
        observations[state]+=1
        for command in by_clk[clk]:
            name=command["command"];vec=[int(command[k]) for k in dut.level_names]
            if not dut.probe(name,vec,clk).ready:raise ValueError("Illegal command in independent state replay")
            dut.issue(name,vec,clk);counts[name]+=1;bank=tuple(vec[:5])
            if name=="ACT":open_rows[bank]=vec[5];last_act[bank]=clk
            elif name=="PREpb":open_rows.pop(bank,None)
            elif name=="PREab":
                for key in list(open_rows):
                    if key[:2]==bank[:2]:open_rows.pop(key)
            if name in ("RD","RDA"):
                if "transaction_id" in command:
                    rid=command["transaction_id"]
                    if rid not in pending or rid in issued or req[rid]["addr_vec"]!=vec or req[rid]["source_tile"]!=int(command["source"]):
                        raise ValueError("Column transaction id is not a pending matching request")
                else:
                    # Compatibility for already archived unique-address traces.
                    matches=[i for i in pending if i not in issued and req[i]["addr_vec"]==vec]
                    if len(matches)!=1:raise ValueError("An ambiguous legacy trace needs end-to-end transaction ids")
                    rid=matches[0]
                issued.add(rid);command_matches.append(dict(id=rid,column_clock=clk))
        open_ticks+=len(open_rows)
        pending.difference_update(completed[clk])
    if len(issued)!=len(req) or pending or sum(observations.values())!=ticks:
        raise ValueError("Command/request replay not closed")
    return dict(status="PASS",issued_commands=sum(counts.values()),commands=dict(counts),
                oldest_pending_read_observations=dict(observations),column_request_matches=command_matches,
                bank_open_row_ticks=open_ticks,total_bank_ticks=ticks*64,
                bank_busy_idle_cycles=None,
                bank_metric_scope="open-row occupancy is measured; open is not synonymous with busy",
                raw_timing_ticks=dut.timings,tick_multiplier=dut.tick_multiplier,
                time_unit_ns=dut.time_unit_ns,
                scope="independent state replay of the same Ramulator device; observations are not additive causal performance losses")


def run_case(exe,out,name,req,queue=64,consumer_rate=32,refresh=True):
    import yaml
    case=out/name;case.mkdir();write_trace(req,case)
    dram,config=device_and_config(case,refresh)
    (case/"config.json").write_text(json.dumps(config,indent=2)+"\n")
    with (case/"execution.log").open("w") as log:
        subprocess.run([str(exe),str(case/"config.json"),str(case/"requests.tsv"),str(case/"run"),str(queue),str(consumer_rate)],
                       stdout=log,stderr=log,check=True)
    events=read_csv(case/"run-events.csv");driver=json.loads((case/"run-driver.json").read_text())
    counts=validate_events(req,events,driver)
    replay=command_replay(dram,req,events,read_csv(case/"commands.csv.ch0"),driver["ticks"],read_csv(case/"transaction-commands.csv"))
    # Nominal half-CK is 0.3125 ns. Upstream stores 312 ps for statistics;
    # command tick counts are unchanged. Keep both conventions explicit.
    tick_ns=replay["time_unit_ns"];time_ns=driver["ticks"]*tick_ns
    stats=yaml.safe_load((case/"run-stats.yaml").read_text())
    result=dict(name=name,profile="isolated_upstream_HBM3_16Gb_8hi_6400Mbps",thermal_condition="T0",
        controls=dict(outstanding_limit=queue,consumer_flops_per_tile_per_tick=consumer_rate,
                      refresh_enabled=refresh,
                      tiles=16,status="Assumed integration controls; not a calibrated NPU"),
        work=counts,driver=driver,command_validation=replay,controller_statistics=stats,
        elapsed_ns=time_ns,useful_bandwidth_gb_s=counts["read_bytes"]/time_ns,
        nominal_tick_ns=tick_ns,native_stats_tick_ns=replay["raw_timing_ticks"]["tCK_ps"]/1000,
        useful_gflops=counts["useful_flops"]/time_ns,
        external_DQ_peak_gb_s=51.2,external_DQ_utilization=counts["read_bytes"]/time_ns/51.2,
        HB_utilization=None,HB_utilization_status="Not applicable to this conventional HBM3 integration",
        column_data_bus_occupancy=(replay["commands"].get("RD",0)*replay["raw_timing_ticks"]["nBL"]/(2*driver["ticks"])),
        average_outstanding=driver["outstanding_sum"]/driver["ticks"],
        assumed_consumer_utilization=driver["consumer_active_tile_ticks"]/(16*driver["ticks"]),
        bytes_per_useful_flop=None if not counts["useful_flops"] else counts["read_bytes"]/counts["useful_flops"],
        power_w=None,temperatures_c=None,
        Stratum_T0_T1_layer_T2_status="NOT_READY: G3 power/command domains/HB/cooling unresolved; G5 deferred")
    if result["column_data_bus_occupancy"]>1 or result["external_DQ_utilization"]>1.01:
        raise ValueError("Bandwidth exceeded the matching data-bus bound")
    if req[-1]["kind"]=="weight":result["functional_gemv"]=verify_gemv_consumption(req,events)
    (case/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def plot(results,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,2,figsize=(12,4.6))
    labels=[r["name"].replace("_","\n") for r in results]
    ax[0].bar(range(len(results)),[r["useful_bandwidth_gb_s"] for r in results])
    ax[0].axhline(51.2,color="grey",ls="--",label="One-channel external DQ peak")
    ax[0].set(xticks=range(len(results)),xticklabels=labels,ylabel="Useful bandwidth (GB/s)")
    ax[0].legend(fontsize=8);ax[0].grid(axis="y",alpha=.2)
    states=sorted(set().union(*(r["command_validation"]["oldest_pending_read_observations"] for r in results)))
    bottom=[0.]*len(results)
    for state in states:
        values=[100*r["command_validation"]["oldest_pending_read_observations"].get(state,0)/r["driver"]["ticks"] for r in results]
        ax[1].bar(range(len(results)),values,bottom=bottom,label=state.replace("_"," "))
        bottom=[a+b for a,b in zip(bottom,values)]
    ax[1].set(xticks=range(len(results)),xticklabels=labels,ylabel="Oldest-read cycle observations (%)",ylim=(0,100))
    ax[1].legend(loc="upper left",bbox_to_anchor=(1.02,1),fontsize=8)
    fig.suptitle("Standard HBM3 integration only — cycle observations are not causal loss percentages")
    fig.tight_layout();fig.savefig(out/"bottleneck_observations.png",dpi=170,bbox_inches="tight");plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--ramulator-root",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args();root=Path(args.ramulator_root).resolve();out=Path(args.output).resolve()
    upstream=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if upstream!=RAMULATOR_COMMIT:raise SystemExit("Use the frozen Ramulator commit")
    upstream_build=verify_upstream(root)
    if out.exists():raise SystemExit("Choose a new directory; preserve failed runs")
    out.mkdir(parents=True);sys.path[:0]=[str(root/"python"),str(root)]
    exe=native_build(root,out)
    results=[run_case(exe,out,"streaming",streaming()),
             run_case(exe,out,"row_conflict",row_conflict()),
             run_case(exe,out,"gemv",gemv()),
             run_case(exe,out,"streaming_queue1",streaming(),queue=1),
             run_case(exe,out,"gemv_slow_consumer",gemv(),consumer_rate=.25)]
    by_name={r["name"]:r for r in results}
    negative=dict(queue_reduction_lowers_streaming_bandwidth=by_name["streaming_queue1"]["useful_bandwidth_gb_s"]<by_name["streaming"]["useful_bandwidth_gb_s"],
                  slow_consumer_lowers_GEMV_completion_rate=by_name["gemv_slow_consumer"]["useful_gflops"]<by_name["gemv"]["useful_gflops"])
    if not all(negative.values()):raise RuntimeError("A bottleneck-active negative control failed")
    report=dict(integration_gate="PASS",Stratum_calibration_gate="NO_GO",new_architecture_gate="NO_GO",
                negative_controls=negative,results=results,
                reason="HBM3 commands/consumer interface verified; Stratum command domains, component power, HB and cooling still unknown; no HB bottleneck claim")
    (out/"summary.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    (out/"provenance.json").write_text(json.dumps(dict(source_commit=revision(),
        source_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True).strip()),
        ramulator_commit=upstream,upstream_build_verification=upstream_build,python=sys.version,started_utc=datetime.now(timezone.utc).isoformat(),
        native_adapter_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/"native/ramulator_trace_driver.cpp").read_bytes()).hexdigest(),
        invocation="python -m thermal_exploration.run_g4 --ramulator-root <pinned-upstream> --output <new-dir>"),indent=2)+"\n")
    plot(results,out)
    print(json.dumps(dict(integration_gate="PASS",Stratum_calibration_gate="NO_GO",negative_controls=negative,
                          bandwidth_gb_s={r["name"]:r["useful_bandwidth_gb_s"] for r in results})))


if __name__=="__main__":main()
