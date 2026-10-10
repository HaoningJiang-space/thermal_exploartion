"""Conservative finite-volume RC assembly and optional HiTS response extraction.

Nodes are layer/y/x ordered: logic, DRAM, passive spreader. Four-neighbor
in-plane conduction; insulated sides; convection from the spreader only.
This coarse model is a screening model, not a calibrated HB package.
"""
from __future__ import annotations

import hashlib
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu


# Keep archived integer identifiers stable; mode 3 is the added two-layer control.
THERMAL_MODES = (0, 1, 3, 2)
THERMAL_NAMES = {0: "T0", 1: "T1_scalar", 3: "T1_layer", 2: "T2"}


def layer_response(h):
    """Remove lateral position while retaining source and receiver layers.

    Each constant block is the response of the receiver's mean temperature to
    one total watt uniformly spread over the source layer. Thus R_rs is the
    mean of the n*n spatial coefficients, not their sum. Nonuniform source
    power is deliberately replaced by uniform loading within its layer.
    """
    h = np.asarray(h)
    if h.ndim != 2 or h.shape[0] != h.shape[1] or h.shape[0] % 2:
        raise ValueError("Expected a square response for two equally sized layers")
    n = h.shape[0] // 2
    r = h.reshape(2, n, 2, n).mean(axis=(1, 3))
    return np.repeat(np.repeat(r, n, axis=0), n, axis=1)


def thermal_control(h, scalar_h, mode):
    if mode not in THERMAL_NAMES:
        raise ValueError(mode)
    if mode == 3:
        return layer_response(h)
    return h if mode == 2 else scalar_h


def assemble(grid: int, cfg: dict) -> sparse.csr_matrix:
    n = grid * grid
    a = np.zeros((3 * n, 3 * n))

    def edge(i, j, conductance):
        a[i, i] += conductance
        a[j, j] += conductance
        a[i, j] -= conductance
        a[j, i] -= conductance

    area = cfg["tile_pitch_m"] ** 2
    lateral = [cfg["silicon_k_w_mk"] * cfg["logic_thickness_m"],
               cfg["silicon_k_w_mk"] * cfg["dram_thickness_m"],
               cfg["lid_k_w_mk"] * cfg["lid_thickness_m"]]
    # Half-cell resistances plus the explicitly parameterized bonding/TIM layers.
    r_ld = (cfg["logic_thickness_m"] / (2 * cfg["silicon_k_w_mk"])
            + cfg["bond_thickness_m"] / cfg["bond_k_w_mk"]
            + cfg["dram_thickness_m"] / (2 * cfg["silicon_k_w_mk"])) / area
    r_dl = (cfg["dram_thickness_m"] / (2 * cfg["silicon_k_w_mk"])
            + cfg["tim_thickness_m"] / cfg["tim_k_w_mk"]
            + cfg["lid_thickness_m"] / (2 * cfg["lid_k_w_mk"])) / area
    for z in range(3):
        for y in range(grid):
            for x in range(grid):
                i = z * n + y * grid + x
                if x + 1 < grid:
                    edge(i, i + 1, lateral[z])
                if y + 1 < grid:
                    edge(i, i + grid, lateral[z])
    for j in range(n):
        edge(j, n + j, cfg["vertical_scale"] / r_ld)
        edge(n + j, 2 * n + j, 1 / r_dl)
        x = j % grid
        factor = 1 + cfg["cooling_gradient"] * (2 * x / max(grid - 1, 1) - 1)
        if factor <= 0:
            raise ValueError("Cooling conductance must be positive")
        a[2 * n + j, 2 * n + j] += cfg["convection_w_m2k"] * area * factor
    return sparse.csr_matrix(a)


def response(grid: int, cfg: dict, backend: str = "scipy"):
    """Solve A H = Q with one unit-W source per active region; returns K/W."""
    a = assemble(grid, cfg)
    n = grid * grid
    q = np.eye(3 * n)[:, :2 * n]
    reference = splu(a.tocsc()).solve(q)
    record = {"backend": backend, "nodes": 3 * n,
              "equation_sha256": hashlib.sha256(a.toarray().tobytes()).hexdigest()}
    if backend == "hits":
        from hits import EquationConvention, HiTS, NodeRegion, ThermalOperator
        convention = EquationConvention("K", "s", "W/K", "W", "J/K", "none",
                                        "AT=b", "temperature rise; convection to zero rise")
        regions = tuple(NodeRegion(z*n, (z+1)*n, "SOLID", label, z)
                        for z, label in enumerate(["logic", "dram", "passive_lid"]))
        columns = []
        residuals = []
        with HiTS(rtol=1e-11, acceptance_rtol=1e-10) as solver:
            for j in range(2*n):
                query = ThermalOperator(a, q[:, j].copy(), None, convention,
                                        "layer-y-x", regions, "thermal-exploration-fv",
                                        "1", record["equation_sha256"],
                                        ("fixed geometry/material/cooling", "steady only", "unit-W source"))
                t, result = solver.solve_steady(query)
                if not result["accepted"]:
                    raise RuntimeError("HiTS original-equation acceptance failed")
                columns.append(t)
                residuals.append(result["relative_residual"])
        full = np.column_stack(columns)
        record["hits_max_residual"] = max(residuals)
        record["hits_vs_direct_max_abs_k_per_w"] = float(np.max(np.abs(full-reference)))
        if record["hits_vs_direct_max_abs_k_per_w"] > 1e-7:
            raise RuntimeError("HiTS/direct response mismatch")
    elif backend == "scipy":
        full = reference
    else:
        raise ValueError(backend)
    record["max_original_residual"] = float(np.max(np.abs(a @ full - q)))
    h = full[:2*n]
    if np.min(h) < -1e-10 or not np.allclose(h, h.T, atol=1e-8):
        raise RuntimeError("Passive response must be nonnegative and reciprocal")
    # Two-node layer-average model, exactly matched to uniform layer loading.
    layer_global = layer_response(h)[::n, ::n]
    # Thermal-1 is a single scalar R: match the hottest layer's mean response
    # under uniform equal-power sources. It contains no position information.
    scalar_r = float(max(layer_global.sum(axis=1))/2)
    global_h = np.full_like(h, scalar_r)
    record["global_layer_resistance_k_per_w"] = layer_global.tolist()
    record["global_scalar_resistance_k_per_w"] = scalar_r
    record["thermal_controls"] = {str(k): v for k, v in THERMAL_NAMES.items()}
    return h, global_h, record
