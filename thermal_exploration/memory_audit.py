"""Necessary DRAM rate ceilings coupled to the existing fixed Local NPU.

No command trace is simulated. Minima of independent rate limits are optimistic
upper bounds, not achievable schedules. Subarray mode relaxes bank ACT rate
only: it retains activation-domain limits and shared column I/O.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from datetime import datetime, timezone

import numpy as np
import scipy

from .model import fabric_cases, kernel, optimize
from .run import revision
from .thermal import THERMAL_MODES, response
from .memory_service import memory_service_model


def internal_ceilings(audit, traffic, subarrays=1):
    org = audit["organization"]; t = audit["timing_ns"]
    useful = traffic["useful_bytes_per_activation"]
    banks = traffic["busy_banks_per_group"]
    if not 0 < useful <= org["physical_row_bytes"] or not 0 < banks <= org["banks_per_group"]:
        raise ValueError("Invalid traffic row utilization or bank parallelism")
    if subarrays < 1 or any(v <= 0 for v in t.values()):
        raise ValueError("Positive subarray count and timing required")
    # byte/ns -> TB/s divides by 1000; tRC = tRAS + tRP.
    return {
        "bank_act_pre_tb_s": useful * banks * subarrays / (t["tRAS"] + t["tRP"]) / 1000,
        "activation_tRRD_tb_s": useful * org["activation_domains_per_group"] / t["tRRD"] / 1000,
        "activation_tFAW_tb_s": useful * org["activation_domains_per_group"] * 4 / t["tFAW"] / 1000,
        "column_periphery_tb_s": org["bytes_per_column_command"] * org["column_domains_per_group"] / t["tCCD"] / 1000,
    }


def power_breakdown(audit, bandwidth_tb_s):
    e = audit["energy"]; useful = audit["useful_bytes_per_activation"]
    acts = bandwidth_tb_s * 1e12 / useful
    return {"act_count_s": acts, "pre_count_s": acts,
            "act_power_w": acts * e["act_nj"] * 1e-9,
            "pre_power_w": acts * e["pre_nj"] * 1e-9,
            "array_dynamic_power_w": bandwidth_tb_s * e["array_pj_per_useful_byte"],
            "peripheral_dynamic_power_w": bandwidth_tb_s * e["peripheral_pj_per_useful_byte"]}


def plot(rows, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    works = sorted({r["workload"] for r in rows})
    cases = list(dict.fromkeys(r["traffic"] for r in rows))
    fig, axs = plt.subplots(1, len(works), figsize=(12, 4), squeeze=False)
    for ax, work in zip(axs[0], works):
        for index, case in enumerate(cases):
            for mode in (0, 2):
                selected = [r for r in rows if r["workload"] == work and r["traffic"] == case
                            and r["thermal_mode"] == mode and r["ideal_subarrays"] == 1]
                ax.plot([r["hb_chip_tb_s"] for r in selected], [r["used_bandwidth_tb_s"] for r in selected],
                        marker="o", color=f"C{index}", linestyle="--" if mode == 0 else "-",
                        label=case + (" / T0" if mode == 0 else " / T2"))
        ax.set(xlabel="HB peak (TB/s)", ylabel="Local LP useful DRAM bandwidth (TB/s)", title=work)
        ax.grid(alpha=.2)
    axs[0, 1].legend(fontsize=7)
    fig.suptitle("Illustrative necessary rate bounds / uncalibrated Local NPU")
    fig.tight_layout(); fig.savefig(out/"bandwidth_limits.png", dpi=180); plt.close(fig)


def report(rows, out):
    lines = ["# HB–DRAM necessary rate audit", "",
             "Illustrative parameter assumptions; optimistic independent rate ceilings, no command-level schedule or physical validation.",
             "All resources remain Local. The subarray control is an uncharged known-mechanism oracle, not a new architecture.", "",
             "16 TB/s HB, conventional bank serialization, gradient cooling:", "",
             "| Traffic | Workload | Noheat limiting ceiling | Internal ceiling TB/s | T0 useful TB/s | T1 layer useful TB/s | T2 useful TB/s | Thermal loss vs T0 | Timing-only relaxation loss at T2 |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        if r["thermal_mode"] != 2 or r["hb_chip_tb_s"] != 16 or r["ideal_subarrays"] != 1:
            continue
        def get(mode):
            return next(s["used_bandwidth_tb_s"] for s in rows if s["traffic"] == r["traffic"] and s["workload"] == r["workload"]
                        and s["thermal_mode"] == mode and s["hb_chip_tb_s"] == 16 and s["ideal_subarrays"] == 1)
        lines.append(f'| {r["traffic"]} | {r["workload"]} | {r["dominant_noheat_ceiling"]} | '
                     f'{r["internal_ceiling_tb_s"]:.4f} | {get(0):.4f} | {get(3):.4f} | {r["used_bandwidth_tb_s"]:.4f} | '
                     f'{r["thermal_loss_vs_noheat"]:.2%} | {r["timing_limit_loss_fraction"]:.2%} |')
    lines += ["", "Loss columns describe different counterfactuals and must not be added together.",
              "Small useful bytes/ACT and bank concentration are already targets of locality, mapping, Tracker and SALP techniques.",
              "tRRD/tFAW and column-domain scope require actual HB device information. No unresolved HB-specific bottleneck is established."]
    (out/"report.md").write_text("\n".join(lines)+"\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/memory_audit.json")
    p.add_argument("--output", required=True)
    p.add_argument("--thermal-backend", choices=("scipy", "hits"), default="scipy")
    args = p.parse_args(); out = Path(args.output)
    if out.exists():
        raise SystemExit("Choose a new directory to preserve evidence")
    out.mkdir(parents=True); started = time.time()
    audit = json.loads(Path(args.config).read_text())
    base = json.loads(Path(audit["base_config"]).read_text())
    base["thermal"]["cooling_gradient"] = audit["cooling_gradient"]
    h, gh, validation = response(base["grid"], base["thermal"], args.thermal_backend)
    n = base["grid"] ** 2; rows = []; ceilings = []
    for traffic in audit["traffic_cases"]:
        for subarrays in (1, audit["organization"]["ideal_subarrays_per_bank"]):
            limits = internal_ceilings(audit, traffic, subarrays)
            internal = min(limits.values())
            ceilings.append(dict(traffic=traffic["name"], ideal_subarrays=subarrays,
                                 **{k: v * n for k, v in limits.items()}))
            for hb in audit["hb_chip_tb_s"]:
                cfg = copy.deepcopy(base); hw = cfg["hardware"]
                hw["bank_group_peak_tb_s"] = hb / n
                hw["internal_bank_group_ceiling_tb_s"] = internal
                hw["dram_pj_per_byte"] = sum(audit["energy"][k] for k in ("array_pj_per_useful_byte", "peripheral_pj_per_useful_byte"))
                hw["activation_nj"] = audit["energy"]["act_nj"] + audit["energy"]["pre_nj"]
                tiling = dict(name="audit_row_burst", chunk_bytes=traffic["useful_bytes_per_activation"], row_miss_fraction=1.0)
                fabric = fabric_cases(hw)[0]
                for workload in cfg["workloads"]:
                    intensity = kernel(workload, tiling)["intensity"]
                    service = memory_service_model(hw, kernel(workload, tiling))
                    logic_bw = n * hw["tile_peak_tflops"] / intensity
                    queue_bw = n * hw["outstanding_per_tile"] * hw["transaction_bytes"] / service.read_latency_ns / 1000
                    ceilings_all = dict(HB=hb, DRAM_internal=internal * n, Logic_consumption=logic_bw, Request_capacity=queue_bw)
                    dominant = min(ceilings_all, key=ceilings_all.get)
                    # Release timing only, preserving ACT/PRE energy and all NPU resources.
                    released = copy.deepcopy(cfg)
                    released["hardware"]["internal_bank_group_ceiling_tb_s"] = hb / n
                    noheat = optimize(cfg, h, gh, workload, tiling, fabric, 0, np.ones(n)/n, "free")
                    for mode in THERMAL_MODES:
                        r = noheat if mode == 0 else optimize(cfg, h, gh, workload, tiling, fabric, mode, np.ones(n)/n, "free")
                        oracle = optimize(released, h, gh, workload, tiling, fabric, mode, np.ones(n)/n, "free")
                        breakdown = power_breakdown(dict(audit, **traffic), r["used_bandwidth_tb_s"])
                        row = {k:v for k,v in r.items() if not isinstance(v, (dict, list))}
                        row.update(traffic=traffic["name"], ideal_subarrays=subarrays, hb_chip_tb_s=hb,
                                   physical_row_utilization=traffic["useful_bytes_per_activation"]/audit["organization"]["physical_row_bytes"],
                                   busy_banks_per_group=traffic["busy_banks_per_group"],
                                   internal_ceiling_tb_s=internal*n, logic_consumption_ceiling_tb_s=logic_bw,
                                   request_ceiling_tb_s=queue_bw, dominant_noheat_ceiling=dominant,
                                   first_activation_to_column_latency_ns=audit["timing_ns"]["tRCD"],
                                   hb_utilization=r["used_bandwidth_tb_s"]/hb,
                                   thermal_loss_vs_noheat=1-r["tflops"]/noheat["tflops"],
                                   timing_release_throughput_upper_bound_tflops=oracle["tflops"],
                                   timing_limit_loss_fraction=1-r["tflops"]/oracle["tflops"], **breakdown)
                        energy_check = hw["dram_static_w"]*n + sum(breakdown[k] for k in
                            ("act_power_w", "pre_power_w", "array_dynamic_power_w", "peripheral_dynamic_power_w"))
                        if not np.isclose(energy_check, r["dram_power_w"], atol=1e-7):
                            raise RuntimeError("DRAM energy accounting mismatch")
                        rows.append(row)
    for name, data in (("config.json", audit), ("results.json", rows), ("internal_ceilings.json", ceilings), ("thermal_validation.json", validation)):
        (out/name).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")
    with (out/"results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    import subprocess
    provenance = dict(source_commit=revision(), source_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
                      thermal_backend=args.thermal_backend, design_points=len(rows),
                      python=sys.version, platform=platform.platform(), numpy=np.__version__, scipy=scipy.__version__,
                      invocation=["python", "-m", "thermal_exploration.memory_audit"]+sys.argv[1:],
                      started_utc=datetime.fromtimestamp(started, timezone.utc).isoformat(),
                      config_sha256=hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
                      base_config_sha256=hashlib.sha256(Path(audit["base_config"]).read_bytes()).hexdigest(),
                      elapsed_s=time.time()-started,
                      scope="necessary rate ceilings + uncalibrated Local LP, no command schedule or new architecture")
    # The noheat LP is reused; four constrained plus four released solves per 4 rows.
    provenance["lp_solves"] = len(rows)//4*8
    if args.thermal_backend == "hits":
        import hits
        provenance["hits_commit"] = revision(Path(hits.__file__).resolve().parent.parent)
    (out/"provenance.json").write_text(json.dumps(provenance, indent=2)+"\n")
    report(rows, out); plot(rows, out)
    print(json.dumps(provenance))


if __name__ == "__main__":
    main()
