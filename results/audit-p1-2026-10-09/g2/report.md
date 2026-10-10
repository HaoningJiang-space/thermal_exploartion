# G2: Multi-Phase Shared-Placement Gate

Uncalibrated linear RC, two phases using one resident weight tensor, fixed completed work.
Migration charges both directions of the periodic cycle; startup and cycle-level arbitration remain unmodeled.

## Periodic gain bounds with shared resident layout

Candidate cycle-average LP time is a necessary lower bound. A peak-checked, paced Local schedule gives an admissible upper time bound.
Their ratio upper-bounds potential net gain within the fluid/constant-phase-power RC model. It is not a measured speedup.

| Cooling | Work mix | Layout | Candidate | Net periodic gain upper bound | Cannot reach 5% |
|---|---|---|---|---:|---|
| gradient | prefill32_decode1 | shared | neighbor_ideal | 1.023147 | True |
| gradient | prefill32_decode1 | shared | global_ideal | 1.029748 | True |
| gradient | prefill32_decode1 | shared | neighbor_paid | 1.003157 | True |
| gradient | prefill32_decode1 | shared | mesh_paid | 1.007149 | True |
| gradient | prefill32_decode1 | migration | neighbor_ideal | 1.023147 | True |
| gradient | prefill32_decode1 | migration | global_ideal | 1.029748 | True |
| gradient | prefill32_decode1 | migration | neighbor_paid | 1.003157 | True |
| gradient | prefill32_decode1 | migration | mesh_paid | 1.007149 | True |
| gradient | prefill32_decode128 | shared | neighbor_ideal | 1.002528 | True |
| gradient | prefill32_decode128 | shared | global_ideal | 1.002966 | True |
| gradient | prefill32_decode128 | shared | neighbor_paid | 0.991220 | True |
| gradient | prefill32_decode128 | shared | mesh_paid | 0.991220 | True |
| gradient | prefill32_decode128 | migration | neighbor_ideal | 1.002528 | True |
| gradient | prefill32_decode128 | migration | global_ideal | 1.002966 | True |
| gradient | prefill32_decode128 | migration | neighbor_paid | 0.991220 | True |
| gradient | prefill32_decode128 | migration | mesh_paid | 0.991220 | True |
| gradient | prefill32_decode32 | shared | neighbor_ideal | 1.000718 | True |
| gradient | prefill32_decode32 | shared | global_ideal | 1.001391 | True |
| gradient | prefill32_decode32 | shared | neighbor_paid | 0.989284 | True |
| gradient | prefill32_decode32 | shared | mesh_paid | 0.989284 | True |
| gradient | prefill32_decode32 | migration | neighbor_ideal | 1.000718 | True |
| gradient | prefill32_decode32 | migration | global_ideal | 1.001391 | True |
| gradient | prefill32_decode32 | migration | neighbor_paid | 0.989284 | True |
| gradient | prefill32_decode32 | migration | mesh_paid | 0.989284 | True |
| uniform | prefill32_decode1 | shared | neighbor_ideal | 1.000015 | True |
| uniform | prefill32_decode1 | shared | global_ideal | 1.000015 | True |
| uniform | prefill32_decode1 | shared | neighbor_paid | 0.989204 | True |
| uniform | prefill32_decode1 | shared | mesh_paid | 0.989204 | True |
| uniform | prefill32_decode1 | migration | neighbor_ideal | 1.000015 | True |
| uniform | prefill32_decode1 | migration | global_ideal | 1.000015 | True |
| uniform | prefill32_decode1 | migration | neighbor_paid | 0.989204 | True |
| uniform | prefill32_decode1 | migration | mesh_paid | 0.989204 | True |
| uniform | prefill32_decode128 | shared | neighbor_ideal | 1.000822 | True |
| uniform | prefill32_decode128 | shared | global_ideal | 1.000822 | True |
| uniform | prefill32_decode128 | shared | neighbor_paid | 0.990002 | True |
| uniform | prefill32_decode128 | shared | mesh_paid | 0.990002 | True |
| uniform | prefill32_decode128 | migration | neighbor_ideal | 1.000822 | True |
| uniform | prefill32_decode128 | migration | global_ideal | 1.000822 | True |
| uniform | prefill32_decode128 | migration | neighbor_paid | 0.990002 | True |
| uniform | prefill32_decode128 | migration | mesh_paid | 0.990002 | True |
| uniform | prefill32_decode32 | shared | neighbor_ideal | 1.000305 | True |
| uniform | prefill32_decode32 | shared | global_ideal | 1.000305 | True |
| uniform | prefill32_decode32 | shared | neighbor_paid | 0.989491 | True |
| uniform | prefill32_decode32 | shared | mesh_paid | 0.989491 | True |
| uniform | prefill32_decode32 | migration | neighbor_ideal | 1.000305 | True |
| uniform | prefill32_decode32 | migration | global_ideal | 1.000305 | True |
| uniform | prefill32_decode32 | migration | neighbor_paid | 0.989491 | True |
| uniform | prefill32_decode32 | migration | mesh_paid | 0.989491 | True |

## All LP interactions

T1_scalar is a legacy control. Spatial interaction uses T2/T1_layer; ideal connections and independent layouts cannot pass.
| Cooling | Work mix | Thermal regime | Layout | Candidate | T0 net | T1 scalar | T1 layer | T2 net | T2/T1 layer | Class |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| gradient | prefill32_decode1 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.015903 | 1.015903 | independent_layout_oracle |
| gradient | prefill32_decode1 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.018699 | 1.018699 | independent_layout_oracle |
| gradient | prefill32_decode1 | phase_steady | independent_oracle | neighbor_paid | 0.980080 | 0.985472 | 0.985348 | 0.997881 | 1.012719 | independent_layout_oracle |
| gradient | prefill32_decode1 | phase_steady | independent_oracle | mesh_paid | 0.980080 | 0.985472 | 0.985348 | 0.998686 | 1.013537 | independent_layout_oracle |
| gradient | prefill32_decode1 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.010751 | 1.010751 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.013235 | 1.013235 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | phase_steady | shared | neighbor_paid | 0.980080 | 0.985472 | 0.985348 | 0.995089 | 1.009887 | no_material_gain |
| gradient | prefill32_decode1 | phase_steady | shared | mesh_paid | 0.980080 | 0.985472 | 0.985348 | 0.995089 | 1.009887 | no_material_gain |
| gradient | prefill32_decode1 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.010751 | 1.010751 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.013235 | 1.013235 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | phase_steady | migration | neighbor_paid | 0.980080 | 0.985472 | 0.985348 | 0.995089 | 1.009887 | no_material_gain |
| gradient | prefill32_decode1 | phase_steady | migration | mesh_paid | 0.980080 | 0.985472 | 0.985348 | 0.995089 | 1.009887 | no_material_gain |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.017369 | 1.017369 | independent_layout_oracle |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.017369 | 1.017369 | independent_layout_oracle |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | neighbor_paid | 0.980080 | 0.988575 | 0.988464 | 0.996458 | 1.008087 | independent_layout_oracle |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | mesh_paid | 0.980080 | 0.988575 | 0.988464 | 0.996458 | 1.008087 | independent_layout_oracle |
| gradient | prefill32_decode1 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.023100 | 1.023100 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.029701 | 1.029701 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | cycle_average | shared | neighbor_paid | 0.980080 | 0.988575 | 0.988464 | 1.003111 | 1.014818 | no_material_gain |
| gradient | prefill32_decode1 | cycle_average | shared | mesh_paid | 0.980080 | 0.988575 | 0.988464 | 1.007102 | 1.018856 | no_material_gain |
| gradient | prefill32_decode1 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.023100 | 1.023100 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.029701 | 1.029701 | spatial_signal_below_gate |
| gradient | prefill32_decode1 | cycle_average | migration | neighbor_paid | 0.980080 | 0.988575 | 0.988464 | 1.003111 | 1.014818 | no_material_gain |
| gradient | prefill32_decode1 | cycle_average | migration | mesh_paid | 0.980080 | 0.988575 | 0.988464 | 1.007102 | 1.018856 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000705 | 1.000705 | independent_layout_oracle |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.001126 | 1.001126 | independent_layout_oracle |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | neighbor_paid | 0.999544 | 0.988489 | 0.988377 | 0.989286 | 1.000920 | independent_layout_oracle |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | mesh_paid | 0.999544 | 0.988489 | 0.988377 | 0.989308 | 1.000943 | independent_layout_oracle |
| gradient | prefill32_decode128 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000911 | 1.000911 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.001323 | 1.001323 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | shared | neighbor_paid | 0.999544 | 0.988489 | 0.988377 | 0.989558 | 1.001195 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | shared | mesh_paid | 0.999544 | 0.988489 | 0.988377 | 0.989558 | 1.001195 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000911 | 1.000911 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.001323 | 1.001323 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | migration | neighbor_paid | 0.999544 | 0.988489 | 0.988377 | 0.989558 | 1.001195 | no_material_gain |
| gradient | prefill32_decode128 | phase_steady | migration | mesh_paid | 0.999544 | 0.988489 | 0.988377 | 0.989558 | 1.001195 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000295 | 1.000295 | independent_layout_oracle |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000649 | 1.000649 | independent_layout_oracle |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | neighbor_paid | 0.999544 | 0.988575 | 0.988464 | 0.989033 | 1.000576 | independent_layout_oracle |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | mesh_paid | 0.999544 | 0.988575 | 0.988464 | 0.989033 | 1.000576 | independent_layout_oracle |
| gradient | prefill32_decode128 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000316 | 1.000316 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000752 | 1.000752 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | shared | neighbor_paid | 0.999544 | 0.988575 | 0.988464 | 0.989033 | 1.000575 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | shared | mesh_paid | 0.999544 | 0.988575 | 0.988464 | 0.989033 | 1.000575 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000316 | 1.000316 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000752 | 1.000752 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | migration | neighbor_paid | 0.999544 | 0.988575 | 0.988464 | 0.989033 | 1.000575 | no_material_gain |
| gradient | prefill32_decode128 | cycle_average | migration | mesh_paid | 0.999544 | 0.988575 | 0.988464 | 0.989033 | 1.000575 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.001932 | 1.001932 | independent_layout_oracle |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.002543 | 1.002543 | independent_layout_oracle |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | neighbor_paid | 0.998255 | 0.988250 | 0.988136 | 0.989984 | 1.001871 | independent_layout_oracle |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | mesh_paid | 0.998255 | 0.988250 | 0.988136 | 0.990070 | 1.001958 | independent_layout_oracle |
| gradient | prefill32_decode32 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.002707 | 1.002707 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.003280 | 1.003280 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | shared | neighbor_paid | 0.998255 | 0.988250 | 0.988136 | 0.991006 | 1.002905 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | shared | mesh_paid | 0.998255 | 0.988250 | 0.988136 | 0.991006 | 1.002905 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.002707 | 1.002707 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.003280 | 1.003280 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | migration | neighbor_paid | 0.998255 | 0.988250 | 0.988136 | 0.991006 | 1.002905 | no_material_gain |
| gradient | prefill32_decode32 | phase_steady | migration | mesh_paid | 0.998255 | 0.988250 | 0.988136 | 0.991006 | 1.002905 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000391 | 1.000391 | independent_layout_oracle |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000744 | 1.000744 | independent_layout_oracle |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | neighbor_paid | 0.998255 | 0.988575 | 0.988464 | 0.989033 | 1.000576 | independent_layout_oracle |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | mesh_paid | 0.998255 | 0.988575 | 0.988464 | 0.989033 | 1.000576 | independent_layout_oracle |
| gradient | prefill32_decode32 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000462 | 1.000462 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.001135 | 1.001135 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | shared | neighbor_paid | 0.998255 | 0.988575 | 0.988464 | 0.989032 | 1.000574 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | shared | mesh_paid | 0.998255 | 0.988575 | 0.988464 | 0.989032 | 1.000574 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000462 | 1.000462 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.001135 | 1.001135 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | migration | neighbor_paid | 0.998255 | 0.988575 | 0.988464 | 0.989032 | 1.000574 | no_material_gain |
| gradient | prefill32_decode32 | cycle_average | migration | mesh_paid | 0.998255 | 0.988575 | 0.988464 | 0.989032 | 1.000574 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | neighbor_paid | 0.980080 | 0.986222 | 0.986096 | 0.986096 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | mesh_paid | 0.980080 | 0.986222 | 0.986096 | 0.986096 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | shared | neighbor_paid | 0.980080 | 0.986222 | 0.986096 | 0.986096 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | shared | mesh_paid | 0.980080 | 0.986222 | 0.986096 | 0.986096 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | migration | neighbor_paid | 0.980080 | 0.986222 | 0.986096 | 0.986096 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | phase_steady | migration | mesh_paid | 0.980080 | 0.986222 | 0.986096 | 0.986096 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | neighbor_paid | 0.980080 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | mesh_paid | 0.980080 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode1 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | shared | neighbor_paid | 0.980080 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | shared | mesh_paid | 0.980080 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | migration | neighbor_paid | 0.980080 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode1 | cycle_average | migration | mesh_paid | 0.980080 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | neighbor_paid | 0.999544 | 0.989213 | 0.989102 | 0.989102 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | mesh_paid | 0.999544 | 0.989213 | 0.989102 | 0.989102 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | shared | neighbor_paid | 0.999544 | 0.989213 | 0.989102 | 0.989102 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | shared | mesh_paid | 0.999544 | 0.989213 | 0.989102 | 0.989102 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | migration | neighbor_paid | 0.999544 | 0.989213 | 0.989102 | 0.989102 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | phase_steady | migration | mesh_paid | 0.999544 | 0.989213 | 0.989102 | 0.989102 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | neighbor_paid | 0.999544 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | mesh_paid | 0.999544 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode128 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | shared | neighbor_paid | 0.999544 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | shared | mesh_paid | 0.999544 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | migration | neighbor_paid | 0.999544 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode128 | cycle_average | migration | mesh_paid | 0.999544 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | neighbor_paid | 0.998255 | 0.988974 | 0.988860 | 0.988860 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | mesh_paid | 0.998255 | 0.988974 | 0.988860 | 0.988860 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | shared | neighbor_paid | 0.998255 | 0.988974 | 0.988860 | 0.988860 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | shared | mesh_paid | 0.998255 | 0.988974 | 0.988860 | 0.988860 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | migration | neighbor_paid | 0.998255 | 0.988974 | 0.988860 | 0.988860 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | phase_steady | migration | mesh_paid | 0.998255 | 0.988974 | 0.988860 | 0.988860 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | neighbor_paid | 0.998255 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | mesh_paid | 0.998255 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | independent_layout_oracle |
| uniform | prefill32_decode32 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | shared | neighbor_paid | 0.998255 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | shared | mesh_paid | 0.998255 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | migration | neighbor_paid | 0.998255 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
| uniform | prefill32_decode32 | cycle_average | migration | mesh_paid | 0.998255 | 0.989299 | 0.989189 | 0.989189 | 1.000000 | no_material_gain |
