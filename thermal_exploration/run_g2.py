from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime,timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import scipy

from .multiphase import g2_fabrics,optimize_cycle
from .periodic import PeriodicAudit
from .run import revision
from .thermal import THERMAL_MODES, THERMAL_NAMES, response
from .gate import classify


def summarize(rows,g2):
    table={(r["scenario"],r["case"],r["thermal_regime"],r["placement"],r["fabric"],r["thermal_mode"]):r for r in rows}
    summaries=[];periodic_bounds=[]
    cases=sorted({(r["scenario"],r["case"]) for r in rows})
    for scenario,case in cases:
        for regime,placement,candidate in itertools.product(["phase_steady","cycle_average"],
                ["independent_oracle","shared","migration"],
                ["neighbor_ideal","global_ideal","neighbor_paid","mesh_paid"]):
            def get(a,m,p=placement,reg=regime):return table[scenario,case,reg,p,a,m]
            baseline="local_matched" if candidate.endswith("paid") else "local"
            net={m:get("local",m)["cycle_time_s"]/get(candidate,m)["cycle_time_s"] for m in THERMAL_MODES}
            matched={m:get(baseline,m)["cycle_time_s"]/get(candidate,m)["cycle_time_s"] for m in THERMAL_MODES}
            complete=all((scenario,case,regime,p,a,m) in table for p in ("independent_oracle","shared","migration")
                         for a in ("local",baseline,candidate) for m in THERMAL_MODES)
            gate=classify(placement=placement,paid=candidate.endswith("paid"),controls_complete=complete,
                          net_t0=net[0],net_t1_layer=net[3],net_t2=net[2],matched_t2=matched[2],
                          speedup_gate=g2["gate"]["net_speedup"],
                          interaction_gate=g2["gate"]["minimum_spatial_interaction_ratio"])
            summaries.append({"scenario":scenario,"case":case,"thermal_regime":regime,"placement":placement,
                              "candidate":candidate,"matched_baseline":baseline,
                              **{f"net_speedup_t{m}":net[m] for m in range(3)},
                              **{f"matched_speedup_t{m}":matched[m] for m in range(3)},
                              "net_speedup_t1_layer":net[3],"matched_speedup_t1_layer":matched[3],
                              "spatial_interaction_ratio":net[2]/net[3],
                              "scalar_to_layer_interaction_ratio":net[3]/net[1],
                              "legacy_t2_over_scalar_t1_ratio":net[2]/net[1],
                              "local_layout_time_penalty_vs_independent_oracle":get("local",2)["cycle_time_s"]/get("local",2,"independent_oracle")["cycle_time_s"]-1,
                              "candidate_layout_time_penalty_vs_independent_oracle":get(candidate,2)["cycle_time_s"]/get(candidate,2,"independent_oracle")["cycle_time_s"]-1,
                              "lp_gate_pass":gate["architecture_gate_pass"],**gate})
        for placement,candidate in itertools.product(["shared","migration"],["neighbor_ideal","global_ideal","neighbor_paid","mesh_paid"]):
            baseline="local_matched" if candidate.endswith("paid") else "local"
            def best(a):
                opts=[table[scenario,case,r,placement,a,2] for r in ("phase_steady","cycle_average")]
                return min(opts,key=lambda r:r["paced_cycle_time_s"])
            original=best("local");matched=best(baseline)
            candidate_lower=table[scenario,case,"cycle_average",placement,candidate,2]["cycle_time_s"]
            upper=original["paced_cycle_time_s"]/candidate_lower
            periodic_bounds.append({"scenario":scenario,"case":case,"placement":placement,"candidate":candidate,
                                    "candidate_necessary_average_cycle_time_lower_bound_s":candidate_lower,
                                    "local_admissible_cycle_time_upper_bound_s":original["paced_cycle_time_s"],
                                    "local_admissible_schedule_from_regime":original["thermal_regime"],
                                    "matched_admissible_cycle_time_upper_bound_s":matched["paced_cycle_time_s"],
                                    "net_periodic_speedup_upper_bound":upper,
                                    "matched_periodic_speedup_upper_bound":matched["paced_cycle_time_s"]/candidate_lower,
                                    "cannot_reach_5_percent_in_this_model":bool(upper<g2["gate"]["net_speedup"]),
                                    "scope":"linear RC + fluid execution + constant phase-power realizability; not a calibrated hardware bound"})
    return summaries,periodic_bounds


def plots(summaries,bounds,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    works=[w for w in ["prefill32_decode1","prefill32_decode32","prefill32_decode128"]
           if any(s["case"]==w for s in summaries)]
    ticks=[w.split("decode")[-1]+" decode(s)" for w in works]
    candidates=["neighbor_ideal","global_ideal","neighbor_paid","mesh_paid"]
    fig,axs=plt.subplots(1,2,figsize=(11,4),sharey=True)
    for ax,scenario in zip(axs,["uniform","gradient"]):
        for c in candidates:
            points=[next(b for b in bounds if b["scenario"]==scenario and b["case"]==w and b["candidate"]==c and b["placement"]=="shared") for w in works]
            ax.plot(range(len(works)),[b["net_periodic_speedup_upper_bound"] for b in points],"o-",label=c)
        ax.axhline(1,color="gray",lw=1);ax.axhline(1.05,color="black",ls="--",label="5% gate")
        ax.set_xticks(range(len(works)),ticks)
        ax.set_title(scenario+" cooling / shared layout");ax.grid(alpha=.2)
    axs[0].set_ylabel("Upper bound on periodic net speedup vs Local")
    axs[1].legend(fontsize=8);fig.suptitle("G2 / uncalibrated RC and fluid scheduling model")
    fig.tight_layout();fig.savefig(out/"shared_gate.png",dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4),sharey=True)
    for ax,regime in zip(axs,["phase_steady","cycle_average"]):
        for placement in ["shared","migration"]:
            vals=[next(s["local_layout_time_penalty_vs_independent_oracle"] for s in summaries
                       if s["scenario"]=="gradient" and s["case"]==w and s["placement"]==placement
                       and s["thermal_regime"]==regime and s["candidate"]=="global_ideal") for w in works]
            ax.plot(range(len(works)),np.asarray(vals)*100,"o-",label=placement)
        ax.set_xticks(range(len(works)),ticks)
        ax.set_title(regime);ax.grid(alpha=.2);ax.legend()
    axs[0].set_ylabel("Local cycle-time penalty vs free-layout oracle (%)")
    fig.suptitle("G2 / gradient cooling / fixed work in every cycle")
    fig.tight_layout();fig.savefig(out/"placement_penalty.png",dpi=180);plt.close(fig)


def reports(summaries,bounds,out):
    lines=["# G2: Multi-Phase Shared-Placement Gate", "",
           "Uncalibrated linear RC, two phases using one resident weight tensor, fixed completed work.",
           "Migration charges both directions of the periodic cycle; startup and cycle-level arbitration remain unmodeled.","",
           "## Periodic gain bounds with shared resident layout", "",
           "Candidate cycle-average LP time is a necessary lower bound. A peak-checked, paced Local schedule gives an admissible upper time bound.",
           "Their ratio upper-bounds potential net gain within the fluid/constant-phase-power RC model. It is not a measured speedup.","",
           "| Cooling | Work mix | Layout | Candidate | Net periodic gain upper bound | Cannot reach 5% |",
           "|---|---|---|---|---:|---|"]
    for b in bounds:
        lines.append(f'| {b["scenario"]} | {b["case"]} | {b["placement"]} | {b["candidate"]} | {b["net_periodic_speedup_upper_bound"]:.6f} | {b["cannot_reach_5_percent_in_this_model"]} |')
    lines += ["", "## All LP interactions", "",
              "T1_scalar is a legacy control. Spatial interaction uses T2/T1_layer; ideal connections and independent layouts cannot pass.",
              "| Cooling | Work mix | Thermal regime | Layout | Candidate | T0 net | T1 scalar | T1 layer | T2 net | T2/T1 layer | Class |",
              "|---|---|---|---|---|---:|---:|---:|---:|---:|---|"]
    for s in summaries:
        lines.append(f'| {s["scenario"]} | {s["case"]} | {s["thermal_regime"]} | {s["placement"]} | {s["candidate"]} | '
                     f'{s["net_speedup_t0"]:.6f} | {s["net_speedup_t1"]:.6f} | {s["net_speedup_t1_layer"]:.6f} | {s["net_speedup_t2"]:.6f} | '
                     f'{s["spatial_interaction_ratio"]:.6f} | {s["screening_class"]} |')
    (out/"report.md").write_text("\n".join(lines)+"\n")


def main():
    p=argparse.ArgumentParser();p.add_argument("--config",default="configs/g2.json")
    p.add_argument("--output",required=True);p.add_argument("--thermal-backend",choices=["scipy","hits"],default="scipy")
    p.add_argument("--case",help="Optional single-case verification, leaving cooling/fabric/layout/thermal comparisons complete")
    args=p.parse_args();out=Path(args.output)
    if out.exists():raise SystemExit("Choose a new output directory to preserve evidence")
    out.mkdir(parents=True);started=time.time()
    g2=json.loads(Path(args.config).read_text());base=json.loads(Path(g2["base_config"]).read_text())
    cases=[c for c in g2["phase_cases"] if not args.case or c["name"]==args.case]
    if not cases:raise SystemExit("Unknown phase case")
    rows=[];thermal_records=[];periodic_records=[]
    for cooling in g2["cooling_cases"]:
        cfg=copy.deepcopy(base);cfg["thermal"]["cooling_gradient"]=cooling["gradient"]
        h,gh,tr=response(cfg["grid"],cfg["thermal"],args.thermal_backend)
        tr["scenario"]=cooling["name"];thermal_records.append(tr)
        audit=PeriodicAudit(cfg,g2["transient"]);periodic_records.append(dict(audit.record,scenario=cooling["name"]))
        n=cfg["grid"]**2
        for case,regime,placement,fabric,mode in itertools.product(cases,["phase_steady","cycle_average"],
                 ["independent_oracle","shared","migration"],g2_fabrics(cfg["hardware"]),THERMAL_MODES):
            r=optimize_cycle(cfg,g2,h,gh,case["repetitions"],fabric,mode,placement,regime)
            r.update(scenario=cooling["name"],case=case["name"])
            if mode==2:
                p0=np.r_[np.full(n,cfg["hardware"]["logic_static_w"]+fabric.static_w),np.full(n,cfg["hardware"]["dram_static_w"])]
                pacing=audit.pace(r["segments"],p0)
                r["periodic_audit"]=pacing;r["pacing_factor"]=pacing["factor"]
                r["paced_cycle_time_s"]=r["cycle_time_s"]*pacing["factor"]
            rows.append(r)
            if mode==2 and fabric.name=="local_matched":
                print(f'Completed {cooling["name"]}/{case["name"]}/{regime}/{placement}: {len(rows)} design points',flush=True)
    summary,bounds=summarize(rows,g2)
    for name,data in [("results.json",rows),("summary.json",summary),("periodic_bounds.json",bounds),
                      ("thermal_validation.json",thermal_records),("periodic_validation.json",periodic_records),
                      ("g2_config.json",g2),("base_config.json",base)]:
        (out/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
    scalars=[k for k,v in rows[0].items() if not isinstance(v,(dict,list))]
    scalars += ["pacing_factor","paced_cycle_time_s"]
    with (out/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=scalars,extrasaction="ignore",lineterminator="\n");w.writeheader();w.writerows(rows)
    with (out/"periodic_bounds.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(bounds[0]),lineterminator="\n");w.writeheader();w.writerows(bounds)
    source_commit=revision();dirty=subprocess.check_output(["git","status","--porcelain"],text=True).strip()
    provenance={"schema_version":2,"thermal_controls":THERMAL_NAMES,"source_commit":source_commit,"source_dirty":bool(dirty),"python":sys.version,"platform":platform.platform(),
                "numpy":np.__version__,"scipy":scipy.__version__,"thermal_backend":args.thermal_backend,
                "config_sha256":hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
                "base_config_sha256":hashlib.sha256(Path(g2["base_config"]).read_bytes()).hexdigest(),
                "invocation":["python","-m","thermal_exploration.run_g2"]+sys.argv[1:],
                "started_utc":datetime.fromtimestamp(started,timezone.utc).isoformat(),
                "elapsed_s":time.time()-started,"design_points":len(rows),"lp_solves":sum(r["lp_solves"] for r in rows),
                "fixed_phase_work":True,"scope":"uncalibrated chip-scale fixed-work shared-resident-layout gate"}
    if args.thermal_backend=="hits":
        import hits
        provenance["hits_commit"]=revision(Path(hits.__file__).resolve().parent.parent)
    (out/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    reports(summary,bounds,out);plots(summary,bounds,out)
    print(json.dumps({"status":"PASS","design_points":len(rows),"lp_solves":provenance["lp_solves"],"elapsed_s":time.time()-started}))


if __name__=="__main__":main()
