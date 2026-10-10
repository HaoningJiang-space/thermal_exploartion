# Pilot screening results

These are optimized steady-state model bounds, not measured hardware performance.
Costs are uncalibrated. Fixed-layout and ideal-connection signals cannot pass the architecture gate.

| Scenario | Workload | Placement | Candidate | T0 matched | T1 scalar | T1 layer | T2 matched | T2/T1 layer | T2 net | Class |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| uniform | batch1_gemv | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch1_gemv | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch1_gemv | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | no_material_gain |
| uniform | batch1_gemv | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch1_gemv | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch1_gemv | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | no_material_gain |
| uniform | batch32_gemm | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch32_gemm | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch32_gemm | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9849 | no_material_gain |
| uniform | batch32_gemm | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch32_gemm | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| uniform | batch32_gemm | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9849 | no_material_gain |
| center_skew | batch1_gemv | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0178 | 1.0178 | 1.0178 | spatial_signal_below_gate |
| center_skew | batch1_gemv | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0202 | 1.0202 | 1.0202 | spatial_signal_below_gate |
| center_skew | batch1_gemv | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | no_material_gain |
| center_skew | batch1_gemv | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| center_skew | batch1_gemv | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| center_skew | batch1_gemv | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9892 | no_material_gain |
| center_skew | batch32_gemm | fixed | neighbor_ideal | 1.8882 | 1.0972 | 1.0978 | 1.2728 | 1.1594 | 1.2728 | fixed_placement_signal |
| center_skew | batch32_gemm | fixed | global_ideal | 1.8882 | 1.0972 | 1.0978 | 1.2728 | 1.1594 | 1.2728 | fixed_placement_signal |
| center_skew | batch32_gemm | fixed | mesh_paid | 1.9466 | 1.0923 | 1.0929 | 1.2611 | 1.1539 | 1.2451 | fixed_placement_signal |
| center_skew | batch32_gemm | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| center_skew | batch32_gemm | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | no_material_gain |
| center_skew | batch32_gemm | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9849 | no_material_gain |
| gradient_uniform | batch1_gemv | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0186 | 1.0186 | 1.0186 | spatial_signal_below_gate |
| gradient_uniform | batch1_gemv | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0284 | 1.0284 | 1.0284 | spatial_signal_below_gate |
| gradient_uniform | batch1_gemv | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9862 | no_material_gain |
| gradient_uniform | batch1_gemv | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0003 | 1.0003 | 1.0003 | no_material_gain |
| gradient_uniform | batch1_gemv | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0006 | 1.0006 | 1.0006 | no_material_gain |
| gradient_uniform | batch1_gemv | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9890 | no_material_gain |
| gradient_uniform | batch32_gemm | fixed | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.1644 | 1.1644 | 1.1644 | fixed_placement_signal |
| gradient_uniform | batch32_gemm | fixed | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.1644 | 1.1644 | 1.1644 | fixed_placement_signal |
| gradient_uniform | batch32_gemm | fixed | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.1546 | 1.1546 | 1.1387 | fixed_placement_signal |
| gradient_uniform | batch32_gemm | free | neighbor_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0217 | 1.0217 | 1.0217 | spatial_signal_below_gate |
| gradient_uniform | batch32_gemm | free | global_ideal | 1.0000 | 1.0000 | 1.0000 | 1.0254 | 1.0254 | 1.0254 | spatial_signal_below_gate |
| gradient_uniform | batch32_gemm | free | mesh_paid | 1.0000 | 1.0000 | 1.0000 | 1.0161 | 1.0161 | 1.0022 | no_material_gain |

Paid fabric is compared to local_matched (same reserved routing area and idle power).
Ideal fabric is compared to local. Scheduling and DVFS are reoptimized for every cell.
Free placement optimizes resident bank fractions within the same per-bank data-capacity bound.
Gate requires complete fixed/free controls, optimized free layout, paid costs, >5% net and matched gain,
T0 and T1_layer net gains <=1%, and T2/T1_layer net interaction >1%. Passing still requires execution/physical validation.
T1_scalar is retained only for legacy reproduction; T1_layer preserves both layer power sources and limits.
T0/T1 solutions can violate the physical spatial temperature limits; their physical temperatures remain reported.
Both architectures may use the tracker-bound row-miss option; it is an oracle upper bound, not an implementation of Voxel.

## Interpretation limits

This LP admits perfectly divisible work, fractional DVFS time sharing, ideal input broadcast, and no reduction overhead.
It has no transient thermal closure, temperature-dependent refresh/leakage, or cycle-level bank scheduler.
Free placement is selected for a stationary kernel. Real multi-operator capacity, relocation cost, and phase dependencies are absent.
The 4×4 coarse thermal mesh assumes one temperature per active region. Subregion hotspots and mesh convergence need validation.
A topology claim requires calibrated cost/thermal parameters, native HotSpot/3D-ICE cross-checks, and workload traces.
