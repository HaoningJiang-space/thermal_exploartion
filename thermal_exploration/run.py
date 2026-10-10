from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
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

from .model import best_tiling, fabric_cases
from .thermal import THERMAL_MODES, THERMAL_NAMES, response
from .gate import classify


def revision(cwd=None):
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        return "unknown"


def summarize(rows):
    groups = {}
    for r in rows:
        key = (r["scenario"],r["workload"],r["placement"])
        groups.setdefault(key, {})[(r["fabric"],r["thermal_mode"])] = r
    summaries = []
    for key, table in groups.items():
        for b in ["neighbor_ideal","global_ideal","mesh_paid"]:
            a = "local_matched" if b == "mesh_paid" else "local"
            ratios = {m:table[(b,m)]["tflops"]/table[(a,m)]["tflops"] for m in THERMAL_MODES}
            f_a2 = table[(a,2)]["tflops"]; f_b2 = table[(b,2)]["tflops"]
            # This is an interaction in optimized ratios, not a unique additive attribution.
            gain = ratios[2]/ratios[3]
            no_heat_gain = ratios[0]
            net_ratios = {m:table[(b,m)]["tflops"]/table[("local",m)]["tflops"] for m in THERMAL_MODES}
            placement_controls = {p:groups.get((key[0],key[1],p),{}) for p in ("fixed","free")}
            complete = all(all((f,m) in t for f in (a,b,"local") for m in THERMAL_MODES)
                           for t in placement_controls.values())
            gate = classify(placement=key[2], paid=b.endswith("paid"), controls_complete=complete,
                            net_t0=net_ratios[0], net_t1_layer=net_ratios[3], net_t2=net_ratios[2],
                            matched_t2=ratios[2])
            summaries.append({"scenario":key[0],"workload":key[1],"placement":key[2],
                              "baseline":a,"candidate":b,
                              "speedup_t0":ratios[0],"speedup_t1":ratios[1],"speedup_t2":ratios[2],
                              "speedup_t1_layer":ratios[3],
                              "spatial_interaction_ratio":gain,
                              "scalar_to_layer_interaction_ratio":ratios[3]/ratios[1],
                              "legacy_t2_over_scalar_t1_ratio":ratios[2]/ratios[1],
                              "resource_ownership_loss_fraction_t2":1-f_a2/f_b2,
                              "local_spatial_penalty_fraction":1-f_a2/table[(a,3)]["tflops"],
                              "net_speedup_t0_vs_original_local":net_ratios[0],
                              "net_speedup_t1_vs_original_local":net_ratios[1],
                              "net_speedup_t1_layer_vs_original_local":net_ratios[3],
                              "net_speedup_t2_vs_original_local":net_ratios[2],
                              "fixed_t2_net_speedup":(placement_controls["fixed"][(b,2)]["tflops"]/
                                  placement_controls["fixed"][("local",2)]["tflops"]) if complete else None,
                              "free_t2_net_speedup":(placement_controls["free"][(b,2)]["tflops"]/
                                  placement_controls["free"][("local",2)]["tflops"]) if complete else None,
                              **gate,
                              "no_heat_gain":no_heat_gain})
    return summaries


def plot(rows, summaries, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups = sorted({(r["scenario"],r["workload"],r["placement"]) for r in rows})
    if len(groups) > 12:
        # Sensitivity plots keep all free-placement cases visible without a giant raster.
        works = sorted({s["workload"] for s in summaries})
        labels = sorted({s["scenario"] for s in summaries})
        fig,axs=plt.subplots(1,len(works),figsize=(13,0.35*len(labels)+2),sharey=True,squeeze=False)
        for ax,work in zip(axs[0],works):
            for candidate in ("global_ideal","mesh_paid"):
                table={s["scenario"]:s for s in summaries if s["placement"] == "free"
                       and s["workload"] == work and s["candidate"] == candidate}
                ax.plot([table[label]["net_speedup_t2_vs_original_local"] for label in labels],range(len(labels)),"o-",label=candidate)
            ax.axvline(1,color="gray",lw=1);ax.axvline(1.05,color="gray",ls="--",lw=1)
            ax.set_title(work);ax.set_xlabel("Net T2 speedup vs original Local (free placement)");ax.legend()
            ax.grid(alpha=0.2)
        axs[0,0].set_yticks(range(len(labels)),labels,fontsize=8)
        fig.tight_layout();fig.savefig(out/"sensitivity.png",dpi=160);plt.close(fig)
        return
    fig, axs = plt.subplots(len(groups), 1, figsize=(9,2.5*len(groups)), squeeze=False)
    archs = ["local","neighbor_ideal","global_ideal","local_matched","mesh_paid"]
    for ax,key in zip(axs[:,0],groups):
        table = {(r["fabric"],r["thermal_mode"]):r for r in rows
                 if (r["scenario"],r["workload"],r["placement"]) == key}
        x = np.arange(4)
        for idx,a in enumerate(archs):
            ax.bar(x+(idx-2)*0.15,[table[(a,m)]["tflops"] for m in THERMAL_MODES],0.15,label=a)
        ax.set_xticks(x,[THERMAL_NAMES[m] for m in THERMAL_MODES])
        ax.set_ylabel("Sustained TFLOP/s"); ax.set_title(" / ".join(key),fontsize=10)
        ax.grid(axis="y",alpha=0.2)
    axs[0,0].legend(ncol=3, fontsize=8)
    fig.suptitle("Uncalibrated chip-scale screening model",fontsize=12)
    fig.tight_layout(rect=(0,0,1,0.99)); fig.savefig(out/"throughput.png",dpi=160); plt.close(fig)
    # One diagnostic per workload, unrestricted-data-placement, hottest nonuniform case.
    for work in sorted({r["workload"] for r in rows}):
        selected = [r for r in rows if r["workload"] == work and r["scenario"] == "gradient_uniform"
                    and r["placement"] == "free" and r["thermal_mode"] == 2
                    and r["fabric"] in ("local","global_ideal","mesh_paid")]
        if not selected:
            continue
        grid = int(np.sqrt(len(selected[0]["power_w"])/2))
        n = grid*grid
        fig,axs = plt.subplots(2,3,figsize=(10,6))
        vmin=min(min(r["temperature_c"]) for r in selected); vmax=max(max(r["temperature_c"]) for r in selected)
        for c,r in enumerate(selected):
            for z in range(2):
                im=axs[z,c].imshow(np.asarray(r["temperature_c"])[z*n:(z+1)*n].reshape(grid,grid),vmin=vmin,vmax=vmax,cmap="inferno")
                axs[z,c].set_title(f'{r["fabric"]} / {"logic" if z==0 else "DRAM"}')
        fig.colorbar(im,ax=axs.ravel().tolist(),label="Region temperature (°C)",shrink=0.8)
        fig.savefig(out/f"temperature_{work}.png",dpi=160); plt.close(fig)


def write_report(summaries, out):
    lines = ["# Pilot screening results", "", "These are optimized steady-state model bounds, not measured hardware performance.",
             "Costs are uncalibrated. Fixed-layout and ideal-connection signals cannot pass the architecture gate.", "",
             "| Scenario | Workload | Placement | Candidate | T0 matched | T1 scalar | T1 layer | T2 matched | T2/T1 layer | T2 net | Class |",
             "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for s in summaries:
        lines.append(f'| {s["scenario"]} | {s["workload"]} | {s["placement"]} | {s["candidate"]} | '
                     f'{s["speedup_t0"]:.4f} | {s["speedup_t1"]:.4f} | {s["speedup_t1_layer"]:.4f} | {s["speedup_t2"]:.4f} | '
                     f'{s["spatial_interaction_ratio"]:.4f} | {s["net_speedup_t2_vs_original_local"]:.4f} | {s["screening_class"]} |')
    lines += ["", "Paid fabric is compared to local_matched (same reserved routing area and idle power).",
              "Ideal fabric is compared to local. Scheduling and DVFS are reoptimized for every cell.",
              "Free placement optimizes resident bank fractions within the same per-bank data-capacity bound.",
              "Gate requires complete fixed/free controls, optimized free layout, paid costs, >5% net and matched gain,",
              "T0 and T1_layer net gains <=1%, and T2/T1_layer net interaction >1%. Passing still requires execution/physical validation.",
              "T1_scalar is retained only for legacy reproduction; T1_layer preserves both layer power sources and limits.",
              "T0/T1 solutions can violate the physical spatial temperature limits; their physical temperatures remain reported.",
              "Both architectures may use the tracker-bound row-miss option; it is an oracle upper bound, not an implementation of Voxel.",
              "", "## Interpretation limits", "",
              "This LP admits perfectly divisible work, fractional DVFS time sharing, ideal input broadcast, and no reduction overhead.",
              "It has no transient thermal closure, temperature-dependent refresh/leakage, or cycle-level bank scheduler.",
              "Free placement is selected for a stationary kernel. Real multi-operator capacity, relocation cost, and phase dependencies are absent.",
              "The 4×4 coarse thermal mesh assumes one temperature per active region. Subregion hotspots and mesh convergence need validation.",
              "A topology claim requires calibrated cost/thermal parameters, native HotSpot/3D-ICE cross-checks, and workload traces."]
    (out/"report.md").write_text("\n".join(lines)+"\n")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="configs/pilot.json")
    p.add_argument("--output",required=True)
    p.add_argument("--thermal-backend",choices=["scipy","hits"],default="scipy")
    p.add_argument("--suite",choices=["pilot","sensitivity"],default="pilot")
    args=p.parse_args()
    out=Path(args.output)
    if out.exists():
        raise SystemExit("Output directory exists; choose a new directory to preserve evidence")
    out.mkdir(parents=True)
    cfg=json.loads(Path(args.config).read_text())
    started=time.time(); rows=[]; thermal_records=[]
    n=cfg["grid"]**2; uniform=np.ones(n)/n
    skew=uniform.copy()
    center=[5,6,9,10] if cfg["grid"] == 4 else [n//2]
    skew[center]*=4; skew/=skew.sum()
    scenarios=[("uniform",0.0,uniform),("center_skew",0.0,skew),("gradient_uniform",0.6,uniform)]
    if args.suite == "sensitivity":
        scenarios=[("uniform",0.0,uniform),("gradient_uniform",0.6,uniform)]
    for name,gradient,profile in scenarios:
        base=copy.deepcopy(cfg); base["thermal"]["cooling_gradient"]=gradient
        variants=[("base",base)]
        if args.suite == "sensitivity":
            variants=[]
            # One factor at a time, no best-case filtering. Zero-cost controls retained.
            sweeps={"vertical_scale":[0.1,1.0,10.0],"mesh_link_tb_s":[0.0625,0.25,1.0],
                    "mesh_pj_per_byte_hop":[0.0,0.5,2.0],"fabric_area_fraction":[0.0,0.03,0.1],
                    "dram_pj_per_byte":[3.0,12.0,24.0],"cooling_gradient":[0.0,0.3,0.6]}
            for key,values in sweeps.items():
                for val in values:
                    c=copy.deepcopy(base)
                    c["thermal" if key in ("vertical_scale","cooling_gradient") else "hardware"][key]=val
                    variants.append((f"{key}={val}",c))
        for variant,c in variants:
            h,gh,record=response(c["grid"],c["thermal"],args.thermal_backend)
            record.update(scenario=name,variant=variant); thermal_records.append(record)
            label=name if args.suite == "pilot" else name+"/"+variant
            for workload,placement,fabric,mode in itertools.product(c["workloads"],["fixed","free"],fabric_cases(c["hardware"]),THERMAL_MODES):
                r=best_tiling(c,h,gh,workload,fabric,mode,profile,placement)
                r["scenario"]=label; rows.append(r)
            print(f"Completed {label}: {len(rows)} optimized design points",flush=True)
    summaries=summarize(rows)
    source_commit=revision()
    dirty=subprocess.check_output(["git","status","--porcelain"],text=True).strip() if source_commit != "unknown" else "unknown"
    provenance={"schema_version":2,"thermal_controls":THERMAL_NAMES,"source_commit":source_commit,"source_dirty":bool(dirty),"python":sys.version,"platform":platform.platform(),
                "numpy":np.__version__,"scipy":scipy.__version__,
                "invocation":["python","-m","thermal_exploration.run"]+sys.argv[1:],
                "started_utc":datetime.fromtimestamp(started,timezone.utc).isoformat(),
                "config_sha256":hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
                "elapsed_s":time.time()-started,"suite":args.suite,"thermal_backend":args.thermal_backend,
                "model_scope":"uncalibrated, chip-scale, linear steady-state divisible-work relaxation"}
    if args.thermal_backend == "hits":
        import hits
        provenance["hits_commit"]=revision(Path(hits.__file__).resolve().parent.parent)
    (out/"config.json").write_text(json.dumps(cfg,indent=2)+"\n")
    for file,data in [("results.json",rows),("summary.json",summaries),("thermal_validation.json",thermal_records),("provenance.json",provenance)]:
        (out/file).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
    fields=[k for k,v in rows[0].items() if not isinstance(v,(list,dict))]
    with (out/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n");w.writeheader();w.writerows(rows)
    write_report(summaries,out)
    plot(rows,summaries,out)
    print(json.dumps({"output":str(out),"design_points":len(rows),"status":"PASS","elapsed_s":time.time()-started}))


if __name__ == "__main__":
    main()
