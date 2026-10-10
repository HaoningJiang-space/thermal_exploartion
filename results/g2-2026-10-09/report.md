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

| Cooling | Work mix | Thermal regime | Layout | Candidate | T0 net | T1 net | T2 net | T2/T1 | LP gate |
|---|---|---|---|---|---:|---:|---:|---:|---|
| gradient | prefill32_decode1 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.015903 | 1.015903 | False |
| gradient | prefill32_decode1 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.018699 | 1.018699 | False |
| gradient | prefill32_decode1 | phase_steady | independent_oracle | neighbor_paid | 0.980080 | 0.985472 | 0.997881 | 1.012591 | False |
| gradient | prefill32_decode1 | phase_steady | independent_oracle | mesh_paid | 0.980080 | 0.985472 | 0.998686 | 1.013409 | False |
| gradient | prefill32_decode1 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.010751 | 1.010751 | False |
| gradient | prefill32_decode1 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.013235 | 1.013235 | False |
| gradient | prefill32_decode1 | phase_steady | shared | neighbor_paid | 0.980080 | 0.985472 | 0.995089 | 1.009759 | False |
| gradient | prefill32_decode1 | phase_steady | shared | mesh_paid | 0.980080 | 0.985472 | 0.995089 | 1.009759 | False |
| gradient | prefill32_decode1 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.010751 | 1.010751 | False |
| gradient | prefill32_decode1 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.013235 | 1.013235 | False |
| gradient | prefill32_decode1 | phase_steady | migration | neighbor_paid | 0.980080 | 0.985472 | 0.995089 | 1.009759 | False |
| gradient | prefill32_decode1 | phase_steady | migration | mesh_paid | 0.980080 | 0.985472 | 0.995089 | 1.009759 | False |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.017369 | 1.017369 | False |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.017369 | 1.017369 | False |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | neighbor_paid | 0.980080 | 0.988575 | 0.996458 | 1.007974 | False |
| gradient | prefill32_decode1 | cycle_average | independent_oracle | mesh_paid | 0.980080 | 0.988575 | 0.996458 | 1.007974 | False |
| gradient | prefill32_decode1 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.023100 | 1.023100 | False |
| gradient | prefill32_decode1 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.029701 | 1.029701 | False |
| gradient | prefill32_decode1 | cycle_average | shared | neighbor_paid | 0.980080 | 0.988575 | 1.003111 | 1.014704 | False |
| gradient | prefill32_decode1 | cycle_average | shared | mesh_paid | 0.980080 | 0.988575 | 1.007102 | 1.018741 | False |
| gradient | prefill32_decode1 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.023100 | 1.023100 | False |
| gradient | prefill32_decode1 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.029701 | 1.029701 | False |
| gradient | prefill32_decode1 | cycle_average | migration | neighbor_paid | 0.980080 | 0.988575 | 1.003111 | 1.014704 | False |
| gradient | prefill32_decode1 | cycle_average | migration | mesh_paid | 0.980080 | 0.988575 | 1.007102 | 1.018741 | False |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000705 | 1.000705 | False |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.001126 | 1.001126 | False |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | neighbor_paid | 0.999544 | 0.988489 | 0.989286 | 1.000806 | False |
| gradient | prefill32_decode128 | phase_steady | independent_oracle | mesh_paid | 0.999544 | 0.988489 | 0.989308 | 1.000829 | False |
| gradient | prefill32_decode128 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000911 | 1.000911 | False |
| gradient | prefill32_decode128 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.001323 | 1.001323 | False |
| gradient | prefill32_decode128 | phase_steady | shared | neighbor_paid | 0.999544 | 0.988489 | 0.989558 | 1.001081 | False |
| gradient | prefill32_decode128 | phase_steady | shared | mesh_paid | 0.999544 | 0.988489 | 0.989558 | 1.001081 | False |
| gradient | prefill32_decode128 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000911 | 1.000911 | False |
| gradient | prefill32_decode128 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.001323 | 1.001323 | False |
| gradient | prefill32_decode128 | phase_steady | migration | neighbor_paid | 0.999544 | 0.988489 | 0.989558 | 1.001081 | False |
| gradient | prefill32_decode128 | phase_steady | migration | mesh_paid | 0.999544 | 0.988489 | 0.989558 | 1.001081 | False |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000295 | 1.000295 | False |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000649 | 1.000649 | False |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | neighbor_paid | 0.999544 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode128 | cycle_average | independent_oracle | mesh_paid | 0.999544 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode128 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000316 | 1.000316 | False |
| gradient | prefill32_decode128 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000752 | 1.000752 | False |
| gradient | prefill32_decode128 | cycle_average | shared | neighbor_paid | 0.999544 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode128 | cycle_average | shared | mesh_paid | 0.999544 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode128 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000316 | 1.000316 | False |
| gradient | prefill32_decode128 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000752 | 1.000752 | False |
| gradient | prefill32_decode128 | cycle_average | migration | neighbor_paid | 0.999544 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode128 | cycle_average | migration | mesh_paid | 0.999544 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.001932 | 1.001932 | False |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.002543 | 1.002543 | False |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | neighbor_paid | 0.998255 | 0.988250 | 0.989984 | 1.001754 | False |
| gradient | prefill32_decode32 | phase_steady | independent_oracle | mesh_paid | 0.998255 | 0.988250 | 0.990070 | 1.001841 | False |
| gradient | prefill32_decode32 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.002707 | 1.002707 | False |
| gradient | prefill32_decode32 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.003280 | 1.003280 | False |
| gradient | prefill32_decode32 | phase_steady | shared | neighbor_paid | 0.998255 | 0.988250 | 0.991006 | 1.002789 | False |
| gradient | prefill32_decode32 | phase_steady | shared | mesh_paid | 0.998255 | 0.988250 | 0.991006 | 1.002789 | False |
| gradient | prefill32_decode32 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.002707 | 1.002707 | False |
| gradient | prefill32_decode32 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.003280 | 1.003280 | False |
| gradient | prefill32_decode32 | phase_steady | migration | neighbor_paid | 0.998255 | 0.988250 | 0.991006 | 1.002789 | False |
| gradient | prefill32_decode32 | phase_steady | migration | mesh_paid | 0.998255 | 0.988250 | 0.991006 | 1.002789 | False |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000391 | 1.000391 | False |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000744 | 1.000744 | False |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | neighbor_paid | 0.998255 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode32 | cycle_average | independent_oracle | mesh_paid | 0.998255 | 0.988575 | 0.989033 | 1.000463 | False |
| gradient | prefill32_decode32 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000462 | 1.000462 | False |
| gradient | prefill32_decode32 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.001135 | 1.001135 | False |
| gradient | prefill32_decode32 | cycle_average | shared | neighbor_paid | 0.998255 | 0.988575 | 0.989032 | 1.000462 | False |
| gradient | prefill32_decode32 | cycle_average | shared | mesh_paid | 0.998255 | 0.988575 | 0.989032 | 1.000462 | False |
| gradient | prefill32_decode32 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000462 | 1.000462 | False |
| gradient | prefill32_decode32 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.001135 | 1.001135 | False |
| gradient | prefill32_decode32 | cycle_average | migration | neighbor_paid | 0.998255 | 0.988575 | 0.989032 | 1.000462 | False |
| gradient | prefill32_decode32 | cycle_average | migration | mesh_paid | 0.998255 | 0.988575 | 0.989032 | 1.000462 | False |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | neighbor_paid | 0.980080 | 0.986222 | 0.986096 | 0.999872 | False |
| uniform | prefill32_decode1 | phase_steady | independent_oracle | mesh_paid | 0.980080 | 0.986222 | 0.986096 | 0.999872 | False |
| uniform | prefill32_decode1 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | phase_steady | shared | neighbor_paid | 0.980080 | 0.986222 | 0.986096 | 0.999872 | False |
| uniform | prefill32_decode1 | phase_steady | shared | mesh_paid | 0.980080 | 0.986222 | 0.986096 | 0.999872 | False |
| uniform | prefill32_decode1 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | phase_steady | migration | neighbor_paid | 0.980080 | 0.986222 | 0.986096 | 0.999872 | False |
| uniform | prefill32_decode1 | phase_steady | migration | mesh_paid | 0.980080 | 0.986222 | 0.986096 | 0.999872 | False |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | neighbor_paid | 0.980080 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode1 | cycle_average | independent_oracle | mesh_paid | 0.980080 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode1 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | cycle_average | shared | neighbor_paid | 0.980080 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode1 | cycle_average | shared | mesh_paid | 0.980080 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode1 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode1 | cycle_average | migration | neighbor_paid | 0.980080 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode1 | cycle_average | migration | mesh_paid | 0.980080 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | neighbor_paid | 0.999544 | 0.989213 | 0.989102 | 0.999888 | False |
| uniform | prefill32_decode128 | phase_steady | independent_oracle | mesh_paid | 0.999544 | 0.989213 | 0.989102 | 0.999888 | False |
| uniform | prefill32_decode128 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | phase_steady | shared | neighbor_paid | 0.999544 | 0.989213 | 0.989102 | 0.999888 | False |
| uniform | prefill32_decode128 | phase_steady | shared | mesh_paid | 0.999544 | 0.989213 | 0.989102 | 0.999888 | False |
| uniform | prefill32_decode128 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | phase_steady | migration | neighbor_paid | 0.999544 | 0.989213 | 0.989102 | 0.999888 | False |
| uniform | prefill32_decode128 | phase_steady | migration | mesh_paid | 0.999544 | 0.989213 | 0.989102 | 0.999888 | False |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | neighbor_paid | 0.999544 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode128 | cycle_average | independent_oracle | mesh_paid | 0.999544 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode128 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | cycle_average | shared | neighbor_paid | 0.999544 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode128 | cycle_average | shared | mesh_paid | 0.999544 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode128 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode128 | cycle_average | migration | neighbor_paid | 0.999544 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode128 | cycle_average | migration | mesh_paid | 0.999544 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | neighbor_paid | 0.998255 | 0.988974 | 0.988860 | 0.999885 | False |
| uniform | prefill32_decode32 | phase_steady | independent_oracle | mesh_paid | 0.998255 | 0.988974 | 0.988860 | 0.999885 | False |
| uniform | prefill32_decode32 | phase_steady | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | phase_steady | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | phase_steady | shared | neighbor_paid | 0.998255 | 0.988974 | 0.988860 | 0.999885 | False |
| uniform | prefill32_decode32 | phase_steady | shared | mesh_paid | 0.998255 | 0.988974 | 0.988860 | 0.999885 | False |
| uniform | prefill32_decode32 | phase_steady | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | phase_steady | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | phase_steady | migration | neighbor_paid | 0.998255 | 0.988974 | 0.988860 | 0.999885 | False |
| uniform | prefill32_decode32 | phase_steady | migration | mesh_paid | 0.998255 | 0.988974 | 0.988860 | 0.999885 | False |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | neighbor_paid | 0.998255 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode32 | cycle_average | independent_oracle | mesh_paid | 0.998255 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode32 | cycle_average | shared | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | cycle_average | shared | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | cycle_average | shared | neighbor_paid | 0.998255 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode32 | cycle_average | shared | mesh_paid | 0.998255 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode32 | cycle_average | migration | neighbor_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | cycle_average | migration | global_ideal | 1.000000 | 1.000000 | 1.000000 | 1.000000 | False |
| uniform | prefill32_decode32 | cycle_average | migration | neighbor_paid | 0.998255 | 0.989299 | 0.989189 | 0.999889 | False |
| uniform | prefill32_decode32 | cycle_average | migration | mesh_paid | 0.998255 | 0.989299 | 0.989189 | 0.999889 | False |
