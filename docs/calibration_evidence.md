# Evidence boundaries after the Mode B change

The historical reference-reproduction gate remains **NOT READY**. Architecture exploration
now proceeds with its own explicitly assumed contract. Unknown Stratum coefficients remain unknown.

| Evidence | Level | What it supports |
|---|---|---|
| 30.34 ×8×0.429 =104.12688 W | L0 | Same-paper reference accounting, not independent power calibration |
| G1/G2 common service and work-conservation checks | L0 | Implementation consistency, not achievable NPU throughput |
| Upstream standard-HBM3 regressions | L1 | Pinned software timing/controller behavior; original integration archive retained |
| Independent request IDs, duplicate-address and no-refresh concurrency controls | L1 | Request/command/return integrity and controlled execution reaction |
| Internal wide-port command replay | L1 | Legality under the same assumed definition; not Mono3D device verification |
| HiTS residual and Direct comparison | L0 | Assembled equations solved correctly; no package validation |
| Source labels and finite architecture sensitivity | Conditional architecture evidence | Relative choices within the stated model; no measured chip claim |
| Independent Stratum command-power holdout | Not available | No L2/L3 power-calibration claim |

[reference_workpoints.json](../configs/reference_workpoints.json) keeps rounded128 TFLOP/s,
topology131.072 TFLOP/s, MAC-only energy and Figure15 power categories separate.
The Figure Compute/MAC-peak ratio is approximately92.7%, but the body explicitly describes
full tensor-core utilization. Thus this ratio does not identify an observed activity factor.
Random-switching synthesis accounting, category definitions and rounded power figures may differ;
their exact relationship remains unresolved. No residual term is added to erase the6.51% difference.

Similarly,144.53−42.67=101.86 W and the approximate104 W must not be forced into a single exact observation.
A single aggregate observation has rank at most1 for ACT/PRE/RD/background/refresh coefficients;
its small residual cannot identify them. The new critical-value report makes this explicit.

Ayna/HBM-Power is an appropriate independent **standard HBM** method-validation path,
but its measured HBM current parameters are not imported into the Stratum-inspired contract.
That integration is deferred because the current user priority is the bounded Memory Service Organization experiment,
not full device calibration. No holdout power success is claimed.

Source: [Stratum sections6.1–6.2, Table3 and Figure15](https://arxiv.org/html/2510.05245v1).
