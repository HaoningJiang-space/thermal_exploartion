"""Publish finite G3/G4 evidence, preserving all controls and removing run paths."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from thermal_exploration.run_g4 import validate_events


def clean(text):
    return re.sub(r'/[^\s"<>]*thermal-exploration-runs', '<run-root>',text)


def table_csv(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    args=p.parse_args();src=Path(args.input);out=Path(args.output)
    if out.exists():raise SystemExit("Preserve previous archives")
    out.mkdir(parents=True);g3=next(src.glob("g3-reference-*"));g4=next(src.glob("g4-command-*/summary.json")).parent
    for f in g3.iterdir():
        data=f.read_bytes() if f.suffix==".png" else clean(f.read_text()).encode()
        (out/("g3-"+f.name)).write_bytes(data)
    summary=json.loads((g4/"summary.json").read_text());metrics=[];state_rows=[];totals=Counter()
    for r in summary["results"]:
        case=g4/r["name"];req=json.loads((case/"requests.json").read_text())
        with (case/"run-events.csv").open() as f:events=list(csv.DictReader(f))
        validate_events(req,events,r["driver"])
        ctrl=r["controller_statistics"]["memory_system"]["controller"]
        n=r["work"]["request_count"]
        if ctrl["num_read_reqs_served"]!=n or sum(ctrl[k] for k in ("read_row_hits","read_row_misses","read_row_conflicts"))!=n:
            raise ValueError("Controller/request accounting did not close")
        for suffix in ("hits","misses","conflicts"):
            if sum(ctrl[f"read_row_{suffix}_core_{i}"] for i in range(16))!=ctrl[f"read_row_{suffix}"]:
                raise ValueError("Source tile accounting did not close")
        cmd=r["command_validation"]["commands"];totals.update(cmd)
        metrics.append(dict(trace=r["name"],requests=n,read_bytes=r["work"]["read_bytes"],flops=r["work"]["useful_flops"],
            ticks=r["driver"]["ticks"],elapsed_ns=r["elapsed_ns"],useful_gb_s=r["useful_bandwidth_gb_s"],
            external_DQ_utilization=r["external_DQ_utilization"],ACT=cmd.get("ACT",0),PREpb=cmd.get("PREpb",0),PREab=cmd.get("PREab",0),
            RD=cmd.get("RD",0),WR=cmd.get("WR",0),REFab=cmd.get("REFab",0),row_hits=ctrl["read_row_hits"],
            row_misses=ctrl["read_row_misses"],row_conflicts=ctrl["read_row_conflicts"],
            read_queue_avg=ctrl["read_queue_len_avg"],avg_read_latency_ticks=ctrl["avg_read_latency"],
            outstanding_avg=r["average_outstanding"],column_bus_occupancy=r["column_data_bus_occupancy"],
            assumed_consumer_utilization=r["assumed_consumer_utilization"],
            HB_utilization="UNKNOWN_FOR_STRATUM",Stratum_power_w="NOT_CALIBRATED",Stratum_temperature_c="NOT_CALIBRATED"))
        for k,v in r["command_validation"]["oldest_pending_read_observations"].items():
            state_rows.append(dict(trace=r["name"],observation=k,cycles=v,fraction=v/r["driver"]["ticks"],scope="oldest pending request; not causal loss"))
        # Compact public JSON retains all metrics; raw archive retains every match.
        r["command_validation"].pop("column_request_matches")
    table_csv(out/"g4-metrics.csv",metrics);table_csv(out/"g4-cycle-observations.csv",state_rows)
    (out/"g4-summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    (out/"g4-provenance.json").write_text(clean((g4/"provenance.json").read_text()))
    (out/"bottleneck_observations.png").write_bytes((g4/"bottleneck_observations.png").read_bytes())
    # Two different observations: read readiness and assumed consumer activity.
    fig,axs=plt.subplots(1,2,figsize=(10,4.5));labels=[r["trace"].replace('_','\n') for r in metrics]
    axs[0].bar(range(5),[100*r["assumed_consumer_utilization"] for r in metrics])
    axs[0].set(xticks=range(5),xticklabels=labels,ylabel="Assumed consumer utilization (%)",ylim=(0,105))
    axs[1].bar(range(5),[r["column_bus_occupancy"]*100 for r in metrics])
    axs[1].set(xticks=range(5),xticklabels=labels,ylabel="Modeled column data-bus occupancy (%)",ylim=(0,105))
    for ax in axs:ax.grid(axis="y",alpha=.2)
    fig.suptitle("Integration diagnostics; simultaneous observations do not add as performance losses")
    fig.tight_layout();fig.savefig(out/"consumer_and_column.png",dpi=170);plt.close(fig)
    with tarfile.open(out/"g4-raw-traces.tar.gz","w:gz") as tar:
        for case in sorted(p for p in g4.iterdir() if p.is_dir()):
            for f in sorted(case.iterdir()):
                if not f.is_file():continue
                data=clean(f.read_text()).encode();info=tarfile.TarInfo(case.name+"/"+f.name)
                info.size=len(data);info.mtime=0;tar.addfile(info,io.BytesIO(data))
    official=src/"bootstrap"
    xml=ET.parse(official/"g4-hbm3-official-v2.xml")
    cases=list(xml.iter("testcase"));groups=Counter(c.attrib["classname"] for c in cases)
    failures=sum(len(list(c.iter("failure")))+len(list(c.iter("error"))) for c in cases)
    if len(cases)!=128 or failures:raise ValueError("Official verification record not passing")
    for element in xml.iter():element.attrib.pop("hostname",None)
    xml.write(out/"official-tests.xml",encoding="utf-8",xml_declaration=True)
    (out/"official-tests.log").write_text(clean((official/"g4-hbm3-official-v2.log").read_text()))
    perf=(official/"g4-hbm3-performance.log").read_text()
    deviations=[float(v) for v in re.findall(r'Deviation = ([+-]?\d+\.\d+)%',perf)]
    if len(deviations)!=3 or max(abs(x) for x in deviations)>5:
        raise ValueError("Official matching-profile performance check outside 5%")
    (out/"official-performance.log").write_text(clean(perf))
    verification=dict(official_unique_tests=len(cases),failures=failures,groups=dict(groups),
        official_printed_deviations_percent=dict(unloaded_latency=deviations[0],streaming=deviations[1],mixed=deviations[2]),
        performance_threshold_percent=5,performance_gate_scope="matching upstream standard configuration; printed precision",
        own_cases=len(metrics),own_requests=sum(r["requests"] for r in metrics),own_commands=sum(totals.values()),
        own_command_counts=dict(totals),source_tile_accounting="PASS",work_transaction_accounting="PASS",
        independent_command_replay="PASS; independent state instance of same model, not independent physical validation",
        G3_whole_calibration="NO_GO",G4_HBM3_integration="PASS",G4_Stratum="NOT_READY",G5_G6_G7="DEFERRED")
    (out/"verification.json").write_text(json.dumps(verification,indent=2)+"\n")
    artifacts={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()}
    (out/"artifact-sha256.json").write_text(json.dumps(artifacts,indent=2)+"\n")
    print(json.dumps(verification))


if __name__=="__main__":main()
