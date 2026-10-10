"""G3.1–G3.3: shared-service regression and source-isolated reference checks."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform as runtime_platform
import subprocess
import sys

import numpy as np
import scipy

from .model import optimize
from .multiphase import g2_fabrics, optimize_cycle
from .hardware_contract import (area_inventory, geometry, hb_interface_contract, load_profile,
                               power_inventory, tier_bound, top_cooling_necessary_bound)
from .run import revision
from .thermal import THERMAL_MODES, response


def check_shared_service():
    # This is an entry-point regression on the unchanged screening machine,
    # explicitly not a Stratum performance/thermal experiment.
    cfg=json.loads(Path("configs/pilot.json").read_text());cfg["thermal"]["cooling_gradient"]=0.6
    g2=json.loads(Path("configs/g2.json").read_text());h,gh,_=response(cfg["grid"],cfg["thermal"])
    records=[]
    for cap,queue in ((None,512),(.01,512),(100,1)):
        c=copy.deepcopy(cfg);c["hardware"]["outstanding_per_tile"]=queue
        if cap is not None:c["hardware"]["internal_bank_group_ceiling_tb_s"]=cap
        for w in c["workloads"]:
            g=copy.deepcopy(g2);g["phases"]=[w["name"]]*2
            t=next(t for t in c["tilings"] if t["name"]==g["tiling"])
            for f in (g2_fabrics(c["hardware"])[0],g2_fabrics(c["hardware"])[4]):
                for mode in THERMAL_MODES:
                    a=optimize(c,h,gh,w,t,f,mode,np.ones(16)/16,"free")
                    b=optimize_cycle(c,g,h,gh,(1,1),f,mode,"independent_oracle")
                    error=max(abs(s["tflops"]/a["tflops"]-1) for s in b["phases"])
                    if error>1e-7:raise RuntimeError("G1/G2 phase service mismatch")
                    records.append(dict(cap_tb_s=cap,queue_entries=queue,workload=w["name"],fabric=f.name,
                                        thermal_mode=mode,g1_tflops=a["tflops"],
                                        g2_phase0_tflops=b["phases"][0]["tflops"],
                                        g2_phase1_tflops=b["phases"][1]["tflops"],max_relative_error=error))
    return records


def audit_profile(p):
    g=geometry(p);tiers=[tier_bound(p,i) for i in range(p["dram"]["timing_tier_count"])]
    areas=area_inventory(p);power=power_inventory(p)
    ref=p["dram"]["reported_internal_bandwidth_tb_s"];policy=p["calibration_policy"]
    fast=tiers[0]["bank_only_full_row_ceiling_tb_s"];slow=tiers[-1]["bank_only_full_row_ceiling_tb_s"]
    errors=dict(fast_body_bandwidth=fast/ref["body_max"]-1,
                slow_body_bandwidth=slow/ref["body_min"]-1,
                fast_table3_bandwidth=fast/ref["table3_max"]-1,
                topology_vs_reported_peak=g["topology_peak_tflops"]/p["logic"]["reported_peak_tflops"]-1)
    rounded=all(abs(errors[k])<=policy["reference_rounded_relative_tolerance"] for k in ("fast_body_bandwidth","slow_body_bandwidth"))
    power_match=abs(power["dram_relative_error_vs_approx"])<=policy["reference_rounded_relative_tolerance"]
    logic_match=abs(power["logic_relative_error"])<=policy["logic_power_closure_relative_tolerance"]
    external=p["external_xpu_interface"]
    return dict(profile_id=p["profile_id"],geometry=g,tiers=tiers,areas=areas,power=power,reference_errors=errors,
                hb_interface=hb_interface_contract(p),
                legacy_parameter_check=dict(cooling_necessary_upper_bound_w=top_cooling_necessary_bound(.02**2,4000,25,85),
                    dram_transfer_only_at_16tb_s_w=16*12,
                    conclusion="Legacy 16 TB/s operation is infeasible by energy conservation before internal thermal resistances; not an architecture discovery"),
                external_xpu_interface_tb_s=external["channels"]*external["data_bits_per_channel"]*external["gbps_per_pin"]/8/1000,
                gates={"G3.1":{"status":"PARTIAL","known_organization_and_tier_timing":"MATCHED",
                               "rounded_body_bank_bandwidth_anchor_pass":rounded,"rounded_104w_dram_aggregate_anchor_pass":power_match,
                               "ACT_PRE_background_and_physical_split":"UNIDENTIFIED","actual_sustained_bandwidth_calibrated":False},
                       "G3.2":{"status":"NOT_CALIBRATED","area_inventory_closed_within_rounding":abs(areas["relative_difference"])<.005,
                               "logic_power_composition_reference_check_pass":logic_match,
                               "separate_SRAM_NoC_controller_coefficients":"UNIDENTIFIED"},
                       "G3.3":{"status":"UNKNOWN","HB_physical_interface_complete":False},
                       "G4_Stratum_command_model":{"status":"NOT_READY"},"G5":{"status":"DEFERRED"}},
                whole_model_calibration_gate_pass=False,prediction_allowed=False,unresolved_inputs=p["unresolved_inputs"])


def plot(audit,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tiers=audit["tiers"];p=audit["power"]
    fig,axs=plt.subplots(1,2,figsize=(11,4))
    axs[0].plot([t["tier"]+1 for t in tiers],[t["bank_only_full_row_ceiling_tb_s"] for t in tiers],"o-")
    axs[0].set(xlabel="Timing tier (fast to slow)",ylabel="Conditional bank-cycle ceiling (TB/s)",title="4096 B/ACT, 256 banks; other domains unknown")
    axs[0].grid(alpha=.2)
    axs[1].bar([0,1],[p["logic_reference_w"],p["mac_plus_figure_memory_communication_w"]],color=["C0","C1"])
    axs[1].bar_label(axs[1].containers[0],fmt="%.3f W",padding=3)
    axs[1].set_xticks([0,1],["Reported Logic total","MAC-energy estimate +\nreported memory/comm group"])
    axs[1].set(ylabel="Power (W)",title="Unresolved reference scope/activity discrepancy",ylim=(0,52))
    axs[1].grid(axis="y",alpha=.2)
    fig.suptitle("Stratum reference checks / calibration gate remains open")
    fig.tight_layout();fig.savefig(out/"reference_checks.png",dpi=180);plt.close(fig)


def write_report(audit,records,out):
    p=audit["power"];a=audit["areas"];e=audit["reference_errors"]
    lines=["# G3.1–G3.3 Model Calibration Gate", "",
           "G4.1 shared-service regression passes. Stratum's known inventory and rounded aggregate anchors are reproduced.",
           "G3.1 is partial, G3.2 is NOT_CALIBRATED, G3.3 physical HB contract is UNKNOWN. Prediction is disabled.", "",
           f'Shared service: {len(records)} comparisons, max relative G1/G2 phase rate error {max(r["max_relative_error"] for r in records):.3e}.', "",
           "| Timing tier | tRCD ns | tRAS ns | tRC ns | Bank-only full-row ceiling TB/s |",
           "|---|---:|---:|---:|---:|"]
    for t in audit["tiers"]:
        lines.append(f'| {t["tier"]+1} | {t["tRCD_ns"]:.2f} | {t["tRAS_ns"]:.2f} | {t["tRC_ns"]:.2f} | {t["bank_only_full_row_ceiling_tb_s"]:.5f} |')
    lines += ["", "The eight timing tiers partition rows within each bank; they are not eight independent copies of all banks.",
              "These are necessary bank-cycle bounds; ACT/column domain, HB and queue constraints are not calibrated.", "",
              "| Check | Derived | Reference | Relative error |",
              "|---|---:|---:|---:|",
              f'| Fast bank-only TB/s | {audit["tiers"][0]["bank_only_full_row_ceiling_tb_s"]:.6f} | 30.34 (body) | {e["fast_body_bandwidth"]:.4%} |',
              f'| Slow bank-only TB/s | {audit["tiers"][-1]["bank_only_full_row_ceiling_tb_s"]:.6f} | 19.01 (body) | {e["slow_body_bandwidth"]:.4%} |',
              f'| DRAM aggregate W at 30.34 TB/s | {p["dram_aggregate_at_reference_bandwidth_w"]:.6f} | 104 (approximate) | {p["dram_relative_error_vs_approx"]:.4%} |',
              f'| Logic MAC + reported memory/comm W | {p["mac_plus_figure_memory_communication_w"]:.6f} | {p["logic_reference_w"]} | {p["logic_relative_error"]:.4%} |',
              f'| Active Logic leaf area mm² | {a["leaf_total_mm2"]:.6f} | {a["reported_active_mm2"]} | {a["relative_difference"]:.4%} |', "",
              "Reported versus topology TFLOPS, body versus Table-3 bandwidth, and detailed versus approximate DRAM power remain separate in audit.json.",
              "The 0.429 pJ/bit value is an aggregate device anchor, not an identified dynamic byte coefficient.",
              "SRAM/NoC/controller/vector energy, ACT/PRE/background split and physical heat-source partition remain null.",
              "No residual is silently assigned to a component; no DDR speed-bin timings or legacy cooling parameters are imported.", "",
              "Legacy pilot: top-only convection permits at most 96 W when all active regions remain ≤85°C; 16 TB/s ×12 pJ/B already requires 192 W before other activity. This parameter combination forces throttling. It is not evidence about Stratum cooling.", "",
              "Source: [Stratum v1, Tables 1/3 and Figure 15](https://arxiv.org/html/2510.05245v1).",
              "G5 thermal closure is deferred; standard HBM3 integration is separate from the unknown Mono3D command model. Fabric remains closed."]
    (out/"report.md").write_text("\n".join(lines)+"\n")


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--profile",default="configs/platforms/stratum_micro2025.json")
    parser.add_argument("--output",required=True);args=parser.parse_args();out=Path(args.output)
    if out.exists():raise SystemExit("Preserve earlier evidence: choose a new directory")
    out.mkdir(parents=True);p=load_profile(args.profile);audit=audit_profile(p);records=check_shared_service()
    audit["gates"]["G4.1"]=dict(status="PASS",comparisons=len(records),max_relative_phase_rate_error=max(r["max_relative_error"] for r in records))
    for name,data in (("profile.json",p),("audit.json",audit),("shared_service_checks.json",records)):
        (out/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
    for name,rows in (("tier_checks.csv",audit["tiers"]),("area_inventory.csv",audit["areas"]["leaves"]),("shared_service_checks.csv",records)):
        with (out/name).open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
    provenance=dict(source_commit=revision(),source_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True).strip()),
                    started_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
                    platform=runtime_platform.platform(),profile_sha256=hashlib.sha256(Path(args.profile).read_bytes()).hexdigest(),
                    invocation=["python","-m","thermal_exploration.calibrate"]+sys.argv[1:],
                    scope="source-isolated reference accounting; legacy LP entry-point regression; no Stratum thermal/timing simulator")
    (out/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    write_report(audit,records,out);plot(audit,out)
    print(json.dumps({"execution_status":"PASS","gates":audit["gates"],"whole_model_calibration_gate_pass":False}))


if __name__=="__main__":main()
