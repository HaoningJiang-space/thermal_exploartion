"""Continuous, divisible-work steady-state upper bounds via linear programming.

One flow x[i,j,k] assigns TFLOP/s served by bank j to compute i at DVFS k.
All energy and bandwidth depend on delivered work, never unused HB peak.
DVFS points may be time-shared; this relaxes finite schedules and transients.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog
from scipy import sparse


@dataclass(frozen=True)
class Fabric:
    name: str
    radius: int | None
    paid: bool = False
    area_fraction: float = 0.0
    static_w: float = 0.0


def fabric_cases(hw):
    a = hw["fabric_area_fraction"]
    s = hw["fabric_static_w_per_tile"]
    return [Fabric("local", 0), Fabric("neighbor_ideal", 1), Fabric("global_ideal", None),
            Fabric("mesh_paid", None, True, a, s),
            # Same reserved routing area/power budget, with remote service disabled.
            Fabric("local_matched", 0, True, a, s)]


def route(i: int, j: int, grid: int):
    """Directed XY path from memory port j to compute i."""
    y, x = divmod(j, grid)
    ty, tx = divmod(i, grid)
    path = []
    while x != tx:
        nx = x + (1 if tx > x else -1)
        path.append((y*grid+x, y*grid+nx)); x = nx
    while y != ty:
        ny = y + (1 if ty > y else -1)
        path.append((y*grid+x, ny*grid+x)); y = ny
    return path


def kernel(workload, tiling):
    b, m, k, e = [workload[key] for key in ["batch", "m", "k", "element_bytes"]]
    operations = 2*b*m*k
    # One weight read and one input/output transfer; ideal shared-input broadcast.
    byte_count = e*(m*k+b*k+b*m)
    return {"flops": operations, "bytes": byte_count, "intensity": operations/byte_count,
            "chunk_bytes": tiling["chunk_bytes"], "row_miss_fraction": tiling["row_miss_fraction"]}


def optimize(cfg, h, global_h, workload, tiling, fabric, thermal_mode,
             profile, placement="fixed"):
    hw = cfg["hardware"]
    tc = cfg["thermal"]
    grid = cfg["grid"]; n = grid*grid
    kr = kernel(workload, tiling); intensity = kr["intensity"]
    if kr["chunk_bytes"] * 2 > hw["sram_bytes_per_tile"]:
        raise ValueError("Double-buffered chunk exceeds private SRAM")
    if placement not in ("fixed", "free"):
        raise ValueError(placement)
    if not np.isclose(sum(profile), 1) or min(profile) < 0:
        raise ValueError("Demand fractions must be nonnegative and sum to one")
    if thermal_mode not in (0, 1, 2):
        raise ValueError(thermal_mode)
    flows = []
    paths = []
    for i in range(n):
        for j in range(n):
            path = route(i, j, grid)
            if fabric.radius is None or len(path) <= fabric.radius:
                for f in hw["dvfs_fractions"]:
                    flows.append((i, j, f)); paths.append(path)
    v = len(flows)
    # Last variable lambda is total completed useful TFLOP/s, shared by all shards.
    duty = np.zeros((n, v+1)); bank = np.zeros((n, v+1))
    queue = np.zeros((n, v+1)); power = np.zeros((2*n, v+1))
    links = sorted({edge for path in paths for edge in path})
    link_load = np.zeros((len(links), v+1)); link_idx = {edge:i for i,edge in enumerate(links)}
    dram_pj_byte = hw["dram_pj_per_byte"] + hw["activation_nj"]*1000*kr["row_miss_fraction"]/kr["chunk_bytes"]
    # Serial row-miss penalty amortized across independent banks in a group.
    bank_bw = 1/(1/hw["bank_group_peak_tb_s"] + hw["row_miss_penalty_ns"]*1000
                 *kr["row_miss_fraction"]/(kr["chunk_bytes"]*hw["independent_banks_per_group"]))
    for c, ((i,j,f), path) in enumerate(zip(flows, paths)):
        duty[i,c] = 1/(hw["tile_peak_tflops"]*(1-fabric.area_fraction)*f)
        bank[j,c] = 1/intensity  # TB/s, since both numerator units scale by 1e12.
        latency_ns = hw["read_latency_ns"] + (len(path)*hw["mesh_hop_latency_ns"] if fabric.paid else 0)
        # Little's Law: outstanding entries = B * latency / transaction size.
        queue[i,c] = 1000*latency_ns/(intensity*hw["transaction_bytes"])
        voltage = hw["voltage_floor_fraction"]+(1-hw["voltage_floor_fraction"])*f
        power[i,c] += hw["logic_pj_per_flop"]*voltage**2
        power[n+j,c] += dram_pj_byte/intensity
        if fabric.paid:
            for edge in path:
                link_load[link_idx[edge],c] += 1/intensity
                # Link energy split between its endpoints on the logic plane.
                for endpoint in edge:
                    power[endpoint,c] += hw["mesh_pj_per_byte_hop"]/(2*intensity)
    p0 = np.r_[np.full(n, hw["logic_static_w"]+fabric.static_w),
               np.full(n, hw["dram_static_w"])]
    inequalities = [duty, bank, queue]
    budgets = [np.ones(n), np.full(n, bank_bw), np.full(n, hw["outstanding_per_tile"])]
    if fabric.paid and links:
        inequalities.append(link_load); budgets.append(np.full(len(links), hw["mesh_link_tb_s"]))
    if thermal_mode:
        hm = h if thermal_mode == 2 else global_h
        allowed = np.r_[np.full(n, tc["logic_limit_c"]-tc["ambient_c"]),
                        np.full(n, tc["dram_limit_c"]-tc["ambient_c"])]
        room = allowed-hm@p0
        if min(room) < -1e-9:
            raise RuntimeError("Static power alone exceeds temperature limits")
        inequalities.append(hm@power); budgets.append(room)
    # bank is bytes; flow shares must be expressed in operations for completion.
    shards = bank*intensity
    if placement == "fixed":
        shards[:,-1] = -np.asarray(profile)
        equalities = shards
    else:
        equalities = np.zeros((1,v+1)); equalities[0,:v] = 1; equalities[0,-1] = -1
        # A stationary placement chosen before execution: bounded resident data share.
        bounds = shards.copy(); bounds[:,-1] = -hw["placement_max_fraction"]
        inequalities.append(bounds); budgets.append(np.zeros(n))
    c = np.zeros(v+1); c[-1] = -1
    au = np.vstack(inequalities); bu = np.concatenate(budgets)
    result = linprog(c, A_ub=sparse.csr_matrix(au), b_ub=bu,
                     A_eq=sparse.csr_matrix(equalities), b_eq=np.zeros(len(equalities)),
                     bounds=(0,None), method="highs")
    if not result.success:
        raise RuntimeError(f"LP solve failed: {result.message}")
    x = result.x
    feasibility = max(0.0,float(np.max(au@x-bu)),float(np.max(np.abs(equalities@x))))
    if feasibility > 1e-6:
        raise RuntimeError("LP solution violates original constraints")
    p = p0+power@x
    spatial_t = tc["ambient_c"]+h@p
    global_t = tc["ambient_c"]+global_h@p
    delivered = bank@x
    remote = sum(x[c] for c, path in enumerate(paths) if path)
    act_per_s = delivered*1e12*kr["row_miss_fraction"]/kr["chunk_bytes"]
    mapping = np.zeros((n,n)); rates = np.zeros((n,len(hw["dvfs_fractions"])))
    for c,(i,j,f) in enumerate(flows):
        mapping[i,j] += x[c]
        rates[i,hw["dvfs_fractions"].index(f)] += duty[i,c]*x[c]
    return {"tflops": float(x[-1]), "fabric": fabric.name, "thermal_mode": thermal_mode,
            "placement": placement, "workload": workload["name"], "tiling": tiling["name"],
            "intensity_flop_byte": intensity, "effective_bank_tb_s": bank_bw,
            "used_bandwidth_tb_s": float(delivered.sum()), "dram_activations_s": float(act_per_s.sum()),
            "remote_fraction": float(remote/x[-1]) if x[-1] else 0.0,
            "logic_power_w": float(p[:n].sum()), "dram_power_w": float(p[n:].sum()),
            "logic_peak_c": float(max(spatial_t[:n])), "dram_peak_c": float(max(spatial_t[n:])),
            "global_logic_c": float(global_t[0]), "global_dram_c": float(global_t[n]),
            "original_constraint_max_violation": feasibility,
            "bank_fractions": (delivered/delivered.sum()).tolist() if delivered.sum() else [0]*n,
            "power_w": p.tolist(), "temperature_c": spatial_t.tolist(),
            "mapping_tflops": mapping.tolist(), "dvfs_time_fractions": rates.tolist()}


def best_tiling(cfg, h, gh, workload, fabric, mode, profile, placement):
    choices = [optimize(cfg,h,gh,workload,t,fabric,mode,profile,placement) for t in cfg["tilings"]]
    best = max(choices, key=lambda x:x["tflops"])
    best["tiling_candidates_tflops"] = {x["tiling"]:x["tflops"] for x in choices}
    return best
