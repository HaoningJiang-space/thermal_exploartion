"""H1 finite traffic audit, reusing D1 evidence without new device claims."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from .horizontal import gemm, redistribution, moe, capacity_bounds, scaling_example, KINDS
from .run import revision


def write_table(path, rows):
    with path.open("w", newline="") as handle:
        writer=csv.DictWriter(handle,list(rows[0]),lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def figures(out, points):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(12,7.5),sharex=True)
    for i,(shape,label) in enumerate((("square","4096 x 4096"),("wide","1024 x 16384"),("tall","16384 x 1024"))):
        for j,batch in enumerate((1,32)):
            ax=axes[j,i]; rows=[r for r in points if r["case"]==f"{shape}_b{batch}" and r["link_gb_s"]==32]
            for key,title,color,style in (("baseline","Row partition / XY tree","#bf8547","-"),
                    ("best_tested_ownership","Best tested partition/tree","#267b9b","-"),
                    ("infinite_noc","Infinite links (ideal)","#777777","--")):
                chosen=sorted((r for r in rows if r["control"]==key),key=lambda r:r["hb_tb_s"])
                ax.plot([r["hb_tb_s"] for r in chosen],[r["rate_upper"] for r in chosen],style,color=color,marker="o",markersize=4,label=title)
            ax.set(title=f"{label}, batch {batch}",ylabel="TFLOP/s capacity upper bound",xlabel="HB bandwidth counterfactual (TB/s)")
            ax.set_xscale("log",base=2);ax.set_xticks([1,4,16,32],["1","4","16","32"]);ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=7)
    fig.suptitle("H1: topology/dataflow capacity pressure; NOT measured execution speedup")
    fig.tight_layout()
    for ext in ("png","pdf"): fig.savefig(out/f"horizontal_capacity.{ext}",dpi=180)
    plt.close(fig)
    selected=[r for r in points if r["hb_tb_s"]==32 and r["link_gb_s"]==32 and r["control"]=="baseline"]
    selected += [r for r in points if r["case"]=="wide_b32" and r["hb_tb_s"]==32 and r["link_gb_s"]==32 and r["control"]=="best_tested_ownership"]
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    labels=[r["case"] if r["control"]=="baseline" else "wide_b32_column_control" for r in selected]
    for ax,axis in zip(axes,("x","y")):
        bottom=[0.]*len(selected)
        for kind,color in zip(KINDS,("#267b9b","#bf8547","#8b93b0","#71a58a")):
            # Choose one heavier cut direction, not a different direction for
            # each kind (that would silently mix full-duplex capacities).
            cuts=[max((c for c in r["cuts"] if c["axis"]==axis),key=lambda c:sum(c["bytes_by_kind"].values())) for r in selected]
            values=[c["bytes_by_kind"][kind]/2**20 for c in cuts]
            ax.bar(labels,values,bottom=bottom,label=kind,color=color)
            bottom=[a+b for a,b in zip(bottom,values)]
        ax.set(title=f"Central {axis} cut: heavier single direction",ylabel="Routed byte volume (MiB)")
        ax.tick_params(axis="x",rotation=60,labelsize=8)
    axes[0].legend(fontsize=8)
    fig.suptitle("Tensor-derived broadcast, reduction, redistribution and expert exchange")
    fig.tight_layout()
    for ext in ("png","pdf"): fig.savefig(out/f"cut_traffic.{ext}",dpi=180)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True)
    args=parser.parse_args();out=Path(args.output)
    if out.exists(): raise ValueError("Preserve previous experiments")
    out.mkdir(parents=True)
    evidence=Path(__file__).resolve().parents[1]/"results/d1-2026-10-10/command-cases.csv"
    with evidence.open() as handle:
        baseline=next(r for r in csv.DictReader(handle) if r["case"]=="baseline")
    dram=float(baseline["tb_s"])
    profile=dict(side=4,tiles=16,logic_area_mm2=121,logic_reference_footprint_mm2=76.55,
        additional_reserved_noc_area_mm2=3,dram_capacity_bytes=32*2**30,fast_tier_capacity_bytes=4*2**30,
        sram_bytes=36*2**20,mac_tflops=128,vector_gadd_s_per_tile=64,link_gb_s_per_direction=32,
        hb_tb_s=[1,4,16,32],link_sensitivity_gb_s=[16,64],dram_full_row_tb_s=dram,
        service_anchor_scope="Assumed delivery cap anchored in D1; the measured steady rate is not a proven maximum over other traces/controllers",
        dram_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
        classification="Mode B assumed chip-scale capacity screen; no timed NoC or new command execution",
        noc_hop_energy_pj_byte=1,noc_energy_scope="Assumed traffic accounting only; no thermal feedback",
        assumptions=["Optimistic full-row service ceiling, not guaranteed operator delivery",
            "Canonical distributed input/output; static local W layouts, no migration",
            "Ideal spatial MAC utilization; SRAM port and buffering limits unmodelled",
            "Full-duplex links, no router/arbitration/latency or task-dependency timing",
            "In-compute-Tile reduction, FP32 partials and FP16 input/output",
            "HB/link capacity changes are isolation counterfactuals, not manufacturable configurations"])
    (out/"profile.json").write_text(json.dumps(profile,indent=2)+"\n")
    cases=[]
    for shape,m,n in (("square",4096,4096),("wide",1024,16384),("tall",16384,1024)):
        for batch in (1,32):
            options=[]
            for rows in (1,2,4,8,16):
                for orientation in ("row","column"):
                    for order in ("xy","yx"):
                        options.append(gemm(m,n,batch,rows,16//rows,orientation,order))
            default=next(o for o in options if o[2]==dict(row_parts=16,column_parts=1,orientation="row",tree_order="xy"))
            cases.append((f"{shape}_b{batch}",default,options))
    cases += [("redistribution",redistribution(),[redistribution(),redistribution(True)]),
              ("moe_cohort",moe(),[moe(shift) for shift in range(16)])]
    points=[];flow_rows=[];all_options=[]
    capacities=[(hb,32) for hb in profile["hb_tb_s"]]+[(32,bw) for bw in profile["link_sensitivity_gb_s"]]
    for name,default,options in cases:
        if len({(o[1]["weight_bytes"],o[1]["mac_flops"]) for o in options})!=1:
            raise ValueError("Unfair ownership control changed memory/MAC work")
        for index,(traffic,work,partition) in enumerate(options):
            if work["weight_bytes"]>profile["fast_tier_capacity_bytes"]:
                raise ValueError("Fast-tier capacity exceeded")
            all_options.append(dict(case=name,option=index,work=work,partition=partition,byte_hops=traffic.totals(),vector_ops=sum(traffic.vector_ops.values())))
            for record in traffic.records:flow_rows.append(dict(case=name,option=index,**record))
        for hb,link in capacities:
            evaluated=[]
            for index,(traffic,work,partition) in enumerate(options):
                result=capacity_bounds(traffic,work,hb,dram,link)
                evaluated.append((result,partition,index))
                points.append(dict(case=name,control="tested_ownership",option=index,hb_tb_s=hb,link_gb_s=link,partition=partition,**result))
            best=min(evaluated,key=lambda r:(r[0]["completion_necessary_lower_us"],
                sum(r[0]["byte_hops_by_kind"].values()),r[0]["vector_additions"]))
            # Minimum necessary time in this family is not a feasible schedule
            # or a global optimum over arbitrary ownership/architectures.
            points.append(dict(case=name,control="best_tested_ownership",option=best[2],hb_tb_s=hb,link_gb_s=link,partition=best[1],**best[0]))
            for control,relax in (("baseline","none"),("infinite_noc","infinite_noc"),("zero_collectives","zero_collectives")):
                traffic,work,partition=default
                points.append(dict(case=name,control=control,option="baseline",hb_tb_s=hb,link_gb_s=link,partition=partition,
                                   **capacity_bounds(traffic,work,hb,dram,link,relax)))
    write_table(out/"routed-flows.csv",flow_rows)
    (out/"all-options.json").write_text(json.dumps(all_options,indent=2)+"\n")
    (out/"all-points.json").write_text(json.dumps(points,indent=2)+"\n")
    compact=[dict(case=r["case"],control=r["control"],option=r["option"],hb_tb_s=r["hb_tb_s"],link_gb_s=r["link_gb_s"],
                  time_lower_us=r["completion_necessary_lower_us"],rate_upper=r["rate_upper"],metric=r["metric"],
                  binding="+".join(r["binding_resources"]),**{k+"_us":v for k,v in r["resource_lower_us"].items()}) for r in points]
    write_table(out/"all-points.csv",compact)
    (out/"scaling-example.json").write_text(json.dumps([scaling_example(s) for s in (4,8,16)],indent=2)+"\n")
    (out/"gate.json").write_text(json.dumps(dict(status="CAPACITY_SCREEN_ONLY",research_status="CHECK_KNOWN_DATAFLOW_AND_TIMED_COMMUNICATION",
        hardware_status="NOT_ASSESSED",scope="Necessary bounds/byte-hop accounting; no actual NoC stalls, speedup, thermal closure or novelty claim",
        ownership_scope="Finite known partitions/tree directions only; not an unrestricted ownership oracle",
        next_requirement="Remaining signal after known mapping/collectives, then bounded-buffer causal execution and costs"),indent=2)+"\n")
    (out/"provenance.json").write_text(json.dumps(dict(source_commit=revision(),source_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True).strip()),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),input_evidence="results/d1-2026-10-10/command-cases.csv",
        new_ramulator_execution=False,thermal_execution=False,scope=profile["classification"]),indent=2)+"\n")
    figures(out,points)
    print("H1 complete: traffic/capacity audit; no execution-speedup claim",flush=True)


if __name__=="__main__":main()
