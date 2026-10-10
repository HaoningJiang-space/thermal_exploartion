# G3.1–G3.3 Model Calibration Gate

G4.1 shared-service regression passes. Stratum's known inventory and rounded aggregate anchors are reproduced.
G3.1 is partial, G3.2 is NOT_CALIBRATED, G3.3 physical HB contract is UNKNOWN. Prediction is disabled.

Shared service: 48 comparisons, max relative G1/G2 phase rate error 7.638e-14.

| Timing tier | tRCD ns | tRAS ns | tRC ns | Bank-only full-row ceiling TB/s |
|---|---:|---:|---:|---:|
| 1 | 2.29 | 29.79 | 34.56 | 30.34074 |
| 2 | 3.92 | 31.42 | 36.19 | 28.97419 |
| 3 | 5.99 | 33.49 | 38.26 | 27.40659 |
| 4 | 8.50 | 36.00 | 40.77 | 25.71930 |
| 5 | 11.44 | 38.94 | 43.71 | 23.98938 |
| 6 | 14.82 | 42.32 | 47.09 | 22.26749 |
| 7 | 18.63 | 46.13 | 50.90 | 20.60071 |
| 8 | 22.88 | 50.38 | 55.15 | 19.01316 |

The eight timing tiers partition rows within each bank; they are not eight independent copies of all banks.
These are necessary bank-cycle bounds; ACT/column domain, HB and queue constraints are not calibrated.

| Check | Derived | Reference | Relative error |
|---|---:|---:|---:|
| Fast bank-only TB/s | 30.340741 | 30.34 (body) | 0.0024% |
| Slow bank-only TB/s | 19.013164 | 19.01 (body) | 0.0166% |
| DRAM aggregate W at 30.34 TB/s | 104.126880 | 104 (approximate) | 0.1220% |
| Logic MAC + reported memory/comm W | 45.448910 | 42.67 | 6.5126% |
| Active Logic leaf area mm² | 76.550000 | 76.63 | -0.1044% |

Reported versus topology TFLOPS, body versus Table-3 bandwidth, and detailed versus approximate DRAM power remain separate in audit.json.
The 0.429 pJ/bit value is an aggregate device anchor, not an identified dynamic byte coefficient.
SRAM/NoC/controller/vector energy, ACT/PRE/background split and physical heat-source partition remain null.
No residual is silently assigned to a component; no DDR speed-bin timings or legacy cooling parameters are imported.

Legacy pilot: top-only convection permits at most 96 W when all active regions remain ≤85°C; 16 TB/s ×12 pJ/B already requires 192 W before other activity. This parameter combination forces throttling. It is not evidence about Stratum cooling.

Source: [Stratum v1, Tables 1/3 and Figure 15](https://arxiv.org/html/2510.05245v1).
G5 thermal closure is deferred; standard HBM3 integration is separate from the unknown Mono3D command model. Fabric remains closed.
