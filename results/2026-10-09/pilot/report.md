# Pilot screening results

These are optimized steady-state model bounds, not measured hardware performance.
All device/package costs are uncalibrated hypotheses. A B_candidate is a follow-up target, not proof of architectural novelty.

| Scenario | Workload | Placement | Candidate | T0 matched | T1 matched | T2 matched | T2/T1 | T2 net vs Local | Class |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| uniform | batch1_gemv | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch1_gemv | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch1_gemv | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | A_no_material_gain |
| uniform | batch1_gemv | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch1_gemv | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch1_gemv | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | A_no_material_gain |
| uniform | batch32_gemm | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch32_gemm | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch32_gemm | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9849 | A_no_material_gain |
| uniform | batch32_gemm | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch32_gemm | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| uniform | batch32_gemm | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9849 | A_no_material_gain |
| center_skew | batch1_gemv | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0178 | 1.0178 | 1.0178 | spatial_signal_below_net_gate |
| center_skew | batch1_gemv | fixed | global_ideal | 1.0000 | 1.0000 | 1.0202 | 1.0202 | 1.0202 | spatial_signal_below_net_gate |
| center_skew | batch1_gemv | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | A_no_material_gain |
| center_skew | batch1_gemv | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| center_skew | batch1_gemv | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| center_skew | batch1_gemv | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | A_no_material_gain |
| center_skew | batch32_gemm | fixed | neighbor_ideal | 1.8882 | 1.0972 | 1.2728 | 1.1601 | 1.2728 | C_or_mixed |
| center_skew | batch32_gemm | fixed | global_ideal | 1.8882 | 1.0972 | 1.2728 | 1.1601 | 1.2728 | C_or_mixed |
| center_skew | batch32_gemm | fixed | mesh_paid | 1.9466 | 1.0923 | 1.2611 | 1.1545 | 1.2451 | C_or_mixed |
| center_skew | batch32_gemm | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| center_skew | batch32_gemm | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | A_no_material_gain |
| center_skew | batch32_gemm | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9849 | A_no_material_gain |
| gradient_uniform | batch1_gemv | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0186 | 1.0186 | 1.0186 | spatial_signal_below_net_gate |
| gradient_uniform | batch1_gemv | fixed | global_ideal | 1.0000 | 1.0000 | 1.0284 | 1.0284 | 1.0284 | spatial_signal_below_net_gate |
| gradient_uniform | batch1_gemv | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9862 | A_no_material_gain |
| gradient_uniform | batch1_gemv | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0003 | 1.0003 | 1.0003 | A_no_material_gain |
| gradient_uniform | batch1_gemv | free | global_ideal | 1.0000 | 1.0000 | 1.0006 | 1.0006 | 1.0006 | A_no_material_gain |
| gradient_uniform | batch1_gemv | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9890 | A_no_material_gain |
| gradient_uniform | batch32_gemm | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.1644 | 1.1644 | 1.1644 | B_candidate |
| gradient_uniform | batch32_gemm | fixed | global_ideal | 1.0000 | 1.0000 | 1.1644 | 1.1644 | 1.1644 | B_candidate |
| gradient_uniform | batch32_gemm | fixed | mesh_paid | 1.0000 | 1.0000 | 1.1546 | 1.1546 | 1.1387 | B_candidate |
| gradient_uniform | batch32_gemm | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0217 | 1.0217 | 1.0217 | spatial_signal_below_net_gate |
| gradient_uniform | batch32_gemm | free | global_ideal | 1.0000 | 1.0000 | 1.0254 | 1.0254 | 1.0254 | spatial_signal_below_net_gate |
| gradient_uniform | batch32_gemm | free | mesh_paid | 1.0000 | 1.0000 | 1.0161 | 1.0161 | 1.0022 | spatial_signal_below_net_gate |

Paid fabric is compared to local_matched (same reserved routing area and idle power).
Ideal fabric is compared to local. Scheduling and DVFS are reoptimized for every cell.
Free placement optimizes resident bank fractions within the same per-bank data-capacity bound.
T0/T1 solutions can violate the physical spatial temperature limits; their physical temperatures remain reported.
Both architectures may use the tracker-bound row-miss option; it is an oracle upper bound, not an implementation of Voxel.

## Interpretation limits

This LP admits perfectly divisible work, fractional DVFS time sharing, ideal input broadcast, and no reduction overhead.
It has no transient thermal closure, temperature-dependent refresh/leakage, or cycle-level bank scheduler.
Free placement is selected for a stationary kernel. Real multi-operator capacity, relocation cost, and phase dependencies are absent.
The 4×4 coarse thermal mesh assumes one temperature per active region. Subregion hotspots and mesh convergence need validation.
A topology claim requires calibrated cost/thermal parameters, native HotSpot/3D-ICE cross-checks, and workload traces.
